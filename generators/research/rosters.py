"""Shift rosters changed by swap emails. A swap only works if both people actually held the slots they name when the email was sent;
stale swaps are ignored. File-delivered answers: the roster of one day, shift counts for a week, or the list of ineffective swaps."""
from __future__ import annotations

import datetime as dt

from fx import dd, family

from . import _world as W

SLOTS = ["early", "late", "night"]


def monday_of(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def build(rng, weeks: int, n_people: int, n_swaps: int):
    org = W.make_org(rng, None, n_people=n_people)
    start = monday_of(W.base_date(rng))
    days = [start + dt.timedelta(days=i) for i in range(7 * weeks)]
    state = {}
    for d in days:
        order = rng.sample(org.people, len(org.people))
        for si, s in enumerate(SLOTS):
            state[(d, s)] = order[si]
    initial = dict(state)
    swaps = []
    t = dt.datetime.combine(start - dt.timedelta(days=rng.randint(3, 8)), dt.time(9, 0))
    for k in range(1, n_swaps + 1):
        t = t + dt.timedelta(hours=rng.randint(4, 40))
        S = rng.choice(org.people)
        P = rng.choice([p for p in org.people if p is not S])
        horizon = [d for d in days if d >= t.date() + dt.timedelta(days=1)] or days[-3:]
        use_initial = rng.random() < 0.35  # people sometimes work from the published rota and forget earlier swaps
        src = initial if use_initial else state
        s_slots = [key for key, who in src.items() if who is S and key[0] in horizon]
        p_slots = [key for key, who in src.items() if who is P and key[0] in horizon]
        if not s_slots or not p_slots:
            continue
        claimed_a, claimed_b = rng.choice(s_slots), rng.choice(p_slots)
        if rng.random() < 0.1:
            other = rng.choice([key for key in state if key[0] in horizon and state[key] is not S and state[key] is not P])
            if rng.random() < 0.5:
                claimed_a = other
            else:
                claimed_b = other
        ok = state[claimed_a] is S and state[claimed_b] is P
        if ok:
            state[claimed_a], state[claimed_b] = P, S
        swaps.append(dict(id=k, t=t, S=S, P=P, a=claimed_a, b=claimed_b, ok=ok))
    return org, start, days, initial, state, swaps


def slot_text(key):
    d, s = key
    return f"{W.WEEKDAYS[d.weekday()]} {d.day} {W.MONTHS[d.month - 1][:3]} ({s})"


def render(rng, org, start, days, initial, swaps, weeks):
    files: dict[str, str] = {}
    for w in range(weeks):
        rows = []
        for d in days[7 * w:7 * w + 7]:
            rows.append([W.d_iso(d), W.WEEKDAYS[d.weekday()][:3]] + [initial[(d, s)].full for s in SLOTS])
        files[f"roster/week-{W.d_iso(days[7 * w])}.csv"] = W.csv_text(["date", "day"] + SLOTS, rows)
    for s in swaps:
        subj = f"SW-{s['id']}: shift swap"
        body = rng.choice([
            f"Hi all,\n\n{s['P'].first} and I have agreed a swap ({'SW-' + str(s['id'])}): I take {s['P'].first}'s {slot_text(s['b'])} and {s['P'].first} takes my {slot_text(s['a'])}.\n\n{s['S'].first}",
            f"Roster change {'SW-' + str(s['id'])}: {s['S'].full} gives up {slot_text(s['a'])}; {s['P'].full} gives up {slot_text(s['b'])}. They exchange.\n\nSent by {s['S'].first}.",
        ])
        files[f"swaps/SW-{s['id']:02d}.eml"] = W.email(org, s["S"], [s["P"]], s["t"].date(), subj, body, time=s["t"].strftime("%H:%M"))
    W.pad_files(rng, org, files, rng.randint(2, 5), "notes", start, days[-1])
    files["README.md"] = dd("""
        # Shift rosters

        `roster/week-<Monday>.csv` is the rota as published: for each date, who works the early, late and night slot.
        `swaps/` holds the swap emails (SW-n) in the order they were sent (see the timestamps). Apply them in that order.

        A swap exchanges the two named slots between the two people **only if, at the moment the email was sent, each person
        actually held the slot the email says they give up** (earlier swaps may have moved things). If either claim is wrong the swap
        is ineffective and changes nothing.
    """)
    return files


@family("research-shift-swaps", category="research", lang="text", kind="greenfield", n=12,
        summary="replay swap emails over weekly rosters (stale swaps ignored): roster of a day, shift counts, ineffective swaps (answer.json)")
def gen(rng, n):
    made = 0
    while made < n:
        weeks = rng.choice([1, 2])
        npeople = rng.choice([5, 6, 7])
        nsw = rng.choice([4, 6, 8, 10, 14])
        org, start, days, initial, final, swaps = build(rng, weeks, npeople, nsw)
        if len(swaps) < 3:
            continue
        files = render(rng, org, start, days, initial, swaps, weeks)
        qk = made % 3
        if qk == 0:
            d = rng.choice(days)
            exp = {s: final[(d, s)].last for s in SLOTS}
            spec = W.json_spec({k: W.jf("str", v) for k, v in exp.items()})
            ph = [f"Who works each slot on {W.d_wdlong(d)} once all the effective swaps are applied? Write `answer.json` as {{\"early\": \"<surname>\", \"late\": \"<surname>\", \"night\": \"<surname>\"}}.",
                  f"I need the final roster for {W.d_iso(d)}. Put it in `answer.json` with keys early, late and night, surnames as values. Apply the swaps as README.md says."]
            sol = W.dumps(exp)
            diff, label = 3 + (len(swaps) >= 8) + (weeks == 2), "day"
        elif qk == 1:
            w = rng.randrange(weeks)
            wdays = days[7 * w:7 * w + 7]
            cnt = {}
            for d in wdays:
                for s in SLOTS:
                    cnt[final[(d, s)].last] = cnt.get(final[(d, s)].last, 0) + 1
            spec = W.json_spec({"shifts": W.jf("map", cnt, sub="int")})
            ph = [f"After the swaps, how many shifts does each person work in the week starting {W.d_iso(wdays[0])}? `answer.json`: {{\"shifts\": {{\"<surname>\": <count>}}}}, everyone who works at least one shift.",
                  f"Count shifts per person for the week of {W.d_long(wdays[0])} (final roster, effective swaps only) and save it as `answer.json` under the key `shifts`, keyed by surname."]
            sol = W.dumps({"shifts": cnt})
            diff, label = 4 + (len(swaps) >= 10), "week-counts"
        else:
            bad = sorted(f"SW-{s['id']}" for s in swaps if not s["ok"])
            if not bad:
                continue
            spec = W.json_spec({"ineffective": W.jf("set", bad)})
            ph = ["Some of the swap emails don't work because someone didn't hold the slot they gave away. Which ones? `answer.json`: {\"ineffective\": [\"SW-3\", ...]}.",
                  "List the swaps (by their SW id) that had no effect under the README's rule. Write `answer.json` with the key `ineffective`."]
            sol = W.dumps({"ineffective": bad})
            diff, label = 4 + (len(swaps) >= 10), "ineffective"
        made += 1
        yield W.file_task(slug=f"{made:02d}-{label}", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=min(5, diff), start=files, spec=spec, solution={"answer.json": sol},
                          scored=True, tags=["roster", "replay"], notes={"weeks": weeks, "swaps": len(swaps), "people": npeople})
