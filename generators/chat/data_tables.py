"""Reading pasted tables, spreadsheet formulas and messy text lists. Answers are computed from the same data that is pasted."""
from __future__ import annotations

import re
import statistics
from datetime import date, timedelta
from fractions import Fraction

from fx import family

from . import _common as C

# --------------------------------------------------------------------------------------------------------------------
# chat-table-read

DOMAINS = [
    dict(key="bikes", unit="station", rows=["Quay Street", "Mill Lane", "Library Corner", "Station North", "Park Gate", "Market Square", "Canal Bridge", "Old Brewery",
                                            "Harbour View", "Chapel Row", "Gasworks", "Tannery Yard", "Riverside East", "Castle Hill", "Ropewalk", "Fish Dock", "Orchard Rd", "Union Wharf"],
         cols=("rides_may", "rides_jun", "avg_ride_min", "repairs_jun"), ranges=((120, 900), (120, 900), (8, 35), (0, 14)),
         story="our bike-share scheme's station report", metric="repairs", per="repairs per 100 June rides", avg="average ride length (minutes)"),
    dict(key="library", unit="branch", rows=["Eastgate", "Hollin Park", "Marsh Road", "Quarry Hill", "St Anne's", "Weavers' Court", "Beacon", "Fenside", "Larkfield", "Oakmoor", "Pit Lane", "Redcar Walk",
                                             "Southbank", "Thornley", "Westmere", "Yewdale"],
         cols=("loans_q1", "loans_q2", "avg_loan_days", "overdue_q2"), ranges=((800, 6000), (800, 6000), (12, 26), (10, 400)),
         story="the branch statistics for our library service", metric="overdue", per="overdue items per 100 Q2 loans", avg="average loan length (days)"),
    dict(key="calls", unit="team", rows=["Billing A", "Billing B", "Returns", "Tech L1", "Tech L2", "Onboarding", "VIP desk", "Night cover", "Claims", "Retention", "Web chat", "Field dispatch"],
         cols=("calls_wk1", "calls_wk2", "avg_handle_min", "abandoned_wk2"), ranges=((300, 2500), (300, 2500), (3, 14), (5, 260)),
         story="the call-centre weekly summary", metric="abandoned", per="abandoned calls per 100 week-2 calls", avg="average handle time (minutes)"),
    dict(key="vans", unit="van", rows=["Van 1", "Van 2", "Van 3", "Van 4", "Van 5", "Van 6", "Van 7", "Van 8", "Van 9", "Van 10", "Van 11", "Van 12", "Van 14", "Van 15"],
         cols=("drops_mon", "drops_tue", "avg_stop_min", "failed_tue"), ranges=((40, 160), (40, 160), (2, 9), (0, 18)),
         story="the courier depot's two-day delivery summary", metric="failed", per="failed deliveries per 100 Tuesday drops", avg="average minutes per stop"),
    dict(key="solar", unit="array", rows=["Barn roof", "Carport", "South field", "Workshop", "Greenhouse", "Pump house", "Gatehouse", "Cow shed", "Farm shop", "Stable block", "Machinery hall", "Annexe"],
         cols=("kwh_jan", "kwh_feb", "avg_peak_kw", "faults_feb"), ranges=((200, 1800), (200, 1800), (2, 9), (0, 12)),
         story="the monthly output log of our farm's solar arrays", metric="faults", per="fault events per 1000 February kWh", avg="average daily peak output (kW)"),
    dict(key="trays", unit="tray", rows=["T-01", "T-02", "T-03", "T-04", "T-05", "T-06", "T-07", "T-08", "T-09", "T-10", "T-11", "T-12", "T-13", "T-14"],
         cols=("sown", "germinated", "avg_height_mm", "mould_trays"), ranges=((60, 200), (30, 200), (6, 40), (0, 20)),
         story="the seed-tray germination notes from the greenhouse", metric="mould", per="mouldy seedlings per 100 germinated", avg="average seedling height (mm)"),
]


