"""Import-graph questions: dependency closures, cycles, what a module exports, and duplicate helper names."""
from __future__ import annotations

from fx import family

from . import _check as C
from . import _fam as F
from . import _repos as RP
from . import _voice as V

DEP_DEF = {
    "python": "A module depends on another when it imports it (`import x`, `from x import y`, including relative imports and imports written inside functions).",
    "javascript": "A file depends on another when it `require`s it (including `require` calls inside functions).",
    "go": "A package depends on another when it imports it; each package here is one directory with one source file.",
    "java": "A class depends on another when it imports it or, inside its own package, refers to it by simple name.",
    "rust": "A module depends on another when it pulls something from it in with a `use crate::...` line.",
    "ruby": "A file depends on another when it loads it with `require_relative` (including a `require_relative` written inside a method).",
}
DEP_UNIT = {"python": "module", "javascript": "file", "go": "package", "java": "class", "rust": "module", "ruby": "file"}
UNIT_PL = {"module": "modules", "file": "files", "package": "packages", "class": "classes"}


def _j(*parts) -> str:
    return " ".join(x for x in parts if x)


def _closure(edges: dict, start: str) -> list:
    seen, stack = set(), [start]
    while stack:
        x = stack.pop()
        for y in edges.get(x, []):
            if y not in seen:
                seen.add(y)
                stack.append(y)
    seen.discard(start)
    return sorted(seen)


def _rev(edges: dict) -> dict:
    r = {k: [] for k in edges}
    for k, vs in edges.items():
        for v in vs:
            r.setdefault(v, []).append(k)
    return r


def _paths(repo, keys):
    return sorted(repo.rend.path[k] for k in keys)


# --------------------------------------------------------------------------------------------------------------------
@family("explain-import-deps", category="explain", lang="mixed", kind="greenfield", n=12,
        summary="module dependency questions: direct imports, the transitive closure, and who depends on a module (six languages)")
def deps(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n)
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        mode = {1: "direct", 2: rng.choice(["direct", "closure"]), 3: rng.choice(["closure", "dependents"]), 4: rng.choice(["closure", "dependents"]),
                5: rng.choice(["closure", "dependents"])}[tier]
        lo, hi = {1: (1, 3), 2: (2, 5), 3: (3, 8), 4: (5, 14), 5: (8, 20)}[tier]

        def find(repo):
            p = repo.proj
            edges = {k: [x for x in v] for k, v in p.import_edges().items()}
            rev = _rev(edges)
            cands = []
            for k, m in p.mods.items():
                if m.layer in ("errors",):
                    continue
                if mode == "direct":
                    ok = lo <= len(edges[k]) <= hi and m.layer != "util"
                elif mode == "closure":
                    c = _closure(edges, k)
                    ok = lo <= len(c) <= hi and len(c) > len(edges[k]) and m.layer != "util"
                else:
                    if m.layer == "cli":
                        continue
                    c = _closure(rev, k)
                    c = [x for x in c]
                    ok = lo <= len(c) <= hi and len(c) > len(rev.get(k, []))
                if ok:
                    cands.append(k)
            return rng.choice(cands) if cands else None

        repo, mk = F.until(rng, lang, tier, find, tries=60, big=(tier == 5 and rng.random() < 0.6))
        p = repo.proj
        edges = p.import_edges()
        unit = DEP_UNIT[lang]
        path = repo.rend.path[mk]
        rule = rng.choice(F.PATH_RULE)
        if mode == "direct":
            ans = _paths(repo, edges[mk])
            ask = rng.choice([
                f"Which source {UNIT_PL[unit]} does `{path}` depend on directly?",
                f"List the {UNIT_PL[unit]} that `{path}` pulls in directly (one hop, not their own dependencies).",
                f"What does `{path}` import? I only want the direct dependencies on other project {UNIT_PL[unit]}.",
            ])
            key, d = "files", F.clamp(tier)
        elif mode == "closure":
            ans = _paths(repo, _closure(edges, mk))
            ask = rng.choice([
                f"If I copy `{path}` into another project, which other source {UNIT_PL[unit]} of this repo must come along? Count everything it depends on, directly or through other {UNIT_PL[unit]}.",
                f"Give me the full transitive dependency set of `{path}`: every project {unit} it reaches by following dependencies.",
                f"Starting from `{path}`, which {UNIT_PL[unit]} of the project can it end up depending on?",
            ])
            key, d = "files", F.clamp(tier)
        else:
            rev = _rev(edges)
            ans = _paths(repo, _closure(rev, mk))
            ask = rng.choice([
                f"If I change the public interface of `{path}`, which other source {UNIT_PL[unit]} might break? Include everything that depends on it directly or through a chain of dependencies.",
                f"Which {UNIT_PL[unit]} depend on `{path}`, directly or indirectly?",
            ])
            key, d = "files", F.clamp(tier)
        extra = " Only the project's own source modules count (the files that define functions); tests, launcher scripts and aggregator files such as `__init__.py`, `lib.rs`, `mod.rs` or `lib/<name>.rb` do not." if mode == "dependents" else " Ignore the tests."
        spec = C.json_spec({key: C.jf("set", ans, norm="path")})
        fmt = f"Write `answer.json` as {{\"files\": [\"path\", ...]}}, each file once, order irrelevant. {rule}"
        ask = ask + " " + DEP_DEF[lang] + extra
        why = rng.choice(["", "", "I'm splitting this into two packages.", "We want to understand the layering before a refactor.", "A teammate added one more import last week and I want to see what it drags in."])
        prompt = V.frame(rng, ask, fmt, why, tag=p.tag)
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{mode}", prompt=prompt, difficulty=d, start=repo.files, spec=spec, answer={key: ans}, lang=lang,
                          tags=["imports", mode, "answer-json"], notes={"mode": mode, "tier": tier, "module": mk, "files": len(repo.files)})


