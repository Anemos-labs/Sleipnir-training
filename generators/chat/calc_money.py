"""Money questions in a person's voice: shared bills, weekly pay, price traps, savings and loans, currency swaps.
Every answer comes from a solver in this file (exact fractions or integer cents)."""
from __future__ import annotations

from fractions import Fraction

from fx import family

from . import _common as C

# --------------------------------------------------------------------------------------------------------------------
# chat-bill-split

MENUS = {
    "Harbour Grill": [("lentil soup", 825), ("grilled sardines", 1650), ("mushroom pizza", 1500), ("lamb skewers", 2150), ("fennel salad", 975),
                      ("sticky toffee pudding", 850), ("sparkling water", 450), ("house red (glass)", 790), ("pear cider", 640)],
    "Little Pho Corner": [("spring rolls", 695), ("beef pho", 1325), ("tofu pho", 1190), ("lemongrass chicken", 1480), ("papaya salad", 920),
                          ("iced coffee", 520), ("jasmine tea pot", 480), ("mango sticky rice", 780), ("lager", 610)],
    "The Copper Kettle": [("scotch egg", 590), ("ploughman's board", 1480), ("steak pie", 1650), ("veggie curry", 1340), ("chips", 450),
                          ("apple crumble", 740), ("ginger beer", 480), ("dark ale pint", 640), ("tea for one", 310)],
    "Casa Mirabel": [("patatas bravas", 780), ("croquetas", 960), ("seafood paella", 2250), ("grilled octopus", 1890), ("tomato bread", 520),
                     ("flan", 690), ("sangria jug", 1850), ("tinto de verano", 580), ("sparkling lemonade", 410)],
    "Dosa Garden": [("onion bhaji", 640), ("masala dosa", 1190), ("lamb rogan josh", 1560), ("chana masala", 1260), ("garlic naan", 390),
                    ("mango lassi", 480), ("kulfi", 590), ("lime soda", 380), ("cobra beer", 560)],
}
BS_INTRO = [
    "We went out for {who}'s thing last night and I volunteered to sort the bill. Now I have to work out who owes what.",
    "dinner with the climbing group, 5 of us were meant to split it evenly but it clearly wasn't even so here we are",
    "Could you help me split a restaurant bill fairly? I am the designated organiser and I hate it.",
    "I have the receipt photo typed up below. Everyone ordered different stuff and a few things were shared.",
    "Whoever invented splitting the bill evenly was not at our table, I had a salad and Tomas had everything.",
]


