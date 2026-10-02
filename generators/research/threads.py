"""Purchase-approval email threads: approvals by people who are not authorised, retractions, delegations, rejections.
Final decisions are computed by replaying each thread under the policy file. Answer mode."""
from __future__ import annotations

import datetime as dt

from fx import dd, family

from . import _world as W

ROLES = [("Team Lead", 0, 500), ("Operations Manager", 501, 5000), ("Director", 5001, 10**9)]
ITEMS = ["a replacement compressor", "two folding tables", "a label printer", "ten safety harnesses", "a pallet truck", "annual licence renewal", "a used van",
         "scaffold hire for a month", "new signage", "a pressure washer", "a refrigerated cabinet", "a set of calibration weights", "twelve office chairs",
         "an air-quality monitor", "a mobile generator", "a laminator", "thermal paper (case of 40)", "a heavy-duty shredder"]
APPROVE = ["Approved.", "Approved, go ahead.", "OK from me, approved.", "I approve this.", "Approved. Please file the invoice under the usual code."]
REJECT = ["I'm declining this one.", "Not approved. Please look for a cheaper option.", "Rejected: not in this year's plan.", "No, I won't approve this."]
RETRACT = ["Please disregard my earlier approval; the quote has changed.", "I'm withdrawing my approval until we have a second quote.", "Hold on, my approval above is withdrawn pending the budget check."]
COMMENT = ["Sounds sensible to me.", "Is that within the budget line?", "We could borrow one from the other site instead.", "+1, we really need it.", "Do we know the delivery time?"]
LOOSE_OK = ["Fine by me, approved!", "Looks good, approved from my side.", "Approved (for what it's worth)."]


def holders(rng, org, d0, d1):
    """role -> (default holder, [(delegate, from, to)])"""
    ppl = rng.sample(org.people, 6)
    out = {}
    for i, (r, _, _) in enumerate(ROLES):
        deleg = []
        if rng.random() < 0.7:
            a = d0 + dt.timedelta(days=rng.randint(20, 150))
            deleg.append((ppl[3 + i], a, a + dt.timedelta(days=rng.randint(10, 40))))
        out[r] = (ppl[i], deleg)
    return out, ppl


def holder_on(h, role, d):
    default, deleg = h[role]
    for who, a, b in deleg:
        if a <= d <= b:
            return who
    return default


def role_for(amount: int) -> str:
    return next(r for r, lo, hi in ROLES if lo <= amount <= hi)


