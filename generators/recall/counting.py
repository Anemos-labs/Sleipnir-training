"""Record piles: dozens of small records (inspections, maintenance jobs, complaints) in three layouts. Questions need the
whole pile: a count under a compound filter, the set of matching ids (answer.json), or an ordering (order.json)."""
from __future__ import annotations

import datetime as dt

from fx import dd, family

from generators.research import _world as W
from . import _recall as R

DOMAINS = {
    "inspection": dict(noun="inspection", plural="inspections", prefix="INSP", dir="inspections", results=["pass", "fail", "conditional"], bad=["fail", "conditional"],
                       metric_label="Defects found", metric_word="defects", cats=["electrical", "structural", "hygiene", "fire", "waste"], follow="Follow-up visit needed",
                       who="Inspector"),
    "job": dict(noun="maintenance job", plural="maintenance jobs", prefix="JOB", dir="jobs", results=["done", "deferred", "abandoned"], bad=["deferred", "abandoned"],
                metric_label="Hours spent", metric_word="hours", cats=["plumbing", "painting", "locks", "glazing", "gardening"], follow="Needs parts", who="Engineer"),
    "complaint": dict(noun="complaint", plural="complaints", prefix="CMP", dir="complaints", results=["resolved", "unresolved", "escalated"], bad=["unresolved", "escalated"],
                      metric_label="Contacts with the customer", metric_word="contacts", cats=["noise", "billing", "delay", "damage", "manners"], follow="Callback promised",
                      who="Handler"),
}


def build(rng, n_rec: int, dom_key: str, org=None):
    dom = DOMAINS[dom_key]
    org = org or W.make_org(rng, None, n_people=7, n_assets=4, n_sites=rng.choice([4, 5, 6]))
    lo = W.base_date(rng)
    hi = lo + dt.timedelta(days=rng.randint(150, 330))
    recs = []
    nums = rng.sample(range(1, 9000), n_rec)
    for i in range(n_rec):
        d = W.rand_date(rng, lo, hi)
        recs.append(dict(
            id=f"{dom['prefix']}-{nums[i]:04d}", site=rng.choice(org.sites), date=d, who=rng.choice(org.people[:6]), cat=rng.choice(dom["cats"]),
            result=rng.choices(dom["results"], [50, 35, 15])[0], metric=rng.choices(range(0, 10), [20, 16, 14, 12, 10, 8, 7, 6, 4, 3])[0],
            follow=rng.random() < 0.35, priority=rng.choice([1, 2, 3, 4]), due=d + dt.timedelta(days=rng.randint(5, 60)), style=rng.choice(["form", "prose", "log"]),
        ))
    return org, dom, recs, lo, hi


def render(rng, org, dom, recs) -> dict[str, str]:
    files: dict[str, str] = {}
    mw, ml = dom["metric_word"], dom["metric_label"]
    for r in recs:
        yn = "yes" if r["follow"] else "no"
        note = W.filler_line(rng, org, r["date"], r["date"] + dt.timedelta(days=20))
        if r["style"] == "form":
            text = dd(f"""
                {dom['noun'].upper()} {r['id']}
                Site: {r['site']}
                Date: {W.d_iso(r['date'])}
                {dom['who']}: {r['who'].full}
                Category: {r['cat']}
                Result: {r['result'].upper()}
                {ml}: {r['metric']}
                {dom['follow']}: {yn}
                Priority: P{r['priority']}   Due: {W.d_iso(r['due'])}
            """) + f"Remarks: {note}\n"
        elif r["style"] == "prose":
            text = (f"{r['id']}. On {W.d_long(r['date'])}, {r['who'].full} dealt with a {r['cat']} {dom['noun']} at {r['site']}. The outcome was {r['result']}. "
                    f"{ml} for this one: {r['metric']}. {dom['follow']}? {yn.capitalize()}. It was rated priority P{r['priority']} and is due by {W.d_long(r['due'])}. {note}\n")
        else:
            text = (f"{W.d_iso(r['date'])} | {r['id']} | {r['site']} | {r['cat']} | {r['result'].upper()} | {mw}={r['metric']} | followup={'Y' if r['follow'] else 'N'} | "
                    f"{r['who'].last} | P{r['priority']} | due {W.d_iso(r['due'])}\n# {note}\n")
        files[f"{dom['dir']}/{r['id']}.txt"] = text
    files["README.md"] = dd(f"""
        # {dom['plural'].capitalize()} archive

        One file per {dom['noun']} in `{dom['dir']}/`. Three layouts are in use (a form, a short prose paragraph, and a one-line log
        entry); every one carries the same facts: id, site, date, who handled it, category, result ({', '.join(dom['results'])}),
        {mw}, whether "{dom['follow'].lower()}", priority (P1 is the most urgent) and the due date. The line starting with "Remarks",
        "#", or the last sentence of a paragraph is office chatter, not data.
    """)
    return files


