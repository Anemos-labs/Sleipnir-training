"""Questions that need the program to be *run in your head* (or for real): what it prints, how often something is called,
what is executed, which test breaks when something changes."""
from __future__ import annotations

from fx import family

from . import _check as C
from . import _fam as F
from . import _ir as I
from . import _repos as RP
from . import _voice as V


def _j(*parts) -> str:
    return " ".join(x for x in parts if x)


def _args(rng, lo=2, hi=60):
    return rng.randint(lo, hi), rng.randint(1, 30)


def _uniq(seq):
    out = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out


# --------------------------------------------------------------------------------------------------------------------
@family("explain-trace-output", category="explain", lang="mixed", kind="trace", n=12, mode="answer",
        summary="what does the program print for given command-line arguments: the whole output, one line of it, or the final value")
def trace_output(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n, (18, 28, 30, 16, 8))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        repo = RP.make_repo(rng, lang, tier, dead=rng.choice([0, 1, 2]))
        p = repo.proj
        for _ in range(30):
            a, b = _args(rng)
            val, tr = repo.run_main(a, b)
            emits = len(tr.emit_stacks)
            if emits >= {1: 2, 2: 3, 3: 4, 4: 6, 5: 8}[tier]:
                break
        cmd = repo.run_cmd(a, b)
        lines = tr.out
        mode = rng.choice(["full", "full", "last", "nth"]) if tier >= 2 else rng.choice(["full", "last"])
        if mode == "full":
            contains = _uniq(lines)
            # a bare number that also occurs inside another line is a weak check on its own
            contains = [c for c in contains if not (c.isdigit() and any(c in o for o in contains if o != c))]
            body = "\n".join(lines)
            ask = rng.choice([
                f"What does `{cmd}` print? Give me the output lines in order, exactly as they would appear.",
                f"I start the program with `{cmd}`. Reconstruct its complete standard output, line by line.",
                f"A teammate ran `{cmd}` but the CI log got truncated. What was printed?",
            ])
            fmt = "Put the output in a code block."
            gold = "Output:\n\n```\n" + body + "\n```"
            d = F.clamp(tier)
        elif mode == "last":
            label = rng.choice(["Result", "Final", "Last line"])
            contains = [f"{label}: [{lines[-1]}]"]
            ask = rng.choice([
                f"What is the very last line that `{cmd}` prints?",
                f"After `{cmd}` finishes, which number is on the final line of its output?",
            ])
            fmt = f"End your reply with `{label}: [VALUE]`."
            gold = f"It prints {lines[-1]} last.\n\n{label}: [{lines[-1]}]"
            d = F.clamp(tier)
        else:
            k = rng.randint(1, max(1, len(lines) - 2))
            contains = [lines[k]]
            ordinal = {1: "second", 2: "third", 3: "fourth", 4: "fifth", 5: "sixth", 6: "seventh", 7: "eighth", 8: "ninth", 9: "tenth"}.get(k, f"{k + 1}th")
            ask = rng.choice([
                f"When I run `{cmd}`, what is the {ordinal} line of the output?",
                f"Tell me the {ordinal} line that `{cmd}` prints.",
            ])
            fmt = "Quote that line exactly."
            gold = f"The {ordinal} line is:\n\n    {lines[k]}"
            d = F.clamp(tier)
        why = rng.choice(["", "", "I'm trying to understand the report format.", "I need to explain this output to a colleague."])
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, why, tag=p.tag)
        yield C.say_task(slug=f"{i + 1:02d}-{lang}-{mode}", prompt=prompt, difficulty=d, start=repo.files, contains=contains, gold=gold, lang=lang,
                         tags=["trace", "prints", mode], notes={"tier": tier, "mode": mode, "args": [a, b], "files": len(repo.files)})


# --------------------------------------------------------------------------------------------------------------------
@family("explain-call-count", category="explain", lang="mixed", kind="trace", n=9, mode="answer",
        summary="how many times is a function called during one run of the program (loops and branches decide)")
