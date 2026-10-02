"""Python ETL tasks on time series for an invented weather-station co-operative (resampling, counters, fills, rolling statistics, as-of joins, ISO weeks, peaks, DST, intervals)."""
import datetime as dt
import json

from fx import dd, family
from generators.data import _etlkit as E

STATIONS = ["ridge", "valley", "harbour", "forest", "plateau"]


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------------------------------------------- 1. hourly resample

def make_resample(rng, big):
    n = rng.randint(30, 60) if big else 10
    t = dt.datetime(2034, 2, 3, rng.randint(0, 5), rng.randint(0, 59), 0)
    rows = []
    for _ in range(n):
        t += dt.timedelta(minutes=rng.choice([5, 10, 10, 25, 40, 70, 130, 200]), seconds=rng.randint(0, 59))
        rows.append((iso(t), f"{rng.randint(-150, 280) / 10:.1f}"))
    rng.shuffle(rows)
    return {"readings.csv": "ts,celsius\n" + "\n".join(f"{a},{b}" for a, b in rows) + "\n"}


REF_RESAMPLE = dd('''
    import csv, datetime as dt, os, sys
    from decimal import Decimal, ROUND_HALF_UP

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    rows = sorted(((r["ts"], Decimal(r["celsius"])) for r in csv.DictReader(open(os.path.join(indir, "readings.csv"), newline="", encoding="utf-8"))), key=lambda x: x[0])
    by = {}
    for ts, v in rows:
        by.setdefault(ts[:13], []).append(v)
    first = dt.datetime.strptime(rows[0][0][:13], "%Y-%m-%dT%H")
    last = dt.datetime.strptime(rows[-1][0][:13], "%Y-%m-%dT%H")
    with open(os.path.join(outdir, "hourly.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["hour", "count", "mean", "last"])
        h = first
        while h <= last:
            key = h.strftime("%Y-%m-%dT%H")
            vs = by.get(key, [])
            if vs:
                w.writerow([key + ":00:00Z", len(vs), f"{(sum(vs) / len(vs)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}", f"{vs[-1]:.1f}"])
            else:
                w.writerow([key + ":00:00Z", 0, "", ""])
            h += dt.timedelta(hours=1)
''')

DOC_RESAMPLE = dd('''
    `readings.csv` (`ts,celsius`) holds temperature readings with UTC timestamps `YYYY-MM-DDTHH:MM:SSZ` in no particular order (every timestamp is unique). Resample them to hours.

    `python3 etl.py IN_DIR OUT_DIR` writes `hourly.csv` with the header `hour,count,mean,last`: one row for **every** clock hour from the hour of the earliest reading to the hour of the latest one (inclusive), in time order.
    `hour` is the start of the hour as `YYYY-MM-DDTHH:00:00Z`; `count` the number of readings in it; `mean` the mean of the readings with exactly two decimals (exact decimal arithmetic, half up);
    `last` the value of the chronologically last reading in that hour with one decimal. Hours without readings have count 0 and empty `mean` and `last`.
''')


# ---------------------------------------------------------------------------------------------------------------- 2. counters

def make_counters(rng, big):
    rows = []
    for dev in rng.sample(["pump-1", "pump-2", "fan-3", "heater-4"], 3 if big else 2):
        v = rng.randint(0, 500)
        t = dt.datetime(2034, 3, 1, 0, 0, 0)
        for _ in range(rng.randint(8, 16) if big else 6):
            t += dt.timedelta(minutes=rng.choice([10, 15, 15, 60]))
            v = v + rng.randint(0, 90) if rng.random() > 0.15 else rng.randint(0, 40)
            rows.append((dev, iso(t), v))
    rng.shuffle(rows)
    return {"counters.csv": "device,ts,total\n" + "\n".join(f"{a},{b},{c}" for a, b, c in rows) + "\n"}


REF_COUNTERS = dd('''
    import csv, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    by = {}
    for r in csv.DictReader(open(os.path.join(indir, "counters.csv"), newline="", encoding="utf-8")):
        by.setdefault(r["device"], []).append((r["ts"], int(r["total"])))
    deltas, summary = [], []
    for dev in sorted(by):
        rows = sorted(by[dev])
        total = resets = 0
        for (t0, v0), (t1, v1) in zip(rows, rows[1:]):
            d = v1 - v0 if v1 >= v0 else v1
            if v1 < v0:
                resets += 1
            total += d
            deltas.append([dev, t1, d])
        summary.append([dev, len(rows), resets, total])
    with open(os.path.join(outdir, "deltas.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["device", "ts", "delta"])
        w.writerows(deltas)
    with open(os.path.join(outdir, "summary.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["device", "readings", "resets", "total"])
        w.writerows(summary)
''')