def pile_size(rng, win, rec_bytes=520):
    return max(24, min(260, int(R.target_chars(win, rng.choice([1.0, 1.25, 1.5])) / rec_bytes)))


def describe(dom, flt) -> str:
    parts = []
    for k, v in flt:
        if k == "site":
            parts.append(f"at {v}")
        elif k == "result":
            parts.append(f"with result {v}")
        elif k == "result_not":
            parts.append(f"whose result was not {v}")
        elif k == "cat":
            parts.append(f"in the {v} category")
        elif k == "metric_ge":
            parts.append(f"with at least {v} {dom['metric_word']}")
        elif k == "who":
            parts.append(f"handled by {v.full}")
        elif k == "follow":
            parts.append(f"where \"{dom['follow'].lower()}\" is {'yes' if v else 'no'}")
        elif k == "month":
            parts.append(f"dated in {W.MONTHS[v[1] - 1]} {v[0]}")
        elif k == "prio":
            parts.append(f"rated P{v} or more urgent")
    return ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1] if len(parts) > 1 else parts[0]


def matches(r, flt) -> bool:
    for k, v in flt:
        if k == "site" and r["site"] != v:
            return False
        if k == "result" and r["result"] != v:
            return False
        if k == "result_not" and r["result"] == v:
            return False
        if k == "cat" and r["cat"] != v:
            return False
        if k == "metric_ge" and r["metric"] < v:
            return False
        if k == "who" and r["who"] is not v:
            return False
        if k == "follow" and r["follow"] != v:
            return False
        if k == "month" and (r["date"].year, r["date"].month) != v:
            return False
        if k == "prio" and r["priority"] > v:
            return False
    return True


