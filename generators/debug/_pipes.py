"""Pipeline modules for the data-corruption forensics tasks: the scenario prints a dump after every stage.

``Module.meta["stages"]`` maps a slot to the dump file its stage produces; a defect is usable when the *first* dump that differs
from the correct run is the one of the defective slot's own stage.
"""
from __future__ import annotations

import difflib
import json
import random
import re

from fx import Task, dd, run
from generators.review._slots import Bad, Module, Slot, render, slot_texts, sub, validate_module

from ._engine import KINDS, accepted, hidden_diag

DUMP_HELPER = '''
def _dump(name, rows):
    import csv
    import sys

    cols = list(rows[0]) if rows else []
    for r in rows:
        for c in r:
            if c not in cols:
                cols.append(c)
    print(f"=== dumps/{name} ===")
    w = csv.writer(sys.stdout, lineterminator="\\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get(c, "") for c in cols])
    print("=== end ===")
'''

# ---------------------------------------------------------------------------------------------------------------------
# order import
# ---------------------------------------------------------------------------------------------------------------------

ORDERS_TEMPLATE = dd('''
    """Order import: CSV text -> parsed rows -> amounts in pence -> UTC timestamps -> de-duplicated -> enriched -> daily totals."""
    import csv
    import io
    from datetime import datetime, timedelta
    from decimal import Decimal


    @@parse@@


    @@money@@


    @@utc@@


    @@dedupe@@


    @@enrich@@


    @@daily@@


    def run(text, customers, dump=lambda name, rows: None):
        rows = parse_rows(text)
        dump("1-parsed.csv", rows)
        for r in rows:
            r["amount_pence"] = to_pence(r.pop("amount"))
        dump("2-money.csv", rows)
        for r in rows:
            r["placed_utc"] = to_utc(r.pop("placed_at"), int(r.pop("tz")))
        dump("3-utc.csv", rows)
        rows = dedupe(rows)
        dump("4-deduped.csv", rows)
        rows = enrich(rows, customers)
        dump("5-enriched.csv", rows)
        totals = daily_totals(rows)
        dump("6-daily.csv", [{"day": d, "total_pence": t} for d, t in totals.items()])
        return rows, totals
''')

_O_PARSE = dd('''
    def parse_rows(text):
        """Rows of the order export as dicts (columns order_id, customer, amount, placed_at, tz); fields are stripped, quoted fields may contain commas."""
        reader = csv.DictReader(io.StringIO(text.strip()))
        return [{k.strip(): (v or "").strip() for k, v in row.items()} for row in reader]
''')
_O_MONEY = dd('''
    def to_pence(amount_text):
        """Exact amount in pence as an int: "19.99" -> 1999, "5" -> 500, "-5.25" -> -525."""
        return int((Decimal(amount_text) * 100).to_integral_value())
''')
_O_UTC = dd('''
    def to_utc(placed_at, tz_minutes):
        """"YYYY-MM-DD HH:MM" in local time with a UTC offset in minutes (east positive) -> "YYYY-MM-DDTHH:MM:00Z" in UTC."""
        local = datetime.strptime(placed_at, "%Y-%m-%d %H:%M")
        return (local - timedelta(minutes=tz_minutes)).strftime("%Y-%m-%dT%H:%M:00Z")
''')
_O_DEDUPE = dd('''
    def dedupe(rows):
        """One row per order_id: the last occurrence wins; ids keep the order in which they were first seen."""
        latest = {}
        for r in rows:
            latest[r["order_id"]] = r
        return list(latest.values())
''')
_O_ENRICH = dd('''
    def enrich(rows, customers):
        """Adds `tier` from the customers table (keys are lower-case names); unknown customers are "standard"."""
        return [{**r, "tier": customers.get(r["customer"].lower(), "standard")} for r in rows]
''')
_O_DAILY = dd('''
    def daily_totals(rows):
        """{UTC day: total pence}, days in ascending order."""
        totals = {}
        for r in rows:
            day = r["placed_utc"][:10]
            totals[day] = totals.get(day, 0) + r["amount_pence"]
        return dict(sorted(totals.items()))
''')

