"""Performance regressions: the same workload before and after a change; the call-count profile tells where the time went.

The scenario counts calls (Python functions of the project plus a handful of interesting library calls) with ``sys.setprofile``
and prints the ten most frequent.  The correct module and the defective one print the same results; only the profile differs.
"""
from __future__ import annotations

import json
import random
import re

from fx import Task, dd, run
from generators.review._slots import Bad, Module, Slot, render, slot_texts, sub, validate_module

from ._engine import KINDS, accepted, hidden_diag

PROFILER = '''
import collections
import os
import sys

_CALLS = collections.Counter()
_WATCH_PY = {"compile", "sub", "findall"}
_WATCH_C = {"sorted", "index", "execute", "executemany", "commit", "sum", "lower", "join", "count"}
_HERE = os.getcwd()


def _prof(frame, event, arg):
    if event == "call":
        co = frame.f_code
        fn = co.co_filename
        if fn.startswith(_HERE):
            _CALLS[f"{os.path.relpath(fn, _HERE)}:{co.co_name}"] += 1
        elif co.co_name in _WATCH_PY and "/re/" in fn:
            _CALLS[f"re.{co.co_name}"] += 1
    elif event == "c_call":
        name = getattr(arg, "__name__", "")
        if name in _WATCH_C:
            _CALLS[f"builtin:{name}"] += 1


def profile(fn, *args):
    sys.setprofile(_prof)
    try:
        return fn(*args)
    finally:
        sys.setprofile(None)


def report():
    print("=== profile ===")
    print("%9s  %s" % ("calls", "function"))
    for key, n in _CALLS.most_common(10):
        print("%9d  %s" % (n, key))
    print("=== end ===")
'''

# ---------------------------------------------------------------------------------------------------------------------
# product search
# ---------------------------------------------------------------------------------------------------------------------

SEARCH_TEMPLATE = dd('''
    """In-memory product search for the Wharfside shop: an inverted index, AND queries, suggestions and highlighting."""
    import re

    _WORD = re.compile(r"[a-z0-9]+")
    _ACCENTS = str.maketrans("àáâäèéêëìíîïòóôöùúûüñç", "aaaaeeeeiiiioooouuuunc")


    @@normalize@@


    @@build@@


    @@search@@


    @@suggest@@


    @@highlight@@
''')

_P_NORM = dd('''
    def normalize(text):
        """Lower-case words of a text with the common accents removed."""
        return _WORD.findall(text.lower().translate(_ACCENTS))
''')
_P_BUILD = dd('''
    def build_index(docs):
        """{word: sorted list of doc ids}, plus the original texts under the key None is not used: docs is {doc_id: text}."""
        index = {}
        for doc_id in sorted(docs):
            for word in set(normalize(docs[doc_id])):
                index.setdefault(word, []).append(doc_id)
        return index
''')
_P_SEARCH = dd('''
    def search(index, query):
        """Doc ids that contain every word of the query, ascending."""
        words = normalize(query)
        if not words:
            return []
        hits = None
        for w in words:
            ids = set(index.get(w, ()))
            hits = ids if hits is None else hits & ids
            if not hits:
                return []
        return sorted(hits)
''')
_P_SUGGEST = dd('''
    def suggest(index, prefix, limit=5):
        """The `limit` most frequent indexed words that start with the prefix (ties: alphabetical)."""
        p = normalize(prefix)
        if not p:
            return []
        words = [w for w in index if w.startswith(p[0])]
        words.sort(key=lambda w: (-len(index[w]), w))
        return words[:limit]
''')
_P_HIGHLIGHT = dd('''
    def highlight(text, terms):
        """The text with every occurrence of any term wrapped in [ ] (case-insensitive)."""
        pattern = re.compile("|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)), re.I)
        return pattern.sub(lambda m: "[" + m.group(0) + "]", text)
''')

