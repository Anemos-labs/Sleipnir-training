"""File-delivered constrained writing (emails, SMS, summaries, commit messages, posters, plain-English rewrites).
The agent writes reply.md; a hidden checker verifies structure and facts only (no judgement of style). Each task's gold reply is
built by the generator and run through the same checker before it is written out."""
from __future__ import annotations

import re
from datetime import date, timedelta

from fx import Task, family

from . import _checker as K
from . import _common as C
from . import _forms as F

SAVE = [
    "Please save the finished text as reply.md in this folder.",
    "Put your final version in reply.md (just the text itself).",
    "Write it into reply.md; I'll copy it from there.",
    "The result should end up in reply.md.",
]


def _alnum_words(text: str) -> int:
    return len([t for t in text.split() if re.search(r"[A-Za-z0-9]", t)])


def _start_notes(rng, extra: dict | None = None) -> dict:
    d = {"notes.txt": "Scratch notes. Nothing needed here.\n"}
    if extra:
        d.update(extra)
    return d


# --------------------------------------------------------------------------------------------------------------------
# chat-write-email


def _sc_rent(rng, sender):
    ll = rng.choice(["Ms Okonkwo", "Mr Halloran", "Mrs Varga", "Mr Castellano"])
    amt = rng.randrange(80000, 220000, 2500)
    d = date(2026, rng.randint(1, 11), rng.randint(2, 26))
    flat = f"Flat {rng.randint(2, 48)}{rng.choice('ABC')}"
    sit = f"My rent ({C.money_c(amt)} for {flat}) is going to be a few days late because a client's invoice is stuck. I'll definitely transfer it on {d.day} {C.MONTHS[d.month - 1]}. The email is to my landlord, {ll}."
    return dict(situation=sit, recipient=ll, facts=[F.money_re(amt), F.date_re(d), F.word_re(flat)], display=[C.money_c(amt), f"{d.day} {C.MONTHS[d.month - 1]}", flat],
                fact_sents=[f"The rent of {C.money_c(amt)} for {flat} will reach you on {d.day} {C.MONTHS[d.month - 1]}.", f"I will make the transfer myself on {d.day} {C.MONTHS[d.month - 1]}.", f"This applies to {flat} only."][:3],
                opening="I am writing about this month's rent.", closing="Thank you for your patience and for being understanding.", subject=f"Rent payment for {flat}",
                fillers=["I have never missed a payment before.", "Please let me know if you need anything else from me.", "I will send the confirmation as soon as it is done."])


def _sc_refund(rng, sender):
    shop = rng.choice(["Customer Care team", "Orders desk", "Returns department"])
    item = rng.choice(["kettle", "desk lamp", "blender", "air fryer", "hairdryer"])
    order = f"ORD-{rng.randint(10000, 99999)}"
    price = rng.randrange(2999, 15999, 100)
    d = date(2026, rng.randint(1, 10), rng.randint(2, 26))
    sit = f"The {item} I bought on {d.day} {C.MONTHS[d.month - 1]} (order {order}, {C.money_c(price)}) stopped working after a week. I want a full refund, not a replacement. I'm emailing the {shop}."
    return dict(situation=sit, recipient=shop, facts=[F.word_re(order), F.money_re(price), F.date_re(d)], display=[order, C.money_c(price), f"{d.day} {C.MONTHS[d.month - 1]}"],
                fact_sents=[f"My order number is {order}.", f"I paid {C.money_c(price)} for the {item}.", f"I bought it on {d.day} {C.MONTHS[d.month - 1]}."],
                opening=f"The {item} I ordered has stopped working and I would like a full refund.", closing="Please confirm by email once the refund has been issued.", subject=f"Refund request for order {order}",
                fillers=["I would prefer a refund to a replacement.", "I am happy to return the item if you send a label.", "I have kept the packaging."])


def _sc_swap(rng, sender):
    col = rng.choice(C.FIRST)
    d1 = date(2026, rng.randint(1, 11), rng.randint(2, 26))
    d2 = d1 + timedelta(days=rng.randint(3, 12))
    st = rng.choice([8, 9, 10, 13, 14]) * 60 + rng.choice([0, 30])
    sit = f"I can't make my shift on {C.wd(d1)} {d1.day} {C.MONTHS[d1.month - 1]}, which starts at {C.hhmm(st)}. I'd like {col} to cover it, and I'll take their shift on {d2.day} {C.MONTHS[d2.month - 1]} in return. Write to {col}."
    return dict(situation=sit, recipient=col, facts=[F.date_re(d1), F.time_re(st), F.date_re(d2)], display=[f"{d1.day} {C.MONTHS[d1.month - 1]}", C.hhmm(st), f"{d2.day} {C.MONTHS[d2.month - 1]}"],
                fact_sents=[f"Could you cover my shift on {d1.day} {C.MONTHS[d1.month - 1]}?", f"It starts at {C.hhmm(st)}.", f"In return I will take your shift on {d2.day} {C.MONTHS[d2.month - 1]}."],
                opening="I have a favour to ask about the rota.", closing="Let me know whether that works for you, and I will tell the manager.", subject=f"Shift swap on {d1.day} {C.MONTHS[d1.month - 1]}",
                fillers=["I would not ask if it were not important.", "I have already checked that it does not clash with your hours.", "I am happy to swap in either direction."])


def _sc_decline(rng, sender):
    host = rng.choice(C.FIRST)
    ev = rng.choice(["housewarming", "book launch", "birthday supper", "garden party"])
    d1 = date(2026, rng.randint(1, 11), rng.randint(2, 26))
    d2 = d1 + timedelta(days=rng.randint(6, 20))
    st = rng.choice([17, 18, 19]) * 60
    sit = f"{host} invited me to a {ev} on {d1.day} {C.MONTHS[d1.month - 1]} at {C.hhmm(st)}, but I can't go. I'd love to meet up on {d2.day} {C.MONTHS[d2.month - 1]} instead. Reply to {host}."
    return dict(situation=sit, recipient=host, facts=[F.date_re(d1), F.date_re(d2), F.time_re(st)], display=[f"{d1.day} {C.MONTHS[d1.month - 1]}", f"{d2.day} {C.MONTHS[d2.month - 1]}", C.hhmm(st)],
                fact_sents=[f"I cannot come to the {ev} on {d1.day} {C.MONTHS[d1.month - 1]}.", f"The {C.hhmm(st)} start is the part that does not work for me.", f"Could we meet on {d2.day} {C.MONTHS[d2.month - 1]} instead?"],
                opening="Thank you so much for the invitation.", closing="I hope it goes brilliantly and I would love to hear all about it.", subject=f"Re: your {ev}",
                fillers=["It sounds like a lovely evening.", "I will bring something if we do meet up.", "Please say hello to everyone from me."])


