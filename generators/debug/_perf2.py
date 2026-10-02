"""More performance-regression modules (see ``_perf``): contact clean-up, bank statements, room bookings, a letter template engine.

Every defect keeps the output of the scenario identical and multiplies the number of calls of some helper (pairwise comparisons, recomputation inside a loop).
"""
from __future__ import annotations

from fx import dd
from generators.review._slots import Bad, Module, Slot, validate_module

from ._perf import PROFILER

# ---------------------------------------------------------------------------------------------------------------------
# contact clean-up
# ---------------------------------------------------------------------------------------------------------------------

BOOK_TEMPLATE = dd('''
    """Contact clean-up for the Eastgate library's newsletter list."""
    import re

    _NON_DIGITS = re.compile(r"\\D")


    def city_key(raw):
        """The canonical spelling of a city name."""
        return " ".join(raw.split()).title()


    @@phone@@


    @@dedupe@@


    @@by_city@@


    @@labels@@
''')

_B_PHONE = dd('''
    def normalize_phone(raw):
        """Digits of a UK phone number; a leading +44 becomes 0."""
        digits = _NON_DIGITS.sub("", raw)
        if raw.strip().startswith("+44"):
            digits = "0" + digits[2:]
        return digits
''')
_B_DEDUPE = dd('''
    def dedupe(contacts):
        """The contacts with a repeated phone number removed (the first one stays), in the original order."""
        seen = set()
        out = []
        for c in contacts:
            key = normalize_phone(c["phone"])
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out
''')
_B_BYCITY = dd('''
    def by_city(contacts):
        """{city: sorted names}, cities in alphabetical order, spelled by city_key."""
        groups = {}
        for c in contacts:
            groups.setdefault(city_key(c["city"]), []).append(c["name"])
        return {city: sorted(names) for city, names in sorted(groups.items())}
''')
_B_LABELS = dd('''
    def labels(contacts):
        """One line per contact, 'Name, City, phone' with the phone normalised, ordered by city then name."""
        rows = sorted(contacts, key=lambda c: (city_key(c["city"]), c["name"]))
        return ["%s, %s, %s" % (c["name"], city_key(c["city"]), normalize_phone(c["phone"])) for c in rows]
''')

