"""Rubric-mode decision and planning tasks: compare options using the user's own numbers (the true totals are in the checks), a week-by-week
study plan under hour limits, and a debugging approach for a described symptom."""
from __future__ import annotations

from fx import Task, family

from . import _common as C
from .rubric_talk import R

# --------------------------------------------------------------------------------------------------------------------
# chat-rubric-compare


def _cmp_phone(rng):
    a_m, a_up = rng.choice([29, 32, 35, 38]), rng.choice([180, 240, 300])
    b_m = a_m + rng.choice([14, 17, 20, 22])
    months = rng.choice([24, 30, 36])
    ta, tb = a_m * months + a_up, b_m * months
    text = (f"I'm choosing between two phone deals. Plan A is ${a_m} a month plus ${a_up} upfront for the handset, and Plan B is ${b_m} a month with the handset included. Both last {months} months. "
            f"Plan B also includes roaming in the EU, which I'd use for about two weeks a year.")
    return text, [f"{ta:,}", f"{tb:,}"], f"Plan A totals ${ta:,} and Plan B ${tb:,} over {months} months", "the roaming value and what happens to the handset at the end"


def _cmp_jobs(rng):
    sx, sy = rng.choice([52000, 54000, 56000]), rng.choice([57000, 59000, 61000])
    commute = rng.choice([220, 260, 300]) * 12
    home = rng.choice([900, 1200, 1500])
    nx, ny = sx - commute, sy - home
    text = (f"Two job offers. Offer X pays ${sx:,} and is in an office I'd commute to; the monthly travel pass is about ${commute // 12}. Offer Y pays ${sy:,} but is fully remote, and I'd need roughly ${home:,} a year for a desk, internet and heating. "
            f"Everything else is about equal, I think.")
    return text, [f"{nx:,}", f"{ny:,}"], f"after those costs X leaves ${nx:,} a year and Y leaves ${ny:,}", "career growth, isolation and what 'about equal' hides"


def _cmp_flat(rng):
    r1, u1, t1 = rng.choice([1100, 1150, 1200]), rng.choice([120, 140]), rng.choice([60, 90])
    r2, u2, t2 = r1 - rng.choice([100, 150, 200]), u1 - rng.choice([10, 20]), t1 + rng.choice([70, 90, 110])
    m1, m2 = r1 + u1 + t1, r2 + u2 + t2
    text = (f"Choosing between two flats. Flat 1: rent ${r1}, utilities about ${u1}, and a transit pass of ${t1} a month. Flat 2: rent ${r2}, utilities about ${u2}, transit pass ${t2} a month because it is further out. "
            f"Flat 2 is also a 35-minute commute each way against 10 minutes for Flat 1.")
    return text, [f"{m1:,}", f"{m2:,}", f"{m1 * 12:,}", f"{m2 * 12:,}"], f"monthly ${m1:,} against ${m2:,}, so ${m1 * 12:,} against ${m2 * 12:,} a year", "the value of the extra commute time and the lease length"


def _cmp_gym(rng):
    fee, eq, run = rng.choice([40, 45, 50]), rng.choice([500, 600, 700]), rng.choice([4, 5, 8])
    months = rng.choice([18, 24, 36])
    tg, th = fee * months, eq + run * months
    text = (f"Should I keep my gym membership (${fee} a month) or buy home equipment for ${eq} (plus about ${run} a month for replacement bands, mats and the like)? I'd judge it over the next {months} months. "
            f"I go roughly twice a week at the moment, though in winter I skip more.")
    return text, [f"{tg:,}", f"{th:,}"], f"the gym costs ${tg:,} over {months} months and home equipment ${th:,}", "whether I'd actually use the equipment as often"


def _cmp_coffee(rng):
    cup, days, weeks = rng.choice([3.8, 4.2, 4.5]), rng.choice([4, 5]), rng.choice([46, 48, 50])
    mach, per = rng.choice([280, 350, 420]), rng.choice([0.5, 0.6, 0.7])
    cups = days * weeks
    cafe = round(cup * cups, 2)
    home = round(mach + per * cups, 2)
    text = (f"I buy a coffee at the cafe near work, ${cup:.2f} a cup, {days} days a week for about {weeks} weeks a year. A machine for the office would cost ${mach} and each cup would cost me about ${per:.2f} in beans and milk. "
            f"What should I do over a year?")
    return text, [f"{cafe:,.2f}", f"{home:,.2f}"], f"the cafe costs ${cafe:,.2f} a year and the machine ${home:,.2f} in the first year", "the quality difference and the walk break"


