"""Shared helpers for optimize families.

An optimize task ships correctness tests (pass on the slow start and on the reference solution) and performance tests
(fail on the start *because of the stated reason*, pass on the solution). ``prove_opt`` checks exactly that at
generation time. Performance bars are operation counts, allocation counts or input sizes with a wide gap: never tight
wall-clock margins.
"""
from __future__ import annotations

from fx import merged, run

PY_ALL = "python3 -m unittest discover -s tests -v"
PY_CORRECT = "python3 -m unittest discover -s tests -p 'test_[bc]*.py'"
PY_PERF = "python3 -m unittest discover -s tests -p 'test_perf*.py'"

PERF_MARK = "PERF"


def prove_opt(label: str, start: dict, hidden: dict, solution: dict, correct_cmd: str, perf_cmd: str, full_cmd: str, timeout: int = 150,
              mark: str = PERF_MARK, start_perf_timeout_ok: bool = False) -> None:
    base = merged(start, hidden)
    r = run(base, correct_cmd, timeout=timeout)
    if not r.ok:
        raise RuntimeError(f"{label}: correctness checks FAIL on the slow start (they must pass):\n{r.out[-1800:]}")
    r = run(base, perf_cmd, timeout=timeout)
    if r.ok:
        raise RuntimeError(f"{label}: performance checks PASS on the slow start (they must fail)")
    if r.timed_out:
        if not start_perf_timeout_ok:
            raise RuntimeError(f"{label}: the slow start timed out instead of failing the bar")
    elif mark not in r.out:
        raise RuntimeError(f"{label}: the start failed, but not on the performance bar:\n{r.out[-1800:]}")
    r = run(merged(base, solution), full_cmd, timeout=timeout)
    if not r.ok:
        raise RuntimeError(f"{label}: reference solution fails:\n{r.out[-2500:]}")
