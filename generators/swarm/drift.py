"""Pipeline stages that each pass their own checks but have drifted from the shared CONTRACT.md; only the whole chain shows it."""
from __future__ import annotations

import base64
import json
import zlib
from datetime import datetime, timedelta

from fx import Task, dd, family, merged, run

from ._kit import GRADE_CMD, oxford, score_script, team

SKINS = [
    dict(key="marina", place="a small marina", slot="berth", unit="boat", prefix="B", what="mooring", night="night"),
    dict(key="campsite", place="a lakeside campsite", slot="pitch", unit="caravan", prefix="C", what="pitch fee", night="night"),
    dict(key="boatyard", place="a boatyard's winter storage", slot="bay", unit="hull", prefix="H", what="storage", night="day"),
    dict(key="airfield", place="a grass airfield", slot="stand", unit="aircraft", prefix="A", what="parking", night="night"),
]
STAGES = ["intake", "pricing", "allocate", "invoice", "notify"]
DRIFTS = {
    "intake": ["id_case", "no_utc", "length_trunc", "lenient"],
    "pricing": ["float_dollars", "bankers", "band_edge", "silent"],
    "allocate": ["zero_based", "unsorted", "touching"],
    "invoice": ["dollars_total", "vat_floor", "none_on_error"],
    "notify": ["utc_shown", "total_fmt", "plural"],
}


def intake_src(sk, p, dr):
    ret_id = 'f"{PREFIX}-{int(m.group(1)):04d}"' + (".lower()" if "id_case" in dr else "")
    rnd = "ROUND_DOWN" if "length_trunc" in dr else "ROUND_HALF_UP"
    off = "" if "no_utc" in dr else "    dt -= sign * timedelta(hours=int(m.group(4)), minutes=int(m.group(5)))\n"
    body = f'''"""Booking intake: raw form rows -> bookings (CONTRACT.md)."""
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP

__all__ = ["parse_row"]

PREFIX = "{sk["prefix"]}"


def _id(text):
    m = re.fullmatch(r"(?:{sk["prefix"]}|{sk["prefix"].lower()})?-?([0-9]{{1,4}})", text.strip())
    if not m:
        raise ValueError("bad id " + repr(text))
    return {ret_id}


def _arrive(text):
    m = re.fullmatch(r"([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}) ([0-9]{{2}}:[0-9]{{2}}) ([+-])([0-9]{{2}}):([0-9]{{2}})", text.strip())
    if not m:
        raise ValueError("bad arrival time " + repr(text))
    try:
        dt = datetime.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError("impossible arrival time " + repr(text)) from None
    sign = 1 if m.group(3) == "+" else -1
{off}    return dt.strftime("%Y-%m-%dT%H:%M")


def _length_dm(text):
    try:
        v = Decimal(text.strip())
    except InvalidOperation:
        raise ValueError("bad length " + repr(text)) from None
    if v <= 0:
        raise ValueError("length must be positive")
    return int((v * 10).quantize(Decimal(1), rounding={rnd}))


def _parse(row):
    nights = int(str(row["nights"]).strip())
    if nights < 1:
        raise ValueError("nights must be at least 1")
    return {{"id": _id(row["id"]), "name": " ".join(row["name"].split()), "arrive_utc": _arrive(row["arrive"]), "nights": nights,
            "length_dm": _length_dm(row["length_m"])}}


def parse_row(row):
'''
    if "lenient" in dr:
        body += "    try:\n        return _parse(row)\n    except (ValueError, KeyError):\n        return None\n"
    else:
        body += "    return _parse(row)\n"
    return body