DOC_COUNTERS = dd('''
    `counters.csv` (`device,ts,total`) holds readings of cumulative counters (energy, volume ...) in no particular order. For each device sort its readings by `ts` (UTC text, sorts correctly as text).

    The *delta* of a reading is the increase since the previous reading of the same device. If the counter went **down** the device was restarted and counts from zero again: the delta is then the new `total` itself
    (and that reading counts as a *reset*). The first reading of a device has no delta.

    `python3 etl.py IN_DIR OUT_DIR` writes `deltas.csv` (`device,ts,delta`: one row per reading except the first of each device, ordered by device name and then time) and `summary.csv`
    (`device,readings,resets,total`: the number of readings, the number of resets, and the sum of the deltas; one row per device, ordered by device name).
''')


# ---------------------------------------------------------------------------------------------------------------- 3. fill gaps

def make_fill(rng, big):
    rows = []
    for st in rng.sample(STATIONS, 3 if big else 2):
        d = dt.date(2034, 4, rng.randint(1, 5))
        for _ in range(rng.randint(8, 14) if big else 6):
            d += dt.timedelta(days=rng.choice([1, 1, 1, 2, 3, 5]))
            rows.append((st, d.isoformat(), rng.randint(0, 40)))
    rng.shuffle(rows)
    return {"daily.csv": "station,day,mm\n" + "\n".join(f"{a},{b},{c}" for a, b, c in rows) + "\n"}


REF_FILL = dd('''
    import csv, datetime as dt, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    by = {}
    for r in csv.DictReader(open(os.path.join(indir, "daily.csv"), newline="", encoding="utf-8")):
        by.setdefault(r["station"], {})[r["day"]] = r["mm"]
    with open(os.path.join(outdir, "filled.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["station", "day", "mm", "filled"])
        for st in sorted(by):
            days = sorted(by[st])
            d, end = dt.date.fromisoformat(days[0]), dt.date.fromisoformat(days[-1])
            last = None
            while d <= end:
                k = d.isoformat()
                if k in by[st]:
                    last = by[st][k]
                    w.writerow([st, k, last, 0])
                else:
                    w.writerow([st, k, last, 1])
                d += dt.timedelta(days=1)
''')

DOC_FILL = dd('''
    `daily.csv` (`station,day,mm`) has daily rainfall per station, but some days are missing and the rows are in no particular order (each station/day appears at most once).

    `python3 etl.py IN_DIR OUT_DIR` writes `filled.csv` with the header `station,day,mm,filled`: for every station (sorted by name) one row for **each calendar day** from its first to its last recorded day, in date order.
    A recorded day keeps its `mm` and has `filled` 0; a missing day carries the `mm` of the most recent earlier recorded day (forward fill) and has `filled` 1. (The first day of a station is always recorded.)
''')


# ---------------------------------------------------------------------------------------------------------------- 4. rolling median

def make_rolling(rng, big):
    rows = []
    for st in rng.sample(STATIONS, 2 if big else 1):
        for i in range(rng.randint(10, 18) if big else 8):
            rows.append((st, i + 1, rng.choice([rng.randint(10, 60), rng.randint(10, 60), rng.randint(80, 200)])))
    return {"series.csv": "station,seq,value\n" + "\n".join(f"{a},{b},{c}" for a, b, c in rows) + "\n"}


REF_ROLLING = dd('''
    import csv, os, statistics, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    by = {}
    for r in csv.DictReader(open(os.path.join(indir, "series.csv"), newline="", encoding="utf-8")):
        by.setdefault(r["station"], []).append((int(r["seq"]), int(r["value"])))
    with open(os.path.join(outdir, "smooth.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["station", "seq", "value", "median5"])
        for st in sorted(by):
            rows = sorted(by[st])
            vals = [v for _, v in rows]
            for i, (seq, v) in enumerate(rows):
                win = vals[max(0, i - 4): i + 1]
                m = statistics.median(win)
                w.writerow([st, seq, v, f"{m:.1f}"])
''')

