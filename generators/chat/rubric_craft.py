"""Rubric-mode writing and explanation tasks: explain at a level, brainstorm under constraints, rewrite in a different tone,
critique a draft with planted flaws, summarise a disagreement neutrally, write a short piece with required facts."""
from __future__ import annotations

from datetime import date, timedelta

from fx import Task, family

from . import _common as C
from .rubric_talk import R

# --------------------------------------------------------------------------------------------------------------------
# chat-rubric-explain

CONCEPTS = [
    dict(key="compound-interest", name="compound interest", core=["interest is paid on earlier interest as well as on the original amount", "growth speeds up the longer the money stays invested"],
         jargon=["exponential", "APR", "principal", "amortis"], kw=["interest on interest", "earlier interest", "snowball", "grows faster", "earns interest", "on the interest", "compound"]),
    dict(key="dns", name="DNS", core=["it translates human-friendly names into the numeric addresses computers use", "the lookup passes through a chain or hierarchy of servers, with answers remembered along the way"],
         jargon=["recursive", "resolver", "TTL", "authoritative"], kw=["address", "phone book", "directory", "lookup", "look up", "IP"]),
    dict(key="heat-pump", name="how a heat pump works", core=["it moves existing heat from outside to inside rather than creating heat", "it can deliver more heat energy than the electricity it uses"],
         jargon=["enthalpy", "coefficient of performance", "refrigerant", "evaporator"], kw=["moves heat", "move heat", "fridge", "refrigerator", "outside", "heat from"]),
    dict(key="tides", name="why we have tides", core=["the Moon's gravity (with a smaller contribution from the Sun) pulls on the oceans", "most coasts get roughly two high tides a day as the Earth rotates through the bulges"],
         jargon=["gravitational gradient", "perigee", "syzygy"], kw=["moon", "Moon", "gravity", "twice"]),
    dict(key="public-key", name="public-key encryption", core=["there are two linked keys: one can be shared openly to lock a message", "only the private key can unlock what the public key locked"],
         jargon=["RSA", "modular", "prime factor", "cipher suite"], kw=["public key", "private key", "padlock", "lock", "two keys"]),
    dict(key="git-branches", name="git branches", core=["a branch is a separate line of work that does not disturb the main line", "branches can later be merged back together"],
         jargon=["rebase", "HEAD", "refspec", "fast-forward"], kw=["merge", "copy", "separate", "main", "parallel", "version"]),
    dict(key="inflation", name="inflation", core=["it is a general rise in prices over time", "the same amount of money buys less than before"],
         jargon=["CPI", "monetary", "deflator", "basis points"], kw=["prices", "buys less", "basket", "cost more", "purchasing power"]),
    dict(key="sourdough", name="what a sourdough starter is", core=["it is a mix of flour and water that wild yeast and bacteria live in", "the microbes ferment the flour, making gas that raises the bread and sourness"],
         jargon=["lactobacilli", "hydration", "autolyse", "proteolysis"], kw=["yeast", "ferment", "bubbles", "wild", "bacteria"]),
    dict(key="gps", name="how GPS works", core=["satellites broadcast signals containing the exact time", "a receiver compares the signal delays from several satellites to work out where it is"],
         jargon=["trilateration", "ephemeris", "pseudorange", "GNSS"], kw=["satellite", "time", "distance", "signal"]),
    dict(key="api", name="what an API is", core=["it is an agreed way for one program to ask another for something", "the asking program does not need to know how the other one works inside"],
         jargon=["endpoint", "REST", "payload", "idempotent"], kw=["menu", "waiter", "ask", "request", "messenger", "message"]),
    dict(key="caching", name="caching", core=["keeping a copy of something slow to get so it can be reused quickly", "the copy can go out of date, so it has to be refreshed or thrown away sometimes"],
         jargon=["eviction", "TTL", "invalidation", "write-through"], kw=["copy", "remember", "faster", "reuse", "store", "save"]),
    dict(key="battery", name="why phone batteries wear out", core=["every charge cycle slightly damages the battery's chemistry so it holds less over time", "heat and being kept at full charge speed this up"],
         jargon=["lithium plating", "electrolyte", "dendrite", "state of charge"], kw=["charge", "heat", "holds less", "cycles", "capacity"]),
]
AUDIENCE = [("a curious nine-year-old", 110), ("my retired grandfather who ran a shop for forty years", 140), ("a new colleague in sales who has never worked with engineers", 150), ("a high-school teacher preparing a ten-minute lesson", 200),
            ("a CEO who has sixty seconds", 90), ("a friend who is nervous about all things technical", 130)]


