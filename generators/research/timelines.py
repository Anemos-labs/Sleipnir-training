"""Project timelines reconstructed from messages that give dates relatively ("yesterday", "last Tuesday", "5 days ago")
or as plans that later slipped. Two families: ``research-timeline-rollout`` writes timeline.json (graded by position),
``research-timeline-gaps`` asks day counts between events."""
from __future__ import annotations

import datetime as dt

from fx import dd, family

from . import _world as W

# (code, description, [sentence templates ending with {when}])
EVENTS = [
    ("kickoff", "the project kickoff meeting took place", ["We held the kickoff meeting {when}.", "The project kicked off {when}."]),
    ("vendor-chosen", "the vendor was selected", ["The vendor was selected {when}; contracts to follow.", "We signed off on the vendor {when}."]),
    ("training", "staff training was run", ["The first staff training session ran {when}.", "Training for the floor staff took place {when}."]),
    ("pilot-start", "the pilot started", ["The pilot started {when}.", "We switched the pilot group over {when}."]),
    ("pilot-end", "the pilot ended", ["The pilot wrapped up {when}.", "We stopped the pilot {when} and collected feedback."]),
    ("incident", "the first production incident happened", ["The first production incident hit {when}.", "We had the outage {when}."]),
    ("rollback", "the rollback to the old system happened", ["We rolled back to the old system {when}.", "The rollback was carried out {when}."]),
    ("retry", "the second attempt started", ["The second attempt began {when}.", "We restarted the rollout {when}."]),
    ("go-live", "full go-live happened", ["Go-live happened {when}.", "We went live for everyone {when}."]),
    ("retro", "the retrospective was held", ["The retrospective was held {when}.", "We ran the retro {when}."]),
]
ORDER = [e[0] for e in EVENTS]
PLAN_T = ["We are aiming to {act} on {date}.", "The current plan is to {act} on {date}.", "Target date to {act}: {date}."]
ACT = {"kickoff": "hold the kickoff", "vendor-chosen": "pick the vendor", "training": "run training", "pilot-start": "start the pilot", "pilot-end": "end the pilot",
       "incident": "freeze changes", "rollback": "finish the migration", "retry": "restart the rollout", "go-live": "go live", "retro": "hold the retro"}


def when_expr(rng, doc: dt.date, ev: dt.date) -> str:
    delta = (doc - ev).days
    opts = [f"on {W.d_long(ev)}", f"on {W.d_us(ev)}"]
    if delta == 0:
        opts += ["this morning", "today"]
    if delta == 1:
        opts += ["yesterday", "yesterday"]
    if 1 <= delta <= 7:
        opts += [f"last {W.WEEKDAYS[ev.weekday()]}", f"last {W.WEEKDAYS[ev.weekday()]}"]
    if 2 <= delta <= 14:
        opts += [f"{delta} days ago", f"{delta} days ago"]
    return rng.choice(opts)


def build(rng, k: int):
    org = W.make_org(rng, None, n_people=8)
    idx = sorted(rng.sample(range(len(EVENTS)), k))
    # keep the causal order of the chosen events
    evs = [EVENTS[i] for i in idx]
    d = W.base_date(rng)
    dates = {}
    for code, _, _ in evs:
        d = d + dt.timedelta(days=rng.randint(3, 30))
        dates[code] = d
    return org, evs, dates


def render(rng, org, evs, dates):
    files: dict[str, str] = {}
    n = 0
    sched = []  # (doc_date, [(code, when-sentence)])
    for code, _, temps in evs:
        ev = dates[code]
        for _ in range(rng.choice([1, 2, 2])):
            off = rng.choice([0, 1, 1, 2, 3, 4, 5, 6, 7, 9, 12])
            doc = ev + dt.timedelta(days=off)
            sched.append([doc, [(code, rng.choice(temps).format(when=when_expr(rng, doc, ev)))]])
    # merge a few documents that fall on the same day, so a document may mention two events
    sched.sort(key=lambda x: x[0])
    merged = []
    for s in sched:
        if merged and merged[-1][0] == s[0] and rng.random() < 0.6:
            merged[-1][1].extend(s[1])
        else:
            merged.append(s)
    for doc, sents in merged:
        n += 1
        p, q = rng.sample(org.people, 2)
        style = rng.choice(["mail", "note", "ticket"])
        text_s = " ".join(x[1] for x in sents)
        extra = W.filler_line(rng, org, lo=doc, hi=doc + dt.timedelta(days=15))
        if style == "mail":
            files[f"messages/{W.d_iso(doc)}-{n:02d}.eml"] = W.email(org, p, [q], doc, rng.choice(["status", "quick update", "rollout", "for the record"]), f"Hi {q.first},\n\n{text_s} {extra}\n\n{p.first}", time=W.hhmm(rng))
        elif style == "note":
            files[f"notes/{W.d_iso(doc)}-{n:02d}.txt"] = f"Meeting notes, {W.d_long(doc)} (taken by {p.full})\n\n- {text_s}\n- {extra}\n"
        else:
            files[f"tickets/R-{200 + n}.txt"] = f"R-{200 + n}: rollout tracking\nCreated {W.d_iso(doc - dt.timedelta(days=rng.randint(0, 3)))}\n\n[{W.d_iso(doc)} {W.hhmm(rng)}] {p.handle}: {text_s}\n"
    # plans that slipped: dated before the event, naming a different date
    plannable = [e for e in evs if e[0] in ACT and e[0] not in ("incident", "rollback")]
    for code, _, _ in rng.sample(plannable, min(len(plannable), rng.randint(2, 3))):
        ev = dates[code]
        doc = ev - dt.timedelta(days=rng.randint(10, 25))
        planned = ev + dt.timedelta(days=rng.choice([-9, -6, -3, 4, 8, 11]))
        if planned == doc:
            continue
        n += 1
        p = rng.choice(org.people)
        files[f"messages/{W.d_iso(doc)}-plan-{n:02d}.txt"] = f"From: {p.full}\nDate: {W.d_iso(doc)}\n\n" + rng.choice(PLAN_T).format(act=ACT[code], date=W.d_long(planned)) + " (Plan only; this may move.)\n"
    W.pad_files(rng, org, files, rng.randint(3, 8), "notes/misc", min(dates.values()) - dt.timedelta(days=30), max(dates.values()) + dt.timedelta(days=30))
    files["README.md"] = dd("""
        # Rollout paper trail

        Messages, meeting notes and tracker comments about one rollout. Each message is dated (its header, its title line or its
        entry timestamp). Relative dates are relative to that date: "yesterday" is the day before; "N days ago" is N days
        before; "last <weekday>" is the most recent such weekday strictly before the message date; "today" and "this morning" are
        the message date. A statement of a plan or a target ("we aim to...") is not an event; an event happened on the day
        the documents say it actually happened.
    """)
    return files


