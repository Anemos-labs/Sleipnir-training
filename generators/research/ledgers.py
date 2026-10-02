"""Ledger CSVs from several departments in three layouts: vendor names written many ways, three currencies with
quarterly rates, voided and credited lines. Output: per-vendor totals as out.csv (exact to the cent)."""
from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal, ROUND_HALF_UP

from fx import dd, family

from . import _world as W

SUFFIX = ["Ltd", "Co.", "Supply Co.", "Traders", "Hauliers", "Works", "Partners"]
DEPTS_SHORT = ["ops", "fin", "fac", "lab", "mkt", "hr", "it"]
STATUS_OK = ["paid", "posted", "invoice"]
STATUS_VOID = ["void", "cancelled"]
STATUS_CR = ["credit", "credit note", "refund"]
CURS = ["credits", "marks", "florins"]


def norm_name(s: str) -> str:
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    words = [w for w in s.split() if w not in ("ltd", "co", "inc", "the")]
    return " ".join(words)


def build(rng, n_vendors: int, n_depts: int, year: int):
    org = W.make_org(rng, None, n_people=6)
    ws = rng.sample(W.NAME_WORDS, n_vendors * 2)
    vendors = []
    for i in range(n_vendors):
        w1, w2 = ws[2 * i], ws[2 * i + 1]
        suf = rng.choice(SUFFIX)
        canon = f"{w1} & {w2} {suf}"
        short = f"{w1[0]}&{w2[0]} {suf.split()[0]}"
        extra = f"{w1} and {w2}" if rng.random() < 0.5 else f"{w1}-{w2}"
        vendors.append(dict(canon=canon, aliases=[short, extra]))
    # a look-alike pair: two canonical vendors sharing the first word
    if n_vendors >= 4:
        a, b = vendors[0], vendors[1]
        w1 = a["canon"].split(" & ")[0]
        w2b = b["canon"].split(" & ")[1].split()[0]
        sufb = " ".join(b["canon"].split(" & ")[1].split()[1:])
        b["canon"] = f"{w1} & {w2b} {sufb}".strip()
        b["aliases"] = [f"{w1[0]}&{w2b[0]} {sufb.split()[0] if sufb else ''}".strip(), f"{w1} and {w2b}"]
    depts = rng.sample(org.teams, n_depts)
    rates = {}
    for q in range(1, 5):
        rates[q] = {"marks": Decimal(rng.randint(110, 160)) / 100, "florins": Decimal(rng.randint(60, 95)) / 100}
    return org, vendors, depts, rates


def spell(rng, v: dict) -> str:
    form = rng.choice(["canon", "canon", "upper", "alias0", "alias1", "nopunct", "lower"])
    c = v["canon"]
    if form == "canon":
        return c
    if form == "upper":
        return c.upper()
    if form == "lower":
        return c.lower()
    if form == "nopunct":
        return c.replace(".", "").replace(",", "")
    return v["aliases"][0 if form == "alias0" else 1]