def pricing_src(sk, p, dr):
    cmp_ = "<" if "band_edge" in dr else "<="
    disc = "round(base * PCT / 100)" if "bankers" in dr else "(base * PCT * 2 + 100) // 200"
    out = "base / 100" if "float_dollars" in dr else "base"
    guard = ("    if \"length_dm\" not in booking:\n        return booking\n" if "silent" in dr
             else "    if \"length_dm\" not in booking:\n        raise ValueError(\"booking has no length\")\n")
    return f'''"""Pricing: bookings -> priced bookings (CONTRACT.md)."""

__all__ = ["price"]

BANDS = {p["bands"]!r}  # (longest length in dm that is still in the band, cents per {sk["night"]}); None = no limit
LONG_STAY_NIGHTS = {p["long_n"]}
PCT = {p["long_pct"]}


def _rate(length_dm):
    for upto, cents in BANDS:
        if upto is None or length_dm {cmp_} upto:
            return cents


def price(booking):
{guard}    base = _rate(booking["length_dm"]) * booking["nights"]
    if booking["nights"] >= LONG_STAY_NIGHTS:
        base -= {disc}
    return {{**booking, "price_cents": {out}}}
'''


def allocate_src(sk, p, dr):
    idx = "i" if "zero_based" in dr else "i + 1"
    order = "list(bookings)" if "unsorted" in dr else 'sorted(bookings, key=lambda b: (b["arrive_utc"], b["id"]))'
    free = "end < s or start > e" if "touching" in dr else "end <= s or start >= e"
    return f'''"""Slot allocation: priced bookings -> bookings with a slot (CONTRACT.md)."""
from datetime import datetime, timedelta

__all__ = ["assign"]

SLOTS = {p["slots"]!r}  # length in dm that each {sk["slot"]} takes, {sk["slot"]} 1 first
FMT = "%Y-%m-%dT%H:%M"


def assign(bookings):
    busy = [[] for _ in SLOTS]
    out = []
    for b in {order}:
        start = datetime.strptime(b["arrive_utc"], FMT)
        end = start + timedelta(days=b["nights"])
        for i, size in enumerate(SLOTS):
            if size >= b["length_dm"] and all({free} for s, e in busy[i]):
                busy[i].append((start, end))
                out.append({{**b, "slot": {idx}}})
                break
        else:
            raise ValueError("no {sk["slot"]} for " + b["id"])
    return out
'''


def invoice_src(sk, p, dr):
    vat = "net * VAT_PCT // 100" if "vat_floor" in dr else "(net * VAT_PCT * 2 + 100) // 200"
    tot = "(net + vat) / 100" if "dollars_total" in dr else "net + vat"
    guard = ('    if "price_cents" not in booking:\n        return None\n' if "none_on_error" in dr
             else '    if "price_cents" not in booking:\n        raise ValueError("booking is not priced")\n')
    return f'''"""Invoices: priced bookings -> invoices (CONTRACT.md)."""

__all__ = ["make"]

VAT_PCT = {p["vat"]}


def make(booking):
{guard}    net = booking["price_cents"]
    vat = {vat}
    return {{"id": booking["id"], "lines": [{{"label": "{sk["what"]}", "cents": net}}, {{"label": "vat", "cents": vat}}], "total_cents": {tot}}}
'''


def notify_src(sk, p, dr):
    shift = "0" if "utc_shown" in dr else "LOCAL_OFFSET"
    money = '"%.1f" % (total / 100)' if "total_fmt" in dr else '"%d.%02d" % (total // 100, total % 100)'
    plural = '"nights"' if "plural" in dr else '"" if n == 1 else "s"'
    if "plural" in dr:
        word = f'"{sk["night"]}s"'
    else:
        word = f'"{sk["night"]}" if n == 1 else "{sk["night"]}s"'
    return f'''"""Guest messages (CONTRACT.md): the only place that shows local time."""
from datetime import datetime, timedelta

__all__ = ["render"]

LOCAL_OFFSET = {p["offset"]}  # hours ahead of UTC
FMT = "%Y-%m-%dT%H:%M"


def render(booking, invoice):
    local = datetime.strptime(booking["arrive_utc"], FMT) + timedelta(hours={shift})
    n = booking["nights"]
    total = invoice["total_cents"]
    return "Booking %s: {sk["slot"]} %d, arriving %s local, %d %s, total %s" % (
        booking["id"], booking["slot"], local.strftime("%Y-%m-%d %H:%M"), n, {word}, {money})
'''


