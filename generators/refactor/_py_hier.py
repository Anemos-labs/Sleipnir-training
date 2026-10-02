"""Class hierarchies (python) for the inheritance-to-composition refactor: start text, reference solution, harness and cases.

Every hierarchy is a template (``$`` placeholders for names and constants) with a start version that uses template methods and virtual
dispatch, a reference solution without any inheritance between the package's classes, and a harness that drives the public API.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------------------------------------------------
# A: channels (format -> guard -> deliver), 4 levels
# ---------------------------------------------------------------------------------------------------------------------
CHANNEL_PARTS = {
    "base": ('''class $C0:
    """Formats and delivers messages; remembers what it sent."""

    prefix = ""

    def __init__(self, name):
        self.name = name
        self.sent = []

    def format(self, text):
        return self.prefix + text

    def deliver(self, line):
        self.sent.append(line)
        return len(self.sent)

    def send(self, text):
        return self.deliver(self.format(text))
''', '''class $C0:
    """Formats and delivers messages; remembers what it sent."""

    prefix = ""

    def __init__(self, name):
        self.name = name
        self.sent = []
        self._d = _Delivery(self.sent, [self._prefixed], [])

    def _prefixed(self, text):
        return self.prefix + text

    def format(self, text):
        return self._d.format(text)

    def deliver(self, line):
        return self._d.deliver(line)

    def send(self, text):
        return self._d.send(text)
'''),
    "throttled": ('''class $C1($C0):
    """Refuses to send more than `limit` messages."""

    def __init__(self, name, limit):
        super().__init__(name)
        self.limit = limit

    def send(self, text):
        if len(self.sent) >= self.limit:
            raise RuntimeError("$LIMITMSG" % self.limit)
        return super().send(text)
''', '''class $C1:
    """Refuses to send more than `limit` messages."""

    prefix = ""

    def __init__(self, name, limit):
        self.name = name
        self.limit = limit
        self.sent = []
        self._d = _Delivery(self.sent, [self._prefixed], [self._check])

    def _prefixed(self, text):
        return self.prefix + text

    def _check(self):
        if len(self.sent) >= self.limit:
            raise RuntimeError("$LIMITMSG" % self.limit)

    def format(self, text):
        return self._d.format(text)

    def deliver(self, line):
        return self._d.deliver(line)

    def send(self, text):
        return self._d.send(text)
'''),
    "mail": ('''class $C2($C1):
    """Adds a mail prefix and a sender address."""

    prefix = "$PREFIX"

    def __init__(self, name, limit, domain):
        super().__init__(name, limit)
        self.domain = domain

    def format(self, text):
        return super().format(text) + " <%s@%s>" % (self.name, self.domain)
''', '''class $C2:
    """Adds a mail prefix and a sender address."""

    prefix = "$PREFIX"

    def __init__(self, name, limit, domain):
        self.name = name
        self.limit = limit
        self.domain = domain
        self.sent = []
        self._d = _Delivery(self.sent, [self._prefixed, self._addressed], [self._check])

    def _prefixed(self, text):
        return self.prefix + text

    def _addressed(self, text):
        return text + " <%s@%s>" % (self.name, self.domain)

    def _check(self):
        if len(self.sent) >= self.limit:
            raise RuntimeError("$LIMITMSG" % self.limit)

    def format(self, text):
        return self._d.format(text)

    def deliver(self, line):
        return self._d.deliver(line)

    def send(self, text):
        return self._d.send(text)
'''),
    "digest": ('''class $C3($C2):
    """Collects `size` messages and sends them as one."""

    def __init__(self, name, limit, domain, size):
        super().__init__(name, limit, domain)
        self.size = size
        self.buffer = []

    def send(self, text):
        self.buffer.append(text)
        if len(self.buffer) < self.size:
            return 0
        merged = "; ".join(self.buffer)
        self.buffer = []
        return super().send(merged)
''', '''class $C3:
    """Collects `size` messages and sends them as one."""

    prefix = "$PREFIX"

    def __init__(self, name, limit, domain, size):
        self.name = name
        self.limit = limit
        self.domain = domain
        self.size = size
        self.buffer = []
        self.sent = []
        self._d = _Delivery(self.sent, [self._prefixed, self._addressed], [self._check])

    def _prefixed(self, text):
        return self.prefix + text

    def _addressed(self, text):
        return text + " <%s@%s>" % (self.name, self.domain)

    def _check(self):
        if len(self.sent) >= self.limit:
            raise RuntimeError("$LIMITMSG" % self.limit)

    def format(self, text):
        return self._d.format(text)

    def deliver(self, line):
        return self._d.deliver(line)

    def send(self, text):
        self.buffer.append(text)
        if len(self.buffer) < self.size:
            return 0
        merged = "; ".join(self.buffer)
        self.buffer = []
        return self._d.send(merged)
'''),
}

CHANNEL_SOLUTION_HEAD = '''class _Delivery:
    """The shared mechanics: run the formatting steps, check the guards, record the line."""

    def __init__(self, sent, steps, guards):
        self.sent = sent
        self.steps = steps
        self.guards = guards

    def format(self, text):
        for step in self.steps:
            text = step(text)
        return text

    def deliver(self, line):
        self.sent.append(line)
        return len(self.sent)

    def send(self, text):
        for guard in self.guards:
            guard()
        return self.deliver(self.format(text))


'''

CHANNEL_HARNESS = '''from $PKG.core import $C0, $C1, $C2, $C3


def run_case(case):
    kind = case["kind"]
    makers = {
        "base": lambda: $C0(case["name"]),
        "throttled": lambda: $C1(case["name"], case["limit"]),
        "mail": lambda: $C2(case["name"], case["limit"], case["domain"]),
        "digest": lambda: $C3(case["name"], case["limit"], case["domain"], case["size"]),
    }
    ch = makers[kind]()
    results = []
    for text in case["messages"]:
        try:
            results.append(ch.send(text))
        except Exception as e:
            results.append("ERR %s %s" % (type(e).__name__, e))
    return {
        "results": results,
        "sent": ch.sent,
        "formatted": ch.format("probe"),
        "delivered": ch.deliver("raw"),
        "attrs": {a: getattr(ch, a) for a in ("name", "limit", "domain", "size", "buffer") if hasattr(ch, a)},
    }
'''


def channel_cases(rng, n, kinds):
    out = []
    for i in range(n):
        out.append({"kind": kinds[i % len(kinds)], "name": rng.choice(["ops", "alerts", "billing"]), "limit": rng.randint(1, 5), "domain": rng.choice(["example.org", "corp.test"]),
                    "size": rng.randint(1, 3), "messages": [rng.choice(["disk full", "ok", "retry 3", "paid"]) for _ in range(rng.randint(0, 8))]})
    return out


# ---------------------------------------------------------------------------------------------------------------------
# B: plans (unit price -> total -> describe), 4 levels
# ---------------------------------------------------------------------------------------------------------------------
PLAN_START = {
    "base": '''class $C0:
    """Per-seat pricing: unit price times seats."""

    label = "$L0"
    base_cents = $BASE

    def __init__(self, seats):
        self.seats = seats

    def unit_price(self):
        return self.base_cents

    def total(self):
        return self.unit_price() * self.seats

    def describe(self):
        return "%s x%d = %d" % (self.label, self.seats, self.total())
''',
    "volume": '''class $C1($C0):
    """Cheaper unit price from $THRESH seats."""

    label = "$L1"

    def unit_price(self):
        price = super().unit_price()
        if self.seats >= $THRESH:
            price = price * $VOL // 100
        return price
''',
    "edu": '''class $C2($C1):
    """A flat percentage of the (volume) unit price for schools."""

    label = "$L2"

    def unit_price(self):
        return super().unit_price() * $EDU // 100
''',
    "grant": '''class $C3($C2):
    """School pricing minus a fixed grant on the total (never below zero)."""

    label = "$L3"

    def __init__(self, seats, grant):
        super().__init__(seats)
        self.grant = grant

    def total(self):
        return max(0, super().total() - self.grant)
''',
}

PLAN_SOLUTION_HEAD = '''def _volume(price, seats):
    return price * $VOL // 100 if seats >= $THRESH else price


def _flat(price, seats):
    return price * $EDU // 100


class _Quote:
    """Pricing mechanics shared by all plans; the differences are plugged in as steps."""

    def __init__(self, plan, unit_steps=(), total_steps=()):
        self.plan = plan
        self.unit_steps = list(unit_steps)
        self.total_steps = list(total_steps)

    def unit_price(self):
        price = self.plan.base_cents
        for step in self.unit_steps:
            price = step(price, self.plan.seats)
        return price

    def total(self):
        amount = self.unit_price() * self.plan.seats
        for step in self.total_steps:
            amount = step(amount)
        return amount


def _describe(plan):
    return "%s x%d = %d" % (plan.label, plan.seats, plan.total())


'''


def _plan_solution(name, doc, label_var, unit_steps, total_steps, extra_init="", extra_params=""):
    return f'''class ${name}:
    """{doc}"""

    label = "${label_var}"
    base_cents = $BASE

    def __init__(self, seats{extra_params}):
        self.seats = seats
{extra_init}        self._quote = _Quote(self, [{unit_steps}], [{total_steps}])

    def unit_price(self):
        return self._quote.unit_price()

    def total(self):
        return self._quote.total()

    def describe(self):
        return _describe(self)
'''


PLAN_SOLUTION = {
    "base": _plan_solution("C0", "Per-seat pricing: unit price times seats.", "L0", "", ""),
    "volume": _plan_solution("C1", "Cheaper unit price from $THRESH seats.", "L1", "_volume", ""),
    "edu": _plan_solution("C2", "A flat percentage of the (volume) unit price for schools.", "L2", "_volume, _flat", ""),
    "grant": _plan_solution("C3", "School pricing minus a fixed grant on the total (never below zero).", "L3", "_volume, _flat", "lambda amount: max(0, amount - self.grant)",
                            extra_init="        self.grant = grant\n", extra_params=", grant"),
}

PLAN_HARNESS = '''from $PKG.core import $C0, $C1, $C2, $C3


def run_case(case):
    kind = case["kind"]
    makers = {
        "base": lambda: $C0(case["seats"]),
        "volume": lambda: $C1(case["seats"]),
        "edu": lambda: $C2(case["seats"]),
        "grant": lambda: $C3(case["seats"], case["grant"]),
    }
    plan = makers[kind]()
    rows = []
    for seats in case["sizes"]:
        plan.seats = seats
        rows.append([plan.unit_price(), plan.total(), plan.describe()])
    plan.base_cents = case["base"]
    return {
        "first": [plan.label, plan.seats],
        "rows": rows,
        "repriced": [plan.unit_price(), plan.total(), plan.describe()],
        "grant": getattr(plan, "grant", None),
    }
'''


def plan_cases(rng, n, kinds):
    out = []
    for i in range(n):
        out.append({"kind": kinds[i % len(kinds)], "seats": rng.choice([1, 3, 9, 10, 11, 25, 60]), "grant": rng.choice([0, 500, 5000, 100000]),
                    "sizes": [rng.choice([1, 5, 9, 10, 12, 24, 25, 50, 200]) for _ in range(rng.randint(1, 4))], "base": rng.choice([700, 1000, 2500])})
    return out


# ---------------------------------------------------------------------------------------------------------------------
# C: stores (audit, quota, expiry), 4 levels; get() on the expiring store calls delete() which must still be audited
# ---------------------------------------------------------------------------------------------------------------------
STORE_START = {
    "base": '''class $C0:
    """In-memory store with get, put and delete."""

    def __init__(self):
        self.data = {}
        self.reads = 0

    def get(self, key, default=None):
        self.reads += 1
        return self.data.get(key, default)

    def put(self, key, value):
        self.data[key] = value

    def delete(self, key):
        return self.data.pop(key, None)
''',
    "audit": '''class $C1($C0):
    """Remembers every change in `log`."""

    def __init__(self):
        super().__init__()
        self.log = []

    def put(self, key, value):
        self.log.append(("put", key))
        super().put(key, value)

    def delete(self, key):
        self.log.append(("delete", key))
        return super().delete(key)
''',
    "quota": '''class $C2($C1):
    """Refuses new keys beyond `max_keys`."""

    def __init__(self, max_keys):
        super().__init__()
        self.max_keys = max_keys

    def put(self, key, value):
        if key not in self.data and len(self.data) >= self.max_keys:
            raise KeyError("$QUOTAMSG" % self.max_keys)
        super().put(key, value)
''',
    "expiry": '''class $C3($C2):
    """Entries live for `ttl` ticks; call tick() to advance the clock."""

    def __init__(self, max_keys, ttl):
        super().__init__(max_keys)
        self.ttl = ttl
        self.now = 0
        self.born = {}

    def put(self, key, value):
        super().put(key, value)
        self.born[key] = self.now

    def get(self, key, default=None):
        if key in self.born and self.now - self.born[key] >= self.ttl:
            self.delete(key)
        return super().get(key, default)

    def delete(self, key):
        self.born.pop(key, None)
        return super().delete(key)

    def tick(self, n=1):
        self.now += n
''',
}

STORE_SOLUTION_HEAD = '''class _Memory:
    """The dictionary and the read counter."""

    def __init__(self):
        self.data = {}
        self.reads = 0

    def get(self, key, default=None):
        self.reads += 1
        return self.data.get(key, default)

    def put(self, key, value):
        self.data[key] = value

    def delete(self, key):
        return self.data.pop(key, None)


'''

STORE_SOLUTION = {
    "base": '''class $C0:
    """In-memory store with get, put and delete."""

    def __init__(self):
        self._mem = _Memory()
        self.data = self._mem.data

    @property
    def reads(self):
        return self._mem.reads

    def get(self, key, default=None):
        return self._mem.get(key, default)

    def put(self, key, value):
        self._mem.put(key, value)

    def delete(self, key):
        return self._mem.delete(key)
''',
    "audit": '''class $C1:
    """Remembers every change in `log`."""

    def __init__(self):
        self._mem = _Memory()
        self.data = self._mem.data
        self.log = []

    @property
    def reads(self):
        return self._mem.reads

    def get(self, key, default=None):
        return self._mem.get(key, default)

    def put(self, key, value):
        self.log.append(("put", key))
        self._mem.put(key, value)

    def delete(self, key):
        self.log.append(("delete", key))
        return self._mem.delete(key)
''',
    "quota": '''class $C2:
    """Refuses new keys beyond `max_keys`."""

    def __init__(self, max_keys):
        self._mem = _Memory()
        self.data = self._mem.data
        self.log = []
        self.max_keys = max_keys

    @property
    def reads(self):
        return self._mem.reads

    def get(self, key, default=None):
        return self._mem.get(key, default)

    def put(self, key, value):
        if key not in self.data and len(self.data) >= self.max_keys:
            raise KeyError("$QUOTAMSG" % self.max_keys)
        self.log.append(("put", key))
        self._mem.put(key, value)

    def delete(self, key):
        self.log.append(("delete", key))
        return self._mem.delete(key)
''',
    "expiry": '''class $C3:
    """Entries live for `ttl` ticks; call tick() to advance the clock."""

    def __init__(self, max_keys, ttl):
        self._mem = _Memory()
        self.data = self._mem.data
        self.log = []
        self.max_keys = max_keys
        self.ttl = ttl
        self.now = 0
        self.born = {}

    @property
    def reads(self):
        return self._mem.reads

    def get(self, key, default=None):
        if key in self.born and self.now - self.born[key] >= self.ttl:
            self.delete(key)
        return self._mem.get(key, default)

    def put(self, key, value):
        if key not in self.data and len(self.data) >= self.max_keys:
            raise KeyError("$QUOTAMSG" % self.max_keys)
        self.log.append(("put", key))
        self._mem.put(key, value)
        self.born[key] = self.now

    def delete(self, key):
        self.born.pop(key, None)
        self.log.append(("delete", key))
        return self._mem.delete(key)

    def tick(self, n=1):
        self.now += n
''',
}

STORE_HARNESS = '''from $PKG.core import $C0, $C1, $C2, $C3


def run_case(case):
    kind = case["kind"]
    makers = {
        "base": lambda: $C0(),
        "audit": lambda: $C1(),
        "quota": lambda: $C2(case["max_keys"]),
        "expiry": lambda: $C3(case["max_keys"], case["ttl"]),
    }
    store = makers[kind]()
    results = []
    for op in case["ops"]:
        name, args = op[0], op[1:]
        try:
            results.append(getattr(store, name)(*args))
        except Exception as e:
            results.append("ERR %s %s" % (type(e).__name__, e))
    return {
        "results": results,
        "data": store.data,
        "reads": store.reads,
        "state": {a: getattr(store, a) for a in ("log", "max_keys", "ttl", "now", "born") if hasattr(store, a)},
    }
'''


def store_cases(rng, n, kinds):
    out = []
    for i in range(n):
        ops = []
        for _ in range(rng.randint(2, 12)):
            r = rng.random()
            key = rng.choice(["a", "b", "c", "d"])
            if r < 0.4:
                ops.append(["put", key, rng.randint(0, 9)])
            elif r < 0.65:
                ops.append(["get", key])
            elif r < 0.75:
                ops.append(["delete", key])
            else:
                ops.append(["tick", rng.randint(1, 3)])
        out.append({"kind": kinds[i % len(kinds)], "max_keys": rng.randint(1, 3), "ttl": rng.randint(1, 4), "ops": ops})
    return out


HIERARCHIES = {
    "channels": dict(kinds=["base", "throttled", "mail", "digest"], start=CHANNEL_PARTS, harness=CHANNEL_HARNESS, cases=channel_cases, head_sol=CHANNEL_SOLUTION_HEAD,
                     doc="Message channels.", unit="channel", d={3: 3, 4: 4},
                     attrs="`name`, `sent`, `limit`, `domain`, `size`, `buffer` (whichever the class has today)",
                     variants=[dict(C0="Channel", C1="ThrottledChannel", C2="MailChannel", C3="DigestChannel", PKG="notify", PREFIX="[mail] ", LIMITMSG="limit of %d reached"),
                               dict(C0="Sender", C1="LimitedSender", C2="SmtpSender", C3="BatchSender", PKG="outbound", PREFIX="MAIL: ", LIMITMSG="too many messages (max %d)"),
                               dict(C0="Outbox", C1="BoundedOutbox", C2="MailOutbox", C3="DigestOutbox", PKG="mailer", PREFIX="(email) ", LIMITMSG="quota exhausted at %d"),
                               dict(C0="Feed", C1="CappedFeed", C2="EmailFeed", C3="SummaryFeed", PKG="feeds", PREFIX=">> ", LIMITMSG="feed is full (%d entries)")]),
    "plans": dict(kinds=["base", "volume", "edu", "grant"], start=PLAN_START, harness=PLAN_HARNESS, cases=plan_cases, head_sol=PLAN_SOLUTION_HEAD, sol=PLAN_SOLUTION,
                  doc="Subscription pricing.", unit="plan", d={3: 3, 4: 4},
                  attrs="`label`, `base_cents`, `seats`, `grant` (whichever the class has today), all readable and assignable",
                  variants=[dict(C0="Plan", C1="VolumePlan", C2="EduPlan", C3="GrantPlan", PKG="billing", L0="plan", L1="volume", L2="edu", L3="grant", BASE="1000", THRESH="10", VOL="90", EDU="50"),
                            dict(C0="Tariff", C1="BulkTariff", C2="SchoolTariff", C3="SponsoredTariff", PKG="tariffs", L0="standard", L1="bulk", L2="school", L3="sponsored", BASE="1500", THRESH="20", VOL="85", EDU="40"),
                            dict(C0="Licence", C1="SeatLicence", C2="CampusLicence", C3="SubsidisedLicence", PKG="licensing", L0="single", L1="seats", L2="campus", L3="subsidised", BASE="2400", THRESH="25", VOL="80", EDU="60")]),
    "stores": dict(kinds=["base", "audit", "quota", "expiry"], start=STORE_START, harness=STORE_HARNESS, cases=store_cases, head_sol=STORE_SOLUTION_HEAD, sol=STORE_SOLUTION,
                   doc="Key-value stores.", unit="store", d={3: 4, 4: 5},
                   attrs="`data`, `reads`, `log`, `max_keys`, `ttl`, `now`, `born` (whichever the class has today)",
                   variants=[dict(C0="Store", C1="AuditedStore", C2="QuotaStore", C3="ExpiringStore", PKG="kvstore", QUOTAMSG="quota of %d keys reached"),
                             dict(C0="Cache", C1="JournalCache", C2="BoundedCache", C3="TtlCache", PKG="cachekit", QUOTAMSG="cache full: %d keys"),
                             dict(C0="Registry", C1="TrackedRegistry", C2="LimitedRegistry", C3="LeaseRegistry", PKG="registry", QUOTAMSG="registry limit %d reached")]),
}
