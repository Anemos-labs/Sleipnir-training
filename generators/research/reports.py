"""Written deliverables graded by a hidden checker: a board report that must contain K of N required facts (current values,
not superseded ones), cite the right document ids and avoid the planted rumours; and a claim-by-claim fact check of a draft
press release against an incident archive."""
from __future__ import annotations

import datetime as dt

from fx import dd, family

from . import _world as W
from . import incidents as INC

PROJECTS = ["Quay wall rebuild", "Cold store extension", "Reading room refit", "Signal box replacement", "Dome re-skinning", "Pump house renewal",
            "Roof and gantry repairs", "Workshop roof replacement", "Boiler house conversion", "Staff entrance remodel", "Archive store fit-out"]
CSUF = ["Civil Ltd", "Construction Co.", "Marine Works", "Build Partners", "Engineering Ltd", "Contracts Ltd"]


def build(rng, months: int):
    org = W.make_org(rng, None, n_people=8)
    proj = f"{rng.choice(PROJECTS)} at {rng.choice(org.sites)}"
    start = W.base_date(rng)
    b0 = rng.randint(80, 600) * 10000
    c0 = start + dt.timedelta(days=rng.randint(300, 520))
    cn = rng.sample(W.NAME_WORDS, 3)
    c1, c2 = f"{cn[0]} {rng.choice(CSUF)}", f"{cn[1]} {rng.choice(CSUF)}"
    rum_contractor = f"{cn[2]} {rng.choice(CSUF)}"
    sr_dates = [dt.date(start.year, start.month, 25) + dt.timedelta(days=31 * i) for i in range(1, months + 1)]
    sr_dates = [dt.date(d.year, d.month, 25) for d in sr_dates]
    # change requests
    crs = []
    for i in range(rng.randint(2, 5)):
        d = W.rand_date(rng, sr_dates[0] - dt.timedelta(days=10), sr_dates[-1] - dt.timedelta(days=3))
        crs.append(dict(d=d, delta=rng.choice([-1, 1, 1, 1]) * rng.randint(4, 60) * 5000, status=rng.choices(["approved", "rejected", "withdrawn"], [60, 25, 15])[0]))
    crs.sort(key=lambda c: c["d"])
    for i, c in enumerate(crs, 1):
        c["no"] = i
    # contractor change
    term = None
    if rng.random() < 0.55 and months >= 5:
        term = sr_dates[rng.randint(2, months - 2)] - dt.timedelta(days=rng.randint(8, 20))
    forecasts, budgets, leads = [], [], []
    f = c0
    for d in sr_dates:
        f = f + dt.timedelta(days=rng.choice([0, 0, 7, 14, 21, 35, -7]))
        forecasts.append(f)
        budgets.append(b0 + sum(c["delta"] for c in crs if c["status"] == "approved" and c["d"] <= d))
        leads.append(c2 if term and term <= d else c1)
    # risks
    regs = []
    for i in range(1, months // 2 + 1):
        d = sr_dates[2 * i - 1] - dt.timedelta(days=rng.randint(1, 6)) if 2 * i - 1 < months else sr_dates[-1]
        risks = []
        for j in range(rng.randint(6, 11)):
            risks.append([f"R{j + 1:02d}", rng.choice(["Weather window", "Supplier delay", "Ground conditions", "Permit renewal", "Key staff loss", "Scaffold hire", "Noise complaints", "Material price", "Access road closure", "Survey error", "Crane availability"]) + f" ({j + 1})",
                          rng.choice(org.people).last, rng.choices(["open", "monitoring", "mitigated", "closed"], [40, 20, 20, 20])[0]])
        regs.append((d, risks))
    ltis = sorted(W.rand_dates(rng, rng.randint(0, 4), start + dt.timedelta(days=30), sr_dates[-1] - dt.timedelta(days=5)))
    nearmiss = sorted(W.rand_dates(rng, rng.randint(2, 6), start + dt.timedelta(days=30), sr_dates[-1] - dt.timedelta(days=5)))
    return dict(org=org, proj=proj, start=start, b0=b0, c0=c0, c1=c1, c2=c2, rum_c=rum_contractor, sr=sr_dates, crs=crs, term=term,
                forecasts=forecasts, budgets=budgets, leads=leads, regs=regs, ltis=ltis, near=nearmiss)


def render(rng, w) -> dict[str, str]:
    org = w["org"]
    files: dict[str, str] = {}
    sponsor = org.people[0]
    pm = org.people[1]
    for i, d in enumerate(w["sr"]):
        rag = rng.choice(["Green", "Amber", "Amber", "Red"])
        sid = f"SR-{d.year}-{d.month:02d}"
        files[f"status/{sid}.txt"] = dd(f"""
            {sid}  MONTHLY STATUS REPORT
            Project: {w['proj']}
            Report date: {W.d_long(d)}
            Prepared by: {pm.full}, project manager
            Sponsor: {sponsor.full}

            Approved budget: {w['budgets'][i]:,} credits
            Forecast completion: {W.d_long(w['forecasts'][i])}
            Lead contractor: {w['leads'][i]}
            Overall status: {rag}

            Notes: {W.filler_para(rng, org, 2, lo=d, hi=d + dt.timedelta(days=10))}
        """)
    for c in w["crs"]:
        sign = "increase" if c["delta"] > 0 else "decrease"
        decided = {"approved": "APPROVED by the steering group", "rejected": "REJECTED by the steering group", "withdrawn": "WITHDRAWN by the requester before decision"}[c["status"]]
        files[f"changes/CR-{c['no']}.txt"] = dd(f"""
            CR-{c['no']}  CHANGE REQUEST
            Project: {w['proj']}
            Date: {W.d_long(c['d'])}
            Requested budget {sign}: {abs(c['delta']):,} credits
            Decision: {decided}
        """)
    if w["term"]:
        files["memos/MEMO-1.txt"] = dd(f"""
            MEMO-1
            Date: {W.d_long(w['term'])}
            From: {sponsor.full}
            Subject: Change of lead contractor

            The contract with {w['c1']} is terminated with effect from the date of this memo. {w['c2']} takes over as lead contractor from the same date.
        """)
    for i, (d, risks) in enumerate(w["regs"], 1):
        rid = f"REG-{d.year}-{d.month:02d}"
        files[f"risks/{rid}.csv"] = f"# {rid} risk register, {w['proj']}, as at {W.d_iso(d)}\n" + W.csv_text(["id", "risk", "owner", "status"], risks)
    for i, d in enumerate(w["ltis"], 1):
        who = rng.choice(org.people)
        files[f"safety/LTI-{i}.txt"] = f"LTI-{i}  LOST-TIME INCIDENT\nProject: {w['proj']}\nDate: {W.d_long(d)}\nPerson affected: a site operative (name withheld)\nReported by: {who.full}\nDays lost: {rng.randint(1, 20)}\n"
    for i, d in enumerate(w["near"], 1):
        files[f"safety/NM-{i}.txt"] = f"NM-{i}  NEAR MISS (no injury, not a lost-time incident)\nProject: {w['proj']}\nDate: {W.d_long(d)}\nSummary: {rng.choice(['dropped tool', 'unsecured load', 'trip hazard', 'reversing vehicle'])}\n"
    # rumours: plausible but false figures
    rb = w["budgets"][-1] + rng.choice([-1, 1]) * rng.randint(7, 30) * 10000 + 3000
    rd = w["forecasts"][-1] + dt.timedelta(days=rng.choice([-40, -23, 29, 45, 61]))
    while rd in w["forecasts"] or rd == w["c0"]:
        rd += dt.timedelta(days=1)
    files["rumours/corridor-talk.txt"] = dd(f"""
        RUM-1  UNVERIFIED HALLWAY TALK (do not rely on this)
        Overheard in the canteen, undated:
        - "the budget is now {rb:,} credits, I saw it on someone's screen"
        - "they say completion has moved to {W.d_long(rd)}"
        - "{w['rum_c']} are taking over the site any day now"
    """)
    w["rumour"] = (rb, rd)
    W.pad_files(rng, org, files, rng.randint(3, 7), "notes", w["start"], w["sr"][-1])
    files["README.md"] = dd("""
        # Programme file

        Every record starts with its document id: `SR-yyyy-mm` monthly status reports (the latest one is the latest word on budget,
        forecast and contractor), `CR-n` change requests (only APPROVED ones change the budget), `MEMO-n` memos, `REG-yyyy-mm` risk
        registers (a risk counts as open when its status is exactly `open`), `LTI-n` lost-time incidents, `NM-n` near misses (these are
        not lost-time incidents). `rumours/` holds hearsay and is not evidence.
    """)
    return files


def facts_for(w):
    n_app = [c for c in w["crs"] if c["status"] == "approved"]
    last_sr = f"SR-{w['sr'][-1].year}-{w['sr'][-1].month:02d}"
    last_reg_d, last_risks = w["regs"][-1]
    last_reg = f"REG-{last_reg_d.year}-{last_reg_d.month:02d}"
    n_open = sum(1 for r in last_risks if r[3] == "open")
    budget, fc, lead = w["budgets"][-1], w["forecasts"][-1], w["leads"][-1]
    approved_ids = [f"CR-{c['no']}" for c in n_app]
    facts = [
        dict(id="budget", any=W.pat_money(budget), cite=[last_sr] + approved_ids[-1:], text=f"The approved budget is {budget:,} credits [{last_sr}].", label="the current approved budget"),
        dict(id="forecast", any=W.pat_date(fc), cite=[last_sr], text=f"Forecast completion is {W.d_long(fc)} [{last_sr}].", label="the forecast completion date"),
        dict(id="contractor", any=[lead.split()[0] + r"\s+" + lead.split()[1].replace(".", r"\.")], cite=[last_sr] + (["MEMO-1"] if w["term"] else []),
             text=f"The lead contractor is {lead} [{last_sr}].", label="the lead contractor"),
        dict(id="risks", any=W.pat_count_near(n_open, ["risk"]), cite=[last_reg], text=f"There are {n_open} open risks in the latest register [{last_reg}].", label="how many risks are open in the latest risk register"),
        dict(id="changes", any=W.pat_count_near(len(n_app), ["change request", "approved change", r"\bCR-\d", "changes approved"], 40), cite=approved_ids or [last_sr],
             text=f"{len(n_app)} change requests have been approved" + (f" ({', '.join(approved_ids)})" if approved_ids else "") + ".", label="how many change requests have been approved"),
        dict(id="lti", any=W.pat_count_near(len(w["ltis"]), ["lost-time", "lost time", "LTI"], 40) if w["ltis"] else W.pat_count_near(0, ["lost-time", "lost time", "LTI"], 40) + [r"no lost[- ]time"],
             cite=[f"LTI-{i}" for i in range(1, len(w["ltis"]) + 1)] or [], text=f"There have been {len(w['ltis'])} lost-time incidents" + (" [" + ", ".join(f"LTI-{i}" for i in range(1, len(w['ltis']) + 1)) + "]" if w["ltis"] else "") + ".", label="how many lost-time incidents have occurred"),
    ]
    return facts


@family("research-board-report", category="research", lang="text", kind="greenfield", n=14,
        summary="write report.md for a board from a project file: current facts only, cited document ids, no rumours")
def gen_report(rng, n):
    made = 0
    while made < n:
        months = rng.choice([6, 7, 8, 9])
        w = build(rng, months)
        files = render(rng, w)
        facts = facts_for(w)
        rb, rd = w["rumour"]
        forbid = [dict(pat=p, why="the rumoured budget") for p in W.pat_money(rb)[:2]] + [dict(pat=p, why="the rumoured completion date") for p in W.pat_date(rd)] \
            + [dict(pat=w["rum_c"].split()[0] + r"\s+" + w["rum_c"].split()[1], why="the rumoured contractor")]
        kofn = rng.random() < 0.5
        k = rng.choice([4, 5]) if kofn else 6
        words = [50, 450]
        spec = {"kind": "report", "file": "report.md", "facts": [{k_: v for k_, v in f.items() if k_ in ("id", "any", "cite")} for f in facts], "need": k,
                "forbid": forbid, "words": words, "bad_cites": ["RUM-1"]}
        topics = "; ".join(f["label"] for f in facts)
        intro = rng.choice([f"Write `report.md` for the programme board on the {w['proj']}.", f"The board meets Thursday and I need a one-page `report.md` on {w['proj']}.",
                            f"Please draft `report.md`, a short status note for the steering group on the {w['proj']} project."])
        if kofn:
            cover = f" It should cover at least {k} of these six: {topics}."
        else:
            cover = f" It must cover all of: {topics}."
        rule = rng.choice([" Use only what the records support (current figures, not superseded ones), and after each fact cite the id of the document it comes from in square brackets, for example [SR-2031-04].",
                           " Cite the source document id in square brackets after every figure, like [CR-2]. Don't repeat anything from the rumours folder, not even to debunk it. Keep it under 300 words."])
        prompt = W.voice(rng, w["org"], intro + cover + rule)
        sol = "# Programme status\n\n" + "\n\n".join(f["text"] for f in facts) + "\n"
        made += 1
        yield W.file_task(slug=f"{made:02d}-{'k' + str(k) + 'of6' if kofn else 'all6'}", prompt=prompt, difficulty=4 + (not kofn), start=files,
                          spec=spec, solution={"report.md": sol}, scored=True, tags=["report", "citations", "falsehoods"], notes={"months": months, "need": k})


# ------------------------------------------------------------------------------------------------ claim checking

@family("research-claim-check", category="research", lang="text", kind="greenfield", n=14,
        summary="check numbered claims of a draft press release against an incident archive (verdicts.json with evidence)")
def gen_claims(rng, n):
    made = 0
    while made < n:
        n_inc = rng.choice([14, 20, 26])
        org, incs, lo, hi = INC.build_world(rng, n_inc)
        files = INC.make_files(rng, org, incs, lo, hi)
        k = rng.choice([6, 8, 10])
        claims = []
        used = set()
        verdict_plan = rng.choices(["true", "false", "unsupported"], [45, 35, 20], k=k)
        for vp in verdict_plan:
            inc = rng.choice(incs)
            for _ in range(8):
                if inc.id not in used:
                    break
                inc = rng.choice(incs)
            used.add(inc.id)
            paths = [p for p in files if inc.id in p and p.startswith("incidents/")]
            kind = rng.choice(["ic", "minutes", "cause", "asset", "sev"])
            if vp == "unsupported":
                topic = rng.choice(["repair bill", "insurance excess", "number of calls to the helpline", "press coverage"])
                amt = rng.randint(2, 90) * 100
                text = f"The {topic} for {inc.id} came to {amt}."
                claims.append((text, "unsupported", []))
                continue
            true = vp == "true"
            if kind == "ic":
                other = rng.choice([p for p in org.people if p is not inc.ic])
                who = inc.ic if true else other
                text = f"{inc.id} was commanded by {who.full}."
            elif kind == "minutes":
                if true:
                    m = inc.minutes
                else:
                    m = inc.minutes + rng.choice([-1, 1]) * rng.randint(5, 40)
                    m = max(3, m)
                    if m == inc.minutes:
                        m += 11
                text = f"The outage in {inc.id} lasted {m} minutes."
            elif kind == "cause":
                if true:
                    c = inc.final_cause
                else:
                    c = inc.cause if inc.cause != inc.final_cause else rng.choice([x for x in INC.CAUSES if x != inc.final_cause])
                text = f"The final root cause of {inc.id} was {c}."
                paths = [p for p in files if inc.id in p and (p.startswith("addenda/") if inc.addendum_date else p.startswith("incidents/"))]
            elif kind == "asset":
                a = inc.asset if true else rng.choice([x for x in org.assets if x != inc.asset])
                text = f"{inc.id} affected {a}."
            else:
                sv = inc.sev if true else rng.choice([x for x in (1, 2, 3) if x != inc.sev])
                text = f"{inc.id} was graded SEV-{sv}."
            claims.append((text, "true" if true else "false", paths))
        files["draft/press-release-claims.md"] = "# Draft press release: numbered claims to verify\n\n" + "\n".join(f"{i}. {c[0]}" for i, c in enumerate(claims, 1)) + "\n"
        files["README.md"] = files["README.md"] + "\n`draft/press-release-claims.md` is a draft with numbered claims that someone wants checked against the records.\n"
        # evidence: any record file of the incident (and the addendum for causes) is acceptable
        ver = {str(i): c[1] for i, c in enumerate(claims, 1)}
        evid = {str(i): c[2] for i, c in enumerate(claims, 1) if c[1] != "unsupported"}
        fields = {"verdicts": W.jf("map", ver, sub="str", weight=3.0), "evidence": W.jf("map", evid, sub="oneof", weight=2.0, lenient_extra=True)}
        sol = {"verdicts": ver, "evidence": {i: v[0] for i, v in evid.items()}}
        ph = [f"Please fact-check the numbered claims in `draft/press-release-claims.md` against the incident records. Write `verdicts.json` with two objects keyed by claim number: `verdicts` (each `true`, `false` or `unsupported`; use unsupported when the records say nothing about it) and `evidence` (for true and false claims, the path of one record file that settles it).",
              f"Comms drafted some claims about our incidents (`draft/press-release-claims.md`). For each numbered claim tell me if the archive makes it true, false, or unsupported (not covered at all). Save `verdicts.json`: {{\"verdicts\": {{\"1\": \"true\", ...}}, \"evidence\": {{\"1\": \"incidents/...\", ...}}}}; evidence is only needed for claims that are true or false and should be a file path from the archive that proves it."]
        made += 1
        yield W.file_task(slug=f"{made:02d}-{k}-claims", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=3 + (k >= 8) + (n_inc >= 26), start=files, spec=W.json_spec(fields),
                          solution={"verdicts.json": W.dumps(sol)}, scored=True, tags=["fact-check", "evidence"], notes={"incidents": n_inc, "claims": k})
