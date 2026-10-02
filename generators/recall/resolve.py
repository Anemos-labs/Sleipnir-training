"""Resolve-by-reading: multi-parent configuration profiles with unset and per-environment sections, constants traced through a small
Python package (imports, env defaults, late overrides, definition-time defaults), and a price/tax/discount join across CSV piles."""
from __future__ import annotations

import datetime as dt

from fx import dd, family

from generators.research import _world as W
from . import _recall as R

# ---------------------------------------------------------------------------------------------------------------- profiles

KEYS = ["pool_size", "retry_limit", "cache_ttl", "batch_rows", "http_timeout", "queue_depth", "shard_count", "page_size", "log_budget", "flush_ms"]
ENVS = ["dev", "staging", "prod", "canary", "eu", "apac"]
UNSET = object()


def make_profiles(rng, n_prof: int, keys: list[str], envs: list[str]):
    names = []
    while len(names) < n_prof:
        w = rng.choice(W.NAME_WORDS).lower() + str(rng.randint(1, 9))
        if w not in names:
            names.append(w)
    profs = {}
    for i, nm in enumerate(names):
        earlier = names[:i]
        ext = rng.sample(earlier, min(len(earlier), rng.choice([0, 1, 1, 2, 2, 3]))) if earlier else []
        own = {}
        for k in rng.sample(keys, rng.randint(0, 3)):
            own[k] = UNSET if rng.random() < 0.15 else rng.randint(1000, 9999)
        env_sec = {}
        if rng.random() < 0.5:
            for e in rng.sample(envs, rng.randint(1, 2)):
                sec = {}
                for k in rng.sample(keys, rng.randint(1, 2)):
                    sec[k] = UNSET if rng.random() < 0.12 else rng.randint(1000, 9999)
                env_sec[e] = sec
        profs[nm] = dict(extends=ext, own=own, env=env_sec)
    return names, profs


def resolve(profs, name, env):
    p = profs[name]
    cur: dict = {}
    for par in p["extends"]:
        cur.update(resolve(profs, par, env))
    cur.update(p["own"])
    if env in p["env"]:
        cur.update(p["env"][env])
    return cur


def effective(profs, defaults, name, env, key):
    v = resolve(profs, name, env).get(key, UNSET)
    return defaults.get(key) if v is UNSET else v


def depth(profs, name):
    ex = profs[name]["extends"]
    return 0 if not ex else 1 + max(depth(profs, e) for e in ex)


def render_profile(rng, org, nm, p, kb):
    lines = [f"# profile {nm}", f"# owner: {rng.choice(org.people).full}"]
    if p["extends"]:
        lines.append("extends = " + ", ".join(p["extends"]))
    for k, v in p["own"].items():
        lines.append(f"unset {k}" if v is UNSET else f"{k} = {v}")
    for e, sec in p["env"].items():
        lines.append(f"[env {e}]")
        for k, v in sec.items():
            lines.append(f"unset {k}" if v is UNSET else f"{k} = {v}")
    pad = R.chatter(rng, org, kb).split("\n")
    out = []
    for ln in lines:
        out.append(ln)
        if rng.random() < 0.4 and pad:
            out.append("# " + pad.pop().strip())
    out.extend("# " + x for x in pad[:max(0, len(pad))] if x.strip())
    return "\n".join(out) + "\n"


@family("recall-profile-resolve", category="recall", lang="text", kind="lookup", n=18, mode="answer",
        summary="effective value of a setting for a profile that extends several parents, with unset and per-environment sections")
