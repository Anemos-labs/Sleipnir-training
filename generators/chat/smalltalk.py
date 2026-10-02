"""Small talk with a checkable question inside it, several questions in one message, and a pasted earlier exchange that contains a slip."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from fractions import Fraction

from fx import family

from . import _common as C
from .calc_time import hm

CHAT_BEFORE = [
    "We finally got the squeaky back door fixed, which felt like a major life achievement.",
    "The new puppy has eaten two phone chargers this week, so I am living dangerously.",
    "It has been one of those grey, drizzly weeks where nobody wants to leave the house.",
    "My neighbour keeps leaving parcels on my porch, which is honestly very kind of him.",
    "I tried sourdough again and it came out like a very dense frisbee.",
    "Work has been a bit of a blur since the reorganisation, but the coffee machine survived.",
    "My sister is visiting and has strong opinions about how I load the dishwasher.",
    "I started learning the ukulele and the cat has started leaving the room whenever I practise.",
    "Honestly I am mostly writing this to procrastinate on the laundry.",
    "The tomatoes on the balcony are finally turning red, I am unreasonably proud of them.",
    "I just got back from a walk and my shoes are soaked, so I am typing with my feet up.",
    "Our team lunch got moved again and I think I am the only one who minds.",
]
CHAT_AFTER = [
    "Anyway, how are you doing?", "Hope your day is calmer than mine.", "Thanks, and sorry for rambling.", "That is all from me, back to the laundry.", "Cheers, and happy Friday if it is Friday where you are.",
    "No pressure, I am in no particular hurry.", "Oh, and the cat says hello.",
]


def _t1_train(rng):
    dep = rng.randint(7 * 60, 20 * 60) + rng.choice([0, 5, 12, 20, 33, 47])
    walk, buf = rng.choice([12, 18, 25]), rng.choice([8, 10, 15])
    q = rng.choice([0, 6, 9])
    leave = dep - walk - buf - q
    qtxt = f" and I want to get a ticket from the machine first, which usually takes {q} minutes" if q else ""
    text = (f"my train goes at {C.hhmm(dep)}, the walk to the station takes me {walk} minutes{qtxt}, and I like a {buf}-minute buffer on the platform. "
            f"What time should I get up and leave the house (HH:MM, 24-hour)?")
    return text, [C.hhmm(leave)], C.hhmm(leave), 1 if not q else 2


def _t2_oven(rng):
    start = rng.randint(14 * 60, 17 * 60) + rng.choice([0, 10, 25, 40])
    cook = rng.choice([55, 70, 85, 100])
    rest = rng.choice([10, 15, 20])
    dinner = start + cook + rest
    text = (f"the roast went into the oven at {C.hhmm(start)} and needs {cook} minutes, then it has to rest for {rest} minutes before carving. "
            f"What time can we sit down to eat (HH:MM) if we carve the moment the rest is over?")
    return text, [C.hhmm(dinner)], C.hhmm(dinner), 2


def _t3_battery(rng):
    start_pct = rng.choice([48, 62, 75, 90])
    rate = rng.choice([6, 8, 9, 12])
    hours = rng.choice([2, 3, 4, 5])
    left = start_pct - rate * hours
    if left <= 5:
        return None
    text = (f"my phone is at {start_pct}% and it loses about {rate} percentage points an hour when I'm using it for maps. "
            f"If I use it like that for {hours} hours, what percentage will be left (just the number)? ")
    return text, [str(left)], f"{left}%", 1


def _t4_tipsplit(rng):
    bill = rng.randrange(6000, 21000, 50)
    ppl = rng.choice([3, 4, 5, 6])
    tip = rng.choice([10, 15, 18, 20])
    total = Fraction(bill) * (100 + tip) / 100
    each = math.ceil(total / ppl / 100) * 100
    text = (f"dinner was {C.money_c(bill)} before the tip, there were {ppl} of us, and we want to leave {tip}%. "
            f"If everyone rounds their share up to the next whole dollar, how much does each person put in (just the dollar amount, like 27.00)?")
    return text, [C.money(each)], C.money(each), 3


def _t5_paint(rng):
    w, l, h = rng.choice([3, 4, 5]), rng.choice([4, 5, 6]), rng.choice([2.4, 2.5, 2.7])
    coats = rng.choice([2, 3])
    cover = rng.choice([10, 12, 13])
    tin = rng.choice([2.5, 5])
    door_win = rng.choice([4, 5, 6])
    area = 2 * (w + l) * h - door_win
    litres = area * coats / cover
    tins = math.ceil(litres / tin)
    text = (f"we're painting the spare room: {w} m by {l} m with {h:g} m ceilings. Four walls only, and the door and windows add up to {door_win} m2 that we won't paint. "
            f"The paint says 1 litre covers {cover} m2 and I want {coats} coats, and it comes in {tin:g}-litre tins. How many tins do I need to buy (a whole number)?")
    return text, [f"{tins} tin"], f"{tins} tins", 3


def _t6_steps(rng):
    goal = rng.choice([8000, 10000, 12000])
    cur = rng.randrange(2500, 6000, 100)
    pace = rng.choice([1200, 1500, 1800, 2000])
    start = rng.choice([13, 14, 15, 16]) * 60
    rem = goal - cur
    mins = math.ceil(rem * 60 / pace)
    t = start + mins
    text = (f"my step goal is {goal} and I'm at {cur} right now, which is {C.hhmm(start)}. If I keep a steady {pace} steps an hour, what time (HH:MM, rounding up to the next whole minute) do I hit the goal? "
            f"And how many steps are left?")
    return text, [C.hhmm(t), str(rem)], f"{C.hhmm(t)}; {rem} steps left", 3


def _t7_rent(rng):
    rent = rng.randrange(180000, 320000, 5000)
    areas = rng.sample([11, 12, 13, 15, 16, 18, 20], 3)
    names = C.pick_names(rng, 3)
    tot = sum(areas)
    shares = [C.cents_half_up(Fraction(rent * a, tot)) for a in areas]
    text = (f"we're splitting rent of {C.money_c(rent)} between {names[0]}, {names[1]} and {names[2]} in proportion to room size: {names[0]} has {areas[0]} m2, {names[1]} has {areas[1]} m2, "
            f"{names[2]} has {areas[2]} m2. What does {names[1]} pay (nearest cent)?")
    return text, [C.money(shares[1])], C.money(shares[1]), 3


def _t8_coffee(rng):
    ml = rng.choice([500, 600, 750, 900, 1000])
    ratio = rng.choice([15, 16, 17])
    scoop = rng.choice([6, 7, 10])
    g = Fraction(ml, ratio)
    scoops = g / scoop
    text = (f"for my pour-over I use 1 gram of coffee per {ratio} ml of water. I'm making {ml} ml today. How many grams of coffee is that (one decimal), "
            f"and how many {scoop} g scoops (one decimal)?")
    return text, [f"{float(g):.1f}", f"{float(scoops):.1f}"], f"{float(g):.1f} g; {float(scoops):.1f} scoops", 3


def _t9_plants(rng):
    plants = rng.randint(6, 18)
    ml = rng.choice([150, 200, 250, 300])
    weeks = rng.choice([4, 6, 8, 10])
    bottle = rng.choice([1.5, 2.0, 5.0])
    total_l = plants * ml * weeks / 1000
    bottles = math.ceil(total_l / bottle)
    text = (f"I'm away for {weeks} weeks and my {plants} plants each need {ml} ml of water per week. How many litres is that altogether (one decimal if needed), "
            f"and how many {bottle:g}-litre bottles do I need to fill (whole bottles)?")
    lit = f"{total_l:g}"
    return text, [lit, f"{bottles}"], f"{lit} L, {bottles} bottles", 3


def _t10_fine(rng):
    rate = rng.choice([15, 20, 25, 30])
    cap = rng.choice([500, 600, 800])
    books = rng.randint(2, 4)
    days = [rng.randint(3, 40) for _ in range(books)]
    fine = sum(min(d * rate, cap) for d in days)
    text = (f"the library charges {rate} cents a day for each overdue book but never more than {C.money_c(cap)} per book. I have {books} books overdue by {', '.join(map(str, days))} days respectively. "
            f"What is my total fine in dollars and cents?")
    return text, [C.money(fine)], C.money(fine), 3


def _t11_movie(rng):
    start = rng.randint(17 * 60, 20 * 60) + rng.choice([0, 15, 30, 45])
    run = rng.randint(95, 170)
    ads = rng.choice([12, 15, 20])
    home = rng.choice([20, 25, 35])
    end = start + ads + run + home
    text = (f"we booked the cinema for {C.hhmm(start)}. The film runs {run} minutes, the adverts and trailers add about {ads} minutes before it starts (so it starts {ads} minutes after the booked time), and the drive home is {home} minutes. "
            f"What time are we home (HH:MM)?")
    return text, [C.hhmm(end)], C.hhmm(end), 2


def _t12_ride(rng):
    dist = rng.choice([36, 45, 52, 64, 80])
    speed = rng.choice([15, 18, 20, 24])
    stops = rng.choice([2, 3, 4])
    stop_len = rng.choice([10, 15, 20])
    start = rng.randint(7, 10) * 60 + rng.choice([0, 15, 30])
    moving = Fraction(dist * 60, speed)
    total = moving + stops * stop_len
    if total.denominator != 1:
        total = math.ceil(total)
    total = int(total)
    arr = start + total
    text = (f"I'm planning a {dist} km ride. I average {speed} km/h while moving, and I'll make {stops} stops of {stop_len} minutes each. If I leave at {C.hhmm(start)}, what time do I get there "
            f"(HH:MM, round the riding time up to a whole minute)?")
    return text, [C.hhmm(arr)], C.hhmm(arr), 3


SCEN_TALK = [_t1_train, _t2_oven, _t3_battery, _t4_tipsplit, _t5_paint, _t6_steps, _t7_rent, _t8_coffee, _t9_plants, _t10_fine, _t11_movie, _t12_ride]


@family("chat-smalltalk-embedded", category="chat", lang="text", kind="lookup", n=14, mode="answer",
        summary="friendly chit-chat with one real calculation buried in it (when to leave, tins of paint, rent shares, riding time); distractor details at higher levels")
def gen_talk(rng, n):
    for i in range(n):
        for _attempt in range(100):
            fn = SCEN_TALK[(i + _attempt) % len(SCEN_TALK)] if False else SCEN_TALK[i % len(SCEN_TALK)]
            r = fn(rng)
            if r is None:
                continue
            text, contains, gold, d = r
            reg = rng.choice(["chatty", "rambling", "chatty", "hurried", "formal"])
            before = " ".join(rng.sample(CHAT_BEFORE, rng.randint(1, 2)))
            after = rng.choice(CHAT_AFTER)
            distract = ""
            if d >= 3 and rng.random() < 0.6:
                distract = rng.choice([" (Not that it matters, but the last time I did something like this I got it wrong by 17.)", " (The neighbour has 3 cats and none of this has anything to do with them.)",
                                       " (Also my birthday is on the 14th, irrelevant here.)", " (I have 2 spare notebooks nearby if that changes anything, which it probably doesn't.)"])
                d = min(5, d + 1)
            q = text[0].upper() + text[1:] if reg == "formal" else text
            prompt_body = f"{before} {q}{distract} {after}"
            op = rng.choice(["Hi!", "Hello!", "Hey you!", "Hi there!"]) if reg != "hurried" else rng.choice(["hey.", "hi."])
            prompt = f"{op} {C.prose(rng, before, reg)} {C.prose(rng, q, reg) if reg != 'formal' else q}{distract} {after}"
            keep = C.unseen(prompt, contains, True, min_keep=len(contains))
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{fn.__name__.split('_', 2)[2]}", prompt, d, keep, gold, fold=True, tags=["small-talk", "embedded-question"], notes={"scenario": fn.__name__})
            break
        else:
            raise RuntimeError("talk: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-multi-ask: several different questions in one message


def _q_date(rng):
    start = date(rng.randint(2026, 2028), rng.randint(1, 12), rng.randint(1, 28))
    k = rng.randint(30, 140)
    end = start + timedelta(days=k)
    return (f"What date is {k} days after {start.day} {C.MONTHS[start.month - 1]} {start.year}? (YYYY-MM-DD)", [C.iso(end)], C.iso(end))


def _q_conv(rng):
    mi = rng.choice([3.1, 6.2, 10, 13.1, 26.2])
    km = Fraction(str(mi)) * Fraction(1609344, 1000000)
    return (f"How many kilometres is {mi:g} miles (1 mile = 1.609344 km, one decimal)?", [f"{float(km):.1f}"], f"{float(km):.1f}")


def _q_pct(rng):
    price = rng.choice([48, 64, 80, 120, 250])
    disc = rng.choice([15, 20, 25, 35])
    fin = Fraction(price * (100 - disc), 100)
    return (f"What is the price after a {disc}% discount on {price} dollars (two decimals)?", [f"{float(fin):.2f}"], f"{float(fin):.2f}")


def _q_time(rng):
    a = rng.randint(6, 11) * 60 + rng.randrange(0, 60, 5)
    b = a + rng.randrange(95, 400, 5)
    return (f"How long is it from {C.hhmm(a)} to {C.hhmm(b)} (H:MM)?", [hm(b - a)], hm(b - a))


def _q_avg(rng):
    xs = [rng.randint(10, 60) for _ in range(rng.randint(4, 6))]
    av = Fraction(sum(xs), len(xs))
    return (f"What is the average of {', '.join(map(str, xs))} (two decimals)?", [f"{float(av):.2f}"], f"{float(av):.2f}")


def _q_wd(rng):
    d0 = date(rng.randint(2026, 2029), rng.randint(1, 12), rng.randint(1, 28))
    return (f"What weekday is {d0.day} {C.MONTHS[d0.month - 1]} {d0.year}?", [C.wd(d0)], C.wd(d0))


def _q_sum(rng):
    xs = [rng.randrange(1000, 9999, 7) for _ in range(rng.randint(3, 4))]
    return (f"What is {' + '.join(map(str, xs))}?", [str(sum(xs))], str(sum(xs)))


def _q_rem(rng):
    a, b = rng.randint(200, 900), rng.randint(7, 19)
    return (f"What is the remainder when {a} is divided by {b}, and what is the whole-number quotient? (Write as 'q r'.)", [f"{a // b} {a % b}"], f"{a // b} {a % b}")


MULTI_Q = [_q_date, _q_conv, _q_pct, _q_time, _q_avg, _q_wd, _q_sum, _q_rem]


@family("chat-multi-ask", category="chat", lang="text", kind="lookup", n=10, mode="answer",
        summary="one chatty message with three to five unrelated small questions (dates, conversions, percentages, durations, averages); every answer is checked")
def gen_multi(rng, n):
    plan = [3, 3, 3, 4, 4, 4, 5, 5, 3, 4]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            k = {3: 3, 4: 4, 5: 5}[d]
            fns = rng.sample(MULTI_Q, k)
            parts = [f(rng) for f in fns]
            contains = [c for p in parts for c in p[1]]
            golds = [p[2] for p in parts]
            if len(set(contains)) != len(contains):
                continue
            reg = C.register_for(rng)
            style = rng.choice(["numbered", "inline"])
            if style == "numbered":
                qs = "\n".join(f"{j + 1}) {p[0]}" for j, p in enumerate(parts))
            else:
                qs = " ".join(f"({j + 1}) {p[0]}" for j, p in enumerate(parts))
            intro = rng.choice(["I have a pile of small questions that have been bugging me all day and I would love to clear them in one go.", "batch of quick ones, answer each please",
                                "My brain is mush and these are all separate things I need for different documents."])
            ask = "Please answer all of them, numbered the same way, one short line each." if style == "numbered" else "Please answer all of them, numbered the same way."
            prompt = C.chat(rng, intro, ask, qs, reg, data_after_ask=False)
            keep = C.unseen(prompt, contains, True, min_keep=len(contains))
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{k}q-{style}", prompt, d, keep, "; ".join(golds), fold=True, tags=["multi-question"], notes={"questions": [f.__name__ for f in fns]})
            break
        else:
            raise RuntimeError("multi: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-earlier-mistake


def _slip(rng, v):
    """A plausible wrong value for an integer v."""
    return v + rng.choice([-10, 10, -1, 1, 100, -100, 2, -2])


def _e1_stock(rng):
    boxes, per = rng.randint(3, 6), rng.choice([12, 18, 24])
    sold = rng.randint(11, 29)
    total = boxes * per
    left = total - sold
    wrong = _slip(rng, left)
    price = rng.choice([475, 650, 825, 1100])
    val = left * price
    u1 = f"I have {boxes} boxes of {per} mugs and sold {sold} mugs on Saturday. How many mugs are left?"
    a1 = f"{boxes} boxes x {per} = {total} mugs. {total} - {sold} = {wrong}. So you have {wrong} mugs left."
    u2 = f"Great. Each mug is valued at {C.money_c(price)} on the insurance form. What is the stock value of the mugs that are left, and how many mugs is that again?"
    return u1, a1, u2, [str(left), C.money(val)], f"{left} mugs; stock value {C.money(val)}", 4


def _e2_fuel(rng):
    km = rng.choice([240, 320, 410, 520])
    cons = rng.choice([5.5, 6.5, 7.5, 8.0])
    price = rng.choice([149, 159, 172, 181])  # cents per litre
    litres = Fraction(str(cons)) * km / 100
    wrong_l = litres * 10 if rng.random() < 0.4 else litres + rng.choice([-6, 6, 10, -10])
    ppl = rng.choice([3, 4])
    cost = Fraction(litres) * price
    cost_c = C.cents_half_up(cost)
    each = C.cents_half_up(Fraction(cost_c, ppl))
    u1 = f"My car uses {cons:g} litres per 100 km and the trip is {km} km. How many litres will I use?"
    a1 = f"{km} km is {km} / 100 = {km / 100:g} hundred-km units, and {km / 100:g} x {cons:g} = {float(wrong_l):g} litres."
    u2 = f"Fuel is {C.money_c(price)} per litre. What will the fuel cost in total (nearest cent), and what does each of the {ppl} passengers pay if we split it evenly (nearest cent)? Also how many litres, please."
    return u1, a1, u2, [f"{float(litres):g}", C.money(cost_c), C.money(each)], f"{float(litres):g} L; total {C.money(cost_c)}; each {C.money(each)}", 4


def _e3_hours(rng):
    h = [rng.randint(3, 9) for _ in range(rng.randint(4, 5))]
    m = [rng.choice([0, 15, 30, 45]) for _ in h]
    tot = sum(a * 60 + b for a, b in zip(h, m))
    wrong_tot = tot + rng.choice([-30, 30, -60, 60, 45, -45])
    rate = rng.choice([1450, 1600, 1875, 2200])
    pay = C.cents_half_up(Fraction(tot * rate, 60))
    u1 = "I worked these shifts: " + ", ".join(f"{a}h{b:02d}" for a, b in zip(h, m)) + ". What is the total time?"
    a1 = f"Adding them up gives {hm(wrong_tot)} in total."
    u2 = f"I'm paid {C.money_c(rate)} an hour, pro rata by the minute. What is my pay for that total (nearest cent), and what is the true total time again (H:MM)?"
    return u1, a1, u2, [hm(tot), C.money(pay)], f"{hm(tot)}; pay {C.money(pay)}", 4


def _e4_date(rng):
    start = date(rng.randint(2026, 2028), rng.randint(1, 11), rng.randint(2, 27))
    k = rng.randint(40, 120)
    true = start + timedelta(days=k)
    wrong = true + timedelta(days=rng.choice([-1, 1, 2, -2]))
    due = true - timedelta(days=7)
    u1 = f"An invoice is dated {start.day} {C.MONTHS[start.month - 1]} {start.year} with payment terms of {k} days. What is the payment deadline date?"
    a1 = f"{k} days after {start.day} {C.MONTHS[start.month - 1]} is {wrong.day} {C.MONTHS[wrong.month - 1]} {wrong.year}."
    u2 = "Thanks. We always pay a week before the deadline. On what date (YYYY-MM-DD) do we pay, and what is the real deadline in the same format?"
    return u1, a1, u2, [C.iso(due), C.iso(true)], f"pay on {C.iso(due)}; deadline {C.iso(true)}", 4


def _e5_scale(rng):
    flour = rng.choice([200, 250, 300, 350])
    f_from, f_to = rng.choice([(4, 6), (4, 10), (6, 9), (8, 12)])
    true = Fraction(flour * f_to, f_from)
    if true.denominator != 1:
        return None
    true = int(true)
    wrong = true + rng.choice([-20, 20, -25, 25, 30])
    butter_pct = rng.choice([40, 50, 60])
    butter = Fraction(true * butter_pct, 100)
    if butter.denominator != 1:
        return None
    u1 = f"My recipe uses {flour} g flour for {f_from} people. How much flour for {f_to} people?"
    a1 = f"Scale factor {f_to}/{f_from} = {f_to / f_from:g}. {flour} x {f_to / f_from:g} = {wrong} g of flour."
    u2 = f"Perfect. The butter should be {butter_pct}% of the flour weight. How many grams of butter is that for the bigger batch, and how much flour is it again?"
    return u1, a1, u2, [str(int(butter)), str(true)], f"{true} g flour; {int(butter)} g butter", 4


def _e6_area(rng):
    w, l = rng.choice([3, 4, 5]), rng.choice([6, 7, 8])
    area = w * l
    wrong = area + rng.choice([-2, 2, 3, -3, 4])
    tile = rng.choice([25, 30, 40])  # cm
    n_tiles = math.ceil(Fraction(area * 10000, tile * tile))
    u1 = f"A room is {w} m by {l} m. What's the floor area?"
    a1 = f"{w} x {l} = {wrong} square metres."
    u2 = f"We're tiling it with {tile} cm x {tile} cm tiles, no waste allowance. How many tiles (round up) do we need, and what is the floor area again?"
    return u1, a1, u2, [str(n_tiles), f"{area}"], f"area {area} m2; {n_tiles} tiles", 4


SCEN_E = [_e1_stock, _e2_fuel, _e3_hours, _e4_date, _e5_scale, _e6_area]


@family("chat-earlier-mistake", category="chat", lang="text", kind="premise", n=12, mode="answer",
        summary="a pasted earlier exchange contains an arithmetic slip by the assistant; the follow-up builds on it, so the answer must use the corrected figure")
def gen_earlier(rng, n):
    plan = [4, 4, 4, 4, 5, 5, 4, 5, 4, 4, 5, 4]
    for i in range(n):
        for _attempt in range(100):
            fn = SCEN_E[i % len(SCEN_E)]
            r = fn(rng)
            if r is None:
                continue
            u1, a1, u2, contains, gold, d = r
            d = plan[i % len(plan)]
            reg = C.register_for(rng)
            transcript = f"Me: {u1}\n\nYou: {a1}\n\nMe: {u2}"
            intro = rng.choice(["Continuing from earlier. I'm pasting the conversation so you have the context, then my follow-up is at the end.",
                                "Here's what we said earlier today, followed by my next question.", "(pasting our chat from this morning so you can pick it up)"])
            prompt = C.chat(rng, intro, "", C.block(transcript), reg) if False else (f"{intro}\n\n```\n{transcript}\n```\n\n" + rng.choice(["Please answer the last question in that chat.", "Can you answer my last message in there?", "Go ahead with the follow-up at the end."]))
            if d == 5:
                prompt += " Be careful, I'm putting these numbers on a form."
            keep = C.unseen(prompt, contains, True, min_keep=len(contains))
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{fn.__name__.split('_', 2)[2]}", prompt, d, keep, gold, fold=True, tags=["false-premise", "earlier-turn"], notes={"scenario": fn.__name__})
            break
        else:
            raise RuntimeError("earlier: no instance")