def _cmp_car(rng):
    lease, down = rng.choice([310, 340, 380]), rng.choice([0, 1000, 1500])
    months = 36
    price, resale = rng.choice([17000, 19500, 22000]), rng.choice([8000, 9500, 11000])
    run = rng.choice([40, 60, 80])
    tl = lease * months + down
    tb = price - resale + run * months
    text = (f"Lease or buy a car for three years? Lease: ${lease} a month for {months} months plus ${down:,} upfront, nothing to pay at the end. Buy: ${price:,} up front, and I'd expect to sell it for about ${resale:,} after three years; "
            f"extra running and repair costs I'd have over the lease are about ${run} a month. Ignore financing and insurance for now.")
    return text, [f"{tl:,}", f"{tb:,}"], f"leasing costs ${tl:,} and buying costs ${tb:,} net over three years", "mileage limits, repair risk and the resale estimate"


CMPS = [_cmp_phone, _cmp_jobs, _cmp_flat, _cmp_gym, _cmp_coffee, _cmp_car]


def _cmp_train(rng):
    single, days, weeks = rng.choice([(6.4, 3, 46), (7.2, 4, 46), (5.8, 5, 44)])
    season = rng.choice([1300, 1450, 1600, 1750])
    pay = round(single * days * weeks, 2)
    text = (f"I commute by train {days} days a week for about {weeks} weeks a year. A day return costs ${single:.2f}, or I could buy an annual season ticket for ${season:,}. "
            f"I might work from home one more day a week next year, but nothing is decided.")
    return text, [f"{pay:,.2f}", f"{season:,}"], f"paying per trip comes to ${pay:,.2f} a year against ${season:,} for the season ticket", "the planned extra day at home changes the per-trip total"


def _cmp_storage(rng):
    cloud, drive, yrs = rng.choice([(9, 120, 3), (12, 150, 4), (6, 90, 3)])
    tc, td = cloud * 12 * yrs, drive + rng.choice([0, 20, 30]) * 0
    text = (f"Backup choices for my photos: cloud storage at ${cloud} a month, or an external drive for ${drive} that I'd replace after {yrs} years. I'd compare them over {yrs} years. "
            f"I do tend to forget to plug the drive in.")
    return text, [f"{tc:,}", f"{td:,}"], f"the cloud costs ${tc:,} over {yrs} years and the drive ${td:,}", "the forgetting-to-back-up risk and the drive's failure risk"


def _cmp_repair(rng):
    rep, new, extra = rng.choice([(180, 650, 15), (240, 720, 25), (120, 480, 10)])
    yrs = rng.choice([2, 3])
    tr = rep + extra * 12 * yrs
    tn = new
    text = (f"My laptop needs a ${rep} repair, or I could replace it with a ${new} one. The old machine would need about ${extra} a month in battery packs and small repairs, and I'd look at the next {yrs} years. "
            f"The old one is noticeably slower.")
    return text, [f"{tr:,}", f"{tn:,}"], f"repairing costs about ${tr:,} over {yrs} years and replacing ${tn:,}", "the speed difference and the resale value of the old laptop"


CMPS += [_cmp_train, _cmp_storage, _cmp_repair]


@family("chat-rubric-compare", category="chat", lang="text", kind="advice", n=9, mode="rubric", summary="choose between two options described with numbers: the correct totals are in the checks; the rubric grades the recommendation, the deciding factor and honesty about what is unknown")
def gen_compare(rng, n):
    plan = [2, 2, 3, 3, 3, 4, 4, 5, 2]
    for i in range(n):
        d = plan[i % len(plan)]
        fn = CMPS[i % len(CMPS)]
        text, nums, sentence, unknown = fn(rng)
        ask = rng.choice(["Which should I pick? Give me a clear recommendation and show the numbers.", "What would you do? I'd like the numbers and a straight answer.", "Help me decide, please."])
        if d >= 4:
            ask += " Keep it under 150 words."
        prompt = C.chat(rng, text, ask, None, C.register_for(rng))
        rub = R((f"Computes the totals correctly from the user's numbers and states them ({sentence})", 4), ("Gives one clear recommendation and names the deciding factor", 3),
                (f"Mentions at least one thing the numbers do not capture or that is uncertain (for example {unknown}) without inventing facts", 2), ("Uses only the figures the user gave; any assumption is labelled as one" + (" and stays under 150 words" if d >= 4 else ""), 1))
        checks = {"must_include_all": nums, "max_words": 150 if d >= 4 else 260}
        yield Task(slug=f"{i + 1:02d}-{fn.__name__[5:]}-d{d}", prompt=prompt, difficulty=d, rubric=rub, checks=checks, tags=["decision", "arithmetic"], notes={"scenario": fn.__name__})


