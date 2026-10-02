"""Table extraction from prose: river-gauge observations written in free text with mixed units (mm, cm, m), doubtful readings to discard,
forecasts and alarm levels that are not readings. Output: out.csv with one row per gauge and day (highest valid reading, cm)."""
from __future__ import annotations

import datetime as dt

from fx import dd, family

from . import _world as W

GAUGES = ["Fennick", "Marram", "Skerry", "Hollin", "Brindle", "Corrach", "Dunnock", "Quillon", "Tarnside", "Westwater"]


def fmt_level(rng, mm: int) -> str:
    style = rng.choice(["cm", "cm", "m", "mm"])
    if style == "cm":
        return f"{mm / 10:.1f} cm"
    if style == "m":
        return f"{mm / 1000:.3f} m"
    return f"{mm} mm"


def build(rng, n_days: int, n_gauges: int):
    org = W.make_org(rng, "lab", n_people=5)
    gauges = rng.sample(GAUGES, n_gauges)
    d0 = W.base_date(rng)
    days = sorted(W.rand_dates(rng, n_days, d0, d0 + dt.timedelta(days=n_days * 2 + 6), distinct=True))
    base = {g: rng.randint(250, 1500) for g in gauges}
    readings = []  # dict(day, gauge, time, mm, valid)
    for d in days:
        for g in gauges:
            if rng.random() < 0.25:
                continue
            for _ in range(rng.choice([1, 2, 2, 3])):
                mm = max(40, base[g] + rng.randint(-200, 400))
                readings.append(dict(day=d, gauge=g, time=W.hhmm(rng, 6, 20), mm=mm, valid=rng.random() > 0.15))
    return org, gauges, days, readings


def render(rng, org, gauges, days, readings):
    files: dict[str, str] = {}
    by_day: dict[dt.date, list] = {}
    for r in readings:
        by_day.setdefault(r["day"], []).append(r)
    for d, lst in by_day.items():
        p = rng.choice(org.people)
        lst = sorted(lst, key=lambda r: r["time"])
        lines = [f"Field log, {W.d_long(d)}. Observer: {p.full}.", ""]
        for r in lst:
            lv = fmt_level(rng, r["mm"])
            if r["valid"]:
                lines.append(rng.choice([f"At {r['time']} the {r['gauge']} gauge read {lv}.", f"{r['time']}: {r['gauge']} gauge {lv}.", f"Level at {r['gauge']} ({r['time']}): {lv}."]))
            else:
                lines.append(rng.choice([f"At {r['time']} the {r['gauge']} gauge showed {lv}, but the float was stuck so this reading is doubtful and must be discarded.",
                                         f"{r['time']}: {r['gauge']} gauge {lv} (instrument fault, ignore)."]))
        if rng.random() < 0.5:
            g = rng.choice(gauges)
            lines.append(rng.choice([f"Forecast: the {g} gauge could reach {rng.randint(60, 190)} cm by Friday if the rain continues.",
                                     f"For reference, the alarm level at {g} is {rng.randint(150, 260)} cm.",
                                     f"Calibration of the {g} gauge board is due next month (nominal range up to {rng.randint(200, 400)} cm)."]))
        lines.append(W.filler_line(rng, org, d, d + dt.timedelta(days=10)))
        files[f"fieldlogs/{W.d_iso(d)}.txt"] = "\n".join(lines) + "\n"
    files["README.md"] = dd("""
        # River gauge field logs

        One log per observation day. Readings are written as free text, in cm, m or mm. A reading that the log itself calls doubtful or
        marks as an instrument fault is not valid. Forecasts, alarm levels and calibration ranges are not readings.
    """)
    return files


@family("research-gauge-readings", category="research", lang="text", kind="greenfield", n=14,
        summary="extract valid gauge readings from prose logs with mixed units into out.csv (daily maximum per gauge in cm)")
def gen(rng, n):
    made = 0
    while made < n:
        n_days = rng.choice([4, 6, 8, 12, 16])
        n_g = rng.choice([2, 3])
        org, gauges, days, readings = build(rng, n_days, n_g)
        files = render(rng, org, gauges, days, readings)
        best = {}
        for r in readings:
            if not r["valid"]:
                continue
            k = (r["gauge"], r["day"])
            best[k] = max(best.get(k, 0), r["mm"])
        if len(best) < 3:
            continue
        rows = [[g, W.d_iso(d), f"{mm / 10:.1f}"] for (g, d), mm in sorted(best.items())]
        spec = W.csv_spec(["gauge", "date", "max_level_cm"], ["str", "date", "num"], rows, key=[0, 1], tol=0.06)
        ph = [f"Turn the field logs into a table: `out.csv` with the header `gauge,date,max_level_cm`, one row per gauge and day, giving the highest valid reading of that day converted to centimetres with one decimal. Sort by gauge, then date.",
              f"I need the gauge data in `out.csv` (columns gauge, date, max_level_cm). For each gauge and each day with at least one valid reading, report the day's highest valid reading in cm (one decimal, ISO dates). The README says what is not a reading.",
              f"The observers wrote everything up as prose and the hydrologists want a spreadsheet. Please produce `out.csv`: gauge,date,max_level_cm. One row for each gauge/day pair, the largest valid level (in cm, one decimal) seen that day. Rows sorted by gauge name and then by date.",
              f"Extract the river levels from `fieldlogs/` into `out.csv` with the columns `gauge`, `date` (YYYY-MM-DD) and `max_level_cm`. Take the peak valid reading per gauge per day, convert every unit to centimetres (one decimal place), and skip anything the logs mark as unreliable. Sorted by gauge, then date.",
              f"Could you build `out.csv` from the observers' field logs? Header `gauge,date,max_level_cm`; each row is one gauge on one day with its highest trustworthy reading in cm. Forecasts and alarm levels aren't readings."]
        made += 1
        yield W.file_task(slug=f"{made:02d}-{n_days}days-{n_g}gauges", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=2 + (n_days >= 8) + (n_days >= 16) + (n_g == 3), start=files,
                          spec=spec, solution={"out.csv": W.csv_text(["gauge", "date", "max_level_cm"], rows)}, scored=True, tags=["extraction", "units", "table"],
                          notes={"days": n_days, "gauges": n_g})
