"""meterreads (python): a meter-reading report tool extended with units, JSON, monthly totals, outliers, billing and configuration."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # meterreads

    A small command line tool that turns the cumulative readings of an electricity meter into consumption reports
    (Python 3, standard library only). Run the tests with `python3 -m unittest discover -s tests`.

    ## Layout

    * `meterreads/readings.py`: `Series`, the readings and the consumption between them.
    * `meterreads/cli.py`: the command line (`python -m meterreads ...`).

    ## Readings

    A reading file is CSV with the header line `date,wh` and one line per reading: an ISO date and the meter value in
    watt-hours (a non-negative integer, cumulative). Blank lines are ignored. Dates must strictly increase and the value never
    goes down.

    * `Series.add(day, wh)`, `Series.consumption()` (a list of `(day, used_wh)` for every reading after the first: the
      difference to the previous reading), `Series.total()` (the sum of the consumption), `Series.from_csv(text)`.
      Problems raise `ValueError`; for CSV text the message starts with `line N: ` (N counts lines from 1, the header is line 1).

    ## Command line

    `meterreads report FILE` prints one line per consumption interval, `DATE  USED` (two spaces, the date of the later
    reading, the used watt-hours), then a last line `total  SUM`. Every line ends with a newline.

    `main(argv=None, out=None, err=None, env=None)` returns the exit status: 0 on success, 2 for any problem (a message
    `meterreads: <reason>` goes to `err`; an unreadable file is `cannot read FILE`). `env` is the environment mapping
    (default `os.environ`); nothing reads it yet.
''')

READINGS = '''\
"""Meter readings."""
from datetime import date
@@uniq imports


class Series:
    def __init__(self):
        self._readings = []

    def add(self, day, wh):
        if not isinstance(day, date):
            raise ValueError("day must be a date")
        if not isinstance(wh, int) or isinstance(wh, bool) or wh < 0:
            raise ValueError("wh must be a non-negative integer")
        if self._readings:
            last_day, last_wh = self._readings[-1]
            if day <= last_day:
                raise ValueError("dates must increase")
            if wh < last_wh:
                raise ValueError("the meter cannot run backwards")
        self._readings.append((day, wh))

    def consumption(self):
        return [(d, w - pw) for (_, pw), (d, w) in zip(self._readings, self._readings[1:])]

    def total(self):
        return sum(used for _, used in self.consumption())

    @classmethod
    def from_csv(cls, text):
        series = cls()
        header_seen = False
        for n, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            if not header_seen:
                if line.strip() != "date,wh":
                    raise ValueError(f"line {n}: expected the header date,wh")
                header_seen = True
                continue
            try:
                day_text, wh_text = [p.strip() for p in line.split(",")]
                series.add(date.fromisoformat(day_text), int(wh_text))
            except ValueError as e:
                raise ValueError(f"line {n}: {e}") from None
        if not header_seen:
            raise ValueError("line 1: expected the header date,wh")
        return series

@@blocks functions
'''

CLI = '''\
"""Command line front end."""
import argparse
import os
import sys
@@uniq imports

from .readings import Series

DEFAULTS = {}
@@slot defaults


def resolve(args, layers=()):
    """The final value of every option: the flag, else the first layer that has it, else the built-in default."""
    out = {}
    for key, default in DEFAULTS.items():
        value = getattr(args, key, None)
        if value is None:
            for layer in layers:
                if key in layer:
                    value = layer[key]
                    break
        out[key] = default if value is None else value
    return out


def load_series(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        raise ValueError(f"cannot read {path}") from None
    return Series.from_csv(text)


@@default value_text
def value_text(row, settings):
    return str(row["wh"])
@@end


def render_text(rows, total, settings):
    lines = []
    for row in rows:
        line = f"{row['label']}  {value_text(row, settings)}"
        @@slot line_extra
        lines.append(line + "\\n")
    lines.append(f"total  {value_text({'wh': total}, settings)}\\n")
    return "".join(lines)


def cmd_report(args, settings, out):
    series = load_series(args.file)
    rows = [{"label": d.isoformat(), "wh": used} for d, used in series.consumption()]
    total = series.total()
    @@slot rows_transform
    @@default render
    out.write(render_text(rows, total, settings))
    @@end
    return 0

@@blocks commands

CASTS = {}
@@slot casts


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def build_parser():
    p = _Parser(prog="meterreads", description="Meter reading reports")
    @@slot global_flags
    sub = p.add_subparsers(dest="cmd", required=True)
    rep = sub.add_parser("report", help="consumption per reading interval")
    rep.add_argument("file")
    @@slot report_flags
    @@slot subcommands
    return p


COMMANDS = {"report": cmd_report}
@@slot registry


def main(argv=None, out=None, err=None, env=None):
    out = out if out is not None else sys.stdout
    err = err if err is not None else sys.stderr
    env = env if env is not None else os.environ
    try:
        args = build_parser().parse_args(argv)
        layers = ()
        @@slot layers_build
        settings = resolve(args, layers)
        return COMMANDS[args.cmd](args, settings, out)
    except ValueError as e:
        err.write(f"meterreads: {e}\\n")
        return 2
'''

HELPERS = '''\
import io
import json
import os
import tempfile
import unittest
@@uniq imports

from meterreads import cli
from meterreads.readings import Series

CSV = """date,wh
2025-01-01,10000
2025-01-05,10800
2025-01-20,12300
2025-02-03,12800
2025-02-17,15800
2025-03-01,16000
"""


class CliCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def csv(self, text=CSV):
        return self.write("readings.csv", text)

    def run_cli(self, *argv, env=None):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(list(argv), out=out, err=err, env=env if env is not None else {})
        return code, out.getvalue(), err.getvalue()

'''

VISIBLE = HELPERS + '''
class BasicTests(CliCase):
    def test_consumption(self):
        s = Series.from_csv(CSV)
        self.assertEqual([used for _, used in s.consumption()], [800, 1500, 500, 3000, 200])
        self.assertEqual(s.total(), 6000)

    def test_report(self):
        code, out, err = self.run_cli("report", self.csv())
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, "2025-01-05  800\\n2025-01-20  1500\\n2025-02-03  500\\n2025-02-17  3000\\n2025-03-01  200\\ntotal  6000\\n")

    def test_errors(self):
        code, out, err = self.run_cli("report", os.path.join(self.dir, "nope.csv"))
        self.assertEqual((code, out), (2, ""))
        self.assertTrue(err.startswith("meterreads: cannot read "))
        code, _, err = self.run_cli("report", self.csv("date,wh\\n2025-01-01,5\\n2025-01-02,4\\n"))
        self.assertEqual(code, 2)
        self.assertIn("line 3", err)
    @@blocks tests
'''

HIDDEN = HELPERS + '''
class FeatureTests(CliCase):
    def test_series_rules(self):
        s = Series()
        self.assertEqual((s.consumption(), s.total()), ([], 0))
        from datetime import date
        s.add(date(2025, 1, 1), 100)
        self.assertEqual(s.consumption(), [])
        s.add(date(2025, 1, 2), 100)
        self.assertEqual(s.consumption(), [(date(2025, 1, 2), 0)])
        for bad in ((date(2025, 1, 2), 150), (date(2024, 1, 1), 150), (date(2025, 1, 3), 99), (date(2025, 1, 3), -1), (date(2025, 1, 3), 1.5), ("2025-01-03", 200)):
            with self.assertRaises(ValueError):
                s.add(*bad)
        self.assertEqual(len(s.consumption()), 1)
        for text in ("", "\\n\\n", "day,wh\\n", "date,wh\\n2025-01-01\\n", "date,wh\\n2025-01-01,x\\n", "date,wh\\nnope,5\\n", "date,wh\\n2025-01-01,5\\n2025-01-01,6\\n"):
            with self.assertRaises(ValueError, msg=repr(text)):
                Series.from_csv(text)
        with self.assertRaisesRegex(ValueError, "^line 4: "):
            Series.from_csv("date,wh\\n\\n2025-01-01,5\\n2025-01-02,x\\n")
        self.assertEqual(Series.from_csv("date,wh\\n").total(), 0)

    def test_report_output(self):
        code, out, err = self.run_cli("report", self.csv("date,wh\\n2025-05-01,0\\n"))
        self.assertEqual((code, out, err), (0, "total  0\\n", ""))
        code, out, _ = self.run_cli("report", self.csv("date,wh\\n\\n2025-05-01,10\\n2025-05-09,10\\n2025-05-10,25\\n"))
        self.assertEqual(out, "2025-05-09  0\\n2025-05-10  15\\ntotal  15\\n")
        code, out, err = self.run_cli("report")
        self.assertEqual((code, out), (2, ""))
        self.assertTrue(err.startswith("meterreads: "))
        code, out, err = self.run_cli("explode", "x")
        self.assertEqual((code, out), (2, ""))
    @@blocks tests
'''


def make_slices(rng: random.Random):
    k_out = rng.choice([1.5, 2.0, 2.5])
    S = []

    S.append(Slice(
        id="unit", title="Kilowatt-hour output", d=1,
        pitch=("Nobody reads watt-hour numbers with five digits.",
               "The tariff documents are in kWh, so the report should be too."),
        reqs=("`report --unit {wh,kwh}` (default `wh`) chooses the unit of the printed amounts. With `kwh` every amount, the `total` line included, is the used watt-hours divided by 1000 and written with exactly three decimals, computed with integers (`1500` Wh is `1.500`, `200` Wh is `0.200`, `0` is `0.000`).",
              "Only the printed text changes; the dates and the order stay as they are."),
        code={
            "meterreads/cli.py::defaults": 'DEFAULTS["unit"] = "wh"',
            "meterreads/cli.py::report_flags": 'rep.add_argument("--unit", choices=["wh", "kwh"], default=None, help="unit of the amounts (default wh)")',
            "meterreads/cli.py::value_text": '''
                def value_text(row, settings):
                    wh = row["wh"]
                    if settings["unit"] == "kwh":
                        return f"{wh // 1000}.{wh % 1000:03d}"
                    return str(wh)
            ''',
        },
        readme="## Kilowatt-hour output\n\n`report --unit kwh` prints amounts as kWh with three decimals (integer arithmetic); the default `wh` is unchanged.\n",
        vtests='''
            def test_unit_kwh_basic(self):
                code, out, _ = self.run_cli("report", self.csv(), "--unit", "kwh")
                self.assertTrue(out.endswith("total  6.000\\n"))
        ''',
        tests='''
            def test_unit_kwh(self):
                code, out, err = self.run_cli("report", self.csv(), "--unit", "kwh")
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(out, "2025-01-05  0.800\\n2025-01-20  1.500\\n2025-02-03  0.500\\n2025-02-17  3.000\\n2025-03-01  0.200\\ntotal  6.000\\n")
                code, out, _ = self.run_cli("report", self.csv("date,wh\\n2025-01-01,0\\n2025-01-02,12345\\n2025-01-03,12345\\n"), "--unit", "kwh")
                self.assertEqual(out, "2025-01-02  12.345\\n2025-01-03  0.000\\ntotal  12.345\\n")

            def test_unit_default_and_errors(self):
                _, plain, _ = self.run_cli("report", self.csv())
                _, wh, _ = self.run_cli("report", self.csv(), "--unit", "wh")
                self.assertEqual(plain, wh)
                code, out, err = self.run_cli("report", self.csv(), "--unit", "joules")
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.startswith("meterreads: "))
        ''',
    ))

    S.append(Slice(
        id="json-output", title="JSON output", d=2,
        pitch=("The billing dashboard scrapes the report with a regular expression.",
               "Other programs should be able to read the report without parsing text."),
        reqs=("`report --format {text,json}` (default `text`) selects the output. `json` prints one JSON document followed by a newline: an object with `rows` (a list of objects with `label` (the date) and `wh` (the used watt-hours as an integer), in report order) and `total` (the sum, an integer).",
              "The JSON always uses integer watt-hours, whatever other display options exist."),
        code={
            "meterreads/cli.py::imports": "import json",
            "meterreads/cli.py::defaults": 'DEFAULTS["format"] = "text"',
            "meterreads/cli.py::report_flags": 'rep.add_argument("--format", choices=["text", "json"], default=None, help="output format (default text)")',
            "meterreads/cli.py::commands": '''
                def row_json(row):
                    @@default row_json_body
                    return {"label": row["label"], "wh": row["wh"]}
                    @@end
            ''',
            "meterreads/cli.py::render": '''
                if settings["format"] == "json":
                    out.write(json.dumps({"rows": [row_json(r) for r in rows], "total": total}) + "\\n")
                else:
                    out.write(render_text(rows, total, settings))
            ''',
        },
        readme="## JSON output\n\n`report --format json` prints `{\"rows\": [{\"label\", \"wh\"}...], \"total\": N}` with integer watt-hours.\n",
        vtests='''
            def test_json_basic(self):
                code, out, _ = self.run_cli("report", self.csv(), "--format", "json")
                self.assertEqual(json.loads(out)["total"], 6000)
        ''',
        tests='''
            def test_json_document(self):
                code, out, err = self.run_cli("report", self.csv(), "--format", "json")
                self.assertEqual((code, err), (0, ""))
                self.assertTrue(out.endswith("\\n") and out.count("\\n") == 1)
                data = json.loads(out)
                self.assertEqual(data["total"], 6000)
                self.assertEqual([(r["label"], r["wh"]) for r in data["rows"]], [("2025-01-05", 800), ("2025-01-20", 1500), ("2025-02-03", 500), ("2025-02-17", 3000), ("2025-03-01", 200)])
                self.assertIsInstance(data["total"], int)
                self.assertIsInstance(data["rows"][0]["wh"], int)
                code, out, _ = self.run_cli("report", self.csv("date,wh\\n2025-01-01,5\\n"), "--format", "json")
                self.assertEqual(json.loads(out), {"rows": [], "total": 0})

            def test_text_is_still_the_default(self):
                _, a, _ = self.run_cli("report", self.csv())
                _, b, _ = self.run_cli("report", self.csv(), "--format", "text")
                self.assertEqual(a, b)
                code, out, err = self.run_cli("report", self.csv(), "--format", "xml")
                self.assertEqual((code, out), (2, ""))
        ''',
        cross={
            "unit": {
                "reqs": ("`--unit` does not affect JSON output.",),
                "tests": '''
                    def test_json_ignores_unit(self):
                        _, a, _ = self.run_cli("report", self.csv(), "--format", "json")
                        _, b, _ = self.run_cli("report", self.csv(), "--format", "json", "--unit", "kwh")
                        self.assertEqual(a, b)
                '''},
        },
    ))

    S.append(Slice(
        id="monthly", title="Monthly totals", d=2,
        pitch=("Per-interval lines are too fine-grained for the monthly review.",
               "Management wants one line per calendar month."),
        reqs=("`report --by {reading,month}` (default `reading`, today's behaviour) chooses the grouping. With `month`, the intervals are added up per calendar month of their date (the date of the later reading): one line `YYYY-MM  USED` per month that has at least one interval, in date order, then the `total` line as before.",),
        code={
            "meterreads/cli.py::defaults": 'DEFAULTS["by"] = "reading"',
            "meterreads/cli.py::report_flags": 'rep.add_argument("--by", choices=["reading", "month"], default=None, help="group the intervals (default reading)")',
            "meterreads/cli.py::rows_transform": '''
                if settings["by"] == "month":
                    months = {}
                    for r in rows:
                        months[r["label"][:7]] = months.get(r["label"][:7], 0) + r["wh"]
                    rows = [{"label": k, "wh": v} for k, v in sorted(months.items())]
            ''',
        },
        readme="## Monthly totals\n\n`report --by month` adds the intervals up per calendar month (`YYYY-MM  USED`); `--by reading` is the default.\n",
        vtests='''
            def test_monthly_basic(self):
                code, out, _ = self.run_cli("report", self.csv(), "--by", "month")
                self.assertTrue(out.startswith("2025-01  2300\\n"))
        ''',
        tests='''
            def test_monthly_totals(self):
                code, out, err = self.run_cli("report", self.csv(), "--by", "month")
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(out, "2025-01  2300\\n2025-02  3500\\n2025-03  200\\ntotal  6000\\n")
                code, out, _ = self.run_cli("report", self.csv("date,wh\\n2024-12-30,0\\n2025-01-02,10\\n2025-02-01,40\\n2025-02-02,41\\n"), "--by", "month")
                self.assertEqual(out, "2025-01  10\\n2025-02  31\\ntotal  41\\n")
                code, out, _ = self.run_cli("report", self.csv("date,wh\\n2025-01-01,5\\n"), "--by", "month")
                self.assertEqual(out, "total  0\\n")

            def test_by_reading_is_the_default(self):
                _, a, _ = self.run_cli("report", self.csv())
                _, b, _ = self.run_cli("report", self.csv(), "--by", "reading")
                self.assertEqual(a, b)
                code, out, _ = self.run_cli("report", self.csv(), "--by", "week")
                self.assertEqual((code, out), (2, ""))
        ''',
        cross={
            "unit": {"tests": '''
                def test_monthly_in_kwh(self):
                    _, out, _ = self.run_cli("report", self.csv(), "--by", "month", "--unit", "kwh")
                    self.assertEqual(out, "2025-01  2.300\\n2025-02  3.500\\n2025-03  0.200\\ntotal  6.000\\n")
            '''},
            "json-output": {
                "reqs": ("In JSON output the `label` of a row is the month (`YYYY-MM`) when `--by month` is used.",),
                "tests": '''
                    def test_monthly_json(self):
                        _, out, _ = self.run_cli("report", self.csv(), "--by", "month", "--format", "json")
                        self.assertEqual([(r["label"], r["wh"]) for r in json.loads(out)["rows"]], [("2025-01", 2300), ("2025-02", 3500), ("2025-03", 200)])
                '''},
        },
    ))

    # expected text of the outlier slice for the default sample (rows 800, 1500, 500, 3000, 200; median 800)
    sample = [("2025-01-05", 800), ("2025-01-20", 1500), ("2025-02-03", 500), ("2025-02-17", 3000), ("2025-03-01", 200)]
    flagged_text = "".join(f"{d}  {v}" + ("  !" if v > k_out * 800 else "") + "\n" for d, v in sample) + "total  6000\n"

    S.append(Slice(
        id="outliers", title="Outlier flags", d=3,
        pitch=("A stuck meter or a leak shows up as one huge interval and people miss it in a long list.",
               "Analysts want unusually high intervals marked."),
        reqs=(f"`report --flag-outliers K` (a number greater than 0; anything else is an error with exit status 2; off by default) marks the rows whose amount is strictly greater than `K` times the median of the amounts of the rows that are shown. For an even number of rows the median is the mean of the two middle amounts; with no rows nothing is marked.",
              "In text output a marked row gets two spaces and `!` appended to its line (`2025-02-17  3000  !`). The `total` line is never marked. Nothing changes for rows that are not marked."),
        code={
            "meterreads/cli.py::imports": "import statistics",
            "meterreads/cli.py::defaults": 'DEFAULTS["flag_outliers"] = None',
            "meterreads/cli.py::report_flags": 'rep.add_argument("--flag-outliers", dest="flag_outliers", type=float, default=None, help="mark rows above K times the median")',
            "meterreads/cli.py::rows_transform": '''
                k = settings["flag_outliers"]
                if k is not None:
                    if k <= 0:
                        raise ValueError("--flag-outliers needs a number greater than 0")
                    if rows:
                        median = statistics.median(r["wh"] for r in rows)
                        for r in rows:
                            r["outlier"] = r["wh"] > k * median
            ''',
            "meterreads/cli.py::line_extra": '''
                if row.get("outlier"):
                    line += "  !"
            ''',
        },
        readme="## Outlier flags\n\n`report --flag-outliers K` marks rows above `K` times the median of the shown rows with a trailing `  !`.\n",
        vtests='''
            def test_outliers_basic(self):
                code, out, _ = self.run_cli("report", self.csv(), "--flag-outliers", "2")
                self.assertIn("2025-02-17  3000  !\\n", out)
        ''',
        tests=fmt('''
            def test_outliers_are_flagged(self):
                code, out, err = self.run_cli("report", self.csv(), "--flag-outliers", "__K__")
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(out, __EXPECTED__)
                _, plain, _ = self.run_cli("report", self.csv())
                self.assertEqual(out.replace("  !", ""), plain)

            def test_outlier_threshold_is_strict(self):
                data = "date,wh\\n2025-01-01,0\\n2025-01-02,10\\n2025-01-03,20\\n2025-01-04,40\\n"
                code, out, _ = self.run_cli("report", self.csv(data), "--flag-outliers", "2")
                self.assertEqual(out, "2025-01-02  10\\n2025-01-03  10\\n2025-01-04  20\\ntotal  40\\n")
                data = "date,wh\\n2025-01-01,0\\n2025-01-02,10\\n2025-01-03,20\\n2025-01-04,41\\n"
                code, out, _ = self.run_cli("report", self.csv(data), "--flag-outliers", "2")
                self.assertEqual(out, "2025-01-02  10\\n2025-01-03  10\\n2025-01-04  21  !\\ntotal  41\\n")
                data = "date,wh\\n2025-01-01,0\\n2025-01-02,10\\n2025-01-03,30\\n"
                code, out, _ = self.run_cli("report", self.csv(data), "--flag-outliers", "1.2")
                self.assertEqual(out, "2025-01-02  10\\n2025-01-03  20  !\\ntotal  30\\n")

            def test_outlier_errors_and_empty(self):
                for bad in ("0", "-1", "abc"):
                    code, out, err = self.run_cli("report", self.csv(), "--flag-outliers", bad)
                    self.assertEqual((code, out), (2, ""), bad)
                    self.assertTrue(err.startswith("meterreads: "))
                code, out, _ = self.run_cli("report", self.csv("date,wh\\n2025-01-01,5\\n"), "--flag-outliers", "2")
                self.assertEqual(out, "total  0\\n")
        ''', K=k_out, EXPECTED=repr(flagged_text)),
        cross={
            "monthly": {
                "reqs": ("With `--by month` the median is taken over the monthly rows that are shown.",),
                "tests": '''
                    def test_outliers_use_the_shown_rows(self):
                        code, out, _ = self.run_cli("report", self.csv(), "--by", "month", "--flag-outliers", "1.5")
                        self.assertEqual(out, "2025-01  2300\\n2025-02  3500  !\\n2025-03  200\\ntotal  6000\\n")
                '''},
            "unit": {"tests": '''
                def test_outlier_mark_follows_unit(self):
                    code, out, _ = self.run_cli("report", self.csv(), "--unit", "kwh", "--flag-outliers", "3")
                    self.assertIn("2025-02-17  3.000  !\\n", out)
                    self.assertTrue(out.endswith("total  6.000\\n"))
            '''},
            "json-output": {
                "reqs": ("In JSON output every row gets an `outlier` boolean when `--flag-outliers` is given (and has no such key otherwise).",),
                "code": {"meterreads/cli.py::row_json_body": '''
                    d = {"label": row["label"], "wh": row["wh"]}
                    if "outlier" in row:
                        d["outlier"] = row["outlier"]
                    return d
                '''},
                "tests": '''
                    def test_json_outlier_flags(self):
                        _, out, _ = self.run_cli("report", self.csv(), "--format", "json", "--flag-outliers", "2")
                        rows = json.loads(out)["rows"]
                        self.assertEqual([r["outlier"] for r in rows], [False, False, False, True, False])
                        _, out, _ = self.run_cli("report", self.csv(), "--format", "json")
                        self.assertNotIn("outlier", json.loads(out)["rows"][0])
                '''},
        },
    ))

    S.append(Slice(
        id="bill", title="Billing command", d=3,
        pitch=("Customer service wants to quote the bill for a reading file with the tiered tariff.",
               "The tool should turn consumption into money using the utility's tiered rates."),
        reqs=("New command `meterreads bill FILE --tiers SPEC` prints the bill per calendar month: one line `YYYY-MM  CENTS` for every month that has at least one interval (the month of the later reading's date), in date order, then `total  CENTS` (the sum of the monthly amounts). Without `--tiers` the command fails with exit status 2.",
              "`SPEC` is a comma-separated list of `SIZE:RATE` tiers. `SIZE` is a positive whole number of kWh and `RATE` the price in cents per kWh (a whole number, 0 or more); the last tier must be `*:RATE` (unbounded), and `*` is not allowed anywhere else. A month's consumption is split over the tiers in order (the first `SIZE` kWh of that month at the first rate, the next ones at the second, ...). The month's cost in cents is the sum of `watt-hours * RATE` over the tiers divided by 1000 and rounded to the nearest cent, halves up: `(sum + 500) // 1000`. A bad spec is an error with exit status 2."),
        code={
            "meterreads/cli.py::defaults": 'DEFAULTS["tiers"] = None',
            "meterreads/cli.py::commands": '''
                def parse_tiers(spec):
                    parts = [p.strip() for p in spec.split(",")]
                    tiers = []
                    for i, part in enumerate(parts):
                        size, sep, rate = part.partition(":")
                        if not sep:
                            raise ValueError(f"bad tier: {part!r}")
                        last = i == len(parts) - 1
                        if size.strip() == "*":
                            if not last:
                                raise ValueError("'*' must be the last tier")
                            limit = None
                        else:
                            if last:
                                raise ValueError("the last tier must be '*:RATE'")
                            limit = int(size)
                            if limit < 1:
                                raise ValueError("tier sizes must be positive")
                        cents = int(rate)
                        if cents < 0:
                            raise ValueError("rates must not be negative")
                        tiers.append((limit, cents))
                    return tiers


                def bill_cents(wh, tiers):
                    total, left = 0, wh
                    for limit, rate in tiers:
                        take = left if limit is None else min(left, limit * 1000)
                        total += take * rate
                        left -= take
                    return (total + 500) // 1000


                def cmd_bill(args, settings, out):
                    if settings["tiers"] is None:
                        raise ValueError("--tiers is required")
                    tiers = parse_tiers(settings["tiers"])
                    months = {}
                    for d, used in load_series(args.file).consumption():
                        months[d.isoformat()[:7]] = months.get(d.isoformat()[:7], 0) + used
                    lines, total = [], 0
                    for month, wh in sorted(months.items()):
                        cents = bill_cents(wh, tiers)
                        total += cents
                        lines.append(f"{month}  {cents}\\n")
                    lines.append(f"total  {total}\\n")
                    out.write("".join(lines))
                    return 0
            ''',
            "meterreads/cli.py::subcommands": '''
                bill = sub.add_parser("bill", help="monthly bill from tiered rates")
                bill.add_argument("file")
                bill.add_argument("--tiers", default=None, help="tiers such as 100:30,*:20 (kWh per month : cents per kWh)")
            ''',
            "meterreads/cli.py::registry": 'COMMANDS["bill"] = cmd_bill',
        },
        readme="## Billing command\n\n`meterreads bill FILE --tiers 1:25,*:12` prices each month's consumption in tiers (`SIZE` kWh at `RATE` cents, the last tier `*`), rounded half up per month.\n",
        vtests='''
            def test_bill_basic(self):
                code, out, _ = self.run_cli("bill", self.csv(), "--tiers", "*:30")
                self.assertTrue(out.endswith("total  180\\n"))
        ''',
        tests='''
            def test_bill_tiers(self):
                code, out, err = self.run_cli("bill", self.csv(), "--tiers", "1:25,*:12")
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(out, "2025-01  41\\n2025-02  55\\n2025-03  5\\ntotal  101\\n")
                code, out, _ = self.run_cli("bill", self.csv(), "--tiers", "1:25,2:20,*:10")
                self.assertEqual(out, "2025-01  51\\n2025-02  70\\n2025-03  5\\ntotal  126\\n")
                code, out, _ = self.run_cli("bill", self.csv(), "--tiers", "*:30")
                self.assertEqual(out, "2025-01  69\\n2025-02  105\\n2025-03  6\\ntotal  180\\n")
                code, out, _ = self.run_cli("bill", self.csv(), "--tiers", " 1 : 25 , * : 12 ")
                self.assertEqual(code, 0)

            def test_bill_rounding_and_empty(self):
                data = "date,wh\\n2025-01-01,0\\n2025-01-09,100\\n2025-02-01,300\\n"
                code, out, _ = self.run_cli("bill", self.csv(data), "--tiers", "*:5")
                self.assertEqual(out, "2025-01  1\\n2025-02  1\\ntotal  2\\n")
                data = "date,wh\\n2025-01-01,0\\n2025-01-09,99\\n"
                code, out, _ = self.run_cli("bill", self.csv(data), "--tiers", "*:5")
                self.assertEqual(out, "2025-01  0\\ntotal  0\\n")
                code, out, _ = self.run_cli("bill", self.csv("date,wh\\n2025-01-01,0\\n"), "--tiers", "*:5")
                self.assertEqual((code, out), (0, "total  0\\n"))

            def test_bill_errors(self):
                code, out, err = self.run_cli("bill", self.csv())
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.startswith("meterreads: "))
                for bad in ("25", "1:25", "*:12,1:25", "x:5,*:1", "0:5,*:1", "1:-5,*:1", "1:5,,*:1", "", "1:5,*", "*:x"):
                    code, out, err = self.run_cli("bill", self.csv(), "--tiers", bad)
                    self.assertEqual((code, out), (2, ""), repr(bad))
                    self.assertTrue(err.startswith("meterreads: "), repr(bad))
        ''',
    ))

    S.append(Slice(
        id="config", title="Settings file and environment", d=4, needs=("unit",),
        pitch=("Everyone types the same flags every day; the team wants defaults in a file, and the cron job wants environment variables.",
               "Options should be settable from the environment and from a settings file, not only from flags."),
        reqs=("Every option of the tool can also come from the environment and from a settings file. For each option `NAME` (the long flag without the dashes, with underscores for dashes, e.g. `unit` or `flag_outliers`) the value is the first one found in this order: the command line flag; the environment variable `METERREADS_` plus the upper-case name (`METERREADS_UNIT`); the key `NAME` in the `[meterreads]` section of the settings file; the built-in default. `main(..., env=...)` supplies the environment mapping.",
              "`--config PATH` (a flag before the command: `meterreads --config PATH report ...`) names an INI settings file; if it does not exist it is an error (exit status 2). Without it the file `meterreads.ini` in the current directory is used when it exists and ignored when it does not. A settings file without a `[meterreads]` section simply sets nothing; unknown keys and unknown environment variables are ignored.",
              "A value from the environment or the file that is not valid for its option (an unknown unit, a number that is not a number) is an error with exit status 2, and the message names the environment variable or the file key. Values are checked in the same way as the flag would be."),
        code={
            "meterreads/cli.py::imports": "import configparser",
            "meterreads/cli.py::global_flags": 'p.add_argument("--config", default=None, help="settings file (default: meterreads.ini in the current directory, if present)")',
            "meterreads/cli.py::commands": '''
                def choice(*names):
                    def cast(text):
                        if text not in names:
                            raise ValueError("must be one of " + ", ".join(names))
                        return text

                    return cast


                def _cast(key, cast, raw, where):
                    try:
                        return cast(raw)
                    except (ValueError, TypeError) as e:
                        raise ValueError(f"bad value for {key} in {where}: {e}") from None


                def load_layers(args, env):
                    env_layer = {}
                    for key, cast in CASTS.items():
                        name = "METERREADS_" + key.upper()
                        if name in env:
                            env_layer[key] = _cast(key, cast, env[name], name)
                    file_layer = {}
                    explicit = args.config is not None
                    path = args.config if explicit else "meterreads.ini"
                    if explicit or os.path.exists(path):
                        parser = configparser.ConfigParser()
                        try:
                            read = parser.read(path, encoding="utf-8")
                        except configparser.Error as e:
                            raise ValueError(f"bad settings file {path}: {e}") from None
                        if explicit and not read:
                            raise ValueError(f"cannot read {path}")
                        if parser.has_section("meterreads"):
                            for key, cast in CASTS.items():
                                if parser.has_option("meterreads", key):
                                    file_layer[key] = _cast(key, cast, parser.get("meterreads", key), path)
                    return [env_layer, file_layer]
            ''',
            "meterreads/cli.py::layers_build": "layers = load_layers(args, env)",
        },
        readme=dd('''
            ## Settings file and environment

            Each option `NAME` is resolved as: flag, then environment variable `METERREADS_NAME`, then the key `NAME` in the
            `[meterreads]` section of the INI file given with `--config PATH` (default `meterreads.ini` in the current directory if it
            exists), then the built-in default. Invalid values are errors (exit status 2) naming where they came from.
        '''),
        vtests='''
            def test_config_basic(self):
                code, out, _ = self.run_cli("report", self.csv(), env={"METERREADS_UNIT": "kwh"})
                self.assertEqual(code, 0)
        ''',
        tests='''
            def test_precedence_flag_env_file_default(self):
                cfg = self.write("m.ini", "[meterreads]\\nunit = kwh\\n")
                code, out, _ = self.run_cli("--config", cfg, "report", self.csv())
                self.assertTrue(out.endswith("total  6.000\\n"))
                code, out, _ = self.run_cli("--config", cfg, "report", self.csv(), env={"METERREADS_UNIT": "wh"})
                self.assertTrue(out.endswith("total  6000\\n"))
                code, out, _ = self.run_cli("--config", cfg, "report", self.csv(), "--unit", "kwh", env={"METERREADS_UNIT": "wh"})
                self.assertTrue(out.endswith("total  6.000\\n"))
                other = self.write("o.ini", "[meterreads]\\nunit = kwh\\n")
                code, out, _ = self.run_cli("--config", other, "report", self.csv(), "--unit", "wh")
                self.assertTrue(out.endswith("total  6000\\n"))
                code, out, _ = self.run_cli("report", self.csv(), env={"METERREADS_UNIT": "kwh"})
                self.assertTrue(out.endswith("total  6.000\\n"))
                code, out, _ = self.run_cli("report", self.csv(), env={"OTHER": "x", "METERREADS_COLOUR": "red"})
                self.assertTrue(out.endswith("total  6000\\n"))

            def test_config_file_handling(self):
                empty = self.write("e.ini", "")
                code, out, _ = self.run_cli("--config", empty, "report", self.csv())
                self.assertEqual(code, 0)
                other = self.write("x.ini", "[other]\\nunit = kwh\\n")
                code, out, _ = self.run_cli("--config", other, "report", self.csv())
                self.assertTrue(out.endswith("total  6000\\n"))
                unknown = self.write("u.ini", "[meterreads]\\ncolour = red\\nunit = kwh\\n")
                code, out, _ = self.run_cli("--config", unknown, "report", self.csv())
                self.assertTrue(out.endswith("total  6.000\\n"))
                code, out, err = self.run_cli("--config", os.path.join(self.dir, "missing.ini"), "report", self.csv())
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.startswith("meterreads: "))
                broken = self.write("b.ini", "this is not an ini file\\n")
                code, out, err = self.run_cli("--config", broken, "report", self.csv())
                self.assertEqual((code, out), (2, ""))

            def test_default_settings_file_is_read_from_the_working_directory(self):
                self.write("meterreads.ini", "[meterreads]\\nunit = kwh\\n")
                old = os.getcwd()
                os.chdir(self.dir)
                self.addCleanup(os.chdir, old)
                code, out, _ = self.run_cli("report", self.csv())
                self.assertTrue(out.endswith("total  6.000\\n"))
                os.remove("meterreads.ini")
                code, out, _ = self.run_cli("report", self.csv())
                self.assertTrue(out.endswith("total  6000\\n"))

            def test_invalid_values_name_their_source(self):
                code, out, err = self.run_cli("report", self.csv(), env={"METERREADS_UNIT": "furlong"})
                self.assertEqual((code, out), (2, ""))
                self.assertIn("METERREADS_UNIT", err)
                cfg = self.write("bad.ini", "[meterreads]\\nunit = furlong\\n")
                code, out, err = self.run_cli("--config", cfg, "report", self.csv())
                self.assertEqual((code, out), (2, ""))
                self.assertIn("unit", err)
                code, out, _ = self.run_cli("--config", cfg, "report", self.csv(), env={"METERREADS_UNIT": "kwh"})
                self.assertEqual(code, 2)
        ''',
        cross={
            "json-output": {
                "reqs": ("The option `format` can be set as `METERREADS_FORMAT` or `format` in the settings file (`text` or `json`).",),
                "code": {"meterreads/cli.py::casts": 'CASTS["format"] = choice("text", "json")'},
                "tests": '''
                    def test_format_from_environment_and_file(self):
                        _, out, _ = self.run_cli("report", self.csv(), env={"METERREADS_FORMAT": "json"})
                        self.assertEqual(json.loads(out)["total"], 6000)
                        cfg = self.write("f.ini", "[meterreads]\\nformat = json\\n")
                        _, out, _ = self.run_cli("--config", cfg, "report", self.csv())
                        self.assertEqual(json.loads(out)["total"], 6000)
                        _, out, _ = self.run_cli("--config", cfg, "report", self.csv(), "--format", "text")
                        self.assertTrue(out.endswith("total  6000\\n"))
                        code, _, err = self.run_cli("report", self.csv(), env={"METERREADS_FORMAT": "yaml"})
                        self.assertEqual(code, 2)
                '''},
            "monthly": {
                "reqs": ("The option `by` can be set as `METERREADS_BY` or `by` in the settings file (`reading` or `month`).",),
                "code": {"meterreads/cli.py::casts": 'CASTS["by"] = choice("reading", "month")'},
                "tests": '''
                    def test_by_from_environment_and_file(self):
                        _, out, _ = self.run_cli("report", self.csv(), env={"METERREADS_BY": "month"})
                        self.assertTrue(out.startswith("2025-01  2300\\n"))
                        cfg = self.write("b.ini", "[meterreads]\\nby = month\\n")
                        _, out, _ = self.run_cli("--config", cfg, "report", self.csv(), "--by", "reading")
                        self.assertTrue(out.startswith("2025-01-05  800\\n"))
                        code, _, _ = self.run_cli("report", self.csv(), env={"METERREADS_BY": "week"})
                        self.assertEqual(code, 2)
                '''},
            "outliers": {
                "reqs": ("The option `flag_outliers` can be set as `METERREADS_FLAG_OUTLIERS` or `flag_outliers` in the settings file (a number).",),
                "code": {"meterreads/cli.py::casts": 'CASTS["flag_outliers"] = float'},
                "tests": '''
                    def test_outlier_factor_from_environment_and_file(self):
                        _, out, _ = self.run_cli("report", self.csv(), env={"METERREADS_FLAG_OUTLIERS": "2"})
                        self.assertIn("2025-02-17  3000  !\\n", out)
                        cfg = self.write("o.ini", "[meterreads]\\nflag_outliers = 2\\n")
                        _, out, _ = self.run_cli("--config", cfg, "report", self.csv())
                        self.assertIn("2025-02-17  3000  !\\n", out)
                        code, _, err = self.run_cli("report", self.csv(), env={"METERREADS_FLAG_OUTLIERS": "lots"})
                        self.assertEqual(code, 2)
                        self.assertIn("METERREADS_FLAG_OUTLIERS", err)
                '''},
            "bill": {
                "reqs": ("The option `tiers` of `bill` can be set as `METERREADS_TIERS` or `tiers` in the settings file; with a value from there `--tiers` can be left out.",),
                "code": {"meterreads/cli.py::casts": 'CASTS["tiers"] = str'},
                "tests": '''
                    def test_tiers_from_environment_and_file(self):
                        code, out, _ = self.run_cli("bill", self.csv(), env={"METERREADS_TIERS": "*:30"})
                        self.assertEqual(out, "2025-01  69\\n2025-02  105\\n2025-03  6\\ntotal  180\\n")
                        cfg = self.write("t.ini", "[meterreads]\\ntiers = 1:25,*:12\\n")
                        code, out, _ = self.run_cli("--config", cfg, "bill", self.csv())
                        self.assertTrue(out.endswith("total  101\\n"))
                        code, out, _ = self.run_cli("--config", cfg, "bill", self.csv(), "--tiers", "*:30")
                        self.assertTrue(out.endswith("total  180\\n"))
                '''},
            "unit": {
                "code": {"meterreads/cli.py::casts": 'CASTS["unit"] = choice("wh", "kwh")'},
            },
        },
    ))

    return S


APP = App(
    name="meterreads", lang="python", title="the meter report tool", role="a utility analyst", key="METER",
    base={
        "README.md": README + "\n@@blocks features\n",
        "meterreads/__init__.py": '"""Electricity meter reports."""\n',
        "meterreads/__main__.py": "import sys\n\nfrom .cli import main\n\nsys.exit(main())\n",
        "meterreads/readings.py": READINGS,
        "meterreads/cli.py": CLI,
        ".gitignore": "__pycache__/\n*.pyc\n",
    },
    visible={"tests/test_basic.py": VISIBLE},
    hidden={"tests/test_features.py": HIDDEN},
)

register_app("feature-py-meterreads", APP, make_slices, n=14, summary="meter report CLI: units, JSON, monthly, outliers, billing, settings precedence")
