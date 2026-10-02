"""Write a python gold suite by *running* the reference implementation: expected values are never typed by hand.

``groups`` is a list of ``(test_name, steps)``; a step is

    ("do", "code")                  a statement (setup)
    ("eq", "expression")            assertEqual(expression, <what the reference returns>)
    ("raises", "ValueError", "code")  assertRaises(ValueError) around the code (checked to raise)

The generated file is a plain ``unittest`` module.
"""
from __future__ import annotations

import ast
import json

from fx import run
from fx.run import merged

DRIVER = r'''
import json, sys
sys.path.insert(0, ".")
GROUPS = json.loads(open("_groups.json").read())
IMPORTS = GROUPS["imports"]
import unittest
from unittest import mock
out = []
for name, steps in GROUPS["groups"]:
    ns = {"self": unittest.TestCase(), "mock": mock}
    exec(IMPORTS, ns)
    res = []
    for st in steps:
        try:
            if st[0] == "do":
                exec(st[1], ns)
                res.append(None)
            elif st[0] == "eq":
                res.append(repr(eval(st[1], ns)))
            elif st[0] in ("raises", "raisesre"):
                try:
                    exec(st[2], ns)
                except BaseException as ex:
                    import re as _re
                    ok = type(ex).__name__ == st[1] and (st[0] == "raises" or _re.search(st[3], str(ex)))
                    res.append("OK" if ok else "WRONG " + type(ex).__name__ + ": " + str(ex))
                else:
                    res.append("NO RAISE")
        except BaseException as ex:
            res.append("ERROR " + type(ex).__name__ + ": " + str(ex))
    out.append(res)
print(json.dumps(out))
'''


def run_groups(files: dict[str, str], imports: str, groups: list) -> list:
    payload = json.dumps({"imports": imports, "groups": groups})
    r = run(merged(files, {"_driver.py": DRIVER, "_groups.json": payload}), "python3 _driver.py", timeout=60)
    if not r.ok:
        raise RuntimeError("gold driver failed:\n" + r.out[-2000:])
    return json.loads(r.out.strip().splitlines()[-1])


def corrupt_literal(val: str, k: int) -> str | None:
    """A plausible but wrong replacement for an expected value (None if the value has no obvious corruption)."""
    try:
        v = ast.literal_eval(val)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(v, bool):
        return repr(not v)
    if isinstance(v, int):
        return repr(v + [1, -1, 5, 10, 100, -10][k % 6] if v + 1 != 0 else v + 7)
    if isinstance(v, float):
        return repr(round(v + 0.5, 3))
    if isinstance(v, str):
        return repr(v + "!") if v else repr("x")
    if isinstance(v, (list, tuple)) and len(v) > 1:
        w = list(reversed(v))
        if w == list(v):
            w = w[1:]
        return repr(type(v)(w))
    if isinstance(v, list):
        return repr(v + [0])
    if isinstance(v, dict) and v:
        k0 = sorted(v, key=repr)[0]
        w = dict(v)
        w[k0] = corrupt_literal(repr(v[k0]), k) and ast.literal_eval(corrupt_literal(repr(v[k0]), k))
        return repr(w) if w != v else None
    return None


def eq_index(groups: list, results: list) -> list[tuple[int, int, int, str, str]]:
    """Every checkable `eq` step as (global index, group, step, expression, expected literal)."""
    out, n = [], 0
    for gi, ((name, steps), res) in enumerate(zip(groups, results)):
        for si, (st, val) in enumerate(zip(steps, res)):
            if st[0] == "eq" and val is not None and not val.startswith("ERROR"):
                out.append((n, gi, si, st[1], val))
                n += 1
    return out


def gold_tests(files: dict[str, str], imports: str, groups: list, header: str = "", path: str = "tests/test_gold.py",
               cls: str = "GoldTests", corrupt: dict | None = None) -> dict[str, str]:
    """``corrupt`` maps a global `eq` index to a replacement literal (a wrong expectation)."""
    results = run_groups(files, imports, groups)
    corrupt = corrupt or {}
    lines = ["import unittest", ""]
    if header:
        lines += [header.rstrip("\n"), ""]
    lines += [imports.rstrip("\n"), "", "", f"class {cls}(unittest.TestCase):"]
    n = 0
    for (name, steps), res in zip(groups, results):
        if not steps:
            continue
        lines.append(f"    def test_{name}(self):")
        for st, val in zip(steps, res):
            if st[0] == "do":
                for ln in st[1].split("\n"):
                    lines.append("        " + ln)
            elif st[0] == "eq":
                if val is None or val.startswith("ERROR"):
                    raise RuntimeError(f"gold step {st[1]!r} failed: {val}")
                lines.append(f"        self.assertEqual({st[1]}, {corrupt.get(n, val)})")
                n += 1
            else:
                if val != "OK":
                    raise RuntimeError(f"gold step {st[2]!r} should raise {st[1]}: {val}")
                if st[0] == "raisesre":
                    lines.append(f"        with self.assertRaisesRegex({st[1]}, {st[3]!r}):")
                else:
                    lines.append(f"        with self.assertRaises({st[1]}):")
                for ln in st[2].split("\n"):
                    lines.append("            " + ln)
        lines.append("")
    return {path: "\n".join(lines).rstrip("\n") + "\n"}