def _sc_status(rng, sender):
    mgr = rng.choice(C.FIRST)
    proj = rng.choice(["the billing migration", "the new intranet", "the warehouse labelling project", "the onboarding revamp"])
    d = date(2026, rng.randint(1, 11), rng.randint(2, 26))
    done, nxt, block = rng.choice([("the data export is finished", "start the import tests", "we are waiting for test credentials"),
                                    ("the first three pages are signed off", "build the order form", "we are waiting for the final logo"),
                                    ("all label templates are printed", "pilot them on aisle nine", "we are waiting for the new scanner firmware")])
    sit = (f"I need to update my manager {mgr} on {proj}. Done: {done}. Next: {nxt}. Blocked: {block}. I'll send the next update on {d.day} {C.MONTHS[d.month - 1]}.")
    return dict(situation=sit, recipient=mgr, facts=[F.date_re(d), F.word_re(done.split()[-1]), F.word_re(block.split()[-1])], display=[f"{d.day} {C.MONTHS[d.month - 1]}", done.split()[-1], block.split()[-1]],
                fact_sents=[f"Done: {done}.", f"Next: {nxt}.", f"Blocked: {block}."], opening=f"Here is the current status of {proj}.", closing=f"I will send the next update on {d.day} {C.MONTHS[d.month - 1]}.",
                subject=f"Status update: {proj.replace('the ', '')}", fillers=["Nothing else is at risk at the moment.", "Happy to talk it through if that is easier."], extra_facts=[F.date_re(d)])


def _sc_repair(rng, sender):
    ll = rng.choice(["Ms Okonkwo", "Mr Halloran", "Mrs Varga"])
    app = rng.choice(["boiler", "oven", "washing machine", "front door lock"])
    d = date(2026, rng.randint(1, 11), rng.randint(2, 26))
    a, b = rng.choice([(9, 12), (13, 17), (10, 14)])
    flat = f"flat {rng.randint(2, 40)}"
    sit = f"The {app} in {flat} has been broken since {d.day} {C.MONTHS[d.month - 1]}. I'm home between {a}:00 and {b}:00 on weekdays and want someone to come then. Write to the landlord, {ll}."
    return dict(situation=sit, recipient=ll, facts=[F.word_re(app), F.date_re(d), F.time_re(a * 60)], display=[app, f"{d.day} {C.MONTHS[d.month - 1]}", f"{a}:00"],
                fact_sents=[f"The {app} in {flat} has not worked since {d.day} {C.MONTHS[d.month - 1]}.", f"I am home from {a}:00 until {b}:00 on weekdays.", "Could you arrange for someone to visit in that window?"],
                opening="I am writing to report a repair that is needed.", closing="Please confirm the appointment by email.", subject=f"Repair needed: {app}",
                fillers=["It is affecting my daily routine.", "I have photos available if they would help."])


def _sc_thanks(rng, sender):
    nb = rng.choice(C.FIRST)
    n = rng.randint(5, 14)
    d1 = date(2026, rng.randint(1, 9), rng.randint(2, 20))
    d2 = d1 + timedelta(days=rng.randint(9, 20))
    sit = f"My neighbour {nb} watered my {n} plants while I was away from {d1.day} {C.MONTHS[d1.month - 1]} to {d2.day} {C.MONTHS[d2.month - 1]}, and not one died. I want to thank {nb} and offer them a jar of my plum jam."
    return dict(situation=sit, recipient=nb, facts=[F.num_re(n), F.date_re(d1), F.date_re(d2)], display=[str(n), f"{d1.day} {C.MONTHS[d1.month - 1]}", f"{d2.day} {C.MONTHS[d2.month - 1]}"],
                fact_sents=[f"You looked after all {n} of my plants.", f"I was away from {d1.day} {C.MONTHS[d1.month - 1]}.", f"I came back on {d2.day} {C.MONTHS[d2.month - 1]} to a jungle that was still alive."],
                opening="I wanted to say a proper thank you.", closing="I would like to drop off a jar of plum jam as a small thank-you.", subject="Thank you for the plants",
                fillers=["Every single one of them survived.", "I could not have done it without you."])


def _sc_intro(rng, sender):
    a, b = rng.sample(C.FIRST, 2)
    recipient = a
    topic = rng.choice(["community gardening grants", "open-source licensing", "running a small bakery", "setting up a repair café"])
    d = date(2026, rng.randint(1, 11), rng.randint(2, 20))
    sit = f"I'd like to introduce {a} to {b}, who knows a lot about {topic}. They should meet up during the week of {d.day} {C.MONTHS[d.month - 1]}. The email goes to {a}, with {b} copied in."
    return dict(situation=sit, recipient=a, facts=[F.word_re(b), F.word_re(topic.split()[0]), F.date_re(d)], display=[b, topic, f"{d.day} {C.MONTHS[d.month - 1]}"],
                fact_sents=[f"I would like you to meet {b}.", f"{b} knows a great deal about {topic}.", f"The week of {d.day} {C.MONTHS[d.month - 1]} could be a good time."],
                opening="I think the two of you should know each other.", closing="I will leave it to you to find a time that suits you both.", subject=f"Introduction: {a} and {b}",
                fillers=["I am sure you will get along.", "Please do keep me posted."])


EMAIL_SCEN = [_sc_rent, _sc_refund, _sc_swap, _sc_decline, _sc_status, _sc_repair, _sc_thanks, _sc_intro]
FORBID_POOL = [("sorry", "sorry"), ("apologies", "apologies"), ("unfortunately", "unfortunately"), ("urgent", "urgent"), ("asap", "ASAP"), ("kindly", "kindly"), ("hope you are well", "hope you are well")]
SIGNS = ["Thanks", "Best", "Regards", "Cheers"]


