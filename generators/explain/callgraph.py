"""Call-graph questions: who calls a function, what it can reach, what is dead, where the call sites are."""
from __future__ import annotations

from fx import family

from . import _check as C
from . import _fam as F
from . import _voice as V

CALLER_BOUNDS = {1: (1, 3), 2: (2, 6), 3: (3, 9), 4: (5, 14), 5: (8, 24)}


def _prefix(rng, repo):
    s = F.intro(rng, repo.lang)
    return (s + " ") if s else ""


# --------------------------------------------------------------------------------------------------------------------
@family("explain-callers-transitive", category="explain", lang="mixed", kind="greenfield", n=12,
        summary="which functions call a given function, directly, transitively or with shortest call distance (six languages, answer.json)")
def callers(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n)
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        mode = {1: "direct", 2: rng.choice(["direct", "transitive"]), 3: "transitive", 4: rng.choice(["transitive", "distance"]),
                5: rng.choice(["distance", "transitive"])}[tier]
        lo, hi = CALLER_BOUNDS[tier]

        def find(repo):
            p = repo.proj
            cands = []
            cm = p.callers_map()
            for f, fn in p.fns.items():
                if fn.kind != "fn" or f == p.run_fid:
                    continue
                direct = cm[f]
                trans = p.reach(f, forward=False)
                if mode == "direct":
                    if 1 <= len(direct) <= 4 and len(trans) > len(direct):
                        cands.append(f)
                elif lo <= len(trans) <= hi and len(trans) > len(direct):
                    cands.append(f)
            if not cands:
                return None
            return rng.choice(cands)

        big = tier == 5 and rng.random() < 0.6
        repo, x = F.until(rng, lang, tier, find, dead=rng.choice([0, 1, 2]), big=big)
        p = repo.proj
        xi = repo.ident(x)
        fw = F.fn_word(lang)
        rule = rng.choice(F.NAME_RULE)
        if mode == "direct":
            ans = repo.idents(p.callers_map()[x])
            spec = C.json_spec({"callers": C.jf("set", ans, norm="name")})
            ask = rng.choice([
                f"Which {fw}s call `{xi}` directly, meaning a call to it appears in their own body?",
                f"List the {fw}s whose body contains a call to `{xi}` (just the direct callers; not the callers of those).",
                f"Find every place `{xi}` is called from and tell me the enclosing {fw}s.",
            ])
            fmt = f"Write `answer.json` as {{\"callers\": [\"name\", ...]}}, one entry per {fw}, order irrelevant. Ignore the test files. {rule}"
            sol = {"callers": ans}
            d = F.clamp(tier - 1)
        elif mode == "transitive":
            ans = repo.idents(p.reach(x, forward=False))
            spec = C.json_spec({"callers": C.jf("set", ans, norm="name")})
            ask = rng.choice([
                f"Which {fw}s can end up calling `{xi}`, whether directly or through a chain of other calls?",
                f"I need the whole upstream of `{xi}`: every {fw} from which some chain of calls reaches it, all the way up to the entry point.",
                f"Trace upward from `{xi}` and list every {fw} that depends on it, directly or indirectly.",
            ])
            fmt = (f"Write `answer.json` as {{\"callers\": [\"name\", ...]}}: each {fw} once, order irrelevant, not including `{xi}` itself. "
                   f"Ignore the test files. {rule}")
            sol = {"callers": ans}
            d = F.clamp(tier)
        else:
            dist = _distances(p, x)
            ans = {repo.ident(k): v for k, v in dist.items()}
            spec = C.json_spec({"distances": C.jf("map", ans, sub="int", knorm="name")})
            ask = rng.choice([
                f"For every {fw} that can reach `{xi}` through calls, how many call hops away is it? A {fw} that calls `{xi}` directly is 1, one that calls that {fw} is 2, and so on; if several chains exist, use the shortest.",
                f"Work out the call distance to `{xi}` from each of its callers, direct or indirect (1 means it calls `{xi}` itself; take the shortest chain when there are several).",
            ])
            fmt = f"Write `answer.json` as {{\"distances\": {{\"name\": hops, ...}}}}. Leave out `{xi}` itself and ignore tests. {rule}"
            sol = {"distances": ans}
            d = F.clamp(tier)
        why = rng.choice(["", "", "I'm about to change a helper's return value.", "A reviewer asked for the blast radius of a change I'm planning.",
                          "I'm writing a migration note for whoever depends on it.", "Something looks hot in the profiler and I want to know who feeds it."])
        prompt = V.frame(rng, _prefix(rng, repo) + ask, fmt, why, tag=p.tag)
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{mode}", prompt=prompt, difficulty=d, start=repo.files, spec=spec, answer=sol, lang=lang,
                          tags=["call-graph", mode, "answer-json"], notes={"mode": mode, "tier": tier, "target": x, "files": len(repo.files)})


