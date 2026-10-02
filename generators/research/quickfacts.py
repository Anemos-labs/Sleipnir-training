"""Small mixed archives (memos, notices, minutes, emails, tickets) with easy and medium questions: one-hop lookups, a join with the
staff directory, and comparisons between two documents. This is the entry-level research family."""
from __future__ import annotations

import datetime as dt

from fx import dd, family

from . import _world as W

WORKS = ["roof repairs", "a new floor", "rewiring", "deep cleaning", "lift replacement", "repainting", "drain survey", "fire door fitting"]
EVENTS = ["the spring open day", "the safety week", "the volunteers' supper", "the annual review", "the autumn fair", "the skills day", "the quiz night"]
THINGS = ["day pass", "family ticket", "parking permit", "locker", "workshop place", "guest badge", "tool hire"]
GOODS = ["folding chairs", "radios", "safety vests", "step ladders", "fire blankets", "headlamps", "storage crates", "kettles"]


def _sentence_time(rng):
    return W.hhmm(rng, 8, 18)


def gen_closure(rng, org, used, base):
    site = next(s for s in rng.sample(org.sites, len(org.sites)) if ("closure", s) not in used)
    used.add(("closure", site))
    work = rng.choice(WORKS)
    a = base + dt.timedelta(days=rng.randint(10, 200))
    b = a + dt.timedelta(days=rng.randint(4, 30))
    author = rng.choice(org.people)
    contact = rng.choice([p for p in org.people if p is not author])
    text = W.memo_doc(org, f"MEMO-{rng.randint(100, 999)}", a - dt.timedelta(days=rng.randint(7, 20)), author, "All staff", f"Closure of {site} for {work}",
                      f"{site} will close on {W.d_long(a)} for {work}. It will reopen on {W.d_long(b)}. Questions to {contact.full} ({contact.team}).")
    return dict(path=f"memos/closure-{W.slugify(site, 24)}.txt", text=text, kind="closure", site=site, work=work, a=a, b=b, author=author, contact=contact)


def gen_price(rng, org, used, base):
    thing = next(t for t in rng.sample(THINGS, len(THINGS)) if ("price", t) not in used)
    used.add(("price", thing))
    d = base + dt.timedelta(days=rng.randint(10, 300))
    price = rng.randint(110, 980)
    author = rng.choice(org.people)
    text = W.memo_doc(org, f"NOTICE-{rng.randint(100, 999)}", d - dt.timedelta(days=rng.randint(10, 30)), author, "Members and visitors", f"New price for the {thing}",
                      f"From {W.d_long(d)} the price of a {thing} is {price} credits.")
    return dict(path=f"notices/price-{W.slugify(thing, 20)}.txt", text=text, kind="price", thing=thing, d=d, price=price, author=author)


def gen_minutes(rng, org, used, base):
    goods = next(g for g in rng.sample(GOODS, len(GOODS)) if ("minutes", g) not in used)
    used.add(("minutes", goods))
    d = base + dt.timedelta(days=rng.randint(10, 300))
    n = rng.randint(120, 480)
    cost = rng.randint(1100, 9800)
    vendor = f"{rng.choice(W.NAME_WORDS)} Supplies"
    chair = rng.choice(org.people)
    present = rng.sample(org.people, 4)
    text = W.minutes_doc(org, "Equipment committee", d, chair, present, [], [("Purchases", f"The committee agreed to buy {n} {goods} from {vendor} for {cost} credits."), ("AOB", W.filler_line(rng, org, d, d + dt.timedelta(days=20)))])
    return dict(path=f"minutes/{W.d_iso(d)}-{W.slugify(goods, 16)}.txt", text=text, kind="minutes", goods=goods, d=d, n=n, cost=cost, vendor=vendor, chair=chair)


def gen_booking(rng, org, used, base):
    event = next(e for e in rng.sample(EVENTS, len(EVENTS)) if ("booking", e) not in used)
    used.add(("booking", event))
    d = base + dt.timedelta(days=rng.randint(10, 300))
    room = rng.choice(org.sites)
    t = _sentence_time(rng)
    p, q = rng.sample(org.people, 2)
    text = W.email(org, p, [q], d - dt.timedelta(days=rng.randint(3, 15)), f"Room for {event}", f"Hi {q.first},\n\nI have booked {room} for {event} on {W.d_long(d)}, starting at {t}.\n\n{p.first}", time=_sentence_time(rng))
    return dict(path=f"mail/{W.slugify(event, 24)}.eml", text=text, kind="booking", event=event, d=d, room=room, t=t, sender=p)


def gen_deadline(rng, org, used, base):
    event = next(e for e in rng.sample(EVENTS, len(EVENTS)) if ("deadline", e) not in used)
    used.add(("deadline", event))
    d = base + dt.timedelta(days=rng.randint(10, 300))
    t = _sentence_time(rng)
    author = rng.choice(org.people)
    text = W.memo_doc(org, f"NOTICE-{rng.randint(100, 999)}", d - dt.timedelta(days=rng.randint(10, 40)), author, "All members", f"Entries for {event}",
                      f"Entries for {event} close on {W.d_long(d)} at {t} sharp. Late entries cannot be accepted.")
    return dict(path=f"notices/entries-{W.slugify(event, 24)}.txt", text=text, kind="deadline", event=event, d=d, t=t, author=author)


KINDS = [gen_closure, gen_price, gen_minutes, gen_booking, gen_deadline]