DOC_ROLLING = dd('''
    `series.csv` (`station,seq,value`) has integer measurements numbered by `seq` per station (already unique; sort by `seq` to be safe).

    `python3 etl.py IN_DIR OUT_DIR` writes `smooth.csv` with the header `station,seq,value,median5`: one row per input row, ordered by station name and `seq`; `median5` is the median of the current value and up to four values before it
    (the *trailing* window of at most 5 values; at the start of a series the window is shorter). The median of an even number of values is the mean of the two middle ones. Write `median5` with exactly one decimal (`40.0`, `37.5`).
''')


# ---------------------------------------------------------------------------------------------------------------- 5. exact outliers

def make_outliers(rng, big):
    rows = []
    for st in rng.sample(STATIONS, 2 if big else 1):
        base = rng.randint(10, 20)
        for i in range(rng.randint(14, 24) if big else 10):
            v = base + rng.randint(-3, 3)
            if rng.random() < 0.1:
                v += rng.choice([-25, 30, 45])
            rows.append((st, f"2034-05-{i % 28 + 1:02d}T{i // 28:02d}:00:00Z", v))
    v0, k = rng.randint(5, 20), rng.choice([6, 8, 10, -7])
    for i, v in enumerate([v0, v0, v0, v0 + k, v0]):  # four equal values and one apart: the odd one is exactly two standard deviations away
        rows.append(("edge", f"2034-05-{i + 1:02d}T05:00:00Z", v))
    rng.shuffle(rows)
    return {"values.csv": "station,ts,value\n" + "\n".join(f"{a},{b},{c}" for a, b, c in rows) + "\n"}


REF_OUTLIERS = dd('''
    import csv, os, sys
    from decimal import Decimal, ROUND_HALF_UP
    from fractions import Fraction

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    by = {}
    for r in csv.DictReader(open(os.path.join(indir, "values.csv"), newline="", encoding="utf-8")):
        by.setdefault(r["station"], []).append((r["ts"], int(r["value"])))
    out, stats = [], []
    for st in sorted(by):
        rows = sorted(by[st])
        n = len(rows)
        mean = Fraction(sum(v for _, v in rows), n)
        var = sum((v - mean) ** 2 for _, v in rows) / n
        bad = [(ts, v) for ts, v in rows if (v - mean) ** 2 > 4 * var]
        out += [[st, ts, v] for ts, v in bad]
        m = Decimal(mean.numerator) / Decimal(mean.denominator)
        stats.append([st, n, f"{m.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}", len(bad)])
    with open(os.path.join(outdir, "outliers.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["station", "ts", "value"])
        w.writerows(out)
    with open(os.path.join(outdir, "stats.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["station", "n", "mean", "outliers"])
        w.writerows(stats)
''')

DOC_OUTLIERS = dd('''
    `values.csv` (`station,ts,value`) holds integer measurements. For each station compute the **population** mean and variance over all its values (divide by n). A value is an *outlier* when it is more than two
    standard deviations from the mean, i.e. when `(value - mean)^2 > 4 x variance` (compare the squares: do it exactly, with fractions or integers, so that nothing depends on floating point rounding).

    `python3 etl.py IN_DIR OUT_DIR` writes `outliers.csv` (`station,ts,value`: the outliers, ordered by station and then `ts`) and `stats.csv` (`station,n,mean,outliers`: one row per station in name order; `mean` with two decimals,
    rounded half up from the exact value). Both files always have their header.
''')


# ---------------------------------------------------------------------------------------------------------------- 6. as-of join

def make_asof(rng, big):
    syms = rng.sample(["PIKE", "WREN", "LARK", "TERN"], 2 if big else 2)
    quotes, trades = [], []
    t = 1_800_000_000
    for _ in range(rng.randint(30, 50) if big else 10):
        t += rng.choice([1, 2, 3, 5])
        if rng.random() < 0.6:
            quotes.append((t, rng.choice(syms), rng.randint(100, 140) / 10))
        else:
            trades.append((t, rng.choice(syms), rng.randint(1, 50)))
    if big:
        trades.append((quotes[3][0], quotes[3][1], 7))  # a trade at exactly the time of a quote
    return {"quotes.csv": "ts,symbol,price\n" + "\n".join(f"{a},{b},{c}" for a, b, c in quotes) + "\n", "trades.csv": "ts,symbol,qty\n" + "\n".join(f"{a},{b},{c}" for a, b, c in trades) + "\n"}