def call_count(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n, (8, 24, 34, 22, 12))
    for i in range(n):
        lang, tier = langs[i], tiers[i]

        def find(repo):
            p = repo.proj
            for _ in range(12):
                a, b = _args(rng)
                v, tr = repo.run_main(a, b)
                cnt: dict = {}
                for _, callee in tr.calls:
                    cnt[callee] = cnt.get(callee, 0) + 1
                static = {f: len(repo.sites_of(f)) for f in cnt}
                cands = [f for f, c in cnt.items() if 2 <= c <= 40 and p.fns[f].kind == "fn" and c != static[f]]
                if cands:
                    f = rng.choice(sorted(cands))
                    return (a, b, f, cnt[f], static[f])
            return None

        repo, (a, b, f, c, st) = F.until(rng, lang, tier, find, tries=60)
        p = repo.proj
        fi = repo.ident(f)
        cmd = repo.run_cmd(a, b)
        label = rng.choice(["Calls", "Count", "Times"])
        ask = rng.choice([
            f"During one run of `{cmd}`, how many times is `{fi}` called? Count every call that actually happens, not the number of places that mention it.",
            f"Run `{cmd}` (in your head or for real). How often does `{fi}` get invoked over the whole run?",
            f"How many calls to `{fi}` happen when the program is started as `{cmd}`? Loops and branches decide, so counting call sites in the source is not enough.",
        ])
        fmt = f"End your reply with `{label}: [N]`."
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "Wondering whether caching would pay off."]), tag=p.tag)
        d = F.clamp(tier)
        yield C.say_task(slug=f"{i + 1:02d}-{lang}-{fi.replace('_', '-')[:24]}", prompt=prompt, difficulty=d, start=repo.files, contains=[f"{label}: [{c}]"],
                         gold=f"`{fi}` is called {c} times in that run.\n\n{label}: [{c}]", lang=lang, tags=["trace", "call-count"],
                         notes={"tier": tier, "args": [a, b], "target": f, "static_sites": st, "files": len(repo.files)})


# --------------------------------------------------------------------------------------------------------------------
@family("explain-executed-functions", category="explain", lang="mixed", kind="greenfield", n=9,
        summary="which functions are actually entered during one run (static reachability is a superset: branches and loops decide)")
def executed(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n, (6, 22, 34, 24, 14))
    for i in range(n):
        lang, tier = langs[i], tiers[i]

        def find(repo):
            p = repo.proj
            reach = set(p.reach(p.main_fid)) | {p.main_fid}
            for _ in range(25):
                a, b = _args(rng, 1, 70)
                v, tr = repo.run_main(a, b)
                ex = set(tr.executed)
                gap = len(reach - ex)
                if gap >= {1: 1, 2: 2, 3: 2, 4: 3, 5: 4}[tier] and len(ex) >= 4:
                    return (a, b, sorted(ex), gap)
            return None

        repo, (a, b, ex, gap) = F.until(rng, lang, tier, find, tries=80)
        p = repo.proj
        ans = repo.idents(ex)
        cmd = repo.run_cmd(a, b)
        fw = F.fn_word(lang)
        ask = rng.choice([
            f"Which {fw}s are entered at least once when the program runs as `{cmd}`? Include `{repo.ident(p.main_fid)}` and `{repo.ident(p.run_fid)}`. Some {fw}s that can be reached in principle are skipped by this input.",
            f"List every {fw} that actually executes during `{cmd}`. A {fw} that is only called from a branch this input never takes does not count.",
            f"For the invocation `{cmd}`, which {fw}s of the project run? Not 'could run': the ones that do.",
        ])
        spec = C.json_spec({"executed": C.jf("set", ans, norm="name")})
        fmt = f"Write `answer.json` as {{\"executed\": [\"name\", ...]}}, each {fw} once, order irrelevant. {__import__('random').Random(0).choice(F.NAME_RULE) if False else rng.choice(F.NAME_RULE)}"
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "Trying to understand why coverage for this entry point is low."]), tag=p.tag)
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{len(ans)}", prompt=prompt, difficulty=F.clamp(tier), start=repo.files, spec=spec, answer={"executed": ans},
                          lang=lang, tags=["trace", "coverage", "answer-json"], notes={"tier": tier, "args": [a, b], "gap": gap, "files": len(repo.files)})