BOOK = Module(
    name="py-eastgate-contacts", lang="python", path="eastgate/clean.py", difficulty=2, title="", intro="", outro="",
    blurb="The `eastgate` package cleans the contact list before every newsletter run of the Eastgate library.",
    template=BOOK_TEMPLATE, ctx={"README.md": "# eastgate\n\nNewsletter list clean-up. `scenario.py` replays a clean-up of a generated contact list.\n", "eastgate/__init__.py": ""},
    scenario=PROFILER + dd('''

        from eastgate.clean import by_city, dedupe, labels, normalize_phone

        NAMES = ["Ada", "Brin", "Cole", "Dara", "Eli", "Faye", "Gus", "Hana", "Ivo", "Jade", "Kit", "Lena"]
        CITIES = ["leeds", " LEEDS", "York", "york ", "bath", "Bath", "hull", "Derby", "Lincoln", "ely", "new  castle", "Newcastle"]
        FORMATS = ["0161 496 %04d", "+44 161 496 %04d", "(0161) 496-%04d"]
        CONTACTS = [{"name": "%s %d" % (NAMES[i % 12], i), "phone": FORMATS[i % 3] % ((i * 7) % 100), "city": CITIES[(i * 5) % 12]} for i in range(160)]


        def clean():
            unique = dedupe(CONTACTS)
            return len(unique), normalize_phone("+44 161 496 0042"), list(by_city(unique).items())[:3], labels(unique)[:2]


        result = profile(clean)
        print("unique contacts, sample number, first cities, first labels:")
        print(result)
        report()
    '''),
    slots=[
        Slot("phone", "normalize_phone", _B_PHONE, []),
        Slot("dedupe", "dedupe", _B_DEDUPE, [
            Bad(dd('''
                def dedupe(contacts):
                    """The contacts with a repeated phone number removed (the first one stays), in the original order."""
                    out = []
                    for c in contacts:
                        if all(normalize_phone(c["phone"]) != normalize_phone(o["phone"]) for o in out):
                            out.append(c)
                    return out
            '''), "performance", "every contact is compared with every kept contact and both phone numbers are normalised again for each comparison, instead of normalising once and keeping a set of seen numbers",
                ("normalize_phone", "pairwise", "set", "seen", "quadratic")),
            Bad(dd('''
                def dedupe(contacts):
                    """The contacts with a repeated phone number removed (the first one stays), in the original order."""
                    out = []
                    for c in contacts:
                        kept = [normalize_phone(o["phone"]) for o in out]
                        if normalize_phone(c["phone"]) not in kept:
                            out.append(c)
                    return out
            '''), "performance", "the numbers of all kept contacts are normalised again for every new contact and searched in a list, instead of keeping a set of normalised numbers", ("normalize_phone", "list", "set", "again", "quadratic")),
        ]),
        Slot("by_city", "by_city", _B_BYCITY, [
            Bad(dd('''
                def by_city(contacts):
                    """{city: sorted names}, cities in alphabetical order, spelled by city_key."""
                    cities = sorted({city_key(c["city"]) for c in contacts})
                    return {city: sorted(c["name"] for c in contacts if city_key(c["city"]) == city) for city in cities}
            '''), "performance", "the contact list is rescanned once per city and city_key is recomputed for every contact each time, instead of grouping in one pass", ("city_key", "rescan", "per city", "one pass", "group")),
        ]),
        Slot("labels", "labels", _B_LABELS, [
            Bad(dd('''
                def labels(contacts):
                    """One line per contact, 'Name, City, phone' with the phone normalised, ordered by city then name."""
                    from functools import cmp_to_key

                    def compare(a, b):
                        ka, kb = (city_key(a["city"]), a["name"]), (city_key(b["city"]), b["name"])
                        return (ka > kb) - (ka < kb)

                    rows = sorted(contacts, key=cmp_to_key(compare))
                    return ["%s, %s, %s" % (c["name"], city_key(c["city"]), normalize_phone(c["phone"])) for c in rows]
            '''), "performance", "the sort uses a comparison function that recomputes both city keys on every comparison instead of a key function evaluated once per contact", ("city_key", "cmp_to_key", "key function", "comparison")),
        ]),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# bank statements
# ---------------------------------------------------------------------------------------------------------------------

LEDGER_TEMPLATE = dd('''
    """Statement processing for the Harbourside credit union."""
    import re

    _AMOUNT = re.compile(r"^-?(\\d{1,3}(,\\d{3})+|\\d+)(\\.\\d{1,2})?$")


    def month_of(date):
        """'2025-03-14' -> '2025-03'."""
        return date[:7]


    def clean_payee(raw):
        """Payee names compare case-insensitively and ignore a trailing reference like ' #4411'."""
        return re.sub(r"\\s*#\\d+$", "", raw.strip()).lower()


    @@amount@@


    @@balance@@


    @@monthly@@


    @@payees@@


    @@repeats@@
''')

_G_AMOUNT = dd('''
    def parse_amount(text):
        """'12.50' -> 1250, '-3' -> -300, '1,234.5' -> 123450 (pence)."""
        t = text.strip()
        if not _AMOUNT.match(t):
            raise ValueError("bad amount: %r" % text)
        neg = t.startswith("-")
        whole, _, frac = t.lstrip("-").replace(",", "").partition(".")
        pence = int(whole) * 100 + int((frac + "00")[:2])
        return -pence if neg else pence
''')
_G_BALANCE = dd('''
    def running_balance(opening, lines):
        """The balance in pence after each statement line (the lines are amount texts), starting from the opening balance."""
        balance = opening
        out = []
        for text in lines:
            balance += parse_amount(text)
            out.append(balance)
        return out
''')
_G_MONTHLY = dd('''
    def monthly_totals(rows):
        """{month: net pence} for rows of (date, payee, pence), months in order."""
        totals = {}
        for date, _, pence in rows:
            m = month_of(date)
            totals[m] = totals.get(m, 0) + pence
        return dict(sorted(totals.items()))
''')
_G_PAYEES = dd('''
    def top_payees(rows, k=3):
        """The k payees money went to most: [(payee, pence spent)], biggest first (ties: name). Only outflows (negative amounts) count."""
        spent = {}
        for _, payee, pence in rows:
            if pence < 0:
                key = clean_payee(payee)
                spent[key] = spent.get(key, 0) - pence
        return sorted(spent.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
''')
_G_REPEATS = dd('''
    def find_repeats(rows):
        """[(first index, repeat index)] for rows with the same date, payee and amount as an earlier row, ordered by repeat index."""
        first = {}
        out = []
        for j, (date, payee, pence) in enumerate(rows):
            key = (date, clean_payee(payee), pence)
            if key in first:
                out.append((first[key], j))
            else:
                first[key] = j
        return out
''')

LEDGER = Module(
    name="py-harbourside-statements", lang="python", path="ledgerly/statement.py", difficulty=3, title="", intro="", outro="",
    blurb="The `ledgerly` package prepares the monthly statements of the Harbourside credit union.",
    template=LEDGER_TEMPLATE, ctx={"README.md": "# ledgerly\n\nStatement processing. `scenario.py` replays one statement run.\n", "ledgerly/__init__.py": ""},
    scenario=PROFILER + dd('''

        from ledgerly.statement import find_repeats, monthly_totals, parse_amount, running_balance, top_payees

        PAYEES = ["Corner Bakery", "corner bakery #4411", "Power Co", "Bus Pass", "Thames Water #77", "Library Fines", "Garden Centre", "Vet", "Pharmacy", "Cinema", "Gas Board", "Post Office"]
        LINES = ["-%d.%02d" % (3 + (i * 13) % 90, (i * 7) % 100) if i % 5 else "%d,%03d.50" % (1 + i % 3, (i * 11) % 1000) for i in range(240)]
        ROWS = [("2025-%02d-%02d" % (1 + i % 12, 1 + (i * 3) % 28), PAYEES[(i * 5) % 12], parse_amount(LINES[i])) for i in range(240)]


        def statement():
            balances = running_balance(10000, LINES)
            months = monthly_totals(ROWS)
            return balances[-1], list(months.items())[:2], top_payees(ROWS), find_repeats(ROWS)[:3]


        result = profile(statement)
        print("closing balance, first months, top payees, first repeats:")
        print(result)
        report()
    '''),
    slots=[
        Slot("amount", "parse_amount", _G_AMOUNT, []),
        Slot("balance", "running_balance", _G_BALANCE, [
            Bad(dd('''
                def running_balance(opening, lines):
                    """The balance in pence after each statement line (the lines are amount texts), starting from the opening balance."""
                    return [opening + sum(parse_amount(t) for t in lines[: i + 1]) for i in range(len(lines))]
            '''), "performance", "every balance re-parses and re-adds all lines from the start (quadratic) instead of carrying the running total", ("parse_amount", "quadratic", "running total", "from the start")),
        ]),
        Slot("monthly", "monthly_totals", _G_MONTHLY, [
            Bad(dd('''
                def monthly_totals(rows):
                    """{month: net pence} for rows of (date, payee, pence), months in order."""
                    months = sorted({month_of(date) for date, _, _ in rows})
                    return {m: sum(p for d, _, p in rows if month_of(d) == m) for m in months}
            '''), "performance", "all rows are rescanned once per month and month_of is recomputed for each of them, instead of one pass with a dictionary", ("month_of", "rescan", "per month", "one pass")),
        ]),
        Slot("payees", "top_payees", _G_PAYEES, [
            Bad(dd('''
                def top_payees(rows, k=3):
                    """The k payees money went to most: [(payee, pence spent)], biggest first (ties: name). Only outflows (negative amounts) count."""
                    names = sorted({clean_payee(p) for _, p, a in rows if a < 0})
                    spent = [(name, -sum(a for _, p, a in rows if a < 0 and clean_payee(p) == name)) for name in names]
                    return sorted(spent, key=lambda kv: (-kv[1], kv[0]))[:k]
            '''), "performance", "the rows are rescanned once per payee and the payee is cleaned again for every row each time, instead of accumulating per payee in one pass", ("clean_payee", "rescan", "per payee", "one pass")),
        ]),
        Slot("repeats", "find_repeats", _G_REPEATS, [
            Bad(dd('''
                def find_repeats(rows):
                    """[(first index, repeat index)] for rows with the same date, payee and amount as an earlier row, ordered by repeat index."""
                    out = []
                    for j in range(len(rows)):
                        for i in range(j):
                            if clean_payee(rows[i][1]) == clean_payee(rows[j][1]) and rows[i][0] == rows[j][0] and rows[i][2] == rows[j][2]:
                                out.append((i, j))
                                break
                    return out
            '''), "performance", "every row is compared with all earlier rows and the payees are cleaned again in each comparison (quadratic), instead of remembering the first index of every key in a dict", ("clean_payee", "quadratic", "dict", "pairwise")),
        ]),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# room bookings
# ---------------------------------------------------------------------------------------------------------------------

SLOT_TEMPLATE = dd('''
    """Meeting-room booking arithmetic for the Wick Street co-working space. Times are minutes after midnight."""


    def minutes(hhmm):
        """'09:30' -> 570."""
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)


    def overlaps(a, b):
        """True if two (start, end) ranges share a minute; ranges that only touch do not overlap."""
        return a[0] < b[1] and b[0] < a[1]


    @@merge@@


    @@free@@


    @@conflicts@@
''')

_S_MERGE = dd('''
    def merge_busy(intervals):
        """Busy ranges merged (overlapping or touching ranges become one), sorted. Ranges are never empty."""
        merged = []
        for s, e in sorted(intervals):
            if merged and s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        return [tuple(x) for x in merged]
''')
_S_FREE = dd('''
    def free_slots(busy, day_start, day_end, min_len=30):
        """Free ranges inside [day_start, day_end] of at least min_len minutes, given non-empty busy ranges."""
        free = []
        cursor = day_start
        for s, e in merge_busy([(max(s, day_start), min(e, day_end)) for s, e in busy if e > day_start and s < day_end]):
            if s - cursor >= min_len:
                free.append((cursor, s))
            cursor = max(cursor, e)
        if day_end - cursor >= min_len:
            free.append((cursor, day_end))
        return free
''')
_S_CONFLICTS = dd('''
    def conflicts(events):
        """Sorted (id_a, id_b) pairs, id_a < id_b, of events (id, start, end) that overlap. Events are never empty."""
        found = []
        active = []
        for ev in sorted(events, key=lambda e: (e[1], e[2], e[0])):
            active = [a for a in active if a[2] > ev[1]]
            for a in active:
                found.append(tuple(sorted((a[0], ev[0]))))
            active.append(ev)
        return sorted(found)
''')

SLOTBOOK = Module(
    name="py-wickstreet-rooms", lang="python", path="slotbook/slots.py", difficulty=3, title="", intro="", outro="",
    blurb="The `slotbook` package finds free time and double bookings for the meeting rooms of a co-working space.",
    template=SLOT_TEMPLATE, ctx={"README.md": "# slotbook\n\nRoom booking arithmetic. `scenario.py` replays a busy day.\n", "slotbook/__init__.py": ""},
    scenario=PROFILER + dd('''

        from slotbook.slots import conflicts, free_slots, merge_busy, minutes

        BUSY = [(minutes("08:00") + (i * 37) % 560, minutes("08:00") + (i * 37) % 560 + 10 + (i * 11) % 50) for i in range(70)]
        EVENTS = [(1000 + i, minutes("08:00") + (i * 53) % 600, minutes("08:00") + (i * 53) % 600 + 5 + (i * 7) % 40) for i in range(130)]


        def day():
            merged = merge_busy(BUSY)
            free = free_slots(BUSY, minutes("08:00"), minutes("18:00"), 30)
            clashes = conflicts(EVENTS)
            return len(merged), merged[:2], free[:3], len(clashes), clashes[:3]


        result = profile(day)
        print("merged ranges, first two, first free slots, clashes, first clashes:")
        print(result)
        report()
    '''),
    slots=[
        Slot("merge", "merge_busy", _S_MERGE, [
            Bad(dd('''
                def merge_busy(intervals):
                    """Busy ranges merged (overlapping or touching ranges become one), sorted. Ranges are never empty."""
                    ranges = [tuple(x) for x in intervals]
                    changed = True
                    while changed:
                        changed = False
                        for i in range(len(ranges)):
                            for j in range(i + 1, len(ranges)):
                                a, b = ranges[i], ranges[j]
                                if overlaps(a, b) or a[1] == b[0] or b[1] == a[0]:
                                    ranges[i] = (min(a[0], b[0]), max(a[1], b[1]))
                                    del ranges[j]
                                    changed = True
                                    break
                            if changed:
                                break
                    return sorted(ranges)
            '''), "performance", "ranges are merged pairwise with overlaps() and the search restarts after every merge, instead of sorting once and sweeping", ("overlaps", "sort", "sweep", "pairwise", "quadratic")),
        ]),
        Slot("free", "free_slots", _S_FREE, [
            Bad(dd('''
                def free_slots(busy, day_start, day_end, min_len=30):
                    """Free ranges inside [day_start, day_end] of at least min_len minutes, given non-empty busy ranges."""
                    taken = [any(overlaps((m, m + 1), b) for b in busy) for m in range(day_start, day_end)]
                    free = []
                    start = None
                    for i, t in enumerate(taken + [True]):
                        m = day_start + i
                        if not t and start is None:
                            start = m
                        elif t and start is not None:
                            if m - start >= min_len:
                                free.append((start, m))
                            start = None
                    return free
            '''), "performance", "the day is scanned minute by minute and every minute is tested against every busy range, instead of merging the busy ranges and reading the gaps", ("overlaps", "minute", "gaps", "merge")),
        ]),
        Slot("conflicts", "conflicts", _S_CONFLICTS, [
            Bad(dd('''
                def conflicts(events):
                    """Sorted (id_a, id_b) pairs, id_a < id_b, of events (id, start, end) that overlap. Events are never empty."""
                    found = []
                    for i, a in enumerate(events):
                        for b in events[i + 1:]:
                            if overlaps((a[1], a[2]), (b[1], b[2])):
                                found.append(tuple(sorted((a[0], b[0]))))
                    return sorted(found)
            '''), "performance", "all pairs of events are tested with overlaps() instead of sorting by start time and sweeping a list of active events", ("overlaps", "pairs", "sweep", "sort", "quadratic")),
            Bad(dd('''
                def conflicts(events):
                    """Sorted (id_a, id_b) pairs, id_a < id_b, of events (id, start, end) that overlap. Events are never empty."""
                    found = set()
                    for a in events:
                        for b in events:
                            if a[0] < b[0] and overlaps((a[1], a[2]), (b[1], b[2])):
                                found.add((a[0], b[0]))
                    return sorted(found)
            '''), "performance", "every ordered pair of events is tested, so each pair is checked twice and nothing prunes the events that are already over, instead of a sweep over events sorted by start time", ("overlaps", "pairs", "twice", "sweep", "quadratic")),
        ]),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# letter templates
# ---------------------------------------------------------------------------------------------------------------------

STENCIL_TEMPLATE = dd('''
    """A tiny template engine for the Fernhill school's letters: {{ name }} and {{ pupil.class }} placeholders."""
    import re

    _TOKEN = re.compile(r"\\{\\{\\s*([\\w.]+)\\s*\\}\\}")


    def split_path(path):
        """'pupil.class' -> ['pupil', 'class']."""
        return path.split(".")


    def has_path(ctx, path):
        """True if every part of the dotted path exists in the nested dicts of ctx."""
        cur = ctx
        for part in split_path(path):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return False
        return True


    def lookup(ctx, path):
        """The value at the dotted path as text, or '' when a part is missing."""
        cur = ctx
        for part in split_path(path):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return ""
        return str(cur)


    @@tokenize@@


    @@variables@@


    @@render@@


    @@missing@@
''')

_T_TOKENIZE = dd('''
    def tokenize(template):
        """[('text', str) | ('var', 'a.b')] in order of appearance."""
        out = []
        pos = 0
        for m in _TOKEN.finditer(template):
            if m.start() > pos:
                out.append(("text", template[pos:m.start()]))
            out.append(("var", ".".join(split_path(m.group(1)))))
            pos = m.end()
        if pos < len(template):
            out.append(("text", template[pos:]))
        return out
''')
_T_VARIABLES = dd('''
    def variables(template):
        """The distinct variable paths of a template, sorted."""
        return sorted({value for kind, value in tokenize(template) if kind == "var"})
''')
_T_RENDER = dd('''
    def render_all(template, contexts):
        """One rendered text per context."""
        tokens = tokenize(template)
        return ["".join(v if k == "text" else lookup(c, v) for k, v in tokens) for c in contexts]
''')
_T_MISSING = dd('''
    def missing(template, contexts):
        """Sorted [(variable, number of contexts that lack it)], only variables that are missing somewhere."""
        counts = {}
        for v in variables(template):
            n = sum(1 for c in contexts if not has_path(c, v))
            if n:
                counts[v] = n
        return sorted(counts.items())
''')

STENCIL = Module(
    name="py-fernhill-letters", lang="python", path="stencil/letters.py", difficulty=3, title="", intro="", outro="",
    blurb="The `stencil` package fills the placeholders of the school's form letters from one record per pupil.",
    template=STENCIL_TEMPLATE, ctx={"README.md": "# stencil\n\nForm letters. `scenario.py` replays one mail merge.\n", "stencil/__init__.py": ""},
    scenario=PROFILER + dd('''

        from stencil.letters import missing, render_all, variables

        TEMPLATE = ("Dear {{ parent.name }}, {{ pupil.first }} {{ pupil.last }} of class {{ pupil.class }} has been chosen for the {{ trip.name }} on {{ trip.date }}. "
                    "Please return the form by {{ trip.deadline }} and pay {{ trip.cost }} to {{ school.contact }}.")
        CONTEXTS = []
        for i in range(90):
            ctx = {"parent": {"name": "Parent %d" % i}, "pupil": {"first": "Kid", "last": "N%d" % i, "class": "4%s" % "ABC"[i % 3]},
                   "trip": {"name": "museum visit", "date": "12 May", "deadline": "1 May", "cost": "8.50"}, "school": {"contact": "office"}}
            if i % 7 == 0:
                del ctx["trip"]["deadline"]
            if i % 11 == 0:
                del ctx["school"]
            CONTEXTS.append(ctx)


        def merge():
            letters = render_all(TEMPLATE, CONTEXTS)
            return len(variables(TEMPLATE)), letters[1][:60], missing(TEMPLATE, CONTEXTS)


        result = profile(merge)
        print("variables, a letter, missing data:")
        print(result)
        report()
    '''),
    slots=[
        Slot("tokenize", "tokenize", _T_TOKENIZE, []),
        Slot("variables", "variables", _T_VARIABLES, []),
        Slot("render", "render_all", _T_RENDER, []),
        Slot("missing", "missing", _T_MISSING, [
            Bad(dd('''
                def missing(template, contexts):
                    """Sorted [(variable, number of contexts that lack it)], only variables that are missing somewhere."""
                    counts = {v: sum(1 for c in contexts if v in variables(template) and not has_path(c, v)) for v in variables(template)}
                    return sorted((v, n) for v, n in counts.items() if n)
            '''), "performance", "variables(template) is recomputed (and the template tokenised again) for every pair of variable and context instead of once before the loops", ("variables", "tokenize", "recomputed", "once", "per context")),
        ]),
    ],
)

PERF2 = [BOOK, LEDGER, SLOTBOOK, STENCIL]
for _m in PERF2:
    validate_module(_m)