def gen_profile(rng, n):
    made = 0
    while made < n:
        org = W.make_org(rng, None, n_people=6)
        tier = R.tier(rng)
        win = None if tier == "easy" else R.window(rng)
        n_prof = rng.choice([5, 6, 8]) if tier == "easy" else rng.choice([14, 18, 24, 30])
        kb = 0.4 if tier == "easy" else max(0.6, R.target_chars(win, rng.choice([1.0, 1.25, 1.5])) / 1000 / n_prof)
        keys = rng.sample(KEYS, 6)
        envs = rng.sample(ENVS, 4)
        names, profs = make_profiles(rng, n_prof, keys, envs)
        defaults = {k: rng.randint(100, 999) for k in keys}  # three digits vs four for explicit values: never equal
        cands = [nm for nm in names if depth(profs, nm) >= (1 if tier == "easy" else 2)]
        if not cands:
            continue
        tgt = rng.choice(cands)
        env = rng.choice(envs)
        key = rng.choice(keys)
        val = effective(profs, defaults, tgt, env, key)
        # interesting only if the value comes from more than the target file itself, and from an explicit setting or an unset fallback
        own_direct = key in profs[tgt]["own"] or key in profs[tgt]["env"].get(env, {})
        if own_direct and rng.random() < 0.8:
            continue
        files = {f"profiles/{nm}.cfg": render_profile(rng, org, nm, profs[nm], kb) for nm in names}
        files["defaults.cfg"] = "# values used when a profile never sets the key (or unsets it)\n" + "".join(f"{k} = {v}\n" for k, v in defaults.items())
        files["README.md"] = dd("""
            # Profiles

            `defaults.cfg` gives the base value of every key. A profile in `profiles/` is resolved for an environment like this:

            1. resolve each profile named in `extends = a, b, ...` first, in the order listed (a later parent overrides an earlier one);
            2. then apply the profile's own top-level `key = value` lines, then the `[env NAME]` section for the requested environment (if
               it has one); within a profile later lines win;
            3. `unset key` takes the key back to its value in `defaults.cfg` at that point (later settings can still override it).

            A parent is resolved for the same environment as its child. The effective value of a key is its resolved value, or the
            `defaults.cfg` value if nothing set it.
        """)
        d = depth(profs, tgt)
        ph = [f"What is the effective value of `{key}` for the `{tgt}` profile in the `{env}` environment? README.md has the resolution rules.",
              f"Resolve the `{tgt}` profile for `{env}` and tell me what `{key}` ends up as.",
              f"We deploy `{tgt}` to `{env}`. Which `{key}` does it get once extends, unsets and env sections are all taken into account?"]
        made += 1
        yield W.say_task(slug=f"{made:02d}-depth{d}", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=min(5, 1 + (d >= 1) + (d >= 2) + (d >= 4) + (tier == "hard")), start=files,
                         contains=[str(val)], gold=f"`{key}` is {val} for {tgt} in {env}.", context_window=win, tags=["config", "inheritance"],
                         notes={"profiles": n_prof, "depth": d, "key": key, "env": env})


# ---------------------------------------------------------------------------------------------------------------- code constants

FILLER_FUNCS = [
    ("def {n}(rows):\n    \"\"\"Group rows by their first field.\"\"\"\n    out = {{}}\n    for r in rows:\n        out.setdefault(r[0], []).append(r)\n    return out\n"),
    ("def {n}(values, width={w}):\n    \"\"\"Split values into chunks of ``width``.\"\"\"\n    return [values[i:i + width] for i in range(0, len(values), width)]\n"),
    ("def {n}(text):\n    \"\"\"Collapse runs of blanks and trim the ends.\"\"\"\n    return \" \".join(text.split())\n"),
    ("def {n}(a, b):\n    \"\"\"Merge two dicts; b wins.\"\"\"\n    out = dict(a)\n    out.update(b)\n    return out\n"),
    ("def {n}(items, key):\n    \"\"\"Stable sort by key, ties keep input order.\"\"\"\n    return sorted(items, key=key)\n"),
    ("class {C}:\n    \"\"\"Tiny counter used by the report helpers.\"\"\"\n\n    def __init__(self):\n        self.n = 0\n\n    def hit(self, k={w}):\n        self.n += k\n        return self.n\n"),
]


def filler_module(rng, org, kb: float) -> str:
    out = ['"""' + W.filler_line(rng, org) + '"""', "", "import os", ""]
    size = 0
    while size < kb * 1000:
        t = rng.choice(FILLER_FUNCS)
        n = rng.choice(["group", "chunk", "squash", "merge", "order", "tally", "bucket", "fold", "split", "gather"]) + "_" + rng.choice(["rows", "items", "lines", "parts", "keys"]) + str(rng.randint(1, 99))
        txt = t.format(n=n, C=n.title().replace("_", ""), w=rng.randint(2, 60))
        out.append(txt)
        size += len(txt)
        if rng.random() < 0.3:
            c = f"{rng.choice(['PAGE', 'LIMIT', 'WINDOW', 'BATCH', 'SLOTS'])}_{rng.choice(['SIZE', 'MAX', 'COUNT'])}{rng.randint(1, 9)} = {rng.randint(2, 500)}\n"
            out.append(c)
            size += len(c)
    return "\n".join(out)


@family("recall-code-constants", category="recall", lang="text", kind="lookup", n=14, mode="answer",
        summary="the timeout a function really uses after imports, env defaults, a late override module and definition-time default arguments")
