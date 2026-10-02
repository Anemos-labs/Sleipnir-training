#!/usr/bin/env python3
"""Hidden checker for the debug tasks: scores the agent's answer file field by field against spec.json.

Strict about the schema (exactly the declared keys, right types, vocabulary), lenient about wording: names are compared
after normalisation, evidence by file and line window, free text only for length and a few key words.
score = share of fields that are right.  Optional extra scenarios (run the code after the agent's fix) are scored too.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = json.load(open(os.path.join(HERE, "spec.json"), encoding="utf-8"))
EVID = re.compile(r"^\s*(.+?):(\d+)(?:\s*-\s*(\d+))?\s*$")


def finish(score, msg=""):
    if msg:
        print(msg)
    print(json.dumps({"score": max(0.0, min(1.0, score))}))
    sys.exit(0)


def norm_path(p):
    p = p.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def same_file(a, b):
    a, b = norm_path(a), norm_path(b)
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def norm_name(s):
    s = s.strip()
    s = re.sub(r"\(.*$", "", s)
    s = re.split(r"::|#|\.", s)[-1] if re.search(r"[A-Za-z_]", s) else s
    return s.strip().lower()


def norm_text(s):
    return re.sub(r"[\s`'\"]+", " ", s.strip().lower())


def check_field(name, rule, val):
    t = rule["type"]
    if t == "path":
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"{name}: expected a path string")
        return any(same_file(val, a) for a in rule["accept"])
    if t == "name":
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"{name}: expected a non-empty string")
        return norm_name(val) in {norm_name(a) for a in rule["accept"]}
    if t == "enum":
        if not isinstance(val, str) or val not in rule["allowed"]:
            raise ValueError(f"{name}: must be one of {rule['allowed']}")
        return val in rule["accept"]
    if t == "string":
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"{name}: expected a non-empty string")
        v = norm_text(val)
        return any(v == norm_text(a) for a in rule["accept"])
    if t == "string_in":
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"{name}: expected a non-empty string")
        v = norm_text(val)
        return any(norm_text(a) in v for a in rule["accept"]) and not any(norm_text(b) in v for b in rule.get("reject", []))
    if t == "number":
        if not isinstance(val, (str, int)) or isinstance(val, bool):
            raise ValueError(f"{name}: expected a string or integer")
        m = re.search(r"\d+", str(val))
        return bool(m) and int(m.group(0)) in {int(a) for a in rule["accept"]}
    if t == "string_all":
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"{name}: expected a non-empty string")
        v = norm_text(val)
        return all(norm_text(a) in v for a in rule["accept"])
    if t == "evidence":
        if not isinstance(val, list) or not 1 <= len(val) <= 10 or not all(isinstance(x, str) for x in val):
            raise ValueError(f"{name}: expected a list of 1-10 strings like 'path:line' or 'path:first-last'")
        ok = False
        slack = rule.get("slack", 1)
        for x in val:
            m = EVID.match(x)
            if not m:
                raise ValueError(f"{name}: {x!r} is not 'path:line' or 'path:first-last'")
            lo = int(m.group(2))
            hi = int(m.group(3) or lo)
            if hi < lo or hi - lo > 40:
                continue
            for w in rule["windows"]:
                if same_file(m.group(1), w["file"]) and lo <= w["end"] + slack and hi >= w["start"] - slack:
                    ok = True
        return ok
    if t == "text":
        if not isinstance(val, str):
            raise ValueError(f"{name}: expected a string")
        v = val.strip()
        if len(v) < rule.get("min_len", 20):
            return False
        words = rule.get("any", [])
        return not words or any(w.lower() in v.lower() for w in words)
    raise ValueError(f"unknown rule type {t}")


def main():
    path = SPEC.get("answer_file", "diagnosis.json")
    if not os.path.exists(path):
        finish(0.0, f"{path} not found")
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        finish(0.0, f"{path} is not valid JSON: {e}")
    fields = SPEC["fields"]
    if not isinstance(data, dict) or set(data) != set(fields):
        finish(0.0, f"expected an object with exactly the keys {sorted(fields)}")
    ok = 0
    total = len(fields)
    for name, rule in fields.items():
        try:
            good = check_field(name, rule, data[name])
        except ValueError as e:
            finish(0.0, str(e))
        print(f"  {name}: {'ok' if good else 'wrong'}")
        ok += 1 if good else 0
    extra = SPEC.get("run")
    if extra:  # fix-too tasks: the repaired code must reproduce the expected output
        total += 1
        try:
            p = subprocess.run(["bash", "-c", extra["cmd"]], capture_output=True, text=True, timeout=extra.get("timeout", 60))
            out = p.stdout + p.stderr
        except subprocess.TimeoutExpired:
            out = ""
        good = out.strip() == extra["expect"].strip()
        print(f"  repaired behaviour: {'ok' if good else 'wrong'}")
        ok += 1 if good else 0
    finish(ok / total)


if __name__ == "__main__":
    main()
