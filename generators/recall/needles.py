"""Needle-style recall: one fact inside dozens of plausible notes, a value updated across files, and a route to follow
through pointer chains. Material is sized to overflow the small context windows in the budget."""
from __future__ import annotations

import datetime as dt

from fx import dd, family

from generators.research import _world as W
from . import _recall as R

# ---------------------------------------------------------------------------------------------------------------- needle


def _needle_types(rng, org):
    people = org.people
    return [
        dict(key="padlock", q=["What is the padlock code for the {site} store room?", "I'm standing outside the {site} store room. What's the current padlock code?",
                               "Which padlock code opens the {site} store room?"],
             sent="The new padlock code for the {site} store room is {v}.", val=lambda: str(rng.randint(1000, 9999)), fmt="digits"),
        dict(key="ext", q=["Which extension takes out-of-hours calls for {site}?", "If something breaks at {site} after hours, which extension do I ring?"],
             sent="Out-of-hours calls for {site} are answered on extension {v}.", val=lambda: str(rng.randint(2000, 8999)), fmt="digits"),
        dict(key="cabinet", q=["Where are the spare keys for {site} kept? I need the cabinet label.", "What is the label of the key cabinet that holds the {site} spares?"],
             sent="Spare keys for {site} are kept in cabinet {v}.", val=lambda: R.code(rng), fmt="code"),
        dict(key="pallets", q=["How many pallets were delivered to {site} in the last big delivery? A number, please.", "The delivery to {site} was how many pallets?"],
             sent="{v} pallets of mixed stock were delivered to {site} this week.", val=lambda: str(rng.randint(120, 980)), fmt="digits"),
        dict(key="contractor", q=["Who is the roofing contractor for {site}? Surname will do.", "Name the roofing contractor booked for {site} (surname)."],
             sent="The roofing contractor for {site} is {v}, who has promised to start before the weather turns.", val=lambda: rng.choice(W.FIRST) + " " + rng.choice(W.SUR_A) + rng.choice(W.SUR_B), fmt="surname"),
        dict(key="shutoff", q=["On what date is the water shutoff at {site}? Give YYYY-MM-DD.", "When is {site}'s water shutoff booked? ISO date please."],
             sent="The {site} water shutoff is booked for {v}.", val=None, fmt="date"),
    ]


@family("recall-needle-notes", category="recall", lang="text", kind="lookup", n=24, mode="answer",
        summary="one fact (code, extension, label, quantity, name, date) for one site buried among near-identical facts for other sites in dozens of notes")