SEARCH = Module(
    name="py-shopsearch", lang="python", path="shopfind/search.py", difficulty=3, title="", intro="", outro="",
    blurb="The `shopfind` package powers the search box of the Wharfside online shop.",
    template=SEARCH_TEMPLATE, ctx={"README.md": "# shopfind\n\nProduct search. `scenario.py` replays a typical morning of queries.\n", "shopfind/__init__.py": ""},
    scenario=PROFILER + dd('''

        from shopfind.search import build_index, highlight, search, suggest

        WORDS = ["copper", "kettle", "enamel", "blue", "teapot", "linen", "apron", "cotton", "towel", "rope", "brass", "lantern", "glass", "jar", "oak", "board", "ceramic", "mug",
                 "wool", "blanket", "tin", "bucket", "café", "crème", "pot", "mini", "large", "set", "vintage", "garden"]
        DOCS = {i: " ".join(WORDS[(i * 7 + k * 3) % len(WORDS)] for k in range(8)) for i in range(1, 301)}
        QUERIES = ["copper kettle", "blue teapot", "linen apron", "oak board", "cafe mug", "brass lantern glass", "wool", "garden set", "crème pot", "tin bucket"] * 12
        PREFIXES = ["co", "bl", "li", "ke", "ca", "br", "wo", "ga"] * 8


        def workload():
            index = build_index(DOCS)
            hits = sum(len(search(index, q)) for q in QUERIES)
            sugg = [suggest(index, p) for p in PREFIXES]
            marked = [highlight(DOCS[i], ["copper", "kettle"]) for i in range(1, 41)]
            return len(index), hits, sugg[0], marked[0]


        result = profile(workload)
        print("index words, total hits, first suggestions, first highlighted doc:")
        print(result)
        report()
    '''),
    slots=[
        Slot("normalize", "normalize", _P_NORM, []),
        Slot("build", "build_index", _P_BUILD, [
            Bad(dd('''
                def build_index(docs):
                    """{word: sorted list of doc ids}, plus the original texts under the key None is not used: docs is {doc_id: text}."""
                    index = {}
                    for doc_id in sorted(docs):
                        for word in set(normalize(docs[doc_id])):
                            index.setdefault(word, [])
                    for word in index:
                        for doc_id in sorted(docs):
                            if word in normalize(docs[doc_id]):
                                index[word].append(doc_id)
                    return index
            '''), "performance", "the index is built by re-normalising every document once per distinct word (quadratic) instead of once per document", ("normalize", "quadratic", "per word", "every document")),
            Bad(dd('''
                def build_index(docs):
                    """{word: sorted list of doc ids}, plus the original texts under the key None is not used: docs is {doc_id: text}."""
                    index = {}
                    for doc_id in docs:
                        for word in set(normalize(docs[doc_id])):
                            index[word] = sorted(index.get(word, []) + [doc_id])
                    return index
            '''), "performance", "the posting list of a word is re-sorted after every single insertion instead of being built in order", ("sorted", "re-sort", "insertion", "posting")),
        ]),
        Slot("search", "search", _P_SEARCH, [
            Bad(dd('''
                def search(index, query, docs=None):
                    """Doc ids that contain every word of the query, ascending."""
                    words = normalize(query)
                    if not words:
                        return []
                    all_ids = sorted({i for ids in index.values() for i in ids})
                    return [i for i in all_ids if all(i in index.get(w, ()) for w in words)]
            '''), "performance", "every query scans all document ids and tests membership in lists, instead of intersecting the (small) posting sets of the query words", ("scan", "all document", "list membership", "intersect")),
            Bad(sub(_P_SEARCH, "words = normalize(query)", "words = [normalize(w)[0] for w in normalize(query)]"), "performance",
                "every query word is normalised a second time, one call per word, although normalize() already returned clean words", ("normalize", "twice", "repeated", "per word")),
        ]),
        Slot("suggest", "suggest", _P_SUGGEST, [
            Bad(dd('''
                def suggest(index, prefix, limit=5):
                    """The `limit` most frequent indexed words that start with the prefix (ties: alphabetical)."""
                    p = normalize(prefix)
                    if not p:
                        return []
                    ranked = sorted(index, key=lambda w: (-len(index[w]), w))
                    return [w for w in ranked if w.startswith(p[0])][:limit]
            '''), "performance", "the whole vocabulary is sorted on every call before filtering by prefix, instead of filtering first", ("sorted", "whole vocabulary", "filter first")),
        ]),
        Slot("highlight", "highlight", _P_HIGHLIGHT, [
            Bad(dd('''
                def highlight(text, terms):
                    """The text with every occurrence of any term wrapped in [ ] (case-insensitive)."""
                    out = text
                    for t in sorted(terms, key=len, reverse=True):
                        out = re.sub("(?i)(?<!\\\\[)" + re.escape(t) + "(?![^\\\\[]*\\\\])", lambda m: "[" + m.group(0) + "]", out)
                    return out
            '''), "performance", "the pattern is recompiled for every term and every call (re.sub with a fresh pattern string) instead of being compiled once per call", ("re.sub", "compile", "pattern", "per term")),
        ]),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# order reports with sqlite
# ---------------------------------------------------------------------------------------------------------------------

SQL_TEMPLATE = dd('''
    """Reports over the orders database of the Bramley bakery."""
    import sqlite3


    def connect():
        conn = sqlite3.connect(":memory:")
        conn.executescript(
            "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT);"
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, placed TEXT, total_pence INTEGER);"
            "CREATE TABLE items (order_id INTEGER, sku TEXT, qty INTEGER);"
            "CREATE INDEX orders_by_customer ON orders (customer_id);"
            "CREATE INDEX items_by_order ON items (order_id);"
        )
        return conn


    @@totals@@


    @@items@@


    @@load@@


    @@latest@@
''')

_Q_TOTALS = dd('''
    def customer_totals(conn):
        """[(name, number of orders, total pence)] for customers with at least one order, biggest total first (ties: name)."""
        rows = conn.execute(
            "SELECT c.name, COUNT(o.id), SUM(o.total_pence) FROM customers c JOIN orders o ON o.customer_id = c.id GROUP BY c.id ORDER BY 3 DESC, 1"
        ).fetchall()
        return [tuple(r) for r in rows]
''')
_Q_ITEMS = dd('''
    def items_by_order(conn, order_ids):
        """{order_id: [(sku, qty), ...]} for the given orders, items in insertion order."""
        out = {oid: [] for oid in order_ids}
        marks = ",".join("?" * len(order_ids))
        for oid, sku, qty in conn.execute(f"SELECT order_id, sku, qty FROM items WHERE order_id IN ({marks}) ORDER BY rowid", list(order_ids)):
            out[oid].append((sku, qty))
        return out
''')
_Q_LOAD = dd('''
    def load_orders(conn, rows):
        """Insert (id, customer_id, placed, total_pence) rows in one transaction."""
        with conn:
            conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", rows)
''')
_Q_LATEST = dd('''
    def latest_order(conn, customer_id):
        """(id, placed) of the customer's most recent order, or None."""
        row = conn.execute("SELECT id, placed FROM orders WHERE customer_id = ? ORDER BY placed DESC, id DESC LIMIT 1", (customer_id,)).fetchone()
        return tuple(row) if row else None
''')

SQLREP = Module(
    name="py-bakeryreports", lang="python", path="bramley/reports.py", difficulty=3, title="", intro="", outro="",
    blurb="The `bramley` package builds the nightly order reports of a bakery chain.",
    template=SQL_TEMPLATE, ctx={"README.md": "# bramley\n\nNightly reports. `scenario.py` replays a night against a generated database.\n", "bramley/__init__.py": ""},
    scenario=PROFILER + dd('''

        from bramley.reports import connect, customer_totals, items_by_order, latest_order, load_orders

        conn = connect()
        conn.executemany("INSERT INTO customers VALUES (?, ?)", [(i, f"customer {i:02d}") for i in range(1, 61)])
        rows = [(1000 + n, 1 + (n * 7) % 60, f"2025-03-{1 + n % 28:02d}", 150 + (n * 37) % 900) for n in range(400)]
        conn.executemany("INSERT INTO items VALUES (?, ?, ?)", [(1000 + n, f"sku-{(n + k) % 23}", 1 + k) for n in range(400) for k in range(3)])


        def night():
            load_orders(conn, rows)
            totals = customer_totals(conn)
            items = items_by_order(conn, [r[0] for r in rows[:150]])
            last = [latest_order(conn, c) for c in range(1, 61)]
            return len(totals), totals[:2], sum(len(v) for v in items.values()), last[:2]


        result = profile(night)
        print("customers with orders, top two, items loaded, latest orders:")
        print(result)
        report()
    '''),
    slots=[
        Slot("totals", "customer_totals", _Q_TOTALS, [
            Bad(dd('''
                def customer_totals(conn):
                    """[(name, number of orders, total pence)] for customers with at least one order, biggest total first (ties: name)."""
                    out = []
                    for cid, name in conn.execute("SELECT id, name FROM customers").fetchall():
                        orders = conn.execute("SELECT total_pence FROM orders WHERE customer_id = ?", (cid,)).fetchall()
                        if orders:
                            out.append((name, len(orders), sum(r[0] for r in orders)))
                    return sorted(out, key=lambda t: (-t[2], t[0]))
            '''), "performance", "one query per customer (N+1) instead of a single JOIN with GROUP BY", ("N+1", "per customer", "JOIN", "GROUP BY")),
            Bad(dd('''
                def customer_totals(conn):
                    """[(name, number of orders, total pence)] for customers with at least one order, biggest total first (ties: name)."""
                    out = []
                    for cid, name in conn.execute("SELECT id, name FROM customers").fetchall():
                        n = conn.execute("SELECT COUNT(*) FROM orders WHERE customer_id = ?", (cid,)).fetchone()[0]
                        if n:
                            total = conn.execute("SELECT SUM(total_pence) FROM orders WHERE customer_id = ?", (cid,)).fetchone()[0]
                            out.append((name, n, total))
                    return sorted(out, key=lambda t: (-t[2], t[0]))
            '''), "performance", "two queries per customer (a COUNT and a SUM) instead of one JOIN with GROUP BY", ("N+1", "per customer", "COUNT", "SUM", "GROUP BY")),
        ]),
        Slot("items", "items_by_order", _Q_ITEMS, [
            Bad(dd('''
                def items_by_order(conn, order_ids):
                    """{order_id: [(sku, qty), ...]} for the given orders, items in insertion order."""
                    out = {}
                    for oid in order_ids:
                        out[oid] = [tuple(r) for r in conn.execute("SELECT sku, qty FROM items WHERE order_id = ? ORDER BY rowid", (oid,))]
                    return out
            '''), "performance", "one query per order (N+1) instead of a single IN (...) query", ("N+1", "per order", "IN", "single query")),
        ]),
        Slot("load", "load_orders", _Q_LOAD, [
            Bad(dd('''
                def load_orders(conn, rows):
                    """Insert (id, customer_id, placed, total_pence) rows in one transaction."""
                    for row in rows:
                        conn.execute("INSERT INTO orders VALUES (?, ?, ?, ?)", row)
                        conn.commit()
            '''), "performance", "every row is inserted and committed on its own instead of one executemany inside one transaction", ("commit", "per row", "executemany", "transaction")),
        ]),
        Slot("latest", "latest_order", _Q_LATEST, [
            Bad(dd('''
                def latest_order(conn, customer_id):
                    """(id, placed) of the customer's most recent order, or None."""
                    rows = conn.execute("SELECT id, placed FROM orders WHERE customer_id = ?", (customer_id,)).fetchall()
                    if not rows:
                        return None
                    return tuple(max(rows, key=lambda r: (r[1], r[0])))
            '''), "performance", "all of the customer's orders are fetched and the latest is picked in Python instead of ORDER BY ... LIMIT 1 in SQL", ("LIMIT", "fetchall", "ORDER BY", "all orders")),
        ]),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# log scanner
# ---------------------------------------------------------------------------------------------------------------------

SCAN_TEMPLATE = dd('''
    """Scans application logs for known problems and summarises them for the morning report."""
    import re

    RULES = [
        ("timeout", r"timed? ?out after (\\d+) ?ms"),
        ("oom", r"out of memory|OOM"),
        ("auth", r"401|403|token (expired|rejected)"),
        ("disk", r"no space left|disk (full|quota)"),
    ]


    @@compile@@


    @@scan@@


    @@summary@@
''')

_L_COMPILE = dd('''
    def compile_rules(rules=RULES):
        """[(name, compiled pattern)] for the rule table."""
        return [(name, re.compile(pattern, re.I)) for name, pattern in rules]
''')
_L_SCAN = dd('''
    def scan(lines, compiled):
        """[(line number, rule name)] for every line that matches a rule; the first matching rule of the table wins."""
        hits = []
        for n, line in enumerate(lines, 1):
            for name, pat in compiled:
                if pat.search(line):
                    hits.append((n, name))
                    break
        return hits
''')
_L_SUMMARY = dd('''
    def summarise(hits):
        """{rule name: count}, most frequent first (ties: name)."""
        counts = {}
        for _, name in hits:
            counts[name] = counts.get(name, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
''')

SCAN = Module(
    name="py-logscan", lang="python", path="morning/scan.py", difficulty=2, title="", intro="", outro="",
    blurb="The `morning` package produces the 7 a.m. problem summary from the overnight application logs.",
    template=SCAN_TEMPLATE, ctx={"README.md": "# morning\n\nMorning log summary. `scenario.py` scans a generated night of logs.\n", "morning/__init__.py": ""},
    scenario=PROFILER + dd('''

        from morning.scan import compile_rules, scan, summarise

        LINES = []
        for i in range(1500):
            kind = i % 11
            LINES.append(["GET /api/cart 200 12ms", "worker-3 timed out after 3000 ms calling billing", "kernel: Out of memory: killed process 411", "POST /login 401 token expired",
                          "GET /api/search 200 31ms", "write failed: no space left on device", "GET /static/app.js 304 2ms", "GET /api/orders 200 44ms", "retrying in 5s", "GET /healthz 200 1ms",
                          "disk quota exceeded for user batch"][kind])


        def morning():
            compiled = compile_rules()
            hits = scan(LINES, compiled)
            return len(hits), summarise(hits)


        result = profile(morning)
        print("matching lines, summary:")
        print(result)
        report()
    '''),
    slots=[
        Slot("compile", "compile_rules", _L_COMPILE, []),
        Slot("scan", "scan", _L_SCAN, [
            Bad(dd('''
                def scan(lines, compiled):
                    """[(line number, rule name)] for every line that matches a rule; the first matching rule of the table wins."""
                    hits = []
                    for n, line in enumerate(lines, 1):
                        for name, pattern in RULES:
                            if re.search(pattern, line, re.I):
                                hits.append((n, name))
                                break
                    return hits
            '''), "performance", "the patterns are passed to re.search as strings for every line (a regex cache lookup per call, and a recompile whenever the cache is full) instead of using the precompiled patterns", ("precompiled", "re.search", "compile", "per line")),
            Bad(dd('''
                def scan(lines, compiled):
                    """[(line number, rule name)] for every line that matches a rule; the first matching rule of the table wins."""
                    hits = []
                    for n, line in enumerate(lines, 1):
                        compiled = compile_rules()
                        for name, pat in compiled:
                            if pat.search(line):
                                hits.append((n, name))
                                break
                    return hits
            '''), "performance", "compile_rules() is called inside the per-line loop, so every line recompiles all patterns", ("compile_rules", "inside the loop", "per line", "recompile")),
        ]),
        Slot("summary", "summarise", _L_SUMMARY, [
            Bad(dd('''
                def summarise(hits):
                    """{rule name: count}, most frequent first (ties: name)."""
                    names = sorted({name for _, name in hits})
                    counts = {name: sum(1 for _, n in hits if n == name) for name in names}
                    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
            '''), "performance", "the hits are rescanned once per rule name instead of being counted in a single pass", ("rescan", "per rule", "single pass", "sum(")),
        ]),
    ],
)

PERF = [SEARCH, SQLREP, SCAN]
for _m in PERF:
    validate_module(_m)


# ---- engine ---------------------------------------------------------------------------------------------------------

_PROF = re.compile(r"=== profile ===\n(.*?)\n=== end ===", re.S)


def run_perf(mod: Module, choice: dict):
    head, spans = render(mod.template, slot_texts(mod, choice), mod.lang)
    files = dict(mod.ctx)
    files[mod.path] = head
    files["scenario.py"] = mod.scenario
    r = run(files, "python3 -u scenario.py", timeout=120)
    m = _PROF.search(r.out)
    prof = m.group(1) if m else ""
    body = _PROF.sub("", r.out).strip()
    return r.code, body, prof, head, spans


def _profile_total(prof: str) -> int:
    t = 0
    for ln in prof.split("\n")[1:]:
        try:
            t += int(ln.split()[0])
        except (ValueError, IndexError):
            pass
    return t


def perf_family(mods, rng: random.Random, n: int):
    cands = []
    for m in mods:
        c0, b0, p0, _, _ = run_perf(m, {})
        if c0 != 0:
            raise RuntimeError(f"{m.name}: scenario fails:\n{b0[-1000:]}")
        for s in m.slots:
            for bi in range(len(s.bad)):
                code, body, prof, head, spans = run_perf(m, {s.name: ("bad", bi)})
                if code != 0 or body != b0:
                    continue  # the defect must not change the results, only the cost
                if _profile_total(prof) < 2.0 * _profile_total(p0):
                    continue
                cands.append((m, s, bi))
    rng.shuffle(cands)
    for i, (m, s, bi) in enumerate(cands[:n], 1):
        bad = s.bad[bi]
        c0, b0, p0, head0, _ = run_perf(m, {})
        code, body, prof, head, spans = run_perf(m, {s.name: ("bad", bi)})
        files = dict(m.ctx)
        files[m.path] = head
        files["scenario.py"] = m.scenario
        files["logs/profile-before.txt"] = p0.strip() + "\n"
        files["logs/profile-after.txt"] = prof.strip() + "\n"
        before_n, after_n = _profile_total(p0), _profile_total(prof)
        windows = [{"file": m.path, "start": spans[s.name][0], "end": spans[s.name][1]}, {"file": "logs/profile-after.txt", "start": 2, "end": 5}]
        spec = {"answer_file": "diagnosis.json", "fields": {
            "root_cause_file": {"type": "path", "accept": [m.path]},
            "function": {"type": "name", "accept": [s.func]},
            "kind": {"type": "enum", "allowed": KINDS, "accept": accepted("performance")},
            "evidence_lines": {"type": "evidence", "windows": windows, "slack": 1},
            "fix_summary": {"type": "text", "min_len": 20, "any": list(bad.kw) + [s.func]},
        }}
        gold = {"root_cause_file": m.path, "function": s.func, "kind": "performance", "evidence_lines": [f"{m.path}:{spans[s.name][0]}", "logs/profile-after.txt:2"], "fix_summary": bad.why}
        schema = ("Write `diagnosis.json`: an object with exactly these keys: `root_cause_file` (path of the file with the regression), `function` (the function that introduced it), `kind` (one of "
                  + ", ".join(KINDS) + "), `evidence_lines` (a list of `path:line` strings: the slow code and/or the telling profile lines) and `fix_summary` (one or two sentences).")
        voices = [
            f"{m.blurb} The nightly run got about {after_n // max(1, before_n)} times slower after last week's change. `scenario.py` replays the workload; the call-count profile before and after is in `logs/profile-before.txt` and `logs/profile-after.txt`. The results are identical, only the cost went up. Find the regression. {schema}",
            f"Performance regression report. {m.blurb} Before the change the workload made {before_n} profiled calls, now {after_n} (`logs/`). The output of the scenario did not change. Which function got slower, and why? {schema}",
            f"Something made {m.name.split('-', 1)[-1]} much more expensive. Compare the profiles in `logs/` (top ten call counts, before and after) and read the code; `scenario.py` is the workload. {schema}",
        ]
        d = max(1, min(5, m.difficulty - 1 + (1 if bad.kw and "N+1" in bad.kw else 0) + (1 if len(spans) > 4 else 0)))
        yield Task(
            slug=f"{i:02d}-{m.name.split('-', 1)[-1]}-{s.name}", prompt=rng.choice(voices), difficulty=d, kind="fix", lang="python", start=files, hidden=hidden_diag(spec),
            solution={"diagnosis.json": json.dumps(gold, indent=1) + "\n"}, verify="python3 _verify/check.py", pass_mode="json-score", protected=sorted(files), timeout_s=60,
            tags=["perf-regression", "profile"], notes={"module": m.name, "slot": s.name, "defect": bad.why, "calls_before": before_n, "calls_after": after_n},
        )
