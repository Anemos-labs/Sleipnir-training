"""Entity resolution: the same person appears as a full name, "F. Last", a nickname, a handle, an email address or a
rotating job title. Tickets say who resolved them; the agent must resolve every alias (a directory and an appointments
memo are provided) and aggregate. File-delivered answers."""
from __future__ import annotations

import datetime as dt

from fx import dd, family

from . import _world as W


def build(rng, n_tickets: int):
    org = W.make_org(rng, None, n_people=rng.randint(8, 10))
    people = org.people
    # a namesake pair: same surname, different initials
    if rng.random() < 0.6:
        a, b = people[2], people[3]
        b.last = a.last
        if a.first[0] == b.first[0]:
            b.first = next(f for f in W.FIRST if f[0] != a.first[0] and f not in {p.first for p in people})
        used = {x.nick for x in people if x is not b}
        b.nick = next(c for c in (b.first[:3], b.first[:4], b.first[:2] + b.first[-1], b.first[:5]) if c not in used)
    titles = rng.sample(org.lex["titles"], 2)
    d0 = W.base_date(rng)
    d_end = d0 + dt.timedelta(days=rng.randint(200, 300))
    # rotating titles: holder A until the changeover, B after
    appoint = []
    holders = {}
    for t in titles:
        a, b = rng.sample(people, 2)
        change = d0 + dt.timedelta(days=rng.randint(60, 160))
        holders[t] = (a, b, change)
        appoint.append((t, a, b, change))
    tickets = []
    dates = W.rand_dates(rng, n_tickets, d0 + dt.timedelta(days=5), d_end, distinct=False)
    weights = [rng.randint(1, 6) for _ in people]
    for i, d in enumerate(dates):
        tno = 1000 + i * rng.randint(1, 3) + i
        resolver = rng.choices(people, weights)[0]
        form = rng.choice(["full", "full", "initial", "nick", "handle", "email", "title"])
        title = None
        if form == "title":
            # only if the resolver holds a rotating title on that date
            cand = [t for t, (a, b, ch) in holders.items() if (a if d < ch else b) is resolver]
            if cand:
                title = rng.choice(cand)
            else:
                form = "full"
        tickets.append(dict(no=tno, date=d, resolver=resolver, form=form, title=title,
                            assignee=rng.choice(people), reporter=rng.choice(people)))
    # unique ticket numbers
    seen = set()
    for t in tickets:
        while t["no"] in seen:
            t["no"] += 1
        seen.add(t["no"])
    return org, people, holders, appoint, tickets, d0, d_end


def alias(p: W.Person, form: str, org, title=None) -> str:
    if form == "full":
        return p.full
    if form == "initial":
        return p.fl
    if form == "nick":
        return p.nick
    if form == "handle":
        return "@" + p.handle
    if form == "email":
        return p.email(org.domain)
    return f"the {title}"


def render(rng, org, people, holders, appoint, tickets, d0, d_end):
    files: dict[str, str] = {}
    files["directory.csv"] = W.csv_text(["name", "handle", "nickname", "team"], [[p.full, p.handle, p.nick, p.team] for p in people])
    lines = [f"{org.name}: appointments to rotating posts", ""]
    for t, a, b, ch in appoint:
        lines.append(f"{t}: {a.full} until {W.d_long(ch - dt.timedelta(days=1))}; {b.full} from {W.d_long(ch)}.")
    files["appointments.txt"] = "\n".join(lines) + "\n"
    for t in tickets:
        style = rng.choice(["form", "thread", "mail"])
        res = alias(t["resolver"], t["form"], org, t["title"])
        asg = alias(t["assignee"], rng.choice(["full", "nick", "handle"]), org)
        rep = t["reporter"]
        d = t["date"]
        topic = rng.choice(["badge reader", "timetable export", "invoice batch", "printer queue", "door sensor", "mail relay", "login loop", "label template", "rota sync"])
        if style == "form":
            text = dd(f"""
                TICKET T-{t['no']}
                Subject: {topic} problem
                Reported by: {rep.full} ({W.d_iso(d - dt.timedelta(days=rng.randint(1, 6)))})
                Assigned to: {asg}
                Status: resolved
                Resolved on: {W.d_iso(d)}
                Resolved by: {res}
            """)
        elif style == "thread":
            text = (f"T-{t['no']}  {topic} problem\n"
                    f"[{W.d_iso(d - dt.timedelta(days=2))} 09:{rng.randint(10, 59)}] {alias(rep, 'handle', org)}: {topic} is broken again\n"
                    f"[{W.d_iso(d - dt.timedelta(days=1))} 14:{rng.randint(10, 59)}] {asg}: looking into it\n"
                    f"[{W.d_iso(d)} 11:{rng.randint(10, 59)}] {res}: sorted, root cause was a stale setting. Closing this ticket.\n")
        else:
            body = f"Ticket T-{t['no']} ({topic}) is now closed. It was resolved by {res} on {W.d_long(d)}. It had been assigned to {asg}."
            text = W.email(org, rep, [rep], d, f"[T-{t['no']}] closed", body)
        files[f"tickets/T-{t['no']}.txt"] = text
    # decoys: auto-closed tickets and a non-ticket note naming people
    for j in range(rng.randint(2, 5)):
        d = W.rand_date(rng, d0, d_end)
        files[f"tickets/T-{9000 + j}.txt"] = f"TICKET T-{9000 + j}\nSubject: stale request\nStatus: auto-closed by the system after 30 days without activity\nClosed on: {W.d_iso(d)}\n"
    W.pad_files(rng, org, files, rng.randint(3, 8), "notes", d0, d_end)
    files["README.md"] = dd("""
        # Support ticket export

        `tickets/` holds one file per ticket. A ticket's resolver is the person who closed it (the person named after
        "Resolved by", or who writes the closing comment, or who is named as the resolver in the notification email).
        The assignee and reporter are not the resolver. Tickets closed by the system have no resolver.

        `directory.csv` lists every staff member with their handle and nickname. People are also referred to as "F. Last",
        by email address, or by a rotating post, for which `appointments.txt` says who held the post on which dates.
    """)
    return files


