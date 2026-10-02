"""Conflicting sources with a documented authority ranking: official register > survey report > guidebook > newsletter,
newest wins inside a rank. The wrong figures are deliberately the majority more often than not, so counting votes fails.
Families: ``research-authority-lookup`` (answers in the message) and ``research-authority-table`` (out.csv)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from fx import dd, family

from . import _world as W

DOMAINS = {
    "lighthouse": dict(title="lighthouses", suffix="Light", attrs=[("tower height", "m", (12, 70)), ("light range", "nautical miles", (8, 28)), ("first lit", "", (1820, 1990))]),
    "footbridge": dict(title="footbridges", suffix="Footbridge", attrs=[("main span", "m", (20, 300)), ("load limit", "tonnes", (2, 40)), ("year opened", "", (1840, 2010))]),
    "hut": dict(title="mountain huts", suffix="Hut", attrs=[("elevation", "m", (900, 3200)), ("bunks", "", (6, 60)), ("year built", "", (1880, 2015))]),
    "reservoir": dict(title="reservoirs", suffix="Reservoir", attrs=[("capacity", "megalitres", (200, 9000)), ("dam height", "m", (8, 90)), ("year completed", "", (1890, 2010))]),
    "windmill": dict(title="windmills", suffix="Mill", attrs=[("sail span", "m", (9, 28)), ("grinding stones", "", (1, 6)), ("year raised", "", (1700, 1900))]),
}
RANK_NAMES = {1: "register", 2: "survey", 3: "guidebook", 4: "newsletter"}


@dataclass
class Claim:
    ent: int
    attr: int
    rank: int
    date: dt.date
    value: int
    doc: str = ""


def _fmt(label: str, unit: str, v: int) -> str:
    return f"{label} {v}" + (f" {unit}" if unit else "")


def build(rng, n_ent: int):
    key = rng.choice(sorted(DOMAINS))
    dom = DOMAINS[key]
    org = W.make_org(rng, None, n_people=7)
    words = rng.sample(W.NAME_WORDS, n_ent)
    ents = [f"{w} {dom['suffix']}" for w in words]
    truth = {(e, a): rng.randint(*dom["attrs"][a][2]) for e in range(n_ent) for a in range(3)}
    lo = dt.date(rng.randint(2010, 2024), 1, 1)
    hi = lo + dt.timedelta(days=rng.randint(1500, 5000))
    claims: list[Claim] = []
    for e in range(n_ent):
        for a in range(3):
            n_src = rng.choice([2, 3, 3, 4, 5])
            ranks = [rng.choices([1, 2, 3, 4], [30, 30, 50, 60])[0] for _ in range(n_src)]
            for rk in ranks:
                claims.append(Claim(e, a, rk, W.rand_date(rng, lo, hi), 0))
    # one claim per (entity, attribute, rank, publication date); guidebooks are per edition year
    uniq = {}
    for c in sorted(claims, key=lambda c: (c.date, c.ent, c.attr, c.rank)):
        uniq[(c.ent, c.attr, c.rank, c.date.year if c.rank == 3 else c.date)] = c
    claims = list(uniq.values())
    # a guidebook entry carries one revision date for all the facts it gives about a site
    latest = {}
    for c in claims:
        if c.rank == 3:
            k = (c.ent, c.date.year)
            latest[k] = max(latest.get(k, c.date), c.date)
    for c in claims:
        if c.rank == 3:
            c.date = latest[(c.ent, c.date.year)]
    # winners by the documented rule
    best = {}
    for c in claims:
        k = (c.ent, c.attr)
        if k not in best or (-c.rank, c.date) > (-best[k].rank, best[k].date):
            best[k] = c
    for c in claims:
        k = (c.ent, c.attr)
        t = truth[k]
        a_lo, a_hi = dom["attrs"][c.attr][2]
        if c is best[k]:
            c.value = t
        else:
            if rng.random() < 0.72:
                wrong = t + rng.choice([-1, 1]) * rng.choice([1, 2, 3, 5, 10, 20])
                if wrong == t or wrong < 1:
                    wrong = t + 7
                c.value = wrong
            else:
                c.value = t
    return org, key, dom, ents, truth, claims, lo, hi


README = dd("""
    # {title_cap} dossier

    Sources about {title} collected from four kinds of publisher, kept in separate folders:

    1. `register/`  the official register (one entry per site)
    2. `surveys/`   survey reports
    3. `guides/`    published guidebooks
    4. `news/`      newsletter items and press cuttings

    When sources disagree about a figure, use the highest-ranking source that states it (register over survey over
    guidebook over newsletter). Among sources of the same rank, use the one with the latest date. A figure that a
    higher-ranking source does not state falls back to the next rank down. Do not count votes: a repeated figure is not
    more reliable than a single official one.
