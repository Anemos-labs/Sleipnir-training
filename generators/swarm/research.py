"""One researcher, several implementers: fee rules scattered over a tariff, its amendments and its corrections."""
from __future__ import annotations

import json
from datetime import date, timedelta

from fx import Task, dd, family

from ._kit import GRADE_CMD, oxford, score_script, team

KINDS = [
    dict(key="berth", title="Berth dues", unit="started block of {step} hours of occupancy", step=4, qty="hours", classes=[("A", "under 40 m"), ("B", "40 to 79 m"), ("C", "80 to 119 m"), ("D", "120 m and over")],
         f1=("night", "an arrival or departure between 22:00 and 06:00 (night work)"), f2=("regular", "a vessel with ten or more calls in the previous twelve months"),
         rate=(900, 6000), sur=(10, 25), disc=(5, 15), minimum=(2500, 9000)),
    dict(key="pilotage", title="Pilotage", unit="movement (entering, leaving or shifting berth)", step=1, qty="movements", classes=[("S", "draft up to 4 m"), ("M", "draft over 4 m up to 7 m"), ("L", "draft over 7 m up to 10 m"), ("X", "draft over 10 m")],
         f1=("night", "a movement that starts between 21:00 and 06:00"), f2=("regular", "a vessel with an annual pilotage exemption certificate"),
         rate=(12000, 60000), sur=(20, 40), disc=(10, 30), minimum=(15000, 40000)),
    dict(key="waste", title="Waste reception levy", unit="started batch of {step} crew-days (crew on board multiplied by days in port)", step=5, qty="crew-days",
         classes=[("cargo", "cargo and bulk vessels"), ("ferry", "ferries and ro-ro vessels"), ("fishing", "fishing vessels"), ("yacht", "yachts and pleasure craft")],
         f1=("hazardous", "a vessel declaring hazardous waste"), f2=("green", "a vessel holding a green-ship certificate"),
         rate=(300, 1800), sur=(25, 60), disc=(10, 25), minimum=(1000, 4000)),
    dict(key="storage", title="Open storage charge", unit="started {step} tonnes per call", step=10, qty="tonnes",
         classes=[("dry", "dry bulk"), ("cold", "refrigerated goods"), ("hazard", "dangerous goods"), ("scrap", "scrap and recyclables")],
         f1=("outdoor", "goods kept on the open apron"), f2=("prepaid", "storage paid for in advance"),
         rate=(450, 2400), sur=(10, 30), disc=(3, 12), minimum=(1500, 5000)),
    dict(key="gate", title="Gate transaction fee", unit="truck passing the gate", step=1, qty="trucks",
         classes=[("std", "standard lane"), ("express", "express lane"), ("oog", "out-of-gauge lane"), ("reefer", "refrigerated lane")],
         f1=("after_hours", "a passage between 20:00 and 05:00"), f2=("booked", "a booking made at least a day ahead"),
         rate=(200, 900), sur=(30, 75), disc=(5, 20), minimum=(500, 1500)),
    dict(key="inspection", title="Quarantine inspection fee", unit="started {step} containers", step=2, qty="containers",
         classes=[("low", "low-risk goods"), ("mid", "medium-risk goods"), ("high", "high-risk goods")],
         f1=("weekend", "an inspection carried out on a Saturday or Sunday"), f2=("repeat", "a consignor with a clean record over the last 20 inspections"),
         rate=(1500, 7000), sur=(40, 90), disc=(10, 35), minimum=(3000, 9000)),
]

FILLER = [
    "The harbour office is staffed from 07:00 to 19:00 on weekdays; outside those hours calls go to the duty officer.",
    "Fees are stated in cents of the harbour currency and exclude any value-added tax that may apply.",
    "Invoices are issued at the end of each calendar month and are payable within thirty days.",
    "The authority reviews its tariff once a year; interim changes are published as numbered amendments.",
    "Complaints about an invoice must be sent in writing to the finance desk within sixty days of the invoice date.",
    "Vessels are classed by the harbour master on first arrival; the class is recorded on the vessel card.",
    "A service is charged at the tariff in force on the day it is performed, not on the day it is invoiced.",
    "The north quay was extended in 1998; the old customs shed is now used as the visitors' centre.",
    "Fees for services not listed here are agreed case by case with the harbour master.",
    "Disputed amounts are held until the harbour master has ruled, normally within ten working days.",
    "Tariff documents are archived by section; an amendment names the section it changes.",
]

