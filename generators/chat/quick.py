"""Quick, genuinely easy chat questions (difficulty 1): one step of arithmetic, one clock calculation, reading one value from a tiny pasted
list or file, one trivial snippet, one reformatting. They exist so that the category has a real easy end."""
from __future__ import annotations

import fx
from datetime import date, timedelta
from fractions import Fraction

from fx import Task, family

from . import _checker as K
from . import _common as C

# --------------------------------------------------------------------------------------------------------------------
# chat-quick-math


def _m_pct(rng):
    base = rng.choice([40, 60, 80, 120, 150, 200, 240, 360])
    pct = rng.choice([5, 10, 15, 20, 25, 30])
    v = Fraction(base * pct, 100)
    what = rng.choice(["tip", "VAT", "discount", "deposit"])
    return f"quick one, what's {pct}% of {base}? it's for the {what}", [f"{float(v):g}"], f"{float(v):g}"


def _m_split(rng):
    n = rng.choice([3, 4, 5, 6, 8])
    each = rng.randrange(7, 40)
    tot = n * each
    return f"We spent ${tot} on a gift between {n} of us. How much each?", [str(each)], str(each)


def _m_change(rng):
    items = [round(rng.uniform(2, 15), 2) for _ in range(3)]
    pay = rng.choice([50, 40, 30]) if sum(items) < 30 else 50
    items = [Fraction(int(round(x * 100)), 100) for x in items]
    ch = Fraction(pay) - sum(items)
    return f"I bought three things at ${float(items[0]):.2f}, ${float(items[1]):.2f} and ${float(items[2]):.2f} and paid with a ${pay} note. What change do I get back?", [f"{float(ch):.2f}"], f"{float(ch):.2f}"


