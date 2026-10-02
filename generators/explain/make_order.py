"""GNU make questions: in which order do the recipes run, what do variables expand to, which rules are skipped. The answer is what the real `make` prints."""
from __future__ import annotations

import fx
from fx import family

from . import _check as C
from . import _fam as F
from . import _voice as V

WORDS = {
    "docs": ["pages", "index", "assets", "toc", "feed", "search", "images", "styles", "sitemap", "glossary", "changelog", "archive"],
    "firmware": ["boot", "kernel", "drivers", "net", "ui", "audio", "storage", "image", "bundle", "sign", "flash", "tests"],
    "report": ["ingest", "clean", "join", "totals", "charts", "summary", "appendix", "cover", "pdf", "bundle", "lint", "publish"],
    "kiln": ["clay", "glaze", "bisque", "firing", "cooling", "sort", "pack", "label", "ship", "audit", "stock", "ledger"],
}
THEMES = list(WORDS)


def _recipe(t: str) -> str:
    return f'\t@echo "build {t}"'


@family("explain-make-order", category="explain", lang="bash", kind="greenfield", n=10,
        summary="what does `make` print: default goal, prerequisite order, existing files that skip a rule, phony targets, := versus =, pattern rules, include files")
def make_order(rng, n):
    tiers = F.tier_plan(rng, n, (10, 26, 32, 20, 12))
    for i in range(n):
        tier = tiers[i]
        for attempt in range(40):
            theme = rng.choice(THEMES)
            names = list(WORDS[theme])
            rng.shuffle(names)
            files: dict = {}
            lines: list = []
            feats = {1: [], 2: ["exists"], 3: ["exists", "vars"], 4: ["exists", "vars", "order_only", "pattern"], 5: ["exists", "vars", "order_only", "pattern", "include", "phony", "defer"]}[tier]
            k = {1: 5, 2: 7, 3: 9, 4: 11, 5: 12}[tier]
            tg = names[:k]
            goal_first = "all"
            # DAG: each target depends on 0-3 later-listed targets
            deps = {t: [] for t in tg}
            for ix, t in enumerate(tg):
                later = tg[ix + 1:]
                if later:
                    deps[t] = rng.sample(later, min(len(later), rng.choice([0, 1, 2, 2, 3])))
            # tier 1-2: leaf targets exist as files to be skipped
            exist = []
            if "exists" in feats:
                leaves = [t for t in tg if not deps[t]]
                exist = rng.sample(leaves, min(len(leaves), rng.choice([1, 2]))) if leaves else []
                for t in exist:
                    files[t] = "present\n"
            phony = []
            if "phony" in feats and exist:
                phony = [rng.choice(exist)] if rng.random() < 0.7 else []
            pats = []
            if "pattern" in feats:
                srcs = rng.sample(names[k:] + ["a", "b", "c"], 3)
                for s_ in srcs:
                    files[f"src/{s_}.txt"] = f"{s_}\n"
                pats = [f"{s_}.out" for s_ in srcs]
            order_only = None
            if "order_only" in feats:
                cand = [t for t in tg if t not in exist and deps[t]]
                if cand:
                    order_only = (rng.choice(cand), rng.choice([t for t in tg if t not in exist]))
            top = ["all"]
            goal_deps = rng.sample(tg, min(len(tg), 3))
            body: list = []
            headers: list = []
            # variables
            var_line = ""
            if "vars" in feats:
                lst = rng.sample(tg, 3)
                var_line = "STEPS := " + " ".join(lst)
                goal_deps = []
                use_sort = rng.random() < 0.5
                headers.append(var_line)
            if "defer" in feats:
                headers += ["MODE = $(PROFILE)", "PROFILE := debug", "SNAP := $(PROFILE)"]
            body.append("all: " + (" ".join(goal_deps) if goal_deps else ("$(sort $(STEPS))" if use_sort else "$(STEPS)")) + (" " + " ".join(pats) if pats else ""))
            if "defer" in feats:
                body.append('\t@echo "mode=$(MODE) snap=$(SNAP)"')
            else:
                body.append(_recipe("all"))
            for t in tg:
                if t in exist and t not in phony:
                    d = ""
                    body.append(f"{t}:")
                else:
                    d = " ".join(deps[t])
                    body.append(f"{t}: {d}".rstrip())
                if order_only and t == order_only[0]:
                    body[-1] = body[-1] + (" |" if "|" not in body[-1] else "") + f" {order_only[1]}"
                body.append(_recipe(t))
            if pats:
                body.append("%.out: src/%.txt")
                body.append('\t@echo "convert $< to $@"')
            phony_line = (".PHONY: " + " ".join(["all"] + phony)) if (phony or "phony" in feats) else ""
            goal_override = ""
            main_lines = []
            if "include" in feats:
                half = len(tg) // 2
                inc = [t for t in tg[:half]]
                incl_body = []
                keep_body = []
                # move the rules for the first half of the targets into mk/rules.mk
                i0 = 0
                rules: dict = {}
                cur = None
                for ln in body:
                    if ln and not ln.startswith("\t") and ":" in ln and not ln.startswith("%") and not ln.startswith("all"):
                        cur = ln.split(":")[0]
                        rules[cur] = [ln]
                    elif ln.startswith("\t") and cur:
                        rules[cur].append(ln)
                    else:
                        cur = None
                        keep_body.append(ln)
                moved = [t for t in inc if t in rules]
                for t in moved:
                    incl_body += rules.pop(t)
                for t, rl in rules.items():
                    keep_body += rl
                if moved:
                    files["mk/rules.mk"] = "\n".join(incl_body) + "\n"
                    body = keep_body
                    headers.append("include mk/rules.mk")
            # a rule placed before `all` changes the default goal
            first_rule_trap = False
            if tier >= 3 and rng.random() < 0.5:
                first_rule_trap = True
                extra = names[k] if k < len(names) else "setup"
                pre = [f"{extra}:", _recipe(extra), ""]
            else:
                pre = []
            mk = "\n".join([f"# Build driver for the {theme} pipeline."] + headers + [""] + ([phony_line] if phony_line else []) + pre + body) + "\n"
            files["Makefile"] = mk
            files["README.md"] = f"# {theme.capitalize()} pipeline\n\nRun `make` to build; every step just announces itself.\n"
            for goal in (None, "all"):
                cmd = "make" if goal is None else f"make {goal}"
                res = fx.run(files, cmd + " 2>&1", timeout=20)
                if res.ok:
                    break
            if not res.ok:
                continue
            asked_goal = None if first_rule_trap or rng.random() < 0.5 else rng.choice([t for t in tg if t not in exist or t in phony])
            cmd = "make" if asked_goal is None else f"make {asked_goal}"
            res = fx.run(files, cmd + " 2>&1", timeout=20)
            out = [ln for ln in res.out.strip().split("\n") if ln]
            if not res.ok or not (3 <= len(out) <= 22):
                continue
            break
        else:
            raise RuntimeError("make-order: no valid makefile")
        spec = C.json_spec({"lines": C.jf("list", out, norm="exact")})
        ask = rng.choice([
            f"What does running `{cmd}` in this directory print, line by line? Every recipe only echoes a line, and nothing else has been built yet.",
            f"I run `{cmd}` in the repo root. Which lines get printed, and in what order?",
            f"Work out the exact output of `{cmd}` here. (None of the build products exist, apart from what is committed in the tree.)",
        ])
        fmt = "Write `answer.json` as {\"lines\": [\"first line\", ...]} with every line GNU make prints to stdout, in order, exactly as printed."
        why = rng.choice(["", "", "Someone reordered the Makefile and CI output changed.", "I want to document the build sequence."])
        prompt = V.frame(rng, ask, fmt, why, tag="MAK")
        d = F.clamp(tier)
        yield C.file_task(slug=f"{i + 1:02d}-{theme}-{len(out)}-lines", prompt=prompt, difficulty=d, start=files, spec=spec, answer={"lines": out}, lang="bash",
                          tags=["make", "build-order", "answer-json"], notes={"tier": tier, "features": feats, "theme": theme, "goal": asked_goal or "default"})
