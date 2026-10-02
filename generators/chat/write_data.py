"""File-delivered writing with computed content: agendas, tables, JSON extraction, redaction, action items, pack lists, itineraries,
release notes and policy-based support replies. The checker recomputes everything from the same data the generator used."""
from __future__ import annotations

import itertools
import json
import re
from datetime import date, timedelta
from fractions import Fraction

from fx import Task, family

from . import _checker as K
from . import _common as C
from . import _forms as F
from .write_text import SAVE, _start_notes

# --------------------------------------------------------------------------------------------------------------------
# chat-write-agenda

TOPICS = ["Budget review", "Hiring plan", "Roadmap check", "Customer feedback", "Security update", "Office move", "Training calendar", "Vendor contracts", "Incident retro", "Q&A with the board",
          "Product demo", "Metrics dashboard", "Policy changes"]


@family("chat-write-agenda", category="chat", lang="text", kind="greenfield", n=12, summary="build a timed agenda that exactly fills a meeting window: minimum minutes per topic, a break, ordering rules and a cap per item; checked arithmetically")
def gen_agenda(rng, n):
    plan = [3, 3, 4, 4, 4, 5, 5, 3, 4, 5, 3, 4]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(200):
            k = {3: 4, 4: 5, 5: 6}[d]
            topics = rng.sample(TOPICS, k)
            mins = {t: rng.choice([10, 15, 20, 25]) for t in topics}
            start = rng.choice([9, 10, 13, 14]) * 60 + rng.choice([0, 30])
            welcome, wrap, brk = 5, 5, 10
            need = sum(mins.values()) + welcome + wrap + brk
            total = need + rng.choice([10, 15, 20, 25, 30])
            total = (total + 4) // 5 * 5
            cap = rng.choice([30, 35]) if d >= 4 else None
            end = start + total
            before = None
            if d >= 4:
                a, b = rng.sample(topics, 2)
                before = (a, b)
            brk_window = None
            if d >= 5:
                brk_window = (start + 50, end - 40)
            # constructive gold: order topics (respect `before`), place break
            order = list(topics)
            rng.shuffle(order)
            if before:
                ia, ib = order.index(before[0]), order.index(before[1])
                if ia > ib:
                    order[ia], order[ib] = order[ib], order[ia]
            extra = total - need
            dur = dict(mins)
            ti = 0
            while extra > 0:
                t = order[ti % len(order)]
                inc = 5
                if cap is None or dur[t] + inc <= cap:
                    dur[t] += inc
                    extra -= inc
                ti += 1
                if ti > 500:
                    break
            if extra > 0:
                continue
            seq = [("Welcome", welcome)]
            # break after enough topics to satisfy the window
            acc = welcome
            placed = False
            items = []
            for t in order:
                items.append((t, dur[t]))
            out, t_now, pos = [], start, 0
            out.append(("Welcome", welcome))
            elapsed = welcome
            for j, (t, du) in enumerate(items):
                out.append((t, du))
                elapsed += du
                if not placed and (brk_window is None or start + elapsed >= brk_window[0]) and j < len(items) - 1 and (brk_window is None or start + elapsed + brk <= brk_window[1] + 0):
                    out.append(("Break", brk))
                    elapsed += brk
                    placed = True
            if not placed:
                continue
            out.append(("Wrap-up", wrap))
            lines, cur = [], start
            for name, du in out:
                lines.append(f"{C.hhmm(cur)}-{C.hhmm(cur + du)} {name}")
                cur += du
            if cur != end:
                continue
            gold = "\n".join(lines) + "\n"
            cons = []
            cons.append(f"it starts at {C.hhmm(start)} and ends at {C.hhmm(end)}, with no gaps or overlaps")
            cons.append("it opens with a 5-minute 'Welcome', ends with a 5-minute 'Wrap-up', and has one 10-minute 'Break' in between (not first or last)")
            cons.append("every topic gets at least its minimum, and all durations are multiples of 5 minutes")
            if cap:
                cons.append(f"no single topic is longer than {cap} minutes")
            if before:
                cons.append(f"'{before[0]}' must come before '{before[1]}'")
            if brk_window:
                cons.append(f"the break must start between {C.hhmm(brk_window[0])} and {C.hhmm(brk_window[1])}")
            code = f'''
import re
START, END = {start}, {end}
MINS = {mins!r}
CAP = {cap!r}
BEFORE = {before!r}
BRKW = {brk_window!r}


def _t(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def extra(text):
    fails = []
    rows = []
    for ln in text.splitlines():
        if not ln.strip():
            continue
        m = re.match(r"^\\s*[-*]?\\s*(\\d\\d:\\d\\d)\\s*[-\\u2013]\\s*(\\d\\d:\\d\\d)\\s+(.+?)\\s*$", ln)
        if not m:
            fails.append("line not in the form HH:MM-HH:MM Topic: " + ln[:50])
            continue
        rows.append((_t(m.group(1)), _t(m.group(2)), m.group(3)))
    if not rows:
        return fails
    if rows[0][0] != START:
        fails.append("first item must start at the meeting start")
    if rows[-1][1] != END:
        fails.append("last item must end at the meeting end")
    for a, b in zip(rows, rows[1:]):
        if a[1] != b[0]:
            fails.append("gap or overlap between " + a[2] + " and " + b[2])
    for s, e, name in rows:
        if e <= s or (e - s) % 5:
            fails.append("duration not a positive multiple of 5: " + name)
    names = [r[2].lower() for r in rows]
    if names[0] != "welcome" or rows[0][1] - rows[0][0] != 5:
        fails.append("first item must be a 5-minute Welcome")
    if names[-1] not in ("wrap-up", "wrap up", "wrapup") or rows[-1][1] - rows[-1][0] != 5:
        fails.append("last item must be a 5-minute Wrap-up")
    brk = [r for r in rows if r[2].lower() == "break"]
    if len(brk) != 1 or brk[0][1] - brk[0][0] != 10 or brk is rows[0] or brk[0] is rows[0] or brk[0] is rows[-1]:
        fails.append("need exactly one 10-minute Break that is neither first nor last")
    for t, mn in MINS.items():
        hit = [r for r in rows if r[2].lower() == t.lower()]
        if len(hit) != 1:
            fails.append("topic missing or repeated: " + t)
        else:
            du = hit[0][1] - hit[0][0]
            if du < mn:
                fails.append(t + " is shorter than its minimum")
            if CAP and du > CAP:
                fails.append(t + " is longer than the cap")
    others = [r for r in rows if r[2].lower() not in [x.lower() for x in MINS] + ["welcome", "break", "wrap-up", "wrap up", "wrapup"]]
    if others:
        fails.append("unexpected item: " + others[0][2])
    if BEFORE:
        a = [r for r in rows if r[2].lower() == BEFORE[0].lower()]
        b = [r for r in rows if r[2].lower() == BEFORE[1].lower()]
        if a and b and a[0][0] > b[0][0]:
            fails.append(BEFORE[0] + " must come before " + BEFORE[1])
    if BRKW and brk and not (BRKW[0] <= brk[0][0] <= BRKW[1]):
        fails.append("the break is outside its allowed window")
    return fails
'''
            rules = [{"t": "lines", "min": k + 3}]
            # run the extra on the gold directly
            ns = {}
            exec(code, ns)
            f_ = ns["extra"](gold)
            assert not f_, (f_, gold)
            assert ns["extra"]("09:00-10:00 Everything") != []
            tl = "\n".join(f"- {t}: at least {m} minutes" for t, m in mins.items())
            intro = rng.choice(["I'm chairing a meeting and need the agenda to fit the room booking exactly.", "Can you build a timed agenda for our {k}-topic meeting? The room is booked for a fixed slot.".format(k=k),
                                "agenda help please, the slot is fixed and my boss hates overruns"])
            spec = (f"The topics and their minimum times:\n{tl}\n\nRules: " + "; ".join(cons) + ". Write one line per item in the form `HH:MM-HH:MM Name` (24-hour clock, name exactly as above), in order, and nothing else.")
            prompt = C.chat(rng, intro, rng.choice(SAVE), None, C.register_for(rng), spec=spec)
            yield Task(slug=f"{i + 1:02d}-{k}topics-d{d}", prompt=prompt, difficulty=d, start=_start_notes(rng), hidden=K.check_files(rules, code), solution={"reply.md": gold}, verify=K.VERIFY, kind="greenfield",
                       tags=["writing", "planning", "arithmetic"], notes={"topics": k, "total": total})
            break
        else:
            raise RuntimeError("agenda: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-write-table

ITEMS_T = ["oat milk", "sourdough", "free-range eggs", "pear cider", "lentil soup", "walnut loaf", "kombucha", "granola"]
STORES = ["Eastside", "Harbour", "Old Town", "Riverside", "Northgate"]
PEOPLE_T = C.FIRST[:20]


@family("chat-write-table", category="chat", lang="text", kind="greenfield", n=12, summary="turn pasted raw lines into a markdown table with computed columns, a sort order and a total row; every cell is recomputed by the checker")
def gen_table_write(rng, n):
    plan = [2, 2, 3, 3, 3, 4, 4, 4, 2, 3, 4, 3]
    for i in range(n):
        d = plan[i % len(plan)]
        kind = ["sales", "hours", "scores"][i % 3]
        if kind == "sales":
            nrows = {2: 8, 3: 12, 4: 18}[d]
            stores = rng.sample(STORES, rng.randint(3, 4))
            lines = []
            agg = {s: [0, 0] for s in stores}
            for _ in range(nrows):
                s = rng.choice(stores)
                it = rng.choice(ITEMS_T)
                u = rng.randint(1, 20)
                pc = rng.choice([180, 250, 399, 450, 625, 810])
                lines.append(f"{s}, {it}, {u}, {C.money(pc)}")
                agg[s][0] += u
                agg[s][1] += u * pc
            hdr = ["Store", "Units", "Revenue"]
            rows = sorted(((s, a[0], a[1]) for s, a in agg.items() if a[0] > 0), key=lambda r: (-r[2], r[0]))
            if len({r[2] for r in rows}) != len(rows):
                continue
            exp = [[s, str(u), C.money(r)] for s, u, r in rows]
            tot = ["Total", str(sum(r[1] for r in rows)), C.money(sum(r[2] for r in rows))]
            raw = "store, item, units, unit_price\n" + "\n".join(lines)
            intro = "These are a day's till lines from our shops. I need a summary table for the manager."
            spec = ("Make a markdown table with exactly these columns in this order: Store | Units | Revenue. One row per store, sorted by Revenue from highest to lowest. Revenue is units times unit price, summed per store, written with two decimals and no currency symbol. "
                    "Finish with a row whose first cell is Total, with the sums of Units and Revenue.")
        elif kind == "hours":
            nrows = {2: 8, 3: 12, 4: 18}[d]
            people = rng.sample(PEOPLE_T, rng.randint(3, 4))
            lines = []
            agg = {p: 0 for p in people}
            for _ in range(nrows):
                p = rng.choice(people)
                h = rng.choice([4, 6, 7.5, 8, 9, 10, 12.5])
                lines.append(f"{p}: {h:g}h")
                agg[p] += h
            hdr = ["Person", "Hours", "Overtime"]
            thr = rng.choice([24, 30, 35]) if d >= 3 else 0
            rows = sorted(((p, agg[p]) for p in people if agg[p] > 0), key=lambda r: (-r[1], r[0]))
            if len({r[1] for r in rows}) != len(rows):
                continue
            exp = []
            for p, h in rows:
                ot = max(0, h - thr) if thr else 0
                exp.append([p, f"{h:.1f}", f"{ot:.1f}"])
            tot = ["Total", f"{sum(r[1] for r in rows):.1f}", f"{sum(max(0, h - thr) if thr else 0 for _, h in rows):.1f}"]
            raw = "\n".join(lines)
            intro = "Here is a fortnight of hour entries from the volunteer rota (one line per shift)."
            ot_txt = f"Overtime is the hours above {thr} (or 0.0 if none)" if thr else "Overtime is always 0.0 for now"
            spec = (f"Make a markdown table with the columns Person | Hours | Overtime. One row per person, sorted by Hours from most to fewest. Hours is the sum of that person's shifts; {ot_txt}. "
                    "Write every number with exactly one decimal place. Finish with a Total row (Total in the first cell).")
        else:
            nrows = {2: 8, 3: 12, 4: 18}[d]
            names = rng.sample(PEOPLE_T, nrows)
            scores = [rng.randint(35, 99) for _ in names]
            bands = [("A", 85, 100), ("B", 70, 84), ("C", 55, 69), ("D", 0, 54)]
            lines = [f"{nm}: {sc}" for nm, sc in zip(names, scores)]
            hdr = ["Grade", "Count", "Average"]
            exp = []
            for g, lo, hi in bands:
                sel = [s_ for s_ in scores if lo <= s_ <= hi]
                if sel:
                    avg = Fraction(sum(sel), len(sel))
                    exp.append([g, str(len(sel)), f"{float(avg):.1f}"])
            if any(((Fraction(sum(s_ for s_ in scores if lo <= s_ <= hi), max(1, len([s_ for s_ in scores if lo <= s_ <= hi]))) * 10) % 1) == Fraction(1, 2) for _, lo, hi in bands):
                continue
            tot = ["Total", str(len(scores)), f"{float(Fraction(sum(scores), len(scores))):.1f}"]
            raw = "\n".join(lines)
            intro = "Exam marks for a small class, one name per line."
            spec = ("Make a markdown table with the columns Grade | Count | Average. Bands: A is 85 to 100, B is 70 to 84, C is 55 to 69, D is 0 to 54. One row per band that has at least one student, in order A to D. "
                    "Average is the mean mark in that band to one decimal place. Finish with a Total row whose first cell is Total, with the overall count and overall mean mark (one decimal).")
        all_rows = exp + [tot]
        gold = "| " + " | ".join(hdr) + " |\n|" + "|".join("---" for _ in hdr) + "|\n" + "\n".join("| " + " | ".join(r) + " |" for r in all_rows) + "\n"
        code = f'''
import re
HDR = {hdr!r}
ROWS = {all_rows!r}


def extra(text):
    fails = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 3:
        return ["not a markdown table"]
    def cells(ln):
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        return [re.sub(r"[*_`]", "", x) for x in c]
    head = cells(lines[0])
    if [h.lower() for h in head] != [h.lower() for h in HDR]:
        fails.append("header should be " + " | ".join(HDR))
    if not re.match(r"^\\|?\\s*:?-+", lines[1].replace(" ", "")):
        fails.append("second line must be the separator row")
    body = [cells(ln) for ln in lines[2:]]
    if len(body) != len(ROWS):
        fails.append(f"expected {{len(ROWS)}} rows (including Total), found {{len(body)}}")
    for got, want in zip(body, ROWS):
        if [g.lower() for g in got] != [w.lower() for w in want]:
            fails.append("row should be " + " | ".join(want) + " but is " + " | ".join(got))
            break
    return fails
'''
        ns = {}
        exec(code, ns)
        assert not ns["extra"](gold), ns["extra"](gold)
        rules = [{"t": "lines", "min": 4}]
        prompt = C.chat(rng, intro, rng.choice(SAVE), C.block(raw), C.register_for(rng), spec=spec)
        yield Task(slug=f"{i + 1:02d}-{kind}-d{d}", prompt=prompt, difficulty=d, start=_start_notes(rng), hidden=K.check_files(rules, code), solution={"reply.md": gold}, verify=K.VERIFY, kind="greenfield",
                   tags=["writing", "tables", "arithmetic"], notes={"kind": kind})


# --------------------------------------------------------------------------------------------------------------------
# chat-write-json


@family("chat-write-json", category="chat", lang="text", kind="greenfield", n=10, summary="extract structured data from a messy typed note into result.json with exact normalisation rules (ISO dates, cents, digits-only phones, sorted lists)")
def gen_json_write(rng, n):
    plan = [3, 3, 4, 4, 4, 5, 5, 3, 4, 5]
    sup = ["Brightline Print", "Northwind Pallets", "Copperfield Packaging", "Tidewater Labels", "Ashgrove Paper"]
    contacts = ["Ines Marchetti", "Tobias Lindqvist", "Amara Okafor", "Pavel Nowak", "Salma Haddad"]
    items = ["A4 flyers", "roll labels", "cardboard sleeves", "box dividers", "gift tags", "tote bags"]
    for i in range(n):
        d = plan[i % len(plan)]
        nrec = 1 if d < 5 else 3
        recs, notes = [], []
        for _ in range(nrec):
            s = rng.choice(sup)
            c = rng.choice(contacts)
            ph = f"07{rng.randint(100, 999)}{rng.randint(100000, 999999)}"
            dt = date(2026, rng.randint(1, 12), rng.randint(1, 28))
            amt = rng.randrange(25000, 480000, 50)
            its = sorted(rng.sample(items, rng.randint(2, 3)))
            qty = {it: rng.choice([50, 100, 250, 500, 1000]) for it in its}
            rush = rng.random() < 0.5
            phs = rng.choice([f"{ph[:5]} {ph[5:8]} {ph[8:]}", f"({ph[:5]}) {ph[5:]}", f"{ph[:4]}-{ph[4:7]}-{ph[7:]}"])
            ds = rng.choice([f"{dt.day}/{dt.month}/{dt.year}", f"{dt.day} {C.MONTHS[dt.month - 1][:3]} {dt.year}"])
            ams = rng.choice([f"{C.money_c(amt, chr(163))}", f"{amt // 100:,} pounds {amt % 100:02d}p".replace(" 00p", ""), f"GBP {C.money(amt)}"])
            order = [f"{qty[it]} x {it}" for it in rng.sample(its, len(its))]
            note = (f"Spoke to {c} at {s} ({phs}) on {ds}. Quote for the lot: {ams}. They need " + ", ".join(order[:-1]) + (" and " if len(order) > 1 else "") + order[-1] + ("." if not rush else ". It's a rush job, needed within the week.")
                    + rng.choice(["", " Wants a call back.", " Said the quote is valid for a month."]))
            notes.append(note)
            rec = {"supplier": s, "contact": c, "phone": ph, "date": dt.isoformat(), "total_pence": amt, "items": [{"name": it, "qty": qty[it]} for it in its], "rush": rush}
            if d == 3:
                rec = {k_: rec[k_] for k_ in ("supplier", "contact", "date", "total_pence")}
            recs.append(rec)
        if nrec > 1:
            recs.sort(key=lambda r: r["date"])
            order_idx = sorted(range(len(notes)), key=lambda j: notes[j])  # notes stay in given (unsorted) order
        expect = recs if nrec > 1 else recs[0]
        gold = json.dumps(expect, indent=2) + "\n"
        keys = list(recs[0].keys())
        spec_keys = {"supplier": "supplier (string, as written)", "contact": "contact (full name)", "phone": "phone (digits only, as a string)", "date": "date (YYYY-MM-DD; numeric dates in the note are day/month/year)",
                     "total_pence": "total_pence (integer number of pence)", "items": "items (list of objects with name and qty, sorted alphabetically by name; qty an integer)", "rush": "rush (true/false: true only if the note says it is a rush job)"}
        spec = ("The JSON must have " + ("an object" if nrec == 1 else f"a list of {nrec} objects (one per note, sorted by date ascending)") + " with exactly these keys: " + "; ".join(spec_keys[k_] for k_ in keys) + ". Valid JSON only, nothing else in the file.")
        code = f'''
import json
EXPECT = json.loads({json.dumps(json.dumps(expect))})


def extra(text):
    try:
        got = json.loads(text)
    except Exception as e:
        return ["not valid JSON: " + str(e)]
    if got != EXPECT:
        if isinstance(EXPECT, list) and isinstance(got, list) and len(got) == len(EXPECT):
            for a, b in zip(got, EXPECT):
                if a != b:
                    return ["a record differs: " + json.dumps(a)[:120] + " (expected keys/values per the notes)"]
        return ["JSON does not match what the note(s) say"]
    return []
'''
        ns = {}
        exec(code, ns)
        assert not ns["extra"](gold)
        intro = rng.choice(["I typed these call notes into notes.txt while on the phone and now need them as data for our ordering tool.", "Can you turn the note(s) in notes.txt into JSON? The import script is picky.",
                            "my call notes are in notes.txt, messy as always. the tool wants clean JSON"])
        files = {"notes.txt": "\n\n".join(notes) + "\n"}
        rules = [{"t": "min_chars", "n": 20}]
        prompt = C.chat(rng, intro + " Write the result to result.json (not reply.md).", "", None, C.register_for(rng), spec=spec)
        yield Task(slug=f"{i + 1:02d}-{nrec}rec-d{d}", prompt=prompt, difficulty=d, start=files, hidden=K.check_files(rules, code, target="result.json"), solution={"result.json": gold}, verify=K.VERIFY, kind="greenfield",
                   tags=["writing", "json", "extraction"], notes={"records": nrec})


# --------------------------------------------------------------------------------------------------------------------
# chat-write-redact


@family("chat-write-redact", category="chat", lang="text", kind="greenfield", n=10, summary="redact personal data from a support transcript with exact placeholder rules; everything else must stay character for character")
def gen_redact(rng, n):
    plan = [2, 2, 3, 3, 3, 4, 4, 4, 5, 3]
    for i in range(n):
        d = plan[i % len(plan)]
        k = {2: 6, 3: 8, 4: 10, 5: 12}[d]
        people = C.full_names(rng, 3)
        email = lambda nm: f"{nm.split()[0].lower()}.{nm.split()[1].lower()}@{rng.choice(['mail', 'post', 'inbox'])}.example"  # noqa: E731
        phone = lambda: f"0{rng.randint(1000, 9999)} {rng.randint(100000, 999999)}"  # noqa: E731
        acct = lambda: f"AC-{rng.randint(100000, 999999)}"  # noqa: E731
        pcode = lambda: f"{rng.choice(['LS', 'M', 'BS', 'EH'])}{rng.randint(1, 20)} {rng.randint(1, 9)}{rng.choice('ABDEFGHJLNPQRSTUWXYZ')}{rng.choice('ABDEFGHJLNPQRSTUWXYZ')}"  # noqa: E731
        cust, agent, third = people
        c_email, c_phone, c_acct, c_pc = email(cust), phone(), acct(), pcode()
        a_email = email(agent)
        src_lines = [
            f"Agent: Hello, you are through to support, my name is {agent.split()[0]}.",
            f"Customer: Hi, this is {cust}. I can't log in to my account {c_acct}.",
            f"Agent: Thanks {cust.split()[0]}. Can you confirm the email address on the account?",
            f"Customer: It's {c_email}, and you can ring me on {c_phone} if easier.",
            f"Agent: I have reset the password and sent a link. If it doesn't arrive, write to {a_email} directly.",
            f"Customer: Great. My sister {third} also uses it, she lives at {c_pc}.",
            "Agent: Noted. Is there anything else I can help with today?",
            "Customer: No, that's all, thanks for the quick help.",
            f"Agent: You're welcome. Have a good day, {cust.split()[0]}.",
            f"Customer: Bye. (Please note the invoice was sent to {c_pc} by mistake.)",
            f"Agent: I have updated that, the address on {c_acct} now matches.",
            "Customer: Perfect, goodbye.",
        ][:k]
        src = "\n".join(src_lines)
        repl_order = []
        rules_txt = ["every email address becomes [EMAIL]", "every phone number becomes [PHONE]", "every account number (AC- followed by six digits) becomes [ACCT]", f"every full name from this list becomes [NAME]: {', '.join(people)}"]
        use_pc = d >= 4
        if use_pc:
            rules_txt.append("every postcode (like LS6 2AB) becomes [POSTCODE]")
        out = src
        for nm in people:
            out = out.replace(nm, "[NAME]")
        out = out.replace(c_email, "[EMAIL]").replace(a_email, "[EMAIL]").replace(c_phone, "[PHONE]").replace(c_acct, "[ACCT]")
        if use_pc:
            out = out.replace(c_pc, "[POSTCODE]")
        if not use_pc and c_pc in src:
            pass
        # first names (e.g. 'Thanks Ines.') are NOT redacted: they are not full names; say so
        norm = " ".join(out.split())
        code = f'''
EXPECT = {norm!r}


def extra(text):
    got = " ".join(text.split())
    if got == EXPECT:
        return []
    # find the first differing word for a readable message
    a, b = got.split(" "), EXPECT.split(" ")
    for j, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return [f"first difference at word {{j + 1}}: got {{x!r}}, expected {{y!r}}"]
    return [f"length differs: got {{len(a)}} words, expected {{len(b)}}"]
'''
        ns = {}
        exec(code, ns)
        assert not ns["extra"](out)
        assert ns["extra"](src)
        intro = rng.choice(["I have to share this support chat with a contractor, so the personal details must go first.", "Please redact the transcript in transcript.txt before it goes into our training deck.",
                            "GDPR clean-up: the chat in transcript.txt needs the personal data removed before I can circulate it."])
        spec = ("Rules: " + "; ".join(rules_txt) + ". First names on their own (for example 'Thanks Ines') are left alone. Change nothing else: same wording, same punctuation, same line breaks. The file should contain only the redacted transcript.")
        prompt = C.chat(rng, intro, rng.choice(SAVE), None, C.register_for(rng), spec=spec)
        rules = [{"t": "min_chars", "n": 20}]
        yield Task(slug=f"{i + 1:02d}-{k}lines-d{d}", prompt=prompt, difficulty=d, start={"transcript.txt": src + "\n", "notes.txt": "n/a\n"}, hidden=K.check_files(rules, code), solution={"reply.md": out + "\n"}, verify=K.VERIFY, kind="greenfield",
                   tags=["writing", "redaction", "privacy"], notes={"lines": k})


# --------------------------------------------------------------------------------------------------------------------
# chat-write-actions


def _next_wd(m: date, wd: int) -> date:
    x = m + timedelta(days=1)
    while x.weekday() != wd:
        x += timedelta(days=1)
    return x


@family("chat-write-actions", category="chat", lang="text", kind="greenfield", n=10, summary="turn a meeting transcript into action items with owners and absolute due dates; decoy statements are not actions and relative dates must be resolved by stated rules")
def gen_actions(rng, n):
    plan = [3, 3, 4, 4, 4, 5, 5, 3, 4, 5]
    people = C.pick_names(rng, 5)
    for i in range(n):
        d = plan[i % len(plan)]
        people = C.pick_names(rng, 4)
        m = date(2026, rng.randint(1, 10), rng.randint(3, 22))
        tasks = [("send the invoice to the council", "invoice"), ("book the venue for the awards", "venue"), ("update the volunteer roster", "roster"), ("order the new banners", "banners"),
                 ("draft the press release", "press"), ("confirm the caterer", "caterer"), ("renew the insurance", "insurance")]
        chosen = rng.sample(tasks, {3: 3, 4: 4, 5: 5}[d])
        exp, lines = [], []
        for j, (txt, kw) in enumerate(chosen):
            who = people[j % len(people)]
            kind = rng.choice(["wd", "inN", "eom"]) if d >= 4 else rng.choice(["wd", "inN"])
            if kind == "wd":
                wdn = rng.randint(0, 4)
                due = _next_wd(m, wdn)
                phrase = f"by {C.WEEKDAYS[wdn]}"
            elif kind == "inN":
                nn = rng.choice([3, 5, 10, 14])
                due = m + timedelta(days=nn)
                phrase = f"in {nn} days"
            else:
                nxt = date(m.year + (m.month // 12), m.month % 12 + 1, 1)
                due = nxt - timedelta(days=1)
                phrase = "by the end of the month"
            lines.append(f"{who}: I'll {txt} {phrase}.")
            exp.append((who, kw, due))
        decoys = [f"{rng.choice(people)}: Last week I already sorted out the printer contract.", f"{rng.choice(people)}: We could maybe look at a new logo at some point, no promises.",
                  f"{rng.choice(people)}: The weather was terrible at the last fair, wasn't it?", f"{rng.choice(people)}: Somebody should really tidy the shared drive."]
        lines += rng.sample(decoys, 2 if d < 5 else 4)
        rng.shuffle(lines)
        gold = "\n".join(f"- [ ] {w}: {t} (due {C.iso(du)})" for (t, kw), (w, kw2, du) in zip(chosen, exp)) + "\n"
        code = f'''
import re
EXP = {[(w, kw, C.iso(du)) for w, kw, du in exp]!r}


def extra(text):
    fails = []
    items = [ln for ln in text.splitlines() if re.match(r"^\\s*-\\s*\\[[ xX]\\]\\s+", ln)]
    if len(items) != len(EXP):
        fails.append(f"expected exactly {{len(EXP)}} action items, found {{len(items)}}")
    for w, kw, due in EXP:
        ok = [ln for ln in items if re.match(r"^\\s*-\\s*\\[[ xX]\\]\\s+" + w + r":", ln) and kw.lower() in ln.lower() and re.search(r"\\(due " + due + r"\\)\\s*$", ln.strip())]
        if not ok:
            fails.append(f"no correct action item for {{w}} about '{{kw}}' due {{due}}")
    return fails
'''
        ns = {}
        exec(code, ns)
        assert not ns["extra"](gold), ns["extra"](gold)
        intro = rng.choice(["Here's the transcript of today's committee meeting (it took place on " + f"{m.day} {C.MONTHS[m.month - 1]} {m.year}" + "). I need the action items out of it.",
                            f"Meeting notes attached as transcript.txt, meeting date {m.day} {C.MONTHS[m.month - 1]} {m.year}. Can you pull out who has to do what by when?"])
        spec = ("Only real commitments count as actions: something a named person says they will do. Past events, vague ideas and general remarks are not actions. Date rules: 'by <weekday>' means the first such weekday strictly after the meeting date; "
                "'in N days' counts from the meeting date; 'by the end of the month' means the last day of the meeting's month. Write one line per action in exactly this form: `- [ ] Owner: task (due YYYY-MM-DD)`, where Owner is the speaker's name and the task keeps the key noun from what they said.")
        rules = [{"t": "min_chars", "n": 20}]
        prompt = C.chat(rng, intro, rng.choice(SAVE), None, C.register_for(rng), spec=spec)
        yield Task(slug=f"{i + 1:02d}-{len(exp)}actions-d{d}", prompt=prompt, difficulty=d, start={"transcript.txt": "\n".join(lines) + "\n"}, hidden=K.check_files(rules, code), solution={"reply.md": gold}, verify=K.VERIFY, kind="greenfield",
                   tags=["writing", "action-items", "dates"], notes={"actions": len(exp)})


# --------------------------------------------------------------------------------------------------------------------
# chat-write-packlist

FOOD = [("oat bars", 60, 240, 150, "carb"), ("trail mix", 100, 520, 280, "carb"), ("dried mango", 80, 250, 310, "fruit"), ("jerky", 50, 130, 420, "protein"), ("peanut butter pouch", 45, 270, 190, "protein"),
        ("instant noodles", 85, 380, 120, "carb"), ("cheese wedge", 70, 280, 260, "protein"), ("energy gel", 40, 100, 220, "carb"), ("dark chocolate", 100, 540, 240, "treat"), ("couscous pot", 90, 330, 170, "carb"),
        ("tuna pouch", 80, 120, 230, "protein"), ("apple chips", 30, 110, 200, "fruit")]


@family("chat-write-packlist", category="chat", lang="text", kind="greenfield", n=10, summary="choose items with quantities from a table so that weight, calories, cost, category and repeat limits all hold; the checker recomputes the totals")
def gen_pack(rng, n):
    plan = [3, 3, 4, 4, 4, 5, 5, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            k = {3: 6, 4: 8, 5: 10}[d]
            menu = rng.sample(FOOD, k)
            maxq = 2
            # find a random feasible combination and derive limits with small slack
            best = None
            for _ in range(200):
                q = [rng.randint(0, maxq) for _ in menu]
                if sum(q) < 4:
                    continue
                w = sum(qq * it[1] for qq, it in zip(q, menu))
                cal = sum(qq * it[2] for qq, it in zip(q, menu))
                cost = sum(qq * it[3] for qq, it in zip(q, menu))
                if cal / max(w, 1) < 3.0:
                    continue
                best = (q, w, cal, cost)
                break
            if best is None:
                continue
            q, w, cal, cost = best
            slack = {3: 120, 4: 60, 5: 25}[d]
            W = w + slack
            Cmin = cal - slack * 2
            B = cost + slack * 3
            need_prot = d >= 4 and any(menu[j][4] == "protein" and q[j] > 0 for j in range(k))
            items_txt = C.table([[it[0], it[1], it[2], C.money(it[3]), it[4]] for it in menu], ["item", "weight_g", "kcal", "price", "type"])
            gold = "\n".join(f"{it[0]} x {qq}" for it, qq in zip(menu, q) if qq > 0) + "\n"
            cons = [f"total weight at most {W} g", f"total energy at least {Cmin} kcal", f"total price at most {C.money_c(B)}", f"no more than {maxq} of any one item"]
            if need_prot:
                cons.append("at least one item of type protein")
            if d == 5:
                cons.append("at least 5 items in total (counting repeats)")
                if sum(q) < 5:
                    continue
            code = f'''
import re
MENU = {[(it[0], it[1], it[2], it[3], it[4]) for it in menu]!r}
W, CMIN, B, MAXQ = {W}, {Cmin}, {B}, {maxq}
NEED_PROT = {need_prot}
MIN_ITEMS = {5 if d == 5 else 0}


def extra(text):
    fails = []
    got = {{}}
    for ln in text.splitlines():
        if not ln.strip():
            continue
        m = re.match(r"^\\s*[-*]?\\s*(.+?)\\s*[x\\u00d7]\\s*(\\d+)\\s*$", ln)
        if not m:
            fails.append("line not in the form 'item x N': " + ln[:50])
            continue
        nm, q = m.group(1).strip().lower(), int(m.group(2))
        names = {{it[0]: it for it in MENU}}
        if nm not in names:
            fails.append("unknown item: " + nm)
            continue
        got[nm] = got.get(nm, 0) + q
    w = sum(q * [it for it in MENU if it[0] == nm][0][1] for nm, q in got.items() if any(it[0] == nm for it in MENU))
    cal = sum(q * [it for it in MENU if it[0] == nm][0][2] for nm, q in got.items() if any(it[0] == nm for it in MENU))
    cost = sum(q * [it for it in MENU if it[0] == nm][0][3] for nm, q in got.items() if any(it[0] == nm for it in MENU))
    if w > W:
        fails.append(f"weight {{w}} g exceeds {{W}} g")
    if cal < CMIN:
        fails.append(f"energy {{cal}} kcal is below {{CMIN}} kcal")
    if cost > B:
        fails.append(f"price {{cost}} exceeds {{B}}")
    if any(q > MAXQ or q < 1 for q in got.values()):
        fails.append("quantities must be between 1 and " + str(MAXQ))
    if NEED_PROT and not any([it for it in MENU if it[0] == nm][0][4] == "protein" for nm in got if any(it[0] == nm for it in MENU)):
        fails.append("no protein item")
    if sum(got.values()) < MIN_ITEMS:
        fails.append("too few items")
    return fails
'''
            ns = {}
            exec(code, ns)
            assert not ns["extra"](gold), (ns["extra"](gold), gold)
            assert ns["extra"]("oat bars x 9") != []
            intro = rng.choice(["I'm packing food for a three-day hike and need to pick from what the shop has. Weight, calories and budget are all tight.", "Help me choose a food bag from this list for the weekend trek.",
                                "planning snacks for an overnight camp, here is what's on offer (table below)"])
            spec = "Constraints: " + "; ".join(cons) + ". Write one line per item you choose in the form `item name x N` (name exactly as in the table, N a whole number of at least 1), nothing else."
            rules = [{"t": "min_chars", "n": 5}]
            prompt = C.chat(rng, intro, rng.choice(SAVE), C.block(items_txt), C.register_for(rng), spec=spec)
            yield Task(slug=f"{i + 1:02d}-{k}items-d{d}", prompt=prompt, difficulty=d, start=_start_notes(rng), hidden=K.check_files(rules, code), solution={"reply.md": gold}, verify=K.VERIFY, kind="greenfield",
                       tags=["writing", "planning", "constraints"], notes={"items": k})
            break
        else:
            raise RuntimeError("pack: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-write-itinerary

SITES = ["Fort Museum", "Glasshouse Gardens", "Old Mill", "Lighthouse", "Clock Tower", "Market Hall", "Abbey Ruins", "Observatory"]


@family("chat-write-itinerary", category="chat", lang="text", kind="greenfield", n=8, summary="schedule visits to sites with opening windows, fixed visit lengths, travel times and a lunch slot; the checker validates every constraint")
def gen_itin(rng, n):
    plan = [4, 4, 5, 5, 4, 5, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(300):
            k = 4 if d == 4 else 5
            sites = rng.sample(SITES, k)
            dur = {s: rng.choice([45, 60, 75, 90]) for s in sites}
            win = {}
            for s in sites:
                o = rng.choice([9, 10, 11, 13]) * 60 + rng.choice([0, 30])
                c = o + rng.choice([5, 6, 7]) * 60
                win[s] = (o, min(c, 18 * 60))
            nodes = ["Hotel"] + sites
            trav = {}
            for a, b in itertools.combinations(nodes, 2):
                t = rng.choice([10, 15, 20, 25, 30])
                trav[(a, b)] = trav[(b, a)] = t
            start = 9 * 60
            end_by = 17 * 60 + 30
            lunch_len = 45
            lw = (12 * 60, 14 * 60)
            sol = None
            for perm in itertools.permutations(sites):
                for lunch_after in range(len(perm)):
                    cur, pos = start, "Hotel"
                    sched, ok = [], True
                    for j, s_ in enumerate(perm):
                        cur += trav[(pos, s_)]
                        cur = max(cur, win[s_][0])
                        if cur + dur[s_] > win[s_][1]:
                            ok = False
                            break
                        sched.append((s_, cur, cur + dur[s_]))
                        cur += dur[s_]
                        pos = s_
                        if j == lunch_after:
                            ls = max(cur, lw[0])
                            if ls + lunch_len > lw[1]:
                                ok = False
                                break
                            sched.append(("Lunch", ls, ls + lunch_len))
                            cur = ls + lunch_len
                    if ok and cur <= end_by:
                        sol = sched
                        break
                if sol:
                    break
            if sol is None:
                continue
            gold = "\n".join(f"{C.hhmm(a)}-{C.hhmm(b)} {nm}" for nm, a, b in sol) + "\n"
            tr_lines = "\n".join(f"{a} to {b}: {trav[(a, b)]} min" for a, b in itertools.combinations(nodes, 2))
            site_lines = "\n".join(f"{s}: open {C.hhmm(win[s][0])}-{C.hhmm(win[s][1])}, visit takes {dur[s]} min" for s in sites)
            code = f'''
import re
SITES = {sites!r}
DUR = {dur!r}
WIN = {win!r}
TRAV = {{(a, b): t for (a, b), t in {trav!r}.items()}}
START, END_BY, LUNCH = {start}, {end_by}, {lunch_len}
LW = {lw!r}


def _t(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def extra(text):
    fails = []
    rows = []
    for ln in text.splitlines():
        if not ln.strip():
            continue
        m = re.match(r"^\\s*[-*]?\\s*(\\d\\d:\\d\\d)\\s*[-\\u2013]\\s*(\\d\\d:\\d\\d)\\s+(.+?)\\s*$", ln)
        if not m:
            fails.append("line not in the form HH:MM-HH:MM Name: " + ln[:50])
            continue
        rows.append((_t(m.group(1)), _t(m.group(2)), m.group(3)))
    if fails or not rows:
        return fails or ["empty"]
    names = [r[2] for r in rows]
    if sorted(n_ for n_ in names if n_ != "Lunch") != sorted(SITES) or names.count("Lunch") != 1:
        return ["the schedule must contain every site exactly once plus one Lunch line"]
    pos, cur = "Hotel", START
    for s, e, nm in rows:
        if nm == "Lunch":
            if e - s != LUNCH:
                fails.append("lunch must be exactly " + str(LUNCH) + " minutes")
            if s < LW[0] or e > LW[1]:
                fails.append("lunch must lie within the lunch window")
            if s < cur:
                fails.append("lunch starts before the previous visit ends")
            cur = e
            continue
        if s < cur + TRAV[(pos, nm)]:
            fails.append("not enough travel time before " + nm)
        if e - s != DUR[nm]:
            fails.append("wrong visit length for " + nm)
        if s < WIN[nm][0] or e > WIN[nm][1]:
            fails.append(nm + " is outside its opening hours")
        pos, cur = nm, e
    if cur > END_BY:
        fails.append("the day runs past the end time")
    return fails
'''
            ns = {}
            exec(code, ns)
            f_ = ns["extra"](gold)
            assert not f_, (f_, gold)
            intro = rng.choice(["We're doing a day trip and I want one watertight itinerary. Everything is walking distance, but the times add up.", "can you plan our day of sightseeing? opening hours and travel times are below"])
            spec = (f"We start from the Hotel at {C.hhmm(start)}. Sites:\n{site_lines}\n\nTravel times (same both ways):\n{tr_lines}\n\nRules: visit every site once; arrive no earlier than opening and finish no later than closing (waiting for a site to open is fine); "
                    f"leave a gap of at least the travel time between leaving one place and starting the next (the first trip starts at the Hotel at {C.hhmm(start)} or later); take one {lunch_len}-minute Lunch that lies completely within {C.hhmm(lw[0])}-{C.hhmm(lw[1])} "
                    f"and happens where you are, with no travel; everything must be finished by {C.hhmm(end_by)}. Write one line per item as `HH:MM-HH:MM Name` (Lunch for lunch), in order, and nothing else.")
            rules = [{"t": "lines", "min": k + 1}]
            prompt = C.chat(rng, intro, rng.choice(SAVE), None, C.register_for(rng), spec=spec)
            yield Task(slug=f"{i + 1:02d}-{k}sites-d{d}", prompt=prompt, difficulty=d, start=_start_notes(rng), hidden=K.check_files(rules, code), solution={"reply.md": gold}, verify=K.VERIFY, kind="greenfield",
                       tags=["writing", "planning", "scheduling"], notes={"sites": k})
            break
        else:
            raise RuntimeError("itin: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-write-release-notes


@family("chat-write-release-notes", category="chat", lang="text", kind="greenfield", n=10, summary="group a commit log into release notes: sections by type, internal types excluded, issue numbers kept, fixed title line")
def gen_notes(rng, n):
    plan = [3, 3, 3, 4, 4, 4, 3, 4, 4, 3]
    msgs = {"feat": ["add CSV export to reports", "support dark mode in the editor", "allow bulk delete of drafts", "add weekly digest emails", "let admins pin announcements"],
            "fix": ["stop duplicate invoices on retry", "handle empty search terms", "correct timezone in reminders", "prevent crash on missing avatar", "fix off-by-one in page counts"],
            "perf": ["cache the product list", "batch database writes in imports", "lazy-load images in the gallery"], "refactor": ["split the billing module", "simplify the settings loader"],
            "chore": ["bump the lint config", "update CI image", "tidy imports"], "docs": ["fix typos in the README", "add API examples"]}
    for i in range(n):
        d = plan[i % len(plan)]
        entries = []
        used = set()
        counts = {"feat": rng.randint(2, 3), "fix": rng.randint(2, 4), "perf": rng.randint(0, 2), "refactor": rng.randint(0, 1), "chore": rng.randint(1, 2), "docs": rng.randint(1, 1)}
        num = rng.randint(100, 900)
        for t, c in counts.items():
            for m in rng.sample(msgs[t], min(c, len(msgs[t]))):
                num += rng.randint(1, 13)
                entries.append((t, rng.choice(["api", "ui", "core", "billing", "docs"]), m, num))
        rng.shuffle(entries)
        ver = f"{rng.randint(1, 4)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}"
        rd = date(2026, rng.randint(1, 12), rng.randint(1, 28))
        sections = [("Added", ["feat"]), ("Fixed", ["fix"]), ("Changed", ["perf", "refactor"])]
        expect, lines = [], [f"## {ver} ({C.iso(rd)})"]
        for title, types in sections:
            es = [e for e in entries if e[0] in types]
            if es:
                lines.append("")
                lines.append(f"### {title}")
                for e in sorted(es, key=lambda e: e[3]):
                    lines.append(f"- {e[2][0].upper() + e[2][1:]} (#{e[3]})")
                expect.append((title, sorted(e[3] for e in es)))
        excluded = sorted(e[3] for e in entries if e[0] in ("chore", "docs"))
        gold = "\n".join(lines) + "\n"
        log = "\n".join(f"{t}({sc}): {m} (#{nm})" for t, sc, m, nm in entries)
        code = f'''
import re
TITLE = {"## " + ver + " (" + C.iso(rd) + ")"!r}
EXPECT = {expect!r}
EXCLUDED = {excluded!r}
ORDER = ["Added", "Fixed", "Changed"]


def extra(text):
    fails = []
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if not lines or lines[0].strip() != TITLE:
        fails.append("first line must be exactly " + TITLE)
    sect, cur = [], None
    for ln in lines[1:]:
        m = re.match(r"^###\\s+(.+?)\\s*$", ln)
        if m:
            cur = [m.group(1), []]
            sect.append(cur)
        elif re.match(r"^\\s*[-*]\\s+", ln) and cur is not None:
            nums = re.findall(r"#(\\d+)", ln)
            if len(nums) != 1:
                fails.append("each bullet needs exactly one #number: " + ln[:50])
            else:
                cur[1].append(int(nums[0]))
        else:
            fails.append("unexpected line: " + ln[:50])
    got = [(a, sorted(b)) for a, b in sect]
    if got != EXPECT:
        fails.append("sections should be " + repr(EXPECT) + " but found " + repr(got))
    allnums = {{n_ for _, b in sect for n_ in b}}
    for x in EXCLUDED:
        if x in allnums or ("#" + str(x)) in text:
            fails.append("internal change #" + str(x) + " must not appear")
    return fails
'''
        ns = {}
        exec(code, ns)
        assert not ns["extra"](gold), (ns["extra"](gold), gold)
        intro = rng.choice(["Release day. Here's the commit log since the last tag (conventional-commit style), and I need user-facing release notes.", "can you turn this git log into release notes? changelog.txt has the log"])
        spec = (f"The notes start with the line `## {ver} ({C.iso(rd)})`. Then sections in this order, each as `### Added` (feat), `### Fixed` (fix) and `### Changed` (perf and refactor); leave out a section that would be empty. "
                "Every entry is a bullet (`- `) with the commit message starting with a capital letter and the issue number kept at the end as (#123). chore and docs commits are internal and must not appear at all. Within a section, order entries by issue number, lowest first.")
        rules = [{"t": "min_chars", "n": 20}]
        prompt = C.chat(rng, intro, rng.choice(SAVE), None, C.register_for(rng), spec=spec)
        yield Task(slug=f"{i + 1:02d}-{len(entries)}commits-d{d}", prompt=prompt, difficulty=d, start={"changelog.txt": log + "\n", "notes.txt": "n/a\n"}, hidden=K.check_files(rules, code), solution={"reply.md": gold}, verify=K.VERIFY, kind="greenfield",
                   tags=["writing", "release-notes", "grouping"], notes={"commits": len(entries)})


# --------------------------------------------------------------------------------------------------------------------
# chat-write-support-reply

PRODUCTS = ["air purifier", "stand mixer", "electric kettle", "robot vacuum", "espresso grinder", "sewing machine"]


def _add_months(d: date, k: int) -> date:
    return C.month_add(d, k)


@family("chat-write-support-reply", category="chat", lang="text", kind="greenfield", n=10, summary="reply to a customer using a policy file: compute the refund deadline, refund amount and warranty end, answer numbered questions, promise nothing the policy does not")
def gen_support(rng, n):
    plan = [3, 3, 4, 4, 4, 5, 5, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            prod = rng.choice(PRODUCTS)
            price = rng.randrange(4999, 29999, 100)
            bought = date(2026, rng.randint(1, 9), rng.randint(2, 27))
            today = bought + timedelta(days=rng.randint(8, 25))
            window = rng.choice([14, 21, 30])
            fee = rng.choice([10, 15, 20])
            warranty = rng.choice([12, 24])
            opened = rng.random() < 0.6
            deadline = bought + timedelta(days=window)
            weekend_rule = d >= 4
            if weekend_rule and deadline.weekday() >= 5:
                deadline += timedelta(days=7 - deadline.weekday())
            refund = price if not opened else C.cents_half_up(Fraction(price) * (100 - fee) / 100)
            wend = _add_months(bought, warranty)
            ship = rng.choice([495, 695, 895])
            tiers = d == 5
            policy = (f"# Returns and warranty policy\n\n- Returns are accepted within {window} days of the purchase date (the purchase date is day 0).\n"
                      + (f"- If the last day of the window falls on a Saturday or Sunday, it is extended to the following Monday.\n" if weekend_rule else "")
                      + f"- Unopened items are refunded in full. Opened items are refunded minus a {fee}% restocking fee.\n- Original delivery charges ({C.money_c(ship)} on this order) are never refunded.\n"
                      + f"- All products carry a {warranty}-month warranty from the purchase date; it ends on the same day-of-month {warranty} months later.\n- We cannot offer free replacements for change-of-mind returns.\n")
            email = (f"Hello, I bought a {prod} on {bought.day} {C.MONTHS[bought.month - 1]} {bought.year} for {C.money_c(price)}. It's {'opened and used once' if opened else 'still in its box'} and I don't want it any more.\n"
                     f"1. Until what date can I return it?\n2. How much will I get back{' if I return it' if True else ''}?\n3. When does the warranty on it run out?\nThanks, {rng.choice(C.FIRST)}")
            qs = 3
            ship_note = f", and the original delivery charge of {C.money_c(ship)} is not refunded" if d >= 4 else ""
            line2 = (f"2. Because it has been opened, a {fee}% restocking fee applies, so the refund is {C.money_c(refund)}{ship_note}." if opened
                     else f"2. Because it is unopened, you will be refunded in full: {C.money_c(refund)}{ship_note}.")
            gold_lines = ["Hello,", "", f"Thank you for getting in touch about your {prod}.", "",
                          f"1. You can return it until {deadline.day} {C.MONTHS[deadline.month - 1]} {deadline.year}.", line2,
                          f"3. The warranty ends on {wend.day} {C.MONTHS[wend.month - 1]} {wend.year}.", "", "Kind regards,", "Support team"]
            gold = "\n".join(gold_lines) + "\n"
            rules = [{"t": "include", "any": [F.date_re(deadline)], "label": "return deadline"}, {"t": "include", "any": [F.money_re(refund)], "label": "refund amount"},
                     {"t": "include", "any": [F.date_re(wend)], "label": "warranty end date"}, {"t": "include", "any": [r"re:(?m)^\s*1[.)]\s"], "label": "numbered answer 1"},
                     {"t": "include", "any": [r"re:(?m)^\s*2[.)]\s"], "label": "numbered answer 2"}, {"t": "include", "any": [r"re:(?m)^\s*3[.)]\s"], "label": "numbered answer 3"},
                     {"t": "exclude", "words": ["free replacement", "free shipping", "guarantee"]}, {"t": "max_words", "n": 120 if d <= 4 else 90}]
            if not opened:
                rules.append({"t": "exclude", "words": ["restocking"]})
            if d >= 4:
                rules.append({"t": "include", "any": [F.money_re(ship)], "label": "states the delivery charge that is not refunded"})
            K.assert_passes(rules, gold, what=f"support {i}")
            intro = rng.choice(["A customer emailed us (email.txt) and our policy is in policy.md. I need a reply that answers all three questions correctly.", "Draft a reply to the customer's email using our policy, please. Both files are in the folder.",
                                "Customer service backlog: can you answer the email in email.txt based on policy.md?"])
            spec = ("Answer the three questions in order, as numbered lines starting `1.`, `2.` and `3.` Give concrete dates and amounts, not formulas. Keep it under " + str(120 if d <= 4 else 90) + " words. "
                    "Stick to what the policy says: do not promise anything it does not offer" + (", and say that the original delivery charge is not refunded." if d >= 4 else "."))
            prompt = C.chat(rng, intro, rng.choice(SAVE), None, C.register_for(rng), spec=spec)
            yield Task(slug=f"{i + 1:02d}-{prod.split()[-1]}-d{d}", prompt=prompt, difficulty=d, start={"policy.md": policy, "email.txt": email + "\n"}, hidden=K.check_files(rules), solution={"reply.md": gold}, verify=K.VERIFY, kind="greenfield",
                       tags=["writing", "customer-support", "policy"], notes={"opened": opened, "window": window})
            break
        else:
            raise RuntimeError("support: no instance")
