"""Shared helpers for the refactor (and, via import, optimize/docs) families.

* ``asset``: read a helper file from ``_assets`` (structural analysers that are shipped into the hidden tree).
* ``py_behaviour``: golden-output behaviour tests computed by *running the starting code* (so "behaviour unchanged"
  is checked against what the code really did before the refactor).
* ``prove``: generation-time self check: behaviour passes on the start, the structure check fails on the start,
  everything passes with the reference solution. A refactor task whose start already satisfies the structure check
  (or whose solution breaks behaviour) is a generator bug and raises here, long before ``admit``.
"""
from __future__ import annotations

import json
from pathlib import Path

from fx import merged, run

ASSETS = Path(__file__).parent / "_assets"

PY_BEHAVIOUR_CMD = "python3 -m unittest discover -s tests -p 'test_[a-y]*.py'"
PY_STRUCT_CMD = "python3 -m unittest discover -s tests -p 'test_zz*.py'"

# node 22: `node --test test/` treats the directory as a module and fails, so name the files
JS_BEHAVIOUR_CMD = "node --test test/*.test.js"
JS_STRUCT_CMD = "python3 checks/structure.py"
JS_FULL_CMD = "node --test test/*.test.js && python3 checks/structure.py"


def load_structlib():
    """The python structure helpers as a module, for use at generation time (same code the hidden checks run)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("fx_structlib", ASSETS / "structlib.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def asset(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def py_structlib() -> dict[str, str]:
    return {"tests/structlib.py": asset("structlib.py")}


def clike_lib() -> dict[str, str]:
    return {"checks/clike.py": asset("clike.py")}


_PRELUDE = "import copy, json, sys\nsys.path.insert(0, '.')\n"

_RUNNER = '''
def _norm(x):
    return json.loads(json.dumps(x))

def _outcome(case):
    try:
        return _norm(run_case(copy.deepcopy(case)))
    except Exception as e:
        return {"raises": type(e).__name__}
'''


def py_golden(files: dict[str, str], harness: str, cases: list) -> list:
    """Run ``harness`` (python source defining ``run_case(case)``) on every case against the given tree."""
    script = _PRELUDE + harness + _RUNNER + (
        f"\nCASES = json.loads({json.dumps(json.dumps(cases))})\n"
        "print(json.dumps([_outcome(c) for c in CASES]))\n")
    r = run(merged(files, {"_golden.py": script}), "python3 _golden.py", timeout=60)
    if not r.ok:
        raise RuntimeError("golden run failed:\n" + r.out[-2000:])
    return json.loads(r.out.strip().splitlines()[-1])


def py_behaviour(files: dict[str, str], harness: str, cases: list, title: str = "behaviour", test_harness: str | None = None) -> str:
    """Text of a hidden unittest module asserting that every case still gives the golden outcome.

    When the API changes in the refactor (``test_harness``), the golden outcomes are recorded with ``harness`` on the
    start tree, and the module drives the *new* API with ``test_harness``."""
    want = py_golden(files, harness, cases)
    harness = test_harness or harness
    cs = json.dumps(json.dumps(cases))
    ws = json.dumps(json.dumps(want))
    return (
        "import unittest\n" + _PRELUDE + harness + _RUNNER +
        f"\nCASES = json.loads({cs})\nWANT = json.loads({ws})\n\n\n"
        f"class {title.title().replace(' ', '').replace('_', '')}Tests(unittest.TestCase):\n"
        "    def test_recorded_outcomes(self):\n"
        "        for i, case in enumerate(CASES):\n"
        "            with self.subTest(i=i, case=str(case)[:200]):\n"
        "                self.assertEqual(_outcome(case), WANT[i])\n\n\n"
        "if __name__ == '__main__':\n    unittest.main()\n"
    )


def prove(label: str, start: dict, hidden: dict, solution: dict, behaviour_cmd: str, struct_cmd: str, full_cmd: str,
          timeout: int = 120, behaviour_on_start: bool = True) -> None:
    base = merged(start, hidden)
    r = run(base, behaviour_cmd, timeout=timeout)
    if behaviour_on_start and not r.ok:
        raise RuntimeError(f"{label}: behaviour checks FAIL on the start (they must pass):\n{r.out[-1800:]}")
    if not behaviour_on_start and r.ok:
        raise RuntimeError(f"{label}: behaviour checks pass on the start although the API is supposed to change")
    r = run(base, struct_cmd, timeout=timeout)
    if r.ok:
        raise RuntimeError(f"{label}: structure checks PASS on the start (they must fail)")
    r = run(merged(base, solution), full_cmd, timeout=timeout)
    if not r.ok:
        raise RuntimeError(f"{label}: reference solution fails:\n{r.out[-2500:]}")


def prompt_pick(rng, options):
    return options[rng.randrange(len(options))]


def indent(text: str, n: int) -> str:
    pad = " " * n
    return "\n".join((pad + ln) if ln.strip() else ln for ln in text.split("\n"))
