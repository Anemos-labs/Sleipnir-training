"""Committee minutes in which standing rules change over time: motions carried, defeated, tabled, amended, rescinded,
with default and explicit effective dates. Questions are temporal ("what applied on 9 May?") and are computed by
replaying the decisions."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from fx import dd, family

from . import _world as W

PARAMS = [
    ("annual subscription", "credits", (20, 90)),
    ("quorum", "members", (4, 15)),
    ("guest passes per member each month", "passes", (1, 6)),
    ("booking window", "days", (7, 60)),
    ("petty-cash limit", "credits", (30, 400)),
    ("notice period for meetings", "days", (5, 21)),
    ("late-return fee", "credits", (2, 20)),
    ("refundable deposit", "credits", (10, 120)),
    ("equipment loan period", "days", (3, 28)),
    ("maximum group size for outings", "people", (6, 30)),
]


@dataclass
class Change:
    eff: dt.date
    value: int
    meeting: dt.date
    kind: str  # initial | carried | amended | rescinded


class Param:
    def __init__(self, name, unit, v0, d0):
        self.name, self.unit = name, unit
        self.changes = [Change(d0, v0, d0, "initial")]

    def value_at(self, d: dt.date) -> int | None:
        """the figure set by the most recently decided decision among those already in effect on day d"""
        best = None
        for i, c in enumerate(self.changes):
            if c.eff <= d and (best is None or (c.meeting, i) >= (best[0].meeting, best[1])):
                best = (c, i)
        return None if best is None else best[0].value


def _vote(rng, carried: bool, size: int = 9):
    if carried:
        a = rng.randint(size // 2 + 1, size)
        return a, rng.randint(0, size - a)
    b = rng.randint(size // 2 + 1, size)
    return rng.randint(0, size - b), b


def simulate(rng, org, params: list[Param], meetings: list[dt.date], d0: dt.date, present: dict):
    """Returns per-meeting item lists: meetings[i] -> [(heading, text)] and fills params[].changes."""
    items: dict[dt.date, list[tuple[str, str]]] = {m: [] for m in meetings}
    tabled: dict[str, tuple[int, dt.date]] = {}  # param -> (value, tabled on)
    mem = org.people[:6]
    for mi, m in enumerate(meetings):
        for prm in params:
            p1, p2 = rng.sample(mem, 2)
            cur = prm.value_at(m)
            lo, hi = next((a, b) for n, u, (a, b) in PARAMS if n == prm.name)

            def newv():
                for _ in range(20):
                    v = rng.randint(lo, hi)
                    if v != cur:
                        return v
                return cur + 1

            def eff_clause(kind_rng):
                r = kind_rng
                if r < 0.55:
                    return W.first_of_next_month(m), ""
                if r < 0.75:
                    return m, " With immediate effect."
                d = m + dt.timedelta(days=rng.randint(10, 75))
                return d, f" To take effect from {W.d_long(d)}."

            if prm.name in tabled:
                v, since = tabled.pop(prm.name)
                carried = rng.random() < 0.6
                a, b = _vote(rng, carried, len(present[m]))
                head = prm.name[0].upper() + prm.name[1:]
                if carried:
                    eff, clause = eff_clause(rng.random())
                    txt = (f"Carried over from {W.d_long(since)}. Motion: that the {prm.name} be set at {W.units(v, prm.unit)}. Quotes were presented by the Treasurer. "
                           f"Carried ({a}-{b}).{clause}")
                    prm.changes.append(Change(eff, v, m, "carried"))
                else:
                    txt = f"Carried over from {W.d_long(since)}. Motion: that the {prm.name} be set at {W.units(v, prm.unit)}. Defeated ({a}-{b})."
                items[m].append((head, txt))
                continue
            if rng.random() > 0.3 or mi == 0:
                continue
            head = prm.name[0].upper() + prm.name[1:]
            kinds = ["carried", "carried", "defeated", "tabled", "amended"]
            if prm.changes[-1].kind in ("carried", "amended") and prm.changes[-1].eff <= m:
                kinds.append("rescind")
            kind = rng.choice(kinds)
            if kind == "carried":
                v = newv()
                a, b = _vote(rng, True, len(present[m]))
                eff, clause = eff_clause(rng.random())
                items[m].append((head, f"Motion (moved {p1.last}, seconded {p2.last}): that the {prm.name} be changed to {W.units(v, prm.unit)}. Carried ({a}-{b}).{clause}"))
                prm.changes.append(Change(eff, v, m, "carried"))
            elif kind == "defeated":
                v = newv()
                a, b = _vote(rng, False, len(present[m]))
                items[m].append((head, f"Motion (moved {p1.last}, seconded {p2.last}): that the {prm.name} be changed to {W.units(v, prm.unit)}. Defeated ({a}-{b})."))
            elif kind == "tabled":
                if mi + 1 >= len(meetings):
                    continue
                v = newv()
                tabled[prm.name] = (v, m)
                items[m].append((head, f"Motion (moved {p1.last}, seconded {p2.last}): that the {prm.name} be changed to {W.units(v, prm.unit)}. "
                                       f"The Chair asked for more information; the motion was tabled to the next meeting."))
            elif kind == "amended":
                v = newv()
                v2 = v + rng.choice([-5, -2, 2, 5]) if hi > 20 else v + rng.choice([-1, 1])
                if v2 == cur or v2 == v or v2 < 1:
                    continue
                a, b = _vote(rng, True, len(present[m]))
                eff, clause = eff_clause(rng.random())
                items[m].append((head, f"Motion (moved {p1.last}, seconded {p2.last}): that the {prm.name} be changed to {W.units(v, prm.unit)}. "
                                       f"{p2.last} moved an amendment to make it {v2} instead; the amendment was accepted and the motion as amended was carried ({a}-{b}).{clause}"))
                prm.changes.append(Change(eff, v2, m, "amended"))
            elif kind == "rescind":
                target = prm.changes[-1]
                if target.kind not in ("carried", "amended") or target.eff > m:
                    continue
                eff, clause = eff_clause(rng.random())
                before = prm.value_at(target.eff - dt.timedelta(days=1))
                if before is None or before == target.value:
                    continue
                a, b = _vote(rng, True, len(present[m]))
                items[m].append((head, f"Motion (moved {p1.last}, seconded {p2.last}): to rescind the decision of {W.d_long(target.meeting)} on the {prm.name}, "
                                       f"restoring the figure that applied before it. Carried ({a}-{b}).{clause}"))
                prm.changes.append(Change(eff, before, m, "rescinded"))
    return items


def build(rng, n_meet: int, n_params: int, theme=None):
    org = W.make_org(rng, theme, n_people=9)
    d0 = W.base_date(rng)
    meetings = []
    d = d0 + dt.timedelta(days=rng.randint(20, 40))
    for _ in range(n_meet):
        meetings.append(d)
        d = d + dt.timedelta(days=rng.choice([14, 21, 28, 28, 35]))
    chosen = rng.sample(PARAMS, n_params)
    params = [Param(n, u, rng.randint(lo, hi), d0) for n, u, (lo, hi) in chosen]
    chair, sec = org.people[0], org.people[1]
    present = {}
    for m in meetings:
        pr = rng.sample(org.people, rng.randint(5, 8))
        for must in (chair, sec):
            if must not in pr:
                pr[-1 if must is sec else -2] = must
        present[m] = list(dict.fromkeys(pr))
    items = simulate(rng, org, params, meetings, d0, present)
    return org, d0, meetings, params, items, present


def render_files(rng, org, d0, meetings, params, items, present, naming: str) -> dict[str, str]:
    files: dict[str, str] = {}
    chair, sec = org.people[0], org.people[1]
    rules = "\n".join(f"* {p.name[0].upper() + p.name[1:]}: {W.units(p.changes[0].value, p.unit)}" for p in params)
    files["standing-rules.txt"] = (f"{org.name}\nSTANDING RULES (as adopted {W.d_long(d0)})\n\n{rules}\n\n"
                                   "Changes to these figures are made by motion at a committee meeting and recorded in the minutes.\n")
    for i, m in enumerate(meetings, 1):
        pres = present[m]
        rest = [p for p in org.people if p not in pres]
        absent = rng.sample(rest, rng.randint(0, min(2, len(rest))))
        its = [("Apologies and minutes", f"Apologies were noted. The minutes of the previous meeting were approved as a true record.")]
        its += items[m]
        its.append(("Any other business", W.filler_para(rng, org, rng.randint(1, 3), lo=m, hi=m + dt.timedelta(days=20))))
        txt = W.minutes_doc(org, "Committee", m, chair, pres, absent, its, [f"{sec.full} to circulate the minutes."])
        if naming == "dated":
            path = f"minutes/{W.d_iso(m)}.txt"
        else:
            path = f"minutes/meeting-{i:02d}.txt"
        files[path] = txt
    return files


README = dd("""
    # Committee records

    `standing-rules.txt` lists the figures as first adopted. Every later change was decided at a committee meeting
    and is recorded in `minutes/`.

    How decisions work (from the club's constitution):

    * A motion that is carried takes effect on the first day of the month after the meeting, unless the minutes give
      another date ("with immediate effect" means the day of the meeting).
    * A motion that is defeated changes nothing. A tabled motion is decided at the following meeting.
    * An amendment accepted before the vote replaces the figure in the motion.
    * Rescinding a decision restores the figure that applied just before the rescinded decision took effect.
    * The figure in force on a given day is the one set by the most recently decided decision among those already in
      effect on that day.
""")


def _pick_date(rng, meetings, params):
    return meetings[0] + dt.timedelta(days=rng.randint(0, (meetings[-1] - meetings[0]).days + 20))


@family("research-committee-rules", category="research", lang="text", kind="lookup", n=24, mode="answer",
        summary="temporal questions over committee minutes: which rule value applied on a date, when it took effect")
def gen_rules(rng, n):
    made = 0
    while made < n:
        nm = rng.choice([8, 11, 14, 18])
        org, d0, meetings, params, items, present = build(rng, nm, rng.choice([2, 3, 4]))
        files = render_files(rng, org, d0, meetings, params, items, present, rng.choice(["dated", "numbered"]))
        files["README.md"] = README
        prm = rng.choice([p for p in params if len(p.changes) >= 3] or params)
        kind = rng.choice(["value_on", "value_on", "eff_of_current", "n_changes", "last_meeting"])
        n_ch = len(prm.changes) - 1
        if kind == "value_on":
            for _ in range(20):
                d = _pick_date(rng, meetings, params)
                v = prm.value_at(d)
                if v is not None:
                    break
            ins, c = W.numfmt(rng, v, ("Answer", "Result", "Figure"))
            ph = [f"What was the {prm.name} in force on {W.d_long(d)}?{ins}",
                  f"Which figure for the {prm.name} applied on {W.d_us(d)}? ({prm.unit}){ins}",
                  f"A member disputes a charge from {W.d_long(d)}. What was the {prm.name} on that day, according to the committee's decisions?{ins}"]
            diff = 3 + (n_ch >= 3) + (any(x.kind == "rescinded" for x in prm.changes)) * 1
            prompt, contains, gold = rng.choice(ph), [c], f"On {W.d_long(d)} the {prm.name} was {v} {prm.unit}. {c}"
        elif kind == "eff_of_current":
            cur = prm.changes[-1]
            if cur.kind == "initial":
                continue
            ph = [f"On what date did the {prm.name} that is now in force take effect? Use YYYY-MM-DD.",
                  f"Give me the exact effective date (ISO format) of the figure for the {prm.name} that is in force now, i.e. the date the latest decision on it came into effect."]
            end = max(c.eff for c in prm.changes)
            prompt = rng.choice(ph) + f" Treat {W.d_long(end)} as 'now'."
            contains = [W.d_iso(cur.eff)]
            gold = f"The current {prm.name} ({cur.value} {prm.unit}) took effect on {W.d_iso(cur.eff)}."
            diff = 4
        elif kind == "n_changes":
            ins, c = W.numfmt(rng, n_ch, ("Count", "Total", "Answer"))
            ph = [f"How many decisions changing the {prm.name} do the minutes record since the standing rules were adopted? Count motions that were carried (as moved or as amended) and rescissions that were carried; defeated motions and motions only tabled don't count, and a tabled motion that was later carried counts once.{ins}",
                  f"Count the decisions on the {prm.name} that actually changed it since {W.d_long(d0)}: carried, carried-as-amended, or rescinding. Defeated and still-tabled motions don't count.{ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"The {prm.name} changed {n_ch} times. {c}"
            diff = 3 + (nm >= 14)
        else:
            lastc = prm.changes[-1] if prm.changes[-1].kind != "initial" else None
            if lastc is None:
                continue
            latest = max(prm.changes[1:], key=lambda c: c.meeting)
            ph = [f"At which meeting was the {prm.name} last changed by a carried, amended or rescinding decision? Give the meeting date as YYYY-MM-DD.",
                  f"What is the date of the latest meeting whose minutes record a change to the {prm.name} (a motion that carried)? ISO date please."]
            prompt, contains, gold = rng.choice(ph), [W.d_iso(latest.meeting)], f"The last change was decided on {W.d_iso(latest.meeting)}."
            diff = 3
        made += 1
        prompt = W.voice(rng, org, prompt, lead=rng.choice(["", "", "Going by the minutes in this folder,", "Using the committee's records here,"]))
        yield W.say_task(slug=f"{made:02d}-{kind.replace('_', '-')}", prompt=prompt, difficulty=min(5, diff), start=files, contains=contains, gold=gold,
                         tags=["minutes", "temporal"], notes={"theme": org.theme, "meetings": nm, "param": prm.name, "kind": kind})


@family("research-committee-ledger", category="research", lang="text", kind="greenfield", n=16,
        summary="rebuild the change history of a rule from committee minutes into out.csv or answer.json")
def gen_ledger(rng, n):
    made = 0
    while made < n:
        nm = rng.choice([9, 12, 15, 18])
        org, d0, meetings, params, items, present = build(rng, nm, rng.choice([2, 3]))
        files = render_files(rng, org, d0, meetings, params, items, present, rng.choice(["dated", "numbered"]))
        files["README.md"] = README
        prm = max(params, key=lambda p: len(p.changes))
        if len(prm.changes) < 3:
            continue
        if made % 2 == 0:
            rows = [[W.d_iso(c.eff), c.value] for c in prm.changes[1:]]
            rows.sort(key=lambda r: r[0])
            # when two changes share an effective date only the later decision matters; keep it simple: skip those
            if len({r[0] for r in rows}) != len(rows):
                continue
            spec = W.csv_spec(["effective_date", "value"], ["date", "int"], rows, key=[0], ordered=True)
            ph = [f"Build the history of the {prm.name} for me: `out.csv` with columns `effective_date,value`, one row for every decision that changed it (carried, amended or rescinded) "
                  f"from the minutes, sorted by effective date, ISO dates. Don't include the original standing-rules figure.",
                  f"Please write `out.csv` (header `effective_date,value`) listing each point at which the {prm.name} changed, with the day the new figure came into force. Defeated or merely tabled motions don't count; the first row is the first change after the standing rules."]
            d = 4 + (nm >= 15)
            made += 1
            yield W.file_task(slug=f"{made:02d}-history", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=d, start=files, spec=spec,
                              solution={"out.csv": W.csv_text(["effective_date", "value"], rows)}, scored=True, tags=["minutes", "table"],
                              notes={"theme": org.theme, "meetings": nm, "param": prm.name})
        else:
            ds = sorted({_pick_date(rng, meetings, params) for _ in range(4)})
            fields = {}
            exp = {}
            for d in ds:
                v = prm.value_at(d)
                exp[W.d_iso(d)] = v
            fields = {"values": W.jf("map", exp, sub="int")}
            keys = ", ".join(f"`{k}`" for k in exp)
            ph = [f"Write `answer.json` of the form {{\"values\": {{\"<date>\": <figure>}}}} giving the {prm.name} in force on each of these dates: {keys}.",
                  f"I need the {prm.name} on {len(exp)} dates for an audit ({keys}). Put them in `answer.json` as an object under `values`, keyed by the ISO date."]
            made += 1
            yield W.file_task(slug=f"{made:02d}-values", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=3 + (len(prm.changes) >= 4), start=files,
                              spec=W.json_spec(fields), solution={"answer.json": W.dumps({"values": exp})}, scored=True, tags=["minutes", "temporal"],
                              notes={"theme": org.theme, "meetings": nm, "param": prm.name})