SRC = {"intake": intake_src, "pricing": pricing_src, "allocate": allocate_src, "invoice": invoice_src, "notify": notify_src}


def contract_md(sk, p):
    return dd(f'''
        # Booking pipeline contract

        {sk["place"][0].upper() + sk["place"][1:]} runs its bookings through five stages, each a module in `pipeline/`:
        `intake.parse_row` -> `pricing.price` -> `allocate.assign` -> `invoice.make` -> `notify.render`.
        Every stage is owned by a different person and was tested in isolation, which is how the conventions below drifted apart.
        **These conventions hold in every module, on every input and output.**

        1. **Ids** are `{sk["prefix"]}-` and four digits, zero-padded, upper case: `{sk["prefix"]}-0042`.
        2. **Time** inside the pipeline is ISO `YYYY-MM-DDTHH:MM` in **UTC**. Raw forms carry an offset (`2024-06-01 14:30 +02:00`) and intake converts to UTC.
           Only `notify` shows local time, which is UTC plus the fixed offset in its `LOCAL_OFFSET`.
        3. **Money** is an integer number of cents, in fields whose names end in `_cents`. Nothing inside the pipeline is a float.
        4. **Lengths** are integer decimetres (`length_dm`); raw forms give metres as a decimal text. Rounding anywhere is **half up** (`.5` goes up), never banker's rounding
           and never truncation unless a stage says so.
        5. **Length bands** are inclusive at the top: a length equal to the band's limit is in that band.
        6. **Slots** are numbered from 1. A slot is free again at the instant of departure (`arrive + nights * 24 h`): back-to-back bookings may share a slot.
        7. **Order**: `allocate.assign` returns its bookings sorted by `(arrive_utc, id)` whatever order it was given, and assigns each booking the lowest-numbered free slot that is long enough.
        8. **Errors**: a stage that is given something invalid (a bad row, an unpriced booking, no slot left) raises `ValueError`. It never returns `None` or a half-filled record.

        ## Stages in one line each

        * `parse_row(row)`: raw row `{{"id", "name", "arrive", "nights", "length_m"}}` -> `{{"id", "name", "arrive_utc", "nights", "length_dm"}}`; the id may come as `b42`, `B-42`, `42`;
          `name` has its whitespace collapsed; `nights` must be at least 1.
        * `price(booking)`: adds `price_cents`: the rate of the booking's length band times `nights`, minus a long-stay discount (from {p["long_n"]} nights, {p["long_pct"]}% of the amount, half up).
        * `assign(bookings)`: returns the bookings with `slot` added; see 6 and 7.
        * `make(booking)`: `{{"id", "lines": [{{"label", "cents"}}, ...], "total_cents"}}`: the fee line, then a `vat` line of {p["vat"]}% of the fee (half up); total is their sum.
        * `render(booking, invoice)`: one line such as `Booking {sk["prefix"]}-0042: {sk["slot"]} 3, arriving 2024-06-01 16:30 local, 2 {sk["night"]}s, total 123.45`
          (`{sk["night"]}` in the singular for exactly 1; the total always has two decimals).
    ''')


def ref_eval(files_ref, **parts):
    base = {"rows": [], "priced_in": [], "alloc_in": [], "invoice_in": [], "notify_in": [], "e2e": []}
    base.update(parts)
    res = run(merged(files_ref, {"_cases.json": json.dumps(base), "_ref.py": REF_SCRIPT}), "python3 _ref.py", timeout=90)
    if not res.ok:
        raise RuntimeError("reference run failed:\n" + res.out[-1500:])
    return json.loads(zlib.decompress(base64.b64decode(res.out.strip().splitlines()[-1])))