def _m_batches(rng):
    g = rng.choice([200, 250, 300, 125])
    bag = rng.choice([1000, 1500, 2000])
    return f"A batch of cookies needs {g} g of flour and I have a {bag} g bag. How many full batches can I make?", [str(bag // g)], str(bag // g)


def _m_avg(rng):
    xs = [rng.randint(6, 20) for _ in range(3)]
    s = sum(xs)
    if s % 3:
        xs[2] += 3 - s % 3
    return f"My last three run times (minutes) were {xs[0]}, {xs[1]} and {xs[2]}. What's the average?", [str(sum(xs) // 3)], str(sum(xs) // 3)


def _m_speed(rng):
    v = rng.choice([40, 48, 60, 72, 80])
    t = rng.choice([1.5, 2, 2.5, 3])
    d = v * t
    return f"We drove {d:g} km in {t:g} hours. What was our average speed in km/h?", [f"{v}"], f"{v}"


def _m_area(rng):
    a, b = rng.randint(3, 12), rng.randint(3, 12)
    return f"My rug is {a} m by {b} m. What's its area in square metres?", [str(a * b)], str(a * b)


def _m_fraction(rng):
    den = rng.choice([4, 5, 8, 10])
    num = rng.randint(1, den - 1)
    tot = den * rng.randint(4, 12)
    v = tot * num // den
    return f"What is {num}/{den} of {tot}?", [str(v)], str(v)


def _m_markup(rng):
    base = rng.choice([40, 50, 80, 120, 200])
    p = rng.choice([10, 20, 25, 50])
    v = Fraction(base * (100 + p), 100)
    return f"An item costs ${base} and the shop adds {p}% on top. What's the new price?", [f"{float(v):g}"], f"{float(v):g}"


def _m_total_time(rng):
    ep = rng.choice([22, 42, 45, 50])
    k = rng.choice([3, 4, 5, 6])
    tot = ep * k
    return f"{k} episodes of {ep} minutes each: how many minutes in total?", [str(tot)], str(tot)


def _m_pages(rng):
    days = rng.choice([8, 10, 12, 15])
    per = rng.randint(14, 40)
    return f"I have to read {days * per} pages in {days} days, evenly. How many pages a day?", [str(per)], str(per)


def _m_years(rng):
    by = rng.randint(1975, 2005)
    return f"My cousin was born in {by}. How old will she be at the end of 2026 (just 2026 minus the birth year)?", [str(2026 - by)], str(2026 - by)


MATHS = [_m_pct, _m_split, _m_change, _m_batches, _m_avg, _m_speed, _m_area, _m_fraction, _m_markup, _m_total_time, _m_pages, _m_years]


@family("chat-quick-math", category="chat", lang="text", kind="lookup", n=12, mode="answer", summary="one-step everyday arithmetic in a casual message (percentage, split, change, average, speed, area)")
def gen_qmath(rng, n):
    for i in range(n):
        for _a in range(50):
            fn = MATHS[i % len(MATHS)]
            text, contains, gold = fn(rng)
            prompt = C.chat(rng, text, "", None, rng.choice(["terse", "hurried", "chatty"]), allow_open=True)
            keep = C.unseen(prompt, contains, True)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{fn.__name__[3:]}", prompt, 1, keep, gold, fold=True, tags=["arithmetic", "quick"])
            break
        else:
            raise RuntimeError("quick-math")


# --------------------------------------------------------------------------------------------------------------------
# chat-quick-time


def _t_add(rng):
    a = rng.randint(8, 16) * 60 + rng.choice([0, 10, 20, 35, 50])
    k = rng.choice([45, 70, 85, 95, 130])
    return f"a meeting starts at {C.hhmm(a)} and runs {k} minutes. what time does it end? (HH:MM)", [C.hhmm(a + k)], C.hhmm(a + k)


def _t_diff(rng):
    a = rng.randint(6, 11) * 60 + rng.choice([5, 15, 30, 45])
    b = a + rng.choice([95, 140, 205, 250])
    return f"How long is it from {C.hhmm(a)} to {C.hhmm(b)}? Answer as H:MM please.", [f"{(b - a) // 60}:{(b - a) % 60:02d}"], f"{(b - a) // 60}:{(b - a) % 60:02d}"


def _t_weekday(rng):
    wd = rng.randint(0, 6)
    k = rng.choice([3, 10, 17, 23, 30])
    return f"Today is {C.WEEKDAYS[wd]}. What day of the week will it be in {k} days?", [C.WEEKDAYS[(wd + k) % 7]], C.WEEKDAYS[(wd + k) % 7]


def _t_12h(rng):
    h, m = rng.randint(1, 11), rng.choice([5, 15, 30, 45])
    pm = rng.random() < 0.6
    t = (h % 12 + (12 if pm else 0)) * 60 + m
    return f"What is {h}:{m:02d} {'pm' if pm else 'am'} on the 24-hour clock? (HH:MM)", [C.hhmm(t)], C.hhmm(t)


def _t_hours(rng):
    d, h = rng.randint(2, 5), rng.randint(1, 20)
    return f"How many hours is {d} days and {h} hours?", [str(d * 24 + h)], str(d * 24 + h)


def _t_bed(rng):
    wake = rng.choice([6, 7]) * 60 + rng.choice([0, 15, 30])
    sleep = rng.choice([465, 480, 450])
    bed = (wake - sleep) % 1440
    return f"My alarm is at {C.hhmm(wake)} and I want {sleep // 60}h{sleep % 60:02d} of sleep. What time do I need to be asleep by? (HH:MM, previous evening)", [C.hhmm(bed)], C.hhmm(bed)


def _t_left(rng):
    now = rng.randint(14, 17) * 60 + rng.choice([5, 20, 50])
    ev = now + rng.choice([35, 65, 95])
    return f"It is {C.hhmm(now)} and the film starts at {C.hhmm(ev)}. How many minutes do I have?", [str(ev - now)], str(ev - now)


def _t_next(rng):
    step = rng.choice([10, 12, 15, 20])
    t = 8 * 60 + rng.randrange(1, 55)
    nxt = 8 * 60 + (-(-(t - 8 * 60) // step)) * step
    return f"A bus leaves every {step} minutes starting at 08:00. I reach the stop at {C.hhmm(t)}. When is the next one? (HH:MM)", [C.hhmm(nxt)], C.hhmm(nxt)


def _t_days(rng):
    pairs = [("April", 30), ("May", 31), ("June", 30), ("July", 31), ("August", 31), ("September", 30)]
    a, b = rng.sample(pairs, 2)
    return f"How many days are there in {a[0]} and {b[0]} together (not a leap-year question)?", [str(a[1] + b[1])], str(a[1] + b[1])


def _t_dates(rng):
    d0 = date(2026, rng.randint(1, 10), rng.randint(1, 20))
    k = rng.choice([7, 14, 21, 28])
    e = d0 + timedelta(days=k)
    return f"What date is {k} days after {d0.day} {C.MONTHS[d0.month - 1]} 2026? Please use the format YYYY-MM-DD.", [C.iso(e)], C.iso(e)


def _t_dur2(rng):
    n, m = rng.randint(2, 4), rng.choice([20, 25, 35, 40])
    tot = n * m
    return f"{n} lessons of {m} minutes with no breaks: how long is that in total as H:MM?", [f"{tot // 60}:{tot % 60:02d}"], f"{tot // 60}:{tot % 60:02d}"


TIMES = [_t_add, _t_diff, _t_weekday, _t_12h, _t_hours, _t_bed, _t_left, _t_next, _t_days, _t_dates, _t_dur2]


@family("chat-quick-time", category="chat", lang="text", kind="lookup", n=12, mode="answer", summary="one clock or calendar step in a casual message (end time, difference, weekday in k days, 12 to 24 hour, next bus)")
def gen_qtime(rng, n):
    for i in range(n):
        for _a in range(50):
            fn = TIMES[i % len(TIMES)]
            text, contains, gold = fn(rng)
            prompt = C.chat(rng, text, "", None, rng.choice(["terse", "hurried", "chatty", "formal"]), allow_open=True)
            keep = C.unseen(prompt, contains, True)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{fn.__name__[3:]}", prompt, 1, keep, gold, fold=True, tags=["time", "quick"])
            break
        else:
            raise RuntimeError("quick-time")


# --------------------------------------------------------------------------------------------------------------------
# chat-quick-list: one derived number from a short pasted list

ITEMS_Q = [("tea", 4.5), ("oats", 3.2), ("honey", 7.9), ("jam", 3.8), ("flour", 2.1), ("rice", 5.4), ("lentils", 3.6), ("salt", 0.9), ("cocoa", 6.3), ("butter", 4.4)]


@family("chat-quick-list", category="chat", lang="text", kind="lookup", n=12, mode="answer", summary="a short pasted shopping or score list and one derived figure (total, difference, count over a threshold, position)")
def gen_qlist(rng, n):
    for i in range(n):
        for _a in range(100):
            k = rng.randint(4, 6)
            its = rng.sample(ITEMS_Q, k)
            prices = [round(p + rng.choice([0, 0.5, 1.0]), 2) for _, p in its]
            lines = "\n".join(f"{nm}: {p:.2f}" for (nm, _), p in zip(its, prices))
            kind = ["total", "range", "count_over", "position", "average", "cheapest_two"][i % 6]
            if kind == "total":
                v = round(sum(prices), 2)
                ask = "What's the total of all of these?"
                contains = [f"{v:.2f}"]
            elif kind == "range":
                v = round(max(prices) - min(prices), 2)
                ask = "How much more is the most expensive item than the cheapest one?"
                contains = [f"{v:.2f}"]
            elif kind == "count_over":
                thr = round(sorted(prices)[len(prices) // 2], 1)
                v = sum(1 for p in prices if p > thr)
                ask = f"How many of these cost more than {thr:.2f}?"
                contains = [str(v)]
            elif kind == "position":
                j = rng.randrange(k)
                ask = f"Which line number (counting from 1) is {its[j][0]} on?"
                contains = [str(j + 1)]
                v = j + 1
            elif kind == "average":
                v = sum(prices) / len(prices)
                ask = "What is the average price to two decimals?"
                contains = [f"{v:.2f}"]
            else:
                v = round(sum(sorted(prices)[:2]), 2)
                ask = "What do the two cheapest items cost together?"
                contains = [f"{v:.2f}"]
            prompt = C.chat(rng, rng.choice(["Here's my shopping list with prices.", "list from the market stall:", "Prices from the till receipt:"]), ask, C.block(lines), rng.choice(["terse", "hurried", "chatty"]))
            keep = C.unseen(prompt, contains, True)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, 1, keep, contains[0], fold=True, tags=["lists", "quick"])
            break
        else:
            raise RuntimeError("quick-list")


# --------------------------------------------------------------------------------------------------------------------
# chat-quick-file: read one value out of a tiny repo; nothing may change


def _f_port(rng):
    p = rng.choice([3000, 8080, 8443, 5173, 9090])
    return {"config.json": f'{{\n  "name": "demo-api",\n  "port": {p},\n  "debug": false\n}}\n', "README.md": "# demo-api\nSmall demo service.\n"}, "What port is the service configured to listen on (look in the config)?", str(p)


def _f_version(rng):
    v = f"{rng.randint(1, 4)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}"
    return {"package.json": f'{{\n  "name": "tiny-tool",\n  "version": "{v}",\n  "license": "MIT"\n}}\n', "index.js": "console.log('hi');\n"}, "Which version does package.json declare?", v


def _f_target(rng):
    t = rng.choice(["build", "all", "serve", "dist"])
    others = [x for x in ["clean", "test", "lint"] if x != t]
    mk = f".DEFAULT_GOAL := {t}\n\n{t}:\n\t@echo building\n\n{others[0]}:\n\t@echo cleaning\n\n{others[1]}:\n\t@echo checking\n"
    return {"Makefile": mk}, "What is the default goal of the Makefile (the target that runs when I type just `make`)?", t


def _f_base(rng):
    img = rng.choice(["python:3.11-slim", "node:22-alpine", "golang:1.22-bookworm", "ruby:3.3-slim"])
    return {"Dockerfile": f"FROM {img}\nWORKDIR /app\nCOPY . .\nCMD [\"./run.sh\"]\n", "run.sh": "#!/bin/sh\necho ok\n"}, "Which base image does the Dockerfile start from?", img


def _f_cron(rng):
    h = rng.randint(1, 5)
    m = rng.choice([0, 10, 25, 40])
    return {"crontab": f"# nightly jobs\n{m} {h} * * * /opt/bin/backup.sh\n*/15 * * * * /opt/bin/ping.sh\n"}, "At what hour of the day does the backup job run according to the crontab? (just the number)", f"{h}"


def _f_env(rng):
    keys = rng.sample(["DB_URL", "CACHE_URL", "API_KEY", "LOG_LEVEL", "REGION", "SENTRY_DSN", "FEATURE_X", "TIMEOUT_S"], rng.randint(3, 6))
    return {".env.example": "".join(f"{k}=\n" for k in keys), "README.md": "Copy .env.example to .env.\n"}, "How many variables are defined in .env.example?", str(len(keys))


def _f_pin(rng):
    v = f"{rng.randint(1, 3)}.{rng.randint(0, 20)}.{rng.randint(0, 9)}"
    return {"requirements.txt": f"requests=={v}\nrich==13.7.1\nclick==8.1.7\n"}, "Which version of requests is pinned in requirements.txt?", v


def _f_change(rng):
    d = date(2026, rng.randint(1, 9), rng.randint(2, 26))
    v = f"{rng.randint(1, 3)}.{rng.randint(1, 9)}.0"
    return {"CHANGELOG.md": f"# Changelog\n\n## {v} - {d.isoformat()}\n- Added export\n\n## 0.9.0 - 2025-06-01\n- First beta\n"}, "What is the date of the most recent release in the changelog?", d.isoformat()


def _f_compose(rng):
    host, cont = rng.choice([(8081, 80), (5433, 5432), (6380, 6379), (9001, 9000)])
    return {"docker-compose.yml": f"services:\n  web:\n    image: demo/web:latest\n    ports:\n      - \"{host}:{cont}\"\n"}, "Which host port does the web service publish?", str(host)


def _f_todo(rng):
    n = rng.randint(4, 9)
    lines = [f"value_{k} = {k}" for k in range(1, 12)]
    lines[n - 1] = "# TODO: handle empty input"
    return {"main.py": "\n".join(lines) + "\n"}, "On which line number of main.py is the comment tagged with the to-do marker?", str(n)


FILES_Q = [_f_port, _f_version, _f_target, _f_base, _f_cron, _f_env, _f_pin, _f_change, _f_compose, _f_todo]


@family("chat-quick-file", category="chat", lang="text", kind="restraint", n=12, mode="answer", summary="read one value out of a tiny config or project file and report it, without touching anything (sha256 manifest)")
def gen_qfile(rng, n):
    for i in range(n):
        fn = FILES_Q[i % len(FILES_Q)]
        files, ask, ans = fn(rng)
        note = rng.choice(["", " (No edits, please.)", " Just reading, leave it alone.", ""])
        intro = rng.choice(["Quick question about this repo.", "tiny question about the files in this folder", "Can you look something up for me?"])
        prompt = C.chat(rng, intro, ask + note, None, rng.choice(["terse", "hurried", "chatty"]))
        keep = C.unseen(prompt, [ans], False)
        if keep is None:
            keep = [ans]
        yield C.answer_task(f"{i + 1:02d}-{fn.__name__[3:]}", prompt, 1, keep, ans, start=files, hidden=K.manifest_only_check(files), verify=K.VERIFY, tags=["restraint", "read-only", "quick"])


# --------------------------------------------------------------------------------------------------------------------
# chat-quick-snippet


def _s_py(rng):
    t = rng.choice(["len", "slice", "split", "mod", "sum", "upper", "max", "join"])
    w = rng.choice(["harbour", "lantern", "orchard", "meadow", "copper"])
    n = rng.randint(3, 9)
    code = {"len": f'print(len("{w}"))', "slice": f'print("{w}"[1:4])', "split": f'print("{w}-x-{n}".split("-")[2])', "mod": f"print({n * 7 + 3} % {n}, {n * 7 + 3} // {n})", "sum": f"print(sum(range(1, {n + 1})))",
            "upper": f'print("{w}".upper()[:3])', "max": f"print(max([{n}, {n + 5}, {n - 2}]) - min([{n}, 2]))", "join": f'print("+".join(["{w}", "{n}"]))'}[t]
    return "python", code


def _s_js(rng):
    t = rng.choice(["len", "map", "join", "idx"])
    n = rng.randint(3, 6)
    code = {"len": f"console.log([{', '.join(str(k) for k in range(n))}].length)", "map": f"console.log([1, 2, 3].map(x => x * {n}).join(','))", "join": f"console.log(['a', 'b', 'c'].reverse().join(''))", "idx": f"console.log('orchard'.indexOf('{rng.choice(['r', 'c', 'h'])}'))"}[t]
    return "javascript", code


@family("chat-quick-snippet", category="chat", lang="mixed", kind="lookup", n=12, mode="answer", summary="what does this one-line Python or JavaScript snippet print (trivial, really executed)")
def gen_qsnip(rng, n):
    for i in range(n):
        for _a in range(50):
            lang, code = (_s_py if i % 3 != 2 else _s_js)(rng)
            res = fx.run({"main.py" if lang == "python" else "main.js": code + "\n"}, "python3 main.py" if lang == "python" else "node main.js", timeout=20)
            if not res.ok or not res.out.strip():
                continue
            out = res.out.strip()
            prompt = C.chat(rng, rng.choice(["What does this print?", "output of this one-liner?", "I'm learning and this confused me, what's the output?"]), "", f"```{'python' if lang == 'python' else 'javascript'}\n{code}\n```", rng.choice(["terse", "hurried", "chatty"]))
            keep = C.unseen(prompt, [out], False)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{lang[:2]}", prompt, 1, keep, out, tags=["code-reading", "quick"], lang=lang)
            break
        else:
            raise RuntimeError("quick-snippet")


# --------------------------------------------------------------------------------------------------------------------
# chat-quick-format


def _r_date(rng):
    d = date(2026, rng.randint(1, 12), rng.randint(1, 28))
    return f"Write {d.day:02d}/{d.month:02d}/2026 (day first) in the format YYYY-MM-DD.", C.iso(d)


def _r_name(rng):
    f, l = rng.choice(C.FIRST), rng.choice(C.LAST)
    return f"Turn '{l}, {f}' into 'First Last' with the first name first.", f"{f} {l}"


def _r_snake(rng):
    ws = rng.sample(["order", "total", "user", "last", "max", "retry", "page", "item", "price", "count"], rng.randint(2, 3))
    return f"Convert the identifier `{'_'.join(ws)}` to camelCase.", ws[0] + "".join(w.capitalize() for w in ws[1:])


def _r_title(rng):
    ws = rng.sample(["the", "quiet", "harbour", "of", "autumn", "lights", "and", "winter", "stone"], 4)
    return f"Put '{' '.join(ws)}' in Title Case, capitalising every word.", " ".join(w.capitalize() for w in ws)


def _r_phone(rng):
    d = f"{rng.randint(200, 999)}{rng.randint(200, 999)}{rng.randint(1000, 9999)}"
    return f"Format the number {d} as (NNN) NNN-NNNN.", f"({d[:3]}) {d[3:6]}-{d[6:]}"


def _r_upper(rng):
    w = rng.sample(["quarterly", "report", "draft", "final", "approved", "summary"], 2)
    return f"Write '{w[0]} {w[1]}' in all capitals with an underscore instead of the space.", f"{w[0].upper()}_{w[1].upper()}"


def _r_money(rng):
    c = rng.randrange(100000, 9999999, 7)
    return f"Write {c} cents as dollars with a thousands separator and two decimals, like $1,234.56.", C.money_c(c)


def _r_clock(rng):
    t = rng.randint(13, 23) * 60 + rng.choice([5, 25, 40, 55])
    h, m = divmod(t, 60)
    return f"Write {h:02d}:{m:02d} as a 12-hour time like 3:05 pm.", f"{h - 12}:{m:02d} pm"


def _r_slug(rng):
    ws = rng.sample(["Summer", "Fair", "Results", "2026", "Garden", "Notes", "Final"], 3)
    return f"Make a URL slug from '{' '.join(ws)}': lower case, hyphens between words.", "-".join(w.lower() for w in ws)


REFORM = [_r_date, _r_name, _r_snake, _r_title, _r_phone, _r_upper, _r_money, _r_clock, _r_slug]


@family("chat-quick-format", category="chat", lang="text", kind="lookup", n=12, mode="answer", summary="one tiny reformatting job (date, name, identifier case, phone, money, clock, slug) whose answer is a new string")
def gen_qformat(rng, n):
    for i in range(n):
        fn = REFORM[i % len(REFORM)]
        for _a in range(50):
            text, ans = fn(rng)
            prompt = C.chat(rng, text, "", None, rng.choice(["terse", "hurried", "chatty"]))
            keep = C.unseen(prompt, [ans], False)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{fn.__name__[3:]}", prompt, 1, keep, ans, fold=False, tags=["formatting", "quick"])
            break
        else:
            raise RuntimeError("quick-format")


# --------------------------------------------------------------------------------------------------------------------
# chat-write-oneliner: the smallest constrained-writing fixture


@family("chat-write-oneliner", category="chat", lang="text", kind="greenfield", n=12, summary="a one- or two-sentence message with a word cap and two facts (the easy end of the constrained-writing set)")
def gen_oneliner(rng, n):
    kinds = [
        ("a text to {name} saying I'll be {k} minutes late", "I'll be {k} minutes late", ["{k}"], ["the number {k}"]),
        ("a note to {name} reminding them the meeting is at {t}", "The meeting is at {t}", ["{t}"], ["the time {t}"]),
        ("a message to {name} saying thanks for the {gift}", "Thanks so much for the {gift}", ["{gift}"], ["the word '{gift}'"]),
        ("a one-line out-of-office reply that says I'm back on {dt}", "I'm out of the office and will be back on {dt}", ["{dt}"], ["the date {dt}"]),
        ("a message to {name} asking whether the {thing} is still available", "Is the {thing} still available", ["{thing}"], ["the word '{thing}'"]),
    ]
    for i in range(n):
        tpl, core, need, descr = kinds[i % len(kinds)]
        name = rng.choice(C.FIRST)
        k = rng.choice([10, 15, 20, 25])
        t = C.hhmm(rng.choice([9, 10, 14, 15, 16]) * 60 + rng.choice([0, 15, 30]))
        gift = rng.choice(["flowers", "lasagne", "book", "plant", "scarf"])
        dt = f"{rng.randint(2, 27)} {rng.choice(C.MONTHS[:11])}"
        thing = rng.choice(["bike", "sofa", "desk", "guitar", "table"])
        vals = dict(name=name, k=k, t=t, gift=gift, dt=dt, thing=thing)
        what = tpl.format(**vals)
        cap = rng.choice([12, 15, 18, 22])
        body = core.format(**vals)
        if "{name}" in tpl:
            body = body[0].lower() + body[1:] if not body.startswith("I'") else body
            gold = f"{name}, {body}."
        else:
            gold = f"{body}."
        words = len([w for w in gold.split() if any(ch.isalnum() for ch in w)])
        cap = max(cap, words + 3)
        facts = [x.format(**vals) for x in need]
        rules = [{"t": "max_words", "n": cap}, {"t": "lines", "max": 2}] + [{"t": "include", "any": [f], "label": f} for f in facts]
        if "{name}" in tpl:
            rules.append({"t": "include", "any": [name], "label": "the name"})
        K.assert_passes(rules, gold, what=f"oneliner {i}")
        intro = f"I need {what}."
        spec = f"At most {cap} words, one or two lines, and it has to include {' and '.join(d_.format(**vals) for d_ in descr)}."
        prompt = C.chat(rng, intro, rng.choice(["Save it in reply.md please.", "Put it in reply.md.", "Write it to reply.md."]), None, rng.choice(["terse", "hurried", "chatty"]), spec=spec)
        yield Task(slug=f"{i + 1:02d}-{need[0].strip('{}')}", prompt=prompt, difficulty=1, start={"notes.txt": "n/a\n"}, hidden=K.check_files(rules), solution={"reply.md": gold + "\n"}, verify=K.VERIFY, kind="greenfield",
                   tags=["writing", "quick", "constraints"])
