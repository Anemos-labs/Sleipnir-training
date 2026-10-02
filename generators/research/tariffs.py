"""Water-board tariff notices: scheduled rate changes per customer class, withdrawn and corrected notices, consultation
drafts, and meter readings. Questions: which rate applied when, which notice set it, and the exact bill for a metering
period that straddles one or more tariff changes (computed with exact fractions)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from fractions import Fraction

from fx import dd, family

from . import _world as W

CLASSES = ["Domestic", "Small Business", "Irrigation", "Community Hall", "Allotment Society", "Boarding House"]


@dataclass
class Change:
    notice: int
    cls: str
    field: str  # standing | rate
    value: int
    eff: dt.date
    printed: int | None = None


@dataclass
class Notice:
    no: int
    made: dt.date
    eff: dt.date
    changes: list[Change] = field(default_factory=list)
    withdrawn_by: int | None = None
    withdraws: int | None = None


def build(rng, n_notices: int):
    org = W.make_org(rng, "waterworks", n_people=8)
    classes = rng.sample(CLASSES, rng.choice([3, 3, 4]))
    d0 = W.base_date(rng)
    v0 = {c: {"standing": rng.randint(18, 110), "rate": rng.randint(60, 380)} for c in classes}
    notices: list[Notice] = []
    cur = d0
    corr = []  # (notice, change index, issued date)
    pend_withdraw = None
    while len(notices) < n_notices:
        cur = cur + dt.timedelta(days=rng.randint(20, 60))
        no = len(notices) + 1
        if pend_withdraw is not None:
            tgt = pend_withdraw
            pend_withdraw = None
            if cur < tgt.eff - dt.timedelta(days=2):
                n = Notice(no, cur, cur)
                n.withdraws = tgt.no
                tgt.withdrawn_by = no
                notices.append(n)
                continue
        eff = cur + dt.timedelta(days=rng.randint(14, 70))
        n = Notice(no, cur, eff)
        for c in rng.sample(classes, rng.choice([1, 1, 2])):
            fields = rng.choice([["standing"], ["rate"], ["rate"], ["standing", "rate"]])
            for f in fields:
                cvals = [ch.value for x in notices if x.withdrawn_by is None for ch in x.changes if ch.cls == c and ch.field == f]
                base = cvals[-1] if cvals else v0[c][f]
                step = rng.choice([-1, 1, 1, 1]) * rng.randint(3, 30 if f == "rate" else 12)
                v = max(5, base + step)
                n.changes.append(Change(no, c, f, v, eff))
        notices.append(n)
        r = rng.random()
        if r < 0.15 and len(notices) < n_notices:
            pend_withdraw = n
        elif r < 0.30 and n.changes:
            ch = rng.choice(n.changes)
            ch.printed = ch.value + rng.choice([-20, -10, -1, 1, 9, 10, 100])
            corr.append((n, ch))
    return org, classes, d0, v0, notices, corr


def value_at(v0, notices, cls: str, fld: str, d: dt.date):
    best = None
    for n in notices:
        if n.withdrawn_by is not None or n.withdraws is not None:
            continue
        for ch in n.changes:
            if ch.cls == cls and ch.field == fld and ch.eff <= d:
                if best is None or (ch.eff, ch.notice) >= (best.eff, best.notice):
                    best = ch
    return (best.value if best else v0[cls][fld]), best


def render(rng, org, classes, d0, v0, notices, corr):
    files: dict[str, str] = {}
    lines = [org.name, "TARIFF SCHEDULE (initial)", f"Applies from {W.d_long(d0)}", ""]
    for c in classes:
        lines.append(f"{c}: standing charge {v0[c]['standing']} cents per day; volume rate {v0[c]['rate']} cents per kilolitre")
    files["tariffs/schedule-initial.txt"] = "\n".join(lines) + "\n"
    for n in notices:
        if n.withdraws:
            files[f"tariffs/TN-{n.no:02d}.txt"] = dd(f"""
                {org.name}
                TARIFF NOTICE TN-{n.no}
                Issued: {W.d_long(n.made)}

                Tariff Notice TN-{n.withdraws} is withdrawn in full before it takes effect. The tariffs in force are unchanged by it.
            """)
            continue
        style = rng.choice(["list", "prose"])
        if style == "list":
            body = [f"{org.name}", f"TARIFF NOTICE TN-{n.no}", f"Issued: {W.d_long(n.made)}", f"Takes effect: {W.d_long(n.eff)}", "", "Changes:"]
            for ch in n.changes:
                shown = ch.printed if ch.printed is not None else ch.value
                what = "standing charge" if ch.field == "standing" else "volume rate"
                unit = "cents per day" if ch.field == "standing" else "cents per kilolitre"
                body.append(f"  - {ch.cls}: {what} becomes {shown} {unit}")
            body.append("")
            body.append("All other tariffs are unchanged.")
        else:
            body = [f"{org.name}", f"TARIFF NOTICE TN-{n.no}", f"Issued: {W.d_long(n.made)}", ""]
            parts = []
            for ch in n.changes:
                shown = ch.printed if ch.printed is not None else ch.value
                what = "standing charge" if ch.field == "standing" else "volume rate"
                unit = "cents per day" if ch.field == "standing" else "cents per kilolitre"
                parts.append(f"the {ch.cls} {what} will be {shown} {unit}")
            body.append(f"With effect from {W.d_long(n.eff)}, " + "; ".join(parts) + ". No other tariff changes.")
        files[f"tariffs/TN-{n.no:02d}.txt"] = "\n".join(body) + "\n"
    for i, (n, ch) in enumerate(corr, 1):
        what = "standing charge" if ch.field == "standing" else "volume rate"
        unit = "cents per day" if ch.field == "standing" else "cents per kilolitre"
        d = n.made + dt.timedelta(days=rng.randint(2, 12))
        files[f"tariffs/correction-{i}.txt"] = dd(f"""
            {org.name}
            CORRECTION TO TARIFF NOTICE TN-{n.no}
            Issued: {W.d_long(d)}

            The {ch.cls} {what} in TN-{n.no} was printed as {ch.printed} {unit}. The correct figure is {ch.value} {unit}.
            The correct figure applies from the date the notice takes effect.
        """)
    for j in range(rng.randint(1, 2)):
        c = rng.choice(classes)
        d = d0 + dt.timedelta(days=rng.randint(60, 400))
        files[f"consultation/proposal-{j + 1}.txt"] = dd(f"""
            CONSULTATION PAPER, NOT A TARIFF NOTICE
            {org.name}, {W.d_long(d)}

            The Board is considering a {c} volume rate of {rng.randint(60, 400)} cents per kilolitre from the following year.
            No decision has been taken. Nothing in this paper changes any tariff.
        """)
    return files


def accounts_and_readings(rng, org, classes, d0, horizon: dt.date):
    n_acc = rng.randint(6, 10)
    accts = []
    used = set()
    while len(accts) < n_acc:
        a = f"AC-{rng.randint(1000, 9999)}"
        if a not in used:
            used.add(a)
            accts.append((a, rng.choice(classes)))
    people = org.people
    suffix = {"Small Business": ["Bakery", "Workshop", "Dairy", "Print Shop", "Laundry"], "Irrigation": ["Farm", "Nursery", "Market Garden"],
              "Community Hall": ["Hall", "Village Hall"], "Allotment Society": ["Allotments"], "Boarding House": ["Guest House", "Lodging House"]}
    acc_rows = [[a, rng.choice(people).last + " household" if c == "Domestic" else rng.choice(W.NAME_WORDS) + " " + rng.choice(suffix[c]), c] for a, c in accts]
    readings: dict[str, list[tuple[dt.date, int]]] = {}
    for a, c in accts:
        d = d0 + dt.timedelta(days=rng.randint(0, 25))
        r = rng.randint(100, 5000)
        lst = [(d, r)]
        while d < horizon:
            d = d + dt.timedelta(days=rng.randint(26, 38))
            r += rng.randint(8, 60)
            lst.append((d, r))
        readings[a] = lst
    files = {"accounts.csv": W.csv_text(["account", "name", "class"], acc_rows)}
    quarters: dict[str, list] = {}
    for a, lst in readings.items():
        for d, r in lst:
            q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
            quarters.setdefault(q, []).append([a, W.d_iso(d), r])
    for q, rows in quarters.items():
        rows.sort(key=lambda x: (x[1], x[0]))
        files[f"readings/{q}.csv"] = W.csv_text(["account", "read_on", "meter_kl"], rows)
    return dict(accts), readings, files


def bill_cents(v0, notices, cls, d1, d2, units) -> int:
    days = (d2 - d1).days
    total = Fraction(0)
    d = d1
    while d < d2:
        st, _ = value_at(v0, notices, cls, "standing", d)
        rt, _ = value_at(v0, notices, cls, "rate", d)
        total += st + Fraction(units, days) * rt
        d += dt.timedelta(days=1)
    return total


def half_up(fr: Fraction) -> int:
    return int((fr * 2 + 1) // 2)


def money_str(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


README = dd("""
    # Tariff records

    * `tariffs/`: the initial schedule, numbered tariff notices (TN-n), corrections and withdrawals.
    * `consultation/`: papers the Board is thinking about. They change nothing.
    * `accounts.csv` and `readings/`: customer accounts (with their tariff class) and quarterly meter readings in kilolitres.

    Reading the notices: a change applies from the date its notice takes effect and stays until another change to the same
    figure (same class, same kind of charge) takes effect. If two notices changing the same figure take effect on the same
    day, the higher-numbered notice applies. A withdrawn notice never had effect. A correction replaces the printed figure for
    the whole life of the notice. Standing charge and volume rate change independently.

    Bills: a billing period runs from one reading date (included) to the next reading date (excluded), so
    `days = later date - earlier date`. The kilolitres used (difference of the two readings) are spread evenly over
    those days. Each day is charged its standing charge plus (kilolitres / days) x that day's volume rate, using the
    tariffs in force that day for the account's class. Add the days up and round the total once, to the nearest cent,
    half up. Bills are written in credits with two decimals (100 cents = 1 credit).
