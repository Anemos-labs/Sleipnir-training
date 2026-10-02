"""Review tasks: a change with planted defects, rendered from slot modules, checked by ``_check_review.py``."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from fx import Task, run
from fx.lib import BUILD
from fx.run import merged

from ._slots import Module, auto_nit, description, render, slot_texts, unified_diff

CHECKER = Path(__file__).with_name("_check_review.py").read_text(encoding="utf-8")
VERIFY = "python3 _verify/check.py"
CATS = "logic, security, concurrency, resource-leak, api-misuse, off-by-one, validation, performance, error-handling, style"


@dataclass
class Part:
    mod: Module
    changed: list  # names of the slots that are part of the change
    choice: dict  # slot name -> "good" | "nit" | "trap" | ("bad", i)   (changed slots only)


@dataclass
class PR:
    files: dict  # the repository after the change, plus PR.md and change.patch
    defects: list  # [{"id","file","start","end","cat","why","func","slot"}]
    decoys: list
    patch_lines: int
    title: str
    paths: list = field(default_factory=list)  # changed source paths


def build_pr(parts: list[Part], title: str | None = None, extra_ctx: dict | None = None) -> PR:
    files: dict[str, str] = {}
    patches: list[str] = []
    defects, decoys, paths = [], [], []
    notes: list[str] = []
    intros, outros = [], []
    for part in parts:
        mod = part.mod
        texts = slot_texts(mod, {n: part.choice.get(n, "good") for n in part.changed})
        head, spans = render(mod.template, texts, mod.lang)
        if mod.new_file:
            base = None
        else:
            btexts = slot_texts(mod, {})
            for name in part.changed:
                s = mod.slot(name)
                btexts[name] = s.good if s.old is None else s.old
            base, _ = render(mod.template, btexts, mod.lang)
        files[mod.path] = head
        paths.append(mod.path)
        for k, v in mod.ctx.items():
            files.setdefault(k, v)
        patches.append(unified_diff(mod.path, base, head))
        for name in part.changed:
            s = mod.slot(name)
            c = part.choice.get(name, "good")
            if name not in spans:
                continue
            notes.append(s.note or f"changes `{s.func}`")
            if isinstance(c, tuple):
                b = s.bad[c[1]]
                defects.append({"id": f"d{len(defects) + 1}", "file": mod.path, "start": spans[name][0], "end": spans[name][1], "cat": b.cat,
                                "why": b.why, "func": s.func, "slot": f"{mod.name}.{name}"})
            elif c in ("nit", "trap"):
                decoys.append({"file": mod.path, "start": spans[name][0], "end": spans[name][1], "kind": c, "func": s.func})
        intros.append(mod.intro)
        outros.append(mod.outro)
    for k, v in (extra_ctx or {}).items():
        files.setdefault(k, v)
    title = title or parts[0].mod.title
    patch = "".join(patches)
    files["change.patch"] = patch
    files["PR.md"] = description(title, "\n\n".join(intros) if len(parts) > 1 else intros[0], notes, outros[-1] if len(parts) == 1 else "\n\n".join(outros))
    return PR(files, defects, decoys, sum(1 for ln in patch.split("\n") if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))), title, paths)


def check_builds(lang: str, files: dict[str, str]) -> None:
    cmd = BUILD.get(lang)
    if not cmd or lang == "python":
        return
    r = run(files, cmd, timeout=120)
    if not r.ok:
        raise RuntimeError(f"review head does not build ({lang}):\n{r.out[-1500:]}")


def schema_text(fmt: str) -> str:
    item = ("an object with exactly the keys `file` (path as in the repository), `line` (1-based line number in the file *as it is now*, "
            "not in the patch), `category` (one of " + CATS + ") and `summary` (one or two sentences)")
    if fmt == "object":
        return ("Write `review.json` as an object `{\"verdict\": \"approve\" | \"request-changes\", \"findings\": [...]}` where each finding is " + item + ".")
    return "Write `review.json`: a JSON list where each finding is " + item + "."


def review_task(pr: PR, prompt: str, difficulty: int, slug: str, fmt: str, lang: str, tags: list[str], notes: dict, scope: str = "full") -> Task:
    spec = {"format": fmt, "slack": 1, "answer_file": "review.json", "scope": scope,
            "defects": [{k: v for k, v in d.items() if k in ("id", "file", "start", "end", "cat", "in_scope")} for d in pr.defects],
            "decoys": pr.decoys}
    hidden = {"_verify/check.py": CHECKER, "_verify/spec.json": json.dumps(spec, sort_keys=True, indent=1) + "\n"}
    gold = []
    for d in pr.defects:
        if d.get("in_scope", True):
            gold.append({"file": d["file"], "line": (d["start"] + d["end"]) // 2, "category": d["cat"], "summary": d["why"]})
    sol = {"review.json": json.dumps({"verdict": "request-changes" if gold else "approve", "findings": gold} if fmt == "object" else gold, indent=1) + "\n"}
    return Task(
        slug=slug, prompt=prompt, difficulty=difficulty, kind="feature", lang=lang, start=pr.files, hidden=hidden, solution=sol,
        verify=VERIFY, pass_mode="json-score", protected=sorted(pr.files), timeout_s=60, tags=["review", *tags],
        notes={"planted": [d["slot"] + ": " + d["why"] for d in pr.defects], "patch_lines": pr.patch_lines, **notes},
    )


# ---- prompts --------------------------------------------------------------------------------------------------------

def _tail(rng: random.Random) -> str:
    return rng.choice([
        "Only report real problems: a finding that does not point at an actual defect counts against the review, and so does a missed one.",
        "Precision matters as much as coverage: I would rather get three right findings than ten with a few wrong ones.",
        "Don't pad the list. A wrong accusation wastes the author's time as much as a missed bug wastes mine.",
        "Style nits are fine under category `style`, they won't be held against you, but the real defects are what I need.",
        "Point at the lines where the problem is; I'll check each finding against the code.",
    ])


def full_prompt(rng, pr: PR, blurb: str, fmt: str) -> str:
    s, t = schema_text(fmt), _tail(rng)
    title = pr.title
    voices = [
        f"Could you review the change in this repository before I merge it? `PR.md` has the description and `change.patch` the diff; the source files already contain the change. {s} {t}",
        f"Second pair of eyes please. \"{title}\" is up for review (see `PR.md` and `change.patch`). Look for bugs: logic errors, security holes, resource problems, missing validation. Ignore formatting. {s} {t}",
        f"{blurb} I'm the author of this PR and I'm nervous: the happy path works but I know that proves little. Please review it like the strictest person on the team (`PR.md`, `change.patch`). {s} {t}",
        f"review please: PR.md + change.patch. {s} be precise, no filler.",
        f"This PR is scheduled for tonight's release and nobody has had time to look at it. {blurb} Read the change and tell me what is wrong with it. {s} {t}",
        f"Reviewer needed. Context: {blurb} The description is in `PR.md`, the diff in `change.patch`, and the working tree has the new code. List every defect you can substantiate. {s} {t}",
        f"You're on the review rotation this week and \"{title}\" landed in your queue. Go through the diff (`change.patch`; the files are already updated) and write down the problems you find. {s} {t}",
        f"A teammate asked for a pre-merge review of this change and went on holiday, so it's on you. The author's notes are in `PR.md`. {s} {t}",
    ]
    return rng.choice(voices)


def security_prompt(rng, pr: PR, blurb: str, fmt: str) -> str:
    s = schema_text(fmt)
    title = pr.title
    voices = [
        f"Security review only, please. \"{title}\" touches code that handles input from outside (see `PR.md`, `change.patch`). Report vulnerabilities and unsafe handling of secrets or untrusted data. Other bugs are out of scope and reporting them counts against you. {s}",
        f"Our AppSec checklist requires a security pass on every change before release. {blurb} Review `change.patch` (the working tree already contains it) strictly from a security point of view: injection, leaking sensitive data, weak crypto, unsafe file or process handling, missing authorisation. Anything that is merely a functional bug is out of scope. {s}",
        f"I only need to know whether this PR introduces security problems; somebody else is checking correctness. {blurb} Findings outside security count as false alarms. {s}",
        f"pentest-style read of this PR (PR.md, change.patch): what could an attacker or a careless operator abuse? Security findings only; non-security bugs are noise here. {s}",
    ]
    return rng.choice(voices)


def verdict_prompt(rng, pr: PR, blurb: str, fmt: str) -> str:
    s = schema_text("object")
    title = pr.title
    voices = [
        f"Is \"{title}\" safe to merge? Read `PR.md` and `change.patch` (the tree already has the change) and give me a verdict, with the findings that justify it. Use `approve` only if you would stake your name on it; use `request-changes` if anything real is wrong. {s} Findings that are not real defects count against you, so don't invent any to look thorough.",
        f"Release manager here. I need a yes/no on this PR before I cut the build: {blurb} Review it and answer in `review.json`. {s} If it is fine, say so with an empty findings list; if not, list exactly the problems that block the merge.",
        f"Merge gate: approve or block. The PR description is in `PR.md`, the diff in `change.patch`. {s} Blocking a good PR is as costly as approving a bad one.",
        f"Final look before merging, please. {blurb} Tell me whether it can go in as it is. {s} Don't flag anything you are not sure is an actual defect.",
    ]
    return rng.choice(voices)


# ---- families -------------------------------------------------------------------------------------------------------

PROFILES = {
    1: dict(changed=(1, 2), k=(1, 1), nit=0, trap=0),
    2: dict(changed=(3, 3), k=(2, 2), nit=1, trap=0),
    3: dict(changed=(4, 6), k=(2, 3), nit=1, trap=1),
    4: dict(changed=(7, 12), k=(3, 4), nit=2, trap=1),
    5: dict(changed=(99, 99), k=(4, 5), nit=2, trap=2),
}


OOS_CATS = {"logic", "off-by-one", "performance"}  # what a security-only review may leave alone without anyone arguing


def _pick_parts(rng, mods: list[Module], d: int, mode: str, clean: bool = False) -> list[Part]:
    prof = PROFILES[d]
    chosen_mods = [rng.choice(mods)]
    if d == 5:
        others = [m for m in mods if m is not chosen_mods[0] and m.lang == chosen_mods[0].lang]
        rng.shuffle(others)
        chosen_mods += others[: rng.choice([1, 2])]
    parts: list[Part] = []
    nslots = rng.randint(*prof["changed"])
    k_total = 0 if clean else rng.randint(*prof["k"])
    per_mod = [0] * len(chosen_mods)
    for i in range(k_total):
        per_mod[i % len(chosen_mods)] += 1
    security = mode == "security"
    for mi, (mod, kk) in enumerate(zip(chosen_mods, per_mod)):
        cand = mod.changed()
        with_bad = [s for s in cand if s.bad]
        rng.shuffle(with_bad)
        picks: list = []
        choice: dict = {}
        if security:
            # one or two security defects (in scope) and one or two clearly non-security ones (out of scope)
            sec = [s for s in with_bad if any(b.cat == "security" for b in s.bad)]
            oos = [s for s in with_bad if any(b.cat in OOS_CATS for b in s.bad) and s not in sec[:2]]
            n_sec = min(len(sec), 1 if kk <= 2 else 2) if (mi == 0 or sec) else 0
            for s in sec[:n_sec]:
                picks.append(s)
                choice[s.name] = ("bad", rng.choice([i for i, b in enumerate(s.bad) if b.cat == "security"]))
            for s in oos[: max(1, kk - n_sec) if mi == 0 else max(0, kk - n_sec)]:
                if s in picks:
                    continue
                picks.append(s)
                choice[s.name] = ("bad", rng.choice([i for i, b in enumerate(s.bad) if b.cat in OOS_CATS]))
        else:
            for s in with_bad[: min(kk, len(with_bad))]:
                picks.append(s)
                choice[s.name] = ("bad", rng.randrange(len(s.bad)))
        changed = list(picks)
        for s in list(changed):
            for dep in s.deps:
                ds = mod.slot(dep)
                if ds not in changed:
                    changed.append(ds)
        rest = [s for s in cand if s not in changed]
        rng.shuffle(rest)
        want = nslots if d < 5 else len(cand)
        for s in rest:
            if len(changed) >= max(want, len(picks)):
                break
            changed.append(s)
            for dep in s.deps:
                ds = mod.slot(dep)
                if ds not in changed:
                    changed.append(ds)
        nit_n, trap_n = prof["nit"], prof["trap"]
        for s in changed:
            if s.name in choice:
                continue
            if trap_n and s.trap:
                choice[s.name] = "trap"
                trap_n -= 1
            elif nit_n and (s.nit or auto_nit(s.good, mod.lang)):
                choice[s.name] = "nit"
                nit_n -= 1
        order = [y.name for y in mod.slots]
        parts.append(Part(mod, [s.name for s in sorted(changed, key=lambda x: order.index(x.name))], choice))
    return parts


def review_family(mods: list[Module], rng: random.Random, n: int, mode: str = "full", profile: list[int] | None = None, tag: str = "", fmt: str | None = None):
    """n review tasks over the given modules (one language).  mode: full | security | verdict."""
    profile = profile or [1, 2, 2, 3, 3, 3, 4, 4, 5]
    for i in range(n):
        d = profile[i % len(profile)]
        clean = mode == "verdict" and rng.random() < 0.35
        for attempt in range(8):
            parts = _pick_parts(rng, mods, d, mode, clean)
            pr = build_pr(parts)
            if mode == "security":
                cats = [x["cat"] for x in pr.defects]
                if "security" not in cats or all(c == "security" for c in cats):
                    continue
            if not clean and not pr.defects:
                continue
            break
        else:
            raise RuntimeError("could not assemble a review task")
        lang = parts[0].mod.lang
        check_builds(lang, {k: v for k, v in pr.files.items() if k not in ("PR.md", "change.patch")})
        for df in pr.defects:
            df["in_scope"] = (df["cat"] == "security") if mode == "security" else True
        fmt_ = fmt or ("object" if mode == "verdict" else "list")
        blurb = parts[0].mod.blurb
        prompt = {"full": full_prompt, "security": security_prompt, "verdict": verdict_prompt}[mode](rng, pr, blurb, fmt_)
        if not any(x.get("in_scope", True) for x in pr.defects) and mode != "verdict":
            continue
        slug = f"{i + 1:02d}-{'-'.join(p.mod.name.split('-', 1)[-1] for p in parts)}-{'clean' if not pr.defects else str(sum(1 for x in pr.defects if x.get('in_scope', True))) + 'd'}"
        dd_ = d
        yield review_task(pr, prompt, dd_, slug[:90], fmt_, lang, [mode, *([tag] if tag else [])],
                          {"mode": mode, "modules": [p.mod.name for p in parts], "decoys": len(pr.decoys)}, scope=mode)
