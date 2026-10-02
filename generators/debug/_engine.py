"""Debug tasks: diagnose a failure from evidence (logs, traces, dumps) and name the root cause.  Checked by ``_check_diag.py``."""
from __future__ import annotations

import difflib
import json
import random
import re
from pathlib import Path

from fx import Task, run
from fx.run import merged
from generators.review._slots import KIND_OF_CAT, Module, render, slot_texts

CHECKER = Path(__file__).with_name("_check_diag.py").read_text(encoding="utf-8")
VERIFY = "python3 _verify/check.py"

KINDS = ["logic-error", "off-by-one", "missing-validation", "null-handling", "type-confusion", "state-mutation", "race-condition",
         "resource-leak", "config-error", "encoding", "timezone", "rounding", "ordering", "stale-cache", "performance", "security",
         "environment", "data-corruption", "api-misuse", "error-handling"]


def schema_text(extra: str = "") -> str:
    return ("Write `diagnosis.json`: an object with exactly these keys: `root_cause_file` (path of the file that contains the defect), "
            "`function` (the function or method that is wrong), `kind` (one of " + ", ".join(KINDS) + "), "
            "`evidence_lines` (a list of `path:line` strings that show the problem: the faulty code and/or the telling log lines) and "
            "`fix_summary` (one or two sentences: what has to change)." + (" " + extra if extra else ""))


def hidden_diag(spec: dict) -> dict[str, str]:
    return {"_verify/check.py": CHECKER, "_verify/spec.json": json.dumps(spec, sort_keys=True, indent=1) + "\n"}


def last_name(func: str) -> str:
    return re.split(r"::|#|\.", func)[-1]


def kind_of(bad) -> str:
    return bad.kind or KIND_OF_CAT[bad.cat]


KIND_ALIASES = {
    "rounding": ["api-misuse", "logic-error"], "null-handling": ["missing-validation", "error-handling"], "type-confusion": ["missing-validation", "api-misuse"],
    "off-by-one": ["logic-error"], "missing-validation": ["null-handling"], "ordering": ["logic-error"], "state-mutation": ["logic-error", "api-misuse"],
    "stale-cache": ["logic-error", "state-mutation"], "api-misuse": ["logic-error"], "error-handling": ["null-handling"],
    "logic-error": ["off-by-one", "null-handling"], "performance": ["logic-error"], "data-corruption": ["logic-error", "encoding", "rounding"],
}


def accepted(kind: str) -> list[str]:
    """The kinds an answer may name for a defect of this kind (classification is fuzzy: near neighbours count)."""
    return sorted({kind, *KIND_ALIASES.get(kind, [])})


def accepted_kinds(bad) -> list[str]:
    return accepted(kind_of(bad))


# ---- running python modules -----------------------------------------------------------------------------------------

_RUNS: dict[str, tuple[int, str]] = {}


def repo_files(mod: Module, choice: dict) -> tuple[dict[str, str], dict]:
    head, spans = render(mod.template, slot_texts(mod, choice), mod.lang)
    files = dict(mod.ctx)
    files[mod.path] = head
    files[mod.scenario_path] = mod.scenario
    return files, spans


def run_scenario(mod: Module, choice: dict) -> tuple[int, str, dict]:
    files, spans = repo_files(mod, choice)
    key = json.dumps([mod.name, sorted(files.items())], sort_keys=True)
    if key not in _RUNS:
        r = run(files, f"python3 -u {mod.scenario_path}", timeout=60)
        _RUNS[key] = (r.code, r.out)
    code, out = _RUNS[key]
    return code, out, spans


def observable_bads(mod: Module) -> list[tuple[str, int]]:
    """(slot, bad index) pairs whose defect changes what the scenario prints; the correct module must run cleanly."""
    code, good, _ = run_scenario(mod, {})
    if code != 0:
        raise RuntimeError(f"{mod.name}: the scenario fails on the correct module:\n{good[-1500:]}")
    out = []
    for s in mod.slots:
        for i in range(len(s.bad)):
            c, o, _ = run_scenario(mod, {s.name: ("bad", i)})
            if o.strip() != good.strip():
                out.append((s.name, i))
    return out


def diff_window(good: str, bad: str, cap: int = 30) -> tuple[int, int]:
    """First/last line (1-based) of the part of `bad` that differs from `good`."""
    a, b = good.strip().split("\n"), bad.strip().split("\n")
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    lo, hi = None, None
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "insert"):
            if lo is None:
                lo = j1 + 1
            hi = j2
    if lo is None:  # only deletions: point at the line after the gap
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "delete":
                lo = hi = min(j1 + 1, len(b))
                break
    lo = lo or 1
    hi = max(hi or lo, lo)
    return lo, min(hi, lo + cap)