def random_filter(rng, org, dom, recs, k: int):
    pool = ["site", "result", "result_not", "cat", "metric_ge", "who", "follow", "month", "prio"]
    for _ in range(40):
        kinds = rng.sample(pool, k)
        if "result" in kinds and "result_not" in kinds:
            continue
        ref = rng.choice(recs)
        flt = []
        for kd in kinds:
            if kd == "site":
                flt.append((kd, ref["site"]))
            elif kd == "result":
                flt.append((kd, ref["result"]))
            elif kd == "result_not":
                flt.append((kd, rng.choice(dom["results"])))
            elif kd == "cat":
                flt.append((kd, ref["cat"]))
            elif kd == "metric_ge":
                flt.append((kd, rng.choice([2, 3, 4, 5, 6])))
            elif kd == "who":
                flt.append((kd, ref["who"]))
            elif kd == "follow":
                flt.append((kd, ref["follow"]))
            elif kd == "month":
                flt.append((kd, (ref["date"].year, ref["date"].month)))
            else:
                flt.append((kd, rng.choice([1, 2, 3])))
        hit = [r for r in recs if matches(r, flt)]
        if 2 <= len(hit) <= max(12, len(recs) // 3):
            return flt, hit
    return None, None


@family("recall-count-files", category="recall", lang="text", kind="lookup", n=22, mode="answer",
        summary="count the records matching a compound filter across a pile of 40-200 small files in three layouts")
def gen_count(rng, n):
    made = 0
    while made < n:
        tier = R.tier(rng)
        win = None if tier == "easy" else R.window(rng)
        dkey = rng.choice(sorted(DOMAINS))
        nrec = rng.choice([14, 20, 28]) if tier == "easy" else pile_size(rng, win)
        org, dom, recs, lo, hi = build(rng, nrec, dkey)
        k = rng.choice([1, 1, 2]) if tier == "easy" else rng.choice([2, 2, 3])
        flt, hit = random_filter(rng, org, dom, recs, k)
        if not flt:
            continue
        files = render(rng, org, dom, recs)
        ins, c = W.numfmt(rng, len(hit), ("Count", "Total", "Answer"))
        desc = describe(dom, flt)
        ph = [f"How many {dom['plural']} {desc} are in this archive?{ins}",
              f"Count the {dom['plural']} {desc}. Read the files, don't estimate.{ins}",
              f"I need a number for a report: {dom['plural']} {desc}, how many?{ins}",
              f"Can you tell me how many {dom['plural']} there are {desc}?{ins}",
              f"For the monthly figures: the number of {dom['plural']} {desc}.{ins}"]
        made += 1
        d = k + (nrec >= 80) + (nrec >= 160)
        yield W.say_task(slug=f"{made:02d}-{dkey}-{k}cond", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=min(5, d), start=files, contains=[c],
                         gold=f"{len(hit)} {dom['plural']}. {c}", context_window=win, tags=["counting", "pile"], notes={"records": nrec, "domain": dkey, "conditions": k})


@family("recall-find-all", category="recall", lang="text", kind="greenfield", n=18,
        summary="list the ids of every record matching a compound filter in a pile of small files (answer.json)")
def gen_find(rng, n):
    made = 0
    while made < n:
        tier = R.tier(rng)
        win = None if tier == "easy" else R.window(rng)
        dkey = rng.choice(sorted(DOMAINS))
        nrec = rng.choice([14, 20, 28]) if tier == "easy" else pile_size(rng, win)
        org, dom, recs, lo, hi = build(rng, nrec, dkey)
        flt, hit = random_filter(rng, org, dom, recs, rng.choice([1, 1, 2]) if tier == "easy" else rng.choice([2, 2, 3]))
        if not flt:
            continue
        files = render(rng, org, dom, recs)
        ids = sorted(r["id"] for r in hit)
        desc = describe(dom, flt)
        ph = [f"List every {dom['noun']} {desc}. Write `answer.json` as {{\"ids\": [\"{dom['prefix']}-0001\", ...]}} with the record ids in any order.",
              f"Which {dom['plural']} {desc}? I need the full list of ids in `answer.json` under the key `ids`.",
              f"Please find all {dom['plural']} {desc} and save their ids to `answer.json` ({{\"ids\": [...]}}).",
              f"Pull out the ids of the {dom['plural']} {desc}. I want them in `answer.json`, key `ids`, as strings exactly as in the filenames.",
              f"Which {dom['plural']} {desc}? Please put the complete list of ids in `answer.json` ({{\"ids\": [...]}}); order doesn't matter."]
        made += 1
        d = len(flt) + (nrec >= 80) + (nrec >= 160)
        yield W.file_task(slug=f"{made:02d}-{dkey}-{len(ids)}ids", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=min(5, d), start=files,
                          spec=W.json_spec({"ids": W.jf("set", ids)}), solution={"answer.json": W.dumps({"ids": ids})}, scored=True, context_window=win,
                          tags=["pile", "set-answer"], notes={"records": nrec, "domain": dkey, "matches": len(ids)})


@family("recall-order-files", category="recall", lang="text", kind="greenfield", n=16,
        summary="order the open records of a pile by priority, due date and id (order.json)")
def gen_order(rng, n):
    made = 0
    while made < n:
        tier = R.tier(rng)
        win = None if tier == "easy" else R.window(rng)
        dkey = rng.choice(sorted(DOMAINS))
        nrec = rng.choice([24, 30, 36]) if tier == "easy" else max(30, pile_size(rng, win) // 2)
        org, dom, recs, lo, hi = build(rng, nrec, dkey)
        files = render(rng, org, dom, recs)
        site = rng.choice(org.sites)
        bad = dom["bad"]
        cond = rng.choice(["site_bad", "cat_bad", "follow"])
        if cond == "site_bad":
            sel = [r for r in recs if r["site"] == site and r["result"] in bad]
            desc = f"at {site} whose result is one of {', '.join(bad)}"
        elif cond == "cat_bad":
            cat = rng.choice(dom["cats"])
            sel = [r for r in recs if r["cat"] == cat and r["result"] in bad]
            desc = f"in the {cat} category whose result is one of {', '.join(bad)}"
        else:
            sel = [r for r in recs if r["follow"] and r["site"] == site]
            desc = f"at {site} where \"{dom['follow'].lower()}\" is yes"
        if not (3 <= len(sel) <= 14):
            continue
        sel.sort(key=lambda r: (r["priority"], r["due"], r["id"]))
        ids = [r["id"] for r in sel]
        ph = [f"Make me a work queue: all {dom['plural']} {desc}, ordered by priority (P1 first), then earliest due date, then id. Write `order.json` as {{\"queue\": [\"<id>\", ...]}}.",
              f"Which {dom['plural']} {desc} should be handled first? Give me the full ordering in `order.json` under `queue`: most urgent priority first, ties broken by the earlier due date, then by id (ascending).",
              f"Please sort the {dom['plural']} {desc} into a queue and save it as `order.json` ({{\"queue\": [...]}}): P1 before P2 and so on, then the earlier due date, then the lower id.",
              f"I'm planning next week's work. List, in `order.json` under `queue`, every {dom['noun']} {desc}, ordered by priority (P1 first), then due date (earliest first), then id."]
        made += 1
        d = 2 + (tier != "easy") + (len(sel) >= 6) + (len(sel) >= 10) + (nrec >= 60)
        yield W.file_task(slug=f"{made:02d}-{dkey}-{len(ids)}", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=min(5, d), start=files,
                          spec=W.json_spec({"queue": W.jf("list", ids)}, file="order.json"), solution={"order.json": W.dumps({"queue": ids})}, scored=True, context_window=win,
                          tags=["pile", "ordering"], notes={"records": nrec, "domain": dkey, "selected": len(ids)})