REF_ASOF = dd('''
    import bisect, csv, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    q = {}
    for r in csv.DictReader(open(os.path.join(indir, "quotes.csv"), newline="", encoding="utf-8")):
        q.setdefault(r["symbol"], []).append((int(r["ts"]), r["price"]))
    for k in q:
        q[k].sort(key=lambda x: x[0])
    rows = []
    for r in csv.DictReader(open(os.path.join(indir, "trades.csv"), newline="", encoding="utf-8")):
        ts = int(r["ts"])
        qs = q.get(r["symbol"], [])
        i = bisect.bisect_right([x[0] for x in qs], ts) - 1
        if i < 0:
            rows.append([ts, r["symbol"], r["qty"], "", "", "none"])
        else:
            age = ts - qs[i][0]
            rows.append([ts, r["symbol"], r["qty"], qs[i][1], age, "stale" if age > 5 else "ok"])
    rows.sort(key=lambda x: (x[0], x[1]))
    with open(os.path.join(outdir, "joined.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["ts", "symbol", "qty", "quote", "age_s", "state"])
        w.writerows(rows)
''')

DOC_ASOF = dd('''
    `quotes.csv` (`ts,symbol,price`) and `trades.csv` (`ts,symbol,qty`) use Unix seconds. Attach to every trade the **latest quote of the same symbol at or before the trade's time** (a quote with the same timestamp counts); prices are copied as text.

    `python3 etl.py IN_DIR OUT_DIR` writes `joined.csv` with the header `ts,symbol,qty,quote,age_s,state`, one row per trade ordered by `ts`, then symbol (trades with equal ts and symbol keep their input order).
    `quote` is the price and `age_s` the trade time minus the quote time; `state` is `ok` when the age is at most 5 seconds, `stale` when it is more, and `none` when there is no earlier quote (then `quote` and `age_s` are empty).
''')


# ---------------------------------------------------------------------------------------------------------------- 7. iso weeks

def make_weeks(rng, big):
    rows = []
    start = dt.date(2035, 12, 14) if big else dt.date(2035, 12, 25)
    d = start
    for _ in range(rng.randint(24, 40) if big else 14):
        d += dt.timedelta(days=rng.choice([1, 1, 2, 3]))
        rows.append((d.isoformat(), rng.randint(0, 25)))
    rng.shuffle(rows)
    return {"rain.csv": "day,mm\n" + "\n".join(f"{a},{b}" for a, b in rows) + "\n"}


REF_WEEKS = dd('''
    import csv, datetime as dt, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    weeks = {}
    for r in csv.DictReader(open(os.path.join(indir, "rain.csv"), newline="", encoding="utf-8")):
        y, w, _ = dt.date.fromisoformat(r["day"]).isocalendar()
        k = f"{y}-W{w:02d}"
        a = weeks.setdefault(k, [0, 0, r["day"]])
        a[0] += int(r["mm"])
        a[1] += 1
        a[2] = min(a[2], r["day"])
    with open(os.path.join(outdir, "weekly.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["week", "monday", "days", "mm"])
        for k in sorted(weeks):
            y, wk = int(k[:4]), int(k[6:])
            monday = dt.date.fromisocalendar(y, wk, 1)
            w.writerow([k, monday.isoformat(), weeks[k][1], weeks[k][0]])
''')

DOC_WEEKS = dd('''
    `rain.csv` (`day,mm`) has one row per day with data (days may be missing; each day appears once). Total the rainfall by **ISO 8601 week** (weeks start on Monday; the week-year can differ from the calendar year around New Year:
    2035-12-31, a Monday, already belongs to week `2036-W01`, and 2027-01-01 to `2026-W53`).

    `python3 etl.py IN_DIR OUT_DIR` writes `weekly.csv` with the header `week,monday,days,mm`: one row for every ISO week that has at least one row, in chronological order; `week` like `2035-W01`, `monday` the ISO date of that
    week's Monday, `days` the number of rows in the week and `mm` their sum.
''')


# ---------------------------------------------------------------------------------------------------------------- 8. peaks