# --------------------------------------------------------------------------------------------------------------------
@family("explain-log-origin", category="explain", lang="mixed", kind="greenfield", n=9,
        summary="given the program's output, which function printed one line and what was the call chain at that moment")
def log_origin(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n, (4, 20, 36, 26, 14))
    for i in range(n):
        lang, tier = langs[i], tiers[i]

        def find(repo):
            p = repo.proj
            cm = p.callers_map()
            for _ in range(25):
                a, b = _args(rng)
                v, tr = repo.run_main(a, b)
                if len(tr.emit_stacks) < 3:
                    continue
                idx = [k for k, st in enumerate(tr.emit_stacks) if len(st) >= 3 and len(cm[st[-1]]) >= 1]
                if idx:
                    k = rng.choice(idx)
                    return (a, b, tr, k)
            return None

        repo, (a, b, tr, k) = F.until(rng, lang, tier, find, tries=80)
        p = repo.proj
        stack = tr.emit_stacks[k]
        ans_stack = [repo.ident(f) for f in stack]
        cmd = repo.run_cmd(a, b)
        fw = F.fn_word(lang)
        out = "\n".join(tr.out)
        text = tr.out[k]
        ask = rng.choice([
            f"Running `{cmd}` prints this:\n\n```\n{out}\n```\n\nThe line `{text}` looks wrong to me. Which {fw} printed it, and what was the chain of calls that led there, from `{repo.ident(p.main_fid)}` down to that {fw}?",
            f"This is the output of `{cmd}`:\n\n```\n{out}\n```\n\nI want to know where `{text}` comes from. Name the {fw} that prints it and the call chain active at that moment (outermost {fw} first, starting with `{repo.ident(p.main_fid)}`).",
        ])
        spec = C.json_spec({"printed_by": C.jf("str", ans_stack[-1], norm="name"), "stack": C.jf("list", ans_stack, norm="name")})
        fmt = (f"Write `answer.json` as {{\"printed_by\": \"name\", \"stack\": [\"name\", ...]}} where `stack` lists every {fw} on the call chain in order, "
               f"outermost first, ending with the one that printed the line. {rng.choice(F.NAME_RULE)}")
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, "", tag=p.tag)
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-line{k + 1}", prompt=prompt, difficulty=F.clamp(tier, 2, 5), start=repo.files, spec=spec,
                          answer={"printed_by": ans_stack[-1], "stack": ans_stack}, lang=lang, tags=["trace", "call-chain", "answer-json"],
                          notes={"tier": tier, "args": [a, b], "line": k + 1, "files": len(repo.files)})


# --------------------------------------------------------------------------------------------------------------------
@family("explain-return-value", category="explain", lang="mixed", kind="trace", n=10, mode="answer",
        summary="what does a function return for given arguments, several calls and branches deep (computed by running the model)")
def return_value(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n, (10, 26, 32, 20, 12))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        lo = {1: 1, 2: 2, 3: 3, 4: 5, 5: 7}[tier]

        def find(repo):
            p = repo.proj
            cands = [f for f, fn in p.fns.items() if fn.kind == "fn" and f != p.run_fid and len(p.reach(f)) >= lo]
            if not cands:
                return None
            f = rng.choice(sorted(cands))
            used = {tuple(a) for a in repo.proj.seed_info.get("test_args", {}).get(f, [])}
            for _ in range(10):
                args = [rng.randint(2, 40) for _ in p.fns[f].params]
                if tuple(args) not in used:
                    val = p.run(f, args)
                    return (f, args, val)
            return None

        repo, (f, args, val) = F.until(rng, lang, tier, find, tries=60)
        p = repo.proj
        fi = repo.ident(f)
        label = rng.choice(["Result", "Value", "Returns"])
        call = _render_call(repo, f, args)
        ask = rng.choice([
            f"What does `{call}` return? Work through the calls it makes.",
            f"Evaluate `{call}` by reading the code. What value comes back?",
            f"I call `{call}` from a scratch file. What number should I expect?",
        ])
        fmt = f"End your reply with `{label}: [N]`."
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "Checking my mental model before a rewrite."]), tag=p.tag)
        d = F.clamp(tier)
        yield C.say_task(slug=f"{i + 1:02d}-{lang}-{fi.replace('_', '-')[:22]}", prompt=prompt, difficulty=d, start=repo.files, contains=[f"{label}: [{val}]"],
                         gold=f"It returns {val}.\n\n{label}: [{val}]", lang=lang, tags=["trace", "evaluate"],
                         notes={"tier": tier, "target": f, "args": args, "reach": len(p.reach(f)), "files": len(repo.files)})