def _distances(p, x):
    cm = p.callers_map()
    dist = {}
    frontier = [x]
    d = 0
    seen = {x}
    while frontier:
        d += 1
        nxt = []
        for f in frontier:
            for c in cm[f]:
                if c not in seen:
                    seen.add(c)
                    dist[c] = d
                    nxt.append(c)
        frontier = nxt
    return dist


# --------------------------------------------------------------------------------------------------------------------
@family("explain-callees-reach", category="explain", lang="mixed", kind="greenfield", n=9,
        summary="which functions a given function can reach by calls: all of them, only those in one package, or only the leaves")
def reach(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n, (10, 25, 30, 25, 10))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        mode = {1: "all", 2: "all", 3: rng.choice(["all", "leaves"]), 4: rng.choice(["filtered", "leaves", "all"]), 5: rng.choice(["filtered", "leaves"])}[tier]
        lo, hi = {1: (2, 5), 2: (3, 8), 3: (4, 12), 4: (7, 20), 5: (12, 40)}[tier]

        def find(repo):
            p = repo.proj
            cands = []
            for f, fn in p.fns.items():
                if fn.kind != "fn" or fn.mod == "cli":
                    continue
                r = p.reach(f)
                if not (lo <= len(r) <= hi):
                    continue
                if mode == "filtered":
                    pk = {p.fns[x].mod for x in r}
                    keys = sorted({p.mods[m].pkg or m for m in pk})
                    if len(keys) < 2:
                        continue
                cands.append(f)
            return rng.choice(cands) if cands else None

        big = tier == 5 and rng.random() < 0.6
        repo, x = F.until(rng, lang, tier, find, dead=rng.choice([0, 1]), big=big)
        p = repo.proj
        xi = repo.ident(x)
        fw = F.fn_word(lang)
        rule = rng.choice(F.NAME_RULE)
        r = p.reach(x)
        gk = ""
        if mode == "all":
            ans = repo.idents(r)
            ask = rng.choice([
                f"Starting from `{xi}`, which {fw}s can end up being called, directly or through further calls?",
                f"Which {fw}s are reachable from `{xi}` by following calls?",
                f"List everything `{xi}` depends on at run time in terms of {fw}s: its callees, their callees, and so on.",
            ])
            d = F.clamp(tier)
            key = "reachable"
        elif mode == "leaves":
            ans = repo.idents([f for f in r if not p.callees(f)])
            ask = rng.choice([
                f"Among the {fw}s that `{xi}` can reach through calls, which are the leaves, the ones that call no other {fw} of this project?",
                f"Follow every call chain that starts at `{xi}` down to its end; which {fw}s sit at the ends of those chains (they call nothing else from the project)?",
            ])
            d = F.clamp(tier)
            key = "leaves"
        else:
            groups = {}
            for f in r:
                m = p.mods[p.fns[f].mod]
                groups.setdefault(m.pkg or m.key, []).append(f)
            gk = rng.choice(sorted(g for g in groups if len(groups[g]) >= 1))
            ans = repo.idents(groups[gk])
            if p.layered:
                where = f"in the `{gk}` package (`{p.mods[p.fns[groups[gk][0]].mod].pkg}/`)"
            else:
                where = f"defined in the `{repo.rend.path[p.fns[groups[gk][0]].mod]}` file"
            ask = rng.choice([
                f"Which of the {fw}s that `{xi}` can reach (directly or through other calls) are {where}?",
                f"Restrict to what is {where}: which {fw}s can `{xi}` end up calling?",
            ])
            d = F.clamp(tier)
            key = "reachable"
        spec = C.json_spec({key: C.jf("set", ans, norm="name")})
        fmt = f"Write `answer.json` as {{\"{key}\": [\"name\", ...]}}, each {fw} once, without `{xi}` itself, order irrelevant. {rule}"
        why = rng.choice(["", "", "I want to know what to mock in a unit test.", "Trying to understand how much code a single call pulls in.",
                          "Doing a dependency review before extracting a package."])
        prompt = V.frame(rng, _prefix(rng, repo) + ask, fmt, why, tag=p.tag)
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{mode}", prompt=prompt, difficulty=d, start=repo.files, spec=spec, answer={key: ans}, lang=lang,
                          tags=["call-graph", "reach", mode, "answer-json"],
                          notes={"mode": mode, "tier": tier, "target": x, "group": gk, "files": len(repo.files)})