def make_peaks(rng, big):
    rows = []
    for st in rng.sample(STATIONS, 2 if big else 1):
        v = rng.randint(20, 40)
        for i in range(rng.randint(24, 40) if big else 16):
            v = max(0, v + rng.choice([-9, -4, -1, 0, 0, 3, 7, 12]))
            rows.append((st, i, v))
    return {"load.csv": "station,minute,watts\n" + "\n".join(f"{a},{b},{c}" for a, b, c in rows) + "\n", "config.json": json.dumps({"min_height": rng.choice([30, 40, 50])})}


REF_PEAKS = dd('''
    import csv, json, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    thr = json.load(open(os.path.join(indir, "config.json")))["min_height"]
    by = {}
    for r in csv.DictReader(open(os.path.join(indir, "load.csv"), newline="", encoding="utf-8")):
        by.setdefault(r["station"], []).append((int(r["minute"]), int(r["watts"])))
    out = []
    for st in sorted(by):
        rows = sorted(by[st])
        i = 0
        while i < len(rows):
            j = i
            while j + 1 < len(rows) and rows[j + 1][1] == rows[i][1]:
                j += 1
            left = rows[i - 1][1] if i > 0 else None
            right = rows[j + 1][1] if j + 1 < len(rows) else None
            h = rows[i][1]
            if left is not None and right is not None and h > left and h > right and h >= thr:
                out.append([st, rows[i][0], h, j - i + 1])
            i = j + 1
    with open(os.path.join(outdir, "peaks.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["station", "minute", "watts", "width"])
        w.writerows(out)
''')

DOC_PEAKS = dd('''
    `load.csv` (`station,minute,watts`) is a power-load series per station (minutes are unique per station; sort by `minute`); `config.json` has `{"min_height": N}`.

    A **peak** is a run of one or more consecutive samples with the same value (a plateau; a single sample is a run of length 1) that is **strictly higher** than the sample just before the run **and** the sample just after it.
    A run at the very start or the very end of a series has only one neighbour and is never a peak. A peak must also have `watts >= min_height`.

    `python3 etl.py IN_DIR OUT_DIR` writes `peaks.csv` with the header `station,minute,watts,width`: for each peak the station, the minute of the **first** sample of the run, the value and the number of samples in the run;
    ordered by station name and then minute.
''')


# ---------------------------------------------------------------------------------------------------------------- 9. DST

def make_dst(rng, big):
    rows = []
    cands = ["2033-03-27 01:30", "2033-03-27 02:00", "2033-03-27 02:30", "2033-03-27 03:00", "2033-03-27 03:30", "2033-10-30 01:59", "2033-10-30 02:00", "2033-10-30 02:30", "2033-10-30 02:59", "2033-10-30 03:00", "2033-10-30 03:01",
             "2033-01-15 12:00", "2033-07-01 00:00", "2033-12-31 23:59"]
    for i in range(rng.randint(14, 22) if big else 8):
        rows.append((f"dev{rng.randint(1, 4)}", rng.choice(cands)))
    return {"events.csv": "device,local\n" + "\n".join(f"{a},{b}" for a, b in rows) + "\n"}


REF_DST = dd('''
    import csv, datetime as dt, os, sys
    from zoneinfo import ZoneInfo

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    tz, utc = ZoneInfo("Europe/Oslo"), dt.timezone.utc
    good, bad = [], []
    for i, r in enumerate(csv.DictReader(open(os.path.join(indir, "events.csv"), newline="", encoding="utf-8")), start=2):
        naive = dt.datetime.strptime(r["local"], "%Y-%m-%d %H:%M")
        a = naive.replace(tzinfo=tz, fold=0)
        b = naive.replace(tzinfo=tz, fold=1)
        ua, ub = a.astimezone(utc), b.astimezone(utc)
        back = ua.astimezone(tz).replace(tzinfo=None)
        if back != naive:
            bad.append([i, r["local"]])
            continue
        amb = ua != ub
        good.append([r["device"], ua.strftime("%Y-%m-%dT%H:%M:%SZ"), 1 if amb else 0, r["local"]])
    good.sort(key=lambda x: (x[1], x[0]))
    with open(os.path.join(outdir, "utc.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["device", "utc", "ambiguous", "local"])
        w.writerows(good)
    with open(os.path.join(outdir, "rejects.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["line", "local"])
        w.writerows(bad)
''')