@family("chat-write-email", category="chat", lang="text", kind="greenfield", n=16, summary="draft an email from a described situation under a set of structural constraints (length, subject line, facts, forbidden words, sign-off, bullets)")
def gen_email(rng, n):
    plan = [1, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 2, 3, 4, 3, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        sender = rng.choice(C.FIRST)
        sc = EMAIL_SCEN[i % len(EMAIL_SCEN)](rng, sender)
        while sender == sc["recipient"]:
            sender = rng.choice(C.FIRST)
        facts = sc["facts"]
        rules, phr = [], []
        cons = {}
        # constraint selection by difficulty
        use_subject = d >= 3 or rng.random() < 0.3
        use_forbid = d >= 2
        use_sign = d >= 3
        use_bullets = d >= 4 and sc["recipient"] and len(sc["fact_sents"]) >= 3 and rng.random() < 0.7
        use_noexc = d >= 4 or rng.random() < 0.25
        use_two_par = d >= 4 and not use_bullets
        word_cap = {1: rng.choice([120, 150]), 2: rng.choice([100, 120]), 3: rng.choice([90, 110]), 4: rng.choice([80, 100]), 5: 70}[d]
        lo = 40 if d >= 5 else None
        # build gold first to see what fits
        forb = rng.sample(FORBID_POOL, 2 if d <= 3 else 3) if use_forbid else []
        signw = rng.choice(SIGNS)
        greet = rng.choice(["Hi", "Dear", "Hello"])
        lines = []
        if use_subject:
            lines.append(f"Subject: {sc['subject']}")
        lines.append(f"{greet} {sc['recipient']},")
        lines.append("")
        facts_s = sc["fact_sents"][:3]
        if use_bullets:
            lines.append(sc["opening"])
            lines.append("")
            lines.extend(f"- {s}" for s in facts_s)
        else:
            lines.append(" ".join([sc["opening"]] + facts_s))
        lines.append("")
        closing = sc["closing"]
        lines.append(closing)
        lines.append("")
        lines.append(f"{signw}, {sender}" if use_sign else sender)
        gold = "\n".join(lines) + "\n"
        # pad with fillers to reach a minimum when requested
        k = 0
        while lo is not None and _alnum_words("\n".join(l for l in lines if not l.startswith("Subject:"))) < lo + 5 and k < len(sc["fillers"]):
            lines.insert(len(lines) - 3, sc["fillers"][k])
            k += 1
        gold = "\n".join(lines) + "\n"
        body_words = _alnum_words("\n".join(l for l in lines if not l.startswith("Subject:")))
        if body_words > word_cap:
            word_cap = ((body_words + 14) // 10) * 10 + 10
        skip = "^Subject:"
        rules.append({"t": "max_words", "n": word_cap, "skip_prefix": skip})
        phr.append(rng.choice([f"keep it under {word_cap} words (the subject line does not count)" if use_subject else f"keep it under {word_cap} words",
                               f"no more than {word_cap} words" + (" in the body" if use_subject else ""), f"at most {word_cap} words" + (", not counting the subject line" if use_subject else "")]))
        if lo is not None:
            rules.append({"t": "min_words", "n": lo, "skip_prefix": skip})
            phr.append(f"but not shorter than {lo} words")
        for fx_ in facts:
            rules.append({"t": "include", "any": [fx_], "label": "a required fact"})
        if use_subject:
            rules.append({"t": "first_line", "re": r"^Subject:\s+(?:\S+\s+){1,8}\S+$", "label": "Subject line of 2 to 9 words"})
            phr.append(rng.choice(["start with a subject line written as 'Subject: ...' that is between two and nine words", "the very first line must be a subject line ('Subject: ' followed by two to nine words)"]))
        if forb:
            rules.append({"t": "exclude", "words": [w for w, _ in forb]})
            phr.append("never use the words " + ", ".join(f"'{dsp}'" for _, dsp in forb))
        if use_sign:
            rules.append({"t": "last_line", "re": rf"^{signw},\s*{re.escape(sender)}$", "label": "sign-off"})
            phr.append(f"end with a last line that reads exactly '{signw}, {sender}'")
        else:
            rules.append({"t": "last_line", "re": rf"{re.escape(sender)}\s*$", "label": "ends with sender name"})
            phr.append(f"finish with my name, {sender}, on the last line")
        rules.append({"t": "first_line" if not use_subject else "include", **({"re": rf"^{greet} {re.escape(sc['recipient'])},?\s*$", "label": "greeting"} if not use_subject else {"any": [rf"re:^{greet} {re.escape(sc['recipient'])},?\s*$"], "label": "greeting"})})
        phr.append(rng.choice([f"open with the greeting '{greet} {sc['recipient']},' on its own line", f"greet {sc['recipient']} with '{greet} {sc['recipient']},' as a separate line"]))
        if use_noexc:
            rules.append({"t": "exclude", "words": ["re:!"]})
            phr.append("no exclamation marks anywhere")
        if use_bullets:
            rules.append({"t": "bullets", "min": 3, "max": 3})
            phr.append("put the three key details as exactly three bullet points (each line starting with '- ')")
        elif use_two_par:
            rules.append({"t": "paragraphs", "min": 3, "max": 6})
        K.assert_passes(rules, gold, what=f"email {i}")
        prompt_phr = "; ".join(phr[:-1]) + "; and " + phr[-1] if len(phr) > 1 else phr[0]
        facts_line = "It should mention " + ", ".join(sc["display"][:-1]) + f" and {sc['display'][-1]}." if len(sc["display"]) > 1 else ""
        reg = C.register_for(rng)
        intro = f"{sc['situation']} My name is {sender}."
        spec = f"{facts_line} Requirements: {prompt_phr}."
        prompt = C.chat(rng, intro, rng.choice(SAVE), None, reg, spec=spec)
        yield Task(slug=f"{i + 1:02d}-{sc['subject'].split()[0].lower().strip(':')}-d{d}", prompt=prompt, difficulty=d, start=_start_notes(rng),
                   hidden=K.check_files(rules), solution={"reply.md": gold}, verify=K.VERIFY, kind="greenfield", tags=["writing", "constraints", "email"], notes={"scenario": EMAIL_SCEN[i % len(EMAIL_SCEN)].__name__})


# --------------------------------------------------------------------------------------------------------------------
# chat-write-sms

SMS_SCEN = [
    ("meet", "Can we meet at {place} at {time} on {date}? I'll be by the {landmark}.", ["place", "time", "date"]),
    ("keys", "The spare keys are under the {landmark} planter. Please collect them at {time} on {date}.", ["time", "date"]),
    ("late", "Running late for {place}. I should arrive around {time}, so please start without me.", ["place", "time"]),
    ("cancel", "I have to cancel our {thing} on {date}. Can we rebook for {date2} at {time}?", ["date", "date2", "time"]),
    ("bring", "Please bring the {thing} to {place} by {time} on {date}. Booking ref {code}.", ["thing", "place", "time", "date", "code"]),
]
PLACES = ["Cafe Orchid", "the Mill Street library", "Platform 2", "the north gate", "Rowan Park bandstand", "the bike shop"]
LANDMARKS = ["red", "fountain", "blue", "clock", "stone"]
THINGS_SMS = ["tent", "folding table", "camera", "cake tin", "tool bag", "dentist appointment"]


@family("chat-write-sms", category="chat", lang="text", kind="greenfield", n=12, summary="a text message with a hard character limit, required details, a name and a sign-off")
def gen_sms(rng, n):
    plan = [1, 2, 2, 3, 3, 4, 4, 5, 2, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        key, tpl, need = SMS_SCEN[i % len(SMS_SCEN)]
        rcpt = rng.choice(C.FIRST)
        sender = rng.choice([x for x in C.FIRST if x != rcpt])
        place = rng.choice(PLACES)
        t = rng.choice([8, 9, 10, 12, 14, 16, 18]) * 60 + rng.choice([0, 15, 30, 45])
        dt = date(2026, rng.randint(1, 11), rng.randint(2, 26))
        dt2 = dt + timedelta(days=rng.randint(2, 9))
        code = f"{rng.choice('KLMNP')}{rng.randint(100, 999)}"
        thing = rng.choice(THINGS_SMS if key == "cancel" else THINGS_SMS[:5])
        vals = {"place": place, "time": C.hhmm(t), "date": f"{dt.day} {C.MONTHS[dt.month - 1][:3]}", "date2": f"{dt2.day} {C.MONTHS[dt2.month - 1][:3]}", "landmark": rng.choice(LANDMARKS), "thing": thing, "code": code}
        msg = tpl.format(**vals)
        gold = f"{rcpt}, {msg} {sender[0]}."
        qm = d >= 3
        if qm and "?" not in gold:
            gold = gold.replace(".", "?", 1) if False else gold
        limit = max(len(gold) + rng.choice([4, 12, 25, 40]), 60)
        if d >= 4:
            limit = len(gold) + rng.choice([2, 5, 8])
        limit = (limit + 4) // 5 * 5
        if limit < len(gold):
            limit = len(gold)
        rules = [{"t": "max_chars", "n": limit}, {"t": "first_line", "re": rf"^{rcpt},", "label": "starts with the name"}, {"t": "last_line", "re": rf"\b{sender[0]}\.?$", "label": "ends with initial"},
                 {"t": "exclude", "words": ["re:[\\U0001F300-\\U0001FAFF\\u2600-\\u27BF]", "re:\\bu\\b", "re:\\bur\\b"]}, {"t": "lines", "max": 2}]
        facts_re = {"place": F.word_re(place) if True else "", "time": F.time_re(t), "date": F.date_re(dt), "date2": F.date_re(dt2), "code": F.word_re(code), "thing": F.word_re(thing)}
        for nd in need:
            if nd in facts_re:
                rules.append({"t": "include", "any": [facts_re[nd]], "label": nd})
        disp = {"place": place, "time": C.hhmm(t), "date": f"{dt.day} {C.MONTHS[dt.month - 1]}", "date2": f"{dt2.day} {C.MONTHS[dt2.month - 1]}", "code": code, "thing": thing}
        K.assert_passes(rules, gold, what=f"sms {i}")
        need_txt = ", ".join(disp[x] for x in need if x in disp)
        situ = {"meet": f"I need to text {rcpt} to arrange meeting up", "keys": f"I'm texting {rcpt} about my spare keys", "late": f"I'm going to be late and need to text {rcpt}",
                "cancel": f"I have to cancel something with {rcpt} and suggest another time", "bring": f"I'm texting {rcpt} to ask them to bring something"}[key]
        extra = ""
        if d >= 3:
            extra = " No emoji, and no text-speak like 'u' or 'ur'."
        if d >= 4:
            extra += f" Start the message with '{rcpt},' and finish with my initial, {sender[0]}."
        else:
            extra += f" Address it to {rcpt} by name at the start, and sign it with my initial, {sender[0]}."
        intro = f"{situ}. My name is {sender}. The details that have to be in there: {need_txt}."
        spec = f"It has to fit in a single text of at most {limit} characters including spaces and punctuation, on one or two lines at most.{extra}"
        prompt = C.chat(rng, intro, rng.choice(SAVE), None, C.register_for(rng), spec=spec)
        yield Task(slug=f"{i + 1:02d}-{key}-{limit}", prompt=prompt, difficulty=d, start=_start_notes(rng), hidden=K.check_files(rules), solution={"reply.md": gold + "\n"}, verify=K.VERIFY, kind="greenfield",
                   tags=["writing", "constraints", "sms"], notes={"limit": limit})


# --------------------------------------------------------------------------------------------------------------------
# chat-write-summary


def _memo_bike(rng):
    d = date(2026, rng.randint(1, 10), rng.randint(2, 26))
    contractor = rng.choice(["Halvorsen Fabrication", "Greywell Steelworks", "Maple & Sons Joinery", "Tidewater Structures"])
    cost = rng.randrange(6000, 24000, 250)
    bikes = rng.choice([12, 16, 20, 24])
    pct = rng.choice([40, 50, 60])
    dl = d + timedelta(days=rng.randint(60, 120))
    text = (f"The residents' committee met on {d.day} {C.MONTHS[d.month - 1]} to discuss a covered bike shelter for the courtyard. {contractor} quoted ${cost:,} for a shelter holding {bikes} bikes. "
            f"The committee agreed to apply for a grant covering {pct}% of the cost and to pay the rest from the maintenance reserve. Work must be finished by {dl.day} {C.MONTHS[dl.month - 1]} to keep the grant. "
            f"Please keep the contractor's name ({contractor}) out of anything circulated to residents until the contract is signed. Several residents asked about lighting, which was put off to a later meeting.")
    facts = [F.money_re(cost * 100), F.date_re(dl), F.word_re("grant")]
    gold_sents = [f"The committee will apply for a grant covering {pct}% of the ${cost:,} cost of a shelter for {bikes} bikes.", "The rest will come from the maintenance reserve.",
                  f"The work must finish by {dl.day} {C.MONTHS[dl.month - 1]} to keep the grant."]
    return text, facts, [contractor, contractor.split()[0]], "the contractor's name", gold_sents, ["decision about the grant", "the cost", "the deadline"]


def _memo_library(rng):
    d = date(2026, rng.randint(1, 10), rng.randint(2, 26))
    eff = d + timedelta(days=rng.randint(20, 50))
    old = rng.choice([40, 44, 48])
    new = old + rng.choice([4, 6, 8])
    saved = rng.randrange(1800, 6200, 100)
    who = rng.choice(["Ms Brandt", "Mr Quist", "Ms Lacroix"])
    text = (f"Following the board meeting on {d.day} {C.MONTHS[d.month - 1]}, the branch library will open for {new} hours a week instead of {old}, starting on {eff.day} {C.MONTHS[eff.month - 1]}. "
            f"The extra hours are all on Saturdays and Sunday afternoons. The change is funded by savings of ${saved:,} from the lighting upgrade. "
            f"Staff were told first; {who} asked that her name is not mentioned in any announcement because of an unrelated HR matter. Volunteers are welcome to help with weekend opening.")
    facts = [F.num_re(new), F.date_re(eff), F.num_re(old)]
    gold_sents = [f"From {eff.day} {C.MONTHS[eff.month - 1]} the library will open {new} hours a week instead of {old}", "with the extra hours on Saturdays and Sunday afternoons.",
                  f"The change is funded by ${saved:,} saved on lighting."]
    return text, facts, [who, who.split()[1]], "the staff member who asked not to be named", gold_sents, ["the new hours", "the start date", "the old hours"]


def _memo_party(rng):
    d = date(2026, rng.randint(4, 9), rng.randint(5, 26))
    fee = rng.randrange(2500, 9000, 500)
    a = rng.choice([12, 13, 14]) * 60
    b = a + rng.choice([5, 6, 7]) * 60
    vol = rng.randint(14, 30)
    neigh = rng.choice(["Mr Abbot", "Mrs Lindgren", "Mr Fenwick"])
    text = (f"The street party will take place on {d.day} {C.MONTHS[d.month - 1]}. The council permit costs ${fee:,} and has been paid from the residents' fund. "
            f"The road will be closed between {C.hhmm(a)} and {C.hhmm(b)}, and {vol} volunteers have signed up to marshal the ends of the street. "
            f"There was a disagreement with {neigh} about parking, which is still unresolved; please do not mention it in the summary that goes to the newsletter.")
    facts = [F.date_re(d), F.time_re(a), F.time_re(b)]
    gold_sents = [f"The street party is on {d.day} {C.MONTHS[d.month - 1]}.", f"The road will be closed from {C.hhmm(a)} to {C.hhmm(b)}.", f"The ${fee:,} permit is paid and {vol} volunteers will marshal."]
    return text, facts, [neigh, neigh.split()[1], "parking"], "the parking disagreement", gold_sents, ["the date", "the closure start", "the closure end"]


def _memo_server(rng):
    d = date(2026, rng.randint(1, 10), rng.randint(5, 26))
    a = rng.choice([1, 2, 3]) * 60
    down = rng.choice([20, 30, 45, 90])
    vendor = rng.choice(["Cirrusworks", "Northpoint Hosting", "BlueFjord Cloud"])
    disc = rng.choice([8, 12, 15])
    text = (f"The server migration is scheduled for the night of {d.day} {C.MONTHS[d.month - 1]}, starting at {C.hhmm(a)}. Expected downtime is {down} minutes. "
            f"If the checks fail, the team will roll back to the old servers within the same window. The vendor, {vendor}, gave us a {disc}% discount on the first year; this is commercially sensitive and must not appear in staff communications.")
    facts = [F.date_re(d), F.time_re(a), F.num_re(down)]
    gold_sents = [f"The server migration starts at {C.hhmm(a)} on {d.day} {C.MONTHS[d.month - 1]}.", f"Expect about {down} minutes of downtime.", "If the checks fail, we roll back to the old servers in the same window."]
    return text, facts, [vendor, vendor.split()[0], "discount"], "the vendor's name and the discount", gold_sents, ["the date", "the start time", "the downtime"]


MEMOS = [_memo_bike, _memo_library, _memo_party, _memo_server]


@family("chat-write-summary", category="chat", lang="text", kind="greenfield", n=12, summary="summarise a pasted memo within a word limit as bullets or a paragraph; required facts, one confidential item must stay out, no invented numbers")
def gen_summary(rng, n):
    plan = [2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 3, 4]
    for i in range(n):
        d = plan[i % len(plan)]
        text, facts, conf, conf_desc, gold_sents, disp = MEMOS[i % len(MEMOS)](rng)
        nums = {m.group(0).rstrip(",").replace(",", "").rstrip("%") for m in re.finditer(r"(?<![A-Za-z0-9.])\d[\d,]*(?:\.\d+)?%?", text)}
        nums |= {n_ + "%" for n_ in list(nums)}
        K_bul = rng.choice([2, 3])
        as_bullets = d >= 3 and rng.random() < 0.7
        gs = [g if g.endswith(".") else g + "." for g in gold_sents]
        if as_bullets:
            items = gs[:3] if K_bul == 3 else [gs[0] + " " + gs[1], gs[2]]
            gold = "\n".join(f"- {it}" for it in items) + "\n"
        else:
            gold = " ".join(gs) + "\n"
            K_bul = 0
        body_words = _alnum_words(gold)
        cap = ((body_words + 12) // 10) * 10 + (10 if d <= 3 else 0)
        rules = [{"t": "max_words", "n": cap}, {"t": "numbers_subset", "allowed": sorted(nums)}, {"t": "exclude", "words": conf}]
        for f_ in facts:
            rules.append({"t": "include", "any": [f_], "label": "key fact"})
        if as_bullets:
            rules.append({"t": "bullets", "min": K_bul, "max": K_bul})
        else:
            rules.append({"t": "bullets", "max": 0})
            rules.append({"t": "paragraphs", "min": 1, "max": 1})
        # the gold must pass; make allowed numbers include any in gold
        K.assert_passes(rules, gold, what=f"summary {i}")
        form = f"exactly {K_bul} bullet points (lines starting with '- ')" if as_bullets else "a single paragraph with no bullet points"
        intro = rng.choice(["Our committee secretary pasted these minutes into notes.txt and I need a short summary for the newsletter.", "Please summarise the memo in memo.txt for people who will not read the whole thing.",
                            "I have to turn the notes in memo.txt into a short summary for the noticeboard."])
        files = {"memo.txt": text + "\n", "notes.txt": "(empty)\n"}
        spec = (f"Keep it to at most {cap} words, as {form}. It has to include {', '.join(disp[:-1])} and {disp[-1]}. "
                f"Do not mention {conf_desc}, and do not introduce any number that is not in the memo.")
        prompt = C.chat(rng, intro, rng.choice(SAVE), None, C.register_for(rng), spec=spec)
        yield Task(slug=f"{i + 1:02d}-{MEMOS[i % len(MEMOS)].__name__[6:]}-{'bul' if as_bullets else 'par'}", prompt=prompt, difficulty=d, start=files, hidden=K.check_files(rules),
                   solution={"reply.md": gold}, verify=K.VERIFY, kind="greenfield", tags=["writing", "summary", "constraints"], notes={"cap": cap, "bullets": K_bul})


# --------------------------------------------------------------------------------------------------------------------
# chat-write-commit

VERBS = ["Fix", "Add", "Remove", "Rename", "Use", "Cache", "Raise", "Trim", "Clamp", "Drop", "Guard", "Handle"]


def _c_pagination(rng):
    fn = rng.choice(["paginate", "page_slice", "window_for"])
    mod = rng.choice(["listing", "paging", "feeds"])
    diff = (f"--- a/{mod}.py\n+++ b/{mod}.py\n@@ -11,7 +11,7 @@ def {fn}(items, page, per_page):\n     if per_page <= 0:\n         raise ValueError(\"per_page must be positive\")\n-    start = page * per_page\n"
            f"+    start = (page - 1) * per_page\n     return items[start:start + per_page]\n")
    subj = f"Fix off-by-one in {fn} page offset"
    body = [f"{fn} treated pages as zero-based, so page 1 skipped the first", "per_page items and the last page came back empty. Pages are one-based", "everywhere else in the app, so subtract one before multiplying."]
    return mod, fn, diff, subj, body, "Fix", {"must": [fn, mod]}


def _c_none_guard(rng):
    fn = rng.choice(["format_price", "render_total", "money_str"])
    mod = rng.choice(["pricing", "display", "invoice"])
    diff = (f"--- a/{mod}.py\n+++ b/{mod}.py\n@@ -4,5 +4,7 @@\n def {fn}(cents):\n+    if cents is None:\n+        return \"n/a\"\n     return f\"{{cents // 100}}.{{cents % 100:02d}}\"\n")
    subj = f"Handle missing amounts in {fn}"
    body = [f"{fn} raised a TypeError when an order had no price yet, which", "broke the whole invoice page. Return the placeholder \"n/a\" instead."]
    return mod, fn, diff, subj, body, "Handle", {"must": [fn, "n/a"]}


def _c_cache(rng):
    fn = rng.choice(["load_rates", "read_config", "fetch_zones"])
    mod = rng.choice(["rates", "settings", "geo"])
    diff = (f"--- a/{mod}.py\n+++ b/{mod}.py\n@@ -1,8 +1,11 @@\n+import functools\n import json\n \n \n+@functools.lru_cache(maxsize=1)\n def {fn}():\n     with open(\"{mod}.json\") as fh:\n         return json.load(fh)\n")
    subj = f"Cache the result of {fn}"
    body = [f"{fn} re-read and re-parsed {mod}.json on every call, which showed", "up in profiles of the checkout flow. Wrap it in lru_cache since the file", "only changes on deploy."]
    return mod, fn, diff, subj, body, "Cache", {"must": [fn, "lru_cache"]}


def _c_timeout(rng):
    fn = rng.choice(["fetch", "download", "call_api"])
    mod = rng.choice(["client", "http_util", "remote"])
    old, new = rng.choice([(5, 30), (3, 20), (10, 45)])
    diff = (f"--- a/{mod}.py\n+++ b/{mod}.py\n@@ -8,7 +8,7 @@ import requests\n \n \n-def {fn}(url, timeout={old}):\n+def {fn}(url, timeout={new}):\n     resp = requests.get(url, timeout=timeout)\n     resp.raise_for_status()\n     return resp.json()\n")
    subj = f"Raise default timeout in {fn} to {new}s"
    body = [f"The {old} second default timed out on the slow report endpoint,", f"so {fn} failed for large exports. Use {new} seconds; callers that need", "a shorter limit can still pass their own."]
    return mod, fn, diff, subj, body, "Raise", {"must": [fn, str(new)]}


def _c_trim(rng):
    fn = rng.choice(["parse_email", "clean_address", "normalise_handle"])
    mod = rng.choice(["contacts", "signup", "forms"])
    diff = (f"--- a/{mod}.py\n+++ b/{mod}.py\n@@ -2,4 +2,4 @@\n def {fn}(raw):\n-    return raw.lower()\n+    return raw.strip().lower()\n")
    subj = f"Trim whitespace in {fn}"
    body = [f"Pasted values with a trailing space were stored as distinct from", "the same value without it, so duplicates slipped through. Strip first", "and then lower-case."]
    return mod, fn, diff, subj, body, "Trim", {"must": [fn, "whitespace"]}


def _c_clamp(rng):
    fn = rng.choice(["add_to_cart", "set_quantity", "update_line"])
    mod = rng.choice(["cart", "basket", "orders"])
    diff = (f"--- a/{mod}.py\n+++ b/{mod}.py\n@@ -9,6 +9,7 @@ class Cart:\n     def {fn}(self, sku, qty):\n+        qty = max(qty, 0)\n         self.lines[sku] = self.lines.get(sku, 0) + qty\n         return self.lines[sku]\n")
    subj = f"Clamp negative quantities in {fn}"
    body = [f"A negative qty from the mobile app reduced the stored line below", "zero and produced negative totals. Clamp the incoming value to zero."]
    return mod, fn, diff, subj, body, "Clamp", {"must": [fn, "negative"]}


COMMITS = [_c_pagination, _c_none_guard, _c_cache, _c_timeout, _c_trim, _c_clamp]


@family("chat-write-commit", category="chat", lang="text", kind="greenfield", n=12, summary="write a commit message for a pasted diff under a house convention (verb list, subject length, blank line, wrapped body, mentions, ticket footer)")
def gen_commit(rng, n):
    plan = [2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 3, 4]
    for i in range(n):
        d = plan[i % len(plan)]
        mod, fn, diff, subj, body, verb, req = COMMITS[i % len(COMMITS)](rng)
        ticket = f"{rng.choice(['REL', 'OPS', 'BUG', 'APP'])}-{rng.randint(100, 9999)}"
        width = 72 if d <= 3 else rng.choice([60, 64])
        maxsubj = 50 if d <= 3 else rng.choice([42, 46])
        if len(subj) > maxsubj:
            subj = subj[:maxsubj].rsplit(" ", 1)[0]
        # rewrap body to width
        text = " ".join(body) + f" The change is in {mod}.py."
        import textwrap
        wrapped = textwrap.wrap(text, width=width - 2)
        gold = subj + "\n\n" + "\n".join(wrapped) + f"\n\nRefs: {ticket}\n"
        verbs = ", ".join(VERBS)
        rules = [{"t": "include", "any": [fn], "label": "the function name"}, {"t": "include", "any": [mod], "label": "the module name"}]
        extra = f'''
ALLOWED = {VERBS!r}
MAXSUBJ = {maxsubj}
WIDTH = {width}
TICKET = {ticket!r}


def extra(text):
    fails = []
    lines = text.rstrip("\\n").split("\\n")
    subj = lines[0]
    if len(subj) > MAXSUBJ:
        fails.append(f"subject is {{len(subj)}} characters, the limit is {{MAXSUBJ}}")
    if subj.endswith("."):
        fails.append("subject must not end with a full stop")
    if subj.split(" ")[0] not in ALLOWED:
        fails.append("subject must start with one of: " + ", ".join(ALLOWED))
    if len(lines) < 3 or lines[1].strip() != "":
        fails.append("line 2 must be blank")
    for ln in lines[2:]:
        if len(ln) > WIDTH:
            fails.append(f"a body line is {{len(ln)}} characters, the limit is {{WIDTH}}")
            break
    if lines[-1].strip() != "Refs: " + TICKET:
        fails.append("the last line must be exactly 'Refs: " + TICKET + "'")
    if len(lines) < 5:
        fails.append("the body should have at least one line of explanation before the Refs line")
    return fails
'''
        K.assert_passes(rules, gold, extra, what=f"commit {i}")
        intro = rng.choice(["I'm about to commit the change below and our repo has a strict message format.", "Can you write the commit message for this diff? My team is picky about the format.",
                            "need a commit message for this patch (ticket below)"])
        spec = (f"House rules: the subject (first line) starts with one of these verbs: {verbs}; it is at most {maxsubj} characters and has no full stop at the end. Then one blank line, then a body that explains the why in lines of at most {width} characters, "
                f"and a final line that is exactly 'Refs: {ticket}'. The body has to mention the name of the function and the file that changed.")
        prompt = C.chat(rng, intro, rng.choice(SAVE), C.block(diff), C.register_for(rng), spec=spec)
        yield Task(slug=f"{i + 1:02d}-{fn}-{width}", prompt=prompt, difficulty=d, start=_start_notes(rng), hidden=K.check_files(rules, extra), solution={"reply.md": gold}, verify=K.VERIFY, kind="greenfield",
                   tags=["writing", "git", "constraints"], notes={"function": fn, "width": width})


# --------------------------------------------------------------------------------------------------------------------
# chat-write-poster

EVENTS = [("jumble sale", "village hall", "free entry"), ("repair cafe", "library annexe", "bring a broken thing"), ("open mic night", "the Blue Door pub", "sign-ups at 18:30"),
          ("plant swap", "Rowan Park pavilion", "bring a cutting"), ("fun run", "the cricket club", "all ages welcome"), ("quiz night", "the scout hut", "teams of four"),
          ("choir concert", "St Anne's church", "tickets on the door"), ("book fair", "the school gym", "proceeds go to the library")]


@family("chat-write-poster", category="chat", lang="text", kind="greenfield", n=10, summary="poster copy in a fixed line format with character limits per line, a URL, a date and place, exactly three bullets")
def gen_poster(rng, n):
    plan = [2, 2, 3, 3, 4, 4, 5, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        ev, place, extra_note = EVENTS[i % len(EVENTS)]
        dt = date(2026, rng.randint(3, 11), rng.randint(2, 26))
        st = rng.choice([10, 14, 18, 19]) * 60 + rng.choice([0, 30])
        host = rng.choice(["Elm Street", "Mill Lane", "Harbourside", "Northfield"])
        url = f"{host.lower().replace(' ', '')}.example.org/{ev.split()[0]}"
        h_lim = 28 if d <= 3 else rng.choice([22, 24])
        s_lim = 60 if d <= 3 else rng.choice([48, 52])
        b_lim = 32 if d <= 3 else rng.choice([24, 28])
        head = f"{host} {ev}".title()
        if len(head) > h_lim:
            head = ev.title()
        sub = f"Join us for a friendly afternoon with {extra_note}"[:s_lim].rstrip()
        bullets = [extra_note.capitalize()[:b_lim], "Tea and cake on sale", "Parking at the hall"]
        bullets = [b[:b_lim].rstrip() for b in bullets]
        gold = "\n".join([f"HEADLINE: {head}", f"SUBLINE: {sub}", *[f"- {b}" for b in bullets], f"WHEN: {dt.day} {C.MONTHS[dt.month - 1]}, {C.hhmm(st)}", f"WHERE: {place}", f"CTA: Details at {url}"]) + "\n"
        rules = [{"t": "lines", "min": 8, "max": 8}, {"t": "every_line", "re": r"^(HEADLINE: .+|SUBLINE: .+|- .+|WHEN: .+|WHERE: .+|CTA: .+)$"}, {"t": "bullets", "min": 3, "max": 3},
                 {"t": "include", "any": [rf"re:^HEADLINE: .{{3,{h_lim}}}$"], "label": f"HEADLINE of at most {h_lim} characters"}, {"t": "include", "any": [rf"re:^SUBLINE: .{{3,{s_lim}}}$"], "label": "SUBLINE length"},
                 {"t": "include", "any": [F.date_re(dt)], "label": "date"}, {"t": "include", "any": [F.time_re(st)], "label": "time"}, {"t": "include", "any": [place.lower()], "label": "place"},
                 {"t": "include", "any": [url], "label": "url"}, {"t": "exclude", "words": ["re:!"]}, {"t": "max_line_chars", "n": 90}]
        extra_code = f'''
def extra(text):
    fails = []
    for ln in text.splitlines():
        if ln.startswith("- ") and len(ln) - 2 > {b_lim}:
            fails.append("a bullet is longer than {b_lim} characters: " + ln[:40])
        if ln.startswith("CTA:") and "{url}" not in ln:
            fails.append("the CTA line must contain the URL")
        if ln.startswith("WHEN:") and not (len(ln) > 8):
            fails.append("WHEN line too short")
    heads = [ln for ln in text.splitlines() if ln.startswith("HEADLINE:")]
    if len(heads) != 1:
        fails.append("exactly one HEADLINE line is needed")
    return fails
'''
        K.assert_passes(rules, gold, extra_code, what=f"poster {i}")
        intro = rng.choice([f"I'm putting up a poster for the {ev} and the print shop's template is very rigid.", f"Poster copy needed for our {ev}, the layout has fixed slots.", f"can you write the text for the {ev} poster? the printer only takes a strict format"])
        spec = (f"The format has to be exactly eight lines, in this order: `HEADLINE: ...` (at most {h_lim} characters after the label), `SUBLINE: ...` (at most {s_lim} characters after the label), three bullet lines each starting with '- ' "
                f"(at most {b_lim} characters after the dash and space), `WHEN: ...`, `WHERE: ...` and `CTA: ...`. Facts: it is a {ev} at {place} on {dt.day} {C.MONTHS[dt.month - 1]}, starting at {C.hhmm(st)}; "
                f"the website is {url}; the CTA line must contain that address. A detail worth mentioning: {extra_note}. No exclamation marks (the council forbids them on posters).")
        prompt = C.chat(rng, intro, rng.choice(SAVE), None, C.register_for(rng), spec=spec)
        yield Task(slug=f"{i + 1:02d}-{ev.split()[0]}-{h_lim}", prompt=prompt, difficulty=d, start=_start_notes(rng), hidden=K.check_files(rules, extra_code), solution={"reply.md": gold}, verify=K.VERIFY, kind="greenfield",
                   tags=["writing", "layout", "constraints"], notes={"limits": [h_lim, s_lim, b_lim]})


# --------------------------------------------------------------------------------------------------------------------
# chat-write-plainwords

GLOSSARY = [("utilise", "use"), ("commence", "start"), ("terminate", "end"), ("remuneration", "pay"), ("prior to", "before"), ("in the event that", "if"), ("facilitate", "help with"),
            ("subsequent to", "after"), ("endeavour", "try"), ("sufficient", "enough"), ("necessitate", "need"), ("ascertain", "find out"), ("approximately", "about"), ("purchase", "buy")]
PLAIN_T = {
    "utilise": "Staff must {w} the online form before the end of the month.",
    "commence": "The scheme will {w} on {d1}.",
    "terminate": "It will {w} on {d2} unless the committee agrees otherwise.",
    "remuneration": "Your {w} is paid on {d2}.",
    "prior to": "Please book {w} {d1}.",
    "in the event that": "{w} the form is late, a reminder goes out on {d2}.",
    "facilitate": "A volunteer will {w} each of the {n} workshops.",
    "subsequent to": "Reviews take place {w} {d1}.",
    "endeavour": "We will {w} to answer within {n} days.",
    "sufficient": "There must be {w} notice, at least {n} days.",
    "necessitate": "Larger groups may {w} extra rooms.",
    "ascertain": "Managers should {w} the figures before signing off.",
    "approximately": "That is {w} {n} per cent of the budget.",
    "purchase": "Staff may {w} up to {n} items at cost.",
}


@family("chat-write-plainwords", category="chat", lang="text", kind="greenfield", n=10, summary="rewrite a stuffy paragraph in plain English using a given glossary: banned terms gone, plain terms in, every number kept, sentence length limited")
def gen_plain(rng, n):
    plan = [2, 2, 3, 3, 3, 4, 4, 5, 3, 4]
    for i in range(n):
        d = plan[i % len(plan)]
        k = {2: 5, 3: 7, 4: 8, 5: 10}[d]
        pairs = rng.sample(GLOSSARY, k)
        dt1 = date(2026, rng.randint(1, 10), rng.randint(2, 26))
        dt2 = dt1 + timedelta(days=rng.randint(20, 80))
        num = rng.randint(3, 40)
        kw = dict(d1=f"{dt1.day} {C.MONTHS[dt1.month - 1]}", d2=f"{dt2.day} {C.MONTHS[dt2.month - 1]}", n=num)
        jar_s = [PLAIN_T[a].format(w=a, **kw) for a, _ in pairs]
        pl_s = [PLAIN_T[a].format(w=b, **kw) for a, b in pairs]
        if d >= 4:
            # long sentences in the source: join pairs with 'and furthermore'; the plain version splits them
            src_parts = []
            for j in range(0, len(jar_s), 2):
                grp = jar_s[j:j + 2]
                src_parts.append(grp[0].rstrip(".") + (", and furthermore " + grp[1][0].lower() + grp[1][1:] if len(grp) > 1 else "."))
            src = " ".join(src_parts)
        else:
            src = " ".join(jar_s)
        gold = " ".join(pl_s) + "\n"
        glossary_txt = "\n".join(f"{a} -> {b}" for a, b in pairs)
        nums = sorted({m.group(0) for m in re.finditer(r"\d+", src)})
        rules = [{"t": "exclude", "words": [a for a, _ in pairs]}] + [{"t": "include", "any": [F.word_re(b)], "label": f"plain word {b}"} for _, b in pairs] + [{"t": "include", "any": [F.num_re(x)], "label": f"number {x}"} for x in nums]
        rules.append({"t": "max_words", "n": int(_alnum_words(src) * 1.1) + 5})
        maxs = 18 if d >= 4 else None
        extra = ""
        if maxs:
            extra = f'''
def extra(text):
    import re
    fails = []
    for s in re.split(r"(?<=[.!?])\\s+", text.strip()):
        if s.strip() and len(s.split()) > {maxs}:
            fails.append("a sentence has more than {maxs} words: " + s[:50])
            break
    return fails
'''
        K.assert_passes(rules, gold, extra, what=f"plain {i}")
        intro = rng.choice(["Our policy text is written like a legal letter and nobody reads it. I need a plain-English version.", "Please rewrite the paragraph in paragraph.txt in plain English; I have a house glossary for the jargon.",
                            "The notice in paragraph.txt reads like a contract. Can you make it human?"])
        spec = (f"Use this glossary: whenever the paragraph uses a term on the left, use the plain word on the right instead (and none of the left-hand terms may remain):\n\n{glossary_txt}\n\n"
                f"Keep every date and number exactly as in the original and do not make the text more than a little longer." + (f" Also keep every sentence to at most {maxs} words, so split the long ones." if maxs else ""))
        prompt = C.chat(rng, intro, rng.choice(SAVE), None, C.register_for(rng), spec=spec)
        yield Task(slug=f"{i + 1:02d}-{k}terms-d{d}", prompt=prompt, difficulty=d, start={"paragraph.txt": src + "\n", "notes.txt": "n/a\n"}, hidden=K.check_files(rules, extra), solution={"reply.md": gold}, verify=K.VERIFY, kind="greenfield",
                   tags=["writing", "rewrite", "constraints"], notes={"terms": k})