FRAME = re.compile(r'File "\./([^"]+)", line (\d+), in (\S+)')


def frames(out: str) -> list[tuple[str, int, str]]:
    return [(m.group(1), int(m.group(2)), m.group(3)) for m in FRAME.finditer(out)]


# ---- prompts --------------------------------------------------------------------------------------------------------

def _excerpt(out: str, n: int = 14) -> str:
    """The end of a log; source lines inside a traceback are dropped (they only repeat the code)."""
    lines = out.strip().split("\n")
    keep = []
    for k, ln in enumerate(lines):
        if ln.startswith("    ") and k + 1 < len(lines) and not lines[k + 1].startswith("    ") and lines[k - 1].lstrip().startswith("File "):
            continue
        keep.append(ln)
    return "\n".join(keep[-n:])


def trace_prompt(rng, mod: Module, crash: bool, out: str, good: str, extra_schema: str = "") -> str:
    s = schema_text()
    first_bad = ""
    if not crash:
        a, b = good.strip().split("\n"), out.strip().split("\n")
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "replace":
                first_bad = f"the line `{b[j1][:140]}` should have been `{a[i1][:140]}`"
                break
            if tag == "insert":
                first_bad = f"there is an extra line `{b[j1][:140]}` that should not be there"
                break
            if tag == "delete":
                first_bad = f"the line `{a[i1][:140]}` is missing"
                break
    blurb = mod.blurb
    if crash:
        ex = _excerpt(out)
        voices = [
            f"{blurb} Our smoke script `scenario.py` died with a traceback overnight; the full output is in `logs/run.log`. The end of it:\n\n```\n{ex}\n```\n\nThe line the traceback ends on is not necessarily where the bug is. Find the root cause. {s}",
            f"CI is red. `python3 scenario.py` crashes (log: `logs/run.log`):\n\n```\n{ex}\n```\n\n{blurb} I need to know which function is actually responsible before I touch anything. {s}",
            f"Ticket: \"scenario run aborts with an exception\". {blurb} Output of the failing run is saved as `logs/run.log` (last lines: `{ex.splitlines()[-1][:160]}`). Please diagnose it, don't just patch the symptom. {s}",
            f"Can you find out why this blows up? `logs/run.log` has the whole run of `scenario.py`. {blurb} Tell me where the defect really is. {s}",
        ]
    else:
        voices = [
            f"{blurb} The reproduction script `scenario.py` runs without errors but its output (saved as `logs/run.log`) is wrong: {first_bad}. Find the root cause. {s}",
            f"QA reports a wrong result in the kiosk back-end: in `logs/run.log` (output of `scenario.py`) {first_bad}. Nothing crashes, so there's no traceback to follow. {blurb} Diagnose it. {s}",
            f"Something is off in what `scenario.py` prints (see `logs/run.log`): {first_bad}. {blurb} I want the root cause, not a workaround. {s}",
            f"Bug report from the field, reproduced by `scenario.py`: {first_bad}. The complete output is in `logs/run.log`. {blurb} What is wrong and where? {s}",
        ]
    return rng.choice(voices)


TRACE_SPREAD = [0.28, 0.28, 0.24, 0.14, 0.06]  # share of d1..d5
FIX_SPREAD = [0.0, 0.13, 0.33, 0.33, 0.21]