def _render_call(repo, f, args) -> str:
    fi = repo.ident(f)
    a = ", ".join(str(x) for x in args)
    if repo.lang == "java":
        return f"{repo.rend_class(repo.proj.fns[f].mod)}.{fi}({a})"
    if repo.lang == "ruby":
        return f"{repo.qual(f)}({a})"
    if repo.lang in ("javascript", "go", "python"):
        return f"{repo.qual(f)}({a})" if repo.lang != "python" else f"{fi}({a})"
    return f"{repo.qual(f)}({a})"


# --------------------------------------------------------------------------------------------------------------------
@family("explain-test-coverage", category="explain", lang="mixed", kind="greenfield", n=10,
        summary="which tests execute a function (through any depth of calls), or which functions no test ever executes")
def test_coverage(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n, (0, 22, 36, 26, 16))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        first = "which-tests" if tier <= 2 or rng.random() < 0.7 else "untested"
        for mode in (first, "which-tests" if first == "untested" else "untested"):
            def find(repo):
                p = repo.proj
                cov = {c.name: set(repo.coverage_of_case(c)) for c in p.cases}
                if len(cov) < 4:
                    return None
                if mode == "which-tests":
                    cands = []
                    for f, fn in p.fns.items():
                        if fn.kind != "fn":
                            continue
                        ts = [c for c, s in cov.items() if f in s]
                        direct = [c for c in p.cases if c.fid == f]
                        if 1 <= len(ts) <= {1: 3, 2: 4, 3: 7, 4: 10, 5: 14}[tier] and len(ts) > len(direct):
                            cands.append((f, ts))
                    return rng.choice(cands) if cands else None
                allc = set().union(*cov.values())
                un = sorted(f for f, fn in p.fns.items() if fn.kind == "fn" and f not in allc)
                if 1 <= len(un) <= {2: 5, 3: 8, 4: 12, 5: 18}[tier]:
                    return un
                return None
            try:
                repo, found = F.until(rng, lang, tier, find, tries=40 if mode == first else 120, dead=rng.choice([0, 1, 2]), big=(tier == 5 and rng.random() < 0.5))
                break
            except RuntimeError:
                continue
        else:
            raise RuntimeError("test-coverage: nothing found")
        p = repo.proj
        fw = F.fn_word(lang)
        nm = TEST_NAME[lang]
        if mode == "which-tests":
            f, ts = found
            ans = [repo.case_ident(next(c for c in p.cases if c.name == t)) for t in ts]
            ask = rng.choice([
                f"Which test cases end up executing `{repo.ident(f)}` when the suite runs? Count a test if `{repo.ident(f)}` runs at any depth below the function it calls, not only if it calls it directly.",
                f"Coverage says `{repo.ident(f)}` is exercised. By which tests? Include tests that reach it only indirectly through other {fw}s.",
            ])
            spec = C.json_spec({"tests": C.jf("set", ans, norm="exact")})
            fmt = f"Write `answer.json` as {{\"tests\": [\"name\", ...]}} using {nm}, order irrelevant."
            d = F.clamp(tier)
            ansobj = {"tests": ans}
        else:
            mi = repo.ident(p.main_fid)
            ans = [x for x in repo.idents(found) if x != mi]
            ask = rng.choice([
                f"Which {fw}s of the project source are never executed by any test (directly or through other {fw}s)? The launcher `{mi}` can be ignored.",
                f"List the {fw}s with zero test coverage: no test, however indirectly, ever runs them. Leave out `{mi}`.",
            ])
            spec = C.json_spec({"untested": C.jf("set", ans, norm="name")})
            fmt = f"Write `answer.json` as {{\"untested\": [\"name\", ...]}}. {rng.choice(F.NAME_RULE)}"
            d = F.clamp(tier)
            ansobj = {"untested": ans}
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "Trying to decide where to add tests next."]), tag=p.tag)
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{'which' if mode == 'which-tests' else 'untested'}", prompt=prompt, difficulty=d, start=repo.files, spec=spec,
                          answer=ansobj, lang=lang, tags=["coverage", mode, "answer-json"],
                          notes={"tier": tier, "mode": mode, "target": (found[0] if mode == "which-tests" else ""), "files": len(repo.files)})