def to_credits(cents: int, cur: str, rate: Decimal) -> int:
    if cur == "credits":
        return cents
    return int((Decimal(cents) * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def render(rng, org, vendors, depts, rates, year: int):
    files: dict[str, str] = {}
    rows_all = []  # (dept, q, vendor idx, cents, cur, mode)
    for d in depts:
        layout = rng.choice(["v1", "v2", "v3"])
        for q in range(1, 5):
            n = rng.randint(5, 11)
            rows = []
            for _ in range(n):
                vi = rng.randrange(len(vendors))
                day = dt.date(year, 3 * (q - 1) + rng.randint(1, 3), rng.randint(1, 28))
                cents = rng.randint(2500, 480000)
                cur = rng.choices(CURS, [70, 18, 12])[0]
                mode = rng.choices(["ok", "void", "credit"], [80, 8, 12])[0]
                rows_all.append((d, q, vi, cents, cur, mode))
                amt = f"{cents // 100}.{cents % 100:02d}"
                name = spell(rng, vendors[vi])
                st = {"ok": rng.choice(STATUS_OK), "void": rng.choice(STATUS_VOID), "credit": rng.choice(STATUS_CR)}[mode]
                memo = rng.choice(["monthly supply", "repair", "call-out", "consumables", "annual fee", "delivery", "parts", "hire"])
                if layout == "v1":
                    rows.append([W.d_iso(day), name, memo, amt, cur, st])
                elif layout == "v2":
                    ty = {"paid": "invoice", "posted": "invoice", "invoice": "invoice", "void": "cancelled", "cancelled": "cancelled"}.get(st, st)
                    rows.append([W.d_iso(day), name, amt, cur, ty, memo])
                else:
                    rows.append([W.d_short(day), name, amt, cur, st])
            slug = W.slugify(d, 12)
            if layout == "v1":
                text = W.csv_text(["date", "vendor", "description", "amount", "currency", "status"], rows)
            elif layout == "v2":
                text = W.csv_text(["Date", "Supplier", "Amount", "Ccy", "Type", "Memo"], rows)
            else:
                text = W.csv_text(["posted", "payee", "amt", "cur", "state"], rows, delim=";")
            files[f"ledgers/{slug}-{year}-Q{q}.csv"] = text
    files["vendors.csv"] = W.csv_text(["vendor", "also_written_as"], [[v["canon"], "; ".join(v["aliases"])] for v in vendors])
    rl = [f"Exchange rates to credits (value of one unit in credits), by quarter of {year}", ""]
    for q in range(1, 5):
        rl.append(f"{year}-Q{q}: 1 mark = {rates[q]['marks']} credits; 1 florin = {rates[q]['florins']} credits")
    files["rates.txt"] = "\n".join(rl) + "\n"
    files["README.md"] = dd(f"""
        # Spend ledgers {year}

        `ledgers/` has one CSV per department and quarter (the finance system was changed once, so the three layouts differ in
        column names, order and delimiter). `vendors.csv` lists each vendor's canonical name and other ways its name appears.
        `rates.txt` gives the conversion rates to credits for each quarter.

        Matching vendor names: two names are the same vendor if they match after lowercasing, removing punctuation and the words
        "ltd", "co", "inc" and "the", and treating "&" as "and"; names in the `also_written_as` column are also that vendor.

        Status (or type/state) of a line: `paid`, `posted`, `invoice` count as spend; `void`, `cancelled` are ignored; `credit`,
        `credit note`, `refund` reduce spend by the line amount.

        Converting: a line in marks or florins is converted with the rate of the quarter its date falls in, rounded to the nearest
        cent (half up) line by line, before adding up. Amounts are in the stated currency; credits need no conversion.
    """)
    return files, rows_all


def totals(vendors, rows_all, depts_filter=None, quarters=None, rates=None):
    tot = {i: 0 for i in range(len(vendors))}
    for d, q, vi, cents, cur, mode in rows_all:
        if depts_filter and d not in depts_filter:
            continue
        if quarters and q not in quarters:
            continue
        if mode == "void":
            continue
        c = to_credits(cents, cur, rates[q].get(cur, Decimal(1)) if cur != "credits" else Decimal(1))
        tot[vi] += c if mode == "ok" else -c
    return tot


@family("research-vendor-ledger", category="research", lang="text", kind="greenfield", n=14,
        summary="vendor totals from department ledgers in three layouts, with aliases, voids, credits and currency conversion (out.csv)")
def gen(rng, n):
    made = 0
    while made < n:
        nv = rng.choice([3, 4, 5, 6])
        nd = rng.choice([1, 2, 3, 4])
        year = rng.randint(2030, 2035)
        org, vendors, depts, rates = build(rng, nv, nd, year)
        names = [norm_name(x) for v in vendors for x in [v['canon']] + v['aliases']]
        if len(set(names)) != len(names):
            continue
        files, rows_all = render(rng, org, vendors, depts, rates, year)
        qk = made % 4
        if qk == 0:
            tot = totals(vendors, rows_all, rates=rates)
            scope = f"the whole of {year} (all departments)"
            dq = 3 + (nd >= 3) + (nv >= 5)
        elif qk == 1:
            d = rng.choice(depts)
            tot = totals(vendors, rows_all, depts_filter={d}, rates=rates)
            scope = f"the {d} department for {year}"
            dq = 2 + (nd >= 3) + (nv >= 5)
        elif qk == 2:
            q = rng.randint(1, 4)
            tot = totals(vendors, rows_all, quarters={q}, rates=rates)
            scope = f"{year}-Q{q}, all departments"
            dq = 2 + (nd >= 3) + (nv >= 5)
        else:
            qs = rng.choice([{1, 2}, {3, 4}, {2, 3}])
            tot = totals(vendors, rows_all, quarters=qs, rates=rates)
            scope = f"quarters {', '.join('Q' + str(x) for x in sorted(qs))} of {year}, all departments"
            dq = 3 + (nd >= 3) + (nv >= 5)
        rows = [[vendors[i]["canon"], f"{c // 100}.{c % 100:02d}" if c >= 0 else f"-{abs(c) // 100}.{abs(c) % 100:02d}"] for i, c in tot.items() if c != 0]
        order = sorted(rows, key=lambda r: -float(r[1]))
        vals = [float(r[1]) for r in order]
        if len(set(vals)) != len(vals) or len(order) < 3:
            continue
        spec = W.csv_spec(["vendor", "total_credits"], ["str", "num"], order, key=[0], tol=0.004, ordered=True)
        ph = [f"From the ledgers, work out what we spent with each vendor over {scope}. `out.csv` with header `vendor,total_credits`, the canonical vendor name from vendors.csv, the total in credits to two decimals, biggest spender first. Skip vendors with a zero total.",
              f"Finance wants a vendor league table for {scope}: `out.csv`, columns vendor,total_credits (canonical names, credits with two decimals, sorted from highest to lowest). The README has the rules for statuses, aliases and currencies.",
              f"Please total up the spend per vendor for {scope} and save it as `out.csv` (`vendor,total_credits`), highest first. Convert foreign currencies and net off credit notes as the README says."]
        made += 1
        yield W.file_task(slug=f"{made:02d}-{['year', 'dept', 'quarter', 'half'][qk]}", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=dq, start=files, spec=spec,
                          solution={"out.csv": W.csv_text(["vendor", "total_credits"], order)}, scored=True, tags=["ledger", "table", "aggregation"],
                          notes={"vendors": nv, "departments": nd, "scope": scope})
