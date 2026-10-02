"""Event streams read in order: rotated logs with a documented anomaly rule, ledger batches with reversals, move orders applied to a
warehouse state, and chat transcripts where decisions are proposed, countered, decided and sometimes reopened."""
from __future__ import annotations

import datetime as dt

from fx import dd, family

from generators.research import _world as W
from . import _recall as R

# ---------------------------------------------------------------------------------------------------------------- log anomalies

ROUTES = ["/orders", "/tickets", "/sync", "/login", "/export", "/health", "/search", "/upload", "/reports", "/status"]


def _hex(rng, used):
    while True:
        h = "".join(rng.choice("0123456789abcdef") for _ in range(6))
        if h not in used:
            used.add(h)
            return h


@family("recall-log-anomaly", category="recall", lang="text", kind="lookup", n=20, mode="answer",
        summary="the N-th anomalous request (documented rule) across rotated logs, or anomaly counts and the worst route")
def gen_logs(rng, n):
    made = 0
    while made < n:
        org = W.make_org(rng, None, n_people=4)
        tier = R.tier(rng)
        win = None if tier == "easy" else R.window(rng)
        nfiles = rng.choice([2, 3]) if tier == "easy" else rng.choice([3, 4, 5, 6, 8])
        total_lines = rng.choice([140, 180, 220]) if tier == "easy" else max(240, int(R.target_chars(win, rng.choice([1.0, 1.25, 1.5])) / 92))
        per = total_lines // nfiles
        style = rng.choice(["kv", "bracket", "json"])
        thr = rng.choice([800, 900, 1000, 1200, 1500])
        start = dt.datetime(rng.randint(2031, 2034), rng.randint(1, 12), rng.randint(1, 27), rng.randint(0, 6), rng.randint(0, 59), rng.randint(0, 59))
        used: set = set()
        t = start
        recs = []
        for i in range(total_lines):
            t = t + dt.timedelta(seconds=rng.randint(1, 45))
            r = rng.random()
            status = 200 if r < 0.86 else 201 if r < 0.91 else 404 if r < 0.94 else 499 if r < 0.955 else rng.choice([500, 502, 503, 504])
            lat = rng.choice([rng.randint(8, 120), rng.randint(30, 400), rng.randint(60, 700)])
            if rng.random() < 0.035:
                lat = rng.randint(thr + 1, thr + 1800)
            elif rng.random() < 0.02:
                lat = rng.choice([thr, thr - 1, thr - 30])  # near misses: not above the threshold
            recs.append(dict(t=t, req=_hex(rng, used), route=rng.choice(ROUTES), status=status, lat=lat, level="ERROR" if status >= 500 else "WARN" if (status >= 400 or lat > thr * 0.8) else "INFO"))
        files: dict[str, str] = {}
        for fi in range(nfiles):
            chunk = recs[fi * per:(fi + 1) * per] if fi < nfiles - 1 else recs[fi * per:]
            lines = []
            for r in chunk:
                ts = r["t"]
                if style == "kv":
                    lines.append(f"{ts.strftime('%Y-%m-%dT%H:%M:%SZ')} {r['level']} req={r['req']} route={r['route']} lat={r['lat']}ms status={r['status']}")
                elif style == "bracket":
                    lines.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] {r['level']:<5} request {r['req']} {r['route']} -> {r['status']} ({r['lat']} ms)")
                else:
                    lines.append('{"ts":"%s","level":"%s","req":"%s","route":"%s","status":%d,"lat_ms":%d}' % (ts.strftime('%Y-%m-%dT%H:%M:%SZ'), r["level"], r["req"], r["route"], r["status"], r["lat"]))
            age = nfiles - 1 - fi
            files["logs/gateway.log" + (f".{age}" if age else "")] = "\n".join(lines) + "\n"
        files["README.md"] = dd(f"""
            # Gateway logs

            `logs/gateway.log` is the current file; `gateway.log.1` is the one rotated out before it, `.2` before that, and so on
            (a higher number is older). Lines within a file are in time order.

            A request is **anomalous** when its status is 500 or higher, or when its latency is strictly above {thr} ms. Nothing else is.
        """)
        anomalies = [r for r in recs if r["status"] >= 500 or r["lat"] > thr]
        if len(anomalies) < (5 if tier == "easy" else 8):
            continue
        qk = rng.choice(["nth", "nth", "count_file", "route_top"])
        if qk == "nth":
            k = rng.randint(2, min(4 if tier == "easy" else 12, len(anomalies) - 1))
            a = anomalies[k - 1]
            ph = [f"Across all the rotated gateway logs, what is the request id of the {W.ordinal(k)} anomalous request in chronological order? README.md defines anomalous.",
                  f"Count anomalous requests (as defined in the README) from the very beginning of the oldest log onwards. Which request id is number {k}?",
                  f"Which request was the {W.ordinal(k)} anomaly overall, oldest first? I need its id."]
            prompt, contains, gold = rng.choice(ph), [a["req"]], f"Request {a['req']} was anomaly number {k}."
            diff = 2 + (k >= 7) + (nfiles >= 5) + (tier == "hard")
        elif qk == "count_file":
            age = rng.randint(0, nfiles - 1)
            name = "gateway.log" + (f".{age}" if age else "")
            fi = nfiles - 1 - age
            chunk = recs[fi * per:(fi + 1) * per] if fi < nfiles - 1 else recs[fi * per:]
            cnt = sum(1 for r in chunk if r["status"] >= 500 or r["lat"] > thr)
            ins, c = W.numfmt(rng, cnt, ("Count", "Total", "Answer"))
            ph = [f"How many anomalous requests (per the README) are in `logs/{name}`?{ins}",
                  f"In {name} alone, count the anomalous requests as the README defines them.{ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"{cnt} in {name}. {c}"
            diff = 1 + (tier != "easy") + (win is not None and win <= 12000)
        else:
            cnt = {}
            for r in anomalies:
                cnt[r["route"]] = cnt.get(r["route"], 0) + 1
            top = sorted(cnt.items(), key=lambda kv: -kv[1])
            if len(top) > 1 and top[0][1] == top[1][1]:
                continue
            ph = ["Which route has the most anomalous requests over all the logs? Give the route path.",
                  "Looking at every log file, which route do the anomalies (README definition) concentrate on? Reply with the path."]
            prompt, contains, gold = rng.choice(ph), [top[0][0]], f"{top[0][0]} has the most anomalies ({top[0][1]})."
            diff = 3 + (nfiles >= 6) + (tier == "hard")
            if top[0][0] in prompt:
                continue
        made += 1
        yield W.say_task(slug=f"{made:02d}-{qk.replace('_', '-')}", prompt=W.voice(rng, org, prompt), difficulty=min(5, diff), start=files, contains=contains, gold=gold,
                         context_window=win, tags=["logs", "haystack"], notes={"lines": total_lines, "files": nfiles, "style": style, "threshold": thr, "question": qk})


# ---------------------------------------------------------------------------------------------------------------- running balance

def cents(s: int) -> str:
    sign = "-" if s < 0 else ""
    s = abs(s)
    return f"{sign}{s // 100}.{s % 100:02d}"


@family("recall-running-balance", category="recall", lang="text", kind="lookup", n=18, mode="answer",
        summary="final or as-of balance of an account after transfers, deposits, fees and reversals spread over dozens of ledger batches")
def gen_balance(rng, n):
    made = 0
    while made < n:
        org = W.make_org(rng, None, n_people=4)
        tier = R.tier(rng)
        win = None if tier == "easy" else R.window(rng)
        n_acc = rng.randint(4, 6) if tier == "easy" else rng.randint(6, 9)
        accs = [f"AC-{x}" for x in rng.sample(range(1000, 9999), n_acc)]
        bal = {a: rng.randint(0, 900000) for a in accs}
        opening = dict(bal)
        nbatches = rng.choice([5, 7, 9]) if tier == "easy" else (rng.choice([18, 26, 36, 48]) if (win or 12000) <= 16000 else 60)
        per = 5 if tier == "easy" else max(6, int(R.target_chars(win, rng.choice([1.0, 1.25, 1.5])) / nbatches / 52))
        dates = W.rand_dates(rng, nbatches, dt.date(2031, 1, 1), dt.date(2031, 12, 28), distinct=False)
        files: dict[str, str] = {}
        trf: dict[int, tuple] = {}
        next_t = rng.randint(100, 400)
        snapshots: dict[dt.date, dict] = {}
        for bi, d in enumerate(dates):
            lines = [f"LEDGER BATCH {bi + 1:02d}  ({W.d_iso(d)})"]
            for _ in range(rng.randint(per // 2 + 2, per + 3)):
                r = rng.random()
                a, b = rng.sample(accs, 2)
                if r < 0.5:
                    amt = rng.randint(500, 90000)
                    next_t += rng.randint(1, 3)
                    trf[next_t] = (a, b, amt, False)
                    bal[a] -= amt
                    bal[b] += amt
                    lines.append(f"TRF {next_t:04d} {a} -> {b} : {cents(amt)}")
                elif r < 0.7:
                    amt = rng.randint(500, 60000)
                    bal[a] += amt
                    lines.append(f"DEP {a} +{cents(amt)}")
                elif r < 0.85:
                    amt = rng.choice([150, 250, 500, 1200, 2500])
                    bal[a] -= amt
                    lines.append(f"FEE {a} -{cents(amt)}")
                else:
                    live = [k for k, v in trf.items() if not v[3]]
                    if live:
                        k = rng.choice(live[-12:])
                        sa, sb, amt, _ = trf[k]
                        trf[k] = (sa, sb, amt, True)
                        bal[sa] += amt
                        bal[sb] -= amt
                        lines.append(f"REVERSE TRF {k:04d}")
            lines.append("# " + W.filler_line(rng, org))
            files[f"ledger/{W.d_iso(d)}-batch-{bi + 1:02d}.txt"] = "\n".join(lines) + "\n"
            snapshots[d] = dict(bal)
            snapshots[(d, bi)] = dict(bal)
        files["opening.csv"] = W.csv_text(["account", "opening_balance"], [[a, cents(opening[a])] for a in accs])
        files["README.md"] = dd("""
            # Ledger batches

            `opening.csv` holds the opening balances (credits). `ledger/` has one file per batch, named with the batch date and
            number; process them in that order (date, then batch number), top to bottom.

            * `TRF n A -> B : x` moves x from A to B (transfer number n);
            * `DEP A +x` and `FEE A -x` add or subtract;
            * `REVERSE TRF n` undoes transfer n completely (both accounts) at the point where it appears.

            Balances may go negative. Amounts are credits with two decimals.
        """)
        qk = rng.choice(["final", "final", "asof", "top"])
        if qk == "final":
            a = rng.choice(accs)
            v = cents(bal[a])
            ph = [f"What is the final balance of account {a} after every ledger batch has been applied? Credits, two decimals (a minus sign if negative).",
                  f"Work out where {a} ends up: opening balance plus everything in the ledger batches (reversals included). Two decimals."]
            prompt, contains, gold = rng.choice(ph), [v], f"{a} ends at {v} credits."
            diff = 2 + (nbatches >= 26) + (tier == "hard")
        elif qk == "asof":
            bi = rng.randrange(max(1, nbatches // 3), nbatches)
            d = sorted(dates)[bi]
            # snapshot at the end of batch number (in processing order) bi: recompute by the processing order = sorted by (date, batch number)
            order = sorted(range(nbatches), key=lambda i: (dates[i], i))
            target = order[bi]
            snap = snapshots[(dates[target], target)]
            a = rng.choice(accs)
            v = cents(snap[a])
            ph = [f"What was the balance of {a} right after batch {target + 1:02d} (dated {W.d_iso(dates[target])}) was applied? Credits, two decimals.",
                  f"After processing everything up to and including batch {target + 1:02d}, what does {a} hold?"]
            prompt, contains, gold = rng.choice(ph), [v], f"After batch {target + 1:02d}, {a} holds {v}."
            diff = 3 + (nbatches >= 26)
        else:
            best = sorted(bal.items(), key=lambda kv: -kv[1])
            if best[0][1] == best[1][1]:
                continue
            ph = ["Which account has the highest balance once all ledger batches are applied? Give the account number.",
                  "After the whole ledger, which account is richest? (account id only)"]
            prompt, contains, gold = rng.choice(ph), [best[0][0]], f"{best[0][0]} is highest."
            diff = 2 + (nbatches >= 26)
        if any(c in prompt for c in contains):
            continue
        made += 1
        yield W.say_task(slug=f"{made:02d}-{qk}", prompt=W.voice(rng, org, prompt), difficulty=min(5, diff), start=files, contains=contains, gold=gold, context_window=win,
                         tags=["ledger", "state"], notes={"batches": nbatches, "accounts": n_acc, "question": qk})


# ---------------------------------------------------------------------------------------------------------------- move orders

@family("recall-state-orders", category="recall", lang="text", kind="lookup", n=18, mode="answer",
        summary="final shelf of a crate, or the crates on a rack, after dozens of move/swap/scrap orders (some cancelled) applied in date order")
def gen_orders(rng, n):
    made = 0
    while made < n:
        org = W.make_org(rng, None, n_people=6)
        tier = R.tier(rng)
        win = None if tier == "easy" else R.window(rng)
        racks = rng.sample("ABCDEFGH", rng.choice([4, 5, 6]))
        shelves = [f"{r}{row}-{slot:02d}" for r in racks for row in (1, 2, 3) for slot in range(1, 5)]
        ncr = rng.randint(14, 22)
        crates = [f"C-{x:04d}" for x in rng.sample(range(1, 9999), ncr + 10)]
        state = {}
        free = set(shelves)
        for c in crates[:ncr]:
            s = rng.choice(sorted(free))
            free.discard(s)
            state[c] = s
        initial = dict(state)
        nord = rng.choice([5, 7, 10]) if tier == "easy" else (rng.choice([24, 34, 46, 60]) if (win or 12000) <= 16000 else 70)
        kb_o = 0.3 if tier == "easy" else max(0.4, R.target_chars(win, rng.choice([1.0, 1.25, 1.5])) / 1000 / nord)
        dates = sorted(W.rand_dates(rng, nord, dt.date(2031, 1, 1), dt.date(2031, 12, 28), distinct=False))
        files: dict[str, str] = {}
        extra_crate = ncr
        nums = sorted(rng.sample(range(100, 999), nord))
        for i, d in enumerate(dates):
            lines = []
            cancelled = rng.random() < 0.1
            tmp = dict(state)
            tfree = set(free)
            for _ in range(rng.randint(1, 3)):
                r = rng.random()
                if r < 0.55 and tmp:
                    c = rng.choice(sorted(tmp))
                    dst = rng.choice(sorted(tfree))
                    lines.append(f"MOVE {c} from {tmp[c]} to {dst}")
                    tfree.add(tmp[c])
                    tfree.discard(dst)
                    tmp[c] = dst
                elif r < 0.7 and len(tmp) >= 2:
                    a, b = rng.sample(sorted(tmp), 2)
                    lines.append(f"SWAP {a} (on {tmp[a]}) with {b} (on {tmp[b]})")
                    tmp[a], tmp[b] = tmp[b], tmp[a]
                elif r < 0.85 and tmp:
                    c = rng.choice(sorted(tmp))
                    lines.append(f"SCRAP {c} from {tmp[c]} (damaged)")
                    tfree.add(tmp[c])
                    del tmp[c]
                elif extra_crate < len(crates) and tfree:
                    c = crates[extra_crate]
                    extra_crate += 1
                    dst = rng.choice(sorted(tfree))
                    lines.append(f"RECEIVE {c} into {dst}")
                    tfree.discard(dst)
                    tmp[c] = dst
            if not lines:
                continue
            text = f"MOVE ORDER MO-{nums[i]}\nDate: {W.d_iso(d)}\nIssued by: {rng.choice(org.people).full}\n\n" + "\n".join(lines) + "\n\nRemarks:\n" + R.chatter(rng, org, kb_o) + "\n"
            files[f"orders/MO-{nums[i]}.txt"] = text
            if cancelled:
                files[f"orders/MO-{nums[i]}-CANCEL.txt"] = f"CANCELLATION\nDate: {W.d_iso(d)}\n\nMove order MO-{nums[i]} is cancelled in full and must not be carried out.\n"
            else:
                state, free = tmp, tfree
        files["initial-state.csv"] = W.csv_text(["crate", "shelf"], [[c, s] for c, s in sorted(initial.items())])
        files["README.md"] = dd("""
            # Warehouse move orders

            `initial-state.csv` is the stock position before the first order. Each file in `orders/` is a move order dated inside the
            file; apply orders in date order (same day: by order number). A cancellation file voids the whole order it names,
            which then never happened (later orders were written with that in mind). `MOVE` relocates a crate,
            `SWAP` exchanges two crates' shelves, `SCRAP` removes a crate, `RECEIVE` adds a new one.
        """)
        qk = rng.choice(["where", "where", "rack_count", "on_shelf"])
        if qk == "where":
            cands = sorted(state)
            c = rng.choice(cands)
            v = state[c]
            ph = [f"Where is crate {c} after all the move orders? Give the shelf code.",
                  f"Which shelf holds {c} at the end of the order stream (cancelled orders ignored)?"]
            prompt, contains, gold = rng.choice(ph), [v], f"{c} is on shelf {v}."
            diff = 1 + (nord >= 24) + (nord >= 46) + (c in initial and initial[c] != state[c])
        elif qk == "rack_count":
            rk = rng.choice(racks)
            cnt = sum(1 for s in state.values() if s.startswith(rk))
            ins, cc = W.numfmt(rng, cnt, ("Count", "Total", "Answer"))
            ph = [f"How many crates are on rack {rk} once every order has been applied?{ins}",
                  f"Count the crates that sit on rack {rk} (shelf codes starting with {rk}) at the end.{ins}"]
            prompt, contains, gold = rng.choice(ph), [cc], f"{cnt} crates. {cc}"
            diff = 3 + (nord >= 24) + (nord >= 46)
        else:
            occupied = sorted(set(state.values()))
            s = rng.choice(occupied)
            c = next(k for k, v in state.items() if v == s)
            ph = [f"Which crate is on shelf {s} at the end of all the orders? Give the crate id.",
                  f"What is sitting on shelf {s} after the last order is applied? Crate id please."]
            prompt, contains, gold = rng.choice(ph), [c], f"Crate {c} is on {s}."
            diff = 2 + (nord >= 24) + (nord >= 46)
        if any(x in prompt for x in contains):
            continue
        made += 1
        yield W.say_task(slug=f"{made:02d}-{qk.replace('_', '-')}", prompt=W.voice(rng, org, prompt), difficulty=min(5, diff), start=files, contains=contains, gold=gold,
                         context_window=win, tags=["state", "orders"], notes={"orders": nord, "crates": ncr, "question": qk})


# ---------------------------------------------------------------------------------------------------------------- chat decisions

TOPICS = [
    ("the room for the Friday review", "{w} Room"),
    ("the caterer for the open day", "{w} Catering"),
    ("the venue for the summer party", "the {w} Hall"),
    ("the supplier for the new signage", "{w} Signs"),
    ("the name of the autumn campaign", "Project {w}"),
    ("the coach company for the staff outing", "{w} Coaches"),
]


def _topic_thread(rng, org, topic, opt_fmt, chair, others):
    words = rng.sample(W.NAME_WORDS, 3)
    opts = [opt_fmt.format(w=w) for w in words]
    p1, p2, p3 = rng.sample(others, 3)
    msgs = []  # (offset minutes, speaker, text)
    t = 0
    msgs.append((t, p1, f"For {topic} I'd suggest {opts[0]}."))
    t += rng.randint(3, 25)
    msgs.append((t, p2, rng.choice([f"Hmm, what about {opts[1]} instead?", f"I'd rather go with {opts[1]}, it's cheaper.", f"{opts[0]} is booked already I think. Could we try {opts[1]}?"])))
    t += rng.randint(2, 30)
    if rng.random() < 0.6:
        msgs.append((t, p3, f"I'll back {opts[1]}." if rng.random() < 0.6 else f"Or {opts[2]}? Just throwing it out."))
        t += rng.randint(2, 30)
    final = opts[1] if rng.random() < 0.6 else (opts[0] if rng.random() < 0.5 else opts[2])
    # the final option must have been proposed by someone in the thread
    if final == opts[2] and not any(opts[2] in m[2] for m in msgs):
        msgs.append((t, p3, f"What about {opts[2]}?"))
        t += rng.randint(2, 20)
    msgs.append((t, chair, f"DECIDED: {topic} is {final}."))
    return opts, final, msgs, (p1, p2, p3)


@family("recall-chat-decisions", category="recall", lang="text", kind="lookup", n=18, mode="answer",
        summary="what was finally decided, who first proposed it, or when, from dozens of chat logs where decisions are countered and sometimes reopened")
def gen_chat(rng, n):
    made = 0
    while made < n:
        org = W.make_org(rng, None, n_people=8)
        tier = R.tier(rng)
        win = None if tier == "easy" else R.window(rng)
        chair = org.people[0]
        others = org.people[1:]
        nfiles = rng.choice([6, 8, 10]) if tier == "easy" else (rng.choice([18, 24, 32, 42]) if (win or 12000) <= 16000 else 56)
        kb = 0.6 if tier == "easy" else max(0.8, R.target_chars(win, rng.choice([1.0, 1.25, 1.5])) / 1000 / nfiles)
        lo = W.base_date(rng)
        days = sorted(W.rand_dates(rng, nfiles, lo, lo + dt.timedelta(days=rng.randint(60, 150)), distinct=True))
        per_day: dict[dt.date, list] = {d: [] for d in days}
        topics = rng.sample(TOPICS, rng.choice([1, 2]) if tier == "easy" else rng.choice([2, 3, 4]))
        truth = {}
        # two near-duplicate topics: "Friday review" and "Monday review" style
        for ti, (topic, fmt) in enumerate(topics):
            opts, final, msgs, who = _topic_thread(rng, org, topic, fmt, chair, others)
            i = rng.randrange(max(1, nfiles - 6))
            d0 = days[i]
            for off, sp, tx in msgs:
                per_day[d0].append((off, sp, tx))
            decided_day = d0
            reopened = rng.random() < 0.35 and i + 3 < nfiles
            if reopened:
                j = rng.randint(i + 2, nfiles - 1)
                alt = rng.choice([o for o in opts if o != final])
                d1 = days[j]
                per_day[d1].append((rng.randint(0, 100), others[0], f"Can we revisit {topic}? {alt} turned out to be available after all."))
                per_day[d1].append((rng.randint(101, 200), chair, f"DECIDED: {topic} is {alt}. This replaces the earlier decision."))
                final = alt
                decided_day = d1
            # first proposer of the final option: earliest message mentioning it as a suggestion
            first = None
            for off, sp, tx in sorted(per_day[d0], key=lambda m: m[0]):
                if final in tx and "DECIDED" not in tx:
                    first = sp
                    break
            if first is None:
                first = next((sp for off, sp, tx in sorted(per_day[days[j]], key=lambda m: m[0]) if final in tx and "DECIDED" not in tx), None) if reopened else None
            truth[topic] = dict(final=final, day=decided_day, first=first, topic=topic)
        files: dict[str, str] = {}
        for d in days:
            msgs = per_day[d]
            lines = []
            chatter_n = max(5, int(kb * 1000 / 105 * rng.uniform(0.8, 1.2)))
            for _ in range(chatter_n):
                sp = rng.choice(org.people)
                lines.append((rng.randint(0, 600), sp, W.filler_line(rng, org, lo, lo + dt.timedelta(days=150)).replace("The ", "the ", 1)))
            allm = sorted(msgs + lines, key=lambda m: m[0])
            base_min = 8 * 60 + 30
            out = [f"#team-chat {W.d_iso(d)}"]
            for off, sp, tx in allm:
                mm = base_min + off
                out.append(f"[{mm // 60:02d}:{mm % 60:02d}] {sp.first}: {tx}")
            files[f"chat/{W.d_iso(d)}.log"] = "\n".join(out) + "\n"
        files["README.md"] = dd("""
            # Team chat export

            One log per day in `chat/`, times are local. Decisions are recorded by the chair (the person whose messages start with
            `DECIDED:`); when the same topic is decided more than once, the latest `DECIDED:` line stands. People are shown by first name.
        """)
        t = rng.choice(list(truth.values()))
        qk = rng.choice(["final", "final", "first", "day"])
        if qk == "final":
            ph = [f"What did the team finally decide about {t['topic']}?", f"Going by the chat logs, what is the final decision on {t['topic']}?"]
            prompt, contains, gold = rng.choice(ph), [t["final"].replace("the ", "")], f"The final decision on {t['topic']}: {t['final']}."
            diff = 1 + (nfiles >= 18) + (nfiles >= 32) + (len(topics) >= 3)
        elif qk == "first":
            if t["first"] is None:
                continue
            ph = [f"Who first suggested the option that was finally chosen for {t['topic']}? First name only.", f"For {t['topic']}, who put forward the option that ended up being decided (the first person to suggest it)?"]
            prompt, contains, gold = rng.choice(ph), [t["first"].first], f"{t['first'].first} first suggested it."
            diff = 2 + (nfiles >= 18) + (nfiles >= 32) + (len(topics) >= 3)
        else:
            ph = [f"On which date was the final decision about {t['topic']} made? YYYY-MM-DD.", f"What day does the latest `DECIDED:` line on {t['topic']} carry? ISO date please."]
            prompt, contains, gold = rng.choice(ph), [W.d_iso(t["day"])], f"{W.d_iso(t['day'])}."
            diff = 2 + (nfiles >= 18) + (nfiles >= 32)
        if any(c in prompt for c in contains):
            continue
        made += 1
        yield W.say_task(slug=f"{made:02d}-{qk}", prompt=W.voice(rng, org, prompt), difficulty=min(5, diff), start=files, contains=contains, gold=gold, context_window=win,
                         tags=["chat", "decisions"], notes={"days": nfiles, "topics": len(topics), "question": qk})
