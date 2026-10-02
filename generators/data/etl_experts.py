"""Expert python ETL tasks: stream sessionisation with a watermark and sealed sessions; recurring calendar rules with weeks, month ends, exclusions and time zones."""
import csv
import datetime as dt
import io
import json

from fx import dd, family
from generators.data import _etlkit as E


def spec(slug, d, prompt, doc, make, ref, outputs, **kw):
    return E.EtlSpec(slug=slug, d=d, prompt=prompt, doc=doc, make=make, ref=ref, outputs=outputs, **kw)


# ---------------------------------------------------------------------------------------------------------------- 1. sessions with a watermark

DEVICES = ["gate-n", "gate-s", "lift-1", "lift-2", "kiosk"]


def make_sessions(rng, big):
    base = dt.datetime(2036, 11, rng.randint(3, 20), rng.randint(6, 15), rng.randint(0, 59), rng.randint(0, 59))
    ev = []  # (ts, device, value)
    devs = rng.sample(DEVICES, 3 if big else 2)
    for d in devs:
        t = base + dt.timedelta(seconds=rng.randint(0, 600))
        for _ in range(rng.randint(3, 6) if big else 2):
            for _ in range(rng.randint(1, 5)):
                ev.append((t, d, rng.randint(1, 40)))
                t += dt.timedelta(seconds=rng.choice([20, 45, 90, 150, 240, 299, 300]))
            t += dt.timedelta(seconds=rng.choice([301, 420, 900, 1500]))
    ev.sort(key=lambda e: (e[0], e[1]))
    # arrival disorder: some events arrive later than they happened
    order = list(ev)
    for _ in range(max(2, len(order) // 6)):
        i = rng.randrange(len(order) - 1)
        j = min(len(order) - 1, i + rng.randint(1, 18))
        order.insert(j, order.pop(i))
    # planted scenarios on a spare device: (1) a late event bridges two open sessions; (2) the same, but a third event has sealed the first session;
    # (3) a late event arrives exactly when the first session becomes sealed (watermark == end + 300)
    spare = [d for d in DEVICES if d not in devs][0]
    t0 = base + dt.timedelta(hours=3)
    plant = [(t0, 5), (t0 + dt.timedelta(seconds=330), 7), (t0 + dt.timedelta(seconds=165), 3)]
    t1 = t0 + dt.timedelta(hours=2)
    plant += [(t1, 2), (t1 + dt.timedelta(seconds=330), 4), (t1 + dt.timedelta(seconds=400), 6), (t1 + dt.timedelta(seconds=165), 9)]
    t2 = t1 + dt.timedelta(hours=2)
    plant += [(t2, 8), (t2 + dt.timedelta(seconds=360), 1), (t2 + dt.timedelta(seconds=200), 5)]
    k = rng.randint(1, len(order))
    arrivals = [(t, spare, v) for t, v in plant]
    order = order[:k] + arrivals + order[k:]
    rows = ["device,ts,value"]
    for i, (t, d, v) in enumerate(order):
        val = "" if rng.random() < 0.04 and i % 5 == 0 else str(v)
        rows.append(f"{d},{t.strftime('%Y-%m-%dT%H:%M:%S')},{val}")
    return {"events.csv": "\n".join(rows) + "\n"}


REF_SESSIONS = dd(r'''
    import csv, datetime as dt, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    GAP, DELAY = dt.timedelta(seconds=300), dt.timedelta(seconds=60)
    sessions = {}  # device -> list of [start, end, events, total]
    late = []
    wm = None
    for line, r in enumerate(csv.DictReader(open(os.path.join(indir, "events.csv"), newline="", encoding="utf-8")), start=2):
        if r["value"].strip() == "":
            continue
        t = dt.datetime.strptime(r["ts"], "%Y-%m-%dT%H:%M:%S")
        v = int(r["value"])
        mine = sessions.setdefault(r["device"], [])
        reach = [s for s in mine if s[0] - GAP <= t <= s[1] + GAP]
        if any(wm is not None and wm >= s[1] + GAP for s in reach):
            late.append([line, r["device"], r["ts"]])
            continue
        if reach:
            s = reach[0]
            for o in reach[1:]:
                s[0], s[1], s[2], s[3] = min(s[0], o[0]), max(s[1], o[1]), s[2] + o[2], s[3] + o[3]
                mine.remove(o)
            s[0], s[1], s[2], s[3] = min(s[0], t), max(s[1], t), s[2] + 1, s[3] + v
        else:
            mine.append([t, t, 1, v])
        wm = t - DELAY if wm is None else max(wm, t - DELAY)
    fmt = lambda x: x.strftime("%Y-%m-%dT%H:%M:%S")
    with open(os.path.join(outdir, "sessions.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["device", "start", "end", "events", "total"])
        for d in sorted(sessions):
            for s in sorted(sessions[d]):
                w.writerow([d, fmt(s[0]), fmt(s[1]), s[2], s[3]])
    with open(os.path.join(outdir, "late.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["line", "device", "ts"])
        w.writerows(late)
''')

ALT_SESSIONS = dd(r'''
    import csv, datetime as dt, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    rows = []
    for line, r in enumerate(csv.DictReader(open(os.path.join(indir, "events.csv"), newline="", encoding="utf-8")), start=2):
        if r["value"].strip():
            rows.append((line, r["device"], dt.datetime.strptime(r["ts"], "%Y-%m-%dT%H:%M:%S"), int(r["value"]), r["ts"]))

    def build(events):
        """sessions of a list of (device, t, v): maximal runs with gaps <= 300 s"""
        out = {}
        for dev, t, v in sorted(events):
            runs = out.setdefault(dev, [])
            if runs and (t - runs[-1][1]).total_seconds() <= 300:
                runs[-1][1] = t
                runs[-1][2] += 1
                runs[-1][3] += v
            else:
                runs.append([t, t, 1, v])
        return out

    accepted, late, wm = [], [], None
    for line, dev, t, v, raw in rows:
        known = build(accepted).get(dev, [])
        sealed = [s for s in known if wm is not None and (wm - s[1]).total_seconds() >= 300]
        if any((s[0] - t).total_seconds() <= 300 and (t - s[1]).total_seconds() <= 300 for s in sealed):
            late.append((line, dev, raw))
            continue
        accepted.append((dev, t, v))
        cand = t - dt.timedelta(seconds=60)
        wm = cand if wm is None or cand > wm else wm
    res = build(accepted)
    with open(os.path.join(outdir, "sessions.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["device", "start", "end", "events", "total"])
        for d in sorted(res):
            for s in res[d]:
                w.writerow([d, s[0].isoformat(), s[1].isoformat(), s[2], s[3]])
    with open(os.path.join(outdir, "late.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["line", "device", "ts"])
        w.writerows(late)
''')

DOC_SESSIONS = dd('''
    `events.csv` (`device,ts,value`) is a log of sensor events **in the order in which they arrived**; `ts` (`YYYY-MM-DDTHH:MM:SS`, one shared clock) says when each event happened, so the file is not sorted by `ts`.
    `value` is an integer; rows with an empty `value` are damaged: ignore them completely (they are not late, they do not move the watermark).

    **Sessions.** Per device, the events that were *accepted* form sessions: two events of a device belong to the same session when the gap between them is at most 300 seconds, directly or through events in between (a session is a maximal run of events whose consecutive gaps are all `<= 300 s`).
    A session has a `start` (earliest `ts`), an `end` (latest `ts`), a number of events and the total of their values.

    **Watermark.** Rows are processed in file order. The watermark `W` is undefined at the start; after a row is *accepted* it becomes `max(W, ts - 60 s)`. A session is **sealed** when `W >= end + 300 s`. It stays sealed.
    A row is **late** when its `ts` lies within 300 s (inclusive, both directions) of a session of its device that is sealed at that moment, i.e. `start - 300 s <= ts <= end + 300 s`. Late rows are not accepted: they change no session and not the watermark.
    All other rows are accepted; an accepted row may start a new session, extend one, or join two unsealed sessions into one.

    `python3 etl.py IN_DIR OUT_DIR` writes `sessions.csv` (`device,start,end,events,total`; sessions as they are after the last row, ordered by device and then `start`, timestamps in the input format)
    and `late.csv` (`line,device,ts`: the line number in `events.csv` with the header as line 1, the device, and the `ts` text; in file order).
''')


# ---------------------------------------------------------------------------------------------------------------- 2. recurring calendar rules

ZONES = ["Europe/Oslo", "America/New_York", "Asia/Kolkata", "Australia/Sydney", "UTC", "America/Sao_Paulo"]
DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
TITLES = ["standup", "review", "backup window", "payroll", "lab cleaning", "newsletter", "tide survey", "board call", "inventory", "rota swap", "fire drill", "stand-down"]


def make_rules(rng, big):
    rows = []
    n = rng.randint(7, 10) if big else 5
    titles = rng.sample(TITLES, n)
    for i in range(n):
        tz = rng.choice(ZONES)
        start = dt.date(2034, rng.randint(1, 3), rng.randint(1, 28)) + dt.timedelta(days=rng.choice([0, 0, 1, 2, 3, 4, 5, 6]))
        time = rng.choice(["06:30", "09:00", "09:00", "12:15", "17:45", "22:30"])
        freq = rng.choice(["daily", "weekly", "weekly", "weekly", "monthly", "monthly"])
        interval = rng.choice([1, 1, 2, 3]) if freq != "daily" else rng.choice([1, 2, 3, 5])
        byday, bymd = "", ""
        if freq == "weekly":
            byday = ",".join(sorted(rng.sample(DAYS, rng.choice([0, 1, 2, 3])), key=DAYS.index))
        if freq == "monthly":
            bymd = rng.choice(["", "31", "30", "29", "-1", "-2", "15", "1"])
        count = rng.choice(["", "", str(rng.randint(3, 12))])
        until = "" if count else rng.choice(["", (start + dt.timedelta(days=rng.randint(60, 400))).isoformat()])
        ex = []
        for _ in range(rng.choice([0, 1, 2])):
            ex.append((start + dt.timedelta(days=rng.randint(0, 200))).isoformat())
        rows.append([f"r{i + 1}", titles[i], tz, time, start.isoformat(), freq, str(interval), byday, bymd, count, until, ";".join(ex)])
    # planted: a month-end rule, an every-other-week rule starting on a Sunday with two days, a count rule whose excluded date is the very first instance
    rows[0][2:] = ["Australia/Sydney", "09:00", "2034-01-31", "monthly", "1", "", "31", "", "", ""]
    rows[1][2:] = ["America/New_York", "17:45", "2034-02-05", "weekly", "2", "SU,MO", "", "6", "", "2034-02-05"]
    rows[-1][2:] = ["Europe/Oslo", "22:30", "2034-03-20", "daily", "1", "", "", "", "2034-04-09", ""]
    lo = dt.date(2034, 2, 20) + dt.timedelta(days=rng.randint(0, 30))
    hi = lo + dt.timedelta(days=rng.randint(100, 220) if big else 75)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["id", "title", "tz", "time", "start", "freq", "interval", "byday", "bymonthday", "count", "until", "exdates"])
    w.writerows(rows)
    return {"rules.csv": buf.getvalue(), "range.txt": f"{lo.isoformat()} {hi.isoformat()}\n"}


REF_RULES = dd(r'''
    import calendar, csv, datetime as dt, os, sys
    from zoneinfo import ZoneInfo

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    lo, hi = (dt.date.fromisoformat(x) for x in open(os.path.join(indir, "range.txt")).read().split())
    DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


    def local_dates(r):
        """every local date of the rule in ascending order, stopping at `hi` (or earlier at `until`); count is applied by the caller"""
        start = dt.date.fromisoformat(r["start"])
        step = int(r["interval"])
        until = dt.date.fromisoformat(r["until"]) if r["until"] else None
        limit = hi if until is None else min(hi, until)
        if r["freq"] == "daily":
            d = start
            while d <= limit:
                yield d
                d += dt.timedelta(days=step)
        elif r["freq"] == "weekly":
            days = [DAYS.index(x) for x in r["byday"].split(",")] if r["byday"] else [start.weekday()]
            monday = start - dt.timedelta(days=start.weekday())
            while monday <= limit:
                for wd in sorted(days):
                    d = monday + dt.timedelta(days=wd)
                    if d >= start and d <= limit:
                        yield d
                monday += dt.timedelta(weeks=step)
        else:
            md = int(r["bymonthday"]) if r["bymonthday"] else start.day
            y, m = start.year, start.month
            while dt.date(y, m, 1) <= limit:
                last = calendar.monthrange(y, m)[1]
                day = md if md > 0 else last + 1 + md
                if 1 <= day <= last:
                    d = dt.date(y, m, day)
                    if d >= start and d <= limit:
                        yield d
                m += step
                y += (m - 1) // 12
                m = (m - 1) % 12 + 1


    out, summary = [], []
    for r in csv.DictReader(open(os.path.join(indir, "rules.csv"), newline="", encoding="utf-8")):
        tz = ZoneInfo(r["tz"])
        hh, mm = (int(x) for x in r["time"].split(":"))
        ex = {dt.date.fromisoformat(x) for x in r["exdates"].split(";") if x}
        limit = int(r["count"]) if r["count"] else None
        seen, n = 0, 0
        for d in local_dates(r):
            if limit is not None and seen >= limit:
                break
            seen += 1
            if d in ex or d < lo or d > hi:
                continue
            utc = dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz).astimezone(dt.timezone.utc)
            out.append([utc.strftime("%Y-%m-%dT%H:%MZ"), r["id"], r["title"]])
            n += 1
        summary.append([r["id"], n])
    out.sort(key=lambda x: (x[0], x[1]))
    with open(os.path.join(outdir, "instances.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["utc", "id", "title"])
        w.writerows(out)
    with open(os.path.join(outdir, "summary.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "in_range"])
        w.writerows(summary)
''')

ALT_RULES = dd(r'''
    import calendar, csv, datetime as dt, os, sys
    from zoneinfo import ZoneInfo

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    lo, hi = (dt.date.fromisoformat(x) for x in open(os.path.join(indir, "range.txt")).read().split())
    NAMES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
    rows = list(csv.DictReader(open(os.path.join(indir, "rules.csv"), newline="", encoding="utf-8")))
    res, per = [], {}
    for r in rows:
        start = dt.date.fromisoformat(r["start"])
        step = int(r["interval"])
        end = hi if not r["until"] else min(hi, dt.date.fromisoformat(r["until"]))
        want = {NAMES.index(x) for x in r["byday"].split(",")} if r["byday"] else {start.weekday()}
        cap = int(r["count"]) if r["count"] else 10 ** 9
        ex = {x for x in r["exdates"].split(";") if x}
        tz, (hh, mm) = ZoneInfo(r["tz"]), (int(x) for x in r["time"].split(":"))
        k, d, per[r["id"]] = 0, start, 0
        while d <= end and k < cap:
            if r["freq"] == "daily":
                hit = (d - start).days % step == 0
            elif r["freq"] == "weekly":
                weeks = ((d - dt.timedelta(days=d.weekday())) - (start - dt.timedelta(days=start.weekday()))).days // 7
                hit = weeks % step == 0 and d.weekday() in want
            else:
                months = (d.year - start.year) * 12 + d.month - start.month
                last = calendar.monthrange(d.year, d.month)[1]
                target = int(r["bymonthday"]) if r["bymonthday"] else start.day
                target = target if target > 0 else last + 1 + target
                hit = months % step == 0 and d.day == target
            if hit:
                k += 1
                if d.isoformat() not in ex and lo <= d:
                    u = dt.datetime.combine(d, dt.time(hh, mm), tzinfo=tz).astimezone(dt.timezone.utc)
                    res.append((u.strftime("%Y-%m-%dT%H:%MZ"), r["id"], r["title"]))
                    per[r["id"]] += 1
            d += dt.timedelta(days=1)
    res.sort(key=lambda x: (x[0], x[1]))
    with open(os.path.join(outdir, "instances.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["utc", "id", "title"])
        w.writerows(res)
    with open(os.path.join(outdir, "summary.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "in_range"])
        for r in rows:
            w.writerow([r["id"], per[r["id"]]])
''')

DOC_RULES = dd('''
    `rules.csv` holds recurring events: `id,title,tz,time,start,freq,interval,byday,bymonthday,count,until,exdates`. `range.txt` holds two dates `FROM TO` (inclusive) on one line.
    Each rule produces **instances** on local calendar dates, at the wall-clock `time` (`HH:MM`) of the IANA zone `tz` (Python's `zoneinfo` knows them; all times in the data exist exactly once).

    * `start` (local date) is the first date that may be an instance. `freq` is `daily`, `weekly` or `monthly`; `interval` is a positive integer.
    * `daily`: `start`, then every `interval` days.
    * `weekly`: weeks run **Monday to Sunday**; the week that contains `start` is week 0, and the rule is active in weeks 0, `interval`, 2 x `interval`, ... In an active week the instances are on the days listed in `byday` (comma-separated `MO`..`SU`; empty means the weekday of `start`),
      but never before `start` (days of the first week before `start` are not instances and do not count).
    * `monthly`: the rule is active in the month of `start` and every `interval` months after it. `bymonthday` is the day of the month: `1`..`31`, or negative counted from the end of the month (`-1` last day, `-2` the day before it); empty means the day of the month of `start`.
      A month that does not have that day (31 in April, 30 in February, ...) has **no instance** (nothing is moved to another day and nothing counts); dates before `start` are not instances.
    * `count` (empty = no limit): only the first `count` instances, counted in date order from `start` **before** `exdates` are removed. `until` (empty = no limit): no instance after this local date (inclusive). If both are given, whichever ends the rule first wins.
    * `exdates`: semicolon-separated local dates that are removed from the instances (they still count toward `count`).

    `python3 etl.py IN_DIR OUT_DIR` writes `instances.csv` (`utc,id,title`): every instance whose **local date** lies in `FROM`..`TO`, with its start as UTC `YYYY-MM-DDTHH:MMZ`, ordered by `utc` and then `id`;
    and `summary.csv` (`id,in_range`): one row per rule in the order of `rules.csv` with the number of its instances in the range (0 allowed).
    Rules whose instances begin long before `FROM` still have to be counted from `start`.
''')


def rep(text, a, b):
    assert a in text, a
    return text.replace(a, b)


SPECS = [
    spec("watermark-sessions", 5, "Write `etl.py` that groups the out-of-order sensor events in `events.csv` into per-device sessions with a watermark: events that arrive after their session was sealed are reported as late. Read README.md carefully.",
         DOC_SESSIONS, make_sessions, REF_SESSIONS, {"sessions.csv": "csv", "late.csv": "csv"}, alt=ALT_SESSIONS,
         wrong=(rep(REF_SESSIONS, "if any(wm is not None and wm >= s[1] + GAP for s in reach):", "if False:"),
                rep(REF_SESSIONS, "wm >= s[1] + GAP", "wm > s[1] + GAP"),
                rep(REF_SESSIONS, "GAP, DELAY = dt.timedelta(seconds=300), dt.timedelta(seconds=60)", "GAP, DELAY = dt.timedelta(seconds=300), dt.timedelta(seconds=0)"),
                rep(REF_SESSIONS, "reach = [s for s in mine if s[0] - GAP <= t <= s[1] + GAP]", "reach = [s for s in mine if s[0] - GAP < t < s[1] + GAP]"))),
    spec("calendar-rules", 5, "Write `etl.py` that expands the recurring calendar rules in `rules.csv` (daily, weekly with weekdays, monthly with month-end days, counts, until dates, exclusions, time zones) into UTC instances within a date range. Read README.md.",
         DOC_RULES, make_rules, REF_RULES, {"instances.csv": "csv", "summary.csv": "csv"}, alt=ALT_RULES,
         wrong=(rep(REF_RULES, "monday = start - dt.timedelta(days=start.weekday())", "monday = start"),
                rep(REF_RULES, "if limit is not None and seen >= limit:", "if limit is not None and n >= limit:"),
                rep(REF_RULES, "day = md if md > 0 else last + 1 + md", "day = min(md, last) if md > 0 else last + 1 + md"),
                rep(REF_RULES, "tz = ZoneInfo(r[\"tz\"])", "tz = ZoneInfo(\"UTC\")"))),
]


@family("data-etl-experts", category="data", lang="python", kind="feature", n=len(SPECS),
        summary="expert python ETL: watermark-based sessionisation with sealed sessions and late events, recurring calendar rules with Monday weeks, month ends, exclusions and time zones")
def etl_experts(rng, n):
    return E.etl_tasks("etl-experts", SPECS, rng, n, "Streams and calendars")