def gen_rows(rng, sk, p, n, errors=False):
    rows = []
    for i in range(n):
        num = rng.randint(1, 9999)
        idtxt = rng.choice([f"{sk['prefix'].lower()}{num}", f"{sk['prefix']}-{num}", str(num), f"{sk['prefix']}{num:04d}"])
        day = datetime(2024, 5, 1) + timedelta(days=rng.randint(0, 60), hours=rng.randint(0, 23), minutes=rng.choice([0, 15, 30, 45]))
        off = rng.choice(["+02:00", "-05:30", "+00:00", "+09:00", "-08:00", "+01:00"])
        length = rng.choice([f"{rng.randint(4, 24)}.{rng.randint(0, 9)}", f"{rng.randint(5, 20)}.{rng.choice([25, 45, 5, 95])}", str(rng.randint(5, 20))])
        rows.append({"id": idtxt, "name": rng.choice(["Mira", "  Old  Salt ", "Kittiwake", "Blue  Heron", "Wren", "Sandpiper"]),
                     "arrive": day.strftime("%Y-%m-%d %H:%M") + " " + off, "nights": str(rng.choice([1, 1, 2, 3, 5, 6, 7, 8, 10, 14])), "length_m": length})
    if errors:
        rows[0] = dict(rows[0], nights="0")
        rows[1 % n] = dict(rows[1 % n], id="zz9")
        rows[2 % n] = dict(rows[2 % n], arrive="2024-02-30 10:00 +00:00")
        rows[3 % n] = dict(rows[3 % n], length_m="-3")
        rows[4 % n] = dict(rows[4 % n], length_m="big")
    return rows


REF_SCRIPT = '''import base64, json, sys, zlib
sys.path.insert(0, ".")
from pipeline import intake, pricing, allocate, invoice, notify

data = json.load(open("_cases.json"))
out = {}


def call(fn, *a):
    try:
        return {"ok": fn(*a)}
    except ValueError:
        return {"error": "ValueError"}


out["intake"] = [call(intake.parse_row, r) for r in data["rows"]]
good = [x["ok"] for x in out["intake"] if "ok" in x]
out["pricing"] = [call(pricing.price, b) for b in data["priced_in"]]
out["allocate"] = [call(allocate.assign, bs) for bs in data["alloc_in"]]
out["invoice"] = [call(invoice.make, b) for b in data["invoice_in"]]
out["notify"] = [call(notify.render, b, inv) for b, inv in data["notify_in"]]
rows = data["e2e"]
try:
    if rows:
        placed = allocate.assign([pricing.price(intake.parse_row(r)) for r in rows])
        out["e2e"] = [notify.render(b, invoice.make(b)) for b in placed]
    else:
        out["e2e"] = []
except ValueError as e:
    out["e2e"] = {"error": str(e)}
print(base64.b64encode(zlib.compress(json.dumps(out).encode(), 9)).decode())
'''