def _mk_table(rng, dom, N, d):
    names = rng.sample(dom["rows"], N)
    rows = []
    for nm in names:
        a = rng.randint(*dom["ranges"][0])
        a2 = rng.randint(*dom["ranges"][1])
        b = rng.randint(*dom["ranges"][2])
        c = rng.randint(*dom["ranges"][3])
        if dom["key"] == "trays":
            a2 = rng.randint(int(a * 0.3), a)
            c = min(c, a2)
        c = min(c, max(0, a2 - 1)) if dom["key"] != "solar" else c
        rows.append([nm, a, a2, b, c])
    return rows


@family("chat-table-read", category="chat", lang="text", kind="lookup", n=16, mode="answer",
        summary="questions about a pasted or attached table: increases, rates per 100, weighted averages, conditional sums, k-th largest, compound filters")
def gen_table(rng, n):
    plan = [1, 2, 2, 3, 3, 3, 4, 4, 5, 2, 3, 4, 3, 4, 5, 2]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(200):
            dom = rng.choice(DOMAINS)
            N = {1: 6, 2: 8, 3: 10, 4: 14, 5: 36}[d]
            N = min(N, len(dom["rows"])) if d != 5 else N
            if d == 5:
                names = [f"{dom['unit']}-{k:02d}" for k in range(1, N + 1)]
                rows = []
                for nm in names:
                    rows.append([nm] + [rng.randint(*r) for r in dom["ranges"]])
                    if dom["key"] == "trays":
                        rows[-1][2] = rng.randint(int(rows[-1][1] * 0.3), rows[-1][1])
                        rows[-1][4] = min(rows[-1][4], rows[-1][2])
            else:
                rows = _mk_table(rng, dom, N, d)
            cols = dom["cols"]
            kind = {1: ["nth", "cond_sum"], 2: ["growth", "cond_sum", "nth"], 3: ["ratio", "wavg", "growth"], 4: ["count2", "ratio2", "wavg"], 5: ["combo"]}[d]
            kind = rng.choice(kind)
            idx = {r[0]: j + 1 for j, r in enumerate(rows)}
            header = ["#", dom["unit"]] + list(cols)
            body = [[j + 1] + r for j, r in enumerate(rows)]
            tbl = C.table(body, header)
            A, A2, B, Cc = 1, 2, 3, 4  # column indexes inside r (name at 0)
            if kind == "nth":
                k = rng.randint(2, 4)
                srt = sorted(rows, key=lambda r: -r[A2])
                if len({r[A2] for r in rows}) != len(rows):
                    continue
                pick = srt[k - 1]
                ask = f"Looking at {cols[1]}, which row number has the {C.ordinal(k)} highest value, and what is that value?"
                contains = [str(pick[A2])]
                gold = f"Row {idx[pick[0]]} ({pick[0]}) with {pick[A2]}."
                # row number is weak; put it too
                contains.append(f"row {idx[pick[0]]}")
                ask += " Please write the row as 'row N'."
            elif kind == "cond_sum":
                thr = int(statistics.median(r[B] for r in rows))
                tot = sum(r[A2] for r in rows if r[B] > thr)
                cnt = sum(1 for r in rows if r[B] > thr)
                if cnt in (0, len(rows)):
                    continue
                ask = f"What is the total of {cols[1]} over only the rows where {cols[2]} is strictly greater than {thr}, and how many rows is that?"
                contains = [str(tot)]
                gold = f"{tot} across {cnt} rows."
                ask += " (Give the total first, then the row count.)"
            elif kind == "growth":
                diffs = [(r[A2] - r[A], r) for r in rows]
                diffs.sort(key=lambda x: -x[0])
                if diffs[0][0] == diffs[1][0]:
                    continue
                best = diffs[0]
                ask = f"Which row had the biggest increase from {cols[0]} to {cols[1]} in absolute terms (not percent)? Give the row as 'row N' and the increase."
                contains = [f"row {idx[best[1][0]]}", str(best[0])]
                gold = f"Row {idx[best[1][0]]} ({best[1][0]}): +{best[0]}."
            elif kind in ("ratio", "ratio2"):
                rat = [(Fraction(r[Cc] * 100, r[A2]), r) for r in rows if r[A2] > 0]
                if dom["key"] == "solar":
                    rat = [(Fraction(r[Cc] * 1000, r[A2]), r) for r in rows]
                rat.sort(key=lambda x: -x[0])
                if rat[0][0] - rat[1][0] < Fraction(1, 5):
                    continue
                val = rat[0][0]
                vs = f"{float(val):.1f}"
                ask = f"Which row has the highest {dom['per']} (dividing {cols[3]} by {cols[1]}), and what is the figure to one decimal place?"
                ask += " Write the row as 'row N'."
                contains = [f"row {idx[rat[0][1][0]]}", vs]
                gold = f"Row {idx[rat[0][1][0]]} ({rat[0][1][0]}): {vs}."
            elif kind == "wavg":
                totw = sum(r[A2] for r in rows)
                wa = Fraction(sum(r[A2] * r[B] for r in rows), totw)
                if (wa * 100 - (wa * 100).numerator // (wa * 100).denominator) == Fraction(1, 2):
                    continue
                vs = f"{float(wa):.2f}"
                ask = f"What is the overall {dom['avg']} across all rows if each row is weighted by its {cols[1]}? Two decimal places."
                contains = [vs]
                gold = vs
            elif kind == "count2":
                thr = int(statistics.median(r[B] for r in rows))
                sel = [r for r in rows if r[A2] < r[A] and r[B] > thr]
                if not sel:
                    continue
                s = sum(r[Cc] for r in sel)
                ask = (f"How many rows have {cols[1]} lower than {cols[0]} AND {cols[2]} strictly above {thr}, and what is the sum of {cols[3]} over just those rows? "
                       f"Give the count first and then the sum.")
                contains = [f"{len(sel)} rows", str(s)] if False else [str(s)]
                gold = f"{len(sel)} rows, sum {s}."
            else:  # combo (file)
                sel = [r for r in rows if r[A2] < r[A]]
                if len(sel) < 5:
                    continue
                tw = sum(r[A2] for r in sel)
                wa = Fraction(sum(r[A2] * r[B] for r in sel), tw)
                top = max(sel, key=lambda r: r[A] - r[A2])
                srt = sorted(sel, key=lambda r: r[A] - r[A2], reverse=True)
                if srt[0][A] - srt[0][A2] == srt[1][A] - srt[1][A2]:
                    continue
                vs = f"{float(wa):.2f}"
                ask = (f"Considering only the rows where {cols[1]} fell compared with {cols[0]}: how many rows are those, what is their {dom['avg']} weighted by {cols[1]} "
                       f"(two decimals), and which row number had the biggest drop (as 'row N')?")
                contains = [vs, f"row {idx[top[0]]}"]
                gold = f"{len(sel)} rows; weighted {vs}; biggest drop row {idx[top[0]]}."
            intro = rng.choice([f"I'm looking at {dom['story']} and I don't trust my head for this.",
                                f"Can you answer a question about this table for me? It's {dom['story']}.",
                                f"this is {dom['story']}, I need one number out of it for a meeting",
                                f"Here's {dom['story']}. Rows are numbered in the first column."])
            reg = C.register_for(rng)
            if d == 5:
                csvt = ",".join(["row", dom["unit"]] + list(cols)) + "\n" + "\n".join(",".join(str(x) for x in [j + 1] + r) for j, r in enumerate(rows)) + "\n"
                prompt = C.chat(rng, intro.replace("Here's", "The data for").replace("this is", "the data for") + " It is in report.csv (row numbers in the first column).", ask, None, reg)
                start = {"report.csv": csvt}
            else:
                prompt = C.chat(rng, intro, ask, C.block(tbl), reg)
                start = None
            keep = C.unseen(prompt, contains, True, min_keep=len(contains))
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{dom['key']}-{kind}", prompt, d, keep, gold, fold=True, start=start, tags=["table", "arithmetic"], notes={"kind": kind, "rows": N})
            break
        else:
            raise RuntimeError("table: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-sheet-formula

SHEET_ITEMS = [("apples", "kiwis", "pears", "plums", "figs", "limes", "dates", "quinces"), ("north", "south", "east", "west", "central"),
               ("mon", "tue", "wed", "thu", "fri", "sat", "sun")]
COLS = "ABCDEF"


def _col_range(c, r1, r2):
    return f"{c}{r1}:{c}{r2}"


@family("chat-sheet-formula", category="chat", lang="text", kind="lookup", n=14, mode="answer",
        summary="what does this spreadsheet formula evaluate to on a pasted grid (blanks, text cells, COUNTIF/SUMIF/INDEX-MATCH traps)")
def gen_sheet(rng, n):
    plan = [1, 2, 2, 3, 3, 3, 4, 4, 5, 2, 3, 4, 5, 3]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(200):
            rows = rng.randint(5, 8)
            labels_pool = rng.choice(SHEET_ITEMS)
            labels = [rng.choice(labels_pool) for _ in range(rows)]
            if d >= 3:
                labels = [labels_pool[j % len(labels_pool)] for j in range(rows)]
                rng.shuffle(labels)
            B = [rng.choice([rng.randint(3, 60), rng.randint(3, 60), None, "n/a"]) if d >= 3 else rng.randint(3, 60) for _ in range(rows)]
            Cv = [rng.randint(2, 40) if d < 4 or rng.random() > 0.15 else None for _ in range(rows)]
            grid = {}
            for r in range(rows):
                grid[f"A{r + 2}"] = labels[r]
                grid[f"B{r + 2}"] = B[r]
                grid[f"C{r + 2}"] = Cv[r]
            hdr = {"A1": "item", "B1": "qty", "C1": "price"}
            r1, r2 = 2, rows + 1

            def nums(col, rr1=r1, rr2=r2):
                return [grid[f"{col}{r}"] for r in range(rr1, rr2 + 1) if isinstance(grid[f"{col}{r}"], (int, float))]
            kind = {1: ["sum", "max"], 2: ["avg", "countif", "sumif"], 3: ["avg_blank", "countif_gt", "sumifs", "count_vs_counta"], 4: ["sumproduct", "indexmatch", "nested_round"],
                    5: ["avg_if_nested", "sumifs_text"]}[d]
            kind = rng.choice(kind)
            lab = rng.choice(labels)
            if kind == "sum":
                f = f"=SUM(B{r1}:B{r2})"
                val = sum(nums("B"))
            elif kind == "max":
                f = f"=MAX(B{r1}:B{r2})-MIN(B{r1}:B{r2})"
                val = max(nums("B")) - min(nums("B"))
            elif kind == "avg":
                f = f"=ROUND(AVERAGE(C{r1}:C{r2}),1)"
                v = nums("C")
                val = Fraction(sum(v), len(v))
                if (val * 10 - (val * 10).numerator // (val * 10).denominator) == Fraction(1, 2):
                    continue
                val = round(float(val), 1)
            elif kind == "countif":
                t = rng.randint(15, 45)
                f = f'=COUNTIF(B{r1}:B{r2},">{t}")'
                val = sum(1 for x in nums("B") if x > t)
            elif kind == "sumif":
                f = f'=SUMIF(A{r1}:A{r2},"{lab}",B{r1}:B{r2})'
                val = sum(grid[f"B{r}"] for r in range(r1, r2 + 1) if grid[f"A{r}"] == lab and isinstance(grid[f"B{r}"], (int, float)))
            elif kind == "avg_blank":
                f = f"=AVERAGE(B{r1}:B{r2})"
                v = nums("B")
                if not v:
                    continue
                val = Fraction(sum(v), len(v))
                val = f"{float(val):.2f}"
            elif kind == "countif_gt":
                f = f'=COUNTIFS(A{r1}:A{r2},"{lab}",B{r1}:B{r2},">=20")'
                val = sum(1 for r in range(r1, r2 + 1) if grid[f"A{r}"] == lab and isinstance(grid[f"B{r}"], (int, float)) and grid[f"B{r}"] >= 20)
            elif kind == "sumifs":
                f = f'=SUMIFS(C{r1}:C{r2},A{r1}:A{r2},"{lab}",B{r1}:B{r2},"<30")'
                val = sum(grid[f"C{r}"] for r in range(r1, r2 + 1) if grid[f"A{r}"] == lab and isinstance(grid[f"B{r}"], (int, float)) and grid[f"B{r}"] < 30 and isinstance(grid[f"C{r}"], (int, float)))
            elif kind == "count_vs_counta":
                f = f"=COUNTA(B{r1}:B{r2})*100+COUNT(B{r1}:B{r2})"
                ca = sum(1 for r in range(r1, r2 + 1) if grid[f"B{r}"] is not None)
                co = len(nums("B"))
                val = ca * 100 + co
            elif kind == "sumproduct":
                f = f"=SUMPRODUCT(B{r1}:B{r2},C{r1}:C{r2})"
                val = sum((grid[f"B{r}"] if isinstance(grid[f"B{r}"], (int, float)) else 0) * (grid[f"C{r}"] if isinstance(grid[f"C{r}"], (int, float)) else 0) for r in range(r1, r2 + 1))
            elif kind == "indexmatch":
                tgt = lab
                firstr = next(r for r in range(r1, r2 + 1) if grid[f"A{r}"] == tgt)
                k = rng.choice(["C", "B"])
                f = f'=INDEX({k}{r1}:{k}{r2},MATCH("{tgt}",A{r1}:A{r2},0))*2'
                x = grid[f"{k}{firstr}"]
                if not isinstance(x, (int, float)):
                    continue
                val = x * 2
            elif kind == "nested_round":
                f = f"=ROUND(SUM(B{r1}:B{r2})/COUNT(C{r1}:C{r2}),2)"
                v = Fraction(sum(nums("B")), len(nums("C")))
                if (v * 100 - (v * 100).numerator // (v * 100).denominator) == Fraction(1, 2):
                    continue
                val = f"{float(v):.2f}"
            elif kind == "avg_if_nested":
                f = f'=IF(COUNTIF(A{r1}:A{r2},"{lab}")>=2,SUMIF(A{r1}:A{r2},"{lab}",B{r1}:B{r2})/COUNTIF(A{r1}:A{r2},"{lab}"),-1)'
                cn = sum(1 for r in range(r1, r2 + 1) if grid[f"A{r}"] == lab)
                if cn < 2:
                    continue
                sm = sum(grid[f"B{r}"] for r in range(r1, r2 + 1) if grid[f"A{r}"] == lab and isinstance(grid[f"B{r}"], (int, float)))
                v = Fraction(sm, cn)
                if (v * 100 - (v * 100).numerator // (v * 100).denominator) == Fraction(1, 2):
                    continue
                val = f"{float(v):.2f}"
            else:  # sumifs_text
                f = f'=SUMIF(A{r1}:A{r2},"<>{lab}",B{r1}:B{r2})+COUNTIF(B{r1}:B{r2},"n/a")'
                val = sum(grid[f"B{r}"] for r in range(r1, r2 + 1) if grid[f"A{r}"] != lab and isinstance(grid[f"B{r}"], (int, float))) + sum(1 for x in B if x == "n/a")
            vs = str(val) if not isinstance(val, float) else (f"{val:.1f}" if kind == "avg" else f"{val}")
            lines = []
            allcells = [["", "A", "B", "C"]]
            allcells.append([1, "item", "qty", "price"])
            for r in range(r1, r2 + 1):
                allcells.append([r, grid[f"A{r}"], "" if grid[f"B{r}"] is None else grid[f"B{r}"], "" if grid[f"C{r}"] is None else grid[f"C{r}"]])
            tbl = C.table(allcells[1:], allcells[0], sep=" | ")
            intro = rng.choice(["My spreadsheet is returning something odd and I want to know what it *should* give.",
                                "Settle a bet at work: what does this formula return?",
                                "I'm auditing a colleague's sheet. Here's the relevant block (blank cells are really empty, n/a is text).",
                                "Quick spreadsheet question about the grid below."])
            ask = f"If I put `{f}` in cell E1, what value should it show? Give just the number (decimal point, no currency symbol)."
            if "COUNTIF" in f or "COUNT" in f:
                ask = f"If I put `{f}` in cell E1, what number does it show?"
            prompt = C.chat(rng, intro, ask, C.block(tbl), C.register_for(rng))
            contains = [vs]
            if not C.uniq_in_prompt_ok(prompt, contains):
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, d, contains, vs, tags=["spreadsheet", "formula"], notes={"kind": kind, "formula": f})
            break
        else:
            raise RuntimeError("sheet: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-text-transform

FN = ["Amelie", "Bastian", "Cosima", "Dagny", "Elio", "Farida", "Gunnar", "Hester", "Idris", "Jolene", "Kasimir", "Lotte", "Mireille", "Nestor", "Odette", "Pascal", "Quillon", "Rosamund", "Soledad", "Tavish"]
LN = ["Abernathy", "Brandt", "Castellane", "Dvorak", "Esterhazy", "Fontaine", "Grimaldi", "Halvorsen", "Ibarra", "Jankowski", "Kellerman", "Lacroix", "Montague", "Nygaard", "Ostrander", "Pellegrini", "Quist", "Rasmussen", "Sorensen", "Thackeray"]


@family("chat-text-transform", category="chat", lang="text", kind="lookup", n=12, mode="answer",
        summary="clean, reformat, sort and dedupe a pasted messy list; ask for a count and the n-th result in the new format")
def gen_text(rng, n):
    plan = [2, 2, 3, 3, 3, 4, 4, 5, 2, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(200):
            kind = {2: ["names", "dates"], 3: ["names_sort", "phones", "dates"], 4: ["phones_dedupe", "names_sort2"], 5: ["contacts"]}[d]
            kind = rng.choice(kind)
            N = {2: 6, 3: 9, 4: 12, 5: 14}[d]
            if kind in ("names", "names_sort", "names_sort2"):
                pairs = rng.sample([(f, l) for f in FN for l in LN], N)
                fmts = []
                lines = []
                for f, l in pairs:
                    sty = rng.choice(["a", "b", "c"])
                    sp = " " * rng.randint(0, 2)
                    if sty == "a":
                        lines.append(f"{sp}{l}, {f}{sp}")
                    elif sty == "b":
                        lines.append(f"{sp}{l.upper()},{f}")
                    else:
                        lines.append(f"{sp}{l},  {f.lower()}{sp}")
                final = [(f, l) for f, l in pairs]
                if kind == "names":
                    # keep order: Nth line converted 'First Last'
                    k = rng.randint(2, N)
                    f, l = final[k - 1]
                    ask = (f"Each line is 'Last, First' (some are in odd capitalisation or spacing). Convert every name to 'First Last' with normal capitalisation (initial capital, rest lower case, no stray spaces). "
                           f"What does line {k} become? Just the converted name.")
                    contains = [f"{f} {l}".replace(f"{f} {l}", f"{f} {l}")]
                    gold = f"{f} {l}"
                else:
                    srt = sorted(final, key=lambda x: (x[1].lower(), x[0].lower()))
                    k = rng.randint(2, N - 1)
                    ask = (f"Each line is 'Last, First' with messy capitalisation and spacing. Convert to 'First Last' (normal capitalisation), then sort the list by last name (A to Z, ignoring case), "
                           f"ties by first name. What is entry number {k} in the sorted list, and which entry number is {final[0][0]} {final[0][1]}?")
                    f, l = srt[k - 1]
                    pos0 = srt.index(final[0]) + 1
                    contains = [f"{f} {l}", str(pos0)]
                    gold = f"{f} {l}; {final[0][0]} {final[0][1]} is number {pos0}"
                    if kind == "names_sort2":
                        ask += " Also give the last entry of the sorted list."
                        contains.append(f"{srt[-1][0]} {srt[-1][1]}")
                        gold += f"; last: {srt[-1][0]} {srt[-1][1]}"
                data = "\n".join(lines)
                intro = rng.choice(["I exported a member list and the names are all over the place.", "A volunteer typed our sign-up sheet into a text file and I am cleaning it up.",
                                    "I inherited this attendee list and need to tidy it before printing badges."])
            elif kind == "dates":
                ds = [date(rng.randint(2025, 2027), rng.randint(1, 12), rng.randint(1, 28)) for _ in range(N)]
                lines = []
                for dd in ds:
                    st = rng.choice(["dmy", "mname", "dots"])
                    if st == "dmy":
                        lines.append(f"{dd.day:02d}/{dd.month:02d}/{dd.year}")
                    elif st == "mname":
                        lines.append(f"{dd.day} {C.MONTHS[dd.month - 1][:3]} {dd.year}")
                    else:
                        lines.append(f"{dd.day}.{dd.month}.{str(dd.year)[2:]}")
                k = rng.randint(2, N)
                ds_sorted = sorted(ds)
                ask = (f"These are all dates, written in different styles (the numeric ones are day first, and two-digit years are 20xx). Convert each to YYYY-MM-DD. "
                       f"What does line {k} become, and what is the earliest date in the whole list (YYYY-MM-DD)?")
                contains = [C.iso(ds[k - 1]), C.iso(ds_sorted[0])]
                gold = f"line {k}: {C.iso(ds[k - 1])}; earliest {C.iso(ds_sorted[0])}"
                data = "\n".join(lines)
                intro = rng.choice(["Our delivery notes use every date style known to humanity.", "I pasted dates from three different spreadsheets and they do not match.", "dates from a messy form, help me normalise them"])
            elif kind in ("phones", "phones_dedupe"):
                base = [f"{rng.choice([20, 7, 78, 79, 117, 131])}{rng.randint(100, 999)}{rng.randint(1000, 9999)}"[:10].ljust(10, "5") for _ in range(N)]
                if kind == "phones_dedupe":
                    base = base[:N - 3] + [base[0], base[2], base[4]]
                lines = []
                for p in base:
                    st = rng.choice(["p", "dash", "plus", "space"])
                    if st == "p":
                        lines.append(f"({p[:3]}) {p[3:6]}-{p[6:]}")
                    elif st == "dash":
                        lines.append(f"{p[:3]}-{p[3:6]}-{p[6:]}")
                    elif st == "plus":
                        lines.append(f"+1 {p[:3]} {p[3:6]} {p[6:]}")
                    else:
                        lines.append(f"{p[:3]} {p[3:6]} {p[6:]}")
                canon = [f"{p[:3]}.{p[3:6]}.{p[6:]}" for p in base]
                k = rng.randint(2, N)
                uniq = list(dict.fromkeys(canon))
                ask = ("All of these are 10-digit numbers with a country code of +1 sometimes present. Normalise each to the style NNN.NNN.NNNN (dots, no country code). "
                       f"What does line {k} become" + (", and how many different numbers are there once duplicates are removed?" if kind == "phones_dedupe" else "?"))
                contains = [canon[k - 1]] + ([str(len(uniq))] if kind == "phones_dedupe" else [])
                gold = f"line {k}: {canon[k - 1]}" + (f"; {len(uniq)} distinct" if kind == "phones_dedupe" else "")
                data = "\n".join(lines)
                intro = rng.choice(["These numbers came out of a CRM export in five different formats.", "Contact list cleanup, the phone column is a mess."])
            else:  # contacts: names + emails + dedupe
                pairs = rng.sample([(f, l) for f in FN for l in LN], N - 3)
                recs = [(f, l, f"{f.lower()}.{l.lower()}@example.org") for f, l in pairs]
                dups = [recs[1], recs[4], recs[6]]
                allr = recs + dups
                rng.shuffle(allr)
                lines = []
                for f, l, e in allr:
                    sty = rng.choice(["a", "b", "c"])
                    em = rng.choice([e, e.upper(), " " + e + " "]) if sty != "c" else e.replace("example.org", "Example.org")
                    nm = f"{l}, {f}" if sty == "a" else f"{f.upper()} {l}" if sty == "b" else f"{f} {l.upper()}"
                    lines.append(f"{nm} <{em.strip()}>")
                uniq = []
                seen = set()
                for f, l, e in allr:
                    if e.lower() not in seen:
                        seen.add(e.lower())
                        uniq.append((f, l, e.lower()))
                srt = sorted(uniq, key=lambda x: (x[1].lower(), x[0].lower()))
                k = rng.randint(2, len(srt) - 1)
                ask = ("Each line is a contact: a name written as 'Last, First', 'FIRST Last' or 'First LAST', and an email in angle brackets with odd capitalisation. Two lines are duplicates if their emails match ignoring case. "
                       f"Keep the first occurrence of each duplicate, normalise the email to lower case, and sort by last name (A to Z, ignoring case, ties by first name). "
                       f"How many contacts are left, and what is the email of entry number {k} in the sorted list?")
                contains = [str(len(srt)), srt[k - 1][2]]
                gold = f"{len(srt)} contacts; entry {k}: {srt[k - 1][2]}"
                data = "\n".join(lines)
                intro = "Mailing list merge: two volunteers added the same people twice and nobody agreed on a format."
            prompt = C.chat(rng, intro, ask, C.block(data), C.register_for(rng))
            keep = C.unseen(prompt, contains, True, min_keep=1)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, d, keep, gold, fold=True, tags=["text", "cleaning"], notes={"kind": kind})
            break
        else:
            raise RuntimeError("text: no instance")
