"""Diagnosis tasks from the slot modules of the other languages (javascript, go, rust, java).

Same idea as ``_engine.trace_family``: pick a defect that changes what a reproduction script prints, run the script, hand over the output as ``logs/run.log``
and ask for ``diagnosis.json``.  The scripts catch their own errors and print them, so every log is plain program output (no stack traces with addresses).
"""
from __future__ import annotations

import json
import random
import re

from fx import Task, run
from generators.review._slots import Module, render, slot_texts

from ._engine import KINDS, VERIFY, accepted_kinds, diff_window, hidden_diag, last_name, schema_text

RUNNERS = {
    "javascript": {"path": "scenario.js", "cmd": "node scenario.js 2>&1", "broken": re.compile(r"SyntaxError|ReferenceError: \w+ is not defined|Cannot find module")},
    "go": {"path": "cmd/scenario/main.go", "cmd": "go run ./cmd/scenario 2>&1", "broken": re.compile(r"\.go:\d+:\d+: |\[build failed\]|^# \S+", re.M)},
    "rust": {"path": "examples/scenario.rs", "cmd": "cargo run --offline --quiet --example scenario 2>&1", "broken": re.compile(r"^error(\[E\d+\])?: |could not compile", re.M)},
    "java": {"path": "Scenario.java", "cmd": "unset JAVA_TOOL_OPTIONS; rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java') 2>&1 && java -cp build Scenario 2>&1", "broken": re.compile(r"error: |\.java:\d+: ")},
}

_CACHE: dict[str, tuple[int, str] | None] = {}


def repo_files_x(mod: Module, choice: dict, scenario: str) -> tuple[dict[str, str], dict]:
    head, spans = render(mod.template, slot_texts(mod, choice), mod.lang)
    files = dict(mod.ctx)
    files[mod.path] = head
    files[RUNNERS[mod.lang]["path"]] = scenario
    return files, spans


def run_x(mod: Module, choice: dict, scenario: str) -> tuple[int, str, dict] | None:
    """(exit code, output, spans); None when the program does not build or its output is not reproducible."""
    files, spans = repo_files_x(mod, choice, scenario)
    r = RUNNERS[mod.lang]
    key = json.dumps([mod.name, sorted(files.items())], sort_keys=True)
    if key not in _CACHE:
        a = run(files, r["cmd"], timeout=120)
        if a.timed_out or r["broken"].search(a.out):
            _CACHE[key] = None
        else:
            b = run(files, r["cmd"] + " # again", timeout=120)
            _CACHE[key] = (a.code, a.out) if (a.code, a.out) == (b.code, b.out) else None
    got = _CACHE[key]
    return None if got is None else (got[0], got[1], spans)


def observable_x(mod: Module, scenario: str) -> list[tuple[str, int]]:
    good = run_x(mod, {}, scenario)
    if good is None or good[0] != 0:
        raise RuntimeError(f"{mod.name}: the scenario does not run cleanly on the correct module:\n{(good or (0, '', {}))[1][-1500:]}")
    out = []
    for s in mod.slots:
        for i in range(len(s.bad)):
            got = run_x(mod, {s.name: ("bad", i)}, scenario)
            if got is not None and got[1].strip() != good[1].strip():
                out.append((s.name, i))
    return out


def _first_difference(good: str, bad: str) -> str:
    a, b = good.strip().split("\n"), bad.strip().split("\n")
    for i in range(max(len(a), len(b))):
        x, y = (a[i] if i < len(a) else None), (b[i] if i < len(b) else None)
        if x != y:
            if x is not None and y is not None:
                if y.startswith("  panic at"):
                    return f"the program panics (`{y.strip()[:140]}`) where the line `{x[:140]}` was expected"
                return f"the line `{y[:140]}` should have been `{x[:140]}`"
            if y is not None:
                return f"there is an extra line `{y[:140]}` that should not be there"
            return f"the line `{x[:140]}` is missing"
    return "something differs"


def x_prompt(rng: random.Random, mod: Module, first_bad: str) -> str:
    r = RUNNERS[mod.lang]
    scn, cmd = r["path"], r["cmd"].replace(" 2>&1", "").replace("unset JAVA_TOOL_OPTIONS; ", "")
    s = schema_text()
    voices = [
        f"{mod.blurb} The reproduction script `{scn}` (run it with `{cmd}`) prints output, saved as `logs/run.log`, that is wrong: {first_bad}. Find the root cause. {s}",
        f"QA reports a wrong result: in `logs/run.log` (the output of `{scn}`) {first_bad}. {mod.blurb} Diagnose it. {s}",
        f"Something is off in what `{scn}` prints (see `logs/run.log`): {first_bad}. {mod.blurb} I want the root cause, not a workaround. {s}",
        f"Bug report from the field, reproduced by `{scn}` (`{cmd}`): {first_bad}. The complete output is in `logs/run.log`. {mod.blurb} What is wrong and where? {s}",
    ]
    return rng.choice(voices)


