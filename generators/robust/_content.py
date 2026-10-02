"""Believable filler content (notes, CSV tables, logs, tiny scripts) for the robust generators."""
from __future__ import annotations

import random

SURNAMES = ["Aldous", "Berg", "Castellan", "Dunmore", "Eklund", "Fairweather", "Grimaldi", "Holt", "Iversen", "Jarrow", "Kowal", "Lindqvist", "Marsh", "Novak", "Orsini", "Penhale"]
GIVEN = ["Ana", "Bram", "Cleo", "Dov", "Edda", "Finn", "Greta", "Hugo", "Ines", "Jun", "Kari", "Lev", "Mina", "Nils", "Odile", "Pavel"]
PLACES = ["Harrow Ridge", "Salt Lode", "Wren Cove", "Tarn End", "Fennick", "Low Marsh", "Cairn Hill", "Pike Water", "Orchard Gate", "Brine Quay"]
WORDS = ["lantern", "ferry", "ledger", "orchard", "tarn", "quill", "bramble", "harbour", "cobble", "mosaic", "ember", "thistle", "pylon", "meadow", "gantry", "kiln",
         "tide", "wicker", "spindle", "fennel", "garret", "sluice", "pennant", "cairn", "dovecote", "brine", "skiff", "alder", "furrow", "lintel"]


def person(rng: random.Random) -> str:
    return f"{rng.choice(GIVEN)} {rng.choice(SURNAMES)}"


def sentence(rng: random.Random, lo=5, hi=12) -> str:
    ws = [rng.choice(WORDS) for _ in range(rng.randint(lo, hi))]
    return ws[0].capitalize() + " " + " ".join(ws[1:]) + "."


def paragraph(rng: random.Random, n=4) -> str:
    return " ".join(sentence(rng) for _ in range(n))


def notes(rng: random.Random, n=8, title="Notes") -> str:
    out = [f"# {title}", ""]
    for _ in range(n):
        out.append(f"- {sentence(rng, 4, 10)}")
    return "\n".join(out) + "\n"


def csv_table(rng: random.Random, header: list[str], n: int, kinds: list[str] | None = None) -> str:
    kinds = kinds or ["word"] * len(header)
    rows = [",".join(header)]
    for i in range(n):
        cells = []
        for k in kinds:
            if k == "int":
                cells.append(str(rng.randint(1, 9999)))
            elif k == "dec":
                cells.append(f"{rng.uniform(0, 500):.2f}")
            elif k == "name":
                cells.append(person(rng))
            elif k == "date":
                cells.append(f"20{rng.randint(15, 24):02d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}")
            elif k == "id":
                cells.append(f"{rng.choice('ABCDKR')}{rng.randint(1000, 9999)}")
            else:
                cells.append(rng.choice(WORDS))
        rows.append(",".join(cells))
    return "\n".join(rows) + "\n"


def log_lines(rng: random.Random, n=12) -> str:
    out = []
    for i in range(n):
        out.append(f"2024-0{rng.randint(1, 9)}-{rng.randint(10, 28)} {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d} {rng.choice(['INFO', 'INFO', 'WARN', 'ERROR'])} {rng.choice(WORDS)} {sentence(rng, 3, 7)}")
    return "\n".join(out) + "\n"


def tiny_script(rng: random.Random, name: str) -> str:
    a, b = rng.sample(WORDS, 2)
    return f'"""{name}: small helper."""\n\n\ndef {a}(rows):\n    return [r for r in rows if r]\n\n\ndef {b}(rows):\n    return sorted({a}(rows))\n'