# --------------------------------------------------------------------------------------------------------------------
def _scc_cycle(edges: dict):
    """the single non-trivial strongly connected component as an ordered simple cycle, or None"""
    index, low, on, stack, out = {}, {}, set(), [], []
    counter = [0]

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in edges.get(v, []):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                out.append(comp)

    for v in sorted(edges):
        if v not in index:
            strong(v)
    if len(out) != 1:
        return None
    comp = set(out[0])
    succ = {v: [w for w in edges[v] if w in comp] for v in comp}
    if any(len(s) != 1 for s in succ.values()):
        return None
    start = sorted(comp)[0]
    order = [start]
    while True:
        nx = succ[order[-1]][0]
        if nx == start:
            break
        order.append(nx)
    return order if len(order) == len(comp) else None


@family("explain-import-cycle", category="explain", lang="mixed", kind="greenfield", n=9,
        summary="find the circular dependency between modules, in python, javascript, java, rust and ruby (answer.json, ordered cycle)")
def cycle(rng, n):
    langs = F.lang_plan(rng, n, ["python", "javascript", "java", "rust", "ruby"])
    tiers = F.tier_plan(rng, n, (0, 15, 35, 30, 20))
    for i in range(n):
        lang, tier = langs[i], tiers[i]

        def find(repo):
            p = repo.proj
            order = _scc_cycle({k: [x for x in v if p.mods[x].layer != "errors"] for k, v in p.import_edges().items()})
            return order

        repo, order = F.until(rng, lang, tier, find, tries=120, cycle=True)
        p = repo.proj
        ans = [repo.rend.path[k] for k in order]
        first = ans.index(min(ans))
        ans = ans[first:] + ans[:first]
        unit = DEP_UNIT[lang]
        spec = C.json_spec({"cycle": C.jf("list", ans, norm="path")})
        fmt = (f"Write `answer.json` as {{\"cycle\": [\"path\", ...]}}: the files in the cycle in dependency order (each one depends on the next, and the last depends on the first), "
               f"starting with the file whose path sorts first alphabetically. {rng.choice(F.PATH_RULE)}")
        ask = rng.choice([
            f"There is a circular dependency among the {UNIT_PL[unit]} of this project. Which {UNIT_PL[unit]} are in the cycle, in order?",
            f"Something in here depends on itself through other {UNIT_PL[unit]}. Find the dependency cycle and list its members in order.",
            f"Our import-graph checker complains about a cycle but not where it is. Which {UNIT_PL[unit]} form it?",
        ])
        ask += " " + DEP_DEF[lang] + " The cycle is a single loop with no shortcuts."
        why = rng.choice(["", "", "The failure only shows up when I load one particular file first.", "The linter says 'cycle detected' without printing the cycle."])
        prompt = V.frame(rng, ask, fmt, why, tag=p.tag)
        d = F.clamp(tier, 2, 5)
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{len(order)}-cycle", prompt=prompt, difficulty=d, start=repo.files, spec=spec, answer={"cycle": ans}, lang=lang,
                          tags=["imports", "cycle", "answer-json"], notes={"tier": tier, "length": len(order), "files": len(repo.files)})


