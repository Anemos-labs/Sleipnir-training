"""Three-stage data pipelines specified in PIPELINE.md (parse -> aggregate -> render); one worker per stage."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from fractions import Fraction

from fx import Task, dd, family

from ._kit import GRADE_CMD, score_script, team

THEMES = [
    dict(key="greenhouse", entity="bed", names=["bed1", "bed2", "bed3", "bed4", "bed5", "bed6", "herbs", "seedling"], thing="soil temperature",
         prim="C", alt="F", conv="(num - 32) * 5 / 9", lo=-5, hi=60, thr=35, title="Greenhouse soil temperatures (C)",
         intro="The greenhouse co-op logs soil temperatures from loggers in every bed."),
    dict(key="cellar", entity="rack", names=["r01", "r02", "r03", "r07", "r08", "r12", "annex", "cold"], thing="rack load",
         prim="kg", alt="lb", conv="num * Fraction(45359237, 100000000)", lo=0, hi=400, thr=250, title="Cellar rack loads (kg)",
         intro="A cheese cellar weighs its shelving racks to catch overloading."),
    dict(key="rainfall", entity="gauge", names=["north", "ridge", "mill", "pier", "g4", "g9", "orchard"], thing="rainfall",
         prim="mm", alt="in", conv="num * Fraction(254, 10)", lo=0, hi=500, thr=50, title="Rain gauge totals (mm)",
         intro="Volunteers across the valley read rain gauges and mail in the logger files."),
    dict(key="tanks", entity="tank", names=["t1", "t2", "t3", "t4", "t5", "spare", "header"], thing="tank level",
         prim="cm", alt="in", conv="num * Fraction(254, 100)", lo=0, hi=600, thr=450, title="Water tank levels (cm)",
         intro="The water board's tank sensors report fill levels every few minutes."),
    dict(key="hives", entity="hive", names=["h01", "h02", "h03", "h04", "h05", "h11", "h12", "queenless"], thing="hive weight",
         prim="kg", alt="lb", conv="num * Fraction(45359237, 100000000)", lo=5, hi=120, thr=60, title="Hive weights (kg)",
         intro="A beekeeping club tracks hive weights from platform scales."),
    dict(key="kilns", entity="kiln", names=["k1", "k2", "k3", "bisque", "glaze"], thing="kiln temperature",
         prim="C", alt="F", conv="(num - 32) * 5 / 9", lo=0, hi=1400, thr=1100, title="Kiln temperatures (C)",
         intro="A pottery studio logs thermocouple readings from its kilns."),
]


def round1(x: Fraction) -> Fraction:
    """Round to one decimal, halves away from zero."""
    if x < 0:
        return -round1(-x)
    return Fraction(int(x * 10 + Fraction(1, 2)), 10)


# ------------------------------------------------------------------------------------------------ stage sources
def stage_a_src(th, style, tz):
    ent = th["entity"]
    parse_ts = '''
def _stamp(text):
    m = re.fullmatch(r"([0-9]{4})-([0-9]{2})-([0-9]{2})[T ]([0-9]{2}):([0-9]{2})%s", text)
    if not m:
        return None
    try:
        dt = datetime(*(int(g) for g in m.groups()[:5]))
    except ValueError:
        return None
%s    return dt.strftime("%%Y-%%m-%%dT%%H:%%M")
''' % (("(Z|[+-][0-9]{2}:[0-9]{2})?", '''    off = m.group(6)
    if off and off != "Z":
        sign = 1 if off[0] == "+" else -1
        dt -= sign * timedelta(hours=int(off[1:3]), minutes=int(off[4:6]))
''') if tz else ("", ""))
    if style == "kv":
        parse_line = f'''
def _fields(line):
    pairs = {{}}
    for part in line.split(";"):
        k, sep, v = part.partition("=")
        if not sep:
            return None
        pairs[k.strip()] = v.strip()
    if not {{"ts", "{ent}", "val"}} <= set(pairs):
        return None
    return pairs["ts"], pairs["{ent}"], pairs["val"]
'''
        body = "    cols = None\n"
    elif style == "columns":
        parse_line = f'''
def _fields(line):
    parts = line.split()
    if len(parts) != 4:
        return None
    return parts[0] + "T" + parts[1], parts[2], parts[3]
'''
        body = "    cols = None\n"
    else:
        parse_line = f'''
def _fields(line, cols):
    parts = [p.strip() for p in line.split(",")]
    if len(parts) != len(cols):
        return None
    row = dict(zip(cols, parts))
    return row["when"], row["{ent}"], row["reading"]
'''
        body = "    cols = None\n"
    loop_head = {
        "kv": "        got = _fields(line)\n",
        "columns": "        got = _fields(line)\n",
        "csv": '''        if cols is None:
            cols = [c.strip() for c in line.split(",")]
            if not {"when", "%s", "reading"} <= set(cols):
                return ""
            continue
        got = _fields(line, cols)
''' % ent,
    }[style]
    return f'''"""Stage A: raw {th["thing"]} lines -> JSON lines."""
import json
import re
from datetime import datetime, timedelta
from fractions import Fraction

__all__ = ["transform"]

LO, HI = {th["lo"]}, {th["hi"]}


def _round1(x):
    if x < 0:
        return -_round1(-x)
    return Fraction(int(x * 10 + Fraction(1, 2)), 10)
{parse_ts}
def _value(token):
    m = re.fullmatch(r"(-?[0-9]+(?:\\.[0-9]+)?)([A-Za-z]+)", token)
    if not m:
        return None
    num, unit = Fraction(m.group(1)), m.group(2)
    if unit == "{th["prim"]}":
        v = num
    elif unit == "{th["alt"]}":
        v = {th["conv"]}
    else:
        return None
    v = _round1(v)
    return v if LO <= v <= HI else None
{parse_line}

def transform(text):
    out = []
{body}    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
{loop_head}        if got is None:
            continue
        stamp, entity, token = got
        ts, value = _stamp(stamp), _value(token)
        if ts is None or value is None or not re.fullmatch(r"[A-Za-z0-9_-]+", entity):
            continue
        out.append(json.dumps({{"ts": ts, "entity": entity, "value": float(value)}}, sort_keys=True))
    return "".join(line + "\\n" for line in out)
'''


AGG_DOC = {
    "count": "`count`: the number of readings",
    "min": "`min`: the smallest value",
    "max": "`max`: the largest value",
    "mean": "`mean`: the average value, rounded to one decimal (halves away from zero)",
    "over": "`over`: how many readings are strictly greater than `config[\"threshold\"]`",
    "last": "`last`: the value of the reading with the latest `ts` (if two share a `ts`, the later input line wins)",
}


def stage_b_src(th, group_by, aggs):
    keyexpr = {"entity": 'r["entity"]', "entity+day": 'r["entity"] + "@" + r["ts"][:10]', "day": 'r["ts"][:10]'}[group_by]
    lines = []
    for a in aggs:
        lines.append({
            "count": '        g["count"] = len(rs)',
            "min": '        g["min"] = float(min(vals))',
            "max": '        g["max"] = float(max(vals))',
            "mean": '        g["mean"] = float(_round1(sum(vals) / len(vals)))',
            "over": '        g["over"] = sum(1 for v in vals if v > thr)',
            "last": '        g["last"] = float(Fraction(str(max(enumerate(rs), key=lambda p: (p[1]["ts"], p[0]))[1]["value"])))',
        }[a])
    return f'''"""Stage B: JSON lines -> per-group summary."""
import json
from fractions import Fraction

__all__ = ["transform"]


def _round1(x):
    if x < 0:
        return -_round1(-x)
    return Fraction(int(x * 10 + Fraction(1, 2)), 10)


def transform(text, config):
    thr = Fraction(str(config["threshold"]))
    recs = [json.loads(line) for line in text.splitlines() if line.strip()]
    groups = {{}}
    for r in recs:
        groups.setdefault({keyexpr}, []).append(r)
    out = []
    for key in sorted(groups):
        rs = groups[key]
        vals = [Fraction(str(r["value"])) for r in rs]
        g = {{"key": key}}
{chr(10).join(lines)}
        out.append(g)
    return json.dumps({{"groups": out}}, indent=2, sort_keys=True) + "\\n"
'''


def stage_c_src(th, aggs, sort, footer):
    sortkey = 'g["key"]' if sort == "key" else f'(-g["{aggs[0]}"], g["key"])'
    foot = {
        "total": '    lines.append("total readings: %d" % sum(g["count"] for g in rows))\n',
        "flagged": '    lines.append("flagged groups: %d" % sum(1 for g in rows if g["over"] > 0))\n',
        "none": "",
    }[footer]
    return f'''"""Stage C: summary JSON -> text report."""
import json

__all__ = ["transform"]

TITLE = {th["title"]!r}
COLUMNS = {aggs!r}


def _cell(name, v):
    return ("%d" % v if name in ("count", "over") else "%.1f" % v).rjust(8)


def transform(text):
    rows = sorted(json.loads(text)["groups"], key=lambda g: {sortkey})
    lines = [TITLE]
    if not rows:
        lines.append("(no readings)")
        return "\\n".join(lines) + "\\n"
    width = max(3, max(len(g["key"]) for g in rows))
    lines.append("key".ljust(width) + "".join("  " + c.rjust(8) for c in COLUMNS))
    for g in rows:
        lines.append(g["key"].ljust(width) + "".join("  " + _cell(c, g[c]) for c in COLUMNS))
{foot}    return "\\n".join(lines) + "\\n"
'''


STUB = '''"""{doc}"""

__all__ = ["transform"]


def transform({args}):
    raise NotImplementedError("{what}: see PIPELINE.md")
'''


# ------------------------------------------------------------------------------------------------ data generation
def load(src):
    ns: dict = {}
    exec(compile(src, "<stage>", "exec"), ns)  # our own generated code
    return ns["transform"]


def fmt_num(x: Fraction) -> str:
    s = f"{float(x):.1f}"
    return s


def gen_raw(rng, th, style, tz, n, bad=True):
    ent = th["entity"]
    day0 = datetime(2024, rng.randint(3, 9), rng.randint(1, 20), 0, 0)
    lines, cols = [], None
    if style == "csv":
        order = ["when", ent, "reading"]
        extra = rng.random() < 0.5
        if extra:
            order.insert(rng.randint(0, 3), "note")
        rng.shuffle(order)
        cols = order
        lines.append(",".join(cols))
    for i in range(n):
        t = day0 + timedelta(minutes=rng.randint(0, 3 * 24 * 60))
        e = rng.choice(th["names"])
        unit = rng.choice([th["prim"], th["prim"], th["alt"]])
        if unit == th["prim"]:
            v = Fraction(rng.randint(th["lo"] * 10 - 30, th["hi"] * 10 + 30), 10)
        else:
            lo_alt, hi_alt = (th["lo"] * 2 if th["prim"] in ("C",) else th["lo"]), th["hi"] * 2 + 40
            v = Fraction(rng.randint(int(lo_alt * 10), int(hi_alt * 10)), 10)
        tok = f"{float(v):.1f}{unit}"
        if bad and rng.random() < 0.06:
            tok = f"{float(v):.1f}{rng.choice(['X', 'K', 'm'])}"
        stamp = t.strftime("%Y-%m-%dT%H:%M") if style != "columns" else t.strftime("%Y-%m-%d %H:%M")
        if tz and rng.random() < 0.6:
            off = rng.choice(["Z", "+02:00", "-05:30", "+09:00", "+00:00", "-08:00"])
            stamp += off
        if bad and rng.random() < 0.05:
            stamp = stamp.replace(stamp[5:7], "13", 1)  # impossible month
        if style == "kv":
            line = f"ts={stamp};{ent}={e};val={tok}"
            if rng.random() < 0.3:
                line = f"val={tok} ; {ent}={e} ; ts={stamp}; seq={i}"
        elif style == "columns":
            d, _, rest = stamp.partition(" ")
            line = f"{d} {rest} {e} {tok}"
        else:
            row = {"when": stamp, ent: e, "reading": tok, "note": rng.choice(["ok", "late", "re-read"])}
            line = ",".join(row[c] for c in cols)
        if bad and rng.random() < 0.04:
            line = line.rsplit(";", 1)[0] if style == "kv" else line[: len(line) // 2]
        lines.append(line)
        if bad and rng.random() < 0.05:
            lines.append(rng.choice(["", "# logger restarted", "   ", "# calibration"]))
    return "\n".join(lines) + "\n"


def gen_records(rng, th, n):
    day0 = datetime(2024, rng.randint(3, 9), rng.randint(1, 20), 0, 0)
    out = []
    for _ in range(n):
        t = day0 + timedelta(minutes=rng.randint(0, 3 * 24 * 60))
        v = Fraction(rng.randint(th["lo"] * 10, min(th["hi"], th["thr"] * 2) * 10), 10)
        out.append(json.dumps({"ts": t.strftime("%Y-%m-%dT%H:%M"), "entity": rng.choice(th["names"]), "value": float(v)}, sort_keys=True))
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------------------------------------ docs
def pipeline_md(th, style, tz, group_by, aggs, sort, footer, ex):
    ent, prim, alt = th["entity"], th["prim"], th["alt"]
    lines = [f"# {th['thing'].capitalize()} pipeline", "", th["intro"] + " Raw files become a morning report in three stages. "
             "Each stage is a function `transform` in `pipeline/stage_*.py`; the stages only talk through the formats below, "
             "so they can be written independently. `run_all.py` chains them. All number handling is exact: use decimal or fraction "
             "arithmetic, not binary floats, wherever the text says \"rounded\".", ""]
    lines += ["## Stage A: parse (`pipeline/stage_a.py`, `transform(text) -> str`)", ""]
    lines += ["Input: the raw logger text. Output: one JSON object per valid reading, one per line, in input order, each "
              '`{"entity": str, "ts": "YYYY-MM-DDTHH:MM", "value": number}`.', ""]
    lines += ["Raw lines:", ""]
    if style == "kv":
        lines += [f"* `key=value` pairs separated by `;` (spaces around keys and values are ignored, pairs may come in any order, "
                  f"unknown keys are ignored). Required keys: `ts`, `{ent}`, `val`. A part without `=` makes the line invalid."]
    elif style == "columns":
        lines += [f"* four whitespace-separated columns: `date time {ent} reading`, e.g. `2024-05-03 06:15 {th['names'][0]} 18.4{prim}`. "
                  "Any other column count makes the line invalid."]
    else:
        lines += [f"* CSV without quoting. The first line that is not blank or a comment is the header; it must contain the columns "
                  f"`when`, `{ent}` and `reading` (in any order, extra columns are ignored); if one is missing the whole input "
                  f"produces no output. Data rows split on `,` with spaces around fields ignored; a row with a different number "
                  f"of fields than the header is invalid."]
    lines += ["* Blank lines and lines starting with `#` are skipped. A line that is invalid in any of the ways below is dropped silently.", ""]
    lines += ["A reading is valid when all of these hold:", ""]
    ts_rule = ("a timestamp `YYYY-MM-DD` and `HH:MM`, separated by `T` or a space, that is a real date and time"
               + ("; it may end in `Z` or an offset `+HH:MM` / `-HH:MM`, and the output `ts` is converted to UTC "
                  "(no suffix means the time is already UTC)" if tz else ""))
    lines += [f"* the time is {ts_rule};",
              f"* the entity matches `[A-Za-z0-9_-]+`;",
              f"* the value is a number (optional leading `-`, optional decimals) immediately followed by a unit: `{prim}` is kept, "
              f"`{alt}` is converted to `{prim}`; any other unit is invalid. The converted value is rounded to one decimal "
              f"(halves away from zero) and must then lie between {th['lo']} and {th['hi']} inclusive."]
    lines += ["", "Example:", "", "```", ex["a_in"].rstrip("\n"), "```", "", "gives", "", "```", ex["a_out"].rstrip("\n"), "```", ""]
    lines += ["## Stage B: summarise (`pipeline/stage_b.py`, `transform(text, config) -> str`)", ""]
    gdoc = {"entity": "the `entity` field", "entity+day": "the entity and the UTC day, joined as `ENTITY@YYYY-MM-DD`", "day": "the UTC day `YYYY-MM-DD` (the first ten characters of `ts`)"}[group_by]
    lines += ["Input: the JSON lines of stage A (any order). `config` is the parsed `config.json`. Output: JSON text "
              '`{"groups": [...]}` where each group is an object with a `"key"` and these fields, groups sorted by key '
              f"(plain string order). Readings are grouped by {gdoc}.", ""]
    lines += [f"* {AGG_DOC[a]}" for a in aggs]
    lines += ["", "No readings give `{\"groups\": []}`.", "", "Example (`config = " + json.dumps(ex["config"]) + "`):", "", "```",
              ex["b_in"].rstrip("\n"), "```", "", "gives (parsed JSON; formatting is free)", "", "```", ex["b_out"].rstrip("\n"), "```", ""]
    lines += ["## Stage C: render (`pipeline/stage_c.py`, `transform(text) -> str`)", ""]
    sdoc = "ascending by key" if sort == "key" else f"by `{aggs[0]}` descending, ties by key ascending"
    lines += ["Input: the JSON text of stage B. Output: a plain text report.", ""]
    lines += [f"1. The title line `{th['title']}`.",
              "2. If there are no groups, the single line `(no readings)` follows and nothing else.",
              "3. Otherwise a header line: `key` left-justified to the width of the longest key (at least 3 characters), then for "
              "each column, in this order: " + ", ".join(f"`{a}`" for a in aggs) + " - each preceded by two spaces and right-justified "
              "to 8 characters.",
              f"4. One line per group, sorted {sdoc}, laid out like the header. `count` and `over` are printed as integers, every "
              "other value with exactly one decimal.",
              {"total": "5. A last line `total readings: N` where N is the sum of `count` over all groups.",
               "flagged": "5. A last line `flagged groups: N` where N is how many groups have `over` above zero.",
               "none": "5. Nothing follows the group lines."}[footer],
              "Every line ends with a newline.", ""]
    lines += ["Example:", "", "```", ex["c_in"].rstrip("\n"), "```", "", "gives", "", "```", ex["c_out"].rstrip("\n"), "```", ""]
    lines += ["## Checking your work", "", "`tests/test_examples.py` runs the examples above. They are small; the real inputs are longer and "
              "contain more kinds of bad lines."]
    return "\n".join(lines) + "\n"


EXAMPLE_TEST = '''import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pipeline import stage_a, stage_b, stage_c

A_IN = %(a_in)r
A_OUT = %(a_out)r
B_IN = %(b_in)r
B_OUT = %(b_out)r
C_IN = %(c_in)r
C_OUT = %(c_out)r
CONFIG = %(config)r


class ExampleTests(unittest.TestCase):
    def test_stage_a(self):
        got = [json.loads(x) for x in stage_a.transform(A_IN).splitlines()]
        self.assertEqual(got, [json.loads(x) for x in A_OUT.splitlines()])

    def test_stage_b(self):
        self.assertEqual(json.loads(stage_b.transform(B_IN, CONFIG)), json.loads(B_OUT))

    def test_stage_c(self):
        self.assertEqual(stage_c.transform(C_IN), C_OUT)


if __name__ == "__main__":
    unittest.main()
'''

RUN_ALL = '''"""Run the whole pipeline: python3 run_all.py data/raw.log > report.txt"""
import json
import sys

from pipeline import stage_a, stage_b, stage_c


def build(raw_text, config):
    return stage_c.transform(stage_b.transform(stage_a.transform(raw_text), config))


if __name__ == "__main__":
    with open("config.json", encoding="utf-8") as f:
        cfg = json.load(f)
    with open(sys.argv[1], encoding="utf-8") as f:
        sys.stdout.write(build(f.read(), cfg))
'''

HIDDEN_TEST = '''import json
import os
import sys
import unittest

sys.path.insert(0, os.getcwd())
from pipeline import stage_a, stage_b, stage_c

CASES = json.loads(%(cases)r)


def jl(text):
    return [json.loads(x) for x in text.splitlines() if x.strip()]


class Hidden(unittest.TestCase):
    def test_a(self):
        for c in CASES["a"]:
            self.assertEqual(jl(stage_a.transform(c["in"])), jl(c["out"]))

    def test_b(self):
        for c in CASES["b"]:
            self.assertEqual(json.loads(stage_b.transform(c["in"], c["config"])), json.loads(c["out"]))

    def test_c(self):
        for c in CASES["c"]:
            self.assertEqual(stage_c.transform(c["in"]), c["out"])

    def test_end_to_end(self):
        for c in CASES["e2e"]:
            report = stage_c.transform(stage_b.transform(stage_a.transform(c["raw"]), c["config"]))
            self.assertEqual(report, c["report"])


def main():
    part = sys.argv[1]
    suite = unittest.TestSuite([Hidden("test_" + part)])
    res = unittest.TextTestRunner(stream=sys.stderr, verbosity=0).run(suite)
    sys.exit(0 if res.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
'''


@family("swarm-pipeline-stages", category="swarm", lang="python", kind="feature", n=12,
        summary="a 3-stage parse/aggregate/render pipeline specified by PIPELINE.md; stages are independent, an end-to-end check joins them")
def pipeline_stages(rng, n):
    plan = [
        ("kv", False, "entity", ["count", "max"], "key", "none"),
        ("columns", False, "entity", ["count", "mean", "max"], "key", "total"),
        ("csv", False, "entity", ["min", "max", "mean"], "max", "none"),
        ("kv", True, "entity", ["count", "mean", "over"], "key", "flagged"),
        ("columns", True, "day", ["count", "min", "max"], "key", "total"),
        ("csv", True, "entity+day", ["count", "max", "over"], "over", "flagged"),
        ("kv", False, "entity+day", ["count", "mean", "last"], "key", "total"),
        ("csv", False, "day", ["count", "mean", "over", "max"], "count", "flagged"),
        ("columns", True, "entity", ["last", "min", "max", "mean"], "last", "none"),
        ("kv", True, "entity+day", ["count", "min", "mean", "max", "over"], "mean", "flagged"),
        ("csv", True, "entity", ["count", "mean", "last", "over"], "mean", "flagged"),
        ("columns", False, "day", ["mean", "over", "count"], "mean", "total"),
    ]
    themes = list(THEMES)
    rng.shuffle(themes)
    for i in range(n):
        style, tz, group_by, aggs, sort, footer = plan[i % len(plan)]
        th = themes[i % len(themes)]
        sort_arg = "key" if sort == "key" else "agg"
        if sort_arg == "agg":
            aggs = [sort] + [a for a in aggs if a != sort]
        if footer == "flagged" and "over" not in aggs:
            aggs = aggs + ["over"]
        if footer == "total" and "count" not in aggs:
            aggs = ["count"] + aggs
        cfg = {"threshold": th["thr"], "site": th["key"]}
        A, B, C = stage_a_src(th, style, tz), stage_b_src(th, group_by, aggs), stage_c_src(th, aggs, sort_arg, footer)
        ta, tb, tc = load(A), load(B), load(C)
        # documentation examples
        ex_raw = gen_raw(rng, th, style, tz, 4, bad=False)
        ex_raw = ex_raw.rstrip("\n") + ("\n" + {"kv": "ts=2024-02-30T10:00;%s=%s;val=1.0%s" % (th["entity"], th["names"][0], th["prim"]),
                                               "columns": "2024-02-30 10:00 %s 1.0%s" % (th["names"][0], th["prim"]),
                                               "csv": ""}[style]).rstrip("\n") + "\n"
        ex = {"config": cfg, "a_in": ex_raw, "a_out": ta(ex_raw)}
        ex_recs = gen_records(rng, th, 6)
        ex.update(b_in=ex_recs, b_out=tb(ex_recs, cfg))
        ex.update(c_in=ex["b_out"], c_out=tc(ex["b_out"]))
        md = pipeline_md(th, style, tz, group_by, aggs, sort_arg, footer, ex)
        # hidden cases
        cases = {"a": [], "b": [], "c": [], "e2e": []}
        for sz in (14, 30):
            raw = gen_raw(rng, th, style, tz, sz)
            cases["a"].append({"in": raw, "out": ta(raw)})
        for sz in (12, 40):
            recs = gen_records(rng, th, sz)
            cases["b"].append({"in": recs, "config": cfg, "out": tb(recs, cfg)})
        cases["b"].append({"in": "", "config": cfg, "out": tb("", cfg)})
        for sz in (9, 25):
            recs = gen_records(rng, th, sz)
            summ = tb(recs, cfg)
            cases["c"].append({"in": summ, "out": tc(summ)})
        cases["c"].append({"in": tb("", cfg), "out": tc(tb("", cfg))})
        for sz in (35, 60):
            raw = gen_raw(rng, th, style, tz, sz)
            cases["e2e"].append({"raw": raw, "config": cfg, "report": tc(tb(ta(raw), cfg))})
        if not any(c["out"].strip() for c in cases["a"]):
            raise RuntimeError("empty stage A output")
        start = {
            "PIPELINE.md": md,
            "config.json": json.dumps(cfg, indent=2) + "\n",
            "run_all.py": RUN_ALL,
            "pipeline/__init__.py": "",
            "pipeline/stage_a.py": STUB.format(doc=f"Stage A: raw {th['thing']} lines to JSON lines.", args="text", what="stage A"),
            "pipeline/stage_b.py": STUB.format(doc="Stage B: JSON lines to a per-group summary.", args="text, config", what="stage B"),
            "pipeline/stage_c.py": STUB.format(doc="Stage C: summary JSON to the text report.", args="text", what="stage C"),
            "data/sample_raw.log": ex_raw,
            "tests/test_examples.py": EXAMPLE_TEST % {k: ex[k] for k in ("a_in", "a_out", "b_in", "b_out", "c_in", "c_out", "config")},
        }
        hidden = {".grade/pipeline_cases.py": HIDDEN_TEST % {"cases": json.dumps(cases, sort_keys=True)}}
        units = [{"name": f"stage {s.upper()}", "cmd": ["python3", ".grade/pipeline_cases.py", s], "weight": 1} for s in "abc"]
        units.append({"name": "end to end", "cmd": ["python3", ".grade/pipeline_cases.py", "end_to_end"], "weight": 1})
        hidden[".grade/score.py"] = score_script(units)
        solution = {"pipeline/stage_a.py": A, "pipeline/stage_b.py": B, "pipeline/stage_c.py": C}
        d = 3 + (1 if tz else 0) + (1 if len(aggs) >= 4 and style == "csv" else 0)
        d = min(5, d + (1 if group_by == "entity+day" and tz else 0)) if d < 5 else 5
        prompts = [
            f"{th['intro']} We need the nightly job that turns the raw files into the morning report, and none of it exists yet. "
            f"PIPELINE.md pins down the three stages and the formats between them, so each stage can be written on its own. "
            f"I want all three done and working end to end.",
            f"Three stages, three modules, one spec: PIPELINE.md describes the parse, summarise and render steps for our "
            f"{th['thing']} logs. Everything in pipeline/ is a stub right now. Implement it all; `tests/test_examples.py` runs the "
            f"examples from the spec but the real files are messier.",
            f"Please implement the {th['key']} report pipeline (stage A, B and C in pipeline/, spec in PIPELINE.md). The stages "
            f"are meant to be developed in parallel against the documented formats. When done, `python3 run_all.py data/sample_raw.log` should print the report.",
            f"Ticket: build the {th['thing']} pipeline. Acceptance: (1) stage A parses raw logger files, (2) stage B summarises, "
            f"(3) stage C renders the report, (4) the chain works on a long, messy file. Formats are fixed in PIPELINE.md, follow them exactly.",
        ]
        yield Task(
            slug=f"{i + 1:02d}-{th['key']}-{style}" + ("-tz" if tz else ""),
            prompt=prompts[i % len(prompts)],
            difficulty=d, start=start, hidden=hidden, solution=solution,
            verify=GRADE_CMD, pass_mode="json-score",
            team=team(rng, 3 + (i % 2), ["backend", "tester"] if i % 2 else ["backend", "tester", "docs"]),
            tags=["pipeline", "formats", "stages"],
            notes={"theme": th["key"], "style": style, "tz": tz, "group_by": group_by, "aggs": aggs, "sort": sort_arg, "footer": footer},
        )