TEST_NAME = {"python": "the `test_...` method name", "javascript": "the title string passed to `test(...)`", "go": "the `TestXxx` function name",
             "java": "the `testXxx` method name", "rust": "the `#[test]` function name", "ruby": "the `test_...` method name"}


# --------------------------------------------------------------------------------------------------------------------
@family("explain-change-impact", category="explain", lang="mixed", kind="greenfield", n=12,
        summary="which tests fail if a constant is changed or a function is replaced by a stub: impact analysis with exact lists")
def change_impact(rng, n):
    langs = F.lang_plan(rng, n)
    tiers = F.tier_plan(rng, n, (0, 24, 34, 26, 16))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        mode = rng.choice(["const", "const", "stub"])

        def find(repo):
            p = repo.proj
            allc = p.cases
            if len(allc) < 5:
                return None
            options = []
            if mode == "const":
                for mk, m in p.mods.items():
                    for name, val in m.consts:
                        options.append(("const", mk, name, val))
            else:
                for f, fn in p.fns.items():
                    if fn.kind == "fn" and f != p.run_fid:
                        options.append(("stub", f))
            rng.shuffle(options)
            for opt in options[:12]:
                if opt[0] == "const":
                    new = opt[3] + rng.choice([1, 2, 3, 5, 10])
                    fail = [c for c in allc if not p.case_passes(c, cover={(opt[1], opt[2]): new})]
                    spec = (opt[1], opt[2], opt[3], new)
                else:
                    f = opt[1]
                    fail = [c for c in allc if not p.case_passes(c, over={f: [("ret", I.N(0))]})]
                    spec = (f,)
                if 1 <= len(fail) <= {2: 4, 3: 6, 4: 10, 5: 16}[tier] and len(fail) < len(allc):
                    return (opt[0], spec, fail)
            return None

        repo, (kind, spec_, fail) = F.until(rng, lang, tier, find, tries=100)
        p = repo.proj
        ans = [repo.case_ident(c) for c in fail]
        nm = TEST_NAME[lang]
        if kind == "const":
            mk, name, old, new = spec_
            cname = repo.const_ident(mk, name)
            path = repo.rend.path[mk]
            ask = rng.choice([
                f"Suppose I change the constant `{cname}` in `{path}` from {old} to {new} and nothing else. Which tests in the suite would then fail?",
                f"I'm about to bump `{cname}` ({path}) from {old} to {new}. Predict exactly which tests break.",
            ])
            slug = f"{i + 1:02d}-{lang}-const"
        else:
            f = spec_[0]
            ask = rng.choice([
                f"If `{repo.ident(f)}` (in `{repo.path_of(f)}`) were stubbed out to always return 0, which tests would fail? Everything else stays as it is, and the stubbed code still compiles.",
                f"Imagine `{repo.ident(f)}` is replaced by a stub that just returns 0 for any input (assume everything still compiles). Which tests would no longer pass?",
            ])
            slug = f"{i + 1:02d}-{lang}-stub"
        spec = C.json_spec({"failing": C.jf("set", ans, norm="exact")})
        fmt = f"Write `answer.json` as {{\"failing\": [\"name\", ...]}} using {nm}; order irrelevant. Tests are assumed to pass today; judge every test on its own, even if the runner would stop early."
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "I want to know the blast radius before touching anything."]), tag=p.tag)
        yield C.file_task(slug=slug, prompt=prompt, difficulty=F.clamp(tier), start=repo.files, spec=spec, answer={"failing": ans}, lang=lang,
                          tags=["impact", kind, "answer-json"],
                          notes={"tier": tier, "kind": kind, "spec": list(spec_), "tests": len(p.cases), "failing": len(ans), "files": len(repo.files)})