def gen_thread(rng, org, h, ppl, d_start, req_no, scenario):
    amount = rng.choice([rng.randint(60, 500), rng.randint(520, 4800), rng.randint(5200, 24000)])
    amount = round(amount, -1)
    role = role_for(amount)
    item = rng.choice(ITEMS)
    requester = rng.choice([p for p in org.people if p not in ppl[:6]] or org.people)
    deleg = h[role][1]
    if scenario in ("early-delegate", "holder-during-cover"):
        if not deleg:
            scenario = "simple"
        else:
            a = deleg[0][1]
            d_start = a - dt.timedelta(days=rng.randint(3, 5)) if scenario == "early-delegate" else a + dt.timedelta(days=rng.randint(1, 3))
    msgs = []  # (date, time, sender, kind, text)
    d = d_start
    t = lambda: W.hhmm(rng, 8, 17)
    msgs.append([d, t(), requester, "ask", f"Hi all,\n\nCould we buy {item}? The quote is {amount} credits. Reference REQ-{req_no:04d}.\n\nThanks,\n{requester.first}"])
    d += dt.timedelta(days=rng.randint(0, 2))
    if rng.random() < 0.7:
        msgs.append([d, t(), rng.choice(org.people), "comment", rng.choice(COMMENT)])
    def auth_on(dd_):
        return holder_on(h, role, dd_)
    d += dt.timedelta(days=rng.randint(0, 3))
    if scenario == "simple":
        who = auth_on(d)
        msgs.append([d, t(), who, rng.choice(["approve", "reject"]), None])
    elif scenario == "loose":
        other = rng.choice([p for p in org.people if p is not auth_on(d) and p is not requester])
        msgs.append([d, t(), other, "approve_unauth", rng.choice(LOOSE_OK)])
        d += dt.timedelta(days=rng.randint(1, 4))
        msgs.append([d, t(), auth_on(d), rng.choice(["reject", "approve", "approve"]), None])
    elif scenario == "retract":
        who = auth_on(d)
        msgs.append([d, t(), who, "approve", None])
        d += dt.timedelta(days=rng.randint(1, 4))
        msgs.append([d, t(), who, "retract", rng.choice(RETRACT)])
        if rng.random() < 0.75:
            d += dt.timedelta(days=rng.randint(2, 8))
            msgs.append([d, t(), auth_on(d), rng.choice(["approve", "reject"]), None])
    elif scenario == "wrong-band":
        lower = ROLES[max(0, [r for r, _, _ in ROLES].index(role) - 1)][0] if role != ROLES[0][0] else None
        if lower:
            msgs.append([d, t(), holder_on(h, lower, d), "approve_unauth", "Approved from me."])
            d += dt.timedelta(days=rng.randint(2, 6))
        who = auth_on(d)
        msgs.append([d, t(), who, rng.choice(["approve", "reject", "approve"]), None])
    elif scenario == "early-delegate":
        deleg_who, a, b = deleg[0]
        # the delegate answers before the cover period starts (not yet authorised), then again once covering
        d = a - dt.timedelta(days=rng.randint(1, 2))
        msgs.append([d, t(), deleg_who, "approve", None])
        d = a + dt.timedelta(days=rng.randint(0, 3))
        msgs.append([d, t(), deleg_who, rng.choice(["approve", "reject"]), None])
    elif scenario == "holder-during-cover":
        deleg_who, a, b = deleg[0]
        d = max(d, a)
        msgs.append([d, t(), h[role][0], rng.choice(["approve", "reject"]), None])  # the usual holder, but on leave: not valid
        d += dt.timedelta(days=rng.randint(1, 3))
        if d <= b:
            msgs.append([d, t(), deleg_who, rng.choice(["approve", "reject"]), None])
    else:
        who = auth_on(d)
        msgs.append([d, t(), who, rng.choice(["approve", "reject"]), None])
    # same-day messages must be in time order
    prev = None
    for m in msgs:
        if prev is not None and m[0] == prev[0] and m[1] <= prev[1]:
            hh, mm = map(int, prev[1].split(":"))
            tot = min(23 * 60 + 50, hh * 60 + mm + rng.randint(7, 50))
            m[1] = f"{tot // 60:02d}:{tot % 60:02d}"
        prev = m
    # decide texts and final outcome
    out = []
    final = None  # (who, date, status)
    for date, time, who, kind, text in msgs:
        if kind in ("approve", "reject"):
            if text is None:
                text = rng.choice(APPROVE if kind == "approve" else REJECT)
            if who is holder_on(h, role, date):
                final = (who, date, "approved" if kind == "approve" else "rejected")
        elif kind == "retract":
            if who is holder_on(h, role, date):
                final = None
        out.append((date, time, who, text))
    return dict(no=req_no, amount=amount, role=role, item=item, msgs=out, final=final, requester=requester)


README_POLICY = dd("""
    # Purchasing policy (extract)

    Any purchase needs an approval from the post-holder for its amount band on the day the approval is given:

    | amount (credits) | who approves |
    |---|---|
    | up to 500 | Team Lead |
    | 501 to 5000 | Operations Manager |
    | over 5000 | Director |

    Approvals are given by email reply on the request thread (every request has a reference REQ-nnnn). Approval or rejection by
    anyone else, however friendly, does not count. A post-holder may withdraw an approval with a later message; a withdrawn
    approval counts as no decision. The decision in force is the last non-withdrawn approval or rejection by the right post-holder.
    `staff.txt` says who holds each post, including temporary cover (an acting post-holder has the full authority during their
    cover period, dates inclusive).
""")