# --------------------------------------------------------------------------------------------------------------------
EXPORT_DEF = {
    "python": "A module's exports are the names `from <module> import *` brings in: its functions that do not start with an underscore, restricted to `__all__` when the module defines one.",
    "javascript": "A file's exports are the functions listed in its `module.exports`.",
    "go": "A package's exports are its exported (capitalised) functions.",
    "java": "A class's exports are its `public static` methods.",
    "rust": "A module's exports are its `pub fn` functions.",
    "ruby": "A module's exports are its public module methods (anything made private with `private_class_method` is not exported).",
}


@family("explain-module-exports", category="explain", lang="mixed", kind="greenfield", n=11,
        summary="what a module exports (honouring __all__, module.exports, capitalisation, pub, private_class_method) and which exports nobody else uses")
def exports(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n, (12, 28, 30, 20, 10))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        mode = "exports" if tier <= 2 else rng.choice(["exports", "unused", "unused"])

        def find(repo):
            p = repo.proj
            cm = p.callers_map()
            cands = []
            for k, m in p.mods.items():
                if m.layer in ("errors", "cli"):
                    continue
                ex = [f for f in m.fids if p.fns[f].kind == "fn" and f in {x for x in repo_exports(repo, k)}]
                if mode == "exports":
                    if lang == "python" and tier >= 2 and not m.all_list and rng.random() < 0.6:
                        continue
                    if 2 <= len(ex) <= 8 and (len([f for f in m.fids if p.fns[f].kind == "fn"]) > len(ex) or m.all_list):
                        cands.append(k)
                else:
                    unused = [f for f in ex if not any(p.fns[c].mod != k for c in cm[f])]
                    if ex and 1 <= len(unused) <= 6 and len(unused) < len(ex):
                        cands.append(k)
            return rng.choice(cands) if cands else None

        repo, mk = F.until(rng, lang, tier, find, tries=80, dead=rng.choice([0, 1, 2]))
        p = repo.proj
        path = repo.rend.path[mk]
        ex = [f for f in repo_exports(repo, mk)]
        fw = F.fn_word(lang)
        rule = rng.choice(F.NAME_RULE)
        if mode == "exports":
            ans = repo.idents(ex)
            ask = rng.choice([
                f"Which {fw}s does `{path}` export?",
                f"What is the public surface of `{path}`? List the {fw}s another file could use from it.",
                f"List the {fw}s that `{path}` exposes to the rest of the project.",
            ])
            d = F.clamp(tier)
            key = "exports"
        else:
            cm = p.callers_map()
            ans = repo.idents([f for f in ex if not any(p.fns[c].mod != mk for c in cm[f])])
            ask = rng.choice([
                f"Which exported {fw}s of `{path}` are never used by any other source file (using them from inside the same file or from tests does not count)?",
                f"`{path}` exports more than the rest of the project actually uses. Which of its exported {fw}s have no caller outside `{path}` (tests ignored)?",
            ])
            d = F.clamp(tier)
            key = "unused"
        ask += " " + EXPORT_DEF[lang]
        spec = C.json_spec({key: C.jf("set", ans, norm="name")})
        fmt = f"Write `answer.json` as {{\"{key}\": [\"name\", ...]}}, order irrelevant. {rule}"
        why = rng.choice(["", "", "Preparing an API review.", "I want to shrink the public API before 1.0."])
        prompt = V.frame(rng, ask, fmt, why, tag=p.tag)
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{mode}", prompt=prompt, difficulty=d, start=repo.files, spec=spec, answer={key: ans}, lang=lang,
                          tags=["exports", mode, "answer-json"], notes={"mode": mode, "tier": tier, "module": mk, "files": len(repo.files)})


