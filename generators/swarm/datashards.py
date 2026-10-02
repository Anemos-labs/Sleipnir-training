"""Messy data shards: every shard is a different supplier export that must be normalised, then merged into one summary."""
from __future__ import annotations

import csv
import io
import json
from datetime import date, timedelta
from decimal import Decimal

from fx import Task, dd, family

from ._kit import GRADE_CMD, oxford, score_script, team

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
FIRST = ["Ana", "Bram", "Cleo", "Dov", "Edda", "Finn", "Greta", "Hugo", "Ines", "Jun", "Kari", "Lev", "Mina", "Nils", "Odile", "Pavel"]
LAST = ["Aldous", "Berg", "Castellan", "Dunmore", "Eklund", "Fairweather", "Grimaldi", "Holt", "Iversen", "Jarrow", "Kowal", "Lindqvist"]
CATS = {
    "produce": ["Fresh Prod.", "produce", "FRUIT & VEG", "Produce "], "dairy": ["Dairy", "milk/cheese", "DAIRY & EGGS", "dairy "],
    "bakery": ["Bakery", "bread", "BAKERY/CAKES", "baked goods"], "drinks": ["Drinks", "beverages", "SOFT DRINKS", "drinks"],
    "household": ["Household", "cleaning", "HOUSE & HOME", "household "], "other": ["Misc", "other", "SUNDRY", "Other "],
}
HEADER_SETS = [
    {"id": "id", "date": "date", "customer": "customer", "category": "category", "amount": "amount", "paid": "paid", "updated": "updated"},
    {"id": "ref", "date": "booked", "customer": "client", "category": "dept", "amount": "value", "paid": "settled", "updated": "last_modified"},
    {"id": "Order No", "date": "Order Date", "customer": "Customer Name", "category": "Product Group", "amount": "Total", "paid": "Paid?", "updated": "Updated At"},
    {"id": "key", "date": "dt", "customer": "who", "category": "cat", "amount": "amt", "paid": "ok", "updated": "mod"},
]
DATE_FMT = ["iso", "dmy", "mdy2", "dmon"]
AMOUNT_FMT = ["plain", "eu", "currency", "accounting", "cents"]
PAID_FMT = [("Y", "N"), ("yes", "no"), ("1", "0"), ("paid", "open")]
DELIMS = [",", ";", "\t", "|"]


def render_date(d: date, fmt: str) -> str:
    if fmt == "iso":
        return d.isoformat()
    if fmt == "dmy":
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    if fmt == "mdy2":
        return f"{d.month:02d}-{d.day:02d}-{d.year % 100:02d}"
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def group(n: int, sep: str) -> str:
    return f"{n:,}".replace(",", sep)


def render_amount(cents: int, fmt: str) -> str:
    neg, mag = cents < 0, abs(cents)
    whole, frac = divmod(mag, 100)
    if fmt == "plain":
        s = f"{whole}.{frac:02d}"
        if frac % 10 == 0 and frac:
            s = f"{whole}.{frac // 10}"
        return ("-" if neg else "") + s
    if fmt == "eu":
        return ("-" if neg else "") + f"{group(whole, '.')},{frac:02d}"
    if fmt == "currency":
        return ("-" if neg else "") + f"${group(whole, ',')}.{frac:02d}"
    if fmt == "accounting":
        body = f"{group(whole, ',')}.{frac:02d}"
        return f"({body})" if neg else body
    return str(cents)


