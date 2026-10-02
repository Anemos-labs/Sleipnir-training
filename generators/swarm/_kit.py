"""Helpers shared by the swarm generators: the hidden scorer, team descriptions, small prose pools."""
from __future__ import annotations

import json
import random

from fx import dd

SCORE_PY = dd('''
    #!/usr/bin/env python3
    """Hidden scorer: runs every unit in its own process and prints {"score": fraction} as the last line."""
    import json
    import os
    import subprocess
    import sys

    UNITS = json.loads(%(units)s)


    def main():
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        got = total = 0.0
        for u in UNITS:
            w = u.get("weight", 1)
            total += w
            try:
                p = subprocess.run(u["cmd"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   timeout=u.get("timeout", 60), env=env, text=True, errors="replace")
                ok, tail = p.returncode == 0, p.stdout[-700:]
            except subprocess.TimeoutExpired:
                ok, tail = False, "timed out"
            if ok:
                got += w
            sys.stderr.write("[%%s] %%s\\n" %% ("ok" if ok else "FAIL", u["name"]))
            if not ok:
                sys.stderr.write(tail + "\\n")
        print(json.dumps({"score": round(got / total, 6)}))


    main()
''')

GRADE_CMD = "python3 .grade/score.py"


def score_script(units: list[dict]) -> str:
    """units: [{"name", "cmd": [argv...], "weight": 1}] -> text of .grade/score.py"""
    return SCORE_PY % {"units": repr(json.dumps(units, sort_keys=True))}


def unit_test(name: str, path: str, weight: float = 1.0) -> dict:
    return {"name": name, "cmd": ["python3", path], "weight": weight}


ROLE_SETS = [
    ["backend", "tester"], ["backend", "reviewer"], ["fullstack", "tester"], ["backend", "tester", "reviewer"],
    ["backend", "docs"], ["fullstack", "reviewer", "tester"], ["backend", "frontend", "tester"], ["scout", "backend"],
]


def team(rng: random.Random, agents: int, roles: list[str] | None = None) -> dict:
    pool = list(roles) if roles else list(rng.choice(ROLE_SETS))
    return {"mode": "swarm", "agents": agents, "roles": pool[: max(2, agents)]}


WORDS = ["amber", "birch", "cobalt", "dune", "ember", "fjord", "garnet", "harbor", "indigo", "juniper", "kelp", "lumen", "marble",
         "nectar", "onyx", "pebble", "quartz", "russet", "sable", "tundra", "umber", "velvet", "willow", "yarrow", "zephyr"]

COMPANIES = ["Halvard Marine", "Pinecrest Labs", "Oddfellow Works", "Brightwater Co-op", "Tern & Tallow", "Quillon Systems",
             "Marrow Valley Council", "Saltmarsh Press", "Kestrel Logistics", "Ninefold Studio", "Bramblewick Farms",
             "Lowmoor Observatory", "Candlewick Rail", "Ashgrove Clinic", "Driftwood Games", "Penhallow Archive"]

SIGNOFFS = ["Thanks.", "", "Please keep it tidy.", "No rush on the style, I care about correctness.", "Ping me when it is green.",
            "Don't touch the tests.", "The SPEC.md next to each package is the contract.", "I'll review the diff afterwards.", ""]


def pick(rng: random.Random, seq):
    return seq[rng.randrange(len(seq))]


def enum(items: list[str], style: str = "bullets") -> str:
    if style == "numbered":
        return "\n".join(f"{i + 1}. {t}" for i, t in enumerate(items))
    return "\n".join(f"- {t}" for t in items)


def oxford(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]