def repo_exports(repo, mk) -> list:
    """function ids that are exported by module mk in its language"""
    p = repo.proj
    m = p.mods[mk]
    fids = [f for f in m.fids if p.fns[f].public and p.fns[f].kind == "fn"]
    if repo.lang == "python" and m.all_list:
        fids = [f for f in fids if f in m.all_names]
    return fids


# --------------------------------------------------------------------------------------------------------------------
@family("explain-surface-count", category="explain", lang="mixed", kind="lookup", n=9, mode="answer",
        summary="how many functions does a package (or the whole project) export in total; the final message must carry the count")
def surface_count(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n, (6, 22, 34, 24, 14))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        repo = RP.make_repo(rng, lang, tier)
        p = repo.proj
        if p.layered:
            pk = rng.choice(["util", "core", "services"])
            mods = [k for k, m in p.mods.items() if m.pkg == pk and m.layer != "errors"]
            where = f"the modules under `{pk}/`" if lang not in ("java", "go", "rust") else {"java": f"the classes in the `{pk}` package", "go": f"the packages under `internal/{pk}/`", "rust": f"the modules under `src/{pk}/`"}[lang]
        else:
            pk = ""
            mods = [k for k, m in p.mods.items() if m.layer not in ("errors", "cli")]
            where = "all the library modules (everything except the command line module `cli`)"
        total = sum(len(repo_exports(repo, k)) for k in mods)
        label = rng.choice(["Total", "Count", "Exported"])
        ask = rng.choice([
            f"How many functions are exported in total by {where}? {EXPORT_DEF[lang]}",
            f"Count the exported functions across {where}. {EXPORT_DEF[lang]}",
            f"I'm auditing the public API. How many functions do {where} expose together? {EXPORT_DEF[lang]}",
        ])
        fmt = f"End your reply with a line `{label}: [N]` where N is the number."
        prompt = V.frame(rng, ask, fmt, rng.choice(["", "", "Needed for the API review."]), tag=p.tag)
        d = F.clamp(tier)
        yield C.say_task(slug=f"{i + 1:02d}-{lang}-{total}", prompt=prompt, difficulty=d, start=repo.files, contains=[f"{label}: [{total}]"],
                         gold=f"The modules export {total} functions in total.\n\n{label}: [{total}]", lang=lang,
                         tags=["exports", "count"], notes={"tier": tier, "package": pk, "total": total, "files": len(repo.files)})


# --------------------------------------------------------------------------------------------------------------------
def _twins(p):
    names: dict = {}
    for f, fn in p.fns.items():
        if fn.kind == "fn":
            names.setdefault(fn.name, []).append(f)
    return {n: fs for n, fs in names.items() if len(fs) > 1}


@family("explain-twin-resolution", category="explain", lang="mixed", kind="lookup", n=9, mode="answer",
        summary="two modules define a helper with the same name: which definition does a given function actually call (import resolution)")