@family("chat-rubric-explain", category="chat", lang="text", kind="advice", n=12, mode="rubric", summary="explain a concept to a stated audience under length and vocabulary limits; graded on the core ideas, level, an analogy and the limits")
def gen_explain(rng, n):
    plan = [2, 2, 3, 3, 3, 3, 4, 4, 4, 2, 3, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        c = CONCEPTS[i % len(CONCEPTS)]
        aud, cap = AUDIENCE[(i * 5 + rng.randrange(len(AUDIENCE))) % len(AUDIENCE)]
        if d >= 4:
            cap = int(cap * 0.8)
        asks = [f"Can you explain {c['name']} to {aud}?", f"I have to explain {c['name']} to {aud} tomorrow and I'd like to get it right. Can you write the explanation?",
                f"Explain {c['name']} for {aud}, please."]
        cons = [f"Keep it under {cap} words."]
        if d >= 3:
            cons.append("Use one everyday analogy.")
        recap = d >= 4
        if recap:
            cons.append("Finish with one sentence that starts 'In short'.")
        if d >= 4:
            cons.append("Avoid jargon; in particular please don't use the words " + ", ".join(f"'{j}'" for j in c["jargon"][:3]) + ".")
        prompt = C.chat(rng, rng.choice(asks), " ".join(cons), None, C.register_for(rng))
        rub = R((f"Gets the core ideas right: {c['core'][0]}; and {c['core'][1]}", 4),
                (f"Pitched for the stated audience ({aud}): plain vocabulary, no unexplained technical terms", 3),
                ("Uses a concrete everyday analogy or example that actually maps onto the mechanism (not decoration)", 2 if d >= 3 else 1),
                (f"Respects the limits it was given ({', '.join(cons)})", 1))
        checks = {"max_words": cap + 25, "must_include_any": c["kw"]}
        if d >= 4:
            checks["must_not_include"] = c["jargon"][:3]
        if recap:
            checks["regex_all"] = [r"In short"]
        yield Task(slug=f"{i + 1:02d}-{c['key']}-d{d}", prompt=prompt, difficulty=d, rubric=rub, checks=checks, tags=["explanation", "audience"], notes={"concept": c["name"], "audience": aud})


# --------------------------------------------------------------------------------------------------------------------
# chat-rubric-brainstorm

BRAIN = [
    ("names for a repair café in our village of {place}", "names", "every name at most three words"),
    ("slogans for a fundraiser to keep the {place} library open", "slogans", "every slogan at most seven words"),
    ("names for our new rescue cat, a grey tabby with one white paw", "names", "every name one word"),
    ("titles for a talk about {topic} at a local meetup", "titles", "every title at most eight words"),
    ("team names for our office pub quiz (we're {team})", "team names", "every name at most four words"),
    ("fundraising event ideas for a small village choir with a budget of ${budget}", "ideas", "each idea described in one short line"),
    ("ways to reduce food waste in our school canteen (about {n} meals a day)", "ideas", "each idea one short line with a rough effort rating (low, medium, high)"),
    ("gift ideas under ${budget} for a friend who loves gardening", "gift ideas", "each with a one-line reason"),
    ("names for a small bakery that specialises in rye bread", "names", "every name at most three words"),
    ("warm-up activities for a {n}-minute classroom session with thirty teenagers", "activities", "each activity labelled with its duration"),
]


@family("chat-rubric-brainstorm", category="chat", lang="text", kind="advice", n=10, mode="rubric", summary="brainstorm a fixed number of items under per-item limits and banned words; graded on constraint compliance, variety and fit to the context")
def gen_brain(rng, n):
    plan = [1, 2, 2, 3, 3, 3, 4, 4, 3, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        what, noun, lim = BRAIN[i % len(BRAIN)]
        p = dict(place=rng.choice(["Little Marsh", "Oakby", "Thornwick", "Penhallow"]), topic=rng.choice(["testing in small teams", "bees and honey", "typography", "community gardening"]), team=rng.choice(["a mix of accountants and engineers", "mostly historians"]),
                 budget=rng.choice([20, 30, 50, 500, 800]), n=rng.choice([300, 450, 15, 20, 25]))
        cnt = {1: 5, 2: 6, 3: 8, 4: 10, 5: 12}[d]
        banned = []
        if d >= 3:
            banned = rng.sample(["fix", "magic", "best", "happy", "classic", "tasty", "super"], 2)
        extra = []
        if d >= 4:
            extra.append("Mark your two favourites with a star and give a one-line reason for each.")
        ask = f"Please give me exactly {cnt} {noun}; {lim}." + (f" Don't use the words {' or '.join(repr(b) for b in banned)}." if banned else "") + (" " + " ".join(extra) if extra else "")
        prompt = C.chat(rng, f"I need {what.format(**p)}.", ask, None, C.register_for(rng))
        rub = R((f"Provides exactly {cnt} distinct {noun}, as a clear list", 3), (f"Every item follows the per-item rule ({lim})" + (f" and avoids the banned words {', '.join(banned)}" if banned else ""), 3),
                ("The items are varied (different angles or tones, not slight rewordings of one idea) and fit the stated context", 3), ("Adds nothing that was not asked for beyond at most a one-line intro" + (" (the starred favourites with reasons are required)" if extra else ""), 1))
        checks = {"bullets_min": cnt, "bullets_max": cnt + (2 if extra else 0), "max_words": 60 * cnt}
        if banned:
            checks["must_not_include"] = banned
        yield Task(slug=f"{i + 1:02d}-{noun.split()[0]}-{cnt}", prompt=prompt, difficulty=d, rubric=rub, checks=checks, tags=["brainstorm", "constraints"], notes={"count": cnt})


# --------------------------------------------------------------------------------------------------------------------
# chat-rubric-rewrite


def _ms(d):
    return f"{d.day} {C.MONTHS[d.month - 1]}"


def _rw_parking(rng):
    spot = rng.choice(["14", "22", "7", "31"])
    t = rng.choice(["8am", "7:30am"])
    msg = f"To whoever keeps taking space {spot}: it is MY space and I pay for it. This is the {rng.choice(['third', 'fourth', 'fifth'])} time this month. If your car is still there at {t} tomorrow I will have it reported. Learn to read the signs."
    return msg, [spot, t], ["MY space", "Learn to read"], "firm but friendly", "a polite but clear note I can leave on the windscreen"


def _rw_invoice(rng):
    inv = f"INV-{rng.randint(1000, 9999)}"
    amt = rng.randrange(300, 4000, 25)
    due = date(2026, rng.randint(1, 11), rng.randint(2, 26))
    msg = f"This is the second time I'm asking about {inv} for ${amt}, which was due on {_ms(due)}. I don't understand why it's so hard to pay a simple invoice. Pay it by Friday or we stop work."
    return msg, [inv, f"${amt}", _ms(due)], ["so hard", "simple invoice"], "polite but firm", "a reminder email that keeps the deadline but doesn't burn the relationship"


def _rw_rambling(rng):
    a, b = rng.sample(["the data migration", "the new onboarding flow", "the vendor audit", "the office move", "the quarterly report"], 2)
    d1, d2 = date(2026, rng.randint(1, 5), rng.randint(2, 26)), date(2026, rng.randint(6, 11), rng.randint(2, 26))
    msg = (f"So basically, as you know, we've been working on a lot of things lately, and it's been quite busy, honestly, with everything going on, but I wanted to give you a quick update. "
           f"Well, first, {a} is more or less done and should be finished by {_ms(d1)}, I think. And then there's {b}, which has had a few hiccups and which will probably, hopefully, be ready around {_ms(d2)}. "
           f"Anyway, let me know if you have any questions or whatever, and sorry again for the long email!")
    return msg, [_ms(d1), _ms(d2), a, b], ["quite busy", "or whatever", "sorry again"], "concise and professional", "a tight status update"


def _rw_feedback(rng):
    who = rng.choice(C.FIRST)
    n = rng.choice([3, 4, 5])
    msg = f"{who}, your slides last week were a mess. Nobody could follow them and you clearly didn't prepare. You went {n} minutes over, which was embarrassing. Fix it before the client call on Thursday."
    return msg, [who, f"{n} minutes", "Thursday"], ["a mess", "embarrassing", "clearly didn't prepare"], "constructive and kind but still honest", "feedback I can send privately"


def _rw_coffee(rng):
    who = rng.choice(C.FIRST)
    co = rng.choice(["Halvorsen & Co", "Brightwater Labs", "Finch Analytics"])
    msg = f"Dear {who}, I am writing to request a meeting at your earliest convenience in order to discuss potential synergies between my skillset and the opportunities at {co}. I have attached my CV for your perusal. Please advise on your availability."
    return msg, [who, co], ["synergies", "perusal", "at your earliest convenience"], "warmer, human and much shorter", "a short friendly message asking for a 20-minute chat"


def _rw_restaurant(rng):
    dish = rng.choice(["risotto", "lamb shank", "mushroom pie"])
    n = rng.choice([40, 50, 55])
    dt = date(2026, rng.randint(1, 11), rng.randint(2, 26))
    msg = f"Your restaurant is a disgrace. We waited {n} minutes on {_ms(dt)} for a cold {dish} and the waiter just shrugged. I want my money back and I'll tell everyone I know."
    return msg, [str(n), _ms(dt), dish], ["disgrace", "tell everyone"], "calm and factual, but clear about wanting a refund", "a complaint email that has a chance of actually working"


REWRITES = [_rw_parking, _rw_invoice, _rw_rambling, _rw_feedback, _rw_coffee, _rw_restaurant]


@family("chat-rubric-rewrite", category="chat", lang="text", kind="advice", n=12, mode="rubric", summary="rewrite a pasted message in a different tone while keeping every fact; graded on facts kept, tone shift, no leftover harshness and the requested length")
def gen_rewrite(rng, n):
    plan = [2, 2, 3, 3, 3, 3, 4, 4, 4, 2, 3, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        fn = REWRITES[i % len(REWRITES)]
        msg, facts, harsh, tone, what = fn(rng)
        cap = {2: 110, 3: 90, 4: 70, 5: 55}[d] if fn is not _rw_rambling else 70
        cap = max(cap, 50)
        intro = f"Here's a message I wrote while annoyed (or just badly):"
        ask = f"Please rewrite it so it is {tone}. I want {what}. Keep every date, number and name, and stay under {cap} words."
        prompt = C.chat(rng, intro, ask, C.block(msg), C.register_for(rng))
        rub = R(("Keeps every concrete fact from the original (" + ", ".join(facts) + ") and invents none", 4), (f"The tone is clearly {tone}: no sarcasm, insults or exaggerations, and the ask or point is still unmistakable", 3),
                ("Has one clear call to action or point, placed early", 2), (f"Within {cap} words and reads like something a real person would send", 1))
        yield Task(slug=f"{i + 1:02d}-{fn.__name__[4:]}-d{d}", prompt=prompt, difficulty=d, rubric=rub, checks={"max_words": cap + 10, "must_include_all": facts, "must_not_include": harsh}, tags=["rewrite", "tone"], notes={"tone": tone})


# --------------------------------------------------------------------------------------------------------------------
# chat-rubric-critique

DRAFTS = [
    dict(key="cover", kind="the opening paragraph of a cover letter", flaws=[("a cliché instead of evidence ('passionate team player')", ["passionate", "team player", "cliché", "cliche"]), ("the actual role applied for is buried in the third sentence", ["buried", "role", "lede", "first sentence"]),
                                                                   ("no concrete achievement or number", ["achievement", "number", "specific", "evidence"])],
         text="I am a passionate team player with a strong work ethic and a hunger to learn. Over the years I have worked in many environments and gained a lot of experience in lots of different areas. I am writing to apply for the Operations Coordinator role at Ashgrove Housing. I believe I would be a great fit."),
    dict(key="blurb", kind="a product page blurb for a cast-iron pan", flaws=[("vague superlatives ('world-class', 'amazing') with no specifics", ["superlative", "world-class", "amazing", "vague", "specific"]), ("one 50-word sentence that is hard to follow", ["long sentence", "one sentence", "split", "hard to follow", "run-on"]),
                                                                     ("no information on size, weight or care", ["size", "weight", "care", "details", "dimensions"])],
         text="Our world-class cast-iron pan is simply amazing and will transform the way you cook, whether you are frying eggs on a Sunday morning, searing a steak for friends who have come over for dinner, baking a loaf of bread in the oven, or just reheating last night's leftovers, because it is made with care and passion by people who love food."),
    dict(key="volunteer", kind="a volunteer recruitment ad for a food bank", flaws=[("it never says when or where to show up", ["when", "where", "date", "time", "address"]), ("passive and impersonal ('volunteers are needed')", ["passive", "impersonal", "you", "personal"]),
                                                                              ("no clear way to sign up", ["sign up", "contact", "call to action", "how to"])],
         text="Volunteers are needed at the community food bank. It is hoped that members of the public will come forward. Tasks include sorting, packing and distribution. Experience is not required but enthusiasm is appreciated. Many hands make light work."),
    dict(key="apology", kind="an apology email to a customer whose order arrived late", flaws=[("it blames the courier instead of owning it", ["blame", "courier", "ownership", "own it", "excuse"]), ("the apology comes in the last line", ["last line", "buried", "end", "start with", "first"]),
                                                                                      ("it offers nothing concrete to make up for the delay", ["compensation", "refund", "discount", "make up", "concrete"])],
         text="Hi, your order #4471 was delayed by four days. This was due to the courier, who had problems at their depot that we had no control over, and also the bank holiday. We know how important deliveries are. Anyway, sorry about that."),
    dict(key="readme", kind="the opening of a README for a small CLI tool", flaws=[("it starts with history instead of what the tool does", ["history", "what it does", "purpose", "first"]), ("there is no install or usage example", ["example", "install", "usage", "command"]),
                                                                           ("jargon ('leverages a paradigm') hides the point", ["jargon", "buzzword", "paradigm", "leverage"])],
         text="Quickrename began in 2019 as a weekend project and has since grown into a flexible framework that leverages a rule-driven paradigm to empower users to manage filenames at scale. Contributions are welcome. See the wiki for more."),
    dict(key="invite", kind="an invitation to a neighbourhood street party", flaws=[("the date and the time are in different paragraphs and the time is missing am/pm", ["date", "time", "am", "pm", "ambiguous"]), ("it asks people to 'bring something' without saying what", ["bring", "vague", "what to bring", "specific"]),
                                                                            ("tone shifts from friendly to bossy at the end", ["tone", "bossy", "friendly", "rules"])],
         text="Hello neighbours! We're having a street party on Saturday the 14th. Everyone is welcome and we'd love to see you. Please bring something. The party starts at 4 and the road will be closed. You must clear away your own mess and anyone who doesn't will not be invited next year."),
]


@family("chat-rubric-critique", category="chat", lang="text", kind="advice", n=12, mode="rubric", summary="give feedback on a pasted draft with three planted flaws; graded on naming the real flaws, prioritising, quoting the text and showing one concrete rewrite")
def gen_critique(rng, n):
    plan = [2, 2, 3, 3, 3, 3, 4, 4, 4, 2, 3, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        dr = DRAFTS[i % len(DRAFTS)]
        intro = f"I wrote {dr['kind']} and I'm not happy with it but can't see why:"
        ask = rng.choice(["What's wrong with it? Be straight with me.", "Can you tell me the main problems, in order of importance?", "Give me honest feedback."]) + (" Please don't rewrite the whole thing, just show me one example fix." if d >= 3 else "")
        prompt = C.chat(rng, intro, ask, C.block(dr["text"]), C.register_for(rng))
        f1, f2, f3 = dr["flaws"]
        rub = R((f"Identifies the main planted problems, including: {f1[0]}; {f2[0]}; {f3[0]}", 4), ("Points to the actual text (quotes or paraphrases specific phrases) instead of giving generic writing advice", 3),
                ("Orders the feedback by importance and keeps it to the few points that matter", 2), ("Shows one concrete improved sentence or opening rather than rewriting everything", 2 if d >= 3 else 1))
        kw = [k for fl in dr["flaws"] for k in fl[1]]
        yield Task(slug=f"{i + 1:02d}-{dr['key']}-d{d}", prompt=prompt, difficulty=d, rubric=rub, checks={"max_words": 330, "must_include_any": kw}, tags=["critique", "feedback"], notes={"draft": dr["key"]})


# --------------------------------------------------------------------------------------------------------------------
# chat-rubric-opinions

DISPUTES = [
    ("moving the monthly club night from Thursday to Saturday", [("Priya", "I support Saturday. I work late on Thursdays and miss half of every club night.", "supports Saturday because she works late on Thursdays"),
                                                                ("Gordon", "I'm against it. My carer only comes on Saturdays and I'd have to cancel.", "opposes it because his carer only comes on Saturdays"),
                                                                ("Mei", "I'm happy either way, but the hall booking has to be sorted before we move anything.", "is happy either way but wants the hall booking sorted first")], "everyone wants the club to keep going"),
    ("introducing paid parking on the village green", [("Alan", "I'm against it. Visitors already complain about how much everything costs here.", "is against it because visitors already complain about prices"),
                                                       ("Sunita", "I'm for it as long as residents get free permits.", "is for it as long as residents get free permits"),
                                                       ("Joe", "I'd like a three-month trial before we decide anything.", "wants a three-month trial first")], "nobody wants the green to be blocked on market days"),
    ("replacing the shared office fridge with individual lockers", [("Hana", "I like the lockers idea because food keeps going missing from the fridge.", "likes lockers because food keeps going missing"),
                                                                    ("Dylan", "I don't like it. Lockers cost money and take up space we don't have.", "dislikes lockers because they cost money and take space"),
                                                                    ("Fatima", "What about labelling everything and a weekly clear-out instead?", "suggests labelling and a weekly clear-out instead")], "the current fridge situation is not working"),
    ("switching the school newsletter from paper to email only", [("Mrs Okoye", "I worry that families without internet at home will miss out completely.", "fears that families without internet will miss out"),
                                                                  ("Mr Lund", "Printing costs us a lot and most copies end up in the bin.", "points to printing costs and wasted paper"),
                                                                  ("Claire", "I'd propose email by default and paper only on request.", "proposes email by default with paper on request")], "every parent should receive the news"),
    ("cutting the Friday team meeting from an hour to twenty minutes", [("Rafa", "Long meetings waste everyone's day, so I think twenty minutes is plenty.", "thinks long meetings waste everyone's day"),
                                                                        ("Beth", "I use the full hour to coordinate across time zones, so I'd lose that.", "uses the full hour to coordinate across time zones"),
                                                                        ("Tom", "How about sending an agenda in advance, with a longer meeting once a month?", "suggests an agenda in advance and a longer meeting monthly")], "meetings should be useful"),
    ("allowing dogs in the community garden", [("Wendy", "I support it. Lots of members walk their dogs past the garden anyway.", "supports it because many members walk their dogs past anyway"),
                                               ("Idris", "I'm against it because of the vegetable beds.", "is against it because of the vegetable beds"),
                                               ("Nora", "Could we make a fenced dog area by the gate?", "suggests a fenced dog area by the gate")], "the garden should stay welcoming"),
]


@family("chat-rubric-opinions", category="chat", lang="text", kind="advice", n=10, mode="rubric", summary="summarise three people's positions in a pasted thread neutrally, with the point of agreement and the decision still open")
def gen_opinions(rng, n):
    plan = [2, 2, 3, 3, 3, 4, 4, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        issue, people, common = DISPUTES[i % len(DISPUTES)]
        thread = "\n".join(f"{nm}: {txt}" for nm, txt, _ in people) + f"\n(All of us agree that {common}.)"
        cap = {2: 140, 3: 120, 4: 100, 5: 80}[d]
        prompt = C.chat(rng, f"I chair a small group and we've been arguing by message about {issue}. Here is the thread.", f"Can you summarise it neutrally for the chair's report in under {cap} words? Say who thinks what, what we agree on, and what still has to be decided.", C.block(thread), C.register_for(rng))
        names = [p[0] for p in people]
        rub = R(("States each person's position accurately and attributes it to the right name: " + "; ".join(f"{a} {c_}" for a, _, c_ in people), 4), ("Neutral: does not take a side, does not rank the arguments and does not use loaded words", 3),
                (f"Records the point of agreement ({common})", 2), ("Ends by saying what decision is still open or needs to be made", 2), (f"Within {cap} words", 1))
        yield Task(slug=f"{i + 1:02d}-{issue.split()[0]}-{issue.split()[1]}-d{d}", prompt=prompt, difficulty=d, rubric=rub, checks={"max_words": cap + 15, "must_include_all": names}, tags=["summary", "neutrality"], notes={"issue": issue})


# --------------------------------------------------------------------------------------------------------------------
# chat-rubric-short-piece

PIECES = [
    ("a wedding toast for my friends {a} and {b}", "{a} and {b} met when {a} spilled coffee on {b}'s laptop at a station cafe; {b} still has the stain", ["coffee", "laptop"], 140),
    ("a short retirement speech for my colleague {a}", "{a} has worked here for {y} years, keeps a drawer full of biscuits, and once saved a client's project over a bank holiday", ["biscuit", "drawer", "bank holiday"], 160),
    ("a thank-you note to my daughter's teacher, {a}", "{a} stayed after school every Tuesday to help with reading, and my daughter now reads aloud to her little brother", ["Tuesday", "reading"], 90),
    ("a conference speaker bio (third person, three sentences)", "I'm {a}, a data engineer for {y} years, I run a free pottery class on weekends, and I'm talking about boring-but-reliable pipelines", ["pottery", "pipelines"], 70),
    ("a eulogy for our office plant, a rubber fig named {a}, for the farewell card", "{a} survived two office moves, was overwatered by everyone, and once grew toward the window during a heatwave", ["office moves", "window"], 100),
    ("a note for the babysitter before we go out", "kids are {a} (age 6, needs the hall light on) and {b} (age 3, no screens after 7pm); bedtime is 8; our neighbour {c} is at number 12 for emergencies", ["hall light", "8", "number 12"], 110),
]


@family("chat-rubric-short-piece", category="chat", lang="text", kind="advice", n=10, mode="rubric", summary="a short piece of writing (toast, speech, bio, note) that must work in the given personal facts, tone and length")
def gen_piece(rng, n):
    plan = [2, 2, 3, 3, 3, 4, 4, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        what, facts, kws, cap = PIECES[i % len(PIECES)]
        a, b, c = rng.sample(C.FIRST, 3)
        y = rng.choice([12, 18, 25, 31])
        what_s, facts_s = what.format(a=a, b=b, c=c, y=y), facts.format(a=a, b=b, c=c, y=y)
        tone = rng.choice(["warm and a little funny", "sincere and understated", "light and cheeky but kind"])
        extra = ""
        if d >= 4:
            extra = rng.choice([" No clichés like 'the happy couple' or 'in all seriousness'.", " Do not start with 'Ladies and gentlemen' or 'Dear'."])
        prompt = C.chat(rng, f"I need {what_s}. Facts to work in: {facts_s}.", f"Tone: {tone}. Under {cap} words.{extra}", None, C.register_for(rng))
        rub = R((f"Works in the supplied facts accurately ({', '.join(kws)}) without inventing new personal details", 4), (f"Tone matches the request ({tone}) and the piece sounds like something a person would actually say or write", 3),
                (f"Has a clear shape: an opening, one or two specific moments, and a closing line", 2), (f"Within {cap} words" + (" and avoids the banned openers or clichés" if extra else ""), 1))
        checks = {"max_words": cap + 15, "must_include_any": kws}
        if extra:
            checks["must_not_include"] = ["the happy couple", "in all seriousness", "Ladies and gentlemen", "Dear "]
        yield Task(slug=f"{i + 1:02d}-{what.split()[1] if len(what.split()) > 1 else 'x'}-{what.split()[2] if len(what.split()) > 2 else 'y'}", prompt=prompt, difficulty=d, rubric=rub, checks=checks, tags=["writing", "personal-facts"], notes={"piece": what})