def build(rng, n_req: int):
    org = W.make_org(rng, None, n_people=11)
    d0 = W.base_date(rng)
    d1 = d0 + dt.timedelta(days=240)
    h, ppl = holders(rng, org, d0, d1)
    lines = [f"{org.name}: post-holders", ""]
    for r, _, _ in ROLES:
        default, deleg = h[r]
        lines.append(f"{r}: {default.full}")
        for who, a, b in deleg:
            lines.append(f"  acting {r}: {who.full} from {W.d_long(a)} to {W.d_long(b)}")
    reqs = []
    scen = ["simple", "loose", "retract", "wrong-band", "early-delegate", "holder-during-cover"]
    for i in range(n_req):
        d = d0 + dt.timedelta(days=rng.randint(10, 220))
        reqs.append(gen_thread(rng, org, h, ppl, d, 100 + i * 7 + rng.randint(0, 5), rng.choice(scen)))
    files = {"policy.md": README_POLICY, "staff.txt": "\n".join(lines) + "\n"}
    for r in reqs:
        parts = []
        first = r["msgs"][0]
        subj = f"REQ-{r['no']:04d}: {r['item']} ({r['amount']} credits)"
        for date, time, who, text in r["msgs"]:
            parts.append(W.email(org, who, [h[r['role']][0] if who is not h[r['role']][0] else r['requester']], date, ("Re: " if parts else "") + subj, text, time=time))
        files[f"requests/REQ-{r['no']:04d}.eml"] = W.thread(parts)
    W.pad_files(rng, org, files, rng.randint(2, 6), "notes", d0, d1)
    return org, reqs, files


@family("research-thread-approvals", category="research", lang="text", kind="lookup", n=16, mode="answer",
        summary="who finally decided purchase requests under a policy with bands, delegation, withdrawn and unauthorised approvals")
def gen(rng, n):
    made = 0
    while made < n:
        n_req = rng.choice([4, 6, 8, 10])
        org, reqs, files = build(rng, n_req)
        decided = [r for r in reqs if r["final"]]
        if len(decided) < 2:
            continue
        qk = rng.choice(["who", "who", "count", "sum"])
        if qk == "who":
            r = rng.choice(decided)
            who, date, st = r["final"]
            ph = [f"Under the purchasing policy, who made the decision in force on REQ-{r['no']:04d} and on what date? Give the surname and the date as YYYY-MM-DD, and finish with a line `Outcome: <granted or refused>`.",
                  f"I need the audit line for request REQ-{r['no']:04d}: the decider's surname and the date of the decision (ISO), then a last line `Outcome: <granted or refused>`. Only valid decisions count; see policy.md."]
            prompt, contains = rng.choice(ph), [who.last, W.d_iso(date), "Outcome: " + ("granted" if st == "approved" else "refused")]
            gold = f"REQ-{r['no']:04d}: decided by {who.full} on {W.d_iso(date)}.\nOutcome: " + ("granted" if st == "approved" else "refused")
            diff = 2 + (len(r["msgs"]) >= 4) + (n_req >= 8)
        elif qk == "count":
            k = sum(1 for r in reqs if r["final"] and r["final"][2] == "approved")
            ins, c = W.numfmt(rng, k, ("Count", "Total", "Answer"))
            ph = [f"How many of the purchase requests in this folder are validly approved at the end of their threads (policy.md applies)?{ins}",
                  f"Count the requests whose decision in force is an approval by the right post-holder. Requests with no valid decision or a rejection don't count.{ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"{k} requests. {c}"
            diff = 3 + (n_req >= 8)
        else:
            tot = sum(r["amount"] for r in reqs if r["final"] and r["final"][2] == "approved")
            if tot == 0:
                continue
            ins, c = W.numfmt(rng, tot)
            ph = [f"What is the total value, in credits, of all requests that are validly approved (decision in force = approval by the proper post-holder)?{ins}",
                  f"Add up the quoted amounts of every request that ended up properly approved. Credits, a single number.{ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"The approved total is {tot} credits. {c}"
            diff = 4 + (n_req >= 8)
        made += 1
        yield W.say_task(slug=f"{made:02d}-{qk}", prompt=W.voice(rng, org, prompt), difficulty=min(5, diff), start=files, contains=contains, gold=gold,
                         tags=["email-threads", "policy"], notes={"requests": n_req, "question": qk})
