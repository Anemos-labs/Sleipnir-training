"""Field-station notebook: daily assay entries with raw instrument readings and dilutions, plus a calibration log whose offsets apply
from the calibration date. Corrected concentration = (raw - offset in force) x dilution; every question needs the right offset."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from fx import dd, family

from . import _world as W


def build(rng, n_days: int, n_inst: int, n_plots: int):
    org = W.make_org(rng, "lab", n_people=7, n_assets=n_plots)
    inst = [f"P{i + 1}" for i in range(n_inst)]
    d0 = W.base_date(rng)
    # calibrations: initial offsets plus 1-3 recalibrations per instrument at random days (never on a day without readings is fine)
    cal = {i: [(d0 - dt.timedelta(days=30), Decimal(rng.randint(-60, 80)) / 100)] for i in inst}
    day_list = sorted(W.rand_dates(rng, n_days, d0, d0 + dt.timedelta(days=n_days * 3 + 10), distinct=True))
    span = (day_list[-1] - d0).days
    for i in inst:
        for _ in range(rng.randint(1, 3)):
            d = d0 + dt.timedelta(days=rng.randint(2, max(3, span - 2)))
            cal[i].append((d, Decimal(rng.randint(-60, 80)) / 100))
        cal[i].sort(key=lambda x: x[0])
        # one calibration date per instrument
        seen, uniq = set(), []
        for d, o in cal[i]:
            if d not in seen:
                seen.add(d)
                uniq.append((d, o))
        cal[i] = uniq
    recs = []
    sid = rng.randint(100, 300)
    for d in day_list:
        for _ in range(rng.randint(2, 5)):
            sid += rng.randint(1, 4)
            dil = rng.choice([1, 1, 2, 5, 10])
            recs.append(dict(sample=f"S-{sid:04d}", date=d, plot=rng.choice(org.assets), inst=rng.choice(inst), dil=dil, raw=Decimal(rng.randint(80, 900)) / 100))
    return org, inst, d0, cal, day_list, recs


def offset_on(cal, inst, d):
    best = None
    for cd, off in cal[inst]:
        if cd <= d:
            best = off
    return best


def corrected(cal, r) -> Decimal:
    return (r["raw"] - offset_on(cal, r["inst"], r["date"])) * r["dil"]


def render(rng, org, inst, d0, cal, day_list, recs, limit):
    files: dict[str, str] = {}
    by_day: dict[dt.date, list] = {}
    for r in recs:
        by_day.setdefault(r["date"], []).append(r)
    for d, lst in by_day.items():
        p = rng.choice(org.people)
        lines = [f"Notebook, {W.d_wdlong(d)}. Kept by {p.full}.", ""]
        for r in lst:
            dil = "undiluted" if r["dil"] == 1 else f"diluted 1:{r['dil']}"
            style = rng.randrange(3)
            if style == 0:
                lines.append(f"{r['sample']} | {r['plot']} | {r['inst']} | {dil} | raw {r['raw']} mg/L")
            elif style == 1:
                lines.append(f"Sample {r['sample']} from {r['plot']}, run on {r['inst']}, {dil}: the meter read {r['raw']} mg/L.")
            else:
                lines.append(f"- {r['inst']}: {r['sample']} ({r['plot']}), {dil}, reading = {r['raw']} mg/L")
        lines.append("")
        lines.append(W.filler_line(rng, org, d, d + dt.timedelta(days=10)))
        files[f"notebook/{W.d_iso(d)}.txt"] = "\n".join(lines) + "\n"
    lines = [f"{org.name}: photometer calibration log", "", "Every entry gives the zero offset (mg/L) to subtract from raw readings. A calibration is done before the day's first run, so it applies from that day.", ""]
    ent = []
    for i in inst:
        for k, (d, off) in enumerate(cal[i]):
            ent.append((d, i, off, k == 0))
    ent.sort()
    for d, i, off, first in ent:
        who = rng.choice(org.people).last
        lines.append(f"{W.d_iso(d)}  {i}  {'initial calibration' if first else 'recalibrated'} by {who}: zero offset {off:+.2f} mg/L")
    files["calibration/log.txt"] = "\n".join(lines) + "\n"
    files["protocol.md"] = dd(f"""
        # Nitrate assay protocol

        Every reading is corrected before use:

            corrected = (raw reading - zero offset of that instrument on the day) x dilution factor

        where the dilution factor is the second number of the dilution ("diluted 1:5" means 5; undiluted means 1). The zero offset is
        the latest entry in `calibration/log.txt` for that instrument dated on or before the day of the run. Concentrations are in mg/L.
        The regulatory limit for this study is {limit} mg/L of corrected nitrate.
    """)
    return files


def fmt(x: Decimal) -> str:
    return f"{x:.2f}"


@family("research-lab-notebook", category="research", lang="text", kind="lookup", n=12, mode="answer",
        summary="corrected assay values from raw notebook readings, dilutions and dated instrument calibrations: one sample, the maximum, a limit count, plot totals")
def gen(rng, n):
    made = 0
    while made < n:
        n_days = rng.choice([6, 9, 14, 20, 26])
        n_inst = rng.choice([2, 3])
        org, inst, d0, cal, days, recs = build(rng, n_days, n_inst, rng.choice([4, 5]))
        limit = rng.choice([10, 15, 20, 25, 30])
        files = render(rng, org, inst, d0, cal, days, recs, limit)
        cors = [(r, corrected(cal, r)) for r in recs]
        qk = rng.choice(["sample", "sample", "max", "count", "plot_total"])
        n_cal = sum(len(v) for v in cal.values())
        if qk == "sample":
            r, v = rng.choice(cors)
            ph = [f"What is the corrected nitrate concentration for sample {r['sample']} (protocol.md has the correction)? Give mg/L to two decimals.",
                  f"Please work out the corrected value for {r['sample']} in mg/L, two decimals. Remember the right calibration offset for its day and instrument."]
            prompt, contains, gold = rng.choice(ph), [fmt(v)], f"{r['sample']}: {fmt(v)} mg/L."
            diff = 3 + (n_days >= 14)
        elif qk == "max":
            top = sorted(cors, key=lambda x: -x[1])
            if len(top) < 2 or top[0][1] == top[1][1]:
                continue
            r, v = top[0]
            ph = ["Which sample has the highest corrected nitrate concentration in the whole notebook? Give the sample id.",
                  "After applying the protocol's correction to every reading, which sample id is the highest?"]
            prompt, contains, gold = rng.choice(ph), [r["sample"]], f"{r['sample']} ({fmt(v)} mg/L)."
            diff = 4 + (n_days >= 20)
        elif qk == "count":
            k = sum(1 for _, v in cors if v > limit)
            if k == 0:
                continue
            ins, c = W.numfmt(rng, k, ("Count", "Total", "Answer"))
            ph = [f"How many samples exceed the regulatory limit once corrected (strictly above it)?{ins}",
                  f"Count the samples whose corrected nitrate is above the study limit given in the protocol.{ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"{k} samples. {c}"
            diff = 4 + (n_days >= 14)
        else:
            tot = {}
            for r, v in cors:
                tot[r["plot"]] = tot.get(r["plot"], Decimal(0)) + v
            ranked = sorted(tot.items(), key=lambda kv: -kv[1])
            if len(ranked) < 2 or ranked[0][1] == ranked[1][1]:
                continue
            ph = ["Which plot has the highest total corrected nitrate (sum of the corrected values of all its samples)? Name the plot.",
                  "Add up the corrected values per plot: which plot comes out on top?"]
            prompt, contains, gold = rng.choice(ph), [ranked[0][0]], f"{ranked[0][0]} ({fmt(ranked[0][1])})."
            diff = 5 if n_days >= 14 else 4
        if any(c in prompt for c in contains):
            continue
        made += 1
        yield W.say_task(slug=f"{made:02d}-{qk.replace('_', '-')}", prompt=W.voice(rng, org, prompt), difficulty=min(5, diff), start=files, contains=contains, gold=gold,
                         tags=["lab", "calibration", "arithmetic"], notes={"days": n_days, "instruments": n_inst, "calibrations": n_cal, "question": qk})
