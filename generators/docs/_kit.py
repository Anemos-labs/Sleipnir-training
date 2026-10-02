"""Generation-time self check for docs tasks: the hidden checks fail on the start and pass with the reference solution."""
from __future__ import annotations

from fx import merged, run


def prove_docs(label: str, start: dict, hidden: dict, solution: dict, cmd: str, visible_cmd: str | None = None, timeout: int = 120) -> None:
    base = merged(start, hidden)
    if visible_cmd:
        r = run(start, visible_cmd, timeout=timeout)
        if not r.ok:
            raise RuntimeError(f"{label}: the visible checks fail on the start:\n{r.out[-1500:]}")
    r = run(base, cmd, timeout=timeout)
    if r.ok:
        raise RuntimeError(f"{label}: the checks pass on the start (they must fail)")
    r = run(merged(base, solution), cmd, timeout=timeout)
    if not r.ok:
        raise RuntimeError(f"{label}: the reference solution fails:\n{r.out[-2500:]}")