@family("research-alias-resolution", category="research", lang="text", kind="greenfield", n=18,
        summary="tally tickets per person when people appear under names, nicknames, handles, emails and rotating posts (answer.json)")
def gen(rng, n):
    made = 0
    while made < n:
        nt = rng.choice([8, 12, 18, 24, 32, 40])
        org, people, holders, appoint, tickets, d0, d_end = build(rng, nt)
        files = render(rng, org, people, holders, appoint, tickets, d0, d_end)
        per = {}
        for t in tickets:
            per.setdefault(t["resolver"], []).append(f"T-{t['no']}")
        qk = made % 3
        if qk == 0:
            p = max(per, key=lambda p: len(per[p]) if len(per[p]) >= 3 else 0)
            exp = sorted(per[p])
            same_last = [x for x in people if x.last == p.last]
            spec = W.json_spec({"tickets": W.jf("set", exp)})
            ph = [f"Which tickets did {p.full} resolve? Write `answer.json` as {{\"tickets\": [\"T-1234\", ...]}} listing every ticket id (as in the filenames), in any order. People get named in many ways in these tickets, so watch for that.",
                  f"I need to credit {p.full} for tickets they closed. Create `answer.json` with the key `tickets`: the list of ticket ids (like \"T-1042\") that {p.first} resolved. Don't include tickets they were merely assigned or that they reported."]
            files_sol = {"answer.json": W.dumps({"tickets": exp})}
            diff, label = 2 + (nt >= 18) + (nt >= 32) + (len(same_last) > 1), "one-person"
        elif qk == 1:
            exp = {p.last: len(v) for p, v in per.items()}
            names = {}
            spec = W.json_spec({"resolved": W.jf("map", exp, sub="int")})
            ph = ["Write `answer.json` with the key `resolved`: an object giving, for every person who resolved at least one ticket, how many tickets they resolved. Key it by surname (if two people share a surname, key them as `Surname F` with the first initial).",
                  "How many tickets did each person resolve? Put it in `answer.json` as {\"resolved\": {\"<surname>\": <count>}}. Only people with at least one resolved ticket; if two staff share a surname use `<surname> <first initial>` for both."]
            # shared surnames use "Surname F"
            lasts = {}
            for p in per:
                lasts[p.last] = lasts.get(p.last, 0) + 1
            exp = {}
            for p, v in per.items():
                key = p.last if sum(1 for x in per if x.last == p.last) == 1 and sum(1 for x in people if x.last == p.last) == 1 else f"{p.last} {p.first[0]}"
                exp[key] = len(v)
            spec = W.json_spec({"resolved": W.jf("map", exp, sub="int")})
            files_sol = {"answer.json": W.dumps({"resolved": exp})}
            diff, label = 3 + (nt >= 18) + (nt >= 32), "all-people"
        else:
            cnt = sorted(((len(v), p) for p, v in per.items()), key=lambda x: -x[0])
            if len(cnt) < 2 or cnt[0][0] == cnt[1][0]:
                continue
            top = cnt[0][1]
            key = top.last if sum(1 for x in people if x.last == top.last) == 1 else f"{top.last} {top.first[0]}"
            spec = W.json_spec({"person": W.jf("str", key), "count": W.jf("int", cnt[0][0])})
            ph = ["Who resolved the most tickets in this export, and how many? Put it in `answer.json` as {\"person\": \"<surname>\", \"count\": <n>} (if another staff member shares the surname, write `Surname F` with the first initial).",
                  "Find the top resolver. `answer.json`: key `person` (surname; add the first initial like `Marrick H` only if someone else shares that surname) and key `count` (their resolved tickets)."]
            files_sol = {"answer.json": W.dumps({"person": key, "count": cnt[0][0]})}
            diff, label = 3 + (nt >= 24), "top"
        made += 1
        yield W.file_task(slug=f"{made:02d}-{label}", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=min(5, diff), start=files, spec=spec, solution=files_sol,
                          scored=True, tags=["aliases", "entity-resolution"], notes={"tickets": nt, "kind": label})