def gen_needle(rng, n):
    made = 0
    while made < n:
        org = W.make_org(rng, None, n_people=9, n_assets=4, n_sites=rng.choice([8, 10, 12]))
        tier = R.tier(rng)
        win = None if tier == "easy" else R.window(rng)
        if tier == "easy":
            nfiles, kb = rng.choice([6, 9, 12, 16]), rng.choice([0.8, 1.2])
        else:
            nfiles = rng.choice([22, 30, 40, 55]) if (win or 16000) <= 16000 else rng.choice([60, 80])
            kb = max(0.8, R.target_chars(win, rng.choice([1.0, 1.25, 1.5])) / 1000 / nfiles)
        lo = W.base_date(rng)
        hi = lo + dt.timedelta(days=rng.randint(120, 330))
        nt = rng.choice(_needle_types(rng, org))
        sites = list(org.sites)
        target = rng.choice(sites)
        files: dict[str, str] = {}
        dates = W.rand_dates(rng, nfiles, lo, hi, distinct=False)
        extras: list[list[str]] = [[] for _ in range(nfiles)]

        def value():
            if nt["key"] == "shutoff":
                d = W.rand_date(rng, lo, hi + dt.timedelta(days=30))
                return d, W.d_long(d)
            v = nt["val"]()
            return v, v
        tv, tshow = value()
        place = rng.randrange(nfiles)
        extras[place].append(nt["sent"].format(site=target, v=tshow))
        others = [s for s in sites if s != target]
        used_vals = {tshow}
        for s in rng.sample(others, min(len(others), rng.randint(5, len(others)))):
            v, shown = value()
            if shown in used_vals:
                continue
            used_vals.add(shown)
            extras[rng.randrange(nfiles)].append(nt["sent"].format(site=s, v=shown))
        # unrelated facts about the target site, so a search for the site name alone is not enough
        for _ in range(rng.randint(2, 5)):
            extras[rng.randrange(nfiles)].append(rng.choice([
                f"{target} was inspected on {W.d_long(W.rand_date(rng, lo, hi))}; nothing to report.",
                f"The bins at {target} are emptied on {rng.choice(W.WEEKDAYS)}s.",
                f"Visitors to {target} should sign in at the front desk.",
                f"{rng.choice(org.people).full} will be at {target} on {W.d_long(W.rand_date(rng, lo, hi))}."]))
        for i, d in enumerate(dates):
            files[R.unique_path(rng, files, "notes", d)] = R.note_file(rng, org, d, kb, extras[i], lo, hi)
        files["README.md"] = "# Site notebook\n\nDated notes written by staff across all our sites. Anything may be in any of them.\n"
        q = rng.choice(nt["q"]).format(site=target)
        if nt["fmt"] == "surname":
            contains = [tv.split()[1]]
            gold = f"The contractor for {target} is {tv}."
        elif nt["fmt"] == "date":
            contains = [W.d_iso(tv)]
            gold = f"The shutoff at {target} is on {W.d_iso(tv)}."
        else:
            contains = [tv]
            gold = f"For {target} it is {tv}."
        if any(c in q for c in contains):
            continue
        d = 1 + (win is not None and win <= 12000) + (nfiles >= 40) + (nt["fmt"] in ("surname", "date")) * (tier != "easy")
        made += 1
        yield W.say_task(slug=f"{made:02d}-{nt['key']}", prompt=W.voice(rng, org, q), difficulty=min(4, d), start=files, contains=contains, gold=gold, context_window=win,
                         tags=["needle", "haystack"], notes={"files": nfiles, "kb_each": round(kb, 1), "type": nt["key"]})


# ---------------------------------------------------------------------------------------------------------------- latest update

ATTRS = [("maximum load", "tonnes"), ("inspection interval", "days"), ("temperature ceiling", "degrees"), ("staff allowance", "people"), ("booking lead time", "days"),
         ("daily cap", "units"), ("noise limit", "decibels"), ("queue length limit", "places")]


@family("recall-latest-update", category="recall", lang="text", kind="lookup", n=22, mode="answer",
        summary="current (or as-of-date) value of a setting updated several times across dozens of dated notes, with proposals that never applied")