""")


def render(rng, org, key, dom, ents, truth, claims, lo, hi):
    files: dict[str, str] = {}
    attrs = dom["attrs"]
    reg: dict[int, list[Claim]] = {}
    sur: dict[tuple[int, str], list[Claim]] = {}
    gui: dict[str, list[Claim]] = {}
    nws: list[Claim] = []
    for c in claims:
        if c.rank == 1:
            reg.setdefault(c.ent, []).append(c)
        elif c.rank == 2:
            sur.setdefault((c.ent, W.d_iso(c.date)), []).append(c)
        elif c.rank == 3:
            gui.setdefault(f"{c.date.year}", []).append(c)
        else:
            nws.append(c)
    # register: one entry per entity, possibly several amendments: each amendment is its own dated block in the same file
    for e, cl in reg.items():
        by_date: dict[dt.date, list[Claim]] = {}
        for c in cl:
            by_date.setdefault(c.date, []).append(c)
        out = [f"OFFICIAL REGISTER ENTRY: {ents[e]}", ""]
        for d in sorted(by_date):
            out.append(f"Amendment dated {W.d_long(d)}:")
            seen = set()
            for c in by_date[d]:
                if c.attr in seen:
                    continue
                seen.add(c.attr)
                lab, unit, _ = attrs[c.attr]
                out.append(f"  {lab[0].upper() + lab[1:]}: {c.value}" + (f" {unit}" if unit else ""))
        files[f"register/{W.slugify(ents[e])}.txt"] = "\n".join(out) + "\n"
    for (e, ds), cl in sur.items():
        method = rng.choice(["laser rangefinding", "tape and theodolite", "drone photogrammetry", "a walked traverse", "plans checked on site"])
        out = [f"SURVEY REPORT: {ents[e]}", f"Surveyed: {W.d_long(dt.date.fromisoformat(ds))}", f"Method: {method}", "", "Findings:"]
        seen = set()
        for c in cl:
            if c.attr in seen:
                continue
            seen.add(c.attr)
            lab, unit, _ = attrs[c.attr]
            out.append(f"  - {lab}: {c.value}" + (f" {unit}" if unit else ""))
        author = rng.choice(org.people)
        out.append(f"\nSigned: {author.full}, {author.role}")
        files[f"surveys/{W.slugify(ents[e])}-{ds}.txt"] = "\n".join(out) + "\n"
    for yr, cl in gui.items():
        by_ent: dict[int, list[Claim]] = {}
        for c in cl:
            by_ent.setdefault(c.ent, []).append(c)
        title = rng.choice(["Coastal Companion", "A Walker's Guide", "The Curious Traveller", "Rambles and Landmarks", "Pocket Gazetteer"]) + f" ({yr} edition)"
        out = [title, ""]
        for e in sorted(by_ent):
            seen = set()
            bits = []
            for c in by_ent[e]:
                if c.attr in seen:
                    continue
                seen.add(c.attr)
                lab, unit, _ = attrs[c.attr]
                bits.append(_fmt(lab, unit, c.value))
            d = max(c.date for c in by_ent[e])
            out.append(f"{ents[e]}. {rng.choice(['A fine example, much visited in summer.', 'Worth a detour.', 'Best seen in the evening light.', 'Popular with photographers.', 'Quiet outside the holidays.', 'A local favourite.'])} Key facts: " + "; ".join(bits) + f". (Entry revised {W.d_long(d)}.)")
            out.append("")
        files[f"guides/guide-{yr}-{W.slugify(title, 18)}.txt"] = "\n".join(out)
    for i, c in enumerate(sorted(nws, key=lambda c: (c.date, c.ent, c.attr))):
        lab, unit, _ = attrs[c.attr]
        p = rng.choice(org.people)
        style = rng.randrange(3)
        if style == 0:
            body = f"Cuttings file: {W.d_long(c.date)}. Locals say the {ents[c.ent]} is something special, with a {lab} of {c.value}" + (f" {unit}" if unit else "") + f", according to {p.full}."
        elif style == 1:
            body = f"Newsletter item ({W.d_long(c.date)}): the {ents[c.ent]}'s {lab} is {c.value}" + (f" {unit}" if unit else "") + ". Come and see for yourself!"
        else:
            body = f"{W.d_long(c.date)}. Friends of the {ents[c.ent]} remind readers that its {lab} stands at {c.value}" + (f" {unit}" if unit else "") + "."
        files[f"news/{W.d_iso(c.date)}-{W.slugify(ents[c.ent], 20)}-{i:02d}.txt"] = body + "\n"
    W.pad_files(rng, org, files, rng.randint(2, 6), "news/misc", lo, hi)
    files["README.md"] = README.format(title=dom["title"], title_cap=dom["title"].capitalize())
    return files


@family("research-authority-lookup", category="research", lang="text", kind="lookup", n=22, mode="answer",
        summary="resolve conflicting figures with an authority ranking, then look up, compare or count across sites")
def gen_lookup(rng, n):
    made = 0
    while made < n:
        n_ent = rng.choice([4, 5, 6, 8, 10, 12])
        org, key, dom, ents, truth, claims, lo, hi = build(rng, n_ent)
        files = render(rng, org, key, dom, ents, truth, claims, lo, hi)
        attrs = dom["attrs"]
        qk = rng.choice(["value", "value", "value", "extreme", "count", "diff"])
        a = rng.randrange(3)
        lab, unit, (a_lo, a_hi) = attrs[a]
        vals = [truth[(e, a)] for e in range(n_ent)]
        if qk == "value":
            e = rng.randrange(n_ent)
            v = truth[(e, a)]
            ins, c = W.numfmt(rng, v, ("Answer", "Result", "Figure"))
            ph = [f"What is the {lab} of the {ents[e]}?{ins}",
                  f"Please settle an argument: how big is the {ents[e]}'s {lab}{' (' + unit + ')' if unit else ''}? The sources don't agree.{ins}",
                  f"Our dossier has several figures for the {lab} of the {ents[e]}. Which one should we publish?{ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"The {lab} of the {ents[e]} is {v}" + (f" {unit}" if unit else "") + f". {c}"
            ncl = sum(1 for c_ in claims if (c_.ent, c_.attr) == (e, a))
            diff = 1 + (ncl >= 3) + (ncl >= 5)
        elif qk == "extreme":
            hi_v, lo_v = max(vals), min(vals)
            if vals.count(hi_v) != 1 or vals.count(lo_v) != 1:
                continue
            which = rng.choice(["greatest", "smallest"])
            tgt = vals.index(hi_v if which == "greatest" else lo_v)
            ph = [f"Which of the {dom['title']} in the dossier has the {which} {lab}? Name it.",
                  f"Across all the {dom['title']} here, which has the {which} {lab}, going by the figure the README says to trust?"]
            prompt, contains, gold = rng.choice(ph), [ents[tgt].split()[0]], f"The {ents[tgt]} has the {which} {lab} ({vals[tgt]})."
            diff = 3 + (n_ent >= 10)
        elif qk == "count":
            thr = sorted(vals)[len(vals) // 2] + rng.choice([0, 1])
            cnt = sum(1 for v in vals if v > thr)
            ins, c = W.numfmt(rng, cnt, ("Count", "Total", "Answer"))
            ph = [f"How many of the {dom['title']} have a {lab} above {thr}{' ' + unit if unit else ''}?{ins}",
                  f"Count the {dom['title']} whose {lab} is greater than {thr}{' ' + unit if unit else ''} (strictly).{ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"{cnt} of them. {c}"
            diff = 3 + (n_ent >= 10)
        else:
            e1, e2 = rng.sample(range(n_ent), 2)
            d_ = abs(truth[(e1, a)] - truth[(e2, a)])
            if d_ == 0:
                continue
            ins, c = W.numfmt(rng, d_, ("Answer", "Difference", "Result"))
            ph = [f"By how much do the {ents[e1]} and the {ents[e2]} differ in {lab}?{ins}",
                  f"What is the absolute difference between the {lab} of the {ents[e1]} and that of the {ents[e2]}?{ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"They differ by {d_}. {c}"
            diff = 3
        made += 1
        yield W.say_task(slug=f"{made:02d}-{qk}", prompt=W.voice(rng, org, prompt, lead=rng.choice(["", "", "Using the dossier in this folder,"])), difficulty=min(5, diff),
                         start=files, contains=contains, gold=gold, tags=["conflict", "authority"], notes={"domain": key, "entities": n_ent, "question": qk})


@family("research-authority-table", category="research", lang="text", kind="greenfield", n=12,
        summary="resolve every figure of a dossier with conflicting sources and write the consolidated table to out.csv")
def gen_table(rng, n):
    made = 0
    while made < n:
        n_ent = rng.choice([3, 4, 5, 6, 8])
        org, key, dom, ents, truth, claims, lo, hi = build(rng, n_ent)
        files = render(rng, org, key, dom, ents, truth, claims, lo, hi)
        attrs = dom["attrs"]
        cols = ["site"] + [a[0].replace(" ", "_") for a in attrs]
        rows = [[ents[e]] + [truth[(e, a)] for a in range(3)] for e in range(n_ent)]
        rows.sort(key=lambda r: r[0])
        spec = W.csv_spec(cols, ["str", "int", "int", "int"], rows, key=[0])
        ph = [f"Build `out.csv` with the header `{','.join(cols)}`: one row per site, using for every figure the value the README says to trust. Sort by site name.",
              f"I need a clean table for the printers: `out.csv`, columns {', '.join(cols)}. One row per site; each figure must be the authoritative one under the README's rules (not the most common one).",
              f"Please consolidate the dossier into `out.csv` ({','.join(cols)}). Resolve disagreements as described in README.md."]
        made += 1
        yield W.file_task(slug=f"{made:02d}-consolidated", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=3 + (n_ent >= 5) + (n_ent >= 8), start=files, spec=spec,
                          solution={"out.csv": W.csv_text(cols, rows)}, scored=True, tags=["conflict", "authority", "table"], notes={"domain": key, "entities": n_ent})