def trace_family(mods: list[Module], rng: random.Random, n: int, tag: str = "", fix_too: bool = False):
    """Diagnosis tasks from python slot modules: pick an observable defect, run the scenario, hand over the log."""
    pools = {m.name: observable_bads(m) for m in mods}
    used: dict[str, set] = {m.name: set() for m in mods}
    made: list[tuple[float, Task]] = []
    i = 0
    guard = 0
    while i < n and guard < n * 20:
        guard += 1
        mod = mods[i % len(mods)]
        avail = [x for x in pools[mod.name] if x not in used[mod.name]]
        if not avail:
            used[mod.name] = set()
            avail = pools[mod.name]
        slot_name, bi = rng.choice(avail)
        used[mod.name].add((slot_name, bi))
        slot = mod.slot(slot_name)
        bad = slot.bad[bi]
        if not any(w.lower() in bad.why.lower() for w in list(bad.kw) + [last_name(slot.func)]):
            raise RuntimeError(f"{mod.name}.{slot_name}: the explanation of defect {bi} contains none of its keywords, the reference diagnosis would fail")
        choice: dict = {slot_name: ("bad", bi)}
        decoy_slots = [s for s in mod.slots if s.name != slot_name and (s.nit or s.trap)]
        rng.shuffle(decoy_slots)
        for s in decoy_slots[: rng.choice([0, 1, 2])]:
            choice[s.name] = "trap" if s.trap and rng.random() < 0.6 else "nit" if s.nit else "trap"
        code, out, spans = run_scenario(mod, choice)
        _, good, _ = run_scenario(mod, {})
        if out.strip() == good.strip():
            continue
        crash = "Traceback (most recent call last)" in out
        fr = frames(out)
        root_fn = last_name(slot.func)
        deceptive = crash and fr and root_fn not in {f[2] for f in fr}
        files, spans = repo_files(mod, choice)
        lo, hi = diff_window(good, out)
        files["logs/run.log"] = out.strip() + "\n"
        windows = [{"file": mod.path, "start": spans[slot_name][0], "end": spans[slot_name][1]}, {"file": "logs/run.log", "start": lo, "end": hi}]
        if crash and fr:
            windows.append({"file": "logs/run.log", "start": lo, "end": len(out.strip().split("\n"))})
        spec = {"answer_file": "diagnosis.json", "fields": {
            "root_cause_file": {"type": "path", "accept": [mod.path]},
            "function": {"type": "name", "accept": [slot.func]},
            "kind": {"type": "enum", "allowed": KINDS, "accept": accepted_kinds(bad)},
            "evidence_lines": {"type": "evidence", "windows": windows, "slack": 1},
            "fix_summary": {"type": "text", "min_len": 20, "any": list(bad.kw) + [root_fn]},
        }}
        d = mod.difficulty - 1 + (1 if deceptive else 0) + (1 if len(choice) > 1 and mod.difficulty >= 3 else 0)
        d = max(1, min(5, d))
        gold = {"root_cause_file": mod.path, "function": slot.func, "kind": accepted_kinds(bad)[0],
                "evidence_lines": [f"{mod.path}:{spans[slot_name][0]}"], "fix_summary": bad.why}
        prompt = trace_prompt(rng, mod, crash, out, good)
        solution = {"diagnosis.json": json.dumps(gold, indent=1) + "\n"}
        protected = sorted(files)
        if fix_too:
            prompt += rng.choice([" After diagnosing it, repair the code as well: `python3 scenario.py` must then print the correct output (the module's docstrings describe the intended behaviour). Touch only what is needed.",
                                  " Then fix the defect in the source so that the scenario runs and prints what it should; the diagnosis and the repaired behaviour are both checked."])
            good_head = render(mod.template, slot_texts(mod, {k: v for k, v in choice.items() if k != slot_name}), mod.lang)[0]
            solution[mod.path] = good_head
            protected = [p for p in protected if p != mod.path]
            spec["run"] = {"cmd": f"PYTHONHASHSEED=0 python3 -u {mod.scenario_path} 2>&1", "expect": good.strip(), "timeout": 60}
            d = min(5, d + 1)
        i += 1
        hardness = 2 * mod.difficulty + (0 if crash else 1) + (2 if deceptive else 0) + len(choice) - 1 + (1 if fix_too else 0) + (i * 7919 % 100) / 100.0
        made.append((hardness, Task(
            slug=f"{i:02d}-{mod.name.split('-', 1)[-1]}-{slot_name}-{'crash' if crash else 'wrong'}",
            prompt=prompt, difficulty=d, kind="fix", lang="python", start=files, hidden=hidden_diag(spec),
            solution=solution, verify=VERIFY, pass_mode="json-score",
            protected=protected, timeout_s=90 if fix_too else 60, tags=["diagnosis", "trace" if crash else "wrong-output", *(["fix-too"] if fix_too else []), *([tag] if tag else [])],
            notes={"module": mod.name, "slot": slot_name, "bad": bad.why, "crash": crash, "deceptive": bool(deceptive), "decoys": sorted(k for k in choice if k != slot_name)},
        )))
    # difficulty is relative to the family: rank the tasks by how much there is to untangle and cut the ranking into the target spread
    dist = FIX_SPREAD if fix_too else TRACE_SPREAD
    ranked = sorted(range(len(made)), key=lambda j: made[j][0])
    cuts, acc = [], 0.0
    for share in dist:
        acc += share
        cuts.append(round(acc * len(made)))
    for rank, j in enumerate(ranked):
        made[j][1].difficulty = next(lvl for lvl, c in enumerate(cuts, 1) if rank < c)
    for _, task in made:
        yield task