HIDDEN = '''import json
import os
import sys

sys.path.insert(0, os.getcwd())
from pipeline import allocate, intake, invoice, notify, pricing

CASES = json.loads(%(cases)r)
STAGE = sys.argv[1]


def same(got, want):
    if isinstance(want, list):
        return isinstance(got, list) and len(got) == len(want) and all(same(g, w) for g, w in zip(got, want))
    if isinstance(want, dict):
        return isinstance(got, dict) and got.keys() == want.keys() and all(same(got[k], want[k]) for k in want)
    return type(got) is type(want) and got == want


def call(fn, *a):
    try:
        return {"ok": fn(*a)}
    except ValueError:
        return {"error": "ValueError"}
    except Exception as e:  # noqa: BLE001
        return {"error": type(e).__name__}


def run():
    if STAGE == "intake":
        pairs = [(call(intake.parse_row, r), w) for r, w in zip(CASES["rows"], CASES["want"]["intake"])]
        inputs = CASES["rows"]
    elif STAGE == "pricing":
        pairs = [(call(pricing.price, b), w) for b, w in zip(CASES["priced_in"], CASES["want"]["pricing"])]
        inputs = CASES["priced_in"]
    elif STAGE == "allocate":
        pairs = [(call(allocate.assign, bs), w) for bs, w in zip(CASES["alloc_in"], CASES["want"]["allocate"])]
        inputs = CASES["alloc_in"]
    elif STAGE == "invoice":
        pairs = [(call(invoice.make, b), w) for b, w in zip(CASES["invoice_in"], CASES["want"]["invoice"])]
        inputs = CASES["invoice_in"]
    elif STAGE == "notify":
        pairs = [(call(notify.render, b, i), w) for (b, i), w in zip(CASES["notify_in"], CASES["want"]["notify"])]
        inputs = CASES["notify_in"]
    else:
        rows = CASES["e2e"]
        got = [notify.render(b, invoice.make(b)) for b in allocate.assign([pricing.price(intake.parse_row(r)) for r in rows])]
        for g, w in zip(got, CASES["want"]["e2e"]):
            if g != w:
                return "got %%r, want %%r" %% (g, w)
        return None
    for (g, w), x in zip(pairs, inputs):
        if not same(g, w):
            return "input %%r\\n  got  %%r\\n  want %%r" %% (x, g, w)
    return None


msg = run()
if msg:
    print("FAILED:", msg, file=sys.stderr)
    sys.exit(1)
'''

VISIBLE_TEST = '''import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pipeline import allocate, intake, invoice, notify, pricing


class StageShapes(unittest.TestCase):
    """Each stage on its own: shapes only. The conventions are in CONTRACT.md."""

    def test_intake_shape(self):
        b = intake.parse_row({"id": "7", "name": "Mira", "arrive": "2024-06-01 14:30 +02:00", "nights": "2", "length_m": "9"})
        self.assertEqual(set(b), {"id", "name", "arrive_utc", "nights", "length_dm"})

    def test_pricing_adds_a_price(self):
        out = pricing.price({"id": "X", "nights": 1, "length_dm": 90})
        self.assertIn("price_cents", out)

    def test_allocate_adds_slots(self):
        out = allocate.assign([{"id": "X", "arrive_utc": "2024-06-01T10:00", "nights": 1, "length_dm": 60}])
        self.assertEqual(len(out), 1)
        self.assertIn("slot", out[0])

    def test_invoice_has_lines(self):
        inv = invoice.make({"id": "X", "price_cents": 1000})
        self.assertEqual(inv["id"], "X")
        self.assertEqual(len(inv["lines"]), 2)

    def test_notify_mentions_the_booking(self):
        text = notify.render({"id": "X", "slot": 1, "arrive_utc": "2024-06-01T10:00", "nights": 1}, {"total_cents": 100})
        self.assertIn("X", text)


if __name__ == "__main__":
    unittest.main()
'''

SCENARIO = '''"""Run a few raw rows through the whole chain and print what the guests would be told."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import allocate, intake, invoice, notify, pricing

ROWS = %(rows)r

parsed = [intake.parse_row(r) for r in ROWS]
priced = [pricing.price(b) for b in parsed]
placed = allocate.assign(priced)
for b in placed:
    print(notify.render(b, invoice.make(b)))
'''


@family("swarm-contract-drift", category="swarm", lang="python", kind="fix", n=12,
        summary="five pipeline stages that drifted from a shared contract (units, time zones, rounding, indexing); each passes alone, the chain is wrong")