NOTES_STYLE = ["Note that", "Please note that", "For the avoidance of doubt,", "It is confirmed that"]


def d(y, m, dd_):
    return date(y, m, dd_)


def hist_value(h, on):
    v = None
    for since, val in h:
        if since <= on:
            v = val
    return v


def ratio(n, dn):
    return (2 * n + dn) // (2 * dn)


def make_module(rng, kind, n_amend):
    classes = [c for c, _ in kind["classes"]]
    draws = sorted(rng.randrange(kind["rate"][0], kind["rate"][1], 5 if kind["rate"][0] > 400 else 1) for _ in classes)
    rates = {c: [("2019-01-01", draws[i])] for i, c in enumerate(classes)}
    sur = [("2019-01-01", rng.randint(*kind["sur"]))]
    disc = [("2019-01-01", rng.randint(*kind["disc"]))]
    minimum = [("2019-01-01", rng.randrange(kind["minimum"][0], kind["minimum"][1], 50))]
    cap = [("2019-01-01", None)]
    rnd = rng.choice([1, 5, 10])
    unit = kind["unit"].format(step=kind["step"])
    amendments = []  # dicts: iso, fmt (with {v}), param, key, val, printed
    dates = sorted({d(2020 + rng.randint(0, 4), rng.randint(1, 12), 1) for _ in range(n_amend + 3)})[:n_amend]
    for eff in dates:
        iso = eff.isoformat()
        choice = rng.choice(["rate", "rate", "sur", "disc", "min", "cap"])
        if choice == "rate":
            c = rng.choice(classes)
            cur = hist_value(rates[c], iso)
            new = max(1, cur + rng.choice([-1, 1]) * rng.randrange(max(5, cur // 20), max(10, cur // 6), 5))
            rates[c].append((iso, new))
            amendments.append(dict(iso=iso, fmt=f"the rate for class {c} is {{v}} per {unit} (previously {cur})", param="rate", key=c, val=new))
        elif choice == "sur":
            new = rng.randint(*kind["sur"]) + rng.choice([-3, 5, 7])
            cur = hist_value(sur, iso)
            if new == cur:
                new += 5
            sur.append((iso, new))
            amendments.append(dict(iso=iso, fmt=f"the {kind['f1'][0].replace('_', ' ')} surcharge changes from {cur}% to {{v}}%", param="sur", key=None, val=new))
        elif choice == "disc":
            new = rng.randint(*kind["disc"]) + rng.choice([-2, 4, 6])
            cur = hist_value(disc, iso)
            if new == cur:
                new += 3
            disc.append((iso, new))
            amendments.append(dict(iso=iso, fmt=f"the {kind['f2'][0]} discount changes from {cur}% to {{v}}%", param="disc", key=None, val=new))
        elif choice == "min":
            cur = hist_value(minimum, iso)
            new = max(100, cur + rng.choice([-1, 1]) * rng.randrange(200, 900, 50))
            minimum.append((iso, new))
            amendments.append(dict(iso=iso, fmt=f"the minimum charge changes from {cur} to {{v}}", param="min", key=None, val=new))
        else:
            cur = hist_value(cap, iso)
            if cur is None:
                top = max(hist_value(rates[c], iso) for c in classes)
                new = top * rng.randint(8, 14) * max(1, kind["step"])
                cap.append((iso, new))
                amendments.append(dict(iso=iso, fmt="a maximum charge of {v} per call is introduced", param="cap", key=None, val=new))
            else:
                cap.append((iso, None))
                amendments.append(dict(iso=iso, fmt=f"the maximum charge of {cur} per call is abolished", param="cap", key=None, val=None))
    for a in amendments:
        a["printed"] = a["val"]
    correction = None
    cands = [j for j, a in enumerate(amendments) if a["val"] is not None and a["param"] != "cap"]
    if cands and rng.random() < 0.6:
        j = rng.choice(cands)
        a = amendments[j]
        wrong = a["val"] + rng.choice([-1, 1]) * max(1, a["val"] // 10)
        a["printed"] = wrong
        correction = (j, wrong, a["val"], a["iso"])
    return {"kind": kind, "classes": classes, "rates": rates, "sur": sur, "disc": disc, "min": minimum, "cap": cap, "rnd": rnd,
            "amendments": amendments, "correction": correction}


def module_source(m):
    kind = m["kind"]
    f1, f2 = kind["f1"][0], kind["f2"][0]
    return f'''"""{kind["title"]}."""

__all__ = ["fee"]

CLASSES = {m["classes"]!r}
STEP = {kind["step"]}
FIRST = "2019-01-01"
RATES = {m["rates"]!r}
SURCHARGE = {m["sur"]!r}
DISCOUNT = {m["disc"]!r}
MINIMUM = {m["min"]!r}
CAP = {m["cap"]!r}
ROUND = {m["rnd"]}


def _at(history, on):
    value = None
    for since, v in history:
        if since <= on:
            value = v
    return value


def _ratio(n, d):
    return (2 * n + d) // (2 * d)


def fee(cls, qty, on, {f1}=False, {f2}=False):
    if cls not in CLASSES:
        raise ValueError("unknown class")
    if qty < 1:
        raise ValueError("qty must be at least 1")
    if on < FIRST:
        raise ValueError("no tariff before " + FIRST)
    units = -(-qty // STEP)
    amount = _at(RATES[cls], on) * units
    if {f1}:
        amount += _ratio(amount * _at(SURCHARGE, on), 100)
    if {f2}:
        amount -= _ratio(amount * _at(DISCOUNT, on), 100)
    amount = max(amount, _at(MINIMUM, on))
    cap = _at(CAP, on)
    if cap is not None:
        amount = min(amount, cap)
    return _ratio(amount, ROUND) * ROUND
'''


def stub_source(m):
    kind = m["kind"]
    f1, f2 = kind["f1"][0], kind["f2"][0]
    return f'''"""{kind["title"]}: see SPEC.md and the tariff documents in docs/."""

__all__ = ["fee"]


def fee(cls, qty, on, {f1}=False, {f2}=False):
    raise NotImplementedError("{kind["key"]}: see SPEC.md")
'''


def spec_md(mods):
    out = ["# Fee functions", "",
           "Every fee lives in `fees/<name>.py` as `fee(cls, qty, on, <flag>=False, <flag>=False) -> int`, an amount in cents. "
           "`cls` is the class code, `qty` the quantity in the tariff's own measure (hours, tonnes, trucks, ...), `on` the ISO date "
           "(`YYYY-MM-DD`) on which the service is performed. All the **numbers** (rates, percentages, the size of a unit, minimums, maximums, "
           "rounding) are in the tariff documents under `docs/`; this file fixes only the order of the calculation. A change applies to services performed on or after "
           "its effective date.", "",
           "## The calculation (the same for every fee)", "",
           "1. `units` = the number of *started* units in `qty` (a unit is defined in the fee's tariff section; `qty` 11 with 10-per-unit is 2 units).",
           "2. `amount` = the rate for `cls` in force on `on`, times `units`.",
           "3. If the first flag is set, add the surcharge: that percentage of `amount`, rounded half up to a whole cent (integer arithmetic).",
           "4. If the second flag is set, subtract the discount: that percentage of the (possibly surcharged) `amount`, rounded half up.",
           "5. Raise `amount` to the minimum charge in force, if it is lower.",
           "6. Lower `amount` to the maximum charge in force, if there is one.",
           "7. Round to the nearest multiple of the rounding unit stated in the tariff, halves up. That is the result.", "",
           "`ValueError` for an unknown class, `qty < 1`, or a date before 2019-01-01 (the first tariff).", "",
           "## Functions", ""]
    for m in mods:
        k = m["kind"]
        out.append(f"* `fees/{k['key']}.py`: `fee(cls, qty, on, {k['f1'][0]}=False, {k['f2'][0]}=False)` for {k['title'].lower()}; "
                   f"the first flag is the surcharge condition, the second the discount condition.")
    return "\n".join(out) + "\n"


def tariff_md(m, rng):
    k = m["kind"]
    unit = k["unit"].format(step=k["step"])
    rows = "\n".join(f"| {c} | {desc} | {m['rates'][c][0][1]} |" for c, desc in k["classes"])
    base_min = m["min"][0][1]
    plural = "s" if m["rnd"] != 1 else ""
    return "\n".join([
        f"# {k['title']}", "", rng.choice(FILLER), "",
        "## Basis of charge", "",
        f"The charge is made per {unit}. Quantities are measured in {k['qty']}; a part of a unit counts as a whole unit.", "",
        "## Rates (first tariff, in force from 2019-01-01)", "",
        "| class | applies to | rate per unit |", "|---|---|---|", rows, "",
        "## Adjustments", "",
        f"* Surcharge: **{m['sur'][0][1]}%** is added for {k['f1'][1]} (parameter `{k['f1'][0]}`).",
        f"* Discount: **{m['disc'][0][1]}%** is deducted for {k['f2'][1]} (parameter `{k['f2'][0]}`).",
        f"* Minimum charge: **{base_min}** per call.",
        "* There is no maximum charge.",
        f"* The result is rounded to the nearest **{m['rnd']}** cent{plural} (halves round up).", "",
        rng.choice(FILLER), ""])


def amendment_files(mods, rng):
    items = []
    for m in mods:
        for idx, a in enumerate(m["amendments"]):
            items.append((a["iso"], m["kind"]["title"], a["fmt"].replace("{v}", str(a["printed"])), m, idx))
    items.sort(key=lambda t: (t[0], t[1]))
    files, nums = {}, {}
    for n, (iso, title, text, m, idx) in enumerate(items, start=1):
        nums[(m["kind"]["key"], idx)] = n
    corrections = []
    for m in mods:
        if m["correction"]:
            j, wrong, right, iso = m["correction"]
            corrections.append((m, j, wrong, right, iso))
    for n, (iso, title, text, m, idx) in enumerate(items, start=1):
        files[f"docs/amendments/amendment-{n:02d}.md"] = dd(f'''
            # Amendment {n}

            Section: {title}.

            With effect from **{iso}** {text}. All other parts of the section stay as they are.

            {rng.choice(FILLER)}
        ''')
    nxt = len(items) + 1
    for m, j, wrong, right, iso in corrections:
        n = nums[(m["kind"]["key"], j)]
        files[f"docs/amendments/amendment-{nxt:02d}.md"] = dd(f'''
            # Amendment {nxt} (correction)

            Section: {m["kind"]["title"]}.

            {rng.choice(NOTES_STYLE)} Amendment {n} was printed with a wrong figure: where it says {wrong}, the figure **{right}** is the one that applies,
            from the same effective date. No other change is made.
        ''')
        nxt += 1
    return files


CHECK = '''import json
import os
import sys

sys.path.insert(0, os.getcwd())
CASES = json.loads(%(cases)r)

name = sys.argv[1]
mod = __import__("fees." + name, fromlist=["fee"])
for c in CASES[name]:
    args, kwargs, want = c["args"], c["kwargs"], c["want"]
    try:
        got = mod.fee(*args, **kwargs)
    except ValueError:
        got = "ValueError"
    if got != want:
        print("FAILED: fee%%r%%r -> %%r, want %%r" %% (tuple(args), kwargs, got, want), file=sys.stderr)
        sys.exit(1)
'''


@family("swarm-research-implement", category="swarm", lang="python", kind="feature", n=10,
        summary="k fee functions whose numbers are scattered over a tariff, dated amendments and corrections; one researcher, several implementers")
def research_implement(rng, n):
    ks = [3, 3, 4, 4, 5, 4, 5, 6, 5, 6]
    kinds = list(KINDS)
    for i in range(n):
        k = ks[i % len(ks)]
        chosen = rng.sample(kinds, k)
        mods = [make_module(rng, kd, rng.randint(2, 4)) for kd in chosen]
        extras = [make_module(rng, kd, 2) for kd in rng.sample([x for x in kinds if x not in chosen], min(2, len(kinds) - k))]
        src = {m["kind"]["key"]: module_source(m) for m in mods}
        start = {
            "README.md": "# Port tariff\n\nThe authority's fee schedule lives in `docs/` as a first tariff plus numbered amendments (and corrections). "
                         "`fees/` holds the calculators, `SPEC.md` the shape of every calculation. Quick check: `python3 try_fee.py`.\n",
            "SPEC.md": spec_md(mods),
            "fees/__init__.py": "",
            "try_fee.py": '"""Try a fee from the shell: python3 try_fee.py berth A 5 2024-05-01"""\nimport importlib\nimport sys\n\nname, cls, qty, on = sys.argv[1:5]\nprint(importlib.import_module("fees." + name).fee(cls, int(qty), on))\n',
        }
        for m in mods:
            start[f"fees/{m['kind']['key']}.py"] = stub_source(m)
            start[f"docs/tariff/{m['kind']['key']}.md"] = tariff_md(m, rng)
        for m in extras:
            start[f"docs/tariff/{m['kind']['key']}.md"] = tariff_md(m, rng)
        start.update(amendment_files(mods + extras, rng))
        index = ["# Document index", ""]
        for p in sorted(start):
            if p.startswith("docs/") and p != "docs/index.md":
                first = start[p].splitlines()[0].lstrip("# ")
                index.append(f"* `{p[5:]}`: {first}")
        start["docs/index.md"] = "\n".join(index) + "\n"
        start["docs/glossary.md"] = dd('''
            # Glossary

            * **Started unit**: any part of a unit counts as a whole one.
            * **Effective date**: the first day a change applies; services performed that day are already charged at the new figure.
            * **Correction**: an amendment that fixes a figure misprinted in an earlier amendment; the correction wins, from the earlier amendment's own effective date.
            * **Call**: one visit of a vessel or one consignment, charged as a single transaction.
        ''')
        # hidden cases
        cases = {}
        for m in mods:
            kd = m["kind"]
            f1, f2 = kd["f1"][0], kd["f2"][0]
            ns = {}
            exec(compile(src[kd["key"]], "<ref>", "exec"), ns)
            boundaries = sorted({a["iso"] for a in m["amendments"]})
            pool = []
            for iso in boundaries:
                dt = date.fromisoformat(iso)
                pool += [iso, (dt - timedelta(days=1)).isoformat(), (dt + timedelta(days=1)).isoformat()]
            pool += [d_.isoformat() for d_ in (date(2019, 1, 1), date(2018, 12, 31), date(2025, 6, 30))]
            lst = []
            for _ in range(160):
                c = rng.choice(m["classes"] + (["zz"] if rng.random() < 0.02 else []))
                q = rng.choice([0, 1, 2, 3, 4, 5, 9, 10, 11, 17, 24, 40, 63, 120, rng.randint(1, 300)])
                on = rng.choice(pool) if rng.random() < 0.7 else (date(2019, 1, 1) + timedelta(days=rng.randint(0, 2370))).isoformat()
                kw = {f1: rng.random() < 0.5, f2: rng.random() < 0.5}
                try:
                    want = ns["fee"](c, q, on, **kw)
                except ValueError:
                    want = "ValueError"
                lst.append({"args": [c, q, on], "kwargs": kw, "want": want})
            cases[kd["key"]] = lst
        hidden = {".grade/check_fees.py": CHECK % {"cases": json.dumps(cases, sort_keys=True)}}
        units = [{"name": m["kind"]["key"], "cmd": ["python3", ".grade/check_fees.py", m["kind"]["key"]], "weight": 1} for m in mods]
        hidden[".grade/score.py"] = score_script(units)
        solution = {f"fees/{m['kind']['key']}.py": src[m["kind"]["key"]] for m in mods}
        titles = oxford([m["kind"]["title"].lower() for m in mods])
        voices = [
            f"The port authority wants fee calculators for {titles}. The rules are in the tariff documents under docs/ and they are scattered: a first tariff "
            f"plus amendments, some of which correct earlier ones. SPEC.md fixes the shape of the calculation. Someone should dig out the facts and the rest implement.",
            f"Implement the {k} fee functions in fees/ (SPEC.md). The numbers live in docs/: base tariffs, dated amendments and corrections. A fee must be right for any "
            f"service date back to 2019-01-01. It is a lot of reading, so divide the work.",
            f"Port tariff project: {titles}. docs/index.md lists the tariff and amendment files; SPEC.md describes the calculation. Get every fee right, including "
            f"the dates when figures changed, and don't trust the first tariff alone.",
            f"We lost the old fee spreadsheet and only have the published tariff documents (docs/). Rebuild the calculators for {titles} as SPEC.md describes. "
            f"Checks will use many different service dates.",
        ]
        d_ = 3 if k <= 3 else 4 if k <= 5 else 5
        yield Task(
            slug=f"{i + 1:02d}-k{k}-" + mods[0]["kind"]["key"],
            prompt=voices[i % len(voices)], difficulty=d_,
            start=start, hidden=hidden, solution=solution, verify=GRADE_CMD, pass_mode="json-score",
            team=team(rng, k, ["scout", "backend", "tester"] if i % 2 else ["scout", "backend", "reviewer"]),
            context_window=32000 if k >= 5 else None,
            tags=["research", "documents", "temporal", "corrections"],
            notes={"modules": [m["kind"]["key"] for m in mods], "amendments": sum(len(m["amendments"]) for m in mods), "corrections": sum(1 for m in mods if m["correction"])},
        )
