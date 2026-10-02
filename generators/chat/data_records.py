"""Reading logs, JSON, SQL and patches: structured data is generated first, the question is answered from the structure."""
from __future__ import annotations

import difflib
import json
import sqlite3
import statistics
from datetime import datetime, timedelta
from fractions import Fraction

from fx import family

from . import _common as C

# --------------------------------------------------------------------------------------------------------------------
# chat-log-read

PATHS = ["/api/orders", "/api/search", "/api/login", "/api/cart", "/api/profile", "/api/export", "/static/app.js"]
UNAMES = ["kim", "tomas", "ayla", "bram", "noor", "ines", "paolo", "yuki", "leif", "sade", "omar", "greta", "ravi", "elin"]


def _rid(rng):
    return "".join(rng.choice("0123456789abcdef") for _ in range(6))


def _fmt_line(r, style):
    ts = r["ts"]
    if style == "kv":
        return f"{ts:%Y-%m-%dT%H:%M:%S}Z method={r['method']} path={r['path']} status={r['status']} ms={r['ms']} user={r['user']} req={r['req']}"
    if style == "json":
        return json.dumps({"ts": f"{ts:%Y-%m-%dT%H:%M:%SZ}", "method": r["method"], "path": r["path"], "status": r["status"], "ms": r["ms"], "user": r["user"], "req": r["req"]}, separators=(",", ":"))
    ip = f"10.0.{abs(hash(r['user'])) % 7 if False else (ord(r['user'][0]) % 7)}.{ord(r['user'][-1]) % 200 + 10}"
    return f"{ip} - {r['user']} [{ts:%d/%b/%Y:%H:%M:%S} +0000] \"{r['method']} {r['path']} HTTP/1.1\" {r['status']} {r['ms'] * 37} {r['ms']}ms req={r['req']}"