def gen_code(rng, n):
    made = 0
    while made < n:
        org = W.make_org(rng, None, n_people=5)
        tier = R.tier(rng)
        win = None if tier == "easy" else R.window(rng)
        n_fill = rng.choice([2, 3, 4]) if tier == "easy" else rng.choice([14, 20, 28, 36])
        kb = 0.6 if tier == "easy" else max(0.8, R.target_chars(win, rng.choice([1.0, 1.25, 1.5])) / 1000 / (n_fill + 6))
        pkg = rng.choice(["svc", "gatewaykit", "reporter", "syncd", "relay"])
        base_d = rng.randint(20, 90)
        base_p = rng.choice([x for x in range(20, 120) if x != base_d])
        factor = rng.randint(2, 9)
        k = rng.randint(5, 60)
        m = rng.randint(80, 400)
        use_prod = rng.random() < (0.0 if tier == "easy" else 0.6)
        base = base_p if use_prod else base_d
        connect = base * factor
        read = connect + k
        report = max(read, m)
        override = rng.random() < (0.0 if tier == "easy" else 0.6)
        o_val = rng.randint(200, 900) if override else None
        binding = rng.choice(["default-arg", "call-time"])
        order = rng.choice(["overrides-first", "overrides-last"])
        applies = override and (binding == "call-time" or order == "overrides-first")
        final = o_val if applies else report
        files = {}
        files[f"{pkg}/settings.py"] = dd(f'''
            """Process-wide settings."""
            import os

            BASE = int(os.environ.get("SVC_BASE", "{base_d}"))
            REGION_FACTOR = {factor}
            OLD_BASE = 15  # used by the 2019 client, not imported any more
        ''')
        files[f"{pkg}/net/__init__.py"] = ""
        files[f"{pkg}/net/limits.py"] = dd(f'''
            """Derived network limits."""
            from ..settings import BASE, REGION_FACTOR

            CONNECT = BASE * REGION_FACTOR
            READ = CONNECT + {k}
            WRITE = CONNECT * 2
        ''')
        files[f"{pkg}/net/client.py"] = dd(f'''
            """HTTP client defaults."""
            from .limits import READ as _READ

            REPORT_TIMEOUT = max(_READ, {m})
            UPLOAD_TIMEOUT = REPORT_TIMEOUT * 3
        ''')
        if binding == "default-arg":
            body = dd('''
                """Report jobs."""
                from ..net import client


                def fetch_report(url, timeout=client.REPORT_TIMEOUT):
                    """Fetch a report; ``timeout`` is in seconds."""
                    return ("GET", url, timeout)


                def fetch_report_async(url, timeout=client.UPLOAD_TIMEOUT):
                    return ("GET-ASYNC", url, timeout)
            ''')
        else:
            body = dd('''
                """Report jobs."""
                from ..net import client


                def fetch_report(url, timeout=None):
                    """Fetch a report; ``timeout`` is in seconds (default: the client's report timeout)."""
                    if timeout is None:
                        timeout = client.REPORT_TIMEOUT
                    return ("GET", url, timeout)


                def fetch_report_async(url, timeout=client.UPLOAD_TIMEOUT):
                    return ("GET-ASYNC", url, timeout)
            ''')
        files[f"{pkg}/jobs/__init__.py"] = ""
        files[f"{pkg}/jobs/reports.py"] = body
        if override:
            decoy = rng.random() < 0.5
            lines = ['"""Per-site overrides, applied at import time."""', "from .net import client" + (", limits" if decoy else ""), "", f"client.REPORT_TIMEOUT = {o_val}"]
            if decoy:
                lines.append(f"limits.READ = {rng.randint(10, 99)}  # tidy-up experiment")
            files[f"{pkg}/local_overrides.py"] = "\n".join(lines) + "\n"
        imports = ["from . import settings", "from .net import client", "from .jobs import reports"]
        if override:
            if order == "overrides-first":
                imports.insert(2, "from . import local_overrides")
            else:
                imports.append("from . import local_overrides")
        files[f"{pkg}/__init__.py"] = "\n".join(imports) + "\n"
        files["deploy/production.env"] = f"# exported before the service starts in production\nSVC_BASE={base_p}\nSVC_REGION=north\n"
        for i in range(n_fill):
            files[f"{pkg}/util/m{i:02d}_{rng.choice(['rows', 'text', 'merge', 'pages', 'slots'])}.py"] = filler_module(rng, org, kb)
        files[f"{pkg}/util/__init__.py"] = ""
        files["legacy/client_v1.py"] = '"""Retired client; nothing imports this."""\nREPORT_TIMEOUT = %d\n\ndef fetch_report(url, timeout=REPORT_TIMEOUT):\n    return ("GET", url, timeout)\n' % rng.randint(10, 400)
        files["README.md"] = f"# {pkg}\n\nA small service library. Settings live in `{pkg}/settings.py`; production environment variables are listed in `deploy/production.env`.\n"
        env_s = f"with the variables in `deploy/production.env` exported" if use_prod else "with no environment variables set at all"
        ph = [f"In the `{pkg}` package, how many seconds does `fetch_report(url)` use as its timeout when called without a timeout argument, after `import {pkg}` has completed, {env_s}? Give the number.",
              f"After `import {pkg}` finishes ({env_s}), what timeout (seconds) does a plain `fetch_report(url)` call end up with?",
              f"I need the effective default timeout of `fetch_report` in `{pkg}`, {env_s}. Careful about import order and when default arguments get evaluated. Just the number."]
        d = 2 + (override) + (binding == "default-arg") * (tier != "easy") + (win is not None and win <= 12000) + (use_prod)
        made += 1
        yield W.say_task(slug=f"{made:02d}-{'prod' if use_prod else 'noenv'}-{binding}", prompt=W.voice(rng, org, rng.choice(ph)), difficulty=min(5, d), start=files, contains=[str(final)],
                         gold=f"{final} seconds.", context_window=win, tags=["code-reading", "constants"],
                         notes={"binding": binding, "override": override, "order": order, "applies": applies, "prod": use_prod})


