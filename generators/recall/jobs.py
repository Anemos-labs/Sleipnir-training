"""Memory across a long job. ``recall-read-then-job``: read a fact (or three) first, do a long unrelated CSV job, then state
the fact. ``recall-prompt-constraint``: a formatting rule given at the start of the prompt must still hold in every file
written at the end of a long reading job (checked by a hidden checker)."""
from __future__ import annotations

import datetime as dt
import re

from fx import dd, family

from generators.research import _world as W
from . import _recall as R

# ---------------------------------------------------------------------------------------------------------------- read then job

FACTS = [
    ("codename", "release codename", lambda rng: f"{rng.choice(W.NAME_WORDS).upper()}-{rng.choice(W.NAME_WORDS).upper()}-{rng.randint(10, 99)}"),
    ("gate", "gate code", lambda rng: str(rng.randint(1000, 9999))),
    ("ext", "on-call extension", lambda rng: str(rng.randint(2000, 8999))),
    ("ref", "reference number", lambda rng: R.code(rng)),
    ("date", "handover date", None),
]


def make_data(rng, org, k: int, win):
    files, rows_out = {}, []
    per = max(6, int(R.target_chars(win, rng.choice([1.0, 1.25, 1.5])) / k / 34))
    names = []
    while len(names) < k:
        nm = f"{W.slugify(rng.choice(org.sites), 14)}-{rng.randint(2031, 2034)}-{rng.randint(1, 12):02d}"
        if nm not in names:
            names.append(nm)
    for nm in sorted(names):
        rows = []
        total = 0
        for _ in range(rng.randint(per // 2 + 2, per + 4)):
            d = dt.date(2031, rng.randint(1, 12), rng.randint(1, 28))
            qty = rng.randint(1, 40)
            price = rng.randint(120, 9900)
            total += qty * price
            rows.append([W.d_iso(d), rng.choice(["bolts", "gloves", "filters", "labels", "tape", "lamps", "straps", "tags", "seals", "paint"]), qty, f"{price // 100}.{price % 100:02d}"])
        files[f"data/{nm}.csv"] = W.csv_text(["date", "item", "qty", "unit_price"], rows)
        rows_out.append([f"{nm}.csv", len(rows), f"{total // 100}.{total % 100:02d}"])
    return files, rows_out


@family("recall-read-then-job", category="recall", lang="text", kind="lookup", n=22, mode="answer",
        summary="read a fact (or three) in a briefing first, finish a long CSV summarising job, then state the fact; the job output is also checked")
def gen_rtj(rng, n):
    made = 0
    while made < n:
        org = W.make_org(rng, None, n_people=7, n_sites=8)
        tier = R.tier(rng)
        win = 8000 if tier == "easy" else (R.window(rng) or 12000)
        k = rng.choice([6, 8, 10]) if tier == "easy" else (rng.choice([18, 24, 30, 38]) if win <= 16000 else rng.choice([40, 48]))
        files, rows_out = make_data(rng, org, k, win)
        nf = 1 if tier == "easy" else rng.choice([1, 1, 1, 3])
        picks = rng.sample(FACTS, nf)
        vals = []
        decoys = []
        lines = ["BATCH BRIEFING", ""]
        for key, label, mk in picks:
            if key == "date":
                d = W.rand_date(rng, dt.date(2031, 6, 1), dt.date(2033, 12, 1))
                v, shown = W.d_iso(d), W.d_long(d)
                dec = W.d_long(d + dt.timedelta(days=rng.choice([-14, 7, 21])))
            else:
                v = mk(rng)
                shown = v
                dec = mk(rng)
            vals.append((key, label, v))
            lines.append(f"The {label} for this batch is {shown}. (The retired one, {dec}, must not be used any more.)")
            lines.append(W.filler_line(rng, org))
        lines.append("")
        files["briefing/START-HERE.txt"] = "\n".join(lines) + "\n"
        files["briefing/JOB.md"] = dd("""
            # The filing job

            `data/` holds one CSV per site-month with the columns `date,item,qty,unit_price`.

            Write `summary.csv` with the header `file,rows,total` and one row per CSV in `data/`:

            * `file`: the file name (like `quay-2031-04.csv`, no folder),
            * `rows`: the number of data rows (the header does not count),
            * `total`: the sum of `qty * unit_price` over its rows, with two decimals.

            Rows may be in any order. Nothing else is needed.
        """)
        W.pad_files(rng, org, files, rng.randint(2, 5), "briefing/misc", dt.date(2031, 1, 1), dt.date(2031, 12, 1))
        spec = W.csv_spec(["file", "rows", "total"], ["str", "int", "num"], rows_out, key=[0], tol=0.004, file="summary.csv")
        labels = ", ".join(l for _, l, _ in vals)
        if nf == 1:
            lab = vals[0][1]
            prompt = rng.choice([f"First, open `briefing/START-HERE.txt` and take note of the {lab}; I'll ask you for it when you're done. Then do the job in `briefing/JOB.md`. When it's finished, tell me the {lab}.",
                                 f"Two things. (1) Do the filing job described in `briefing/JOB.md`. (2) Before you start, read `briefing/START-HERE.txt`: it has this batch's {lab}, and I want you to report it back to me at the very end.",
                                 f"Please start by reading the batch briefing (`briefing/START-HERE.txt`) for the {lab}. Don't write it anywhere. Then complete the job in `briefing/JOB.md` and, in your last message, repeat the {lab}."])
        else:
            prompt = rng.choice([f"Read `briefing/START-HERE.txt` first: it gives the {labels}. Then do the job in `briefing/JOB.md`. At the end, in your last message, give me all three again.",
                                 f"Please remember the {labels} from `briefing/START-HERE.txt` (don't write them down anywhere). Once the job in `briefing/JOB.md` is done, tell me all three."])
        contains = [v for _, _, v in vals]
        if any(c in prompt for c in contains):
            continue
        gold = "Done; summary.csv is written. " + "; ".join(f"{l}: {v}" for _, l, v in vals)
        made += 1
        # date facts: the answer must be ISO, say so
        if any(k_ == "date" for k_, _, _ in vals):
            prompt += " (Give the date as YYYY-MM-DD.)"
        d = 2 + (nf == 3) + (tier == "hard") + (k >= 30)
        yield W.say_task(slug=f"{made:02d}-{nf}fact-{k}files", prompt=W.voice(rng, org, prompt, closers=False, sentence=True), difficulty=min(5, d), start=files, contains=contains, gold=gold,
                         context_window=None if tier == "easy" else win, verify=f"python3 {W.CHECK_PATH}", hidden=W.checker(spec), solution={"summary.csv": W.csv_text(["file", "rows", "total"], rows_out)},
                         tags=["memory", "long-job"], notes={"files": k, "facts": [k_ for k_, _, _ in vals]})


# ---------------------------------------------------------------------------------------------------------------- prompt constraint

def _constraint(rng, org):
    tag = f"{rng.choice(['Q', 'R', 'T'])}{rng.randint(1, 4)}-{rng.choice(W.NAME_WORDS).upper()[:6]}"
    sig = rng.choice(org.people).full
    kinds = [
        dict(key="tag", text=f"Whatever else you do: the very first line of every file you put in `out/` must be exactly `[batch: {tag}]`.",
             must=[rf"\A\[batch: {re.escape(tag)}\]"], must_not=[], prefix="", note=tag),
        dict(key="signature", text=f"One rule for everything you put in `out/`: each file must end with the line `-- reviewed by {sig}` (as its last line).",
             must=[rf"-- reviewed by {re.escape(sig)}\s*\Z"], must_not=[], prefix="", note=sig),
        dict(key="forbid", text="Rule for anything you put in `out/`: never use the word \"delivery\" or \"delivered\" in it (say \"received\" instead).",
             must=[], must_not=[r"(?i)deliver"], prefix="", note="deliver"),
        dict(key="width", text="Formatting rule: no line in any file you put in `out/` may be longer than 40 characters.",
             must=[], must_not=[r"^.{41,}$"], prefix="", note="40"),
        dict(key="prefix", text="Naming rule: every file name in `out/` must start with `q3_` (so `out/q3_<site>.txt`).",
             must=[], must_not=[], prefix="q3_", note="q3_"),
        dict(key="upper", text="Style rule: every file you put in `out/` must be written entirely in UPPER CASE (letters), including labels.",
             must=[], must_not=[r"[a-z]"], prefix="", note="upper"),
    ]
    return rng.choice(kinds)


@family("recall-prompt-constraint", category="recall", lang="text", kind="greenfield", n=20,
        summary="a formatting rule stated at the top of the prompt must hold in every output file written after a long reading job")
def gen_pc(rng, n):
    made = 0
    while made < n:
        org = W.make_org(rng, None, n_people=7, n_sites=rng.choice([3, 4, 5]))
        tier = R.tier(rng)
        win = 8000 if tier == "easy" else (R.window(rng) or 12000)
        con = _constraint(rng, org)
        sites = org.sites
        nrep = rng.choice([5, 7, 9]) if tier == "easy" else (rng.choice([18, 26, 34]) if win <= 16000 else 44)
        per_site_lines = 6 if tier == "easy" else max(4, int(R.target_chars(win, rng.choice([1.0, 1.25, 1.5])) / nrep / 70 / 1))
        files: dict[str, str] = {}
        stats = {s: {"total": 0, "best": (0, None)} for s in sites}
        dates = W.rand_dates(rng, nrep, dt.date(2031, 1, 1), dt.date(2031, 12, 28), distinct=False)
        for i, d in enumerate(dates):
            lines = [f"DAILY RECEIVING LOG {W.d_iso(d)}", ""]
            for _ in range(rng.randint(per_site_lines // 2 + 1, per_site_lines + 2)):
                s = rng.choice(sites)
                q = rng.randint(5, 400)
                lines.append(f"{rng.choice(['08', '09', '10', '11', '13', '14', '15'])}:{rng.randint(10, 59)} | {s} | received {q} units | driver {rng.choice(org.people).last}")
                st = stats[s]
                st["total"] += q
                if q > st["best"][0] or (q == st["best"][0] and d < st["best"][1]):
                    st["best"] = (q, d)
            files[f"logs/{W.d_iso(d)}-{i:02d}.txt"] = "\n".join(lines) + "\n" + "# " + W.filler_line(rng, org) + "\n"
        # the biggest receipt of each site must be a single line (no ties)
        tie = False
        for s in sites:
            q = stats[s]["best"][0]
            n_hit = 0
            for p, t in files.items():
                if p.startswith("logs/"):
                    n_hit += sum(1 for ln in t.split("\n") if f"| {s} | received {q} units" in ln)
            if n_hit != 1:
                tie = True
        if tie:
            continue
        files["README.md"] = "# Receiving logs\n\nOne file per day in `logs/`. Each line: time | site | received N units | driver.\n"
        ex = con["prefix"]
        outfiles = []
        sol = {}
        for s in sites:
            slug = W.slugify(s, 20)
            path = f"out/{ex}{slug}.txt"
            tot, (q, d) = stats[s]["total"], stats[s]["best"]
            label_t, label_b = "Total units", "Biggest receipt"
            body = [f"{label_t}: {tot}", f"{label_b}: {W.d_iso(d)} ({q} units)"]
            if con["key"] == "upper":
                body = [x.upper() for x in body]
            if con["key"] == "tag":
                body.insert(0, f"[batch: {con['note']}]")
            if con["key"] == "signature":
                body.append(f"-- reviewed by {con['note']}")
            text = "\n".join(body) + "\n"
            sol[path] = text
            lab_t = r"(?i)total units:\s*" if con["key"] == "upper" else r"Total units:\s*"
            lab_b = r"(?i)biggest receipt:\s*" if con["key"] == "upper" else r"Biggest receipt:\s*"
            outfiles.append(dict(path=path, must=[lab_t + str(tot) + r"\b", lab_b + W.d_iso(d)] + con["must"], must_not=con["must_not"]))
        spec = {"kind": "files", "files": outfiles}
        site_list = ", ".join(sites)
        job = rng.choice([
            f"Then the job: the receiving logs in `logs/` cover our sites ({site_list}). For each site write `out/<name>.txt` (name = the site name in lowercase with dashes) containing two lines: `Total units: <sum of all units received at that site>` and `Biggest receipt: <YYYY-MM-DD> (<units> units)` for the day of its single largest receipt line.",
            f"The job: go through every file in `logs/` and, for each of our sites ({site_list}), write one file `out/<site slug>.txt` (lowercase, words joined by dashes) with `Total units: N` on the first content line and `Biggest receipt: YYYY-MM-DD (M units)` on the next, for that site's largest single receipt."])
        prompt = con["text"] + " " + job
        d = 2 + (tier == "mid") + 2 * (tier == "hard") + (con["key"] in ("width", "upper", "signature")) - (tier == "easy")
        made += 1
        yield W.file_task(slug=f"{made:02d}-{con['key']}", prompt=W.voice(rng, org, prompt, closers=False, sentence=True), difficulty=min(5, d), start=files, spec=spec, solution=sol,
                          scored=True, context_window=None if tier == "easy" else win, tags=["memory", "constraint"], notes={"constraint": con["key"], "logs": nrep})