def twin_resolution(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n, (0, 20, 35, 30, 15))
    for i in range(n):
        lang, tier = langs[i], tiers[i]

        def find(repo):
            p = repo.proj
            tw = _twins(p)
            cands = []
            for name, fs in tw.items():
                for f in fs:
                    for g in p.callers_map()[f]:
                        gf = p.fns[g]
                        called_twins = [x for x in fs if x in p.callees(g)]
                        if len(called_twins) == 1 and gf.kind == "fn" and gf.mod != p.fns[f].mod and gf.name != p.fns[f].name:
                            cands.append((g, f))
            return rng.choice(cands) if cands else None

        repo, (g, f) = F.until(rng, lang, tier, find, tries=120, dup=2 + tier // 2)
        p = repo.proj
        name = repo.ident(f)
        tw = _twins(p)[p.fns[f].name]
        path = repo.rend.path[p.fns[f].mod]
        fw = F.fn_word(lang)
        ask = rng.choice([
            f"There are several `{name}` {fw}s in this repo, defined in different files. Which file defines the one that `{repo.ident(g)}` calls?",
            f"`{repo.ident(g)}` calls something named `{name}`, but that name is defined in more than one file. Which file's `{name}` does it actually end up calling?",
            f"Name clash alert: `{name}` exists in {len(tw)} places. Following the imports, which file holds the `{name}` that `{repo.ident(g)}` uses?",
        ])
        fmt = f"Give the path of that file relative to the repo root in square brackets on the last line, like `File: [dir/file.ext]`."
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "Grep finds several definitions and I can't tell which is live."]), tag=p.tag)
        d = F.clamp(tier)
        yield C.say_task(slug=f"{i + 1:02d}-{lang}-{name.replace('_', '-')}", prompt=prompt.strip(), difficulty=d, start=repo.files, contains=[f"File: [{path}]"],
                         gold=f"`{repo.ident(g)}` calls the `{name}` defined in `{path}`.\n\nFile: [{path}]", lang=lang, tags=["name-resolution", "imports"],
                         notes={"tier": tier, "caller": g, "callee": f, "twins": tw, "files": len(repo.files)})


@family("explain-twin-callers", category="explain", lang="mixed", kind="greenfield", n=8,
        summary="two modules define a helper with the same name: list the callers of the one defined in a given file")
def twin_callers(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n, (0, 15, 35, 30, 20))
    for i in range(n):
        lang, tier = langs[i], tiers[i]

        def find(repo):
            p = repo.proj
            tw = _twins(p)
            dupnames = set(tw)
            cands = []
            cm = p.callers_map()
            for name, fs in tw.items():
                for f in fs:
                    cs = cm[f]
                    idents = [repo.ident(c) for c in cs]
                    if 2 <= len(cs) <= 7 and len(set(idents)) == len(idents) and not any(p.fns[c].name in dupnames for c in cs):
                        # the other twin must also have callers, so a lazy name search gives a wrong answer
                        others = [x for x in fs if x != f]
                        if any(cm[o] for o in others):
                            cands.append(f)
            return rng.choice(cands) if cands else None

        repo, f = F.until(rng, lang, tier, find, tries=150, dup=2 + tier // 2)
        p = repo.proj
        name = repo.ident(f)
        path = repo.rend.path[p.fns[f].mod]
        ans = repo.idents(p.callers_map()[f])
        fw = F.fn_word(lang)
        ask = rng.choice([
            f"`{name}` is defined in more than one file. Which {fw}s call the version that lives in `{path}`? Calls to the other definitions do not count.",
            f"Two files both define `{name}`. List the {fw}s that call the one in `{path}` (and only that one).",
        ])
        spec = C.json_spec({"callers": C.jf("set", ans, norm="name")})
        fmt = f"Write `answer.json` as {{\"callers\": [\"name\", ...]}}, order irrelevant, ignoring tests. {rng.choice(F.NAME_RULE)}"
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "I'm about to delete the other copy."]), tag=p.tag)
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{name.replace('_', '-')}", prompt=prompt.strip(), difficulty=F.clamp(tier), start=repo.files, spec=spec,
                          answer={"callers": ans}, lang=lang, tags=["name-resolution", "imports", "answer-json"],
                          notes={"tier": tier, "callee": f, "files": len(repo.files)})
