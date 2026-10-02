"""Questions whose set-up contains a false premise (a wrong fact, a slipped sum, a misread table, a mis-ordered timeline).
The answer is checked on the *correct* computed result, which a premise-accepting answer cannot produce."""
from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta
from fractions import Fraction

from fx import family

from . import _common as C
from .calc_time import hm, long_date

# --------------------------------------------------------------------------------------------------------------------
# chat-premise-fact

TRUE_OFFSET = {"Mumbai": 330, "Kathmandu": 345, "Dhaka": 360, "Kabul": 270, "Tehran": 210, "Colombo": 330, "Yangon": 390, "Singapore": 480, "Tokyo": 540, "Dubai": 240,
               "Nairobi": 180, "Lagos": 60, "Reykjavik": 0, "Adelaide": 570, "Caracas": -240}
WRONG_OFFSET = {"Mumbai": 360, "Kathmandu": 330, "Dhaka": 330, "Kabul": 300, "Tehran": 240, "Colombo": 360, "Yangon": 420, "Singapore": 420, "Tokyo": 480, "Dubai": 180,
                "Nairobi": 120, "Lagos": 120, "Reykjavik": 60, "Adelaide": 600, "Caracas": -180}
UNITS = [("mile", "km", Fraction(1609344, 1000000), Fraction(12, 10), "km"), ("inch", "cm", Fraction(254, 100), Fraction(2), "cm"), ("gallon", "litres", Fraction(3785411784, 10 ** 9), Fraction(4, 1), "litres"),
         ("pound", "kg", Fraction(45359237, 10 ** 8), Fraction(1, 2), "kg"), ("foot", "m", Fraction(3048, 10000), Fraction(1, 4), "m"), ("ounce", "g", Fraction(28349523125, 10 ** 9), Fraction(30), "g")]
# slightly different constants a careful person might use; an instance is only kept when they all round to the same one-decimal answer
ALT_CONST = {"mile": [Fraction(1609, 1000), Fraction(16093, 10000)], "inch": [Fraction(254, 100)], "gallon": [Fraction(3785, 1000), Fraction(37854, 10000)], "pound": [Fraction(4536, 10000), Fraction(45359, 100000)],
             "foot": [Fraction(3048, 10000), Fraction(30, 100)], "ounce": [Fraction(2835, 100), Fraction(28349, 1000)]}
MONTH31_WRONG = [("April", 4), ("June", 6), ("September", 9), ("November", 11)]


def _r1(x: Fraction) -> str:
    return f"{float(x):.1f}"


@family("chat-premise-fact", category="chat", lang="text", kind="premise", n=8, mode="answer",
        summary="the question builds on a confidently stated false fact (month length, weekday, time-zone offset, unit constant, area formula, stacked discounts); the answer is checked on the true result")