# --------------------------------------------------------------------------------------------------------------------
# chat-rubric-study-plan

SKILLS = [
    ("conversational Spanish", "I can order food and say hello, nothing more", "hold a five-minute chat about my day", "a weekly 20-minute call with a language partner"),
    ("basic SQL", "I use spreadsheets daily but have never written a query", "answer questions about a sample sales table with joins and group by", "a free sample database"),
    ("running a 5K", "I can jog about two minutes before I need to walk", "run 5 kilometres without stopping", "a flat route near home"),
    ("watercolour painting", "I've never painted, only drawn with pencil", "paint a simple landscape I'd be happy to frame", "a cheap starter set"),
    ("intro Python", "I know what a variable is from a school class and that's it", "write a script that reads a CSV and prints a summary", "a laptop with Python installed"),
    ("public speaking", "I freeze when more than four people are listening", "give a five-minute talk to my team without notes", "two supportive colleagues"),
    ("bread baking", "I've only made one flat, dense loaf", "bake a decent loaf from a starter on a weekday routine", "an oven and a kitchen scale"),
    ("touch typing", "I use two fingers and look at the keys", "type 45 words per minute without looking", "ten minutes a day at a keyboard"),
    ("basic guitar chords", "I own a guitar and can't play anything", "play a simple three-chord song cleanly at a steady tempo", "a tuner app and a few chord charts"),
]


@family("chat-rubric-study-plan", category="chat", lang="text", kind="advice", n=9, mode="rubric", summary="a week-by-week learning plan with a fixed number of weeks and hours per week; checks count the week headings, the rubric grades realism, milestones and review")
def gen_plan(rng, n):
    plan = [2, 2, 3, 3, 3, 4, 4, 5, 2]
    for i in range(n):
        d = plan[i % len(plan)]
        skill, level, goal, resource = SKILLS[i % len(SKILLS)]
        W = {2: rng.choice([3, 4]), 3: rng.choice([4, 5, 6]), 4: rng.choice([6, 7]), 5: 8}[d]
        H = rng.choice([3, 4, 5, 6])
        extra = ""
        if d >= 3:
            extra = " One day a week must be a full rest day."
        if d >= 4:
            extra += f" The last week should be a review week with a self-test, and I don't want any week to exceed {H} hours."
        intro = f"I want to learn {skill}. Where I am now: {level}. My goal in {W} weeks: {goal}. I can spend about {H} hours a week and I have {resource}."
        ask = f"Please give me a week-by-week plan with headings 'Week 1' to 'Week {W}'.{extra}"
        prompt = C.chat(rng, intro, ask, None, C.register_for(rng))
        pairs = [(f"Has exactly {W} clearly labelled weeks, each with a concrete weekly focus", 3), (f"Weekly time fits the user's limit of about {H} hours (and the plan states or implies how the hours are split)", 3),
                 (f"Milestones are measurable and build towards the goal ({goal})", 3), ("Includes practice-and-review or a self-test, and the pace is realistic for the stated starting point", 2)]
        if d >= 3:
            pairs.append(("Respects the extra rules given in the request (rest day each week" + ("; final week is a review week with a self-test; no week above the hour limit" if d >= 4 else "") + ")", 2))
        else:
            pairs.append(("Stays concise (no long preamble)", 1))
        rub = R(*pairs)
        checks = {"regex_all": [rf"Week {k}\b" for k in (1, W)], "regex_none": [rf"Week {W + 1}\b"], "max_words": 120 * W + 100}
        yield Task(slug=f"{i + 1:02d}-{skill.split()[0].lower()}-{W}w-d{d}", prompt=prompt, difficulty=d, rubric=rub, checks=checks, tags=["planning", "learning"], notes={"weeks": W, "hours": H})


