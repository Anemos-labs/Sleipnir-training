"""Python ETL tasks: cleaning messy instrument exports from an invented tide-pool monitoring lab (dates, units, encodings)."""
from fractions import Fraction

from fx import dd, family
from generators.data import _etlkit as E

STATIONS = ["pool-a1", "pool-a2", "pool-b7", "pool-c3", "rock-n9", "rock-s2", "cove-01", "cove-14"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def tie(x: Fraction, places: int) -> bool:
    y = x * 10 ** places
    return (y - (y.numerator // y.denominator)) == Fraction(1, 2) or (-y - ((-y).numerator // (-y).denominator)) == Fraction(1, 2)


# ---------------------------------------------------------------------------------------------------------------- 1. dates

def make_dates(rng, big):
    n = rng.randint(40, 70) if big else 10
    rows = []
    for i in range(n):
        y, m, d = 2031, rng.randint(1, 12), rng.randint(1, 28)
        kind = rng.choice(["iso", "slash", "name", "compact", "iso", "slash"])
        txt = {"iso": f"{y}-{m:02d}-{d:02d}", "slash": f"{d:02d}/{m:02d}/{y}", "name": f"{d} {MONTHS[m - 1]} {y}", "compact": f"{y}{m:02d}{d:02d}"}[kind]
        r = rng.random()
        if r < 0.07:
            txt = rng.choice(["31/02/2031", "2031-02-30", "2031-13-01", "n/a", "", "29/02/2031", "00/05/2031", "31 Apr 2031", "20311301"])
        rows.append(f"{rng.choice(STATIONS)},{txt},{rng.randint(10, 380)}")
    if big:
        rows.append(f"pool-a1,03/04/2031,120")  # ambiguous-looking: day first
        rows.append(f"pool-a1,03/04/2031,121")
    rng.shuffle(rows)
    return {"readings.csv": "station,taken,level_cm\n" + "\n".join(rows) + "\n"}


REF_DATES = dd('''
    import csv, datetime, re, sys, os

    FORMATS = [(re.compile(r"^\\d{4}-\\d{2}-\\d{2}$"), "%Y-%m-%d"), (re.compile(r"^\\d{2}/\\d{2}/\\d{4}$"), "%d/%m/%Y"),
               (re.compile(r"^\\d{1,2} [A-Z][a-z]{2} \\d{4}$"), "%d %b %Y"), (re.compile(r"^\\d{8}$"), "%Y%m%d")]


    def parse(s):
        s = s.strip()
        for rx, fmt in FORMATS:
            if rx.match(s):
                try:
                    return datetime.datetime.strptime(s, fmt).date().isoformat()
                except ValueError:
                    return None
        return None


    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    good, bad = [], []
    with open(os.path.join(indir, "readings.csv"), newline="", encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd)
        for i, row in enumerate(rd, start=2):
            d = parse(row[1])
            if d is None:
                bad.append((i, row[1]))
            else:
                good.append((d, row[0], row[2]))
    good.sort(key=lambda r: (r[0], r[1]))
    with open(os.path.join(outdir, "clean.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["station", "date", "level_cm"])
        for d, st, lv in good:
            w.writerow([st, d, lv])
    with open(os.path.join(outdir, "rejects.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["line", "raw"])
        for i, raw in bad:
            w.writerow([i, raw])
''')

DOC_DATES = dd('''
    The tide-pool sensors upload `readings.csv` with the columns `station,taken,level_cm`. The `taken` column was typed
    by hand in the field and arrives in four formats:

    | format | example | note |
    |---|---|---|
    | ISO | `2031-03-04` | zero padded |
    | slashes | `04/03/2031` | **day/month/year**, always, zero padded |
    | words | `4 Mar 2031` | day without padding, English three-letter month |
    | compact | `20310304` | exactly eight digits |

    Anything else, or a date that does not exist (`31/02/2031`, month 13, `n/a`, empty), is a *reject*.

    The script is called `python3 etl.py IN_DIR OUT_DIR` and writes two files into `OUT_DIR` (create it if needed):

    * `clean.csv`: header `station,date,level_cm`; one line per good input row with the date as ISO `YYYY-MM-DD`, `level_cm`
      copied as it is. Sorted by date, then station; rows that tie on both keep their input order.
    * `rejects.csv`: header `line,raw`; one line per rejected row: the line number in `readings.csv` (the header is line 1)
      and the original `taken` text. In input order.

    Both files are written even when they have nothing but the header.
''')

# ---------------------------------------------------------------------------------------------------------------- 2. temperatures


def make_temps(rng, big):
    n = rng.randint(35, 60) if big else 9
    rows = []
    while len(rows) < n:
        probe = rng.choice(STATIONS) + "/" + rng.choice(["t1", "t2"])
        unit = rng.choice(["C", "C", "F", "K", "c", " °C", "f"])
        u = unit.strip().replace("°", "").upper()
        if u == "C":
            val = Fraction(rng.randint(-50, 400), 10)
            c = val
        elif u == "F":
            val = Fraction(rng.randint(150, 1100), 10)
            c = (val - 32) * 5 / 9
        else:
            val = Fraction(rng.randint(25000, 31500), 100)
            c = val - Fraction(27315, 100)
        if tie(c, 1):
            continue
        txt = f"{float(val):.2f}".rstrip("0").rstrip(".") if val.denominator != 1 else str(int(val))
        sep = rng.choice(["", " ", ""])
        s = f"{txt}{sep}{unit.strip() if unit.strip() != '°C' else '°C'}"
        if rng.random() < 0.06:
            s = rng.choice(["12.5X", "warm", "-", "40..2C", "9 Rankine"])
        rows.append(f"{probe},{s}")
    return {"probes.csv": "probe,reading\n" + "\n".join(rows) + "\n"}


REF_TEMPS = dd('''
    import csv, os, re, sys
    from decimal import Decimal, ROUND_HALF_UP

    RX = re.compile(r"^\\s*(-?\\d+(?:\\.\\d+)?)\\s*(°C|C|F|K)\\s*$", re.I)
    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    good, bad = [], []
    with open(os.path.join(indir, "probes.csv"), newline="", encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd)
        for i, (probe, reading) in enumerate(rd, start=2):
            m = RX.match(reading)
            if not m:
                bad.append((i, reading))
                continue
            v, u = Decimal(m.group(1)), m.group(2).upper().replace("°", "")
            c = v if u == "C" else (v - 32) * 5 / 9 if u == "F" else v - Decimal("273.15")
            c = c.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            s = f"{c:.1f}"
            if s == "-0.0":
                s = "0.0"
            good.append((probe, s))
    good.sort(key=lambda r: r[0])
    with open(os.path.join(outdir, "celsius.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["probe", "celsius"])
        w.writerows(good)
    with open(os.path.join(outdir, "rejects.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["line", "raw"])
        w.writerows(bad)
''')

ALT_TEMPS = dd('''
    import csv, os, re, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    good, bad = [], []
    rows = list(csv.reader(open(os.path.join(indir, "probes.csv"), encoding="utf-8")))[1:]
    for i, (probe, reading) in enumerate(rows, start=2):
        m = re.fullmatch(r"\\s*(-?[0-9]+(?:\\.[0-9]+)?)\\s*(°C|C|F|K)\\s*", reading, re.I)
        if not m:
            bad.append((i, reading))
            continue
        v = float(m.group(1))
        u = m.group(2).upper().replace("°", "")
        c = v if u == "C" else (v - 32) * 5.0 / 9.0 if u == "F" else v - 273.15
        s = "%.1f" % (round(c, 1) + 0.0)
        good.append((probe, "0.0" if s == "-0.0" else s))
    good.sort(key=lambda r: r[0])
    with open(os.path.join(outdir, "celsius.csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["probe", "celsius"])
        w.writerows(good)
    with open(os.path.join(outdir, "rejects.csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["line", "raw"])
        w.writerows(bad)
''')

DOC_TEMPS = dd('''
    Temperature probes in the tide pools log `probes.csv` with the columns `probe,reading`. A reading is a number
    (optional leading minus, optional decimals) followed by a unit, with optional blanks around the number and the
    unit: `20.5C`, `68.9 F`, `293.15K`, `7 °C`. The unit letters may be upper or lower case; `°C` and `C` both mean
    Celsius. Anything else is a reject.

    `python3 etl.py IN_DIR OUT_DIR` writes into `OUT_DIR`:

    * `celsius.csv`: header `probe,celsius`; every good reading converted to Celsius (F: `(f - 32) * 5 / 9`; K: `k - 273.15`)
      and written with exactly one decimal, rounded half up on the exact decimal value. Never write `-0.0`: write `0.0`.
      Sorted by probe name; rows of the same probe keep their input order.
    * `rejects.csv`: header `line,raw`; line number (header = line 1) and the original reading text, in input order.
''')

# ---------------------------------------------------------------------------------------------------------------- 3. decimal formats


def make_decimals(rng, big):
    n = rng.randint(25, 40) if big else 8
    fmt = {}
    cols = ["flow", "depth", "salinity"]
    for c in cols:
        fmt[c] = rng.choice(["us", "eu", "plain"])
    rows = ["site," + ",".join(cols)]
    for i in range(n):
        vals = []
        for c in cols:
            v = rng.choice([rng.randint(1, 900), rng.randint(1000, 98000)]) + rng.randint(0, 99) / 100
            ip, fp = f"{v:,.2f}".split(".")
            if fmt[c] == "us":
                s = f"{ip}.{fp}"
            elif fmt[c] == "eu":
                s = ip.replace(",", ".") + "," + fp
            else:
                s = f"{v:.2f}"
            if rng.random() < 0.08:
                s = ""
            vals.append(f'"{s}"' if "," in s else s)
        rows.append(f"S{rng.randint(1, 30):02d}," + ",".join(vals))
    return {"export.csv": "\n".join(rows) + "\n", "format.json": '{\n' + ",\n".join(f'  "{c}": "{fmt[c]}"' for c in cols) + "\n}\n"}


REF_DECIMALS = dd('''
    import csv, json, os, sys
    from decimal import Decimal

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    fmt = json.load(open(os.path.join(indir, "format.json"), encoding="utf-8"))


    def num(s, kind):
        s = s.strip()
        if s == "":
            return None
        if kind == "us":
            s = s.replace(",", "")
        elif kind == "eu":
            s = s.replace(".", "").replace(",", ".")
        return Decimal(s)


    rows = list(csv.DictReader(open(os.path.join(indir, "export.csv"), newline="", encoding="utf-8")))
    cols = [c for c in rows[0].keys() if c != "site"] if rows else []
    with open(os.path.join(outdir, "numbers.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["site"] + cols)
        for r in rows:
            out = [r["site"]]
            for c in cols:
                v = num(r[c], fmt[c])
                out.append("" if v is None else f"{v:.2f}")
            w.writerow(out)
    totals = {}
    for c in cols:
        vals = [num(r[c], fmt[c]) for r in rows]
        vals = [v for v in vals if v is not None]
        totals[c] = {"count": len(vals), "sum": f"{sum(vals, Decimal(0)):.2f}"}
    json.dump(totals, open(os.path.join(outdir, "totals.json"), "w", encoding="utf-8"), indent=1, sort_keys=True)
''')

DOC_DECIMALS = dd('''
    A water-quality logger exports `export.csv` (columns `site,flow,depth,salinity`) and the number format of each
    measurement column is declared in `format.json`, because different loggers disagree:

    * `"us"`: `1,234.50`: comma groups thousands, a dot starts the decimals.
    * `"eu"`: `1.234,50`: dots group thousands, a comma starts the decimals.
    * `"plain"`: `1234.50`: no grouping, dot decimals.

    Fields containing a comma are double-quoted in the CSV. An empty field is a missing measurement.

    `python3 etl.py IN_DIR OUT_DIR` writes into `OUT_DIR`:

    * `numbers.csv`: header `site,flow,depth,salinity` (same column order as the input), one line per input row in input order,
      every present value normalised to plain notation with exactly two decimals (`1234.50`), missing values left empty.
    * `totals.json`: for each measurement column an object `{"count": N, "sum": "S"}` with the number of present values and
      their sum formatted with two decimals (a string), e.g. `{"flow": {"count": 3, "sum": "9.50"}, ...}`.
''')

# ---------------------------------------------------------------------------------------------------------------- 4. dedupe by revision


def make_dedupe(rng, big):
    n = rng.randint(30, 50) if big else 8
    rows = []
    for i in range(n):
        st = rng.choice(STATIONS[: 6 if big else 3])
        ts = f"2031-04-{rng.randint(1, 9 if big else 3):02d}T{rng.randint(0, 3):02d}:{rng.choice(['00', '30'])}Z"
        rows.append((st, ts, rng.randint(0, 5), rng.randint(10, 99)))
    rows += [rng.choice(rows) for _ in range(n // 3)]
    rows = [(a, b, rng.randint(0, 5), rng.randint(10, 99)) if rng.random() < 0.5 else (a, b, c, d) for a, b, c, d in rows]
    rng.shuffle(rows)
    return {"feed.csv": "station,ts,rev,value\n" + "\n".join(f"{a},{b},{c},{d}" for a, b, c, d in rows) + "\n"}


REF_DEDUPE = dd('''
    import csv, json, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    best = {}
    total = 0
    with open(os.path.join(indir, "feed.csv"), newline="", encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd)
        for line, (st, ts, rev, val) in enumerate(rd, start=2):
            total += 1
            key = (st, ts)
            cand = (int(rev), -line)
            if key not in best or cand > best[key][0]:
                best[key] = (cand, (st, ts, rev, val))
    rows = [v[1] for _, v in sorted(best.items())]
    with open(os.path.join(outdir, "dedup.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["station", "ts", "rev", "value"])
        w.writerows(rows)
    stations = {}
    for st, ts, rev, val in rows:
        stations[st] = stations.get(st, 0) + 1
    json.dump({"input_rows": total, "kept": len(rows), "dropped": total - len(rows), "per_station": stations},
              open(os.path.join(outdir, "stats.json"), "w", encoding="utf-8"), indent=1, sort_keys=True)
''')

DOC_DEDUPE = dd('''
    Two uploaders sometimes send the same reading twice. `feed.csv` has the columns `station,ts,rev,value`. A reading is
    identified by `(station, ts)`; when several rows share that identity keep the one with the **highest `rev`** (a number);
    if revisions tie, keep the one that appears **earliest** in the file.

    `python3 etl.py IN_DIR OUT_DIR` writes into `OUT_DIR`:

    * `dedup.csv`: same header, the kept rows (all four fields copied unchanged), sorted by station, then ts (plain string order).
    * `stats.json`: `{"input_rows": N, "kept": K, "dropped": N-K, "per_station": {"<station>": kept rows of that station, ...}}`.
      `per_station` only lists stations that have kept rows; key order does not matter.
''')

# ---------------------------------------------------------------------------------------------------------------- 5. csv hygiene


def make_hygiene(rng, big):
    n = rng.randint(14, 24) if big else 6
    words = ["kelp bed", "mussel line", "north, upper", 'the "big" one', "tidal\nflat", "  padded  ", "café", "Zoë's", "plain"]
    rows = []
    for i in range(n):
        note = rng.choice(words)
        q = '"' + note.replace('"', '""') + '"' if any(ch in note for ch in ',"\n') or rng.random() < 0.3 else note
        rows.append(f"{rng.randint(1000, 9999)},{q},{rng.choice(['yes', 'YES', 'y', 'no', 'No', 'n', ''])}")
    nl = rng.choice(["\r\n", "\r\n", "\n"])
    text = nl.join(["id,note,verified"] + rows).replace("\n" if nl == "\r\n" else "\x00", "\n") + nl + (nl if rng.random() < 0.7 else "")
    if rng.random() < 0.7 or not big:
        text = "﻿" + text
    return {"survey.csv": text}


REF_HYGIENE = dd('''
    import csv, io, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    text = open(os.path.join(indir, "survey.csv"), newline="", encoding="utf-8").read()
    if text.startswith("\\ufeff"):
        text = text[1:]
    rows = [r for r in csv.reader(io.StringIO(text, newline="")) if r and any(c.strip() for c in r)]
    header, body = rows[0], rows[1:]
    YES, NO = {"yes", "y"}, {"no", "n"}
    out = []
    for r in body:
        note = " ".join(r[1].split())
        v = r[2].strip().lower()
        out.append([r[0].strip(), note, "true" if v in YES else "false" if v in NO else "unknown"])
    with open(os.path.join(outdir, "survey_clean.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n", quoting=csv.QUOTE_MINIMAL)
        w.writerow(header)
        w.writerows(out)
''')

DOC_HYGIENE = dd('''
    Field surveyors export `survey.csv` (columns `id,note,verified`) from three different tablets, so the file may

    * start with a UTF-8 byte-order mark,
    * use `\\r\\n` or `\\n` line endings (also inside quoted fields),
    * contain quoted fields with commas, doubled quotes (`""`) and line breaks,
    * end with one or more blank lines.

    `python3 etl.py IN_DIR OUT_DIR` writes `survey_clean.csv` into `OUT_DIR`:

    * UTF-8, no BOM, `\\n` line endings, header unchanged; fully blank lines dropped.
    * `id`: surrounding blanks trimmed.
    * `note`: every run of whitespace (spaces, tabs, line breaks) collapsed to one space, and trimmed, so notes never contain a line break.
    * `verified`: `yes`/`y` (any case) become `true`, `no`/`n` (any case) become `false`, anything else (including empty) becomes `unknown`.
    * Fields are quoted only when necessary (comma, quote or line break inside), with `""` for a quote, as Python's `csv` module does by default.
''')

# ---------------------------------------------------------------------------------------------------------------- 6. fixed width


def make_fixed(rng, big):
    n = rng.randint(14, 26) if big else 6
    ws, wl, wn = rng.randint(8, 11), rng.randint(5, 9), rng.randint(14, 24)
    layout = {"station": [0, ws], "date": [ws, ws + 8], "level": [ws + 8, ws + 8 + wl], "flag": [ws + 8 + wl, ws + 9 + wl], "note": [ws + 9 + wl, ws + 9 + wl + wn]}
    lines = []
    for i in range(n):
        st = rng.choice(STATIONS)
        date = f"2031{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
        lv = rng.choice([f"{rng.randint(10, 3999) / 10:.1f}", "-", f"{rng.randint(1, 99) / 10:.1f}"])
        flag = rng.choice([" ", "*", "E", " "])
        note = rng.choice(["", "swell", "low sun glare", "sensor wet", "", "ice on probe"])
        width = layout["level"][1] - layout["level"][0]
        line = st.ljust(ws) + date + lv.rjust(width) + flag + note
        lines.append(line.rstrip() if rng.random() < 0.5 else line.ljust(layout["note"][1]))
    return {"dump.txt": "\n".join(lines) + "\n", "layout.json": "{\n" + ",\n".join(f'  "{k}": [{a}, {b}]' for k, (a, b) in layout.items()) + "\n}\n"}


REF_FIXED = dd('''
    import csv, json, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    layout = json.load(open(os.path.join(indir, "layout.json"), encoding="utf-8"))
    names = ["station", "date", "level", "flag", "note"]
    rows = []
    for line in open(os.path.join(indir, "dump.txt"), encoding="utf-8").read().split("\\n"):
        if not line.strip():
            continue
        rec = {k: line[layout[k][0]:layout[k][1]].strip() for k in names}
        d = rec["date"]
        rec["date"] = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        rec["level"] = "" if rec["level"] == "-" else rec["level"]
        rec["flag"] = {"*": "estimated", "E": "error"}.get(rec["flag"], "")
        rows.append([rec[k] for k in names])
    with open(os.path.join(outdir, "readings.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(names)
        w.writerows(rows)
''')

DOC_FIXED = dd('''
    An old data logger writes `dump.txt`, one reading per line in **fixed-width columns**. The columns are described in
    `layout.json` as `{"field": [start, end]}` with 0-based, end-exclusive character offsets (Python slice style); the
    layout can differ between loggers, so read it. Fields: `station`, `date` (`YYYYMMDD`), `level`, `flag`, `note`.
    Lines may be shorter than the full width (trailing blanks are often stripped). Blank lines are ignored.

    `python3 etl.py IN_DIR OUT_DIR` writes `readings.csv` into `OUT_DIR` with the header `station,date,level,flag,note`:

    * every field is trimmed of surrounding blanks;
    * `date` becomes `YYYY-MM-DD`;
    * `level` is written as it is, except that the placeholder `-` means "no reading" and becomes empty;
    * `flag` is expanded: `*` becomes `estimated`, `E` becomes `error`, a blank stays empty;
    * rows keep their input order; the CSV uses `\\n` line endings and Python-`csv`-style quoting.
''')

# ---------------------------------------------------------------------------------------------------------------- 7. sessionize


def make_episodes(rng, big):
    rows = []
    for st in STATIONS[: 4 if big else 2]:
        minute = rng.randint(0, 60)
        for _ in range(rng.randint(10, 18) if big else rng.randint(4, 7)):
            minute += rng.choice([1, 2, 3, 5, 5, 10, 20, 29, 30, 31, 45, 90, 200])
            rows.append((st, minute, rng.randint(1, 60)))
    rng.shuffle(rows)
    base = 12 * 60
    lines = []
    for st, m, v in rows:
        mm = base + m
        lines.append(f"{st},2031-05-{1 + mm // 1440:02d}T{(mm % 1440) // 60:02d}:{mm % 60:02d},{v}")
    return {"pings.csv": "station,at,spl_db\n" + "\n".join(lines) + "\n"}


REF_EPISODES = dd('''
    import csv, datetime as dt, json, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    by = {}
    with open(os.path.join(indir, "pings.csv"), newline="", encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd)
        for st, at, db in rd:
            by.setdefault(st, []).append((dt.datetime.strptime(at, "%Y-%m-%dT%H:%M"), int(db)))
    episodes = []
    for st in sorted(by):
        pts = sorted(by[st])
        cur = [pts[0]]
        for p in pts[1:]:
            if (p[0] - cur[-1][0]) > dt.timedelta(minutes=30):
                episodes.append((st, cur))
                cur = [p]
            else:
                cur.append(p)
        episodes.append((st, cur))
    out = []
    for st, pts in episodes:
        out.append({"station": st, "start": pts[0][0].strftime("%Y-%m-%dT%H:%M"), "end": pts[-1][0].strftime("%Y-%m-%dT%H:%M"),
                    "pings": len(pts), "peak_db": max(p[1] for p in pts), "minutes": int((pts[-1][0] - pts[0][0]).total_seconds() // 60)})
    json.dump(out, open(os.path.join(outdir, "episodes.json"), "w", encoding="utf-8"), indent=1)
''')

DOC_EPISODES = dd('''
    Hydrophones log a sound-pressure ping into `pings.csv` (`station,at,spl_db`, `at` as `YYYY-MM-DDTHH:MM`, rows in no
    particular order). Group each station's pings into **episodes**: after sorting a station's pings by time, a new
    episode starts whenever the gap to the previous ping is **more than 30 minutes** (exactly 30 minutes continues the episode).
    Episodes never mix stations.

    `python3 etl.py IN_DIR OUT_DIR` writes `episodes.json` into `OUT_DIR`: a JSON list, one object per episode, ordered by
    station name and then start time, with the keys `station`, `start` and `end` (first and last ping time, same text format
    as the input), `pings` (count), `peak_db` (largest `spl_db`) and `minutes` (whole minutes from start to end).
''')

# ---------------------------------------------------------------------------------------------------------------- 8. forward fill


def make_fill(rng, big):
    rows = []
    for st in STATIONS[: 3 if big else 2]:
        for day in range(1, (8 if big else 4) + 1):
            for h in range(0, 24, 6):
                if rng.random() < 0.28:
                    v = ""
                else:
                    v = f"{rng.randint(80, 260) / 10:.1f}"
                rows.append(f"{st},2031-06-{day:02d} {h:02d}:00,{v}")
    return {"temps.csv": "station,at,temp_c\n" + "\n".join(rows) + "\n"}


REF_FILL = dd('''
    import csv, json, os, sys
    from decimal import Decimal, ROUND_HALF_UP

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    rows = list(csv.DictReader(open(os.path.join(indir, "temps.csv"), newline="", encoding="utf-8")))
    last = {}
    gap = {}
    out = []
    for r in rows:
        st = r["station"]
        if r["temp_c"] != "":
            last[st] = r["temp_c"]
            gap[st] = 0
            out.append([st, r["at"], r["temp_c"], "measured"])
        else:
            gap[st] = gap.get(st, 0) + 1
            if st in last and gap[st] <= 2:
                out.append([st, r["at"], last[st], "filled"])
            else:
                out.append([st, r["at"], "", "missing"])
    with open(os.path.join(outdir, "filled.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["station", "at", "temp_c", "quality"])
        w.writerows(out)
    days = {}
    for st, at, v, q in out:
        if v != "":
            days.setdefault((st, at[:10]), []).append(float(v))
    mean = {}
    for (st, d), vs in sorted(days.items()):
        mean.setdefault(st, {})[d] = float((sum(Decimal(str(x)) for x in vs) / len(vs)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    json.dump(mean, open(os.path.join(outdir, "daily_mean.json"), "w", encoding="utf-8"), indent=1, sort_keys=True)
''')

DOC_FILL = dd('''
    `temps.csv` holds a reading every 6 hours per station (`station,at,temp_c`; rows are already in time order inside
    each station, stations may be interleaved); `temp_c` is empty when the sensor missed a reading.

    Fill short gaps by carrying the last measured value forward, but **at most two consecutive missing readings per
    station**: the 1st and 2nd empty reading after a measured one are filled, the 3rd and later stay missing until the
    next real measurement. Readings before a station's first measurement stay missing.

    `python3 etl.py IN_DIR OUT_DIR` writes into `OUT_DIR`:

    * `filled.csv`: header `station,at,temp_c,quality`; every input row in input order with `quality` `measured`, `filled`
      or `missing` (temp copied/filled as text, empty when missing).
    * `daily_mean.json`: `{"<station>": {"YYYY-MM-DD": mean}}` where the mean covers every non-missing value of that day in
      `filled.csv` (measured **and** filled), rounded half up to 2 decimals. Days with no non-missing value are left out.
''')

# ---------------------------------------------------------------------------------------------------------------- 9. outliers


def make_outliers(rng, big):
    rows = []
    for st in STATIONS[: 4 if big else 2]:
        base = rng.randint(100, 300)
        for i in range(rng.randint(14, 24) if big else rng.randint(6, 9)):
            v = base + rng.randint(-12, 12)
            if rng.random() < 0.12:
                v = base + rng.choice([-1, 1]) * rng.randint(60, 200)
            rows.append(f"{st},{v}")
    rng.shuffle(rows)
    return {"levels.csv": "station,level_mm\n" + "\n".join(rows) + "\n"}


REF_OUTLIERS = dd('''
    import csv, json, os, sys
    from decimal import Decimal, ROUND_HALF_UP

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    by = {}
    order = []
    with open(os.path.join(indir, "levels.csv"), newline="", encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd)
        for st, v in rd:
            by.setdefault(st, []).append(int(v))
            order.append((st, int(v)))


    def median2(vals):
        """twice the median, an integer"""
        s = sorted(vals)
        n = len(s)
        return 2 * s[n // 2] if n % 2 else s[n // 2 - 1] + s[n // 2]


    limits = {}
    for st, vals in by.items():
        m2 = median2(vals)
        dev = [abs(2 * v - m2) for v in vals]  # twice the absolute deviations
        mad2 = median2(dev)  # dev holds twice the absolute deviations, so this is 4 * MAD
        limits[st] = (m2, mad2)
    kept, dropped = [], []
    for st, v in order:
        m2, mad2 = limits[st]
        # |v - median| > 3 * MAD  <=>  (|2v - m2| / 2) > 3 * (mad2 / 4)  <=>  2 * |2v - m2| > 3 * mad2
        if 2 * abs(2 * v - m2) > 3 * mad2:
            dropped.append((st, v))
        else:
            kept.append((st, v))
    with open(os.path.join(outdir, "kept.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["station", "level_mm"])
        w.writerows(kept)
    summary = {}
    for st in sorted(by):
        k = [v for s, v in kept if s == st]
        summary[st] = {"kept": len(k), "dropped": sum(1 for s, v in dropped if s == st), "mean": float((Decimal(sum(k)) / len(k)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)) if k else None}
    json.dump(summary, open(os.path.join(outdir, "summary.json"), "w", encoding="utf-8"), indent=1, sort_keys=True)
''')

DOC_OUTLIERS = dd('''
    `levels.csv` (`station,level_mm`, integers) contains the odd wave-slap spike. Remove outliers **per station** with the
    median-absolute-deviation rule:

    * `median` of the station's levels (for an even count, the mean of the two middle values);
    * `MAD` = the median of `|level - median|` over the station's levels;
    * a reading is an outlier when `|level - median| > 3 * MAD` (strictly greater). Note that with `MAD = 0`
      every reading that differs from the median is an outlier.

    The median and MAD are computed over **all** of the station's readings (before any removal).

    `python3 etl.py IN_DIR OUT_DIR` writes into `OUT_DIR`:

    * `kept.csv`: header `station,level_mm`; the non-outlier rows in input order.
    * `summary.json`: for each station `{"kept": K, "dropped": D, "mean": M}`, the mean of the kept levels rounded half up to 1 decimal
      (`null` if nothing was kept).
''')

# ---------------------------------------------------------------------------------------------------------------- 10. reconcile


def make_reconcile(rng, big):
    auto, manual = [], []
    n = rng.randint(24, 36) if big else 8
    for i in range(n):
        st = rng.choice(STATIONS[:4])
        t = rng.randint(0, 40 * 60 * (2 if big else 1))
        v = rng.randint(100, 400)
        auto.append((st, t, v))
        r = rng.random()
        if r < 0.55:
            manual.append((st, t + rng.randint(-5, 5), v + rng.choice([0, 0, 0, 1, -1, 2, -2, 5])))
        elif r < 0.7:
            manual.append((st, t + rng.choice([-10, 10, -11, 11, 6, -6]), v))
    for _ in range(3 if big else 1):
        manual.append((rng.choice(STATIONS[:4]), rng.randint(0, 40 * 60), rng.randint(100, 400)))

    def fmt(m):
        return f"2031-07-{1 + m // 1440:02d} {(m % 1440) // 60:02d}:{m % 60:02d}"
    auto = [(a, max(0, b), c) for a, b, c in auto]
    manual = [(a, max(0, b), c) for a, b, c in manual]
    return {"auto.csv": "station,at,level\n" + "\n".join(f"{a},{fmt(b)},{c}" for a, b, c in auto) + "\n",
            "manual.csv": "station,at,level\n" + "\n".join(f"{a},{fmt(b)},{c}" for a, b, c in manual) + "\n"}


REF_RECONCILE = dd('''
    import csv, datetime as dt, json, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)


    def load(name):
        with open(os.path.join(indir, name), newline="", encoding="utf-8") as f:
            rd = csv.reader(f)
            next(rd)
            return [(st, dt.datetime.strptime(at, "%Y-%m-%d %H:%M"), int(v), i) for i, (st, at, v) in enumerate(rd)]


    auto, manual = load("auto.csv"), load("manual.csv")
    used = set()
    result = []
    for st, at, v, i in auto:
        best = None
        for mst, mat, mv, j in manual:
            if mst != st or j in used:
                continue
            gap = abs((mat - at).total_seconds()) / 60
            if gap <= 10 and (best is None or (gap, j) < best[0]):
                best = ((gap, j), j, mv)
        if best is None:
            result.append((st, at, "auto_only", v, ""))
        else:
            used.add(best[1])
            diff = abs(best[2] - v)
            result.append((st, at, "match" if diff <= 2 else "conflict", v, best[2]))
    for st, at, v, j in manual:
        if j not in used:
            result.append((st, at, "manual_only", "", v))
    result.sort(key=lambda r: (r[0], r[1], r[2]))
    with open(os.path.join(outdir, "reconciled.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["station", "at", "status", "auto_level", "manual_level"])
        for st, at, status, a, m in result:
            w.writerow([st, at.strftime("%Y-%m-%d %H:%M"), status, a, m])
    counts = {}
    for r in result:
        counts[r[2]] = counts.get(r[2], 0) + 1
    json.dump({k: counts.get(k, 0) for k in ("match", "conflict", "auto_only", "manual_only")}, open(os.path.join(outdir, "counts.json"), "w", encoding="utf-8"), indent=1, sort_keys=True)
''')

DOC_RECONCILE = dd('''
    Each station has an automatic logger (`auto.csv`) and a field notebook that someone typed up (`manual.csv`); both have the
    columns `station,at,level` (`at` as `YYYY-MM-DD HH:MM`, `level` an integer). Reconcile them:

    1. Go through the automatic readings **in file order**. Pair each with the *unused* manual reading of the **same station**
       whose time is closest, as long as the two are **at most 10 minutes apart**; if two candidates are equally close the one
       earlier in `manual.csv` wins. A manual reading can be paired only once.
    2. A pair is a `match` when the levels differ by at most 2, otherwise a `conflict`. An automatic reading with no partner
       is `auto_only`; a manual reading never paired is `manual_only`.

    `python3 etl.py IN_DIR OUT_DIR` writes into `OUT_DIR`:

    * `reconciled.csv`: header `station,at,status,auto_level,manual_level`; one row per pair or lone reading. `at` is the
      automatic reading's time (manual time for `manual_only`); the missing level of a lone reading is left empty. Sorted by
      station, then `at`, then status (plain string order); rows that tie on all three keep the order in which they were produced (all automatic readings in file order, then the unpaired manual ones in file order).
    * `counts.json`: `{"match": n, "conflict": n, "auto_only": n, "manual_only": n}`.
''')

S = E.EtlSpec

SPECS = [
    S("mixed-dates", 2,
      "The field team types dates however they like and `etl.py` has to turn the tide-pool readings export into a clean file with ISO dates, plus a list of the rows it couldn't read. The formats and file layouts are in the README.",
      DOC_DATES, make_dates, REF_DATES, {"clean.csv": "csv", "rejects.csv": "csv"},
      wrong=("""import csv, datetime, os, sys
indir, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
good, bad = [], []
for i, row in enumerate(list(csv.reader(open(os.path.join(indir, 'readings.csv'))))[1:], start=2):
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d %b %Y', '%Y%m%d'):
        try:
            good.append((datetime.datetime.strptime(row[1], fmt).date().isoformat(), row[0], row[2])); break
        except ValueError:
            pass
    else:
        bad.append((i, row[1]))
good.sort(key=lambda r: (r[0], r[1]))
w = csv.writer(open(os.path.join(outdir, 'clean.csv'), 'w', newline=''), lineterminator='\\n'); w.writerow(['station', 'date', 'level_cm']); w.writerows([(s, d, l) for d, s, l in good])
w = csv.writer(open(os.path.join(outdir, 'rejects.csv'), 'w', newline=''), lineterminator='\\n'); w.writerow(['line', 'raw']); w.writerows(bad)
""",), title="Tide-pool readings: date cleanup", tags=("dates",)),
    S("probe-units", 3,
      "Probe readings arrive as text like `68.9 F`, `293.15K` or `7 °C`. Write `etl.py` so it converts everything to Celsius with one decimal as described in the README and sets aside what it can't parse.",
      DOC_TEMPS, make_temps, REF_TEMPS, {"celsius.csv": "csv", "rejects.csv": "csv"}, alt=ALT_TEMPS,
      title="Tide-pool probes: units", tags=("units",)),
    S("number-formats", 3,
      "The water-quality loggers export numbers in different regional formats, and `format.json` says which column uses which. Normalise `export.csv` to plain two-decimal numbers and total each column, as the README describes.",
      DOC_DECIMALS, make_decimals, REF_DECIMALS, {"numbers.csv": "csv", "totals.json": "json"},
      title="Water-quality export: number formats", tags=("locale",)),
    S("dedupe-revisions", 3,
      "Readings are sometimes uploaded twice, with a revision number. I need a script that keeps only the highest revision of each reading and tells me how much it threw away. The README has the exact rules.",
      DOC_DEDUPE, make_dedupe, REF_DEDUPE, {"dedup.csv": "csv", "stats.json": "json"},
      wrong=("""import csv, json, os, sys
indir, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
rows = list(csv.reader(open(os.path.join(indir, 'feed.csv'))))[1:]
best = {}
for st, ts, rev, v in rows:
    k = (st, ts)
    if k not in best or int(rev) >= int(best[k][2]):
        best[k] = (st, ts, rev, v)
kept = [best[k] for k in sorted(best)]
w = csv.writer(open(os.path.join(outdir, 'dedup.csv'), 'w', newline=''), lineterminator='\\n'); w.writerow(['station', 'ts', 'rev', 'value']); w.writerows(kept)
per = {}
for r in kept: per[r[0]] = per.get(r[0], 0) + 1
json.dump({'input_rows': len(rows), 'kept': len(kept), 'dropped': len(rows) - len(kept), 'per_station': per}, open(os.path.join(outdir, 'stats.json'), 'w'))
""",), title="Sensor feed: duplicate uploads", tags=("dedupe",)),
    S("csv-hygiene", 3,
      "Surveyors' tablets produce `survey.csv` files with a BOM, mixed line endings, quoted commas and line breaks inside notes. Make `etl.py` write a clean, canonical version (rules in the README).",
      DOC_HYGIENE, make_hygiene, REF_HYGIENE, {"survey_clean.csv": "text"},
      title="Survey tablets: CSV hygiene", tags=("encoding", "csv")),
    S("fixed-width-dump", 3,
      "An old logger prints fixed-width text. The column offsets are in `layout.json` (and differ per logger). Convert `dump.txt` to a proper CSV, following the README.",
      DOC_FIXED, make_fixed, REF_FIXED, {"readings.csv": "csv"},
      title="Logger dump: fixed-width columns", tags=("fixed-width",)),
    S("ping-episodes", 4,
      "Hydrophone pings need to be grouped into listening episodes per station (a pause longer than half an hour starts a new one) and summarised as JSON. Details in the README.",
      DOC_EPISODES, make_episodes, REF_EPISODES, {"episodes.json": "json"},
      wrong=("""import csv, datetime as dt, json, os, sys
indir, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
by = {}
for st, at, db in list(csv.reader(open(os.path.join(indir, 'pings.csv'))))[1:]:
    by.setdefault(st, []).append((dt.datetime.strptime(at, '%Y-%m-%dT%H:%M'), int(db)))
out = []
for st in sorted(by):
    pts = sorted(by[st]); cur = [pts[0]]; eps = []
    for p in pts[1:]:
        if (p[0] - cur[-1][0]) >= dt.timedelta(minutes=30):
            eps.append(cur); cur = [p]
        else:
            cur.append(p)
    eps.append(cur)
    for pts in eps:
        out.append({'station': st, 'start': pts[0][0].strftime('%Y-%m-%dT%H:%M'), 'end': pts[-1][0].strftime('%Y-%m-%dT%H:%M'), 'pings': len(pts), 'peak_db': max(p[1] for p in pts), 'minutes': int((pts[-1][0] - pts[0][0]).total_seconds() // 60)})
json.dump(out, open(os.path.join(outdir, 'episodes.json'), 'w'))
""",), title="Hydrophone pings: episodes", tags=("sessionize",)),
    S("short-gap-fill", 4,
      "Temperature loggers drop readings. Fill short gaps (at most two in a row) from the last good value, flag what you filled, and produce daily means that use the filled values too. The README has the rules.",
      DOC_FILL, make_fill, REF_FILL, {"filled.csv": "csv", "daily_mean.json": "json"},
      title="Temperature logs: filling short gaps", tags=("imputation",)),
    S("mad-outliers", 4,
      "Wave slaps put spikes in the water-level series. Drop outliers per station with the median/MAD rule from the README and report what was kept, using exact integer comparisons where it matters.",
      DOC_OUTLIERS, make_outliers, REF_OUTLIERS, {"kept.csv": "csv", "summary.json": "json"},
      title="Water levels: MAD outlier removal", tags=("statistics",)),
    S("auto-vs-notebook", 5,
      "We have an automatic logger and a typed-up field notebook for the same stations. Pair the readings up, classify the pairs and the leftovers, and write the reconciliation files described in the README.",
      DOC_RECONCILE, make_reconcile, REF_RECONCILE, {"reconciled.csv": "csv", "counts.json": "json"},
      title="Logger vs notebook: reconciliation", tags=("matching",)),
]


@family("data-etl-tidepool", category="data", lang="python", kind="feature", n=len(SPECS),
        summary="python ETL scripts on messy tide-pool sensor exports: dates, units, locales, dedupe, gaps, outliers, reconciliation")
def tidepool(rng, n):
    return E.etl_tasks("tidepool", SPECS, rng, n)