def gen_pfact(rng, n):
    plan = [2, 2, 2, 3, 3, 4, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(200):
            kind = rng.choice({2: ["units", "stack"], 3: ["month_days", "weekday", "weeks_month", "units"], 4: ["tz", "formula", "leap"], 5: ["combo_tz_weekday", "combo_units_month"]}[d])
            reg = C.register_for(rng)
            if kind == "units":
                u = rng.choice(UNITS)
                qty = rng.choice([13.1, 26.2, 42, 50, 7.5, 150, 18, 3.25])
                qf = Fraction(str(qty))
                val = qf * u[2]
                if abs(float(val * 10) - round(float(val * 10)) - 0.5) < 1e-9:
                    continue
                ans = _r1(val)
                if u[0] == "foot":
                    ALT_CONST["foot"] = [Fraction(3048, 10000)]
                if any(_r1(qf * c) != ans for c in ALT_CONST[u[0]]):
                    continue
                intro = (f"I'm converting some figures for a form. A {u[0]} is {float(u[3]):g} {u[1]}, right? "
                         f"Then I need {qty:g} {u[0]}s expressed in {u[4]}.")
                ask = f"What is {qty:g} {u[0]}s in {u[4]}, to one decimal place?"
                contains = [ans]
                gold = f"Actually 1 {u[0]} is {float(u[2]):.4g} {u[1]}, not {float(u[3]):g}; so {qty:g} {u[0]}s is {ans} {u[4]}."
            elif kind == "stack":
                a = rng.choice([10, 15, 20, 25, 30])
                price = rng.choice([4500, 8500, 12000, 15900, 24000])
                claim = 2 * a
                fin = Fraction(price) * (100 - a) * (100 - a) / 10000
                fin_c = C.cents_half_up(fin)
                intro = (f"The shop has a sale that takes {a}% off, and then a code that takes another {a}% off the sale price. "
                         f"That's {claim}% off in total, I assume, since it's the same {a} twice.")
                ask = f"What would I pay for an item with a sticker price of {C.money_c(price)}? Give the amount to the cent."
                contains = [C.money(fin_c)]
                gold = f"Not {claim}% off: the second discount applies to the reduced price, so you pay {C.money(fin_c)}."
            elif kind == "month_days":
                mname, mnum = rng.choice(MONTH31_WRONG)
                y = rng.randint(2026, 2028)
                day0 = rng.randint(14, 28)
                ln = rng.randint(40, 60)
                start = date(y, mnum, day0)
                end = start + timedelta(days=ln - 1)
                intro = (f"I signed up for a {ln}-day free trial on {day0} {mname} {y}; {mname} has 31 days, so I figure I will have at least a couple of days left over in the next month. "
                         f"Day 1 of the trial is the day I signed up.")
                ask = "On which date does the trial's last day fall? Please give it as YYYY-MM-DD."
                contains = [C.iso(end)]
                gold = f"{mname} actually has 30 days, so the last day is {C.iso(end)}."
            elif kind == "weekday":
                y = rng.randint(2026, 2029)
                x = date(y, 12, 25)
                wrong = C.WEEKDAYS[(x.weekday() + rng.choice([1, 2, 3])) % 7]
                nxt = date(y + 1, 1, 1)
                firstmon = nxt + timedelta(days=(0 - nxt.weekday()) % 7)
                intro = f"Christmas Day {y} falls on a {wrong}, I'm fairly sure, so I'm planning the holiday rota around that."
                ask = f"What is the date of the first Monday of {y + 1}, and what weekday is 1 January {y + 1}? (Date as YYYY-MM-DD.)"
                contains = [C.iso(firstmon), C.wd(nxt)]
                gold = f"Christmas {y} is actually a {C.wd(x)}; first Monday of {y + 1} is {C.iso(firstmon)}, and 1 Jan is a {C.wd(nxt)}."
            elif kind == "weeks_month":
                y = rng.randint(2026, 2028)
                m0 = rng.randint(1, 7)
                span = rng.randint(4, 6)
                st = date(y, m0, 1)
                en = date(y + (m0 + span) // 13, (m0 + span - 1) % 12 + 1, 1) - timedelta(days=1) if False else C.month_add(st, span) - timedelta(days=1)
                days = (en - st).days + 1
                intro = f"Every month is basically four weeks, so a {span}-month project is {span * 4} weeks, which I'm putting in the contract."
                ask = (f"If the project runs from {st.day} {C.MONTHS[st.month - 1]} {y} to the very end of the {span}th calendar month (so through {en.day} {C.MONTHS[en.month - 1]} {en.year}, both ends included), "
                       f"how many days and how many full weeks plus days is that? Write it like 'N days = W weeks D days'.")
                w, rem = divmod(days, 7)
                contains = [f"{days} days"]
                gold = f"{days} days = {w} weeks {rem} days (not {span * 4} weeks)."
            elif kind == "tz":
                city = rng.choice(list(TRUE_OFFSET))
                tr, wr = TRUE_OFFSET[city], WRONG_OFFSET[city]
                local = rng.choice([9 * 60, 10 * 60 + 30, 14 * 60, 15 * 60, 16 * 60 + 15])
                utc = (local - tr) % 1440
                dayshift = (local - tr) // 1440
                sign = lambda m: ("+" if m >= 0 else "-") + f"{abs(m) // 60}" + (f":{abs(m) % 60:02d}" if abs(m) % 60 else "")  # noqa: E731
                intro = f"My call with the {city} office is booked for {C.hhmm(local)} their local time. {city} is UTC{sign(wr)} all year round, as far as I know."
                ask = "What time is that in UTC (HH:MM)? And if it is the next or previous day in UTC, tell me which."
                contains = [C.hhmm(utc)]
                gold = f"{city} is UTC{sign(tr)}, so {C.hhmm(local)} there is {C.hhmm(utc)} UTC" + (" on the previous day" if dayshift < 0 else " on the next day" if dayshift > 0 else "") + "."
            elif kind == "formula":
                sub = rng.choice(["circle", "triangle", "cylinder", "sphere"])
                if sub == "circle":
                    r = rng.randint(2, 6)
                    area = math.pi * r * r
                    claimed = 2 * math.pi * r
                    ans = math.ceil(area)
                    intro = f"I'm mulching a circular flower bed with a radius of {r} m. The area of a circle is 2 x pi x r, so that's about {claimed:.1f} m2."
                    ask = "Mulch comes in bags that each cover exactly 1 m2. How many whole bags do I need (round up)?"
                    gold = f"Area is pi x r^2 = {area:.2f} m2, so {ans} bags."
                elif sub == "triangle":
                    b, h = rng.randint(4, 9), rng.randint(3, 8)
                    area = b * h / 2
                    ans = math.ceil(area)
                    intro = f"I need turf for a triangular lawn with a base of {b} m and a height of {h} m. Area of a triangle is base times height, so {b * h} m2."
                    ask = "Turf comes in 1 m2 rolls only. How many whole rolls do I need, rounding up?"
                    if area == int(area):
                        ans = int(area) + 0
                    gold = f"Area is half of base times height = {area:g} m2, so {ans} rolls."
                elif sub == "cylinder":
                    r, h = rng.randint(2, 5), rng.randint(2, 6)
                    vol = math.pi * r * r * h
                    ans = math.ceil(vol)
                    intro = f"I'm filling a cylindrical planter with radius {r} dm and height {h} dm. The volume is pi x r x h, so about {math.pi * r * h:.1f} dm3."
                    ask = "Compost is sold in 1-litre bags (1 dm3 each). How many whole bags do I need, rounding up?"
                    gold = f"Volume is pi x r^2 x h = {vol:.2f} dm3, so {ans} bags."
                else:
                    r = rng.randint(2, 5)
                    vol = 4 / 3 * math.pi * r ** 3
                    ans = math.ceil(vol)
                    intro = f"A spherical water tank has a radius of {r} m. Volume of a sphere is 4 x pi x r^2, so the surface-ish number {4 * math.pi * r * r:.1f} is what I'll quote."
                    ask = "How many whole cubic metres of water does it hold when full, rounding up?"
                    gold = f"Volume is 4/3 x pi x r^3 = {vol:.2f} m3, so {ans}."
                contains = [str(ans)]
                if abs(ans - (area if sub in ("circle", "triangle") else vol)) < 0.02:
                    continue
            elif kind == "leap":
                y = rng.choice([2029, 2030, 2031, 2033, 2034])
                intro = f"{y} is a leap year because it's coming up after 2028, which was one, and leap years just alternate every couple of years like that. I'm setting up a yearly counter."
                ask = f"How many days are there from 1 January {y} up to (not including) 1 January {y + 1}? And how many days is it from 28 February {y} to 1 March {y} (the 1st of March minus the 28th of February)?"
                tot = (date(y + 1, 1, 1) - date(y, 1, 1)).days
                gap = (date(y, 3, 1) - date(y, 2, 28)).days
                contains = [str(tot), str(gap)] if tot != gap else [str(tot)]
                contains = [str(tot)]
                gold = f"{y} is not a leap year: {tot} days, and 28 Feb to 1 Mar is {gap} day."
            elif kind == "combo_tz_weekday":
                city = rng.choice(["Kathmandu", "Mumbai", "Adelaide", "Tehran", "Kabul"])
                y = rng.randint(2026, 2029)
                x = date(y, 12, 25)
                wrong = C.WEEKDAYS[(x.weekday() + rng.choice([1, 2, 3])) % 7]
                mon = x + timedelta(days=(0 - x.weekday()) % 7 or 7)
                tr, wr = TRUE_OFFSET[city], WRONG_OFFSET[city]
                local = rng.choice([8 * 60, 9 * 60, 7 * 60 + 30])
                dt = datetime(mon.year, mon.month, mon.day) + timedelta(minutes=local - tr)
                sign = lambda m: ("+" if m >= 0 else "-") + f"{abs(m) // 60}" + (f":{abs(m) % 60:02d}" if abs(m) % 60 else "")  # noqa: E731
                intro = (f"A colleague in {city} starts a new shift on the first Monday after Christmas Day {y}, at {C.hhmm(local)} {city} time. "
                         f"Christmas that year is on a {wrong}, and {city} is UTC{sign(wr)}.")
                ask = "What is the start of that shift in UTC? Give it as YYYY-MM-DD HH:MM."
                contains = [f"{dt:%Y-%m-%d %H:%M}"]
                gold = f"Christmas {y} is a {C.wd(x)}; the Monday after is {C.iso(mon)}; {city} is UTC{sign(tr)}; so {dt:%Y-%m-%d %H:%M} UTC."
            else:  # combo_units_month
                u = rng.choice(UNITS[:3])
                mname, mnum = rng.choice(MONTH31_WRONG)
                y = rng.randint(2026, 2028)
                per_day = rng.choice([1.5, 2, 2.5, 3])
                day0 = rng.randint(18, 27)
                nd = rng.randint(14, 22)
                start = date(y, mnum, day0)
                end = start + timedelta(days=nd - 1)
                tot = Fraction(str(per_day)) * nd * u[2]
                intro = (f"Training plan: I run {per_day:g} {u[0]}s every day for {nd} days, starting {day0} {mname} {y}. For my log, a {u[0]} is {float(u[3]):g} {u[1]}, "
                         f"and {mname} has 31 days, so I'll be finished by the first of next month at the latest.")
                ask = f"What date is my last training day (YYYY-MM-DD), and how many {u[4]} is the whole plan to one decimal place?"
                contains = [C.iso(end), _r1(tot)]
                gold = f"{mname} has 30 days: last day {C.iso(end)}; a {u[0]} is {float(u[2]):.4g} {u[1]}: total {_r1(tot)} {u[4]}."
            prompt = C.chat(rng, intro, ask, None, reg)
            keep = C.unseen(prompt, contains, True, min_keep=len(contains))
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, d, keep, gold, fold=True, tags=["false-premise", "correction"], notes={"kind": kind})
            break
        else:
            raise RuntimeError("premise-fact: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-premise-arith


@family("chat-premise-arith", category="chat", lang="text", kind="premise", n=8, mode="answer",
        summary="the user's own arithmetic contains a slip and the follow-up builds on it: re-derive the total, the tax, the pace or the unit price")
def gen_parith(rng, n):
    plan = [2, 2, 2, 3, 3, 4, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(200):
            kind = rng.choice({2: ["unit_price", "pct_slip"], 3: ["sum_slip", "duration", "unit_price"], 4: ["sum_slip", "avg_slip", "unit_slip"], 5: ["chain", "avg_slip"]}[d])
            reg = C.register_for(rng)
            if kind == "sum_slip":
                k = rng.randint(3, 4)
                amts = [rng.randrange(8000, 220000, 25) for _ in range(k)]
                true = sum(amts)
                wrong = true + rng.choice([-10000, 10000, -100000, 100000, -1000, 1000])
                tax = rng.choice([5, 8, 10])
                pay = rng.choice([3, 4, 6])
                tot_tax = C.cents_half_up(Fraction(true) * (100 + tax) / 100)
                per = C.cents_half_up(Fraction(tot_tax, pay))
                intro = (f"I'm tidying the books. {k} invoices came in: " + ", ".join(C.money_c(a) for a in amts) + f". I added them up and got {C.money_c(wrong)}.")
                ask = (f"{tax}% tax gets added on top of the total, and then I want to pay it off in {pay} equal monthly instalments (rounded to the nearest cent). "
                       f"What is the total including tax, and what is each instalment?")
                contains = [C.money(tot_tax), C.money(per)]
                gold = f"The invoices actually sum to {C.money(true)}; with tax {C.money(tot_tax)}; each instalment {C.money(per)}."
            elif kind == "pct_slip":
                base = rng.choice([120, 250, 480, 640, 900])
                pct = rng.choice([8, 12, 15, 20])
                claim = base + pct
                true = Fraction(base) * (100 + pct) / 100
                people = rng.choice([3, 4, 5])
                intro = f"The bill is {base} before tax and tax is {pct}%, so I made it {claim} in total."
                ask = f"We split the real total evenly between {people} of us. How much is the full total, and how much does each person pay (two decimals)?"
                per = Fraction(true, people)
                contains = [f"{float(true):.2f}", f"{float(per):.2f}"]
                gold = f"{pct}% of {base} is {float(base * Fraction(pct, 100)):g}, not {pct}: total {float(true):.2f}, each {float(per):.2f}."
            elif kind == "duration":
                a = rng.randint(2, 4) * 60 + rng.randrange(35, 59, 3)
                b = rng.randint(1, 3) * 60 + rng.randrange(25, 55, 5)
                tot = a + b
                wrong = (a // 60 + b // 60) * 60 + (a % 60 + b % 60)  # forgot to carry minutes
                wrong_s = f"{wrong // 60}:{wrong % 60:02d}" if False else f"{(a // 60 + b // 60)}h{a % 60 + b % 60}"
                start = rng.randint(8, 11) * 60 + rng.choice([0, 15, 40])
                intro = f"Two legs of a journey take {hm(a)} and {hm(b)} (hours:minutes). I added them and got {wrong_s}, which looked a bit odd but I went with it."
                ask = f"If I set off at {C.hhmm(start)}, what time do I arrive (HH:MM, 24-hour; ignore any stop in between)? And what is the true total in H:MM?"
                contains = [C.hhmm(start + tot), hm(tot)]
                gold = f"Total {hm(tot)}; arrival {C.hhmm(start + tot)}."
            elif kind == "unit_price":
                bars = rng.choice([12, 18, 24])
                pack = rng.randrange(450, 1800, 5)
                unit_true = Fraction(pack, bars)
                unit_wrong = C.cents_half_up(Fraction(pack, bars + rng.choice([2, 3, 4])))
                want = rng.choice([30, 45, 50, 70])
                cost = C.cents_half_up(unit_true * want)
                if unit_true.denominator != 1 and (unit_true * want).denominator != 1 and False:
                    continue
                intro = f"A pack of {bars} cereal bars is {C.money_c(pack)}, so each one works out at {C.money_c(unit_wrong)}."
                ask = f"I need exactly {want} bars for the school trip. Using the pack price and the real pack size, what will {want} bars cost (nearest cent)? And what is the real price per bar to three decimals?"
                contains = [C.money(cost), f"{float(unit_true / 100):.3f}"]
                gold = f"Per bar {float(unit_true / 100):.3f}; {want} bars cost {C.money(cost)}."
            elif kind == "avg_slip":
                xs = [rng.randint(8, 40) for _ in range(rng.randint(5, 7))]
                true = Fraction(sum(xs), len(xs))
                wrong = Fraction(sum(xs), len(xs) + 1)
                if (true * 100).denominator != 1 and (true * 10).denominator != 1 and False:
                    continue
                intro = f"Weekly sales (units): {', '.join(map(str, xs))}. The average came out at {float(wrong):.2f} when I did it on my phone."
                top = max(xs)
                ask = f"By how much does the best week exceed the true average (two decimals), and what is the true average (two decimals)?"
                contains = [f"{float(true):.2f}", f"{float(top - true):.2f}"]
                gold = f"True average {float(true):.2f}; best week exceeds it by {float(top - true):.2f}."
            elif kind == "unit_slip":
                km = rng.choice([5, 8, 10, 12, 15, 21])
                wrong_mi = round(km * 0.7, 1)
                long = rng.choice([30, 42, 50, 75])
                mi = Fraction(long * 1000000, 1609344)
                intro = f"A {km} km run is {wrong_mi:g} miles, so I use 0.7 as my km-to-miles factor."
                ask = f"My long run is {long} km. How many miles is that, to two decimals, and how many km is a 10-mile race (two decimals)? Use the exact definition 1 mile = 1.609344 km."
                contains = [f"{float(mi):.2f}", f"{10 * 1.609344:.2f}"]
                gold = f"{long} km = {float(mi):.2f} miles (the factor is 0.6214, not 0.7); 10 miles = {10 * 1.609344:.2f} km."
            else:  # chain: two linked slips
                pcs = rng.randint(4, 7)
                price = rng.randrange(1200, 4800, 50)
                disc = rng.choice([10, 15, 20])
                gross = pcs * price
                wrong_gross = gross + rng.choice([-500, 500, 1000, -1000])
                net = C.cents_half_up(Fraction(gross) * (100 - disc) / 100)
                per = C.cents_half_up(Fraction(net, 2))
                intro = (f"I'm ordering {pcs} chairs at {C.money_c(price)} each. Multiply that out and I get {C.money_c(wrong_gross)}, and the supplier gives {disc}% off the whole order.")
                ask = "Taking the real figures: what is the price after the discount, and if two of us split that evenly, what does each pay (nearest cent)?"
                contains = [C.money(net), C.money(per)]
                gold = f"{pcs} x {C.money_c(price)} = {C.money_c(gross)} (not {C.money_c(wrong_gross)}); after {disc}% off {C.money(net)}; each pays {C.money(per)}."
            prompt = C.chat(rng, intro, ask + C.nosep(contains), None, reg)
            keep = C.unseen(prompt, contains, True, min_keep=len(contains))
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, d, keep, gold, fold=True, tags=["false-premise", "arithmetic"], notes={"kind": kind})
            break
        else:
            raise RuntimeError("premise-arith: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-premise-data

SHOPS = ["Alder St", "Bridge Rd", "Canal Walk", "Dock Lane", "Elm Court", "Fountain Sq", "Grove Ave", "High Pavement", "Ivy Gate", "Jubilee Way", "Kiln Row", "Lime Yard"]
MONTHS4 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]


@family("chat-premise-data", category="chat", lang="text", kind="premise", n=8, mode="answer",
        summary="a claim about a pasted table that the table contradicts (wrong winner, 'rose every month', 'all branches reported', wrong units); the follow-up needs the true figures")
def gen_pdata(rng, n):
    plan = [2, 2, 2, 3, 3, 4, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(200):
            kind = rng.choice({2: ["wrong_top"], 3: ["wrong_top", "all_reported"], 4: ["rose_every", "units"], 5: ["rose_every", "units", "all_reported"]}[d])
            reg = C.register_for(rng)
            if kind == "wrong_top":
                N = rng.randint(6, 9)
                shops = rng.sample(SHOPS, N)
                vals = [rng.randrange(1800, 9800, 10) for _ in shops]
                if len(set(vals)) != N:
                    continue
                order = sorted(range(N), key=lambda j: -vals[j])
                top, second = order[0], order[1]
                wrong = rng.choice([j for j in range(N) if j != top])
                rows = [[j + 1, shops[j], vals[j]] for j in range(N)]
                tbl = C.table(rows, ["#", "shop", "takings_sat"])
                margin = vals[top] - vals[second]
                intro = f"Here are last Saturday's takings by shop. I'm pretty sure {shops[wrong]} (row {wrong + 1}) was our best shop."
                ask = "By how many pounds did the best shop beat the second-best, and which row number is the best shop? Write the row as 'row N'."
                contains = [str(margin), f"row {top + 1}"]
                gold = f"Actually the best was row {top + 1} ({shops[top]}), beating the second by {margin}."
                data = C.block(tbl)
            elif kind == "all_reported":
                N = rng.randint(6, 8)
                shops = rng.sample(SHOPS, N)
                vals = [rng.randrange(1800, 9800, 10) for _ in shops]
                miss = rng.sample(range(N), rng.randint(1, 2))
                rows = [[j + 1, shops[j], "" if j in miss else vals[j]] for j in range(N)]
                tbl = C.table(rows, ["#", "shop", "takings_sat"])
                rep = [vals[j] for j in range(N) if j not in miss]
                avg = Fraction(sum(rep), len(rep))
                intro = f"All {N} shops reported their takings for last Saturday, so I'd like the per-shop average for the board paper."
                ask = "What is the average takings per shop that reported (two decimals), how many shops actually reported, and what is the total?"
                contains = [f"{float(avg):.2f}", str(sum(rep))]
                gold = f"Only {len(rep)} of {N} reported; total {sum(rep)}; average {float(avg):.2f}."
                data = C.block(tbl)
            elif kind == "rose_every":
                ms = MONTHS4[:rng.randint(5, 6)]
                vals = [rng.randrange(3000, 7000, 10)]
                for _ in ms[1:]:
                    vals.append(vals[-1] + rng.randrange(-600, 900, 10))
                ups = [vals[j + 1] - vals[j] for j in range(len(vals) - 1)]
                if all(u > 0 for u in ups) or sum(1 for u in ups if u < 0) != 1:
                    continue
                dropj = next(j for j, u in enumerate(ups) if u < 0)
                rows = [[ms[j], vals[j]] for j in range(len(ms))]
                tbl = C.table(rows, ["month", "orders"])
                intro = f"Orders have gone up every single month this year, haven't they? Here are the figures from the dashboard."
                ask = "Between which two consecutive months was the largest month-on-month change in orders (give it as e.g. 'Feb to Mar'), and by how much did orders change then (a signed number)?"
                big = max(range(len(ups)), key=lambda j: abs(ups[j]))
                if sorted(abs(u) for u in ups)[-1] == sorted(abs(u) for u in ups)[-2]:
                    continue
                sgn = ups[big]
                contains = [f"{ms[big]} to {ms[big + 1]}", str(abs(sgn))]
                gold = f"Not every month rose (it fell {ms[dropj]} to {ms[dropj + 1]}). Largest change: {ms[big]} to {ms[big + 1]}, {sgn:+d}."
                data = C.block(tbl)
            else:  # units
                N = rng.randint(5, 7)
                lots = [f"Lot {chr(65 + j)}" for j in range(N)]
                grams = [rng.randrange(850, 9800, 5) for _ in lots]
                tbl = C.table([[lots[j], grams[j]] for j in range(N)], ["lot", "weight_g"])
                tot_kg = Fraction(sum(grams), 1000)
                heavy = max(grams)
                intro = "This is the weigh-bridge export. The weights are all in kilograms, I believe, so the whole delivery should be a few tonnes."
                ask = "What is the total weight of the delivery in kilograms (three decimals), and what is the heaviest lot's weight in kilograms (three decimals)?"
                contains = [f"{float(tot_kg):.3f}", f"{heavy / 1000:.3f}"]
                gold = f"The column is weight_g (grams): total {float(tot_kg):.3f} kg; heaviest {heavy / 1000:.3f} kg."
                data = C.block(tbl)
            prompt = C.chat(rng, intro, ask, data, reg)
            keep = C.unseen(prompt, contains, True, min_keep=len(contains))
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, d, keep, gold, fold=True, tags=["false-premise", "tables"], notes={"kind": kind})
            break
        else:
            raise RuntimeError("premise-data: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-premise-timeline

SYSTEMS = [("web gateway", "payments worker"), ("api edge", "billing cron"), ("search frontend", "indexer"), ("login service", "mailer")]


@family("chat-premise-timeline", category="chat", lang="text", kind="premise", n=6, mode="answer",
        summary="an incident timeline in two logs with different clocks: the user's 'X happened after Y' is false once offsets and skew are applied")
def gen_ptime(rng, n):
    plan = [3, 4, 4, 5, 4, 3]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(200):
            a_name, b_name = rng.choice(SYSTEMS)
            offs = rng.choice([60, 120, 180, 240])
            skew = rng.choice([0, 3, 4, 7]) if d >= 4 else 0
            base = datetime(2026, rng.randint(1, 12), rng.randint(1, 27), rng.randint(8, 19), rng.randint(0, 59))
            # true UTC times
            t_deploy = base
            gap = rng.randint(4, 23)
            first_err_true = t_deploy - timedelta(minutes=gap)  # the error actually started BEFORE the deploy
            alert_true = first_err_true + timedelta(minutes=rng.randint(1, 3))
            # log A (system A) in UTC: records deploy + alert. Log B in local time (UTC+offs) with a clock that runs `skew` minutes fast, records the first error.
            deploy_a = t_deploy
            err_b_local = first_err_true + timedelta(minutes=offs + skew)
            alert_a = alert_true
            la = [f"{(t_deploy - timedelta(minutes=30)):%H:%M:%S}  INFO  {a_name} healthy", f"{alert_a:%H:%M:%S}  WARN  alert fired: error rate above threshold",
                  f"{deploy_a:%H:%M:%S}  INFO  deploy v2.{rng.randint(10, 40)} started", f"{(deploy_a + timedelta(minutes=2)):%H:%M:%S}  INFO  deploy finished"]
            la.sort()
            lb = [f"{(err_b_local - timedelta(minutes=9)):%H:%M:%S}  INFO  {b_name} idle", f"{err_b_local:%H:%M:%S}  ERROR first failed job: connection refused", f"{(err_b_local + timedelta(minutes=12)):%H:%M:%S}  ERROR 5 jobs failing"]
            sgn = "+" if offs >= 0 else "-"
            off_txt = f"UTC{sgn}{abs(offs) // 60}" + (f":{abs(offs) % 60:02d}" if abs(offs) % 60 else "")
            intro = (f"Post-incident review. Log A is from the {a_name} and is in UTC. Log B is from the {b_name}; its timestamps are in local time ({off_txt})"
                     + (f" and its clock is known to run {skew} minutes fast" if skew else "") + ". "
                     "Our manager's theory is that the deploy caused the failures, because the first failure shows up in log B only after the deploy shows up in log A.")
            data = "Log A (UTC)\n" + "\n".join(la) + "\n\nLog B (local)\n" + "\n".join(lb)
            ask = ("Working it out on a single UTC timeline, how many minutes before or after the deploy start did the first failure in log B happen (give the number of minutes), "
                   "and at what UTC time did that first failure occur (HH:MM:SS)?")
            contains = [f"{first_err_true:%H:%M:%S}", f"{gap}"]
            gold = (f"The first failure was at {first_err_true:%H:%M:%S} UTC, {gap} minutes BEFORE the deploy started at {deploy_a:%H:%M:%S}, so the deploy can't be the cause.")
            prompt = C.chat(rng, intro, ask, C.block(data), C.register_for(rng))
            keep = C.unseen(prompt, contains, True, min_keep=2)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{offs}-{skew}", prompt, d, keep, gold, fold=True, tags=["false-premise", "timelines"], notes={"offset": offs, "skew": skew})
            break
        else:
            raise RuntimeError("premise-timeline: no instance")
