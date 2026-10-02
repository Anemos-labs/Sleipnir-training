"""Dates, clocks and schedules: calendar arithmetic, business days, flights across offsets, meeting slots, cron, rotas,
timesheets, timetables. All answers come from the solvers in this file."""
from __future__ import annotations

import calendar
import functools
from datetime import date, datetime, timedelta

from fx import family

from . import _common as C


def hm(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d}"


def long_date(d: date) -> str:
    return f"{C.wd(d)} {d.day} {C.MONTHS[d.month - 1]} {d.year}"


def rdate(rng, y0=2026, y1=2028) -> date:
    return date(rng.randint(y0, y1), rng.randint(1, 12), rng.randint(1, 28))


# --------------------------------------------------------------------------------------------------------------------
# chat-date-offset

def _last_weekday(y, m, wdn):
    d = date(y, m, calendar.monthrange(y, m)[1])
    while d.weekday() != wdn:
        d -= timedelta(days=1)
    return d


def _on_or_after(d, allowed):
    while d.weekday() not in allowed:
        d += timedelta(days=1)
    return d


@family("chat-date-offset", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="calendar arithmetic in daily-life clothes: add days, nth weekday, month-end clamps, ISO weeks, leap birthdays, shipping chains")
def gen_date(rng, n):
    plan = [1, 2, 2, 3, 3, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            reg = C.register_for(rng)
            kind = {1: ["plus_days"], 2: ["before_event", "age_days", "nth_weekday"], 3: ["month_clamp", "iso_week", "nth_weekday", "age_days"],
                    4: ["on_or_after", "leap_birthday", "month_clamp"], 5: ["chain", "on_or_after"]}[d]
            kind = rng.choice(kind)
            if kind == "plus_days":
                start = rdate(rng)
                N = rng.randint(21, 380)
                end = start + timedelta(days=N)
                what = rng.choice([("my visa appointment will be", "the processing time is"), ("my library hold expires", "holds last"),
                                   ("the warranty on my laptop ends", "the warranty runs for"), ("the customs hold on my parcel will be lifted", "the hold lasts")])
                intro = rng.choice([f"I bought it on {long_date(start)} and {what[1]} {N} days from that day.",
                                    f"Starting from {long_date(start)}, {what[1]} {N} days.",
                                    f"My paperwork was filed on {long_date(start)}. Apparently {what[1]} {N} days."])
                ask = rng.choice(["What calendar date does that land on, and which weekday? Please give the date as YYYY-MM-DD.",
                                  "I need the exact date (YYYY-MM-DD) and the day of the week."])
                contains = [C.iso(end), C.wd(end)]
                gold = f"{C.iso(end)}, a {C.wd(end)}."
            elif kind == "before_event":
                ev = rdate(rng)
                items = [("save-the-dates go out", rng.choice([12, 14, 16]) * 7), ("RSVPs are due", rng.choice([3, 4, 5]) * 7),
                         ("the caterer needs final numbers", rng.choice([10, 12, 9])), ("the florist wants a deposit", rng.choice([21, 28, 35, 20]))]
                chosen = rng.sample(items, 3)
                dates = [ev - timedelta(days=k) for _, k in chosen]
                text = "; ".join(f"{lbl} {k // 7} weeks before" if k % 7 == 0 else f"{lbl} {k} days before" for lbl, k in chosen)
                intro = f"We are organising a reunion for {long_date(ev)}. The plan: {text}."
                ask = "Give me each of those three dates as YYYY-MM-DD, in the order I listed them."
                contains = [C.iso(x) for x in dates]
                gold = "; ".join(f"{lbl}: {C.iso(x)}" for (lbl, _), x in zip(chosen, dates))
            elif kind == "age_days":
                a = rdate(rng)
                b = a + timedelta(days=rng.randint(40, 700))
                incl = rng.random() < 0.5
                days = (b - a).days + (1 if incl else 0)
                intro = (f"My course starts on {long_date(a)} and ends on {long_date(b)}. I want to put the day count in the brochure.")
                ask = (f"How many days is that, counting both the first and the last day?" if incl else
                       f"How many days is that, counting the first day but not the last day (so a one-day gap between consecutive dates would be 1)?")
                contains = [str(days)]
                if d == 3:
                    wks, rem = divmod(days, 7)
                    ask += " And also as whole weeks plus left-over days, written like 'W weeks D days'."
                    contains = [str(days), f"{wks} weeks {rem} days" if rem != 1 else f"{wks} weeks 1 days"]
                    contains = [str(days), f"{wks} week"]
                gold = f"{days} days" + (f" ({days // 7} weeks {days % 7} days)" if d == 3 else "")
            elif kind == "nth_weekday":
                y, m = rng.randint(2026, 2028), rng.randint(1, 12)
                wdn = rng.randint(0, 6)
                nth = rng.choice([1, 2, 3])
                dn = C.nth_weekday(y, m, wdn, nth)
                if dn is None:
                    continue
                lastd = _last_weekday(y, m, wdn)
                intro = rng.choice([f"The book club always meets on the {C.ordinal(nth)} {C.WEEKDAYS[wdn]} of the month, and the committee dinner is on the last {C.WEEKDAYS[wdn]}.",
                                    f"Our neighbourhood swap meet is on the {C.ordinal(nth)} {C.WEEKDAYS[wdn]} each month and the cleanup is the last {C.WEEKDAYS[wdn]}."])
                ask = f"What are the two dates in {C.MONTHS[m - 1]} {y}? Please write them as YYYY-MM-DD, the {C.ordinal(nth)}-one first."
                contains = [C.iso(dn), C.iso(lastd)]
                if dn == lastd:
                    continue
                gold = f"{C.iso(dn)} and {C.iso(lastd)}"
            elif kind == "month_clamp":
                start = date(rng.randint(2026, 2028), rng.choice([1, 3, 5, 7, 8, 10, 12]), rng.choice([29, 30, 31]))
                k = rng.randint(4, 13)
                tgt = C.month_add(start, k)
                intro = (f"My gym membership started on {long_date(start)} and renews every month on the same day-of-month, or on the last day of the month when that day does not exist "
                         f"(always counted from the original start date, never from the previous renewal date).")
                ask = f"On what date is renewal number {k} (renewal 1 is one month after the start)? Give YYYY-MM-DD and the weekday."
                contains = [C.iso(tgt), C.wd(tgt)]
                gold = f"{C.iso(tgt)}, {C.wd(tgt)}"
            elif kind == "iso_week":
                y = rng.randint(2025, 2029)
                base = rng.choice([date(y, 12, 28), date(y, 1, 1), date(y, 12, 31), date(y, 1, 2), date(y, 1, 4), date(y, 12, 29)])
                dt = base + timedelta(days=rng.randint(0, 3))
                iy, iw, _ = dt.isocalendar()
                intro = (f"Our planning tool labels everything with ISO 8601 week numbers (weeks start on Monday, and week 1 is the week containing the year's first Thursday). "
                         f"The release is scheduled for {long_date(dt)}.")
                ask = "Which week label is that? Write it like 2027-W05 (ISO year, then W, then two-digit week)."
                contains = [f"{iy}-W{iw:02d}"]
                gold = f"{iy}-W{iw:02d}"
            elif kind == "on_or_after":
                start = rdate(rng)
                N = rng.randint(10, 60)
                allowed = rng.choice([{0}, {0, 3}, {1, 4}, {2}])
                t = _on_or_after(start + timedelta(days=N), allowed)
                names = " or ".join(C.WEEKDAYS[x] for x in sorted(allowed))
                intro = (f"We freeze the code {N} days after the kickoff on {long_date(start)}, and the audit meeting is held on the first {names} on or after the freeze day "
                         f"(if the freeze day is already a {names}, that is the day).")
                ask = "What date is the audit meeting (YYYY-MM-DD)?"
                contains = [C.iso(t)]
                gold = C.iso(t)
            elif kind == "leap_birthday":
                by = rng.choice([2004, 2008, 2012, 2016, 2020])
                age = rng.randint(14, 21)
                y = by + age
                if y < 2026:
                    continue
                cele = date(y, 2, 29) if calendar.isleap(y) else date(y, 3, 1)
                intro = (f"My niece was born on 29 February {by}. In years that are not leap years the family celebrates on 1 March instead, and in leap years on 29 February itself. "
                         f"She turns {age} in {y}.")
                ask = "On what date is the party that year (YYYY-MM-DD), and what day of the week is it?"
                contains = [C.iso(cele), C.wd(cele)]
                gold = f"{C.iso(cele)} ({C.wd(cele)})"
            else:  # chain
                start = rdate(rng)
                prep = rng.randint(5, 14)
                ship_days = rng.choice([{0, 3}, {1, 4}, {0, 2, 4}])
                transit = rng.randint(3, 9)
                ship = _on_or_after(start + timedelta(days=prep), ship_days)
                arr = ship + timedelta(days=transit)
                note = ""
                if arr.weekday() == 6:
                    arr += timedelta(days=1)
                    note = " (moved from Sunday)"
                elif arr.weekday() == 5:
                    arr += timedelta(days=2)
                    note = " (moved from Saturday)"
                names = " or ".join(C.WEEKDAYS[x] for x in sorted(ship_days))
                intro = (f"I ordered a custom frame on {long_date(start)}. They need {prep} days to prepare it, then it ships on the first {names} on or after that point "
                         f"(the same day counts). Transit takes {transit} days from the shipping day, but the courier does not deliver at weekends, so a weekend arrival slides to the following Monday.")
                ask = "On which dates does it ship and arrive? Give both as YYYY-MM-DD, shipping first."
                contains = [C.iso(ship), C.iso(arr)]
                gold = f"ships {C.iso(ship)}, arrives {C.iso(arr)}{note}"
            prompt = C.chat(rng, intro, ask, None, reg)
            keep = C.unseen(prompt, contains, True)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, d, keep, gold, fold=True, tags=["calendar", "dates"], notes={"kind": kind})
            break
        else:
            raise RuntimeError("date-offset: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-business-days

HOLIDAY_NAMES = ["Founders' Day", "Harvest Monday", "Lantern Holiday", "River Day", "Midwinter Break", "Spring Bank Day", "Foundation Day",
                 "Unity Day", "Seafarers' Day", "Archive Day", "Maple Day", "Orchard Holiday"]


def _is_work(d, work, hol):
    return d.weekday() in work and d not in hol


def _add_work(d, k, work, hol):
    cur = d
    while k > 0:
        cur += timedelta(days=1)
        if _is_work(cur, work, hol):
            k -= 1
    return cur


@family("chat-business-days", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="working-day deadlines and counts with holiday lists, odd working weeks, and a two-calendar delivery chain")
def gen_bdays(rng, n):
    plan = [2, 2, 2, 3, 3, 4, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            reg = C.register_for(rng)
            start = rdate(rng)
            work = {0, 1, 2, 3, 4}
            if d >= 4:
                work = rng.choice([{1, 2, 3, 4, 5}, {0, 1, 2, 3}, {0, 1, 2, 4, 5}, {2, 3, 4, 5, 6}])
            kind = "deadline" if d in (2, 3, 4) and rng.random() < 0.6 else "count" if d in (3, 4) else "deadline"
            if d == 5:
                kind = "chain"
            hols = {}
            k_hol = rng.randint(1, 3)
            for _ in range(k_hol):
                hd = start + timedelta(days=rng.randint(1, 30))
                hols[hd] = rng.choice(HOLIDAY_NAMES)
            hol_txt = "\n".join(f"{C.iso(h)}  {nm}" for h, nm in sorted(hols.items()))
            workdesc = "Monday to Friday" if work == {0, 1, 2, 3, 4} else ", ".join(C.WEEKDAYS[x] for x in sorted(work))
            if d <= 2:
                work = {0, 1, 2, 3, 4}
                hols = {}
                hol_txt = ""
            if kind == "deadline":
                N = rng.randint(5, 14)
                if not _is_work(start, work, hols) and d >= 3:
                    pass
                dl = _add_work(start, N, work, hols)
                intro = rng.choice([f"A customer complaint arrives on {long_date(start)} and our policy says we must reply within {N} working days (the arrival day is not counted).",
                                    f"Support ticket received {long_date(start)}. The SLA is {N} working days, starting from the day after it arrives.",
                                    f"The supplier invoice landed on {long_date(start)}; we pay {N} working days later, not counting the day it landed."])
                spec = f"Working days here are {workdesc}." + (" The company is also closed on: " + ", ".join(f"{C.iso(h)} ({nm})" for h, nm in sorted(hols.items())) + "." if hols else "")
                ask = "What is the last day to reply/pay (YYYY-MM-DD), and what weekday is it?"
                contains = [C.iso(dl), C.wd(dl)]
                gold = f"{C.iso(dl)}, {C.wd(dl)}"
                data = None
            elif kind == "count":
                b = start + timedelta(days=rng.randint(14, 45))
                cnt = [x for x in (start + timedelta(days=j) for j in range((b - start).days + 1)) if _is_work(x, work, hols)]
                intro = f"I am planning leave from {long_date(start)} up to and including {long_date(b)} and want to know how many of those days I would actually be using up."
                spec = (f"Working days are {workdesc}, and the office is also closed on: " + ", ".join(f"{C.iso(h)} ({nm})" for h, nm in sorted(hols.items())) + ".") if hols else f"Working days are {workdesc}."
                ask = "How many working days is that, and what is the date of the last working day in the range (YYYY-MM-DD)?"
                contains = [str(len(cnt)), C.iso(cnt[-1])]
                gold = f"{len(cnt)} working days; the last is {C.iso(cnt[-1])}."
                data = None
            else:  # chain
                sup_work = {0, 1, 2, 3}
                cou_work = {1, 2, 3, 4, 5}
                sup_h = {start + timedelta(days=rng.randint(1, 8)): "plant shutdown" for _ in range(2)}
                cou_h = {start + timedelta(days=rng.randint(3, 14)): "courier holiday" for _ in range(2)}
                Ns = rng.randint(3, 5)
                dispatch = _add_work(start, Ns, sup_work, sup_h)
                Nc = rng.randint(2, 4)
                deliver = _add_work(dispatch, Nc, cou_work, cou_h)
                intro = (f"I placed an order with a small workshop on {long_date(start)}. They dispatch on their working day number {Ns} counted from the day after the order, "
                         f"and the courier then delivers on courier working day number {Nc} counted from the day after dispatch.")
                spec = ("The workshop works Monday to Thursday and is shut on " + ", ".join(C.iso(x) for x in sorted(sup_h)) + ". "
                        "The courier works Tuesday to Saturday and does not run on " + ", ".join(C.iso(x) for x in sorted(cou_h)) + ".")
                ask = "On which dates is it dispatched and delivered? Give both as YYYY-MM-DD, dispatch first."
                contains = [C.iso(dispatch), C.iso(deliver)]
                gold = f"dispatched {C.iso(dispatch)}, delivered {C.iso(deliver)}"
                data = None
            prompt = C.chat(rng, intro, ask, data, reg, spec=spec, data_after_ask=False)
            keep = C.unseen(prompt, contains, True)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, d, keep, gold, fold=True, tags=["calendar", "business-days"], notes={"kind": kind})
            break
        else:
            raise RuntimeError("bdays: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-flight-times

CITIES = [("Lisbon", 0), ("Reykjavik", 0), ("Lagos", 60), ("Johannesburg", 120), ("Nairobi", 180), ("Doha", 180), ("Dubai", 240),
          ("Karachi", 300), ("Mumbai", 330), ("Kathmandu", 345), ("Dhaka", 360), ("Bangkok", 420), ("Singapore", 480), ("Perth", 480),
          ("Tokyo", 540), ("Adelaide", 570), ("Sydney", 600), ("Auckland", 720), ("Sao Paulo", -180), ("Santiago", -240), ("Bogota", -300),
          ("Mexico City", -360), ("Denver", -420), ("Vancouver", -480), ("Anchorage", -540), ("Honolulu", -600)]


def _off(m):
    sign = "+" if m >= 0 else "-"
    a = abs(m)
    return f"UTC{sign}{a // 60}" + (f":{a % 60:02d}" if a % 60 else "")


@family("chat-flight-times", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="itineraries in local times with fixed UTC offsets: leg durations, layovers, total elapsed, arrival on the home clock")
def gen_flights(rng, n):
    plan = [2, 2, 2, 3, 3, 4, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            legs = {2: 1, 3: 2, 4: 3, 5: 3}[d]
            cities = rng.sample(CITIES, legs + 1)
            t0 = datetime(rng.randint(2026, 2027), rng.randint(1, 12), rng.randint(1, 25), rng.randint(0, 23), rng.randrange(0, 60, 5))
            utc = t0 - timedelta(minutes=cities[0][1])  # departure in UTC
            rows, durs, lays, tt = [], [], [], utc
            for k in range(legs):
                dur = rng.randrange(95, 15 * 60, 5)
                dep_u = tt
                arr_u = dep_u + timedelta(minutes=dur)
                dep_l = dep_u + timedelta(minutes=cities[k][1])
                arr_l = arr_u + timedelta(minutes=cities[k + 1][1])
                rows.append((cities[k], cities[k + 1], dep_l, arr_l))
                durs.append(dur)
                if k < legs - 1:
                    lay = rng.randrange(65, 11 * 60, 5)
                    lays.append(lay)
                    tt = arr_u + timedelta(minutes=lay)
            total = sum(durs) + sum(lays)
            home_arr = rows[-1][3] - timedelta(minutes=cities[-1][1]) + timedelta(minutes=cities[0][1])

            def f(dt):
                return f"{C.WEEKDAYS[dt.weekday()][:3]} {dt.day} {C.MONTHS[dt.month - 1][:3]} {dt:%H:%M}"
            lines = []
            for k, (a, b, dl, al) in enumerate(rows):
                lines.append(f"Leg {k + 1}: {a[0]} ({_off(a[1])}) dep {f(dl)}  ->  {b[0]} ({_off(b[1])}) arr {f(al)}")
            data = C.block("\n".join(lines))
            if d == 2:
                ask = "How long is the flight, door to door in the air? Write the duration as H:MM (for example 7:05)."
                contains = [hm(durs[0])]
                gold = f"The flight takes {hm(durs[0])}."
            elif d == 3:
                ask = "How long is each flight, and how long is the layover? Please write every duration as H:MM (for example 7:05), flights first, then the layover."
                contains = [hm(durs[0]), hm(durs[1]), hm(lays[0])]
                gold = f"Flights {hm(durs[0])} and {hm(durs[1])}, layover {hm(lays[0])}."
            elif d == 4:
                ask = ("What is the total time from my first departure to my final arrival (flights plus layovers, as H:MM, for example 25:10), "
                       "and how long is each of the two layovers (also H:MM)?")
                contains = [hm(total), hm(lays[0]), hm(lays[1])]
                gold = f"Total {hm(total)}; layovers {hm(lays[0])} and {hm(lays[1])}."
            else:
                ask = ("Three things, all using the offsets shown: (1) the total elapsed time from first departure to final arrival as H:MM, "
                       f"(2) the total time actually spent in the air as H:MM, and (3) what time it is in {cities[0][0]} (as HH:MM on the 24-hour clock) at the moment I land.")
                contains = [hm(total), hm(sum(durs)), f"{home_arr:%H:%M}"]
                gold = f"Elapsed {hm(total)}, airborne {hm(sum(durs))}, home clock {home_arr:%H:%M}."
            intro = rng.choice([f"I booked a trip with {legs} flight{'s' if legs > 1 else ''} and the airline's confirmation only shows local times, which makes my head hurt.",
                                f"my itinerary is below, all times are local to each airport and the offsets are fixed (ignore daylight saving).",
                                f"Trying to work out how knackered I'll be. These are the legs, with local times and the UTC offset of each city.",
                                f"Can you help me with the maths on this routing? I never trust myself with time zones."])
            prompt = C.chat(rng, intro, ask, data, C.register_for(rng))
            keep = C.unseen(prompt, contains, True)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{legs}leg-d{d}", prompt, d, keep, gold, fold=True, tags=["timezones", "durations"], notes={"legs": legs})
            break
        else:
            raise RuntimeError("flights: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-meeting-slot

TEAM_ROLES = ["design lead", "backend dev", "customer success manager", "QA engineer", "data analyst", "product owner", "support engineer", "researcher"]


@family("chat-meeting-slot", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="earliest common meeting slot across fixed UTC offsets with working hours and busy blocks, answer in UTC and one local clock")
def gen_slot(rng, n):
    plan = [3, 3, 3, 4, 4, 5, 3, 4]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(300):
            k = 3 if d <= 4 else 4
            people = C.pick_names(rng, k)
            cities = rng.sample(CITIES, k)
            length = rng.choice([30, 45, 60]) if d < 5 else rng.choice([60, 90])
            ws = [(rng.choice([8, 9, 9, 10]) * 60 + rng.choice([0, 30]), rng.choice([16, 17, 18]) * 60 + rng.choice([0, 30])) for _ in range(k)]
            if d == 3:
                ws = [(9 * 60, 17 * 60)] * k
            busy = []
            for p in range(k):
                bl = []
                if d >= 4:
                    cur = ws[p][0]
                    for _ in range(rng.randint(1, 3)):
                        cur += rng.choice([30, 60, 90, 120])
                        if cur + 30 > ws[p][1]:
                            break
                        ln = rng.choice([30, 60, 90])
                        bl.append((cur, min(cur + ln, ws[p][1])))
                        cur += ln
                if d == 5:
                    bl.append((12 * 60, 13 * 60))  # local lunch
                busy.append(sorted(bl))
            # search the UTC day in 15 minute steps
            sol = None
            for st in range(0, 24 * 60 - length + 1, 15):
                ok = True
                for p in range(k):
                    off = cities[p][1]
                    ls, le = st + off, st + off + length
                    # local day window must lie within one local day (same date as working hours)
                    day_shift = (ls // 1440) * 1440
                    ls2, le2 = ls - day_shift, le - day_shift
                    if not (ws[p][0] <= ls2 and le2 <= ws[p][1]):
                        ok = False
                        break
                    if any(not (le2 <= b0 or ls2 >= b1) for b0, b1 in busy[p]):
                        ok = False
                        break
                if ok:
                    sol = st
                    break
            if sol is None:
                continue
            ref = rng.randrange(k)
            loc = (sol + cities[ref][1]) % 1440
            date_ = date(rng.randint(2026, 2027), rng.randint(1, 12), rng.randint(1, 25))
            lines = []
            for p in range(k):
                bl = ", ".join(f"{C.hhmm(a)}-{C.hhmm(b)}" for a, b in busy[p])
                lines.append(f"{people[p]} ({rng.choice(TEAM_ROLES)}, {cities[p][0]}, {_off(cities[p][1])}): works {C.hhmm(ws[p][0])}-{C.hhmm(ws[p][1])} local"
                             + (f"; already booked (local): {bl}" if bl else ""))
            data = C.block("\n".join(lines))
            intro = rng.choice([f"I need to find a call time on {long_date(date_)} (UTC date) for the team below. Nobody should be asked to work outside their local hours, and the call must fit completely inside everyone's working window and not overlap anything they have booked.",
                                f"We are scattered across the world and need one {length}-minute slot on {long_date(date_)} (counted as a UTC day, 00:00 to 24:00 UTC).",
                                f"Scheduling headache: one {length}-minute meeting on {long_date(date_)} UTC, everyone's local details below."])
            ask = (f"What is the earliest {length}-minute slot that works for everybody, starting on a quarter hour? Give the start in UTC as HH:MM UTC, and also the start time on {people[ref]}'s local clock as HH:MM.")
            if d == 5:
                ask += " (The 12:00-13:00 local lunch hour is blocked for everybody too, I have listed it already.)"
            prompt = C.chat(rng, intro, ask, data, C.register_for(rng))
            contains = [f"{C.hhmm(sol)} UTC", C.hhmm(loc)]
            keep = C.unseen(prompt, contains, True)
            if keep is None:
                continue
            gold = f"Earliest slot starts {C.hhmm(sol)} UTC, which is {C.hhmm(loc)} for {people[ref]}."
            yield C.answer_task(f"{i + 1:02d}-{k}p-d{d}", prompt, d, keep, gold, fold=True, tags=["timezones", "scheduling"], notes={"people": k, "len": length})
            break
        else:
            raise RuntimeError("slot: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-cron-next


@functools.lru_cache(maxsize=None)
def _parse_field(f, lo, hi):
    out = set()
    for part in f.split(","):
        step = 1
        if "/" in part:
            part, st = part.split("/")
            step = int(st)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = (int(x) for x in part.split("-"))
        else:
            a = int(part)
            b = hi if step != 1 else a
        out.update(range(a, b + 1, step))
    return out


def cron_matches(expr, dt):
    mi, ho, dom, mon, dw = expr.split()
    if dt.minute not in _parse_field(mi, 0, 59) or dt.hour not in _parse_field(ho, 0, 23) or dt.month not in _parse_field(mon, 1, 12):
        return False
    dm_ok = dt.day in _parse_field(dom, 1, 31)
    dw_ok = ((dt.weekday() + 1) % 7) in _parse_field(dw, 0, 6)
    if dom != "*" and dw != "*":
        return dm_ok or dw_ok
    return dm_ok and dw_ok


def cron_next(expr, after, k):
    out, t = [], after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = after + timedelta(days=400)
    while len(out) < k and t < end:
        if cron_matches(expr, t):
            out.append(t)
        t += timedelta(minutes=1)
    return out


CRONS = {
    1: ["*/20 9-17 * * 1-5", "15 3 * * *", "0 */6 * * *", "30 8 * * 1", "45 23 * * 5", "5 4 1 * *"],
    2: ["*/15 8-11 * * 1-5", "10,40 7-9 * * *", "0 6,18 * * 6,0", "20 5 * * 1,3,5", "0 12 1,15 * *"],
    3: ["10-50/20 22,23 * * *", "5 */8 * 1-6 *", "0,30 9-16/3 * * 1-5", "*/25 0-3 * * 0", "15 2 10-20 * *"],
    4: ["7 4-20/4 * * 2,4", "*/45 6-18/6 * * *", "30 7 */10 * *", "0 9 5 * 1", "20 8 29 * *"],
    5: ["0 8 13 * 5", "30 5 1,15 * 1", "*/50 * 28-31 * 5", "10 */7 1-7 * 1", "15 6 25 * 1"],
}


@family("chat-cron-next", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="when does this crontab line fire next (or how often): ranges, steps, lists, and day-of-month versus weekday semantics")
def gen_cron(rng, n):
    plan = [1, 2, 2, 3, 3, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            expr = rng.choice(CRONS[d])
            after = datetime(rng.randint(2026, 2027), rng.randint(1, 12), rng.randint(1, 27), rng.randint(0, 23), rng.randint(0, 59))
            both = expr.split()[2] != "*" and expr.split()[4] != "*"
            k = 3 if d <= 4 else 4
            fires = cron_next(expr, after, k)
            if len(fires) < k or (fires[-1] - after).days > 120:
                continue
            fmt = lambda t: f"{t:%Y-%m-%d %H:%M}"  # noqa: E731
            what = rng.choice(["a nightly report script", "the invoice export", "a backup job", "the log rotation hack I inherited", "my plant-watering reminder bot"])
            intro = rng.choice([f"I inherited a crontab and one line runs {what}. The line is `{expr}` and the server clock is UTC.",
                                f"quick cron question, the entry for {what} is `{expr}`, machine time is UTC.",
                                f"Can you read this cron expression for me? `{expr}` (it drives {what}, server on UTC)."])
            spec = ""
            if both:
                spec = "On this machine, when both the day-of-month and the day-of-week fields are restricted (not `*`), a day matches if either of them matches. Day-of-week uses 0 = Sunday."
            else:
                spec = "Day-of-week uses 0 = Sunday, 1 = Monday ... 6 = Saturday; ranges are inclusive and `a-b/s` or `*/s` means every s-th value starting from the range start."
            ask = f"It is now {fmt(after)} UTC. List the next {k} times it will run, one per line, as YYYY-MM-DD HH:MM."
            contains = [fmt(t) for t in fires]
            gold = "\n".join(contains)
            prompt = C.chat(rng, intro, ask, None, C.register_for(rng), spec=spec)
            keep = C.unseen(prompt, contains, True, min_keep=k)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-d{d}-{expr.split()[0].replace('*', 'x').replace('/', 's').replace(',', 'c').replace('-', 'r')}", prompt, d, keep, gold, fold=True,
                                tags=["cron", "scheduling"], notes={"expr": expr})
            break
        else:
            raise RuntimeError("cron: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-recurring-events


@family("chat-recurring-events", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="recurring-meeting dates: nth weekdays, every-k-days series, cancelled dates, collections that coincide")
def gen_recur(rng, n):
    plan = [2, 2, 2, 3, 3, 4, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(200):
            kind = {2: "nth", 3: rng.choice(["nth", "every_k"]), 4: rng.choice(["nth_cancel", "every_k_weekend"]), 5: "coincide"}[d]
            reg = C.register_for(rng)
            y = rng.randint(2026, 2027)
            if kind in ("nth", "nth_cancel"):
                wdn = rng.randint(0, 6)
                ords = rng.choice([[1, 3], [2, 4], [1, 2, 3], [2], [1, 3, 5]]) if kind == "nth" else rng.choice([[1, 3], [2, 4], [1, 3, 5]])
                m0 = rng.randint(1, 8)
                span = rng.randint(3, 5)
                ds = []
                for m in range(m0, m0 + span):
                    for o in ords:
                        x = C.nth_weekday(y, m, wdn, o)
                        if x:
                            ds.append(x)
                cancelled = set()
                if kind == "nth_cancel":
                    cancelled = set(rng.sample(ds, 2))
                ds2 = [x for x in ds if x not in cancelled]
                if len(ds2) < 4:
                    continue
                kth = rng.randint(4, len(ds2))
                ordtxt = ", ".join(C.ordinal(o) for o in ords[:-1]) + (" and " if len(ords) > 1 else "") + C.ordinal(ords[-1])
                club = rng.choice(["choir rehearsal", "repair café", "board-game night", "volunteer briefing", "knitting circle"])
                intro = (f"Our {club} is on the {ordtxt} {C.WEEKDAYS[wdn]} of every month, starting with the first one in {C.MONTHS[m0 - 1]} {y}"
                         f" and running for {span} months (the last month is {C.MONTHS[m0 + span - 2]}).")
                spec = ""
                if 5 in ords:
                    spec = "(Months that do not have a fifth one just skip it.) "
                if cancelled:
                    spec += "These sessions are cancelled and do not count as sessions: " + ", ".join(C.iso(x) for x in sorted(cancelled)) + "."
                spec = spec.strip()
                ask = f"How many sessions actually take place, and what is the date of session number {kth} (YYYY-MM-DD)?"
                contains = [str(len(ds2)), C.iso(ds2[kth - 1])]
                gold = f"{len(ds2)} sessions; session {kth} is on {C.iso(ds2[kth - 1])}."
            elif kind == "every_k":
                start = date(y, rng.randint(1, 10), rng.randint(1, 28))
                step = rng.choice([9, 10, 11, 13, 17])
                cnt = rng.randint(10, 16)
                series = [start + timedelta(days=step * j) for j in range(cnt)]
                wk = [x for x in series if x.weekday() >= 5]
                intro = f"I am putting a filter change on the calendar for {long_date(start)} and then every {step} days after that, {cnt} changes in total counting the first. The shop is closed at weekends so I need to see how many land on a Saturday or Sunday."
                spec = ""
                ask = "How many of the changes fall on a weekend, and what is the date of the last change (YYYY-MM-DD)?"
                contains = [str(len(wk)), C.iso(series[-1])]
                gold = f"{len(wk)} on weekends; last change {C.iso(series[-1])}."
                if len(wk) == 0:
                    continue
            else:  # coincide
                wdn = rng.randint(0, 4)
                start = date(y, rng.randint(1, 9), 1)
                start += timedelta(days=(wdn - start.weekday()) % 7)
                a_every, b_every, c_every = 2, rng.choice([3, 4]), rng.choice([5, 6])
                b_off, c_off = rng.randint(0, b_every - 1), rng.randint(0, c_every - 1)
                found = None
                for w in range(0, 150):
                    day = start + timedelta(weeks=w)
                    if w % a_every == 0 and (w - b_off) % b_every == 0 and (w - c_off) % c_every == 0 and w >= max(b_off, c_off):
                        found = day
                        break
                if found is None or found == start:
                    continue
                intro = (f"Our street's bins go out every {C.WEEKDAYS[wdn]}. The recycling truck comes every {a_every} weeks, starting the week of {long_date(start)}. "
                         f"The garden-waste truck comes every {b_every} weeks starting on {long_date(start + timedelta(weeks=b_off))}, and the glass bank is emptied every {c_every} weeks starting on {long_date(start + timedelta(weeks=c_off))}.")
                spec = ""
                ask = "I would love a day when all three collections happen together. What is the first date on which recycling, garden waste and glass all coincide (YYYY-MM-DD)?"
                contains = [C.iso(found)]
                gold = C.iso(found)
            prompt = C.chat(rng, intro, ask, None, reg, spec=spec)
            keep = C.unseen(prompt, contains, True)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, d, keep, gold, fold=True, tags=["calendar", "recurrence"], notes={"kind": kind})
            break
        else:
            raise RuntimeError("recur: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-timesheet-sum


def _fmt_t(m, style):
    h, mi = divmod(m % 1440, 60)
    if style == "ampm":
        suf = "am" if h < 12 else "pm"
        h12 = h % 12 or 12
        return f"{h12}:{mi:02d}{suf}"
    if style == "dot":
        return f"{h}.{mi:02d}"
    if style == "compact":
        return f"{h:02d}{mi:02d}"
    return f"{h:02d}:{mi:02d}"


@family("chat-timesheet-sum", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="add up messy hand-written work-time ranges (am/pm, 24h, compact, overnight, unpaid breaks) and compare to a contract")
def gen_timesheet(rng, n):
    plan = [1, 2, 2, 3, 3, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            style = rng.choice(["ampm", "dot", "compact", "plain"]) if d >= 2 else "plain"
            days = rng.sample(range(7), rng.randint(3, 5) if d >= 3 else rng.randint(2, 3))
            lines, total = [], 0
            for di in sorted(days):
                segs = []
                night = d >= 4 and rng.random() < 0.3 and di < 5
                if night:
                    st = rng.choice([20, 21, 22, 23]) * 60 + rng.choice([0, 15, 30])
                    en = 24 * 60 + rng.choice([5, 6, 7]) * 60 + rng.choice([0, 20, 40])
                    segs = [(st, en)]
                else:
                    cur = rng.choice([7, 8, 9, 10]) * 60 + rng.choice([0, 5, 15, 30, 45])
                    for _ in range(rng.choice([1, 2] if d >= 2 else [1])):
                        ln = rng.randrange(120, 300, 5)
                        segs.append((cur, cur + ln))
                        cur += ln + rng.randrange(30, 75, 5)
                unpaid = rng.choice([0, 0, 15, 30]) if d >= 3 and not night else 0
                mins = sum(b - a for a, b in segs) - unpaid
                total += mins
                if style == "ampm" and any(b >= 24 * 60 for _, b in segs):
                    st2 = "plain"
                else:
                    st2 = style
                txt = ", ".join(f"{_fmt_t(a, st2)}-{_fmt_t(b, st2)}" for a, b in segs)
                if night:
                    txt += " (ends next morning)"
                if unpaid:
                    txt += f" (minus {unpaid} min unpaid)"
                lines.append(f"{C.WEEKDAYS[di][:3]}: {txt}")
            contract = rng.choice([1350, 1500, 1800, 2100, 2250, 2400])
            diff = total - contract
            intro = rng.choice(["I jot my hours down in my phone notes and I need the weekly total for my invoice.",
                                "Here are my hours for last week. I'm paid by the hour and my agency wants one number.",
                                "tracking my hours as a freelancer, honestly my notes are a mess"])
            ask = ("What is the total time worked, written H:MM (for example 31:05)?" if d <= 2 else
                   f"What is the total time worked (H:MM, like 31:05), and by how much is that over or under my {hm(contract)} contracted week (say over or under, then H:MM)?")
            contains = [hm(total)] + ([hm(abs(diff))] if d >= 3 else [])
            gold = f"Total {hm(total)}" + (f"; {'over' if diff > 0 else 'under'} by {hm(abs(diff))}" if d >= 3 else "")
            prompt = C.chat(rng, intro, ask, C.block("\n".join(lines)), C.register_for(rng))
            keep = C.unseen(prompt, contains, True, min_keep=len(contains))
            if keep is None or diff == 0:
                continue
            yield C.answer_task(f"{i + 1:02d}-{style}-d{d}", prompt, d, keep, gold, fold=True, tags=["durations", "parsing"], notes={"style": style})
            break
        else:
            raise RuntimeError("timesheet: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-bus-timetable


def _departures(rules):
    """rules: [(start_min, end_min_inclusive, headway)] consecutive bands; each band's first departure is its start."""
    out = []
    for st, en, hw in rules:
        t = st
        while t <= en:
            out.append(t)
            t += hw
    return out


@family("chat-bus-timetable", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="bus services described by headway bands: first bus after I arrive, riding time, transfers, last-service cut-offs")
def gen_bus(rng, n):
    plan = [2, 2, 2, 3, 3, 4, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(200):
            routes = []
            for r in range(1 if d <= 3 else 2):
                s0 = rng.choice([5, 6]) * 60 + rng.randrange(0, 40, 2)
                hws = [rng.choice([8, 10, 12]), rng.choice([15, 20]), rng.choice([30, 40])]
                ms = [rng.randint(12, 24), rng.randint(14, 24), rng.randint(6, 10)]
                rules, cur = [], s0
                for hw, m in zip(hws, ms):
                    end = cur + hw * m
                    rules.append((cur, end, hw))
                    cur = end + hw
                if rules[-1][1] > 23 * 60 + 55:
                    continue
                routes.append(rules)
            if len(routes) < (1 if d <= 3 else 2):
                continue
            names = [rng.choice(["12", "37", "9A", "21X", "40", "5", "88", "14C", "63"]) for _ in routes]
            if len(set(names)) < len(names):
                continue
            ride = [rng.randint(14, 48) for _ in routes]
            arrive = rng.randint(6 * 60, 22 * 60 + 30)
            deps = [_departures(r) for r in routes]
            if d == 5:
                arrive = rng.choice([22 * 60 + 5, 22 * 60 + 40, 23 * 60 + 10, rng.randint(5 * 60 + 10, 6 * 60)])
            first = next((t for t in deps[0] if t >= arrive), None)
            if first is None:
                if d < 5:
                    continue
                first = deps[0][0] + 1440
            arr1 = first + ride[0]
            if len(routes) == 1:
                contains = [C.hhmm(first), C.hhmm(arr1)]
                ask = "When does the next bus leave after I get to the stop, and when do I get off at my destination? Both as HH:MM on the 24-hour clock."
                gold = f"Bus leaves {C.hhmm(first)}, I arrive {C.hhmm(arr1)}."
                transfer = 0
            else:
                transfer = rng.choice([4, 6, 8])
                ready = arr1 + transfer
                second = next((t for t in deps[1] if t >= ready % 1440), None)
                if second is None:
                    if d < 5:
                        continue
                    second = deps[1][0] + 1440
                second += (ready // 1440) * 1440
                arr2 = second + ride[1]
                contains = [C.hhmm(first), C.hhmm(second), C.hhmm(arr2)]
                ask = "What time does the first bus leave, what time does the second one leave, and when do I finally arrive? All HH:MM, 24-hour."
                gold = f"First bus {C.hhmm(first)}, second bus {C.hhmm(second)}, arrive {C.hhmm(arr2)}."
            lines = []
            for rn, rules in zip(names, routes):
                parts = []
                for st, en, hw in rules:
                    parts.append(f"every {hw} min from {C.hhmm(st)} to {C.hhmm(en)}")
                lines.append(f"Route {rn}: " + "; then ".join(parts))
            if d == 5:
                lines[0] += ". Services restart the next morning on the same pattern."
            tt = "\n".join(lines) + "\n(times are departures from the stop; the last bus of the last band is the final one of the night)"
            rides = ", ".join(f"route {nm} takes {rd} minutes" for nm, rd in zip(names, ride))
            intro = rng.choice(["I'm trying to work out my commute by bus and the timetable leaflet is baffling.",
                                "Going to visit my aunt by bus tomorrow, here is how the timetable is written.",
                                "Can you play timetable decoder for me? The operator publishes these as bands rather than a list."])
            extra = f" I get to the first stop at {C.hhmm(arrive)}"
            if transfer:
                extra += f" and change at a second stop, which needs {transfer} minutes' walking after the first ride before I can board (I can only board a departure at or after that time)."
            else:
                extra += " and can board a departure at that exact minute."
            extra += f" Riding times: {rides}."
            if d == 5:
                extra += " If the last bus has gone, assume I take the first bus of the next morning (it is the first departure of that route's day)."
            ask_full = ask
            prompt = C.chat(rng, intro, ask_full, C.block(tt), C.register_for(rng), spec=extra.strip())
            keep = C.unseen(prompt, contains, True, min_keep=len(contains))
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{len(routes)}route-d{d}", prompt, d, keep, gold, fold=True, tags=["timetable", "durations"], notes={"routes": len(routes)})
            break
        else:
            raise RuntimeError("bus: no instance")