@family("research-timeline-rollout", category="research", lang="text", kind="greenfield", n=18,
        summary="reconstruct the dated event timeline of a rollout from relative dates and slipped plans (timeline.json)")
def gen(rng, n):
    made = 0
    while made < n:
        k = rng.choice([5, 6, 7, 8])
        org, evs, dates = build(rng, k)
        files = render(rng, org, evs, dates)
        rows = [[c, W.d_iso(dates[c])] for c, _, _ in evs]
        rows.sort(key=lambda r: r[1])
        if len({r[1] for r in rows}) != len(rows):
            continue
        spec = W.seq_spec("timeline", [["event", "str"], ["date", "date"]], rows)
        listing = "; ".join(f"`{c}` ({d})" for c, d, _ in evs)
        ph = [f"Reconstruct when the milestones of this rollout actually happened. Write `timeline.json` as {{\"timeline\": [{{\"event\": \"kickoff\", \"date\": \"2031-03-04\"}}, ...]}}, oldest first, one entry per event, dates in ISO format. Events (use these names): {listing}.",
              f"Our rollout record is a mess of emails and notes. Please produce `timeline.json`: a chronological list under the key `timeline`, each item with `event` and `date` (YYYY-MM-DD). Events to cover, using exactly these ids: {listing}.",
              f"Put the following events in the order they really happened and give each its actual date (not a planned one): {listing}. Save as `timeline.json` ({{\"timeline\": [{{\"event\": ..., \"date\": ...}}]}})."]
        made += 1
        sol = W.dumps({"timeline": [{"event": r[0], "date": r[1]} for r in rows]})
        yield W.file_task(slug=f"{made:02d}-{k}-events", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=3 + (k >= 6) + (k >= 8), start=files, spec=spec,
                          solution={"timeline.json": sol}, scored=True, tags=["timeline", "temporal"], notes={"events": k})


@family("research-timeline-gaps", category="research", lang="text", kind="lookup", n=14, mode="answer",
        summary="day counts between two milestones of a rollout whose dates are given relatively or as slipped plans")
def gen_gaps(rng, n):
    made = 0
    while made < n:
        k = rng.choice([5, 6, 7])
        org, evs, dates = build(rng, k)
        files = render(rng, org, evs, dates)
        a, b = rng.sample([c for c, _, _ in evs], 2)
        if dates[a] > dates[b]:
            a, b = b, a
        gap = (dates[b] - dates[a]).days
        desc = {c: d for c, d, _ in evs}
        qk = rng.choice(["gap", "date"])
        if qk == "gap":
            ins, c = W.numfmt(rng, gap, ("Days", "Answer", "Gap"))
            ph = [f"How many days passed between the moment {desc[a]} and the moment {desc[b]} (actual dates)?{ins}",
                  f"Count the days from the event where {desc[a]} to the one where {desc[b]}. Use the real dates, not the plans.{ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"{gap} days. {c}"
        else:
            ph = [f"On what date did it happen that {desc[a]}? Reply in YYYY-MM-DD; plans don't count, only what really happened.",
                  f"Give me the actual date (ISO) on which {desc[a]}."]
            prompt, contains, gold = rng.choice(ph), [W.d_iso(dates[a])], f"It happened on {W.d_iso(dates[a])}."
        made += 1
        yield W.say_task(slug=f"{made:02d}-{qk}", prompt=W.voice(rng, org, prompt), difficulty=3 + (k >= 6) + (qk == "gap"), start=files, contains=contains, gold=gold,
                         tags=["timeline", "temporal"], notes={"events": k, "question": qk})