SPREAD = [0.28, 0.28, 0.24, 0.14, 0.06]


def x_trace_family(mods: list[Module], scenarios: dict[str, str], rng: random.Random, n: int):
    pools = {m.name: observable_x(m, scenarios[m.name]) for m in mods}
    used: dict[str, set] = {m.name: set() for m in mods}
    made: list[tuple[float, Task]] = []
    i, guard = 0, 0
    while i < n and guard < n * 20:
        guard += 1
        mod = mods[i % len(mods)]
        scenario = scenarios[mod.name]
        avail = [x for x in pools[mod.name] if x not in used[mod.name]]
        if not avail:
            used[mod.name] = set()
            avail = pools[mod.name]
        if not avail:
            raise RuntimeError(f"{mod.name}: no observable defect")
        slot_name, bi = rng.choice(avail)
        used[mod.name].add((slot_name, bi))
        slot = mod.slot(slot_name)
        bad = slot.bad[bi]
        if not any(w.lower() in bad.why.lower() for w in list(bad.kw) + [last_name(slot.func)]):
            raise RuntimeError(f"{mod.name}.{slot_name}: the explanation of defect {bi} contains none of its keywords, the reference diagnosis would fail")
        choice: dict = {slot_name: ("bad", bi)}
        decoys = [s for s in mod.slots if s.name != slot_name and s.name != "imports" and (s.nit or s.trap)]
        rng.shuffle(decoys)
        for s in decoys[: rng.choice([0, 1, 2])]:
            choice[s.name] = "trap" if s.trap and rng.random() < 0.6 else "nit" if s.nit else "trap"
        got = run_x(mod, choice, scenario)
        if got is None:  # a decoy that does not build or is not reproducible: fall back to the plain defect
            choice = {slot_name: ("bad", bi)}
            got = run_x(mod, choice, scenario)
        good = run_x(mod, {}, scenario)
        if got is None or good is None or got[1].strip() == good[1].strip():
            continue
        _, out, spans = got
        files, spans = repo_files_x(mod, choice, scenario)
        lo, hi = diff_window(good[1], out)
        files["logs/run.log"] = out.strip() + "\n"
        windows = [{"file": mod.path, "start": spans[slot_name][0], "end": spans[slot_name][1]}, {"file": "logs/run.log", "start": lo, "end": hi}]
        spec = {"answer_file": "diagnosis.json", "fields": {
            "root_cause_file": {"type": "path", "accept": [mod.path]},
            "function": {"type": "name", "accept": [slot.func]},
            "kind": {"type": "enum", "allowed": KINDS, "accept": accepted_kinds(bad)},
            "evidence_lines": {"type": "evidence", "windows": windows, "slack": 1},
            "fix_summary": {"type": "text", "min_len": 20, "any": list(bad.kw) + [last_name(slot.func)]},
        }}
        gold = {"root_cause_file": mod.path, "function": slot.func, "kind": accepted_kinds(bad)[0],
                "evidence_lines": [f"{mod.path}:{spans[slot_name][0]}"], "fix_summary": bad.why}
        i += 1
        hardness = 2 * mod.difficulty + len(choice) - 1 + (1 if bad.cat in ("concurrency", "api-misuse") else 0) + (i * 7919 % 100) / 100.0
        made.append((hardness, Task(
            slug=f"{i:02d}-{mod.name.split('-', 1)[-1]}-{slot_name}", prompt=x_prompt(rng, mod, _first_difference(good[1], out)), difficulty=3, kind="fix", lang=mod.lang,
            start=files, hidden=hidden_diag(spec), solution={"diagnosis.json": json.dumps(gold, indent=1) + "\n"}, verify=VERIFY, pass_mode="json-score",
            protected=sorted(files), timeout_s=60, tags=["diagnosis", "wrong-output", mod.lang],
            notes={"module": mod.name, "slot": slot_name, "bad": bad.why, "decoys": sorted(k for k in choice if k != slot_name)},
        )))
    ranked = sorted(range(len(made)), key=lambda j: made[j][0])
    cuts, acc = [], 0.0
    for share in SPREAD:
        acc += share
        cuts.append(round(acc * len(made)))
    for rank, j in enumerate(ranked):
        made[j][1].difficulty = next(lvl for lvl, c in enumerate(cuts, 1) if rank < c)
    for _, task in made:
        yield task
