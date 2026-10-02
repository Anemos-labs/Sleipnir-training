"""Incident archives: reports in three document styles, addenda that revise the root cause, and questions over them.

Two families share one world builder: ``research-incident-lookup`` (short answers in the final message) and
``research-incident-tally`` (multi-part answers written to a file and graded by a hidden checker)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from fx import dd, family

from . import _world as W

CAUSES = [
    "power supply failure", "expired credential", "faulty sensor", "timetable import error", "third-party damage",
    "software update regression", "handover error", "supplier delay", "overheating", "network outage",
]


@dataclass
class Incident:
    id: str
    date: dt.date
    asset: str
    sev: int
    start: int  # minutes after midnight
    minutes: int
    cause: str
    ic: W.Person
    responders: list[W.Person]
    impact: int
    followup: str
    final_cause: str = ""
    addendum_date: dt.date | None = None
    style: str = "report"

    @property
    def end(self) -> int:
        return self.start + self.minutes


def _t(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _dur_words(m: int) -> str:
    h, mm = divmod(m, 60)
    if h and mm:
        return f"{h} h {mm} min"
    return f"{h} h" if h else f"{mm} min"


def build_world(rng, n_inc: int, theme: str | None = None):
    org = W.make_org(rng, theme, n_people=rng.randint(8, 12), n_assets=rng.randint(4, 6))
    lo = W.base_date(rng)
    hi = lo + dt.timedelta(days=rng.randint(150, 330))
    dates = W.rand_dates(rng, n_inc, lo, hi, distinct=False)
    incs: list[Incident] = []
    for i, d in enumerate(dates, 1):
        dur = rng.choice([rng.randint(8, 60), rng.randint(30, 180), rng.randint(60, 480)])
        cause = rng.choice(CAUSES)
        ic = rng.choice(org.people[:7])
        resp = rng.sample([p for p in org.people if p is not ic], rng.randint(2, 4))
        inc = Incident(
            id=f"INC-{d.year}-{i:03d}", date=d, asset=rng.choice(org.assets), sev=rng.choices([1, 2, 3], [15, 35, 50])[0],
            start=rng.randint(30, 1440 - dur - 30), minutes=dur, cause=cause, ic=ic, responders=resp,
            impact=rng.randint(5, 900), followup=f"FU-{rng.randint(100, 999)}", style=rng.choice(["report", "warroom", "mail"]),
        )
        inc.final_cause = inc.cause
        if rng.random() < 0.22:
            inc.final_cause = rng.choice([c for c in CAUSES if c != cause])
            inc.addendum_date = d + dt.timedelta(days=rng.randint(4, 25))
        incs.append(inc)
    # follow-up ids must be unique
    seen = set()
    for inc in incs:
        while inc.followup in seen:
            inc.followup = f"FU-{rng.randint(100, 999)}"
        seen.add(inc.followup)
    return org, incs, lo, hi


def render(rng, org: W.Org, inc: Incident, files: dict[str, str]) -> None:
    unit = org.lex["unit"]
    resp = ", ".join(p.full for p in inc.responders)
    if inc.style == "report":
        text = dd(f"""
            INCIDENT REPORT {inc.id}
            {org.name}

            Date of incident:  {W.d_long(inc.date)}
            Asset affected:    {inc.asset}
            Severity:          SEV-{inc.sev}
            Duration:          {inc.minutes} minutes (first alert {_t(inc.start)})
            Incident commander: {inc.ic.full} ({inc.ic.role})
            Responders:        {resp}
            People/{unit} affected: {inc.impact}
            Root cause:        {inc.cause}
            Follow-up ticket:  {inc.followup}
        """)
        text += "\n" + W.filler_para(rng, org, 2, lo=inc.date, hi=inc.date + dt.timedelta(days=20)).replace(". ", ".\n") + "\n"
        files[f"incidents/{inc.id}_report.txt"] = text
    elif inc.style == "warroom":
        lines = [f"== war room log: {inc.id} ({W.d_iso(inc.date)}) =="]
        r1 = inc.responders[0]
        lines.append(f"[{_t(inc.start)}] {r1.handle}: {inc.asset} is alarming, looks bad. paging {inc.ic.first}")
        lines.append(f"[{_t(inc.start + rng.randint(1, 4))}] {inc.ic.handle}: I'll take incident command. calling this SEV-{inc.sev}.")
        for p in inc.responders[1:]:
            lines.append(f"[{_t(inc.start + rng.randint(5, max(6, inc.minutes // 2)))}] {p.handle}: joined, looking at {rng.choice(['logs', 'the panel', 'the last change', 'vendor docs'])}")
        lines.append(f"[{_t(inc.start + inc.minutes - 1)}] {inc.ic.handle}: leading theory is {inc.cause}. {inc.impact} {unit} affected as far as we can tell.")
        lines.append(f"[{_t(inc.end)}] {inc.ic.handle}: service restored. closing the room. follow-up is {inc.followup}.")
        lines.append(f"(responders on the bridge: {resp}; IC role: {inc.ic.role})")
        files[f"incidents/{inc.id}.warroom.log"] = "\n".join(lines) + "\n"
    else:
        to = [p for p in org.people if p not in inc.responders and p is not inc.ic][:2] or [org.people[0]]
        body = (f"Hello all,\n\nA short summary of {inc.id}. On {W.d_long(inc.date)} the alarm on {inc.asset} went off at {_t(inc.start)} and we were fully back "
                f"at {_t(inc.end)}, so the outage ran for {_dur_words(inc.minutes)}. It was graded SEV-{inc.sev}. About {inc.impact} {unit} were affected. "
                f"The cause was {inc.cause}. I commanded the response; {resp} helped. The follow-up is tracked as {inc.followup}.\n\n"
                f"{inc.ic.first}\n{inc.ic.role}")
        files[f"incidents/{inc.id}-summary.eml"] = W.email(org, inc.ic, to, inc.date + dt.timedelta(days=rng.randint(0, 2)), f"{inc.id} summary: {inc.asset}", body, time=W.hhmm(rng))
    if inc.addendum_date:
        ib = rng.choice(org.people[:7])
        files[f"addenda/{inc.id}-A1.txt"] = dd(f"""
            ADDENDUM A1 to {inc.id}
            Date: {W.d_long(inc.addendum_date)}
            Author: {ib.full}, {ib.role}

            Following the post-incident review the root cause of {inc.id} is reclassified from "{inc.cause}" to "{inc.final_cause}".
            All other fields of the original report stand. This classification is final.
        """)


README = dd("""
    # Incident archive

    Everything here was exported from the incident tracker of {org}.

    * `incidents/` holds one record per incident, in whichever format the commander used at the time:
      `*_report.txt` (formal report), `*.warroom.log` (chat log from the war room) or `*-summary.eml` (email summary).
    * `addenda/` holds later amendments. An addendum that reclassifies a root cause is final and overrides the original record.
    * `notes/` is general office chatter and is not part of the incident record.

    Conventions: durations are measured from the first alert to the moment service was restored. An incident belongs to
    the calendar month of its date of incident. Severity SEV-1 is the worst.