ORDERS = Module(
    name="py-orderimport", lang="python", path="ordersync/pipeline.py", difficulty=3, title="", intro="", outro="",
    blurb="The `ordersync` package imports the shop's order export every night and prepares the daily totals for accounting.",
    template=ORDERS_TEMPLATE, ctx={"README.md": "# ordersync\n\nNightly order import: see `ordersync/pipeline.py` (`run` shows the stages in order).\n", "ordersync/__init__.py": ""},
    meta={"stages": {"parse": "1-parsed.csv", "money": "2-money.csv", "utc": "3-utc.csv", "dedupe": "4-deduped.csv", "enrich": "5-enriched.csv", "daily": "6-daily.csv"}},
    scenario=dd('''
        from ordersync.pipeline import run
        ''') + DUMP_HELPER + dd('''

        TEXT = """order_id,customer,amount,placed_at,tz
        1001,Acme Ltd,19.99,2025-03-02 23:30,60
        1002,"Smith, Jones & Co",0.29,2025-03-03 00:15,-300
        1003, acme ltd ,5, 2025-03-03 08:00 ,0
        1004,Birch Bros,1250.50,2025-03-03 23:45,330
        1005,Cedar & Sons,0.07,2025-03-04 02:10,120
        1002,"Smith, Jones & Co",0.31,2025-03-03 00:15,-300
        1006,BIRCH BROS, -5.25 ,2025-03-04 09:00,0
        1007,Acme Ltd,100.10,2025-03-04 22:30,-60
        1008,Cedar & Sons,3,2025-03-05 00:05,60
        """
        CUSTOMERS = {"acme ltd": "gold", "birch bros": "silver", "smith, jones & co": "gold"}
        rows, totals = run(TEXT, CUSTOMERS, _dump)
        print(f"imported {len(rows)} orders, {len(totals)} days")
    '''),
    slots=[
        Slot("parse", "parse_rows", _O_PARSE, [
            Bad(dd('''
                def parse_rows(text):
                    """Rows of the order export as dicts (columns order_id, customer, amount, placed_at, tz); fields are stripped, quoted fields may contain commas."""
                    lines = text.strip().split("\\n")
                    cols = [c.strip() for c in lines[0].split(",")]
                    return [dict(zip(cols, [v.strip() for v in ln.split(",")])) for ln in lines[1:]]
            '''), "logic", "the lines are split on every comma instead of being parsed as CSV, so a quoted field that contains a comma shifts the columns", ("split", "csv", "quoted", "comma"), kind="data-corruption"),
            Bad(sub(_O_PARSE, "return [{k.strip(): (v or \"\").strip() for k, v in row.items()} for row in reader]", "return [{k.strip(): (v or \"\") for k, v in row.items()} for row in reader]"), "logic",
                "the fields are not stripped, so blanks around values survive into the data", ("strip", "whitespace", "blank"), kind="data-corruption"),
            Bad(sub(_O_PARSE, "reader = csv.DictReader(io.StringIO(text.strip()))", "reader = list(csv.DictReader(io.StringIO(text.strip())))[:-1]"), "off-by-one",
                "the last data row is dropped ([:-1])", ("last", "[:-1]", "dropped", "row")),
        ]),
        Slot("money", "to_pence", _O_MONEY, [
            Bad(sub(_O_MONEY, "return int((Decimal(amount_text) * 100).to_integral_value())", "return int(float(amount_text) * 100)"), "api-misuse",
                "binary floating point and int() truncation: 0.29 becomes 28 pence", ("float", "int(", "truncat", "Decimal"), kind="rounding"),
            Bad(sub(_O_MONEY, "return int((Decimal(amount_text) * 100).to_integral_value())", "return int(amount_text.replace(\".\", \"\"))"), "logic",
                "the decimal point is simply deleted, so amounts without decimals (\"5\") are 100 times too small", ("replace", "decimal point", "5", "scale"), kind="data-corruption"),
            Bad(sub(_O_MONEY, "return int((Decimal(amount_text) * 100).to_integral_value())", "return abs(int((Decimal(amount_text) * 100).to_integral_value()))"), "logic",
                "abs() drops the sign, so credit notes become charges", ("abs", "sign", "negative", "credit"), kind="data-corruption"),
        ]),
        Slot("utc", "to_utc", _O_UTC, [
            Bad(_O_UTC.replace("local - timedelta(minutes=tz_minutes)", "local + timedelta(minutes=tz_minutes)"), "logic", "the offset is added instead of subtracted, so every timestamp is moved the wrong way", ("offset", "sign", "+", "timedelta"), kind="timezone"),
            Bad(_O_UTC.replace("local - timedelta(minutes=tz_minutes)", "local"), "logic", "the UTC offset is ignored: local times are labelled Z", ("offset", "ignored", "timezone", "tz"), kind="timezone"),
            Bad(_O_UTC.replace("timedelta(minutes=tz_minutes)", "timedelta(hours=tz_minutes)"), "logic", "the offset in minutes is passed as hours", ("hours", "minutes", "unit", "timedelta"), kind="timezone"),
        ]),
        Slot("dedupe", "dedupe", _O_DEDUPE, [
            Bad(sub(_O_DEDUPE, "latest[r[\"order_id\"]] = r", "latest.setdefault(r[\"order_id\"], r)"), "logic", "the first occurrence wins instead of the last, so corrections of an order are ignored", ("setdefault", "first", "last", "latest"), kind="ordering"),
            Bad(sub(_O_DEDUPE, "latest[r[\"order_id\"]] = r", "latest[(r[\"customer\"], r[\"amount_pence\"])] = r"), "logic", "rows are keyed by customer and amount instead of order_id, which merges different orders that look alike", ("key", "order_id", "customer", "amount"), kind="data-corruption"),
            Bad(dd('''
                def dedupe(rows):
                    """One row per order_id: the last occurrence wins; ids keep the order in which they were first seen."""
                    ids = set(r["order_id"] for r in rows)
                    return [[r for r in rows if r["order_id"] == i][-1] for i in ids]
            '''), "logic", "iterating over a set loses the first-seen order of the ids", ("set", "order", "first-seen"), kind="ordering"),
        ]),
        Slot("enrich", "enrich", _O_ENRICH, [
            Bad(sub(_O_ENRICH, "customers.get(r[\"customer\"].lower(), \"standard\")", "customers.get(r[\"customer\"], \"standard\")"), "logic", "the lookup is not lower-cased, so any customer written with capitals is treated as unknown", ("lower", "case", "lookup", "key"), kind="data-corruption"),
        ]),
        Slot("daily", "daily_totals", _O_DAILY, [
            Bad(sub(_O_DAILY, "totals[day] = totals.get(day, 0) + r[\"amount_pence\"]", "totals[day] = r[\"amount_pence\"]"), "logic", "each row overwrites the day's total instead of adding to it", ("overwrite", "+", "total", "sum"), kind="data-corruption"),
            Bad(sub(_O_DAILY, "return dict(sorted(totals.items()))", "return dict(sorted(totals.items(), key=lambda kv: kv[1]))"), "logic", "days are sorted by total instead of by date", ("sorted", "order", "key", "date"), kind="ordering"),
        ]),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# sensor calibration
# ---------------------------------------------------------------------------------------------------------------------

SENSOR_TEMPLATE = dd('''
    """Sensor frames: hex text -> signed counts -> calibrated values -> moving average -> alerts."""
    from decimal import ROUND_HALF_UP, Decimal


    @@frames@@


    @@decode@@


    @@calibrate@@


    @@smooth@@


    @@alerts@@


    def run(text, cal, window, limits, dump=lambda name, rows: None):
        rows = parse_frames(text)
        dump("1-frames.csv", rows)
        rows = decode(rows)
        dump("2-decoded.csv", rows)
        rows = calibrate(rows, cal)
        dump("3-calibrated.csv", rows)
        rows = smooth(rows, window)
        dump("4-smoothed.csv", rows)
        out = alerts(rows, limits)
        dump("5-alerts.csv", out)
        return rows, out
''')

_S_FRAMES = dd('''
    def parse_frames(text):
        """"<sensor>:<4 hex digits>" per line, in time order -> [{"seq", "sensor", "hex"}] with sensor and hex upper-cased; blank lines and # comments are skipped."""
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            sensor, _, raw = line.partition(":")
            rows.append({"seq": len(rows), "sensor": sensor.strip().upper(), "hex": raw.strip().upper()})
        return rows
''')
_S_DECODE = dd('''
    def decode(rows):
        """The hex word is a big-endian signed 16-bit count (two's complement)."""
        out = []
        for r in rows:
            n = int(r["hex"], 16)
            if n >= 0x8000:
                n -= 0x10000
            out.append({**r, "count": n})
        return out
''')
_S_CAL = dd('''
    def calibrate(rows, cal):
        """value = count * gain + offset with the sensor's (gain, offset) as Decimals, rounded half up to 2 decimals."""
        out = []
        for r in rows:
            gain, offset = cal[r["sensor"]]
            v = (Decimal(r["count"]) * gain + offset).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            out.append({**r, "value": v})
        return out
''')
_S_SMOOTH = dd('''
    def smooth(rows, window):
        """Moving average of `value` per sensor over its last `window` readings (fewer at the start), 2 decimals half up."""
        history = {}
        out = []
        for r in rows:
            h = history.setdefault(r["sensor"], [])
            h.append(r["value"])
            recent = h[-window:]
            avg = (sum(recent) / len(recent)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            out.append({**r, "avg": avg})
        return out
''')
_S_ALERTS = dd('''
    def alerts(rows, limits):
        """Rows whose smoothed value is strictly above the sensor's limit."""
        return [{"seq": r["seq"], "sensor": r["sensor"], "avg": r["avg"], "limit": limits[r["sensor"]]} for r in rows if r["avg"] > limits[r["sensor"]]]
''')

SENSORS = Module(
    name="py-sensorcal", lang="python", path="coldchain/signal.py", difficulty=3, title="", intro="", outro="",
    blurb="The `coldchain` package turns raw sensor frames of refrigerated trucks into calibrated temperatures and alerts.",
    template=SENSOR_TEMPLATE, ctx={"README.md": "# coldchain\n\nSensor pipeline: see `coldchain/signal.py` (`run` shows the stages in order).\n", "coldchain/__init__.py": ""},
    meta={"stages": {"frames": "1-frames.csv", "decode": "2-decoded.csv", "calibrate": "3-calibrated.csv", "smooth": "4-smoothed.csv", "alerts": "5-alerts.csv"}},
    scenario=dd('''
        from decimal import Decimal

        from coldchain.signal import run
        ''') + DUMP_HELPER + dd('''

        TEXT = """# truck 14, afternoon run
        T1:0FA0
        T2:0A28
        T1:0FB4
        T2:FF9C
        t1: 0fc8
        T2:0A3C
        T1:0FDC
        T2:FFB0
        T1:1068
        T2:0A50
        """
        CAL = {"T1": (Decimal("0.01"), Decimal("-35.50")), "T2": (Decimal("0.01"), Decimal("-22.00"))}
        LIMITS = {"T1": Decimal("5.00"), "T2": Decimal("3.50")}
        rows, out = run(TEXT, CAL, 3, LIMITS, _dump)
        print(f"{len(rows)} readings, {len(out)} alerts")
    '''),
    slots=[
        Slot("frames", "parse_frames", _S_FRAMES, [
            Bad(sub(_S_FRAMES, "rows.append({\"seq\": len(rows), \"sensor\": sensor.strip().upper(), \"hex\": raw.strip().upper()})", "rows.append({\"seq\": len(rows), \"sensor\": sensor.strip(), \"hex\": raw.strip().upper()})"), "logic",
                "the sensor name is not upper-cased, so `t1` and `T1` are treated as different sensors (and the calibration lookup fails)", ("upper", "case", "sensor", "t1"), kind="data-corruption"),
            Bad(sub(_S_FRAMES, "\"seq\": len(rows)", "\"seq\": len(rows) + 1"), "off-by-one", "the sequence numbers start at 1 instead of 0 although the alerts refer to row numbers counted from 0", ("seq", "+ 1", "start", "index")),
        ]),
        Slot("decode", "decode", _S_DECODE, [
            Bad(sub(_S_DECODE, "if n >= 0x8000:\nn -= 0x10000", ""), "logic", "the two's complement conversion is missing: negative counts come out as values around 65000", ("signed", "two's complement", "0x8000", "negative"), kind="data-corruption"),
            Bad(_S_DECODE.replace("n = int(r[\"hex\"], 16)", "n = int(r[\"hex\"][2:] + r[\"hex\"][:2], 16)"), "logic", "the two bytes are swapped (little-endian read of a big-endian word)", ("endian", "bytes", "swap", "[2:]"), kind="data-corruption"),
            Bad(_S_DECODE.replace("if n >= 0x8000:", "if n > 0x8000:"), "off-by-one", "the count 0x8000 (-32768) is not converted", (">", "0x8000", "boundary")),
        ]),
        Slot("calibrate", "calibrate", _S_CAL, [
            Bad(_S_CAL.replace("Decimal(r[\"count\"]) * gain + offset", "(Decimal(r[\"count\"]) + offset) * gain"), "logic", "the offset is applied before the gain instead of after it", ("offset", "gain", "order", "precedence"), kind="logic-error"),
            Bad(sub(_S_CAL, "gain, offset = cal[r[\"sensor\"]]", "offset, gain = cal[r[\"sensor\"]]"), "logic", "gain and offset are unpacked in the wrong order", ("gain", "offset", "swap", "unpack"), kind="data-corruption"),
        ]),
        Slot("smooth", "smooth", _S_SMOOTH, [
            Bad(_S_SMOOTH.replace("recent = h[-window:]", "recent = h[-(window - 1):] or h"), "off-by-one", "the window covers window - 1 readings instead of window", ("window", "- 1", "off by one")),
            Bad(dd('''
                def smooth(rows, window):
                    """Moving average of `value` per sensor over its last `window` readings (fewer at the start), 2 decimals half up."""
                    history = []
                    out = []
                    for r in rows:
                        history.append(r["value"])
                        recent = history[-window:]
                        avg = (sum(recent) / len(recent)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        out.append({**r, "avg": avg})
                    return out
            '''), "logic", "a single history is shared by all sensors, so each average mixes readings of different sensors", ("history", "per sensor", "shared", "mix"), kind="state-mutation"),
        ]),
        Slot("alerts", "alerts", _S_ALERTS, [
            Bad(_S_ALERTS.replace("r[\"avg\"] > limits[r[\"sensor\"]]]", "r[\"avg\"] >= limits[r[\"sensor\"]]]"), "off-by-one", "a value exactly at the limit raises an alert although the rule is *strictly above*", (">=", "limit", "strictly", "boundary")),
            Bad(sub(_S_ALERTS, "if r[\"avg\"] > limits[r[\"sensor\"]]]", "if r[\"avg\"] > max(limits.values())]"), "logic", "one global limit (the highest) is used instead of the limit of each sensor", ("limit", "global", "max", "per sensor")),
        ]),
    ],
)

PIPES = [ORDERS, SENSORS]
for _m in PIPES:
    validate_module(_m)


# ---- engine ---------------------------------------------------------------------------------------------------------

_BLOCK = re.compile(r"=== dumps/(\S+) ===\n(.*?)\n=== end ===\n", re.S)


def run_pipe(mod: Module, choice: dict) -> tuple[int, str, dict[str, str], str, dict]:
    head, spans = render(mod.template, slot_texts(mod, choice), mod.lang)
    files = dict(mod.ctx)
    files[mod.path] = head
    files["scenario.py"] = mod.scenario
    r = run(files, "python3 -u scenario.py", timeout=60)
    dumps = {m.group(1): m.group(2) + "\n" for m in _BLOCK.finditer(r.out + ("\n" if not r.out.endswith("\n") else ""))}
    rest = _BLOCK.sub("", r.out + ("\n" if not r.out.endswith("\n") else ""))
    return r.code, rest, dumps, head, spans


def first_diff(good: dict[str, str], bad: dict[str, str]) -> tuple[str, int, int] | None:
    for name in sorted(good):
        if good[name] != bad.get(name):
            a, b = good[name].strip().split("\n"), bad.get(name, "").strip().split("\n")
            sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
            lo = hi = None
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag in ("replace", "insert"):
                    lo = j1 + 1 if lo is None else lo
                    hi = j2
            if lo is None:
                lo = hi = 1
            return name, lo, min(hi, lo + 8)
    return None


def pipe_prompt(rng, mod: Module, stage_files: list[str]) -> str:
    schema = ("Write `diagnosis.json`: an object with exactly these keys: `root_cause_file` (path of the file that contains the defect), `function` (the function that corrupts the data), "
              "`kind` (one of " + ", ".join(KINDS) + "), `evidence_lines` (a list of `path:line` strings: the first corrupted line in the dumps and/or the faulty code) and `fix_summary` (one or two sentences).")
    voices = [
        f"{mod.blurb} Accounting says the numbers coming out of the pipeline are wrong. `scenario.py` replays a sample through every stage and the intermediate result of each stage is saved under `dumps/` (numbered in stage order, with the printed summary in `logs/run.log`). Somewhere between input and output a stage corrupts the data. Find it. {schema}",
        f"Data quality incident. {mod.blurb} The files in `dumps/` are what each stage produced for the sample in `scenario.py`; the final one is wrong and I can't tell where it went off the rails. Which stage is responsible? {schema}",
        f"Please trace this data corruption to its source: the stage dumps are in `dumps/` (`scenario.py` generates them), the code is in the package. The first dump that is wrong tells you the stage. {schema}",
        f"{mod.blurb} A reconciliation job flagged mismatching values. I replayed the sample from `scenario.py` and kept the output of every stage in `dumps/`. Work out which function damages the data. {schema}",
    ]
    return rng.choice(voices)


def pipe_family(mods: list[Module], rng: random.Random, n: int):
    cands = []
    for m in mods:
        c0, o0, d0, _, _ = run_pipe(m, {})
        if c0 != 0:
            raise RuntimeError(f"{m.name}: scenario fails:\n{o0[-1000:]}")
        for s in m.slots:
            for bi in range(len(s.bad)):
                code, out, dumps, head, spans = run_pipe(m, {s.name: ("bad", bi)})
                fd = first_diff(d0, dumps)
                if fd is None or fd[0] != m.meta["stages"][s.name]:
                    continue
                cands.append((m, s, bi, fd))
    rng.shuffle(cands)
    i = 0
    for m, s, bi, fd in cands[:n]:
        i += 1
        bad = s.bad[bi]
        choice = {s.name: ("bad", bi)}
        code, out, dumps, head, spans = run_pipe(m, choice)
        files = dict(m.ctx)
        files[m.path] = head
        files["scenario.py"] = m.scenario
        for name, text in dumps.items():
            files[f"dumps/{name}"] = text
        files["logs/run.log"] = out.strip() + "\n"
        name, lo, hi = fd
        windows = [{"file": m.path, "start": spans[s.name][0], "end": spans[s.name][1]}, {"file": f"dumps/{name}", "start": lo, "end": hi}]
        spec = {"answer_file": "diagnosis.json", "fields": {
            "root_cause_file": {"type": "path", "accept": [m.path]},
            "function": {"type": "name", "accept": [s.func]},
            "kind": {"type": "enum", "allowed": KINDS, "accept": accepted(bad.kind or "data-corruption")},
            "evidence_lines": {"type": "evidence", "windows": windows, "slack": 1},
            "fix_summary": {"type": "text", "min_len": 20, "any": list(bad.kw) + [s.func]},
        }}
        gold = {"root_cause_file": m.path, "function": s.func, "kind": bad.kind or "data-corruption", "evidence_lines": [f"{m.path}:{spans[s.name][0]}", f"dumps/{name}:{lo}"], "fix_summary": bad.why}
        stage_no = int(name.split("-")[0])
        d = max(1, min(5, m.difficulty - 2 + (1 if stage_no >= 2 else 0) + (1 if stage_no >= 4 else 0) + (1 if bad.kind in ("rounding", "timezone", "encoding", "stale-cache") else 0)))
        yield Task(
            slug=f"{i:02d}-{m.name.split('-', 1)[-1]}-{s.name}", prompt=pipe_prompt(rng, m, sorted(dumps)), difficulty=d, kind="fix", lang="python", start=files, hidden=hidden_diag(spec),
            solution={"diagnosis.json": json.dumps(gold, indent=1) + "\n"}, verify="python3 _verify/check.py", pass_mode="json-score", protected=sorted(files), timeout_s=60,
            tags=["data-corruption", "stage-dumps"], notes={"module": m.name, "slot": s.name, "defect": bad.why, "first_bad_dump": name},
        )