@family("chat-bill-split", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="restaurant bill with shared dishes, tax, tip, coupon, gift card or birthday rule; each person's final amount")
def gen_bill(rng, n):
    plan = [2, 2, 2, 3, 3, 4, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            venue = rng.choice(list(MENUS))
            menu = MENUS[venue]
            P = rng.randint(3, 4) if d <= 3 else rng.randint(4, 6)
            people = C.pick_names(rng, P)
            own = {p: [] for p in people}
            for p in people:
                for _ in range(rng.randint(1, 3 if d >= 3 else 2)):
                    own[p].append(rng.choice(menu))
            shared = []
            for _ in range(rng.randint(1, 2 if d <= 3 else 3)):
                it = rng.choice(menu[:5])
                group = rng.sample(people, rng.randint(2, P))
                shared.append((it, group))
            tax = rng.choice([0, 0, Fraction(7, 100), Fraction(825, 10000), Fraction(8, 100), Fraction(1, 10)]) if d >= 3 else 0
            tip = rng.choice([Fraction(10, 100), Fraction(15, 100), Fraction(18, 100), Fraction(20, 100)])
            coupon = Fraction(rng.choice([10, 15, 20]), 100) if d >= 4 and rng.random() < 0.8 else 0
            bday = rng.choice(people) if d == 5 else None
            gift = None
            if d >= 4:
                gp = rng.choice([p for p in people if p != bday])
                gift = (gp, rng.choice([1000, 1500, 2000, 2500]))
            svc = rng.choice([0, 300, 500]) if d == 5 else 0
            # solve
            pre = {p: Fraction(sum(c for _, c in own[p])) for p in people}
            for (nm, c), group in shared:
                for p in group:
                    pre[p] += Fraction(c, len(group))
            if bday:
                bd_own = Fraction(sum(c for _, c in own[bday]))
                for p in people:
                    if p == bday:
                        pre[p] -= bd_own
                    else:
                        pre[p] += bd_own / (P - 1)
            pre = {p: v * (1 - coupon) for p, v in pre.items()}
            final = {}
            for p in people:
                v = pre[p] * (1 + tax + tip)
                v += Fraction(svc, P)
                if gift and gift[0] == p:
                    v = max(Fraction(0), v - gift[1])
                final[p] = C.cents_half_up(v)
            if bday and pre[bday] == 0:
                continue
            amounts = [C.money(final[p]) for p in people]
            # receipt text
            lines = [venue, ""]
            for p in people:
                lines.append(f"{p}: " + ", ".join(f"{nm} {C.money(c)}" for nm, c in own[p]))
            for (nm, c), group in shared:
                lines.append(f"Shared: {nm} {C.money(c)} (between {', '.join(group)})")
            receipt = "\n".join(lines)
            rules = []
            if bday:
                rules.append(f"It was {bday}'s birthday, so {bday}'s own dishes (not the shared ones) are split equally among everyone else, and {bday} pays only a share of the shared dishes.")
            if coupon:
                rules.append(f"We had a {int(coupon * 100)}% off coupon on the whole food bill, so it comes off every person's food total before tax and tip.")
            adj = " (after the coupon/birthday arrangement above)" if (coupon or bday) else ""
            if tax:
                pct = tax * 100
                rules.append(f"Tax is {float(pct):g}%, charged on each person's own food total{adj}.")
            rules.append(f"Tip is {int(tip * 100)}% of each person's own food total{adj}, before any tax, covered by that person.")
            if svc:
                rules.append(f"There is also a flat {C.money(svc)} service charge, split equally between all {P} of us.")
            if gift:
                rules.append(f"{gift[0]} has a {C.money(gift[1])} gift card, which comes off {gift[0]}'s own final amount at the very end (it can't go below zero).")
            rules.append("Each person's number is rounded to the nearest cent, halves up; if the total is off by a cent or two it's fine.")
            intro = rng.choice(BS_INTRO).format(who=rng.choice(people))
            ask = "How much does each person pay?"
            ask += rng.choice([" Please give each person's amount like Name: 12.34.", " List everyone with their exact amount please.", " One line per person with the amount to two decimals."])
            reg = C.register_for(rng)
            prompt = C.chat(rng, intro, ask, C.block(receipt), reg, spec=" ".join(rules))
            if not C.uniq_in_prompt_ok(prompt, amounts) or len(set(amounts)) < len(amounts) - 1:
                continue
            gold = "; ".join(f"{p}: {C.money(final[p])}" for p in people)
            yield C.answer_task(f"{i + 1:02d}-{venue.split()[0].lower()}-{P}p", prompt, d, amounts, gold, tags=["bill", "rounding"],
                                notes={"people": P, "tax": float(tax), "tip": float(tip), "coupon": float(coupon), "birthday": bool(bday)})
            break
        else:
            raise RuntimeError("bill split: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-shift-pay

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
JOBS = [("kitchen porter at a hotel", "the hotel kitchen"), ("pharmacy assistant", "the pharmacy"), ("night-shift stock handler", "the warehouse"),
        ("bar and events staff", "the bar"), ("care-home support worker", "the care home"), ("ferry deck hand", "the ferry company"),
        ("bakery counter staff", "the bakery"), ("museum evening guide", "the museum")]


def _t(m):
    return f"{m // 60:02d}:{m % 60:02d}"


@family("chat-shift-pay", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="weekly gross pay from a pasted timesheet with unpaid gaps, weekly overtime, night uplift, Sunday premium, a lead rate")
def gen_pay(rng, n):
    plan = [2, 2, 2, 3, 3, 4, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(200):
            rate = rng.choice([1150, 1240, 1325, 1480, 1575, 1690, 1810])
            ot_after = rng.choice([38, 40]) if d >= 3 else None
            night = rng.choice([Fraction(15, 100), Fraction(20, 100), Fraction(25, 100)]) if d >= 4 else 0
            sun = rng.choice([Fraction(25, 100), Fraction(50, 100)]) if d == 5 else 0
            lead_rate = rate + rng.choice([150, 200, 250]) if d == 5 else None
            shifts = []  # (dayidx, [(start,end)], lead)
            days_on = sorted(rng.sample(range(7), rng.randint(4, 6)))
            if d == 5 and 6 not in days_on:
                days_on = sorted(days_on[:-1] + [6]) if len(days_on) > 4 else sorted(days_on + [6])
            for di in days_on:
                if night and rng.random() < 0.45 and di != 5 and di != 6:
                    st = rng.choice([18 * 60, 19 * 60, 20 * 60 + 30, 21 * 60, 22 * 60])
                    en = (rng.choice([2, 3, 5, 6]) * 60 + 24 * 60) + rng.choice([0, 30])
                    segs = [(st, en)]
                    if d >= 4 and rng.random() < 0.5:
                        mid = st + rng.randrange(180, 300, 15)
                        segs = [(st, mid), (mid + rng.choice([30, 45]), en)]
                else:
                    st = rng.choice([6 * 60, 7 * 60 + 30, 8 * 60, 9 * 60, 12 * 60, 14 * 60, 16 * 60])
                    segs = []
                    cur = st
                    for _ in range(rng.choice([1, 2])):
                        ln = rng.randrange(180, 330, 15)
                        segs.append((cur, cur + ln))
                        cur += ln + rng.choice([30, 45, 60])
                    if di == 6 or (di == 5):
                        segs = [(a, min(b, 23 * 60 + 30)) for a, b in segs if a < 23 * 60]
                if di == 5:
                    segs = [(a, min(b, 24 * 60)) for a, b in segs]
                lead = bool(lead_rate) and rng.random() < 0.4
                shifts.append((di, segs, lead))
            if any(b <= a for _, segs, _ in shifts for a, b in segs):
                continue
            # solve minute by minute
            total = Fraction(0)
            worked = 0
            ot_min = ot_after * 60 if ot_after else None
            for di, segs, lead in sorted(shifts, key=lambda s: s[0]):
                r = Fraction(lead_rate if lead else rate, 60)
                for a, b in segs:
                    for m in range(a, b):
                        mult = Fraction(1)
                        if ot_min is not None and worked >= ot_min:
                            mult = Fraction(3, 2)
                        worked += 1
                        clock = m % 1440
                        if night and (clock >= 22 * 60 or clock < 6 * 60):
                            mult += night
                        if sun and di == 6:
                            mult += sun
                        total += r * mult
            cents = C.cents_half_up(total)
            hours = Fraction(worked, 60)
            if d >= 3 and not (hours > ot_after + 1):
                continue
            if d == 2 and not (hours >= 15):
                continue
            # text
            tbl = []
            for di in range(7):
                row = next((s for s in shifts if s[0] == di), None)
                if row is None:
                    tbl.append(f"{DAYS[di]}  off")
                else:
                    parts = []
                    for a, b in row[1]:
                        parts.append(f"{_t(a % 1440)}-{_t(b % 1440)}")
                    tag = "  (lead)" if row[2] else ""
                    tbl.append(f"{DAYS[di]}  " + "  ".join(parts) + tag)
            job, place = rng.choice(JOBS)
            rules = [f"The base rate is {C.money_c(rate)} an hour, paid by the minute, and the gaps between the two time ranges on a day are unpaid."]
            if ot_after:
                rules.append(f"Overtime: every minute after the first {ot_after} paid hours of the week (counting in day order from Monday) is paid at 1.5 times the base rate.")
            if lead_rate:
                rules.append(f"Days marked (lead) are paid at {C.money_c(lead_rate)} an hour base instead.")
            if night:
                rules.append(f"Night work: any minute between 22:00 and 06:00 on the clock earns an extra {int(night * 100)}% of the base rate on top (this adds to overtime rather than multiplying with it, so a night minute in overtime is 1.5 + {float(night):g} times).")
            if sun:
                rules.append(f"Anything on a Sunday shift earns an extra {int(sun * 100)}% of the base rate on top, added the same way.")
            rules.append("A shift that runs past midnight counts for the day it started.")
            intro = rng.choice([
                f"I work as a {job} and I think {place} underpaid me last week. Here is my timesheet.",
                f"payslip looks wrong, i do shifts at {place}. This is what I actually worked (I keep my own notes).",
                f"Can you work out what I should have been paid for last week? I'm a {job}, and payroll never explains the maths.",
                f"I want to check my own pay before I raise it with {place}. The week ran Monday to Sunday.",
            ])
            spec = " ".join(rules)
            ask = rng.choice(["What is my gross pay for the week", "What should the gross pay have been", "How much gross pay do I get"]) + " in dollars and cents (round to the nearest cent, halves up, only at the very end)?"
            reg = C.register_for(rng)
            if d >= 4 and rng.random() < 0.5:
                files = {"timesheet.txt": "\n".join(tbl) + "\n"}
                prompt = C.chat(rng, intro.replace(" Here is my timesheet.", "").replace(" This is what I actually worked (I keep my own notes).", "").replace(" Here are my notes.", ""), ask, None, reg, spec="My hours for the week are in timesheet.txt (one line per day). " + spec)
                start = files
            else:
                prompt = C.chat(rng, intro, ask, C.block("\n".join(tbl)), reg, spec=spec)
                start = None
            ans = C.money(cents)
            if C.nosep([ans]):
                prompt = prompt.rstrip("\n") + "\n" + C.nosep([ans]).strip()
            if not C.uniq_in_prompt_ok(prompt, [ans]):
                continue
            gold = f"Gross pay for the week: {ans}"
            yield C.answer_task(f"{i + 1:02d}-d{d}-{DAYS[days_on[0]].lower()}", prompt, d, [ans], gold, start=start,
                                tags=["payroll", "time"], notes={"overtime_after": ot_after, "night": float(night), "sunday": float(sun), "lead": bool(lead_rate)})
            break
        else:
            raise RuntimeError("pay: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-price-traps

THINGS = ["a standing desk", "a pair of trail shoes", "a second-hand cargo bike", "a espresso machine", "a tent", "a set of paint rollers",
          "a pressure cooker", "noise-cancelling headphones", "a record player", "a garden shed", "a drum kit", "a wool coat", "a e-reader"]


@family("chat-price-traps", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="discount stacking, reverse sales tax, margin vs markup, up-then-down percentages, plan comparisons")
def gen_traps(rng, n):
    plan = [1, 2, 2, 3, 3, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(300):
            k = rng.choice({1: ["updown", "tip_base"], 2: ["stack_two", "tax_rev", "annual"], 3: ["bulk", "annual", "margin", "stack_two"],
                            4: ["stack_rev", "margin", "tax_rev"], 5: ["stack_rev", "margin"]}[d])
            thing = rng.choice(THINGS)
            reg = C.register_for(rng)
            if k == "updown":
                p = rng.choice([4000, 6000, 8000, 12000, 20000, 24000])
                a, b = rng.choice([10, 20, 25, 30, 40, 50]), rng.choice([10, 20, 25, 30, 40, 50])
                num = (100 + a) * (100 - b)
                if num == 10000:
                    continue
                fin_c = p * num // 10000
                net = Fraction(num - 10000, 100)
                net_s = f"{float(abs(net)):.2f}"
                contains = [C.money(fin_c), net_s]
                intro = f"The price of {thing} at my local shop went up {a}% in spring and then dropped {b}% in the summer sale. It started at {C.money_c(p)}."
                ask = "What does it cost now, and what is the overall change versus the starting price in percent (two decimals; tell me whether it is up or down)?"
                gold = f"Now {C.money(fin_c)}; overall change {'up' if net > 0 else 'down'} {net_s}%."
            elif k == "stack_two":
                p = rng.choice([8800, 12000, 15600, 24000, 32400])
                a, b = rng.choice([10, 20, 25, 30]), rng.choice([10, 15, 20])
                fin_c = p * (100 - a) * (100 - b) // 10000
                eff = Fraction(10000 - (100 - a) * (100 - b), 100)
                contains = [C.money(fin_c), f"{float(eff):.2f}"]
                intro = f"I'm looking at {thing} with a sticker price of {C.money_c(p)}. The shop has {a}% off, and at checkout my loyalty card takes a further {b}% off the already-reduced price."
                ask = "What do I pay, and what single overall discount percentage is that compared to the sticker (two decimals)?"
                gold = f"{C.money(fin_c)}; effective discount {float(eff):.2f}%."
            elif k == "stack_rev":
                p = rng.choice([8000, 12000, 16000, 20000, 24000, 36000, 48000])
                a, b = rng.choice([10, 20, 25, 30, 40]), rng.choice([5, 10, 15, 20])
                fin_c = p * (100 - a) * (100 - b) // 10000
                tax = rng.choice([5, 8, 10])
                paid = C.cents_half_up(Fraction(fin_c) * (100 + tax) / 100)
                saved = p - fin_c
                contains = [str(p // 100), C.money(saved)]
                intro = (f"I lost the tag for {thing} but I kept the receipt. It was marked down {a}%, then I used a {b}% off code on the reduced price, "
                         f"and {tax}% sales tax was added at the end. I paid {C.money_c(paid)} in total.")
                ask = ("The original sticker price was a whole number of dollars. What was it, and how much did the markdown and the code save me together "
                       "before tax (dollars and cents)?")
                gold = f"Sticker {p // 100} dollars; the two discounts saved {C.money(saved)} before tax."
            elif k == "tax_rev":
                tax = rng.choice([Fraction(5), Fraction(6), Fraction(75, 10), Fraction(8), Fraction(20), Fraction(15)])
                total = rng.randrange(2000, 40000, 5)
                pre = Fraction(total) * 100 / (100 + tax)
                if (pre - pre.numerator // pre.denominator) == Fraction(1, 2):
                    continue
                pre_c = C.cents_half_up(pre)
                contains = [C.money(pre_c), C.money(total - pre_c)]
                intro = f"The receipt for {thing} just says {C.money_c(total)} total, tax included. The tax rate here is {float(tax):g}%."
                ask = "How much of that is the pre-tax price and how much is the tax itself? Nearest cent for each."
                gold = f"Pre-tax {contains[0]}, tax {contains[1]}."
            elif k == "margin":
                cost = rng.choice([1800, 2400, 3000, 4500, 6000, 7500, 12000])
                m = rng.choice([20, 50, 60, 75])
                price = cost * 100 // (100 - m)
                markup = (price - cost) * 100 // cost
                contains = [C.money(price), str(markup)]
                intro = (f"I resell {thing}. They cost me {C.money_c(cost)} each, and I want a gross margin of {m}% of the *selling price* "
                         f"(not of my cost).")
                ask = "What should I charge, and what markup on cost does that work out to (a whole number of percent)?"
                gold = f"Price {contains[0]}, markup {markup}% on cost."
            elif k == "annual":
                mo = rng.choice([899, 1099, 1299, 1499, 1999, 2499])
                free = rng.choice([1, 2, 3])
                yearly = mo * (12 - free)
                eff = Fraction(yearly, 12)
                if eff - (eff.numerator // eff.denominator) == Fraction(1, 2):
                    continue
                disc = Fraction(free * 100, 12)
                contains = [C.money(yearly), C.money(C.cents_half_up(eff)), f"{float(disc):.2f}"]
                intro = f"My streaming app charges {C.money_c(mo)} a month, or an annual plan where {free} month{'s are' if free > 1 else ' is'} free (so you pay for {12 - free} months upfront)."
                ask = "What does the annual plan cost, what is the effective monthly price on that plan (nearest cent), and what percent saving is it versus paying monthly all year (two decimals)?"
                gold = f"Annual {C.money(yearly)}; effective monthly {contains[1]}; saving {contains[2]}%."
            elif k == "bulk":
                small_w, small_p = rng.choice([(500, 189), (750, 249), (400, 215)])
                big_w, big_p = rng.choice([(2000, 599), (3000, 799), (1500, 489), (5000, 1349)])
                us, ub = Fraction(small_p * 1000, small_w), Fraction(big_p * 1000, big_w)
                if any(x - (x.numerator // x.denominator) == Fraction(1, 2) for x in (us, ub)) or abs(us - ub) < 10:
                    continue
                better = "big" if ub < us else "small"
                contains = [C.money(C.cents_half_up(us)), C.money(C.cents_half_up(ub))]
                what = rng.choice(["oat bags", "bags of basmati rice", "tubs of fabric softener", "boxes of dishwasher tabs"])
                intro = f"At the supermarket the {what} come in two sizes: the {small_w} g one is {C.money_c(small_p)} and the {big_w} g one is {C.money_c(big_p)}."
                ask = ("What is the price per kilogram of each (nearest cent, written like 3.78), and which is the better value? "
                       "In your answer use the word big or small for the winning pack.")
                gold = f"Small {contains[0]}/kg, big {contains[1]}/kg; the {better} one is cheaper per kg."
            else:  # tip_base
                bill = rng.randrange(25, 120) * 100
                tax = rng.choice([7, 8, 10])
                tippct = rng.choice([15, 18, 20])
                tot = bill * (100 + tax) // 100
                tip_pre = bill * tippct // 100
                tp = Fraction(tot * tippct, 100)
                if tp - (tp.numerator // tp.denominator) == Fraction(1, 2):
                    continue
                tip_post = C.cents_half_up(tp)
                contains = [C.money(tip_pre), C.money(tip_post)]
                intro = (f"Dinner came to {C.money_c(bill)} before tax, and {tax}% tax is added to give the total on the bill. My friend says the tip should be "
                         f"{tippct}% of the pre-tax amount, my other friend says {tippct}% of the final total.")
                ask = "How much is the tip under each method (nearest cent)? Give the pre-tax-method tip first."
                gold = f"Tip on pre-tax: {contains[0]}; tip on total: {contains[1]}."
                if tip_pre == tip_post:
                    continue
            prompt = C.chat(rng, intro, ask, None, reg)
            if not C.uniq_in_prompt_ok(prompt, contains, True):
                continue
            yield C.answer_task(f"{i + 1:02d}-{k}", prompt, d, contains, gold, fold=True, tags=["percent", "prices"], notes={"kind": k})
            break
        else:
            raise RuntimeError("traps: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-savings-sim

SIM_INTRO = [
    "My credit union is offering a savings account and I want to know what actually happens month by month, because their leaflet only shows a rosy headline.",
    "I am trying to decide between paying down my loan faster or just letting my savings grow, so I am simulating both by hand and getting different answers each time.",
    "Last year I opened a regular-saver account and I want to check the bank's maths.",
    "I borrowed money from my uncle on 'bank-like' terms and we agreed the rules below, but I cannot make the final numbers agree with his spreadsheet.",
    "I keep getting different answers from different online calculators, so here are the exact rules and I want one definitive result.",
]


def _simulate_savings(open_c, monthly, apr_bp, months, fee, bonus_pct, deposit_at):
    bal = open_c
    hist = []
    for m in range(1, months + 1):
        if deposit_at == "start":
            bal += monthly
        interest = C.cents_half_up(Fraction(bal) * apr_bp / 120000)
        bal += interest
        if deposit_at == "end":
            bal += monthly
        bal -= fee
        if bonus_pct and m % 12 == 0:
            bal += C.cents_half_up(Fraction(bal) * bonus_pct / 100)
        hist.append(bal)
    return hist


def _simulate_loan(principal, apr_bp, pay):
    bal, m, tot_int = principal, 0, 0
    while bal > 0:
        m += 1
        interest = C.cents_half_up(Fraction(bal) * apr_bp / 120000)
        tot_int += interest
        bal += interest
        p = min(pay, bal)
        bal -= p
        last = p
        if m > 600:
            raise ValueError("never ends")
    return m, last, tot_int


@family("chat-savings-sim", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="month-by-month savings and loan simulations with per-month rounding, fees and bonuses; first month crossing a target")
def gen_savings(rng, n):
    plan = [2, 2, 2, 3, 3, 4, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(200):
            reg = C.register_for(rng)
            kind = "loan" if (d >= 4 and rng.random() < 0.55) or (d == 5) else "save"
            intro = rng.choice(SIM_INTRO)
            if kind == "save":
                open_c = rng.randrange(40000, 450000, 2500)
                monthly = rng.choice([0, 2500, 5000, 10000, 15000]) if d >= 3 else 0
                apr = rng.randrange(150, 650, 5)
                months = rng.choice([6, 9, 12, 18, 24]) if d <= 3 else rng.choice([24, 30, 36])
                fee = rng.choice([0, 0, 150, 300]) if d >= 4 else 0
                bonus = rng.choice([0, 1, 2]) if d == 5 else 0
                dep_at = rng.choice(["start", "end"]) if monthly else "start"
                hist = _simulate_savings(open_c, monthly, apr, months, fee, bonus, dep_at)
                target = hist[-1] - rng.randrange(1, max(2, months // 3)) * max(1, hist[-1] // 100)
                first = next((m + 1 for m, b in enumerate(hist) if b >= target), None)
                if first is None or first == months:
                    continue
                rules = [f"I open the account with {C.money_c(open_c)}.", f"The interest rate is {apr / 100:g}% a year, credited every month at month end as the balance times (rate divided by 12), rounded to the nearest cent, halves up."]
                if monthly:
                    rules.append(f"I add {C.money_c(monthly)} every month, at the {'start of the month (so it earns interest that month)' if dep_at == 'start' else 'end of the month, after that month’s interest has been credited'}.")
                if fee:
                    rules.append(f"There is a monthly fee of {C.money_c(fee)} taken at month end after the interest is credited.")
                if bonus:
                    rules.append(f"After month 12 and every 12 months after that, the bank adds a loyalty bonus of {bonus}% of the balance (rounded to the nearest cent, halves up), after that month's fee.")
                spec = " ".join(rules)
                ask = f"What is the balance after {months} months, and in which month (counting the first month as month 1) does the end-of-month balance first reach {C.money_c(target)} or more?"
                ask += " Give the balance as dollars and cents, and the month as 'month N'."
                contains = [C.money(hist[-1]), f"month {first}"]
                gold = f"Balance after {months} months: {C.money(hist[-1])}; first reaches the target in month {first}."
            else:
                principal = rng.choice([300000, 450000, 800000, 1200000, 1500000])
                apr = rng.choice([450, 590, 725, 899, 1050])
                pay = rng.choice([25000, 30000, 40000, 55000, 60000])
                # payment must be well above first month's interest
                if pay < C.cents_half_up(Fraction(principal) * apr / 120000) * 1.5:
                    continue
                m, last, tot_int = _simulate_loan(principal, apr, pay)
                if m > 90:
                    continue
                rules = [f"The loan is {C.money_c(principal)} at {apr / 100:g}% a year. Each month interest is added first (balance times rate divided by 12, nearest cent, halves up), then I pay {C.money_c(pay)}.",
                         "The last payment is just whatever is left, no extra fees."]
                spec = " ".join(rules)
                ask = "In which month do I make the final payment, how big is the final payment, and what is the total interest I pay over the whole loan?"
                ask += " Please give the month as 'month N' and the other two as dollars and cents."
                contains = [f"month {m}", C.money(last), C.money(tot_int)]
                gold = f"Final payment in month {m}: {C.money(last)}; total interest {C.money(tot_int)}."
            prompt = C.chat(rng, intro, ask + C.nosep(contains), None, reg, spec=spec)
            if not C.uniq_in_prompt_ok(prompt, contains, True):
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}-d{d}", prompt, d, contains, gold, fold=True, tags=["interest", "simulation"], notes={"kind": kind})
            break
        else:
            raise RuntimeError("savings: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-currency-trip

CUR = ["EUR", "USD", "GBP", "CHF", "CAD", "AUD"]


def _floor_c(x: Fraction) -> int:
    return x.numerator // x.denominator


@family("chat-currency-trip", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="currency exchange with spreads, flat fees and floor rounding; round trips and kiosk-versus-card comparisons")
def gen_currency(rng, n):
    plan = [2, 2, 3, 3, 4, 4, 5, 3]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            a, b = rng.sample(CUR, 2)
            amount = rng.choice([30000, 50000, 80000, 120000, 200000])
            buy = Fraction(rng.randrange(8000, 12500), 10000)  # 1 A = buy B at the kiosk
            sell = Fraction(rng.randrange(8000, 12500), 10000) * Fraction(1, 1)
            # choose a plausible back rate: 1 B = back A, a little worse than 1/buy
            back = Fraction(int(float(1 / buy) * 10000 * rng.uniform(0.93, 0.975)), 10000)
            fee = rng.choice([0, 300, 500, 800])
            reg = C.register_for(rng)
            if d <= 3:
                got = _floor_c(Fraction(amount - fee) * buy)
                contains = [C.money(got)]
                spend = (got * rng.choice([50, 60, 70, 80]) // 100) // 100 * 100 if d == 3 else 0
                if d == 2:
                    intro = f"I'm swapping {C.money(amount)} {a} for {b} at an airport kiosk before a trip."
                    spec = (f"The kiosk gives {float(buy):.4f} {b} per 1 {a}, and takes a flat fee of {C.money(fee)} {a} off the amount first. "
                            f"The kiosk rounds the result down to the cent.") if fee else (
                        f"The kiosk gives {float(buy):.4f} {b} per 1 {a} with no fee, and rounds down to the cent.")
                    ask = rng.choice([f"How many {b} do I get?", f"What will I walk away with in {b}?"])
                    gold = f"{C.money(got)} {b}."
                else:
                    left = got - spend
                    back_got = _floor_c(Fraction(left) * back)
                    contains = [C.money(back_got)]
                    intro = f"After a holiday I want to know how much I lose swapping money back and forth. I changed {C.money(amount)} {a} into {b} before leaving."
                    spec = (f"Outbound: {float(buy):.4f} {b} per 1 {a}, flat fee {C.money(fee)} {a} taken off the {a} first, result rounded down to the cent. "
                            f"I spent {C.money(spend)} {b} and changed the rest back at {float(back):.4f} {a} per 1 {b}, no fee on the way back, rounded down to the cent.")
                    ask = f"How many {a} do I end up with?"
                    gold = f"{C.money(back_got)} {a} (from {C.money(left)} {b} left)."
                    if spend <= 0 or left <= 0:
                        continue
                prompt = C.chat(rng, intro, ask + C.nosep(contains), None, reg, spec=spec)
            else:
                # compare kiosk vs card for a spending amount in B
                spend_b = rng.choice([40000, 65000, 90000, 150000])
                kiosk_need = Fraction(spend_b) / buy  # A needed at kiosk (pay fee in A)
                kiosk_a = int(-(-(kiosk_need * 1) // 1)) + fee  # ceil to cent, plus fee
                card_rate = Fraction(int(float(buy) * 10000 * rng.uniform(0.985, 1.0)), 10000)
                markup = rng.choice([Fraction(15, 1000), Fraction(2, 100), Fraction(25, 1000)])
                card_cost = Fraction(spend_b) / card_rate * (1 + markup)
                card_a = int(-(-card_cost // 1))
                cheaper = "card" if card_a < kiosk_a else "kiosk"
                diff = abs(card_a - kiosk_a)
                if diff < 200:
                    continue
                contains = [C.money(kiosk_a), C.money(card_a)]
                intro = (f"I need to pay {C.money(spend_b)} {b} worth of stuff on a trip and I'm torn between exchanging cash up front and "
                         f"just using my {a} card abroad.")
                spec = (f"Cash route: the kiosk gives {float(buy):.4f} {b} per 1 {a}; to get exactly {C.money(spend_b)} {b} I would hand over the {a} amount needed (rounded up to the cent once) plus a flat {C.money(fee)} {a} fee. "
                        f"Card route: the card network uses {float(card_rate):.4f} {b} per 1 {a}, then my bank adds a {float(markup * 100):g}% foreign fee on top, so the cost is the {b} amount divided by that rate, times {float(1 + markup):g}, rounded up to the cent once at the end.")
                ask = f"What does each route cost me in {a}, and which is cheaper?"
                gold = f"Kiosk {C.money(kiosk_a)} {a}, card {C.money(card_a)} {a}; the {cheaper} is cheaper."
                prompt = C.chat(rng, intro, ask + C.nosep(contains), None, reg, spec=spec)
            if not C.uniq_in_prompt_ok(prompt, contains, True):
                continue
            yield C.answer_task(f"{i + 1:02d}-{a.lower()}{b.lower()}-d{d}", prompt, d, contains, gold, fold=True, tags=["currency", "rounding"])
            break
        else:
            raise RuntimeError("currency: no instance")