# --------------------------------------------------------------------------------------------------------------------
@family("explain-dead-functions", category="explain", lang="mixed", kind="greenfield", n=11,
        summary="dead code: functions unreachable from main, functions nothing calls, or functions only the tests keep alive")
def dead(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n, (8, 22, 32, 24, 14))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        mode = {1: "unreachable", 2: rng.choice(["unreachable", "no-callers"]), 3: rng.choice(["unreachable", "no-callers", "test-only"]),
                4: rng.choice(["unreachable", "test-only"]), 5: rng.choice(["unreachable", "test-only", "no-callers"])}[tier]
        k = {1: 1, 2: 2, 3: 3, 4: 4, 5: 6}[tier]

        def find(repo):
            p = repo.proj
            un = repo.dead_from_main()
            cm = p.callers_map()
            if mode == "unreachable":
                ans = un
            elif mode == "no-callers":
                tested_direct = {c.fid for c in p.cases}
                ans = [f for f in p.fns if p.fns[f].kind == "fn" and not cm[f] and f != p.run_fid and f not in tested_direct]
            else:
                tested = {c.fid for c in p.cases}
                reach_t = set()
                for t in tested:
                    reach_t |= set(p.reach(t)) | {t}
                ans = [f for f in un if f in reach_t]
            ans = [f for f in ans if p.fns[f].kind == "fn"]
            if 1 <= len(ans) <= {1: 3, 2: 5, 3: 8, 4: 12, 5: 18}[tier]:
                return ans
            return None

        big = tier == 5 and rng.random() < 0.6
        repo, found = F.until(rng, lang, tier, find, dead=k, tries=80, big=big)
        p = repo.proj
        fw = F.fn_word(lang)
        rule = rng.choice(F.NAME_RULE)
        ans = repo.idents(found)
        entry = f"`{repo.ident(p.main_fid)}`"
        if mode == "unreachable":
            ask = rng.choice([
                f"Which {fw}s in the project source are never reached when the program runs from {entry}? Follow calls transitively; the tests are not entry points.",
                f"I think there is dead code in here. List every {fw} that cannot be reached from {entry} by any chain of calls (ignore the tests).",
                f"Starting at {entry} and following every call, some {fw}s are never touched. Which ones?",
            ])
            d = F.clamp(tier)
        elif mode == "no-callers":
            ask = rng.choice([
                f"Which {fw}s are never called by anything, neither by other source {fw}s nor by tests? ({entry} itself does not count, nothing is expected to call it.)",
                f"List the {fw}s that have zero callers anywhere in the repository, tests included, apart from {entry}.",
            ])
            d = F.clamp(tier)
        else:
            ask = rng.choice([
                f"Some {fw}s are unreachable from {entry} but are still exercised by a test, so they look alive in a coverage report. Which {fw}s are those: unreachable from {entry}, yet executed by at least one test?",
                f"Find the {fw}s that only the test suite keeps alive: no chain of calls from {entry} reaches them, but some test calls them (directly or through other {fw}s).",
            ])
            d = F.clamp(tier)
        spec = C.json_spec({"functions": C.jf("set", ans, norm="name")})
        fmt = f"Write `answer.json` as {{\"functions\": [\"name\", ...]}}, one entry per {fw}, order irrelevant. {rule}"
        why = rng.choice(["", "", "Cleaning up before the next release.", "We're trying to cut the binary size.", "Someone wants to delete unused code and asked me to confirm."])
        prompt = V.frame(rng, _prefix(rng, repo) + ask, fmt, why, tag=p.tag)
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{mode}", prompt=prompt, difficulty=d, start=repo.files, spec=spec, answer={"functions": ans}, lang=lang,
                          tags=["call-graph", "dead-code", mode, "answer-json"], notes={"mode": mode, "tier": tier, "files": len(repo.files)})