DOC_DST = dd('''
    `events.csv` (`device,local`) holds timestamps as shown on the wall clock of Oslo (`Europe/Oslo`, CET/CEST): `YYYY-MM-DD HH:MM`. Convert them to UTC. Python's `zoneinfo` knows the zone.

    Around the clock changes some wall-clock times are special: a time that **does not exist** (the hour skipped when the clocks go forward) is a *reject*; a time that **exists twice** (the hour repeated when the clocks go back)
    is *ambiguous* and is converted as its **first** occurrence (the summer-time one).

    `python3 etl.py IN_DIR OUT_DIR` writes `utc.csv` with the header `device,utc,ambiguous,local`: the good rows with `utc` as `YYYY-MM-DDTHH:MM:SSZ`, `ambiguous` 1 or 0 and the original `local` text, ordered by `utc` and then device
    (equal pairs keep their input order); and `rejects.csv` (`line,local`: the line number, header = line 1, and the text) in input order.
''')


# ---------------------------------------------------------------------------------------------------------------- 10. intervals

def make_intervals(rng, big):
    rows = []
    for room in rng.sample(["lab", "hall", "attic", "barn"], 3 if big else 2):
        for _ in range(rng.randint(5, 9) if big else 4):
            s = rng.randint(8 * 60, 17 * 60)
            rows.append((room, s, s + rng.choice([15, 30, 45, 60, 90, 150])))
        t = rng.choice(range(8 * 60, 15 * 60, 15))  # two bookings that touch: the second starts when the first ends
        rows += [(room, t, t + 30), (room, t + 30, t + 75)]
    rng.shuffle(rows)
    hm = lambda m: f"{m // 60:02d}:{m % 60:02d}"
    return {"bookings.csv": "room,start,end\n" + "\n".join(f"{a},{hm(b)},{hm(c)}" for a, b, c in rows) + "\n"}


REF_INTERVALS = dd('''
    import csv, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    mins = lambda s: int(s[:2]) * 60 + int(s[3:])
    hm = lambda m: f"{m // 60:02d}:{m % 60:02d}"
    by = {}
    for r in csv.DictReader(open(os.path.join(indir, "bookings.csv"), newline="", encoding="utf-8")):
        by.setdefault(r["room"], []).append((mins(r["start"]), mins(r["end"])))
    merged_rows, sums = [], []
    for room in sorted(by):
        merged = []
        for s, e in sorted(by[room]):
            if merged and s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        busy = sum(e - s for s, e in merged)
        day_s, day_e = 8 * 60, 18 * 60
        free = (day_e - day_s) - sum(max(0, min(e, day_e) - max(s, day_s)) for s, e in merged)
        merged_rows += [[room, hm(s), hm(e)] for s, e in merged]
        sums.append([room, len(merged), busy, free])
    with open(os.path.join(outdir, "merged.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["room", "start", "end"])
        w.writerows(merged_rows)
    with open(os.path.join(outdir, "summary.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["room", "blocks", "busy_min", "free_min"])
        w.writerows(sums)
''')

DOC_INTERVALS = dd('''
    `bookings.csv` (`room,start,end`) lists bookings on one day as `HH:MM` times (start before end; no booking crosses midnight). For every room merge the bookings into *busy blocks*: bookings that overlap **or touch**
    (one ends exactly when the next starts) form one block.

    `python3 etl.py IN_DIR OUT_DIR` writes `merged.csv` (`room,start,end`: the blocks, ordered by room name and start time) and `summary.csv` (`room,blocks,busy_min,free_min`: one row per room in name order;
    `busy_min` is the total length of its blocks in minutes; `free_min` is the part of the working day 08:00 to 18:00 that is not covered by any block, in minutes; time outside the working day is not counted at all).
''')


def spec(slug, d, prompt, doc, make, ref, outputs, **kw):
    return E.EtlSpec(slug=slug, d=d, prompt=prompt, doc=doc, make=make, ref=ref, outputs=outputs, **kw)