""")


def make_files(rng, org, incs, lo, hi) -> dict[str, str]:
    files: dict[str, str] = {}
    for inc in incs:
        render(rng, org, inc, files)
    W.pad_files(rng, org, files, rng.randint(6, 14), "notes", lo, hi)
    files["README.md"] = README.format(org=org.name)
    return files


def _sole_max(items, key):
    best = max(items, key=key)
    return best if sum(1 for x in items if key(x) == key(best)) == 1 else None


# ------------------------------------------------------------------------------------------------ lookup (answer mode)

def _q_ic(rng, org, incs):
    inc = rng.choice(incs)
    ph = [f"who was the incident commander for {inc.id}? Give their full name.",
          f"Who ran the response to {inc.id}? I need the name of the incident commander.",
          f"Name the person who acted as incident commander on {inc.id}."]
    return rng.choice(ph), [inc.ic.last], f"{inc.ic.full} was the incident commander of {inc.id}.", 1


def _q_followup(rng, org, incs):
    inc = rng.choice(incs)
    ph = [f"Ticket {inc.followup} is a follow-up to one of our incidents. Who commanded that incident? Full name please.",
          f"Which incident does follow-up ticket {inc.followup} belong to, and what asset did it hit? Give the incident id and the asset name.",
          f"{inc.followup} came out of an incident. What was the incident's id?"]
    k = rng.randrange(3)
    if k == 0:
        return ph[0], [inc.ic.last], f"{inc.followup} follows {inc.id}, commanded by {inc.ic.full}.", 2
    if k == 1:
        return ph[1], [inc.id, inc.asset], f"{inc.followup} belongs to {inc.id} on {inc.asset}.", 2
    return ph[2], [inc.id], f"It follows {inc.id}.", 2


def _q_longest(rng, org, incs):
    for _ in range(30):
        asset = rng.choice(org.assets)
        sub = [i for i in incs if i.asset == asset]
        if len(sub) >= 2:
            best = _sole_max(sub, lambda i: i.minutes)
            if best:
                ph = [f"Which incident had the longest outage on {asset}? Reply with the incident id.",
                      f"Of all the incidents that hit {asset}, which one kept it down the longest (id please)?",
                      f"I need the id of the worst outage (by duration) on {asset}."]
                return rng.choice(ph), [best.id], f"{best.id} was the longest on {asset} at {best.minutes} minutes.", 2 + (len(sub) > 4)
    return None


def _q_month_minutes(rng, org, incs):
    for _ in range(40):
        asset = rng.choice(org.assets)
        ref = rng.choice(incs).date
        sub = [i for i in incs if i.asset == asset and (i.date.year, i.date.month) == (ref.year, ref.month)]
        if len(sub) >= 2:
            tot = sum(i.minutes for i in sub)
            mon = f"{W.MONTHS[ref.month - 1]} {ref.year}"
            ins, c = W.numfmt(rng, tot, ("Answer", "Minutes", "Total"))
            ph = [f"What was the total downtime of {asset} in {mon}, in minutes?{ins}",
                  f"Add up the outage minutes for {asset} during {mon}. I want a single number of minutes.{ins}",
                  f"How many minutes in total was {asset} out of action in {mon}?{ins}"]
            return rng.choice(ph), [c], f"{asset} was down for a total of {tot} minutes in {mon} ({len(sub)} incidents). {c}", 3 + (len(sub) > 3)
    return None


def _q_sev1_count(rng, org, incs):
    for _ in range(40):
        p = rng.choice(org.people[:7])
        sev = rng.choice([1, 2])
        sub = [i for i in incs if i.ic is p and i.sev == sev]
        if sub:
            ins, c = W.numfmt(rng, len(sub), ("Count", "Total", "Answer"))
            ph = [f"How many SEV-{sev} incidents did {p.full} command?{ins}",
                  f"Count the SEV-{sev} incidents where {p.full} was the incident commander.{ins}",
                  f"{p.full}: how many SEV-{sev}s as incident commander?{ins}"]
            return rng.choice(ph), [c], f"{p.full} commanded {len(sub)} SEV-{sev} incidents. {c}", 3
    return None


def _q_final_cause(rng, org, incs):
    revised = [i for i in incs if i.addendum_date]
    if not revised:
        return None
    inc = rng.choice(revised)
    sub = [i for i in incs if i.final_cause == inc.final_cause]
    if len(sub) != 1:
        # ask for the unique one differently: which incident hit this asset and was finally attributed to this cause
        sub = [i for i in sub if i.asset == inc.asset]
        if len(sub) != 1:
            return None
        ph = [f"Which incident on {inc.asset} was finally attributed to \"{inc.final_cause}\"? Give the id.",
              f"On {inc.asset}, one incident ended up classed as \"{inc.final_cause}\" after review. Which id?"]
    else:
        ph = [f"Which incident was ultimately classified as \"{inc.final_cause}\"? Give the id.",
              f"One incident in the archive ended up with the root cause \"{inc.final_cause}\" (after any review). Which one?"]
    return rng.choice(ph), [inc.id], f"{inc.id} carries the final root cause \"{inc.final_cause}\".", 3


def _q_cmd_longest(rng, org, incs):
    for _ in range(30):
        ref = rng.choice(incs)
        sub = [i for i in incs if i.ic is ref.ic]
        best = _sole_max(sub, lambda i: i.minutes) if len(sub) >= 3 else None
        if best and best is not ref:
            ph = [f"The person who commanded {ref.id} has run several incidents. Which of theirs lasted the longest? Give the incident id.",
                  f"Take whoever was incident commander on {ref.id}: among all incidents they commanded, which was the longest-running (id)?"]
            return rng.choice(ph), [best.id], f"{ref.ic.full} commanded {best.id} ({best.minutes} min), their longest.", 3
    return None


def _q_most_responder(rng, org, incs):
    cnt = {}
    for i in incs:
        for p in i.responders:
            cnt[p.full] = cnt.get(p.full, 0) + 1
    best = _sole_max(list(cnt.items()), lambda kv: kv[1])
    if not best:
        return None
    p = next(p for p in org.people if p.full == best[0])
    ph = ["Who shows up most often as a responder (not incident commander) across all the incidents? Full name, please.",
          "Across every incident record, which person is listed as a responder the most times (commanders don't count unless also listed as a responder)?"]
    return rng.choice(ph), [p.last], f"{p.full} appears as a responder in {best[1]} incidents.", 4


def _q_impact_cause(rng, org, incs):
    for _ in range(30):
        cause = rng.choice(CAUSES)
        sub = [i for i in incs if i.final_cause == cause]
        best = _sole_max(sub, lambda i: i.impact) if len(sub) >= 2 else None
        if best:
            ph = [f"Among the incidents whose final root cause is \"{cause}\", which affected the most people/units? Reply with the id.",
                  f"Looking only at incidents finally attributed to \"{cause}\": which had the largest impact figure? Id, please."]
            return rng.choice(ph), [best.id], f"{best.id} (impact {best.impact}).", 3 + (len(sub) > 4)
    return None


Q_LOOKUP = [_q_ic, _q_followup, _q_longest, _q_month_minutes, _q_sev1_count, _q_final_cause, _q_cmd_longest, _q_most_responder, _q_impact_cause]
Q_WEIGHTS = [4, 3, 3, 3, 2, 3, 2, 1, 2]


@family("research-incident-lookup", category="research", lang="text", kind="lookup", n=20, mode="answer",
        summary="short factual questions over an incident archive with reports in three formats and later addenda")
def gen_lookup(rng, n):
    made = 0
    k = 0
    while made < n:
        k += 1
        n_inc = rng.choice([8, 10, 14, 20, 26, 34, 42])
        org, incs, lo, hi = build_world(rng, n_inc)
        files = make_files(rng, org, incs, lo, hi)
        q = None
        for _ in range(12):
            fn = rng.choices(Q_LOOKUP, Q_WEIGHTS)[0]
            q = fn(rng, org, incs)
            if q:
                break
        if not q:
            continue
        body, contains, gold, d = q
        prompt = W.voice(rng, org, body, lead=rng.choice(["", "", "Going by the incident archive (README.md explains the layout),", "In `incidents/` and the other folders here,"]))
        if n_inc >= 34:
            d = min(5, d + 1)
        elif n_inc <= 10:
            d = max(1, d - 1)
        made += 1
        yield W.say_task(slug=f"{made:02d}-{fn.__name__[3:].replace('_', '-')}", prompt=prompt, difficulty=d, start=files, contains=contains, gold=gold,
                         tags=["incidents", fn.__name__[3:]], notes={"theme": org.theme, "incidents": n_inc, "question": fn.__name__})


# ------------------------------------------------------------------------------------------------ tally (file-delivered)

def _tally_assets(rng, org, incs):
    """json: for one asset, count, total minutes, worst severity, longest incident id"""
    for _ in range(40):
        asset = rng.choice(org.assets)
        sub = [i for i in incs if i.asset == asset]
        best = _sole_max(sub, lambda i: i.minutes) if len(sub) >= 3 else None
        if best:
            exp = {"incidents": len(sub), "total_minutes": sum(i.minutes for i in sub), "worst_severity": min(i.sev for i in sub), "longest": best.id}
            fields = {"incidents": W.jf("int", exp["incidents"]), "total_minutes": W.jf("int", exp["total_minutes"]),
                      "worst_severity": W.jf("int", exp["worst_severity"]), "longest": W.jf("str", exp["longest"])}
            ph = [f"For {asset}, write `answer.json` with the keys `incidents` (how many incidents hit it), `total_minutes` (their combined duration), "
                  f"`worst_severity` (the SEV number of the worst one; 1 is worst) and `longest` (id of the longest incident).",
                  f"I'm preparing an asset review of {asset}. Please create `answer.json` in the repo root: {{\"incidents\": <count>, \"total_minutes\": <sum of durations>, "
                  f"\"worst_severity\": <number 1-3>, \"longest\": \"<incident id>\"}}, covering every incident on that asset in the archive."]
            return rng.choice(ph), W.json_spec(fields), W.dumps(exp), 2 + (len(incs) > 20) + (len(sub) > 5), "asset"
    return None


def _tally_commanders(rng, org, incs):
    """json: map commander surname -> number of incidents commanded (all commanders)"""
    cnt = {}
    for i in incs:
        cnt[i.ic.last] = cnt.get(i.ic.last, 0) + 1
    fields = {"commanded": W.jf("map", cnt, sub="int")}
    ph = ["Make me a tally of how many incidents each person commanded. Write it to `answer.json` as {\"commanded\": {\"<surname>\": <count>, ...}}, one entry per commander (surname only).",
          "Please write `answer.json` with a single key `commanded`: an object mapping the surname of every incident commander to the number of incidents they commanded."]
    return rng.choice(ph), W.json_spec(fields), W.dumps({"commanded": cnt}), 2 + (len(incs) > 14) + (len(incs) > 30), "commanders"


def _tally_final_causes(rng, org, incs):
    """csv: final root cause, count, total minutes (sorted by count desc then name)"""
    agg = {}
    for i in incs:
        c, m = agg.get(i.final_cause, (0, 0))
        agg[i.final_cause] = (c + 1, m + i.minutes)
    rows = sorted(([k, v[0], v[1]] for k, v in agg.items()), key=lambda r: (-r[1], r[0]))
    csvt = W.csv_text(["root_cause", "incidents", "total_minutes"], rows)
    spec = W.csv_spec(["root_cause", "incidents", "total_minutes"], ["str", "int", "int"], rows, key=[0])
    ph = ["Summarise the archive by *final* root cause (after addenda): write `out.csv` with the header `root_cause,incidents,total_minutes` and one row per cause that occurs at least once.",
          "I need `out.csv` listing each final root cause with how many incidents it explains and their combined downtime in minutes. Columns: root_cause, incidents, total_minutes. Header row required."]
    return rng.choice(ph), spec, csvt, 3 + (len(incs) > 20), "causes"


def _tally_month(rng, org, incs):
    """json: per-month incident counts for sev 1 and 2 combined"""
    cnt = {}
    for i in incs:
        if i.sev <= 2:
            key = f"{i.date.year}-{i.date.month:02d}"
            cnt[key] = cnt.get(key, 0) + 1
    fields = {"per_month": W.jf("map", cnt, sub="int")}
    ph = ["Count SEV-1 and SEV-2 incidents per calendar month. Save it as `answer.json`: {\"per_month\": {\"YYYY-MM\": count}}; leave out months with none.",
          "For the board pack: how many SEV-1 or SEV-2 incidents happened in each month? Put it in `answer.json` under the key `per_month` (keys like `2031-04`, only months that have at least one)."]
    return rng.choice(ph), W.json_spec(fields), W.dumps({"per_month": cnt}), 2 + (len(incs) > 14) + (len(incs) > 30), "months"


Q_TALLY = [_tally_assets, _tally_commanders, _tally_final_causes, _tally_month]


@family("research-incident-tally", category="research", lang="text", kind="greenfield", n=16,
        summary="aggregate an incident archive into answer.json or out.csv (per asset, commander, cause, month)")
def gen_tally(rng, n):
    made = 0
    while made < n:
        n_inc = rng.choice([8, 12, 16, 22, 30, 40])
        org, incs, lo, hi = build_world(rng, n_inc)
        files = make_files(rng, org, incs, lo, hi)
        fn = Q_TALLY[made % len(Q_TALLY)]
        q = fn(rng, org, incs)
        if not q:
            continue
        body, spec, sol, d, label = q
        solfile = spec["file"]
        prompt = W.voice(rng, org, body)
        made += 1
        yield W.file_task(slug=f"{made:02d}-{label}", prompt=prompt, difficulty=d, start=files, spec=spec, solution={solfile: sol},
                          tags=["incidents", "aggregation", label], notes={"theme": org.theme, "incidents": n_inc})
