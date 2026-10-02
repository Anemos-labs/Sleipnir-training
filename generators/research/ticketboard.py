"""Ticket histories (status changes over time, reopenings) in three layouts. File-delivered answers: status counts as of a date, or the
set of tickets that were ever reopened, or the tickets open on a given day."""
from __future__ import annotations

import datetime as dt

from fx import dd, family

from . import _world as W

STATUSES = ["open", "in-progress", "resolved", "closed"]
TOPICS = ["login loop", "slow export", "wrong totals", "missing badge", "printer jam", "label template", "sync failure", "timetable typo", "door sensor", "mail bounce",
          "stuck queue", "bad rota", "calendar clash", "invoice mismatch"]


def build(rng, n_tickets: int, span_days: int):
    org = W.make_org(rng, None, n_people=8)
    d0 = W.base_date(rng)
    tickets = []
    nums = sorted(rng.sample(range(1000, 9999), n_tickets))
    for no in nums:
        opened = d0 + dt.timedelta(days=rng.randint(0, span_days))
        events = [(opened, "open")]
        d = opened
        state = "open"
        for _ in range(rng.choice([0, 1, 2, 2, 3, 4])):
            d = d + dt.timedelta(days=rng.randint(1, 20))
            if state == "open":
                state = rng.choice(["in-progress", "in-progress", "resolved"])
            elif state == "in-progress":
                state = rng.choice(["resolved", "resolved", "open"])
            elif state == "resolved":
                state = rng.choice(["closed", "closed", "in-progress"])  # a resolved ticket may be reopened into in-progress
            else:
                break
            events.append((d, state))
        tickets.append(dict(no=no, topic=rng.choice(TOPICS), events=events, style=rng.choice(["log", "prose", "table"]), who=rng.choice(org.people), opened=opened))
    return org, d0, tickets


def status_on(t, d: dt.date):
    cur = None
    for ed, st in t["events"]:
        if ed <= d:
            cur = st
    return cur


def reopened(t) -> bool:
    prev = None
    for ed, st in t["events"]:
        if prev == "resolved" and st == "in-progress":
            return True
        prev = st
    return False


def render(rng, org, tickets, d0):
    files: dict[str, str] = {}
    for t in tickets:
        ev = t["events"]
        if t["style"] == "log":
            lines = [f"TICKET T-{t['no']}  {t['topic']}  (raised by {t['who'].full})"]
            for d, st in ev:
                lines.append(f"{W.d_iso(d)}  status -> {st}")
            text = "\n".join(lines) + "\n"
        elif t["style"] == "prose":
            parts = [f"Ticket T-{t['no']} ({t['topic']}) was opened on {W.d_long(ev[0][0])} by {t['who'].full}."]
            for d, st in ev[1:]:
                parts.append(f"On {W.d_long(d)} it was moved to {st}.")
            text = " ".join(parts) + "\n"
        else:
            rows = [[W.d_iso(d), st] for d, st in ev]
            text = f"# T-{t['no']}: {t['topic']} (raised by {t['who'].full})\n" + W.csv_text(["date", "status"], rows)
        files[f"tickets/T-{t['no']}.txt"] = text
    W.pad_files(rng, org, files, rng.randint(2, 6), "notes", d0, d0 + dt.timedelta(days=200))
    files["README.md"] = dd("""
        # Ticket histories

        One file per ticket in `tickets/`. Every file lists the dated status changes of the ticket: the first one is the day it was opened
        (status `open`), later ones move it between `open`, `in-progress`, `resolved` and `closed`. A ticket has the status of its latest
        change on or before a given day; before its opening day it does not exist. "Reopened" means a `resolved` ticket going back to
        `in-progress`.
    """)
    return files


@family("research-ticket-board", category="research", lang="text", kind="greenfield", n=12,
        summary="status counts as of a date, tickets ever reopened, or tickets in a given status on a day, from per-ticket histories (answer.json)")
def gen(rng, n):
    made = 0
    while made < n:
        nt = rng.choice([8, 12, 18, 26, 36])
        span = rng.choice([40, 70, 110])
        org, d0, tickets = build(rng, nt, span)
        files = render(rng, org, tickets, d0)
        qk = made % 3
        end = max(ev[-1][0] for t in tickets for ev in [t["events"]])
        if qk == 0:
            d = d0 + dt.timedelta(days=rng.randint(span // 3, span + 20))
            cnt = {}
            for t in tickets:
                s = status_on(t, d)
                if s:
                    cnt[s] = cnt.get(s, 0) + 1
            if sum(cnt.values()) < 3:
                continue
            exp = {s: cnt.get(s, 0) for s in STATUSES}
            spec = W.json_spec({"counts": W.jf("map", exp, sub="int")})
            ph = [f"How many tickets had each status on {W.d_long(d)}? Write `answer.json` as {{\"counts\": {{\"open\": n, \"in-progress\": n, \"resolved\": n, \"closed\": n}}}} (all four keys, zero allowed; tickets not yet opened that day are not counted).",
                  f"For the board pack I need the ticket mix as of {W.d_iso(d)}: `answer.json` with the key `counts` giving the number of tickets per status (open, in-progress, resolved, closed)."]
            sol = W.dumps({"counts": exp})
            diff, label = 2 + (nt >= 18) + (nt >= 36), "counts"
        elif qk == 1:
            ids = sorted(f"T-{t['no']}" for t in tickets if reopened(t))
            if not ids:
                continue
            spec = W.json_spec({"reopened": W.jf("set", ids)})
            ph = ["Which tickets were ever reopened? Write `answer.json` as {\"reopened\": [\"T-1234\", ...]}: ids of tickets that went from resolved back to in-progress at least once.",
                  "List the reopened tickets (a resolved ticket that went back to in-progress, per README.md) in `answer.json` under the key `reopened`."]
            sol = W.dumps({"reopened": ids})
            diff, label = 2 + (nt >= 18), "reopened"
        else:
            d = d0 + dt.timedelta(days=rng.randint(span // 3, span + 20))
            st = rng.choice(["open", "in-progress", "resolved"])
            ids = sorted(f"T-{t['no']}" for t in tickets if status_on(t, d) == st)
            if not ids:
                continue
            spec = W.json_spec({"tickets": W.jf("set", ids)})
            ph = [f"Which tickets had the status `{st}` on {W.d_long(d)}? `answer.json`: {{\"tickets\": [\"T-1234\", ...]}}.",
                  f"I need the list of ticket ids whose status was `{st}` as of {W.d_iso(d)}. Save it as `answer.json` under `tickets`."]
            sol = W.dumps({"tickets": ids})
            diff, label = 3 + (nt >= 18), f"status-{st}"
        made += 1
        yield W.file_task(slug=f"{made:02d}-{label}", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=min(5, diff), start=files, spec=spec, solution={"answer.json": sol},
                          scored=True, tags=["tickets", "temporal"], notes={"tickets": nt, "span": span})