SPECS = [
    spec("hourly-resample", 3, "Write `etl.py` that resamples the temperature readings in `readings.csv` to hourly rows, including the hours without data. Read README.md.", DOC_RESAMPLE, make_resample, REF_RESAMPLE, {"hourly.csv": "csv"},
         wrong=(REF_RESAMPLE.replace("while h <= last:", "while h < last:"),)),
    spec("counter-deltas", 3, "Write `etl.py` that turns the cumulative counter readings in `counters.csv` into per-reading deltas, handling counter resets. Read README.md.", DOC_COUNTERS, make_counters, REF_COUNTERS, {"deltas.csv": "csv", "summary.csv": "csv"},
         wrong=(REF_COUNTERS.replace("d = v1 - v0 if v1 >= v0 else v1", "d = max(0, v1 - v0)"),)),
    spec("forward-fill-days", 2, "Write `etl.py` that fills the missing days of the daily rainfall series in `daily.csv` by carrying the last value forward. Read README.md.", DOC_FILL, make_fill, REF_FILL, {"filled.csv": "csv"},
         wrong=(REF_FILL.replace("w.writerow([st, k, last, 1])", "w.writerow([st, k, 0, 1])"),)),
    spec("rolling-median", 4, "Write `etl.py` that adds a trailing 5-point rolling median to the series in `series.csv`. Read README.md.", DOC_ROLLING, make_rolling, REF_ROLLING, {"smooth.csv": "csv"},
         wrong=(REF_ROLLING.replace("vals[max(0, i - 4): i + 1]", "vals[max(0, i - 2): i + 3]"),)),
    spec("exact-outliers", 3, "Write `etl.py` that flags the values more than two standard deviations from their station's mean, using exact arithmetic. Read README.md.", DOC_OUTLIERS, make_outliers, REF_OUTLIERS, {"outliers.csv": "csv", "stats.csv": "csv"},
         wrong=(REF_OUTLIERS.replace("> 4 * var", ">= 4 * var"),)),
    spec("as-of-join", 4, "Write `etl.py` that attaches to each trade in `trades.csv` the latest earlier quote from `quotes.csv`. Read README.md.", DOC_ASOF, make_asof, REF_ASOF, {"joined.csv": "csv"},
         wrong=(REF_ASOF.replace("bisect.bisect_right", "bisect.bisect_left"),)),
    spec("iso-week-totals", 3, "Write `etl.py` that totals the daily rainfall in `rain.csv` by ISO week. Read README.md.", DOC_WEEKS, make_weeks, REF_WEEKS, {"weekly.csv": "csv"},
         wrong=(REF_WEEKS.replace("y, w, _ = dt.date.fromisoformat(r[\"day\"]).isocalendar()", "d0 = dt.date.fromisoformat(r[\"day\"]); y, w = d0.year, int(d0.strftime(\"%W\"))"),)),
    spec("find-peaks", 4, "Write `etl.py` that finds the peaks (including flat-topped ones) above the configured height in `load.csv`. Read README.md.", DOC_PEAKS, make_peaks, REF_PEAKS, {"peaks.csv": "csv"},
         wrong=(REF_PEAKS.replace("while j + 1 < len(rows) and rows[j + 1][1] == rows[i][1]:", "while False:"),)),
    spec("oslo-to-utc", 5, "Write `etl.py` that converts the Oslo wall-clock timestamps in `events.csv` to UTC, handling the nonexistent and repeated hours around the clock changes. Read README.md.", DOC_DST, make_dst, REF_DST, {"utc.csv": "csv", "rejects.csv": "csv"},
         wrong=(REF_DST.replace("a = naive.replace(tzinfo=tz, fold=0)", "a = naive.replace(tzinfo=tz, fold=1)"),)),
    spec("merge-bookings", 3, "Write `etl.py` that merges the overlapping or touching room bookings in `bookings.csv` into busy blocks and reports the free time of the working day. Read README.md.", DOC_INTERVALS, make_intervals, REF_INTERVALS, {"merged.csv": "csv", "summary.csv": "csv"},
         wrong=(REF_INTERVALS.replace("if merged and s <= merged[-1][1]:", "if merged and s < merged[-1][1]:"),)),
]


@family("data-etl-timeseries", category="data", lang="python", kind="feature", n=len(SPECS),
        summary="python ETL on time series: hourly resampling with gaps, counter resets, forward fill, rolling medians, exact outlier tests, as-of joins, ISO weeks, plateau peaks, DST conversion, interval merging")
def etl_timeseries(rng, n):
    return E.etl_tasks("etl-timeseries", SPECS, rng, n, "Weather-station time series")