def contract_drift(rng, n):
    plan = [2, 3, 3, 4, 3, 4, 5, 4, 5, 5, 4, 5]
    for i in range(n):
        sk = SKINS[i % len(SKINS)]
        nd = plan[i % len(plan)]
        drifted_stages = sorted(rng.sample(STAGES, nd), key=STAGES.index)
        drifts = {s: set() for s in STAGES}
        for s in drifted_stages:
            pool = DRIFTS[s]
            drifts[s].add(rng.choice(pool))
            if nd >= 5 and rng.random() < 0.5:
                drifts[s].add(rng.choice(pool))
        b0 = rng.choice([60, 70, 80])
        bands = [(b0, rng.choice([1800, 2200, 2500])), (b0 + 40, rng.choice([3100, 3500, 3900])), (b0 + 90, rng.choice([4800, 5400, 6100])), (None, rng.choice([7600, 8300, 9100]))]
        slot_sizes = sorted([260] + [rng.choice([b0, b0 + 40, b0 + 40, b0 + 90, b0 + 90, 260, 300]) for _ in range(rng.randint(8, 10))])
        p = {"bands": bands, "long_n": rng.choice([5, 7, 10]), "long_pct": rng.choice([5, 10, 12, 15]), "slots": slot_sizes, "vat": rng.choice([5, 7, 9, 19, 21]),
             "offset": rng.choice([1, 2, 3, -4, 5, 9])}
        ref = {s: SRC[s](sk, p, set()) for s in STAGES}
        start_src = {s: SRC[s](sk, p, drifts[s]) for s in STAGES}
        for s in drifted_stages:
            if start_src[s] == ref[s]:
                raise RuntimeError("drift had no effect on " + s)
        files_ref = {f"pipeline/{s}.py": ref[s] for s in STAGES}
        files_ref["pipeline/__init__.py"] = ""
        # cases
        rows = gen_rows(rng, sk, p, 40, errors=True)
        e2e_rows = gen_rows(rng, sk, p, 26)
        for j, r in enumerate(e2e_rows):
            r["id"] = f"{sk['prefix']}{j + 1}"
            r["nights"] = str(min(int(r["nights"]), 10))
        for _ in range(12):
            out = ref_eval(files_ref, e2e=e2e_rows)["e2e"]
            if not isinstance(out, dict):
                break
            bad = out["error"].rsplit(" ", 1)[-1]
            e2e_rows = [r for r in e2e_rows if f"{sk['prefix']}-{int(r['id'][1:]):04d}" != bad]
        else:
            raise RuntimeError("could not make the end-to-end rows allocatable")
        parsed_ok = ref_eval(files_ref, rows=rows)["intake"]
        good = [x["ok"] for x in parsed_ok if "ok" in x]
        priced_in = [dict(b) for b in good[:25]] + [{"id": "X-1", "nights": 2}, {**good[0], "length_dm": b0}, {**good[0], "length_dm": b0 + 1},
                                                    {**good[0], "length_dm": b0 + 40}, {**good[0], "nights": p["long_n"]}, {**good[0], "nights": p["long_n"] - 1}]
        for nights in (p["long_n"], p["long_n"] + 1, p["long_n"] + 3):
            for ln in (b0 - 10, b0 + 20, b0 + 70, b0 + 120):
                priced_in.append({**good[0], "nights": nights, "length_dm": ln})
        priced_ok = ref_eval(files_ref, priced_in=priced_in)["pricing"]
        priced_bookings = [x["ok"] for x in priced_ok if "ok" in x]
        alloc_in = []
        for _ in range(6):
            bs = [dict(b) for b in rng.sample(priced_bookings, min(len(priced_bookings), rng.randint(2, 6)))]
            for k_, b in enumerate(bs):
                b["id"] = f"{sk['prefix']}-{k_ + 1:04d}"
            rng.shuffle(bs)
            alloc_in.append(bs)
        t0 = datetime(2024, 6, 1, 12, 0)
        b2b = [{"id": f"{sk['prefix']}-0002", "name": "n", "arrive_utc": (t0 + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"), "nights": 1, "length_dm": b0, "price_cents": 100},
               {"id": f"{sk['prefix']}-0001", "name": "n", "arrive_utc": t0.strftime("%Y-%m-%dT%H:%M"), "nights": 2, "length_dm": b0, "price_cents": 100},
               {"id": f"{sk['prefix']}-0003", "name": "n", "arrive_utc": t0.strftime("%Y-%m-%dT%H:%M"), "nights": 1, "length_dm": b0, "price_cents": 100}]
        alloc_in.append(b2b)
        alloc_in.append([{**b2b[0], "length_dm": 10_000}])
        invoice_in = [{"id": b["id"], "price_cents": b["price_cents"]} for b in priced_bookings[:14]] + [{"id": "Z"}, {"id": "Q", "price_cents": 10}, {"id": "R", "price_cents": 50}, {"id": "S", "price_cents": 1250}]
        notify_in = []
        for b in priced_bookings[:10]:
            nb = {**b, "slot": rng.randint(1, 8), "nights": rng.choice([1, 2, 5])}
            notify_in.append([nb, {"id": b["id"], "lines": [], "total_cents": rng.choice([5, 100, 12345, 99999, 250, 7])}])
        cases = {"rows": rows, "priced_in": priced_in, "alloc_in": alloc_in, "invoice_in": invoice_in, "notify_in": notify_in, "e2e": e2e_rows}
        want = ref_eval(files_ref, **cases)
        cases["want"] = want
        hidden = {".grade/chain_unit.py": HIDDEN % {"cases": json.dumps(cases, sort_keys=True)}}
        units = [{"name": s, "cmd": ["python3", ".grade/chain_unit.py", s], "weight": 1} for s in STAGES]
        units.append({"name": "end to end", "cmd": ["python3", ".grade/chain_unit.py", "e2e"], "weight": 2})
        hidden[".grade/score.py"] = score_script(units)
        start = {f"pipeline/{s}.py": start_src[s] for s in STAGES}
        start["pipeline/__init__.py"] = ""
        start["CONTRACT.md"] = contract_md(sk, p)
        start["tests/test_stages.py"] = VISIBLE_TEST
        start["scenario.py"] = SCENARIO % {"rows": [e2e_rows[0], e2e_rows[1], e2e_rows[2]]}
        start["README.md"] = f"# Booking pipeline\n\nFive stages in `pipeline/`, one contract in `CONTRACT.md`. `python3 scenario.py` runs three sample rows through the chain; `python3 -m unittest discover -s tests` checks each stage's shape.\n"
        solution = {f"pipeline/{s}.py": ref[s] for s in drifted_stages}
        voices = [
            f"The booking chain of {sk['place']} produces nonsense: every stage's tests are green, yet the messages to guests are wrong. CONTRACT.md fixes the conventions all five stages share. "
            f"Find out which stages have drifted from it and put them right; each stage can be audited separately.",
            f"Audit pipeline/ against CONTRACT.md. `python3 scenario.py` shows the end result looks off ({sk['slot']}s, totals, times), but each module passes its own tests. "
            f"Fix whatever deviates from the contract, in whichever stage it is.",
            f"Five people each wrote one stage of our {sk['unit']} booking pipeline and nobody agreed on conventions in the end. CONTRACT.md is the agreed version. "
            f"Bring every stage in line with it; don't change the contract.",
            f"Something in the {sk['slot']} booking chain doesn't match the contract (CONTRACT.md): units, time zones, rounding, numbering... I don't know which stages are affected. "
            f"Check all five and fix the deviations.",
        ]
        d = 3 if nd <= 2 else 4 if nd <= 4 else 5
        yield Task(
            slug=f"{i + 1:02d}-{sk['key']}-" + "-".join(s[:3] for s in drifted_stages),
            prompt=voices[i % len(voices)], difficulty=d, start=start, hidden=hidden, solution=solution,
            verify=GRADE_CMD, pass_mode="json-score", protected=["CONTRACT.md"],
            team=team(rng, min(5, nd + 1), ["backend", "tester", "reviewer"] if i % 2 else ["backend", "reviewer"]),
            tags=["contract", "integration", "audit"],
            notes={"skin": sk["key"], "drifted": {s: sorted(v) for s, v in drifts.items() if v}},
        )
