"""Write a python gold suite by *running* the reference implementation: expected values are never typed by hand.

``groups`` is a list of ``(test_name, steps)``; a step is

    ("do", "code")                  a statement (setup)
    ("eq", "expression")            assertEqual(expression, <what the reference returns>)
    ("raises", "ValueError", "code")  assertRaises(ValueError) around the code (checked to raise)

The generated file is a plain ``unittest`` module.
"""
from __future__ import annotations

import json

from fx import run
from fx.run import merged

DRIVER = r'''
import json, sys
sys.path.insert(0, ".")
GROUPS = json.loads(open("_groups.json").read())
IMPORTS = GROUPS["imports"]
out = []
for name, steps in GROUPS["groups"]:
    ns = {}
    exec(IMPORTS, ns)
    res = []
    for st in steps:
        try:
            if st[0] == "do":
                exec(st[1], ns)
                res.append(None)
            elif st[0] == "eq":
                res.append(repr(eval(st[1], ns)))
            elif st[0] == "raises":
                try:
                    exec(st[2], ns)
                except BaseException as ex:
                    res.append("OK" if type(ex).__name__ == st[1] else "WRONG " + type(ex).__name__ + ": " + str(ex))
                else:
                    res.append("NO RAISE")
        except BaseException as ex:
            res.append("ERROR " + type(ex).__name__ + ": " + str(ex))
    out.append(res)
print(json.dumps(out))
'''


def gold_tests(files: dict[str, str], imports: str, groups: list, header: str = "", path: str = "tests/test_gold.py",
               cls: str = "GoldTests") -> dict[str, str]:
    payload = json.dumps({"imports": imports, "groups": groups})
    r = run(merged(files, {"_driver.py": DRIVER, "_groups.json": payload}), "python3 _driver.py", timeout=60)
    if not r.ok:
        raise RuntimeError("gold driver failed:\n" + r.out[-2000:])
    results = json.loads(r.out.strip().splitlines()[-1])
    lines = ["import unittest", ""]
    if header:
        lines += [header.rstrip("\n"), ""]
    lines += [imports.rstrip("\n"), "", "", f"class {cls}(unittest.TestCase):"]
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
                lines.append(f"        self.assertEqual({st[1]}, {val})")
            else:
                if val != "OK":
                    raise RuntimeError(f"gold step {st[2]!r} should raise {st[1]}: {val}")
                lines.append(f"        with self.assertRaises({st[1]}):")
                for ln in st[2].split("\n"):
                    lines.append("            " + ln)
        lines.append("")
    return {path: "\n".join(lines).rstrip("\n") + "\n"}