# --------------------------------------------------------------------------------------------------------------------
# chat-rubric-debug-approach

SYMPTOMS = [
    ("our checkout page takes about six seconds to load, but only between 12:00 and 14:00 on weekdays", ["lunch", "traffic", "load", "p95", "profil", "connection pool", "cache", "database"], "the time-of-day pattern and a first measurement"),
    ("one test in our suite fails about one run in ten, but only in CI and never on my laptop", ["flaky", "order", "timing", "seed", "isolat", "environment", "rerun", "race"], "reproducing the flake and finding what differs in CI"),
    ("our service's memory climbs by roughly 50 MB an hour until it is restarted", ["leak", "heap", "profil", "growth", "cache", "restart", "snapshot"], "confirming the growth source with a heap profile"),
    ("behind our load balancer we get a 502 about once in every few hundred requests, never in the app logs", ["keep-alive", "timeout", "idle", "upstream", "load balancer", "logs", "502"], "comparing timeouts and looking at the balancer's logs"),
    ("a nightly cron job started running twice last Tuesday and nobody changed the schedule", ["duplicate", "lock", "crontab", "two", "scheduler", "deploy", "host"], "checking for a second scheduler or host and adding a lock"),
    ("our CSV import silently drops the last row of some files, not others", ["newline", "trailing", "end of file", "line ending", "off-by-one", "sample", "compare"], "finding what the affected files have in common"),
    ("dates in the production reports are shifted by a day for some users, but local tests are fine", ["timezone", "time zone", "UTC", "offset", "server", "locale", "midnight"], "separating stored time from displayed time"),
    ("the server's disk fills up completely every Friday and we clean it up by hand", ["logs", "rotate", "du", "largest", "cron", "temp", "weekly"], "finding what grows on Fridays with du and timestamps"),
    ("after Thursday's deploy our API's p95 latency doubled, but the median is unchanged", ["p95", "tail", "slow", "endpoint", "bisect", "diff", "deploy", "trace"], "isolating which endpoint or code path drives the tail"),
    ("emails from our app have been landing in spam since Tuesday", ["SPF", "DKIM", "DMARC", "reputation", "headers", "blacklist", "sending"], "checking authentication records and recent sending changes"),
]


@family("chat-rubric-debug-approach", category="chat", lang="text", kind="advice", n=9, mode="rubric", summary="a vague production symptom with one telling detail: how would you go about finding the cause? graded on the first measurement, narrowing strategy and not jumping to a root cause")
def gen_debug(rng, n):
    plan = [2, 2, 3, 3, 3, 4, 4, 5, 2]
    for i in range(n):
        d = plan[i % len(plan)]
        sym, kws, label = SYMPTOMS[i % len(SYMPTOMS)]
        voices = ["I'm the only dev on call and I'd rather not guess. ", "", "My manager wants an answer by tomorrow. ", "We've already restarted everything once. "]
        extra = rng.choice(voices)
        ask = "How would you go about finding the cause? I'd like an ordered plan, not a lecture." + (" Max seven steps." if d >= 4 else "")
        prompt = C.chat(rng, f"{extra}Symptom: {sym}.", ask, None, C.register_for(rng))
        rub = R((f"Starts with a concrete first measurement or check that targets this symptom ({label})", 3), ("Gives an ordered plan to narrow the search (what changed, what differs between good and bad cases, bisecting or reproducing)", 3),
                ("Refrains from declaring a root cause without evidence; hypotheses are presented as hypotheses", 2), ("Names specific, relevant tools or data sources to use rather than generic 'check the logs'", 2), ("Is organised as a short ordered list" + (" of at most seven steps" if d >= 4 else ""), 1))
        yield Task(slug=f"{i + 1:02d}-{sym.split()[1]}-{sym.split()[2]}-d{d}", prompt=prompt, difficulty=d, rubric=rub, checks={"must_include_any": kws, "bullets_min": 3, "bullets_max": 7 if d >= 4 else 10, "max_words": 300}, tags=["debugging", "approach"], notes={"symptom": sym})