def build_shard(rng, idx, n_rows, quirks):
    """Returns (raw text, expected rows as list of dicts, doc bullets)."""
    hdr = quirks["header"]
    cols = ["id", "date", "customer", "category", "amount", "paid"] + (["updated"] if quirks["dupes"] else [])
    rng.shuffle(cols)
    if quirks["delim"] == "\t" or True:
        pass
    delim = quirks["delim"]
    prefix = rng.choice(["A", "B", "K", "M", "P", "R"]) + str(idx)
    truth, rows_raw = [], []
    base = date(1996, 1, 1)
    used = set()
    cats = list(CATS)
    for i in range(n_rows):
        num = rng.randint(1000, 9999)
        while num in used:
            num = rng.randint(1000, 9999)
        used.add(num)
        d = base + timedelta(days=rng.randint(0, 365 * 38))
        cust = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        cat = rng.choice(cats)
        cents = rng.choice([rng.randint(-5000, 900), rng.randint(100, 250000), rng.randint(100, 25000), rng.randint(100000, 9999999)])
        paid = rng.random() < 0.6
        truth.append({"id": f"{prefix}-{num}", "date": d, "customer": cust, "category": cat, "amount": cents, "paid": paid})
    rows_raw = []
    pay_t, pay_f = quirks["paid"]
    for t in truth:
        raw_cust = t["customer"]
        if quirks["messy_names"]:
            raw_cust = rng.choice(["  ", ""]) + raw_cust.replace(" ", rng.choice([" ", "  ", "   "])) + rng.choice(["", " ", "  "])
        label = rng.choice(CATS[t["category"]][: quirks["cat_variants"]])
        rec = {"id": t["id"], "date": render_date(t["date"], quirks["date"]), "customer": raw_cust, "category": label,
               "amount": render_amount(t["amount"], quirks["amount"]), "paid": pay_t if t["paid"] else pay_f}
        rows_raw.append((t, rec))
    out_rows = []  # (truth or None, raw record) in file order
    stamp = 0
    for t, rec in rows_raw:
        stamp += 1
        if quirks["dupes"]:
            rec = dict(rec, updated=f"2024-02-{(stamp % 27) + 1:02d}T10:{stamp % 60:02d}:00")
            if rng.random() < 0.3:
                # an older, stale version of the same id appears (earlier timestamp, other amount)
                stale = dict(rec, amount=render_amount(t["amount"] + rng.choice([-700, 350, 1200]), quirks["amount"]),
                             updated=f"2023-11-{(stamp % 27) + 1:02d}T09:{stamp % 60:02d}:00", paid=pay_t if not t["paid"] else pay_f)
                out_rows.append((None, stale))
        out_rows.append((t, rec))
    rng.shuffle(out_rows)
    lines = []
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delim, lineterminator="\n")
    header_row = [hdr[c] for c in cols]
    w.writerow(header_row)
    junk_kinds = quirks["junk"]
    for j, (t, rec) in enumerate(out_rows):
        w.writerow([rec[c] for c in cols])
        if "pagebreak" in junk_kinds and j in (len(out_rows) // 3, 2 * len(out_rows) // 3):
            w.writerow(header_row)
        if "test" in junk_kinds and rng.random() < 0.08:
            w.writerow([rec[c] if c != "id" else rng.choice(["TEST-", "test", "Test_"]) + str(rng.randint(1, 99)) for c in cols])
        if "blank" in junk_kinds and rng.random() < 0.06:
            buf.write("\n")
    if "footer" in junk_kinds:
        w.writerow(["TOTAL" if c == "id" else "" for c in cols])
    raw = buf.getvalue()
    expected = []
    for t in sorted(truth, key=lambda r: r["id"]):
        expected.append({"id": t["id"], "date": t["date"].isoformat(), "customer": t["customer"], "category": t["category"],
                         "amount": f"{Decimal(t['amount']) / 100:.2f}", "paid": "true" if t["paid"] else "false"})
    return raw, expected, cols, delim


def shard_doc(idx, name, quirks, cols, delim):
    hdr = quirks["header"]
    dname = {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}[delim]
    out = [f"### `{name}` (`raw/{name}.csv`)", ""]
    out.append(f"* {dname}-separated, with a header line; columns: " + ", ".join(f"`{hdr[c]}` = {c}" for c in cols) + ".")
    df = {"iso": "dates are already ISO (`YYYY-MM-DD`)", "dmy": "dates are `DD/MM/YYYY`",
          "mdy2": "dates are `MM-DD-YY` with a two-digit year: 00-69 mean 2000-2069, 70-99 mean 1970-1999",
          "dmon": "dates look like `3 Mar 2024` (day without padding, English month abbreviation)"}[quirks["date"]]
    out.append(f"* {df}.")
    af = {"plain": "amounts are plain decimals (`1234.5`, `-12.30`), possibly with one decimal only",
          "eu": "amounts use European notation: `.` groups thousands and `,` marks the decimals (`1.234,56`, `-12,30`)",
          "currency": "amounts carry a dollar sign and comma thousands (`$1,234.50`, `-$12.30`)",
          "accounting": "negative amounts are written in parentheses, `(1,234.50)`; positive ones as `1,234.50`",
          "cents": "amounts are whole **cents** (`123450` is 1234.50), possibly negative"}[quirks["amount"]]
    out.append(f"* {af}.")
    out.append(f"* paid flag: `{quirks['paid'][0]}` means true, `{quirks['paid'][1]}` means false.")
    if quirks["cat_variants"]:
        out.append("* category labels are free text; map them with `mappings/categories.csv` (compare after trimming and ignoring case).")
    if quirks["messy_names"]:
        out.append("* customer names may have leading, trailing or repeated spaces: trim and collapse runs of spaces to one.")
    junk = quirks["junk"]
    if "pagebreak" in junk:
        out.append("* the header line is repeated in the middle of the file (page breaks): drop those rows.")
    if "test" in junk:
        out.append("* rows whose id starts with `TEST` (any capitalisation, followed by `-` or `_` or digits) are test data: drop them.")
    if "blank" in junk:
        out.append("* blank lines appear here and there: skip them.")
    if "footer" in junk:
        out.append("* the last row has the id `TOTAL` and is a footer: drop it.")
    if quirks["dupes"]:
        out.append(f"* an id can appear more than once: keep only the row with the latest `{hdr['updated']}` (ISO timestamp, never tied).")
    return out


SUMMARY_DOC = dd('''
    ## Merged summary

    Write `report/summary.json` (pretty-printed or not, keys in any order) from the six canonical columns of all the clean shards:

    ```json
    {"rows": 123, "total": "45678.90", "unpaid": 41,
     "by_category": {"bakery": "123.45", "dairy": "..."},
     "shards": {"shard_1": 30, "shard_2": 41}}
    ```

    * `rows`: number of clean rows over all shards; `shards`: rows per shard;
    * `total`: sum of `amount` over all rows as a string with exactly two decimals;
    * `by_category`: per category (only categories that occur), the same kind of sum; `unpaid`: rows with `paid` = `false`.
''')

CANON_DOC = dd('''
    ## Clean format

    `clean/<shard>.csv`: comma-separated, one header line `id,date,customer,category,amount,paid`, then one row per record, **sorted by id**
    (plain string order). `date` is ISO `YYYY-MM-DD`; `customer` is trimmed text; `category` is one of `produce`, `dairy`, `bakery`, `drinks`,
    `household`, `other`; `amount` has exactly two decimals (`-12.30`, `1234.50`; no thousands separators, no currency sign); `paid` is `true` or `false`.
    Standard CSV quoting is fine. A label missing from the mapping file is `other`.
''')

CHECK = '''import csv
import io
import json
import os
import sys
from decimal import Decimal

DATA = json.loads(%(data)r)


def fail(msg):
    print("FAILED:", msg, file=sys.stderr)
    sys.exit(1)


def read_clean(name):
    path = os.path.join("clean", name + ".csv")
    if not os.path.exists(path):
        fail("missing " + path)
    text = open(path, encoding="utf-8", newline="").read()
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or rows[0] != ["id", "date", "customer", "category", "amount", "paid"]:
        fail("%%s: wrong header %%r" %% (path, rows[0] if rows else None))
    return [dict(zip(rows[0], r)) for r in rows[1:]]


def check_shard(name):
    want = DATA["shards"][name]
    got = read_clean(name)
    if len(got) != len(want):
        fail("%%s: %%d rows, want %%d" %% (name, len(got), len(want)))
    for g, w in zip(got, want):
        if g != w:
            fail("%%s: row %%r\\n  want %%r" %% (name, g, w))


def check_summary():
    path = "report/summary.json"
    if not os.path.exists(path):
        fail("missing report/summary.json")
    got = json.load(open(path, encoding="utf-8"))
    want = DATA["summary"]
    for key in ("rows", "total", "unpaid", "by_category", "shards"):
        if got.get(key) != want[key]:
            fail("summary %%s is %%r, want %%r" %% (key, got.get(key), want[key]))


if __name__ == "__main__":
    what = sys.argv[1]
    check_summary() if what == "summary" else check_shard(what)
'''


@family("swarm-data-shards", category="swarm", lang="mixed", kind="feature", n=10,
        summary="k differently messy supplier exports to normalise into one canonical format, then merge into a summary")
def data_shards(rng, n):
    ks = [3, 3, 4, 4, 5, 5, 6, 4, 6, 7]
    for i in range(n):
        k = ks[i % len(ks)]
        names = [f"shard_{j + 1}" for j in range(k)]
        shard_quirks = []
        dates = list(DATE_FMT)
        amounts = list(AMOUNT_FMT)
        rng.shuffle(dates)
        rng.shuffle(amounts)
        for j in range(k):
            junk = [x for x in ("pagebreak", "test", "blank", "footer") if rng.random() < 0.45]
            shard_quirks.append({
                "header": HEADER_SETS[j % len(HEADER_SETS)] if j < len(HEADER_SETS) else rng.choice(HEADER_SETS),
                "delim": DELIMS[j % 4] if rng.random() < 0.7 else rng.choice(DELIMS),
                "date": dates[j % len(dates)], "amount": amounts[j % len(amounts)], "paid": PAID_FMT[(j + i) % len(PAID_FMT)],
                "cat_variants": rng.choice([2, 3, 4]), "messy_names": rng.random() < 0.5, "junk": junk, "dupes": rng.random() < 0.5 or j == 0,
            })
        raws, expected, docs = {}, {}, []
        for j, name in enumerate(names):
            raw, exp, cols, delim = build_shard(rng, j + 1, rng.randint(24, 50), shard_quirks[j])
            raws[name], expected[name] = raw, exp
            docs += shard_doc(j + 1, name, shard_quirks[j], cols, delim) + [""]
        all_rows = [r for name in names for r in expected[name]]
        by_cat = {}
        for r in all_rows:
            by_cat[r["category"]] = by_cat.get(r["category"], Decimal(0)) + Decimal(r["amount"])
        summary = {"rows": len(all_rows), "total": f"{sum(Decimal(r['amount']) for r in all_rows):.2f}",
                   "unpaid": sum(1 for r in all_rows if r["paid"] == "false"),
                   "by_category": {c: f"{v:.2f}" for c, v in sorted(by_cat.items())}, "shards": {nm: len(expected[nm]) for nm in names}}
        mapping = ["label,category"]
        for cat, labels in CATS.items():
            for lab in labels:
                mapping.append(f"{lab.strip().lower()},{cat}" if "," not in lab else f'"{lab.strip().lower()}",{cat}')
        start = {f"raw/{nm}.csv": raws[nm] for nm in names}
        start["mappings/categories.csv"] = "\n".join(dict.fromkeys(mapping)) + "\n"
        start["SHARDS.md"] = "# Supplier exports\n\nEach file in `raw/` is one supplier's monthly export, in its own shape. Turn every one into the clean format "
        start["SHARDS.md"] += "and then build the merged summary. The shards are independent of each other.\n\n" + CANON_DOC + "\n## The raw shards\n\n" + "\n".join(docs) + "\n" + SUMMARY_DOC
        start["README.md"] = "# Month-end data\n\n`raw/` holds the exports, `mappings/` the shared lookup tables, `SHARDS.md` the rules. Put results in `clean/` and `report/`. Scripts you write belong in `tools/`.\n"
        data = {"shards": expected, "summary": summary}
        hidden = {".grade/check_shards.py": CHECK % {"data": json.dumps(data, sort_keys=True)}}
        units = [{"name": nm, "cmd": ["python3", ".grade/check_shards.py", nm], "weight": 1} for nm in names]
        units.append({"name": "summary", "cmd": ["python3", ".grade/check_shards.py", "summary"], "weight": max(1, k // 3)})
        hidden[".grade/score.py"] = score_script(units)
        solution = {}
        for nm in names:
            buf = io.StringIO()
            w = csv.writer(buf, lineterminator="\n")
            w.writerow(["id", "date", "customer", "category", "amount", "paid"])
            for r in expected[nm]:
                w.writerow([r[c] for c in ("id", "date", "customer", "category", "amount", "paid")])
            solution[f"clean/{nm}.csv"] = buf.getvalue()
        solution["report/summary.json"] = json.dumps(summary, indent=2, sort_keys=True) + "\n"
        voices = [
            f"Month-end again and the {k} supplier exports in raw/ all look different. SHARDS.md says how to read each one and what the clean format is. "
            f"Produce every clean/ file and then the merged report/summary.json; the shards don't depend on each other, so split them up.",
            f"Please normalise the supplier shards in raw/ ({oxford(names)}) into clean/ as described in SHARDS.md, then write the merged summary. "
            f"Watch for the traps: stale duplicate rows, footers, different number formats.",
            f"I have {k} CSV exports from different suppliers and need them in one canonical format plus a summary of the lot. Everything is spelled out in "
            f"SHARDS.md. Any scripts you write should go in tools/.",
            f"Data cleanup job: raw/ -> clean/ for each shard (rules in SHARDS.md), then report/summary.json over all of them. "
            f"The totals have to match to the cent.",
        ]
        d = 3 if k <= 3 else 4 if k <= 5 else 5
        yield Task(
            slug=f"{i + 1:02d}-k{k}-" + shard_quirks[0]["amount"],
            prompt=voices[i % len(voices)], difficulty=d, start=start, hidden=hidden, solution=solution,
            verify=GRADE_CMD, pass_mode="json-score",
            team=team(rng, min(k, 6), ["backend", "tester"] if i % 2 else ["backend", "reviewer", "tester"]),
            tags=["data", "csv", "normalisation", "merge"],
            notes={"shards": k, "quirks": [{"date": q["date"], "amount": q["amount"], "delim": q["delim"], "dupes": q["dupes"], "junk": q["junk"]} for q in shard_quirks]},
        )