def questions(rng, org, docs, tier):
    """list of (prompt, contains, gold, difficulty_hint)"""
    out = []
    for dc in docs:
        k = dc["kind"]
        if k == "closure":
            out.append((f"On what date does {dc['site']} reopen after the closure for {dc['work']}? Reply YYYY-MM-DD.", [W.d_iso(dc["b"])], f"{dc['site']} reopens on {W.d_iso(dc['b'])}.", 1))
            out.append((f"Who is the contact person named in the memo about the closure of {dc['site']}? Surname is enough.", [dc["contact"].last], f"{dc['contact'].full}.", 1))
            out.append((f"Who wrote the memo announcing the closure of {dc['site']}, and which team are they in? Give the person's surname and the team name from directory.csv.", [dc["author"].last, dc["author"].team], f"{dc['author'].full} ({dc['author'].team}).", 2))
        elif k == "price":
            ins, c = W.numfmt(rng, dc["price"])
            out.append((f"What is the new price of a {dc['thing']}, in credits?{ins}", [c], f"{dc['price']} credits. {c}", 1))
            out.append((f"From what date does the new {dc['thing']} price apply? ISO date please.", [W.d_iso(dc["d"])], f"From {W.d_iso(dc['d'])}.", 1))
        elif k == "minutes":
            ins, c = W.numfmt(rng, dc["n"])
            out.append((f"How many {dc['goods']} did the equipment committee agree to buy?{ins}", [c], f"{dc['n']} {dc['goods']}. {c}", 1))
            out.append((f"Which supplier is the committee buying the {dc['goods']} from?", [dc["vendor"].split()[0]], f"{dc['vendor']}.", 1))
            out.append((f"Who chaired the equipment committee meeting at which the {dc['goods']} were bought? Give the surname and the job title from directory.csv.", [dc["chair"].last, dc["chair"].role], f"{dc['chair'].full}, {dc['chair'].role}.", 2))
        elif k == "booking":
            out.append((f"Which room was booked for {dc['event']}, and at what time does it start?", [dc["room"], dc["t"]], f"{dc['room']} at {dc['t']}.", 1))
            out.append((f"Who booked the room for {dc['event']}? Give the surname and their team from directory.csv.", [dc["sender"].last, dc["sender"].team], f"{dc['sender'].full}, {dc['sender'].team}.", 2))
        elif k == "deadline":
            out.append((f"By what date and time must entries for {dc['event']} be in? Date as YYYY-MM-DD, time as HH:MM.", [W.d_iso(dc["d"]), dc["t"]], f"{W.d_iso(dc['d'])} at {dc['t']}.", 1))
    # comparisons between two documents of the same kind
    closures = [d for d in docs if d["kind"] == "closure"]
    if len(closures) >= 2:
        a, b = closures[:2]
        first = a if a["b"] < b["b"] else b
        if a["b"] != b["b"]:
            out.append((f"Which reopens first: {a['site']} or {b['site']}? Name the site.", [first["site"]], f"{first['site']}.", 3))
            gap = abs((a["b"] - b["b"]).days)
            ins, c = W.numfmt(rng, gap, ("Days", "Answer", "Gap"))
            out.append((f"By how many days do the reopening dates of {a['site']} and {b['site']} differ?{ins}", [c], f"{gap} days. {c}", 3))
    prices = [d for d in docs if d["kind"] == "price"]
    if len(prices) >= 2:
        a, b = prices[:2]
        if a["price"] != b["price"]:
            hi = a if a["price"] > b["price"] else b
            out.append((f"Which is dearer, the new {a['thing']} or the new {b['thing']}? Name the item.", [hi["thing"]], f"The {hi['thing']}.", 3))
    return out


@family("research-quick-facts", category="research", lang="text", kind="lookup", n=30, mode="answer",
        summary="entry-level lookups in a small mixed archive of memos, notices, minutes, emails: one hop, directory join, comparison")
def gen(rng, n):
    made = 0
    while made < n:
        org = W.make_org(rng, None, n_people=8, n_sites=6)
        tier = rng.choice(["tiny", "small", "small", "medium"])
        nd = {"tiny": rng.randint(4, 6), "small": rng.randint(8, 12), "medium": rng.randint(14, 20)}[tier]
        base = W.base_date(rng)
        used: set = set()
        docs = []
        for i in range(nd):
            fn = KINDS[i % len(KINDS)] if i < len(KINDS) else rng.choice(KINDS)
            try:
                docs.append(fn(rng, org, used, base))
            except StopIteration:
                continue
        files = {}
        for dc in docs:
            files[dc["path"]] = dc["text"]
        files["directory.csv"] = W.csv_text(["name", "job_title", "team"], [[p.full, p.role, p.team] for p in org.people])
        files["README.md"] = "# Office archive\n\nMemos, notices, committee minutes and a few emails, filed by type. `directory.csv` lists staff with their job titles and teams.\n"
        W.pad_files(rng, org, files, {"tiny": 1, "small": 3, "medium": 6}[tier], "notes", base, base + dt.timedelta(days=300))
        qs = questions(rng, org, docs, tier)
        if not qs:
            continue
        # tiny archives only get one-hop questions; comparisons need the larger ones
        qs = [q for q in qs if q[3] <= {"tiny": 1, "small": 2, "medium": 3}[tier]]
        if not qs:
            continue
        wts = {"tiny": {1: 1}, "small": {1: 40, 2: 60}, "medium": {1: 15, 2: 40, 3: 45}}[tier]
        hints = sorted({q[3] for q in qs})
        h = rng.choices(hints, [wts.get(x, 1) for x in hints])[0]
        prompt, contains, gold, dh = rng.choice([q for q in qs if q[3] == h])
        if any(c in prompt for c in contains if len(c) > 3):
            continue
        d = min(dh + (tier == "medium"), 3)
        made += 1
        yield W.say_task(slug=f"{made:02d}-{tier}-{dh}hop", prompt=W.voice(rng, org, prompt), difficulty=d, start=files, contains=contains, gold=gold,
                         tags=["lookup", "entry-level"], notes={"docs": nd, "tier": tier})