def gen_update(rng, n):
    made = 0
    while made < n:
        tier = R.tier(rng)
        org = W.make_org(rng, None, n_people=9, n_assets=3 if tier == "easy" else rng.choice([5, 7, 8]))
        win = None if tier == "easy" else R.window(rng)
        if tier == "easy":
            nfiles, kb = rng.choice([6, 8, 10, 14]), 0.8
        else:
            nfiles = rng.choice([24, 32, 44, 56]) if (win or 16000) <= 16000 else rng.choice([60, 70])
            kb = max(0.7, R.target_chars(win, rng.choice([1.0, 1.25, 1.5])) / 1000 / nfiles)
        lo = W.base_date(rng)
        hi = lo + dt.timedelta(days=rng.randint(200, 420))
        attrs = rng.sample(ATTRS, 3)
        ents = org.assets
        ev: dict[tuple, list] = {}
        extras: list[list[str]] = [[] for _ in range(nfiles)]
        for e in ents:
            for a in attrs:
                k = rng.choice([1, 2, 3, 4]) if (e == ents[0]) else rng.choice([1, 1, 2])
                ds = W.rand_dates(rng, k, lo, hi)
                v = rng.randint(5, 120)
                lst = []
                for d in ds:
                    nv = v
                    while nv == v:
                        nv = rng.randint(5, 120)
                    v = nv
                    lst.append((d, v))
                ev[(e, a[0])] = lst
        # render the confirmed updates, and proposals that never applied
        for (e, an), lst in ev.items():
            unit = next(u for a, u in attrs if a == an)
            for d, v in lst:
                tag = rng.choice(["[confirmed]", "[confirmed]", "[confirmed by the committee]"])
                s = rng.choice([f"{tag} {e}: {an} is now {v} {unit}, effective {W.d_long(d)}.",
                                f"{tag} Effective {W.d_long(d)}, the {an} for {e} becomes {v} {unit}.",
                                f"{tag} {an} ({e}): {v} {unit} from {W.d_long(d)}."])
                extras[rng.randrange(nfiles)].append(s)
            for _ in range(rng.choice([0, 1, 1, 2])):
                d = W.rand_date(rng, lo, hi + dt.timedelta(days=60))
                v = rng.randint(5, 120)
                extras[rng.randrange(nfiles)].append(rng.choice([f"[proposed] {e}: {an} to {v} {unit}, from {W.d_long(d)}. Not yet agreed.",
                                                                  f"[proposed] Someone suggested the {an} for {e} be {v} {unit} from {W.d_long(d)}; the committee has not decided."]))
        files: dict[str, str] = {}
        dates = W.rand_dates(rng, nfiles, lo, hi + dt.timedelta(days=40), distinct=False)
        for i, d in enumerate(dates):
            files[R.unique_path(rng, files, "notes", d)] = R.note_file(rng, org, d, kb, extras[i], lo, hi)
        files["README.md"] = dd("""
            # Operating limits: working notes

            Staff drop dated notes here. A line tagged `[confirmed]` records a decision with an effective date; a line tagged
            `[proposed]` records only a suggestion and changes nothing. The figure in force for any day is the confirmed update with
            the latest effective date on or before that day (the date inside the line, not the date of the note). The starting
            figures were published in an old booklet that is no longer in this folder; every figure you need here is
            in a confirmed line.
        """)
        cands = [(e, an) for (e, an), lst in ev.items() if len(lst) >= (1 if tier == "easy" else 2)]
        e, an = rng.choice(cands)
        lst = ev[(e, an)]
        unit = next(u for a, u in attrs if a == an)
        qk = rng.choice(["current", "current", "asof"])
        if qk == "current":
            v = lst[-1][1]
            ins, c = W.numfmt(rng, v, ("Answer", "Result", "Figure"))
            ph = [f"What is the current {an} for {e} (the latest confirmed update)?{ins}",
                  f"Looking through the notes: what {an} is in force now for {e}? Only confirmed updates count.{ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"The latest confirmed {an} for {e} is {v} {unit}. {c}"
            diff = 1 + (len(lst) >= 2) + (len(lst) >= 4) + (win is not None and win <= 12000) + (tier == "hard")
        else:
            d = W.rand_date(rng, lst[0][0], lst[-1][0] + dt.timedelta(days=30))
            v = [x for x in lst if x[0] <= d][-1][1]
            ins, c = W.numfmt(rng, v, ("Answer", "Result", "Figure"))
            ph = [f"What {an} was in force for {e} on {W.d_long(d)}? Use the confirmed updates and their effective dates.{ins}",
                  f"Which {an} applied to {e} on {W.d_iso(d)}?{ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"On {W.d_iso(d)} it was {v} {unit}. {c}"
            diff = 3 + (len(lst) >= 4) + (tier == "hard")
        made += 1
        yield W.say_task(slug=f"{made:02d}-{qk}", prompt=W.voice(rng, org, prompt), difficulty=min(5, diff), start=files, contains=contains, gold=gold, context_window=win,
                         tags=["drift", "haystack"], notes={"files": nfiles, "question": qk, "updates": len(lst)})


# ---------------------------------------------------------------------------------------------------------------- chains

TITLES_A = ["Marram", "Lantern", "Tide", "Cinder", "Hollow", "Sorrel", "Quarry", "Pennant", "Kestrel", "Anchor", "Fathom", "Gable", "Harrow", "Ivy", "Jetty", "Keel"]
TITLES_B = ["Ledger", "Ferry", "Beacon", "Latch", "Cairn", "Bridle", "Tally", "Gantry", "Mooring", "Sluice", "Larder", "Wicket", "Rampart", "Trellis", "Scuttle", "Spindle"]


@family("recall-chain-hops", category="recall", lang="text", kind="lookup", n=24, mode="answer",
        summary="follow a route of NEXT pointers (by path, title or card number) past stale and decoy pointers to the final code")
def gen_chain(rng, n):
    made = 0
    while made < n:
        org = W.make_org(rng, None, n_people=8)
        tier = R.tier(rng)
        win = None if tier == "easy" else R.window(rng)
        depth = rng.choice([2, 3]) if tier == "easy" else rng.choice([3, 4, 5, 6, 8, 9])
        style = rng.choice(["path", "number"] if tier == "easy" else ["path", "title", "number"])
        n_decoy = rng.randint(1, 3) if tier == "easy" else rng.randint(3, 5) + depth
        total = depth + 1 + n_decoy
        kb = 0.6 if tier == "easy" else max(0.5, R.target_chars(win, rng.choice([1.0, 1.25, 1.5])) / 1000 / total)
        titles = rng.sample([f"{a} {b}" for a in TITLES_A for b in TITLES_B], total)
        numbers = rng.sample(range(1000, 9999), total)
        ids = list(range(total))
        rng.shuffle(ids)
        route = ids[: depth + 1]
        decoys = ids[depth + 1:]
        names = {i: (f"cards/card-{numbers[i]}.txt" if style == "number" else f"cards/c{rng.randint(10000, 99999)}-{i:02d}.txt") for i in ids}

        def ref(i):
            if style == "title":
                return f"the card titled \"{titles[i]}\""
            if style == "number":
                return f"card {numbers[i]}"
            return names[i]
        final_code = R.code(rng)
        files: dict[str, str] = {}

        def body(i, lines):
            head = f"CARD {numbers[i]}\nTitle: {titles[i]}\n\n"
            return head + R.chatter(rng, org, kb) + "\n\n" + "\n".join(lines) + "\n"
        for k, i in enumerate(route):
            lines = []
            if k < depth:
                lines.append(f"NEXT >> {ref(route[k + 1])}")
            else:
                lines.append(f"FINAL >> the vault code is {final_code}")
            for _ in range(rng.randint(1, 2)):
                lines.append(rng.choice(["OLD", "ALSO SEE"]) + f" >> {ref(rng.choice(decoys))}")
            rng.shuffle(lines)
            files[names[i]] = body(i, lines)
        # decoy chains end in wrong codes
        for j, i in enumerate(decoys):
            if j % 3 == 0:
                files[names[i]] = body(i, [f"FINAL >> the vault code is {R.code(rng)}"])
            else:
                nxt = decoys[(j + 1) % len(decoys)]
                files[names[i]] = body(i, [f"NEXT >> {ref(nxt)}"] if rng.random() < 0.5 else [f"OLD >> {ref(nxt)}"])
        start_ref = ref(route[0])
        files["START.txt"] = dd(f"""
            Vault route
            -----------
            The vault code is at the end of a trail of cards. Begin at {start_ref}.
            Only lines that start with `NEXT >>` are part of the route. Lines starting with `OLD >>` or `ALSO SEE >>` are stale or
            side references and must be ignored. The last card of the route has a line starting `FINAL >>`.
        """)
        ph = [f"Follow the vault route described in START.txt and tell me the vault code at the end of it.",
              f"There is a trail of cards in this folder that ends with a vault code. START.txt says how to follow it. What is the code?",
              f"Can you walk the route in START.txt to its last card and give me the code written there?"]
        d = 1 + (depth >= 3) + (depth >= 5) + (depth >= 8) + (style == "title")
        made += 1
        yield W.say_task(slug=f"{made:02d}-{style}-{depth}hops", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=min(5, d), start=files, contains=[final_code],
                         gold=f"The vault code is {final_code}.", context_window=win, tags=["multi-hop", "chain"], notes={"depth": depth, "style": style, "cards": total})
