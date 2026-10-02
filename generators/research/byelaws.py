"""Byelaws amended by numbered orders: figures substituted, sections repealed or inserted, corrections printed later,
an order revoked before it commenced, drafts that never became law. Questions ask what applied on a date; answers
come from replaying the orders."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from fx import dd, family

from . import _world as W

SCENARIOS = {
    "quay": ("Quayside Byelaws", "harbour", [
        ("Maximum vessel length", "No vessel longer than {v} metres may berth at the north quay.", "metres", (8, 40)),
        ("Mooring limit", "A vessel may remain at a visitor berth for no more than {v} consecutive hours.", "hours", (12, 96)),
        ("Speed limit", "Inside the harbour limits no vessel shall exceed {v} knots.", "knots", (3, 10)),
        ("Quiet hours", "Engines and generators shall not be run from {v}:00 until 06:00 except in an emergency.", "o'clock", (20, 23)),
        ("Berthing fee", "The fee for a visitor berth is {v} credits per night.", "credits", (10, 120)),
        ("Fuel jetty", "No more than {v} vessels may use the fuel jetty at one time.", "vessels", (2, 5)),
        ("Late departure surcharge", "A surcharge of {v} credits applies to any vessel departing after its booked time.", "credits", (5, 60)),
        ("Pump-out", "A vessel with a holding tank must use the pump-out station at least once every {v} days in port.", "days", (2, 14)),
        ("Waste oil", "Waste oil must be handed to the reception tank within {v} hours of arrival.", "hours", (2, 48)),
        ("Crew passes", "Each berthed vessel is entitled to {v} crew passes for the gate.", "passes", (2, 6)),
    ]),
    "market": ("Market Hall Regulations", "market", [
        ("Stall width", "No stall may be wider than {v} metres.", "metres", (2, 9)),
        ("Opening hour", "The hall opens to traders at {v}:00 on trading days.", "o'clock", (5, 9)),
        ("Stall fee", "The stall fee is {v} credits per trading day.", "credits", (6, 60)),
        ("Stalls per trader", "No trader may hold more than {v} stalls at one time.", "stalls", (2, 5)),
        ("Deposit", "A new trader pays a refundable deposit of {v} credits.", "credits", (20, 200)),
        ("Cleaning charge", "A stall left unclean at closing incurs a charge of {v} credits.", "credits", (4, 40)),
        ("Loading window", "Vehicles may load or unload for no longer than {v} minutes at the east gate.", "minutes", (10, 60)),
        ("Notice of absence", "A trader who will miss a trading day must give notice at least {v} days beforehand.", "days", (2, 10)),
        ("Generator limit", "Generators above {v} decibels are not allowed in the hall.", "decibels", (50, 85)),
        ("Trader badges", "Each stall holder may register up to {v} helpers' badges.", "badges", (2, 6)),
    ]),
    "allotments": ("Allotment Rules", "allotment", [
        ("Annual rent", "The annual rent for a standard plot is {v} credits.", "credits", (15, 150)),
        ("Shed size", "A shed on a plot may not exceed {v} square metres.", "square metres", (3, 12)),
        ("Bonfire hours", "Bonfires are permitted only after {v}:00 on permitted days.", "o'clock", (15, 20)),
        ("Waiting list", "A name stays on the waiting list for at most {v} years without renewal.", "years", (2, 6)),
        ("Notice to quit", "The society gives {v} days' notice to quit for a neglected plot.", "days", (14, 90)),
        ("Water cap", "Each plot may draw no more than {v} litres of mains water per week.", "litres", (100, 900)),
        ("Hedge height", "Boundary hedges may not exceed {v} metres in height.", "metres", (2, 4)),
        ("Guest limit", "A plot holder may bring up to {v} guests at a time.", "guests", (2, 6)),
        ("Compost bins", "Each plot may keep up to {v} compost bins.", "bins", (2, 4)),
        ("Key deposit", "The deposit for the gate key is {v} credits.", "credits", (5, 40)),
    ]),
}


@dataclass
class Sec:
    sid: str
    title: str
    text: str
    unit: str
    rng_: tuple
    v0: int | None  # None: not in the original (inserted later)
    after: str = ""


@dataclass
class Op:
    order: int
    sec: str
    kind: str  # set | repeal | insert
    value: int | None
    commence: dt.date
    printed: int | None = None  # figure printed in the order if it differs from the true one (corrected later)
    old: int | None = None
    para: int = 1
    explicit_date: bool = False


@dataclass
class Order:
    no: int
    made: dt.date
    commence: dt.date
    ops: list[Op] = field(default_factory=list)
    revokes: int | None = None
    revoked: bool = False
    revoke_made: dt.date | None = None


@dataclass
class Correction:
    no: int
    made: dt.date
    order: int
    para: int
    printed: int
    true: int


def build(rng, n_orders: int, theme=None):
    key = rng.choice(sorted(SCENARIOS))
    title, kind, base = SCENARIOS[key]
    org = W.make_org(rng, theme, n_people=7)
    chosen = rng.sample(base, 8)
    secs: list[Sec] = []
    reserve = [c for c in base if c not in chosen]
    order_ids = list(range(1, 9))
    for i, (t, txt, unit, rg) in enumerate(chosen, 1):
        secs.append(Sec(str(i), t, txt, unit, rg, rng.randint(*rg)))
    for j, (t, txt, unit, rg) in enumerate(rng.sample(reserve, 2)):
        after = str(rng.randint(2, 7))
        sid = f"{after}{'AB'[j]}"
        secs.append(Sec(sid, t, txt, unit, rg, None, after=after))
    by_id = {s.sid: s for s in secs}
    made0 = W.base_date(rng)
    cur = made0
    orders: list[Order] = []
    corrections: list[Correction] = []
    hist: dict[str, list[Op]] = {s.sid: [] for s in secs}
    locked: dict[str, int] = {}  # section -> order id that holds it (pending revocation/correction)
    pending_revoke: Order | None = None
    pending_corr: tuple[Order, Op] | None = None
    inserted = set()
    no = 0
    last_commence: dict[str, dt.date] = {}

    def prior_value(sid):
        for op in reversed(hist[sid]):
            if orders[op.order - 1].revoked:
                continue
            return None if op.kind == "repeal" else op.value
        return by_id[sid].v0

    while len(orders) < n_orders:
        cur = cur + dt.timedelta(days=rng.randint(18, 55))
        no = len(orders) + 1
        if pending_revoke is not None:
            tgt = pending_revoke
            pending_revoke = None
            for op in tgt.ops:
                locked.pop(op.sec, None)
            if cur < tgt.commence - dt.timedelta(days=2):
                o = Order(no, cur, cur)
                o.revokes = tgt.no
                tgt.revoked = True
                tgt.revoke_made = cur
                orders.append(o)
                continue
        if pending_corr is not None:
            od, op = pending_corr
            pending_corr = None
            corrections.append(Correction(len(corrections) + 1, cur, od.no, op.para, op.printed, op.value))
            locked.pop(op.sec, None)
            cur = cur + dt.timedelta(days=rng.randint(3, 12))
        # a normal order
        immediate = rng.random() < 0.4
        commence = cur if immediate else cur + dt.timedelta(days=rng.randint(20, 75))
        o = Order(no, cur, commence)
        free = [s for s in secs if s.sid not in locked and (s.v0 is not None or s.sid in inserted or True)]
        k = rng.choice([1, 1, 2, 2, 3])
        random_secs = rng.sample(free, min(k, len(free)))
        random_secs.sort(key=lambda s: s.sid)
        for para, s in enumerate(random_secs, 1):
            cm = commence
            explicit = False
            if rng.random() < 0.15:
                cm = commence + dt.timedelta(days=rng.randint(10, 40))
                explicit = True
            if cm < last_commence.get(s.sid, cm):
                cm = last_commence[s.sid]
                explicit = True
            pv = prior_value(s.sid)
            if s.v0 is None and s.sid not in inserted:
                v = rng.randint(*s.rng_)
                op = Op(no, s.sid, "insert", v, cm, para=para, explicit_date=explicit)
                inserted.add(s.sid)
            elif pv is None:
                # repealed earlier: skip (cannot amend a repealed section)
                continue
            elif rng.random() < 0.15 and sum(1 for x in secs if x.sid in inserted or x.v0 is not None) > 6:
                op = Op(no, s.sid, "repeal", None, cm, para=para, explicit_date=explicit, old=pv)
            else:
                v = pv
                for _ in range(20):
                    v = rng.randint(*s.rng_)
                    if v != pv:
                        break
                if v == pv:
                    continue
                op = Op(no, s.sid, "set", v, cm, para=len(o.ops) + 1, explicit_date=explicit, old=pv)
            op.para = len(o.ops) + 1
            o.ops.append(op)
            hist[s.sid].append(op)
            last_commence[s.sid] = cm
        if not o.ops:
            continue
        orders.append(o)
        # decide the fate of this order
        r = rng.random()
        if r < 0.14 and (commence - cur).days >= 25 and len(orders) < n_orders - 1:
            pending_revoke = o
            for op in o.ops:
                locked[op.sec] = o.no
        elif r < 0.30 and len(orders) < n_orders - 1:
            sets = [op for op in o.ops if op.kind == "set" and op.value is not None]
            if sets:
                op = rng.choice(sets)
                bad = op.value + rng.choice([-10, -1, 1, 10, 100])
                if bad > 0 and bad != op.value:
                    op.printed = bad
                    pending_corr = (o, op)
                    locked[op.sec] = o.no
    return org, title, kind, secs, orders, corrections, made0


def sec_text(s: Sec, v: int) -> str:
    return s.text.format(v=v)


def value_at(secs, orders, d: dt.date, sid: str):
    """(value or None if not in force, last effective op or None)"""
    s = next(x for x in secs if x.sid == sid)
    best = None
    for o in orders:
        if o.revoked:
            continue
        for op in o.ops:
            if op.sec == sid and op.commence <= d:
                if best is None or (op.commence, op.order) >= (best.commence, best.order):
                    best = op
    if best is None:
        return s.v0, None
    return (None if best.kind == "repeal" else best.value), best


def title_of(s: Sec) -> str:
    return s.title.lower()


def render(rng, org, title, kind, secs, orders, corrections, made0) -> dict[str, str]:
    files: dict[str, str] = {}
    base = [s for s in secs if s.v0 is not None]
    base.sort(key=lambda s: int(s.sid))
    lines = [f"{org.name}", f"{title.upper()}", f"as made on {W.d_long(made0)}", ""]
    for s in base:
        lines.append(f"{s.sid}. {s.title}. {sec_text(s, s.v0)}")
        lines.append("")
    files["byelaws/original.txt"] = "\n".join(lines)
    by_id = {s.sid: s for s in secs}
    for o in orders:
        head = [f"{org.name}", f"AMENDMENT ORDER AO-{o.no}", f"Made: {W.d_long(o.made)}"]
        if o.revokes:
            head.append("")
            head.append(f"1. Amendment Order AO-{o.revokes} is revoked in full. It is to be treated as never having had effect.")
            head.append("2. This Order comes into force on the day it is made.")
            files[f"orders/AO-{o.no:02d}.txt"] = "\n".join(head) + "\n"
            continue
        head.append(f"Commencement: {W.d_long(o.commence)} unless a paragraph says otherwise")
        head.append("")
        for op in o.ops:
            s = by_id[op.sec]
            tail = f" This paragraph has effect from {W.d_long(op.commence)}." if op.explicit_date else ""
            if op.kind == "set":
                shown = op.printed if op.printed is not None else op.value
                head.append(f"{op.para}. In section {op.sec} ({s.title}), for the figure \"{op.old}\" substitute \"{shown}\".{tail}")
            elif op.kind == "repeal":
                head.append(f"{op.para}. Section {op.sec} ({s.title}) is repealed.{tail}")
            else:
                head.append(f"{op.para}. After section {s.after} insert the following new section:{tail}")
                head.append(f"   \"{op.sec}. {s.title}. {sec_text(s, op.value)}\"")
        files[f"orders/AO-{o.no:02d}.txt"] = "\n".join(head) + "\n"
    for c in corrections:
        files[f"orders/CN-{c.no:02d}.txt"] = dd(f"""
            {org.name}
            CORRECTION NOTICE CN-{c.no}
            Issued: {W.d_long(c.made)}

            In Amendment Order AO-{c.order}, paragraph {c.para}, for the figure "{c.printed}" read "{c.true}".
            This correction has effect as if the Order had been printed correctly.
        """)
    # drafts that were never made: decoys
    for j in range(rng.randint(1, 3)):
        s = rng.choice(base)
        dv = rng.choice([x for x in range(s.rng_[0], s.rng_[1] + 1) if x != s.v0])
        d = made0 + dt.timedelta(days=rng.randint(30, 400))
        files[f"drafts/draft-{j + 1}.txt"] = dd(f"""
            DRAFT, FOR CONSULTATION ONLY. NOT MADE.
            {org.name}
            Proposed Amendment Order, circulated {W.d_long(d)}

            1. In section {s.sid} ({s.title}), for the figure "{s.v0}" substitute "{dv}".
            (The committee did not proceed with this draft.)
        """)
    W.pad_files(rng, org, files, rng.randint(3, 8), "notices", made0, orders[-1].made)
    files["README.md"] = dd(f"""
        # {title} (legal archive)

        * `byelaws/original.txt`: the byelaws as first made.
        * `orders/`: amendment orders (AO-n) and correction notices (CN-n), numbered in the order they were made.
        * `drafts/`: consultation drafts. They were never made and have no legal effect.
        * `notices/`: general notices, not part of the law.

        Rules for reading the orders: an order's changes apply from its commencement date, or from the date a paragraph
        gives for itself. The figure in force on a day is the one set by the latest-commencing change before or on that day
        (the higher-numbered order wins if two commence together). "For the figure X substitute Y" refers to the figure
        in the law at the time. A correction notice works as if the order had been printed correctly. An order that was
        revoked before it commenced is treated as never made.
    """)
    return files


def _pick_day(rng, orders, made0):
    end = max(op.commence for o in orders for op in o.ops) if any(o.ops for o in orders) else made0
    return made0 + dt.timedelta(days=rng.randint(10, (end - made0).days + 30))


@family("research-byelaw-lookup", category="research", lang="text", kind="lookup", n=18, mode="answer",
        summary="what a byelaw figure was on a date after substitutions, repeals, insertions, corrections and a revoked order")
def gen_lookup(rng, n):
    made = 0
    while made < n:
        n_orders = rng.choice([2, 3, 4, 6, 8, 10])
        org, title, kind, secs, orders, corrs, made0 = build(rng, n_orders)
        files = render(rng, org, title, kind, secs, orders, corrs, made0)
        eff_orders = [o for o in orders if not o.revoked]
        touched = sorted({op.sec for o in eff_orders for op in o.ops})
        if len(touched) < 2:
            continue
        sid = rng.choice(touched)
        s = next(x for x in secs if x.sid == sid)
        qk = rng.choice(["original", "value_on", "value_on", "which_order", "current_since", "n_changed"])
        end = max(op.commence for o in eff_orders for op in o.ops)
        if qk == "original":
            s0 = next(x for x in secs if x.v0 is not None)
            sid = s0.sid
            s = s0
            ins, c = W.numfmt(rng, s.v0, ("Answer", "Result", "Figure"))
            ph = [f"What did the {title} originally say for the {title_of(s)} (the text as first made, before any amendment)?{ins}",
                  f"In the byelaws as first made, what is the figure for \"{title_of(s)}\"?{ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"Originally {s.v0} {s.unit}. {c}"
            diff = 1 + (n_orders >= 6)
        elif qk == "value_on":
            for _ in range(30):
                d = _pick_day(rng, orders, made0)
                v, op = value_at(secs, orders, d, sid)
                if v is not None:
                    break
            else:
                continue
            ins, c = W.numfmt(rng, v, ("Answer", "Result", "Figure"))
            ph = [f"Under the {title}, what was the {title_of(s)} figure on {W.d_long(d)}?{ins}",
                  f"What number did the section on \"{title_of(s)}\" give on {W.d_us(d)}, counting every amendment in force by then?{ins}",
                  f"A visitor was told something about \"{title_of(s)}\" on {W.d_long(d)}. What did the law actually say that day (the figure)?{ins}"]
            diff = 2 + (len(orders) >= 6) + (any(o.revoked for o in orders)) + (any(op.printed for o in orders for op in o.ops if op.sec == sid))
            prompt, contains, gold = rng.choice(ph), [c], f"On {W.d_long(d)} section {sid} ({s.title}) gave {v} {s.unit}. {c}"
        elif qk == "which_order":
            v, op = value_at(secs, orders, end + dt.timedelta(days=1), sid)
            if op is None or v is None:
                continue
            ph = [f"Which amendment order set the figure now in force for the {title_of(s)} (taking everything in the archive into account)? Give it as AO-<number>.",
                  f"Which order last changed \"{title_of(s)}\" in a way that is still in force today ({W.d_long(end + dt.timedelta(days=1))})? Reply AO-<number>."]
            prompt = rng.choice(ph)
            contains, gold = [f"AO-{op.order}"], f"AO-{op.order} set the current figure ({v} {s.unit})."
            diff = 2 + (len(orders) >= 6) + any(o.revoked for o in orders)
        elif qk == "current_since":
            v, op = value_at(secs, orders, end + dt.timedelta(days=1), sid)
            if op is None or v is None:
                continue
            ph = [f"Since which date has the current {title_of(s)} figure been in force? Treat {W.d_long(end + dt.timedelta(days=1))} as today and answer YYYY-MM-DD.",
                  f"What is the commencement date (ISO) of the change that gave the {title_of(s)} its present figure? 'Present' means {W.d_long(end + dt.timedelta(days=1))}."]
            prompt, contains, gold = rng.choice(ph), [W.d_iso(op.commence)], f"It has applied since {W.d_iso(op.commence)}."
            diff = 3 + (len(orders) >= 8)
        else:
            d = _pick_day(rng, orders, made0)
            cnt = 0
            for x in secs:
                if x.v0 is None:
                    continue
                v, _ = value_at(secs, orders, d, x.sid)
                if v != x.v0:
                    cnt += 1
            if cnt == 0:
                continue
            ins, c = W.numfmt(rng, cnt, ("Count", "Total", "Answer"))
            ph = [f"Of the {sum(1 for x in secs if x.v0 is not None)} sections in the original text, how many differ on {W.d_long(d)} from the original (a different figure, or repealed)?{ins}",
                  f"On {W.d_long(d)}, how many of the original sections no longer read as first made, either because the figure changed or because they were repealed? (Sections inserted later don't count; a figure that went up and came back counts as unchanged.){ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"{cnt} original sections differed on {W.d_long(d)}. {c}"
            diff = 3 + (len(orders) >= 6) + (len(orders) >= 9)
        made += 1
        yield W.say_task(slug=f"{made:02d}-{qk.replace('_', '-')}", prompt=W.voice(rng, org, prompt, lead=rng.choice(["", "", "Using the legal archive in this folder,"])),
                         difficulty=min(5, diff), start=files, contains=contains, gold=gold, tags=["byelaws", "temporal", "amendments"],
                         notes={"scenario": kind, "orders": n_orders, "question": qk, "revoked": [o.no for o in orders if o.revoked]})


@family("research-byelaw-consolidate", category="research", lang="text", kind="greenfield", n=12,
        summary="write the consolidated figures of an amended byelaw as of a date (answer.json)")
def gen_consolidate(rng, n):
    made = 0
    while made < n:
        n_orders = rng.choice([3, 4, 5, 7, 9])
        org, title, kind, secs, orders, corrs, made0 = build(rng, n_orders)
        files = render(rng, org, title, kind, secs, orders, corrs, made0)
        eff = [o for o in orders if not o.revoked]
        if len(eff) < 3:
            continue
        d = _pick_day(rng, orders, made0)
        exp = {}
        for x in secs:
            v, _ = value_at(secs, orders, d, x.sid)
            if v is None and x.v0 is None:
                continue  # not yet inserted: omitted
            exp[x.sid] = v
        fields = {"sections": W.jf("map", {k: (v if v is not None else "repealed") for k, v in exp.items()}, sub="str")}
        # the checker's "str" compare: figures as strings
        fields["sections"]["value"] = {k: str(v) if v is not None else "repealed" for k, v in exp.items()}
        ph = [f"Produce the consolidated {title} as they stood on {W.d_long(d)}. Write `answer.json` as {{\"sections\": {{\"<section number>\": <figure>}}}} with one entry for every section that existed on that date "
              f"(use the string \"repealed\" instead of a figure for a repealed section; leave out sections not yet inserted).",
              f"I need a consolidated snapshot of the {title} for {W.d_iso(d)}. `answer.json`: key `sections`, an object from section number (like \"3\" or \"4A\") to the figure in force that day, or \"repealed\". "
              f"Only include sections that were part of the law on that day."]
        made += 1
        yield W.file_task(slug=f"{made:02d}-snapshot", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=3 + (n_orders >= 5) + (n_orders >= 8), start=files,
                          spec=W.json_spec(fields), solution={"answer.json": W.dumps({"sections": {k: (v if v is not None else "repealed") for k, v in exp.items()}})},
                          scored=True, tags=["byelaws", "temporal", "consolidation"], notes={"scenario": kind, "orders": n_orders, "date": W.d_iso(d)})
