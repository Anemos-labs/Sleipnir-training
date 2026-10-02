"""Exception-flow questions in python, javascript, java and ruby: which exceptions can escape a function, and what a crash looks like."""
from __future__ import annotations

from fx import family

from . import _check as C
from . import _fam as F
from . import _ir as I
from . import _voice as V

EXC4 = ["python", "javascript", "java", "ruby"]


def _j(*parts) -> str:
    return " ".join(x for x in parts if x)


@family("explain-exception-escape", category="explain", lang="mixed", kind="greenfield", n=10,
        summary="which exception classes can escape a function (hierarchy-aware catch clauses, nested calls)")
def escape(rng, n):
    langs = F.lang_plan(rng, n, EXC4)
    tiers = F.tier_plan(rng, n, (0, 22, 34, 28, 16))
    for i in range(n):
        lang, tier = langs[i], tiers[i]

        def find(repo):
            p = repo.proj
            cands = []
            memo: dict = {}
            for f, fn in p.fns.items():
                if fn.kind != "fn":
                    continue
                esc = p.escapes(f, memo)
                naive = set()
                for g in [f] + p.reach(f):
                    for st in I._stmts(p.fns[g].body):
                        if st[0] == "raise":
                            naive.add(st[1])
                if 1 <= len(esc) <= 4 and esc != naive and len(p.reach(f)) >= {2: 2, 3: 3, 4: 4, 5: 6}[tier]:
                    cands.append((f, esc, naive))
            return rng.choice(cands) if cands else None

        repo, (f, esc, naive) = F.until(rng, lang, tier, find, tries=100, exc=True)
        p = repo.proj
        ans = sorted(esc)
        fi = repo.ident(f)
        fw = F.fn_word(lang)
        hier = ", ".join(f"{a} extends {b}" for a, b in p.excs if b)
        ask = rng.choice([
            f"Which exception classes can escape `{fi}`, meaning they can propagate out of it to its caller? Look through everything it calls, and remember that a `catch`/`except`/`rescue` for a base class also stops its subclasses. Assume any branch may be taken.",
            f"What can `{fi}` throw at its caller? List every exception class that might come out of a call to it after all the handlers below it have had their say (handlers for a parent class catch the child classes too; treat every branch as possible).",
        ])
        spec = C.json_spec({"escapes": C.jf("set", ans, norm="name")})
        fmt = f"Write `answer.json` as {{\"escapes\": [\"ClassName\", ...]}}, each class once, order irrelevant."
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "I'm deciding what the caller has to handle.", "Documenting failure modes for the runbook."]), tag=p.tag)
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{len(ans)}", prompt=prompt, difficulty=F.clamp(tier), start=repo.files, spec=spec, answer={"escapes": ans}, lang=lang,
                          tags=["exceptions", "static", "answer-json"], notes={"tier": tier, "target": f, "naive": sorted(naive), "files": len(repo.files)})


@family("explain-crash-message", category="explain", lang="mixed", kind="trace", n=9, mode="answer",
        summary="a run with given arguments dies with an uncaught exception: which exception, which message, which function raised it")
def crash(rng, n):
    langs = F.lang_plan(rng, n, EXC4)
    tiers = F.tier_plan(rng, n, (6, 20, 34, 26, 14))
    for i in range(n):
        lang, tier = langs[i], tiers[i]

        def find(repo):
            p = repo.proj
            for _ in range(60):
                a = rng.choice([rng.randint(2, 60), rng.randint(60, 2000), rng.randint(2000, 9000)])
                b = rng.randint(1, 40)
                try:
                    p.run(p.main_fid, [a, b])
                except I.Raised as r:
                    tr = I.Trace()
                    try:
                        p.run(p.main_fid, [a, b], tr)
                    except I.Raised:
                        pass
                    return (a, b, r, tr)
            return None

        repo, (a, b, r, tr) = F.until(rng, lang, tier, find, tries=60, exc=True)
        p = repo.proj
        cmd = repo.run_cmd(a, b)
        # the function that raised: the last executed function when it raised
        raised_in = _raiser(p, a, b)
        mode = rng.choice(["message", "message", "where"])
        if mode == "message":
            ask = rng.choice([
                f"Running `{cmd}` ends with an uncaught exception. What is the exception class and what does its message say?",
                f"`{cmd}` crashes instead of finishing. Tell me the exception type and the exact error message it reports.",
            ])
            fmt = "Quote the message exactly and name the class."
            contains = [r.msg, r.exc]
            gold = f"It dies with {r.exc}: {r.msg}"
        else:
            ask = rng.choice([
                f"`{cmd}` terminates with an uncaught exception. Which function raises it, what is its class and what is the message?",
                f"I ran `{cmd}` and it blew up. Find the function that raises the exception that kills it, and tell me its class and message.",
            ])
            fmt = f"Quote the message exactly, name the class, and put the raising function's name in brackets on a line `Raised in: [name]`."
            contains = [r.msg, r.exc, f"Raised in: [{repo.ident(raised_in)}]"]
            gold = f"{r.exc}: {r.msg}\n\nRaised in: [{repo.ident(raised_in)}]"
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "The ticket just says 'it crashes with big numbers'."]), tag=p.tag)
        yield C.say_task(slug=f"{i + 1:02d}-{lang}-{mode}", prompt=prompt, difficulty=F.clamp(tier), start=repo.files, contains=contains, gold=gold, lang=lang,
                         tags=["exceptions", "crash", mode], notes={"tier": tier, "args": [a, b], "exc": r.exc, "files": len(repo.files)})


def _raiser(p, a, b):
    """function id whose raise statement fired and killed the run"""
    tr = I.Trace()
    try:
        p.run(p.main_fid, [a, b], tr)
    except I.Raised:
        pass
    return tr.raised_in