# ---------------------------------------------------------------------------------------------------------------- join chain

TIERS = [("bronze", 0), ("silver", 5), ("gold", 10), ("platinum", 15)]


@family("recall-table-join", category="recall", lang="text", kind="lookup", n=14, mode="answer",
        summary="total payable for an order (or a customer's month, or the top customer) via order, customer, region tax, tier discount and dated price lists")
def gen_join(rng, n):
    made = 0
    while made < n:
        org = W.make_org(rng, None, n_people=5)
        tier = R.tier(rng)
        win = None if tier == "easy" else R.window(rng)
        year = rng.randint(2031, 2034)
        n_sku = rng.randint(8, 14)
        skus = [f"SK-{x}" for x in rng.sample(range(100, 999), n_sku)]
        regions = rng.sample(["North", "South", "East", "West", "Harbour", "Uplands"], 4)
        tax = {r: rng.choice([0, 5, 8, 10, 12, 20]) for r in regions}
        cust_n = rng.randint(14, 30)
        custs = []
        for i in range(cust_n):
            custs.append(dict(id=f"CU-{rng.randint(1000, 9999)}", name=rng.choice(W.NAME_WORDS) + " " + rng.choice(["Bakery", "Stores", "Works", "Studio", "Garage", "Dairy"]),
                              region=rng.choice(regions), tier=rng.choice(TIERS)))
        ids = {c["id"] for c in custs}
        if len(ids) != len(custs):
            continue
        # price lists
        plist = []
        eff = dt.date(year, 1, 1)
        prices = {s: rng.randint(150, 9000) for s in skus}
        for pi in range(rng.randint(3, 5)):
            if pi:
                eff = eff + dt.timedelta(days=rng.randint(40, 100))
                for s in rng.sample(skus, rng.randint(3, n_sku)):
                    prices[s] = max(100, prices[s] + rng.choice([-1, 1]) * rng.randint(20, 600))
            plist.append((eff, dict(prices)))
        n_orders = rng.choice([30, 45, 60]) if tier == "easy" else max(80, int(R.target_chars(win, rng.choice([1.0, 1.25, 1.5])) / 36))
        orders = []
        used = set()
        for _ in range(n_orders):
            d = dt.date(year, rng.randint(1, 12), rng.randint(1, 28))
            if d < plist[0][0]:
                d = plist[0][0] + dt.timedelta(days=rng.randint(0, 20))
            oid = f"O-{rng.randint(10000, 99999)}"
            if oid in used:
                continue
            used.add(oid)
            orders.append(dict(id=oid, date=d, cust=rng.choice(custs), sku=rng.choice(skus), qty=rng.randint(1, 30)))
        orders.sort(key=lambda o: (o["date"], o["id"]))

        def price_on(sku, d):
            cur = None
            for e, pr in plist:
                if e <= d:
                    cur = pr[sku]
            return cur

        def payable(o):
            gross = o["qty"] * price_on(o["sku"], o["date"])  # cents
            disc_pct = o["cust"]["tier"][1]
            net = gross * (100 - disc_pct)  # in 1/100 cent... keep exact: net/100 cents
            total_num = net * (100 + tax[o["cust"]["region"]])  # over 10000
            cents = (total_num * 2 + 10000) // 20000
            return cents
        files: dict[str, str] = {}
        by_month: dict[int, list] = {}
        for o in orders:
            by_month.setdefault(o["date"].month, []).append(o)
        for mo, lst in by_month.items():
            files[f"orders/orders-{year}-{mo:02d}.csv"] = W.csv_text(["order_id", "date", "customer_id", "sku", "qty"], [[o["id"], W.d_iso(o["date"]), o["cust"]["id"], o["sku"], o["qty"]] for o in lst])
        files["customers.csv"] = W.csv_text(["customer_id", "name", "region", "tier"], [[c["id"], c["name"], c["region"], c["tier"][0]] for c in custs])
        for e, pr in plist:
            files[f"prices/price-list-{W.d_iso(e)}.csv"] = W.csv_text(["sku", "unit_price"], [[s, f"{p // 100}.{p % 100:02d}"] for s, p in sorted(pr.items())])
        files["regions.csv"] = W.csv_text(["region", "tax_percent"], [[r, tax[r]] for r in regions])
        files["tiers.txt"] = "Customer tiers and their discount on the goods total:\n" + "".join(f"  {t}: {p} percent\n" for t, p in TIERS)
        files["README.md"] = dd("""
            # Order book

            `orders/` has monthly CSVs. An order's amount payable is worked out like this:

            1. goods = qty x unit price, where the unit price comes from the latest `prices/price-list-<date>.csv` whose date is on or before the
               order date (a price list lists every SKU);
            2. discount: the customer's tier (in `customers.csv`; percentages in `tiers.txt`) is taken off the goods;
            3. tax: the customer's region (`regions.csv`) tax percentage is added on the discounted amount;
            4. round the final result once, to the nearest cent, half up. Write amounts in credits with two decimals.
        """)
        qk = rng.choice(["order", "order"] if tier == "easy" else ["order", "order", "customer_month", "top_customer"])
        if qk == "order":
            o = rng.choice(orders)
            v = payable(o)
            val = f"{v // 100}.{v % 100:02d}"
            ph = [f"What is the amount payable for order {o['id']}? Credits with two decimals.",
                  f"Work out what customer {o['cust']['id']} owes for order {o['id']} (discount and tax included). Two decimals.",
                  f"Please compute the invoice total for {o['id']} following the order-book README. Two decimal places."]
            prompt, contains, gold = rng.choice(ph), [val], f"Order {o['id']} comes to {val} credits."
            diff = 3 + (win is not None and win <= 12000) + (tier == "hard")
        elif qk == "customer_month":
            c = rng.choice(custs)
            mo = rng.choice(sorted(by_month))
            lst = [o for o in by_month[mo] if o["cust"] is c]
            if len(lst) < 2:
                continue
            tot = sum(payable(o) for o in lst)
            val = f"{tot // 100}.{tot % 100:02d}"
            ph = [f"What is the total payable by customer {c['id']} for all its orders dated in {W.MONTHS[mo - 1]} {year}? Credits, two decimals (each order rounded separately, then added).",
                  f"Add up what {c['name']} ({c['id']}) owes for its {W.MONTHS[mo - 1]} {year} orders: compute each order's payable amount (rounded to the cent) and sum them."]
            prompt, contains, gold = rng.choice(ph), [val], f"{val} credits."
            diff = 3 + (tier == "hard")
        else:
            tot = {}
            for o in orders:
                tot[o["cust"]["id"]] = tot.get(o["cust"]["id"], 0) + payable(o)
            ranked = sorted(tot.items(), key=lambda kv: -kv[1])
            if ranked[0][1] == ranked[1][1]:
                continue
            top = next(c for c in custs if c["id"] == ranked[0][0])
            ph = ["Which customer has the largest total amount payable over the whole year? Give the customer's name as in customers.csv.",
                  "Who is our biggest customer by total payable (tier discount and region tax applied per order, each order rounded to the cent)? Name, please."]
            prompt, contains, gold = rng.choice(ph), [top["name"]], f"{top['name']} ({top['id']})."
            diff = 4 + (tier == "hard")
        if any(c in prompt for c in contains):
            continue
        made += 1
        yield W.say_task(slug=f"{made:02d}-{qk.replace('_', '-')}", prompt=W.voice(rng, org, prompt), difficulty=min(5, diff), start=files, contains=contains, gold=gold,
                         context_window=win, tags=["join", "arithmetic"], notes={"orders": len(orders), "question": qk})