# --------------------------------------------------------------------------------------------------------------------
@family("explain-callsites", category="explain", lang="mixed", kind="greenfield", n=11,
        summary="where is a function called (path:line of every call site), with or without the tests")
def callsites(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n)
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        with_tests = rng.random() < 0.45
        lo, hi = {1: (1, 3), 2: (2, 4), 3: (2, 6), 4: (3, 8), 5: (4, 10)}[tier]

        def find(repo):
            p = repo.proj
            cands = []
            for f, fn in p.fns.items():
                if fn.kind != "fn" or f == p.run_fid:
                    continue
                s = repo.sites_of(f, tests=with_tests)
                if lo <= len(s) <= hi and len({(a, b) for _, a, b in s}) == len(s):
                    cands.append(f)
            return rng.choice(cands) if cands else None

        repo, x = F.until(rng, lang, tier, find, big=(tier == 5 and rng.random() < 0.6))
        p = repo.proj
        xi = repo.ident(x)
        sites = repo.sites_of(x, tests=with_tests)
        ans = [f"{path}:{line}" for _, path, line in sites]
        fw = F.fn_word(lang)
        scope = "including the test files" if with_tests else "in the project source (not in the tests)"
        ask = rng.choice([
            f"I'm going to add a parameter to `{xi}`. Where does it have to be updated? Give me every line that calls it, {scope}.",
            f"List the exact call sites of `{xi}` as file and line number, {scope}. A definition is not a call.",
            f"Which lines call `{xi}`? I need `path:line` for each one, {scope}.",
        ])
        spec = C.json_spec({"sites": C.jf("set", ans, norm="site")})
        fmt = (f"Write `answer.json` as {{\"sites\": [\"path/to/file:LINE\", ...]}} with one entry per call, line numbers counted from 1 in the file as it is now. "
               f"{rng.choice(F.PATH_RULE)}")
        why = rng.choice(["", "", "Changing a signature next sprint.", "The linter flagged a deprecated argument and I need every caller."])
        prompt = V.frame(rng, _prefix(rng, repo) + ask, fmt, why, tag=p.tag)
        d = F.clamp(tier)
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{'tests' if with_tests else 'src'}", prompt=prompt, difficulty=d, start=repo.files, spec=spec,
                          answer={"sites": ans}, lang=lang, tags=["call-graph", "call-sites", "answer-json"],
                          notes={"tier": tier, "target": x, "with_tests": with_tests, "files": len(repo.files)})