""")


@family("research-tariff-bill", category="research", lang="text", kind="lookup", n=18, mode="answer",
        summary="tariff in force on a date, which notice set it, and an exact bill across tariff changes")
def gen(rng, n):
    made = 0
    while made < n:
        k = rng.choice([2, 3, 4, 5, 6, 8])
        org, classes, d0, v0, notices, corr = build(rng, k)
        horizon = max(nn.eff for nn in notices) + dt.timedelta(days=60)
        accts, readings, rfiles = accounts_and_readings(rng, org, classes, d0, horizon)
        files = render(rng, org, classes, d0, v0, notices, corr)
        files.update(rfiles)
        W.pad_files(rng, org, files, rng.randint(3, 7), "notes", d0, horizon)
        files["README.md"] = README
        qk = rng.choice(["initial", "rate_on", "standing_on", "which_notice", "bill", "bill"])
        cls = rng.choice(classes)
        if qk == "initial":
            fld = rng.choice(["rate", "standing"])
            v = v0[cls][fld]
            what = "volume rate (cents per kilolitre)" if fld == "rate" else "daily standing charge (cents)"
            ins, c = W.numfmt(rng, v, ("Answer", "Result", "Cents"))
            ph = [f"What did the initial tariff schedule give as the {what} for {cls} customers?{ins}",
                  f"In the very first schedule (before any notice), what was the {what} for the {cls} class?{ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"The initial {cls} {what} was {v}. {c}"
            diff = 1 + (k >= 5)
        elif qk in ("rate_on", "standing_on"):
            fld = "rate" if qk == "rate_on" else "standing"
            d = d0 + dt.timedelta(days=rng.randint(0, (horizon - d0).days))
            v, ch = value_at(v0, notices, cls, fld, d)
            ins, c = W.numfmt(rng, v, ("Answer", "Result", "Cents"))
            what = "volume rate (cents per kilolitre)" if fld == "rate" else "daily standing charge (cents)"
            ph = [f"What was the {what} for {cls} customers on {W.d_long(d)}?{ins}",
                  f"A customer on the {cls} tariff asks what the {what.split(' (')[0]} was on {W.d_us(d)}. Give me the figure in cents.{ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"On {W.d_long(d)} the {cls} {what} was {v}. {c}"
            diff = 2 + (any(x.withdrawn_by or x.withdraws for x in notices)) + bool(corr) + (k >= 6)
        elif qk == "which_notice":
            fld = rng.choice(["rate", "standing"])
            end = horizon
            v, ch = value_at(v0, notices, cls, fld, end)
            if ch is None:
                continue
            what = "volume rate" if fld == "rate" else "standing charge"
            ph = [f"Which tariff notice set the {cls} {what} that applies today ({W.d_long(end)})? Reply with TN-<number>.",
                  f"Today is {W.d_long(end)}. Which notice is responsible for the current {cls} {what}? (TN-<number>)"]
            prompt, contains, gold = rng.choice(ph), [f"TN-{ch.notice}"], f"TN-{ch.notice} set it ({v} cents)."
            diff = 2 + bool(corr) + (any(x.withdrawn_by for x in notices)) + (k >= 6)
        else:
            a = rng.choice(sorted(accts))
            lst = readings[a]
            i = rng.randrange(len(lst) - 1)
            (d1, r1), (d2, r2) = lst[i], lst[i + 1]
            c_ = accts[a]
            fr = bill_cents(v0, notices, c_, d1, d2, r2 - r1)
            # avoid exact ties
            if (fr * 2).denominator == 1 and int(fr * 2) % 2 == 1:
                continue
            cents = half_up(fr)
            amount = money_str(cents)
            crossing = len({(f, (lambda ch: ch.notice if ch else 0)(value_at(v0, notices, c_, f, d1 + dt.timedelta(days=x))[1])) for f in ("standing", "rate") for x in range((d2 - d1).days)})
            ph = [f"What is the bill, in credits with two decimals, for account {a} for the metering period from its reading on {W.d_iso(d1)} to its next reading? The README explains how bills are worked out.",
                  f"Customer account {a} was read on {W.d_long(d1)} and again at the next reading. I need the exact amount to charge for that period (credits, two decimals).",
                  f"Please work out the invoice amount for {a} covering the period that starts with the {W.d_iso(d1)} meter reading. Credits, two decimal places, as per the README."]
            prompt, contains, gold = rng.choice(ph), [amount], f"The bill for {a} (class {c_}) from {W.d_iso(d1)} to {W.d_iso(d2)} is {amount} credits."
            diff = 3 + (crossing > 1) + (crossing > 3)
        made += 1
        yield W.say_task(slug=f"{made:02d}-{qk.replace('_', '-')}", prompt=W.voice(rng, org, prompt), difficulty=min(5, diff), start=files, contains=contains,
                         gold=gold, tags=["tariff", "temporal", "arithmetic"], notes={"notices": k, "question": qk})