def _make_log(rng, N, inject):
    t = datetime(2026, rng.randint(1, 12), rng.randint(1, 27), rng.randint(0, 22), rng.randint(0, 50), rng.randint(0, 59))
    users = rng.sample(UNAMES, rng.randint(5, 8))
    recs = []
    for _ in range(N):
        t += timedelta(seconds=rng.randint(1, 45))
        p = rng.choice(PATHS)
        st = rng.choices([200, 200, 200, 200, 304, 404, 500, 503, 401], k=1)[0]
        ms = rng.randint(12, 180) if st < 400 else rng.randint(20, 400)
        if st == 401 and p != "/api/login":
            p = "/api/login"
        recs.append(dict(ts=t, method="POST" if p == "/api/login" else rng.choice(["GET", "GET", "GET", "POST"]), path=p, status=st, ms=ms, user=rng.choice(users), req=_rid(rng)))
    if "outage" in inject:
        i0 = rng.randint(2, max(3, N // 2))
        k = rng.randint(3, 5)
        base = recs[i0]["ts"]
        # replace a run of health checks
        step = rng.choice([15, 20, 30])
        hs = []
        for j in range(-2, k + 3):
            ts = base + timedelta(seconds=step * j)
            ok = not (0 <= j < k)
            hs.append(dict(ts=ts, method="GET", path="/health", status=200 if ok else 503, ms=rng.randint(3, 20) if ok else rng.randint(900, 3000), user="probe", req=_rid(rng)))
        recs = [r for r in recs if r["path"] != "/health"] + hs
    if "brute" in inject:
        for u in rng.sample(users, 2):
            base = recs[rng.randint(0, N - 1)]["ts"]
            for j in range(rng.randint(3, 4)):
                recs.append(dict(ts=base + timedelta(seconds=7 * j), method="POST", path="/api/login", status=401, ms=rng.randint(40, 90), user=u, req=_rid(rng)))
            recs.append(dict(ts=base + timedelta(seconds=40), method="POST", path="/api/login", status=200, ms=rng.randint(60, 120), user=u, req=_rid(rng)))
    recs.sort(key=lambda r: (r["ts"], r["req"]))
    return recs


@family("chat-log-read", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="answer questions from pasted or attached request logs (kv, JSON lines, access-log style): counts, windows, medians, outages, rate spikes")
def gen_log(rng, n):
    plan = [1, 2, 2, 3, 3, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(300):
            kind = {1: ["count5xx"], 2: ["count5xx", "path_status"], 3: ["window", "slowest", "distinct_err"], 4: ["median", "outage", "brute"], 5: ["rate_window", "outage_file"]}[d]
            kind = rng.choice(kind)
            style = rng.choice(["kv", "json", "access"])
            as_file = d >= 4 or (d == 3 and rng.random() < 0.5)
            N = rng.randint(120, 260) if as_file else rng.randint(14, 22)
            inject = []
            if kind in ("outage", "outage_file"):
                inject.append("outage")
            if kind == "brute":
                inject.append("brute")
            recs = _make_log(rng, N if kind not in ("outage", "outage_file", "brute") or not as_file else N, inject)
            if len(recs) < 8:
                continue
            first, last = recs[0]["ts"], recs[-1]["ts"]
            body = "\n".join(_fmt_line(r, style) for r in recs)
            P = rng.choice([r["path"] for r in recs if r["path"] not in ("/health",)])
            contains = []
            if kind == "count5xx":
                v = sum(1 for r in recs if r["status"] >= 500)
                ask = "How many of these requests got a 5xx status (500 or above)?"
                contains = [str(v)]
                if v == 0:
                    continue
                gold = str(v)
            elif kind == "path_status":
                S = rng.choice([200, 404, 401, 503])
                v = sum(1 for r in recs if r["path"] == P and r["status"] == S)
                if v == 0:
                    continue
                ask = f"How many requests to {P} ended with status {S}?"
                contains = [str(v)]
                gold = str(v)
            elif kind == "window":
                a = first + (last - first) * rng.uniform(0.15, 0.4)
                b = first + (last - first) * rng.uniform(0.6, 0.9)
                a, b = a.replace(microsecond=0), b.replace(microsecond=0)
                v = sum(1 for r in recs if r["path"] == P and r["status"] == 200 and a <= r["ts"] <= b)
                if v == 0:
                    continue
                ask = (f"Between {a:%H:%M:%S} and {b:%H:%M:%S} (both ends included, all in UTC on the same day shown), how many requests to {P} returned status 200? "
                       f"(If the log spans midnight, the day is the one the first line belongs to.)")
                if first.date() != last.date():
                    continue
                contains = [str(v)]
                gold = str(v)
            elif kind == "slowest":
                oks = [r for r in recs if r["path"] == P and r["status"] == 200]
                if len(oks) < 2:
                    continue
                oks.sort(key=lambda r: (-r["ms"], r["req"]))
                if oks[0]["ms"] == oks[1]["ms"]:
                    continue
                ask = f"What was the slowest successful (status 200) request to {P}: how many milliseconds did it take" + (", and what was its req id?" if as_file else "?")
                contains = [str(oks[0]["ms"])] + ([oks[0]["req"]] if as_file else [])
                gold = f"{oks[0]['ms']} ms" + (f", req {oks[0]['req']}" if as_file else "")
            elif kind == "distinct_err":
                users = {r["user"] for r in recs if r["status"] >= 500}
                if not users:
                    continue
                ask = "How many different users (the user field) hit at least one 5xx?" + " (Ignore the 'probe' user if there is one.)" if any(r["user"] == "probe" for r in recs) else "How many different users (the user field) hit at least one 5xx?"
                users.discard("probe")
                if not users:
                    continue
                contains = [str(len(users))]
                gold = str(len(users))
            elif kind == "median":
                vals = sorted(r["ms"] for r in recs if r["path"] == P and r["status"] == 200)
                if len(vals) < 6:
                    continue
                med = statistics.median(vals)
                ms = f"{med:.1f}" if len(vals) % 2 == 0 else str(int(med))
                ask = f"What is the median latency in ms of the status-200 requests to {P}? (If there is an even number of them, take the average of the two middle values and give one decimal; otherwise a whole number.)"
                contains = [ms]
                gold = ms
            elif kind in ("outage", "outage_file"):
                hs = [r for r in recs if r["path"] == "/health"]
                bad = [r for r in hs if r["status"] == 503]
                if not bad:
                    continue
                t0 = bad[0]["ts"]
                rec_ = next((r for r in hs if r["ts"] > t0 and r["status"] == 200), None)
                if rec_ is None:
                    continue
                sec = int((rec_["ts"] - t0).total_seconds())
                ask = ("The /health probe returned 503 for a while. How many seconds passed between the first 503 and the first 200 after it? Also, how many 503s did /health return in total?")
                contains = [str(sec), str(len(bad))]
                gold = f"{sec} seconds; {len(bad)} 503s"
            elif kind == "brute":
                lg = [r for r in recs if r["path"] == "/api/login"]
                cnt = 0
                for u in {r["user"] for r in lg}:
                    seq = [r["status"] for r in lg if r["user"] == u]
                    run = 0
                    hit = False
                    for s_ in seq:
                        if s_ == 401:
                            run += 1
                        else:
                            if s_ == 200 and run >= 3:
                                hit = True
                            run = 0
                    cnt += hit
                if cnt == 0:
                    continue
                ask = "How many users failed to log in (401 on /api/login) at least three times in a row and then logged in successfully (200 on /api/login) on their very next login attempt?"
                contains = [str(cnt)]
                gold = str(cnt)
            else:  # rate_window
                buckets = {}
                for r in recs:
                    k = r["ts"].replace(second=0)
                    b = buckets.setdefault(k, [0, 0])
                    b[0] += 1
                    b[1] += r["status"] >= 500
                found = None
                for k in sorted(buckets):
                    tot, er = buckets[k]
                    if tot >= 5 and Fraction(er, tot) >= Fraction(2, 5):
                        found = (k, tot, er)
                        break
                if found is None:
                    continue
                k, tot, er = found
                ask = ("Group the requests into one-minute buckets by the minute of the timestamp. What is the first bucket (give it as HH:MM) in which at least 5 requests arrived "
                       "and at least 40% of them were 5xx, and how many requests were in that bucket?")
                contains = [f"{k:%H:%M}", str(tot)]
                gold = f"{k:%H:%M}, {tot} requests ({er} errors)"
            story = rng.choice(["the checkout service during this morning's incident", "our API gateway after the deploy", "the staging box we were load-testing", "an old internal tool nobody maintains"])
            intro = rng.choice([f"Here are logs from {story}. Times are UTC.", f"I'm going through logs from {story} and need one number.", f"log excerpt from {story}, can you read it for me? timestamps are UTC"])
            reg = C.register_for(rng)
            if as_file:
                prompt = C.chat(rng, intro + " The log is in logs/service.log.", ask + C.nosep(contains), None, reg)
                start = {"logs/service.log": body + "\n"}
            else:
                prompt = C.chat(rng, intro, ask + C.nosep(contains), C.block(body), reg)
                start = None
            keep = C.unseen(prompt, contains, True, min_keep=len(contains))
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}-{style}", prompt, d, keep, gold, fold=True, start=start, tags=["logs", "parsing"], notes={"kind": kind, "style": style, "lines": len(recs)})
            break
        else:
            raise RuntimeError("log: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-json-read

SKUS = ["TEA-100", "TEA-250", "MUG-BLU", "MUG-RED", "FILT-01", "KETL-2L", "SPN-WD", "TIN-GRN", "HONEY-S", "HONEY-L", "CAKE-ST", "BOOK-TEA", "SCALE-9", "BAG-LIN", "CLOTH-4"]
STATUSES = ["shipped", "shipped", "shipped", "pending", "cancelled"]


@family("chat-json-read", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="answer from a pasted or attached JSON export of orders: revenue with per-line discounts, cancelled orders, distinct SKUs, best customer")
def gen_json(rng, n):
    plan = [1, 2, 2, 3, 3, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(300):
            kind = {1: ["order_qty"], 2: ["cancel_count"], 3: ["revenue", "distinct_sku"], 4: ["best_customer", "revenue_month"], 5: ["two_part"]}[d]
            kind = rng.choice(kind)
            as_file = d >= 4
            N = rng.randint(30, 55) if as_file else rng.randint(4, 7)
            custs = rng.sample(C.FIRST, 8 if as_file else 4)
            orders = []
            for k in range(N):
                items = []
                for _ in range(rng.randint(1, 4 if d >= 3 else 3)):
                    it = {"sku": rng.choice(SKUS), "qty": rng.randint(1, 6), "unit_cents": rng.choice([450, 799, 1250, 1999, 2400, 3500])}
                    if d >= 3 and rng.random() < 0.3:
                        it["discount_pct"] = rng.choice([5, 10, 20])
                    items.append(it)
                orders.append({"id": f"A{1000 + k * 7 + rng.randint(0, 6)}", "customer": rng.choice(custs), "placed": f"2026-{rng.randint(1, 3):02d}-{rng.randint(1, 28):02d}",
                               "status": rng.choice(STATUSES) if d >= 2 else "shipped", "items": items})
            orders.sort(key=lambda o: o["id"])

            def line_cents(it):
                return it["qty"] * it["unit_cents"] * (100 - it.get("discount_pct", 0))  # x1/100

            def order_total(o):
                return sum(line_cents(it) for it in o["items"])  # in cents*100
            if kind == "order_qty":
                o = rng.choice(orders)
                v = sum(it["qty"] for it in o["items"])
                ask = f"How many units in total are in order {o['id']}?"
                contains = [str(v)]
                gold = str(v)
            elif kind == "cancel_count":
                cc = sum(1 for o in orders if o["status"] == "cancelled")
                units = sum(it["qty"] for o in orders if o["status"] == "cancelled" for it in o["items"])
                if cc == 0:
                    continue
                ask = "How many orders are cancelled, and how many units were in those cancelled orders altogether?"
                contains = [str(cc), str(units)] if str(units) != str(cc) else [str(units)]
                gold = f"{cc} orders, {units} units"
            elif kind == "revenue":
                tot = sum(order_total(o) for o in orders if o["status"] != "cancelled")
                cents = Fraction(tot, 100)
                if cents.denominator != 1:
                    cents = C.cents_half_up(cents)
                else:
                    cents = int(cents)
                ask = ("What is the total revenue of all orders that are not cancelled (so shipped and pending), in dollars and cents? "
                       "Each line is quantity times unit_cents, less discount_pct percent when present; unit_cents is in cents, and round once at the very end.")
                contains = [C.money(cents)]
                gold = C.money(cents)
            elif kind == "distinct_sku":
                skus = {it["sku"] for o in orders if o["status"] == "shipped" for it in o["items"]}
                ask = "How many different SKUs appear across the shipped orders only?"
                contains = [str(len(skus))]
                gold = str(len(skus))
            elif kind == "best_customer":
                rev = {}
                for o in orders:
                    if o["status"] == "shipped":
                        rev[o["customer"]] = rev.get(o["customer"], 0) + order_total(o)
                top = sorted(rev.items(), key=lambda kv: (-kv[1], kv[0]))
                if len(top) < 2 or top[0][1] == top[1][1]:
                    continue
                cents = C.cents_half_up(Fraction(top[0][1], 100))
                ask = ("Which customer has the highest total over their shipped orders (line = quantity times unit_cents, less discount_pct percent when present), "
                       "and how much is that in dollars and cents?")
                contains = [top[0][0], C.money(cents)]
                gold = f"{top[0][0]}: {C.money(cents)}"
            elif kind == "revenue_month":
                m = rng.randint(1, 3)
                sel = [o for o in orders if o["status"] != "cancelled" and o["placed"].startswith(f"2026-{m:02d}")]
                if len(sel) < 3:
                    continue
                tot = C.cents_half_up(Fraction(sum(order_total(o) for o in sel), 100))
                ask = (f"For orders placed in 2026-{m:02d} that are not cancelled, how many orders is that and what is their combined value in dollars and cents "
                       f"(line = quantity times unit_cents, less discount_pct percent when present, rounded once at the end)?")
                contains = [C.money(tot), f"{len(sel)} orders"] if False else [C.money(tot)]
                gold = f"{len(sel)} orders, {C.money(tot)}"
            else:  # two_part
                units = {}
                for o in orders:
                    if o["status"] == "shipped":
                        for it in o["items"]:
                            units[it["sku"]] = units.get(it["sku"], 0) + it["qty"]
                top = sorted(units.items(), key=lambda kv: (-kv[1], kv[0]))
                if top[0][1] == top[1][1]:
                    continue
                shipped = [o for o in orders if o["status"] == "shipped"]
                avg = Fraction(sum(order_total(o) for o in shipped), 100 * len(shipped))
                avg_c = C.cents_half_up(avg)
                ask = ("Two things for the shipped orders only: which SKU sold the most units overall (and how many units), and what is the average order value in dollars and cents "
                       "(line = quantity times unit_cents, less discount_pct percent when present; average over shipped orders, rounded to the cent at the end)?")
                contains = [top[0][0], str(top[0][1]), C.money(avg_c)]
                gold = f"{top[0][0]} with {top[0][1]} units; average order {C.money(avg_c)}"
            txt = '{"orders": [\n' + ",\n".join("  " + json.dumps(o, separators=(", ", ": ")) for o in orders) + "\n]}"
            intro = rng.choice(["Here's an export from our little shop's order system.", "I pulled this JSON out of the storefront admin and need a number from it.", "Can you read this order export for me?"])
            reg = C.register_for(rng)
            if as_file:
                prompt = C.chat(rng, intro + " It's saved as orders.json.", ask, None, reg)
                start = {"orders.json": txt + "\n"}
            else:
                prompt = C.chat(rng, intro, ask, C.block(txt), reg)
                start = None
            keep = C.unseen(prompt, contains, True, min_keep=len(contains))
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, d, keep, gold, fold=True, start=start, tags=["json", "reading"], notes={"kind": kind, "orders": N})
            break
        else:
            raise RuntimeError("json: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-sql-reading

DEPTS = ["ops", "design", "sales", "legal", "support", "infra"]


def _run_sql(tables, query):
    con = sqlite3.connect(":memory:")
    for name, (cols, rows) in tables.items():
        con.execute(f"CREATE TABLE {name} ({', '.join(cols)})")
        con.executemany(f"INSERT INTO {name} VALUES ({', '.join('?' * len(cols))})", rows)
    cur = con.execute(query)
    res = cur.fetchall()
    con.close()
    return res


def _tbl_text(name, cols, rows):
    head = [c.split()[0] for c in cols]
    body = [["NULL" if v is None else v for v in r] for r in rows]
    return f"{name}\n" + C.table(body, head)


@family("chat-sql-reading", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="what does this SQL return on these pasted tables (NULL traps, LEFT JOIN filters, many-to-many joins, COUNT(col), HAVING); sqlite is the oracle")
def gen_sql(rng, n):
    plan = [2, 2, 2, 3, 3, 4, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(300):
            kind = {2: ["count_null", "group_having"], 3: ["left_filter", "count_col", "union"], 4: ["many_many", "above_avg", "limit_offset"], 5: ["left_on_vs_where", "not_in_null", "distinct_pairs"]}[d]
            kind = rng.choice(kind)
            names = C.pick_names(rng, 9)
            if kind in ("count_null", "count_col", "above_avg", "group_having", "limit_offset"):
                staff = [(k + 1, names[k], rng.choice(DEPTS), rng.choice([None, rng.randrange(3000, 6500, 100), rng.randrange(3000, 6500, 100)])) for k in range(rng.randint(6, 9))]
                tables = {"staff": (["id", "name", "dept", "salary"], staff)}
                if kind == "count_null" or kind == "count_col":
                    q = "SELECT COUNT(*), COUNT(salary), AVG(salary) FROM staff"
                    res = _run_sql(tables, q)[0]
                    if res[1] == res[0] or res[1] == 0:
                        continue
                    avgs = f"{res[2]:.1f}"
                    ask = "What does this query return? Give me the three numbers in order (the average to one decimal place)."
                    gold = f"{res[0]}, {res[1]}, {avgs}"
                    contains = [f"{res[0]}", f"{res[1]}", avgs]
                elif kind == "group_having":
                    q = "SELECT dept, COUNT(*) AS n FROM staff GROUP BY dept HAVING COUNT(*) >= 2 ORDER BY dept"
                    res = _run_sql(tables, q)
                    if len(res) < 2:
                        continue
                    ask = "What rows does it return? Write each as dept:count, one per line, in the order returned."
                    contains = [f"{a}:{b}" for a, b in res]
                    gold = "\n".join(contains)
                elif kind == "above_avg":
                    q = ("SELECT COUNT(*) FROM staff s WHERE salary > (SELECT AVG(salary) FROM staff WHERE dept = s.dept)")
                    res = _run_sql(tables, q)[0][0]
                    if res == 0:
                        continue
                    ask = "What single number does it return? (Remember how SQL treats NULLs in AVG and in comparisons.)"
                    contains = [str(res)]
                    gold = str(res)
                    if len({r[2] for r in staff}) == len(staff):
                        continue
                else:  # limit_offset
                    q = "SELECT salary FROM staff WHERE salary IS NOT NULL ORDER BY salary DESC LIMIT 1 OFFSET 2"
                    rr = _run_sql(tables, q)
                    if not rr:
                        continue
                    ask = "What single value does it return?"
                    contains = [str(rr[0][0])]
                    gold = str(rr[0][0])
            elif kind in ("left_filter", "left_on_vs_where", "many_many", "not_in_null", "distinct_pairs"):
                ppl = [(k + 1, names[k]) for k in range(rng.randint(5, 7))]
                visits = [(rng.randint(1, len(ppl)), rng.choice([2025, 2026]), rng.choice(["north", "south", None])) for _ in range(rng.randint(6, 10))]
                tables = {"person": (["id", "name"], ppl), "visit": (["pid", "year", "site"], visits)}
                if kind == "left_filter":
                    q = "SELECT COUNT(*) FROM person p LEFT JOIN visit v ON v.pid = p.id WHERE v.year = 2026"
                    ask = "What single number does it return?"
                elif kind == "left_on_vs_where":
                    q = "SELECT COUNT(*) FROM person p LEFT JOIN visit v ON v.pid = p.id AND v.year = 2026"
                    ask = "What single number does it return? (Careful: where the year condition sits matters here.)"
                elif kind == "many_many":
                    tables["badge"] = (["pid", "colour"], [(rng.randint(1, len(ppl)), rng.choice(["red", "blue", "green"])) for _ in range(rng.randint(5, 8))])
                    q = "SELECT COUNT(*) FROM visit v JOIN badge b ON b.pid = v.pid"
                    ask = "How many rows does it return?"
                elif kind == "not_in_null":
                    q = "SELECT COUNT(*) FROM person WHERE id NOT IN (SELECT pid FROM visit WHERE site = 'north')"
                    tables["visit"] = (["pid", "year", "site"], [(v[0], v[1], v[2]) for v in visits])
                    ask = "What single number does it return?"
                else:
                    q = "SELECT COUNT(*) FROM (SELECT DISTINCT pid, year FROM visit)"
                    ask = "What single number does it return?"
                res = _run_sql(tables, q)[0][0]
                if res == 0:
                    continue
                contains = [str(res)]
                gold = str(res)
            else:  # union
                a = [(rng.randint(1, 9),) for _ in range(rng.randint(5, 8))]
                b = [(rng.randint(1, 9),) for _ in range(rng.randint(5, 8))]
                tables = {"morning": (["slot"], a), "evening": (["slot"], b)}
                q = "SELECT slot FROM morning UNION SELECT slot FROM evening"
                res = len(_run_sql(tables, q))
                q2 = "SELECT slot FROM morning UNION ALL SELECT slot FROM evening"
                res2 = len(_run_sql(tables, q2))
                q = f"-- A\n{q};\n-- B\n{q2};"
                ask = "How many rows does query A return, and how many does query B return? (A first.)"
                contains = [f"{res}", f"{res2}"]
                if res == res2:
                    continue
                gold = f"A: {res}, B: {res2}"
                contains = [f"{res}", f"{res2}"]
            data = "\n\n".join(_tbl_text(nm, cols, rows) for nm, (cols, rows) in tables.items()) + "\n\nQuery:\n" + q
            intro = rng.choice(["I'm debugging a report and I want to know what this SQL returns on the sample data below before I run it for real.",
                                "Settle a disagreement on our team: what will this query give on these rows?", "SQL quiz from my new colleague, I think it's a trick question."])
            if kind == "union":
                data = "\n\n".join(_tbl_text(nm, cols, rows) for nm, (cols, rows) in tables.items()) + "\n\nQueries:\n" + q
            prompt = C.chat(rng, intro + " (SQLite semantics.)", ask, C.block(data), C.register_for(rng))
            keep = C.unseen(prompt, contains, True, min_keep=len(contains))
            if keep is None and kind not in ("count_null", "count_col"):
                continue
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, d, keep, gold, fold=True, tags=["sql", "reading"], notes={"kind": kind})
            break
        else:
            raise RuntimeError("sql: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-diff-apply

CFG = {"retries": ["2", "3", "5"], "timeout_ms": ["250", "500", "1200"], "cache_ttl": ["60", "300", "900"], "max_conn": ["20", "40", "100"],
       "log_level": ["info", "warn", "debug"], "region": ["eu-west", "us-east", "ap-south"], "workers": ["4", "8", "16"], "backoff": ["1.5", "2", "2.5"],
       "batch": ["32", "64", "128"], "flush_s": ["5", "15", "30"], "pool": ["10", "20"], "tls": ["on", "off"], "proxy": ["none", "edge-1", "edge-2"],
       "shards": ["4", "12", "16"], "quota": ["500", "1000", "5000"], "burst": ["10", "20", "50"]}
CFG_KEYS = list(CFG)
CFG_VALS = sorted({v for vs in CFG.values() for v in vs})


def _val(rng, key):
    return rng.choice(CFG[key.split("_x")[0].rstrip("_0123456789") if key not in CFG else key] if (key in CFG or key.split("_x")[0] in CFG) else CFG_VALS)


@family("chat-diff-apply", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="apply a pasted unified diff in your head: how long is the file now, on which line is X, how many lines mention Y")
def gen_diff(rng, n):
    plan = [2, 2, 2, 3, 3, 4, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(300):
            N = {2: 12, 3: 16, 4: 22, 5: 30}[d]
            keys = rng.sample(CFG_KEYS, min(N, len(CFG_KEYS)))
            lines = []
            sect = 0
            for k in range(N):
                if k % 6 == 0:
                    lines.append(f"[section_{chr(97 + sect)}]")
                    sect += 1
                else:
                    base = keys[k % len(keys)]
                    kk = base if k < len(keys) else f"{base}_{k}"
                    lines.append(f"{kk} = {rng.choice(CFG[base])}")
            new = list(lines)
            nedit = {2: 2, 3: 3, 4: 4, 5: 5}[d]
            for _ in range(nedit):
                op = rng.choice(["replace", "insert", "delete", "insert2"])
                pos = rng.randrange(1, len(new))
                if op == "replace" and not new[pos].startswith("["):
                    kk = new[pos].split(" = ")[0]
                    base = kk.split("_x")[0]
                    base = base if base in CFG else next((b for b in CFG if kk.startswith(b)), "retries")
                    new[pos] = f"{kk} = {rng.choice(CFG[base])}"
                elif op in ("insert", "insert2"):
                    for _j in range(1 if op == "insert" else 2):
                        base = rng.choice(CFG_KEYS)
                        new.insert(pos, f"{base}_x{rng.randint(1, 99)} = {rng.choice(CFG[base])}")
                elif op == "delete" and not new[pos].startswith("["):
                    del new[pos]
            if new == lines:
                continue
            diff = list(difflib.unified_diff(lines, new, "a/service.conf", "b/service.conf", n=1, lineterm=""))
            if len(diff) < 5:
                continue
            target_key = rng.choice([ln.split(" = ")[0] for ln in new if " = " in ln])
            if sum(1 for ln in new if ln.startswith(target_key + " =")) != 1:
                continue
            kind = rng.choice(["len", "lineno", "count_val"] if d >= 3 else ["len", "lineno"])
            if kind == "len":
                v = len(new)
                ask = "How many lines does the file have after the patch is applied?"
                contains = [str(v)]
            elif kind == "lineno":
                v = next(j + 1 for j, ln in enumerate(new) if ln.startswith(target_key + " ="))
                ask = f"After the patch is applied, on which line number (counting from 1) does the `{target_key}` setting sit?"
                contains = [str(v)]
            else:
                val = rng.choice(CFG_VALS)
                v = sum(1 for ln in new if ln.endswith(f"= {val}"))
                if v == 0:
                    continue
                ask = f"After the patch is applied, how many lines end with `= {val}`?"
                contains = [str(v)]
            as_file = d >= 4
            intro = rng.choice(["A teammate sent me a patch for our service config and I want to know what the file looks like afterwards before I apply it.",
                                "I have the old config and the diff for a change request, and I don't want to apply it just to count lines.",
                                "Reviewing a config diff. I need one fact about the result."])
            reg = C.register_for(rng)
            dtxt = "\n".join(diff)
            if as_file:
                prompt = C.chat(rng, intro + " The current file is service.conf in this folder, and here is the diff:", ask, C.block(dtxt), reg)
                start = {"service.conf": "\n".join(lines) + "\n"}
            else:
                prompt = C.chat(rng, intro + " The current file:", ask, C.block("\n".join(lines)) + "\n\nand the diff:\n\n" + C.block(dtxt), reg)
                start = None
            keep = C.unseen(prompt, contains, True)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, d, keep, str(v), fold=True, start=start, tags=["diff", "reading"], notes={"kind": kind, "edits": nedit})
            break
        else:
            raise RuntimeError("diff: no instance")
