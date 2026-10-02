"""Repository-wide mechanical API migrations, split by directory: one worker per service directory."""
from __future__ import annotations

import base64
import json
import re
import zlib

from fx import Task, dd, family, merged, run

from ._kit import GRADE_CMD, oxford, score_script, team

SERVICES = ["billing", "shipping", "reports", "portal", "scheduler", "inventory", "payroll", "notices", "ticketing", "loyalty"]
FILES = {
    "billing": ["invoices", "receipts", "statements", "refunds"], "shipping": ["labels", "manifests", "rates", "tracking"],
    "reports": ["daily", "weekly", "exports", "digest"], "portal": ["profile", "orders", "account", "support"],
    "scheduler": ["jobs", "windows", "retries", "calendar"], "inventory": ["stock", "reorder", "counts", "audit"],
    "payroll": ["runs", "slips", "adjust", "taxes"], "notices": ["email", "sms", "letters", "banners"],
    "ticketing": ["queue", "sla", "escalate", "digest"], "loyalty": ["points", "tiers", "offers", "expiry"],
}


# ================================================================================================= migrations
class Mig:
    name = ""
    old_mod = ""
    old_name = ""
    new_mod = ""
    new_name = ""
    shim: dict = {}
    newlib: dict = {}
    doc = ""
    templates: list = []
    decoy = ""
    tomb: dict = {}
    capture = False

    def old_import(self, style):
        if style == "from":
            return f"from {self.old_mod} import {self.old_name}", self.old_name
        if style == "alias":
            return f"from {self.old_mod} import {self.old_name} as {self.alias}", self.alias
        return f"import {self.old_mod} as {self.modalias}", f"{self.modalias}.{self.old_name}"

    def new_import(self):
        return f"from {self.new_mod} import {self.new_name}"


def render(template, calls):
    out = template
    for key, text in calls.items():
        out = out.replace(f"@{key}@", text)
    return out


def multiline(fn, args, indent="    "):
    return fn + "(\n" + "".join(f"{indent}{a},\n" for a in args) + ")"


# ----------------------------------------------------------------------------------------------------- money
class Money(Mig):
    name = "money"
    old_mod, old_name, new_mod, new_name = "legacy.money", "fmt_money", "ledgerfmt", "money_text"
    alias, modalias = "fm", "lm"
    shim = {
        "legacy/__init__.py": '"""Deprecated helpers. Everything here is a thin wrapper around the new packages and goes away next release."""\n',
        "legacy/money.py": dd('''
            """Deprecated: use ledgerfmt.money_text."""
            from ledgerfmt import money_text


            def fmt_money(cents, currency="EUR", sep=","):
                return money_text(currency, cents, thousands=sep)
        '''),
    }
    newlib = {
        "ledgerfmt/__init__.py": dd('''
            """Money formatting."""


            def money_text(currency, cents, *, thousands=","):
                """`EUR 1,234.50`: currency code, a space, the amount with grouped thousands and two decimals."""
                sign = "-" if cents < 0 else ""
                whole, frac = divmod(abs(cents), 100)
                digits = f"{whole:,}".replace(",", thousands)
                return f"{currency} {sign}{digits}.{frac:02d}"
        '''),
    }
    tomb = {"legacy/money.py": 'def fmt_money(*a, **k):\n    raise RuntimeError("legacy.money was removed")\n'}
    doc = dd('''
        ### Money formatting

        `legacy.money.fmt_money(cents, currency="EUR", sep=",")` is replaced by
        `ledgerfmt.money_text(currency, cents, *, thousands=",")` (import it with `from ledgerfmt import money_text`).

        * the first two parameters swap places: the currency now comes first and is **required**; a call that relied on the
          old default must now pass `"EUR"` explicitly;
        * `sep` is now the keyword-only `thousands`;
        * the output is identical.
    ''')

    def old_call(self, name, spec, form):
        c, cur, sep = spec["cents"], spec.get("cur"), spec.get("sep")
        if form == "kw":
            parts = [f"cents={c}"] + ([f"currency={cur}"] if cur else []) + ([f"sep={sep}"] if sep else [])
            return f"{name}({', '.join(parts)})"
        if sep and not cur:
            return f"{name}({c}, sep={sep})"
        args = [c] + ([cur] if cur else []) + ([sep] if sep else [])
        if form == "multi":
            return multiline(name, args)
        return f"{name}({', '.join(args)})"

    def new_call(self, spec):
        args = [spec.get("cur") or '"EUR"', spec["cents"]] + ([f"thousands={spec['sep']}"] if spec.get("sep") else [])
        return f"{self.new_name}({', '.join(args)})"

    templates = [
        dict(code='def {fn}(label, qty, unit_cents):\n    total = qty * unit_cents\n    return label + ": " + @c0@\n',
             calls=[dict(cents="total", cur=[None, "'GBP'"], sep=[None, "' '"])], args=[["tea", 3, 1450], ["rope", 12, 999], ["tin", 0, 5]]),
        dict(code='def {fn}(total_cents, tip_cents, cur):\n    return "Total " + @c0@ + " (tip " + @c1@ + ")"\n',
             calls=[dict(cents="total_cents", cur=["cur"], sep=[None]), dict(cents="tip_cents", cur=["cur"], sep=["'.'", None])],
             args=[[123456, 500, "USD"], [99, 0, "EUR"], [-250, 10, "GBP"]]),
        dict(code='def {fn}(name, cents):\n    return f"{name:<12}{@c0@:>16}"\n', fstring=True,
             calls=[dict(cents="cents", cur=["'EUR'", "'CHF'"], sep=[None])], args=[["widget", 123456], ["gadget", -99], ["bolt", 100000000]]),
        dict(code='def {fn}(order):\n    parts = []\n    for item in order["items"]:\n        parts.append(@c0@)\n    return ", ".join(parts)\n',
             calls=[dict(cents='item["cents"]', cur=['order["cur"]'], sep=[None, "'_'"])],
             args=[[{"cur": "EUR", "items": [{"cents": 500}, {"cents": 1200000}]}], [{"cur": "USD", "items": []}], [{"cur": "GBP", "items": [{"cents": 7}]}]]),
        dict(code='def {fn}(rows, cur):\n    return [@c0@ for cents in rows]\n',
             calls=[dict(cents="cents", cur=["cur"], sep=[None, "'.'"])], args=[[[100, 250000, 5], "EUR"], [[], "USD"], [[1000000, -1], "CHF"]]),
        dict(code='def {fn}(order):\n    refund = order["refund"]\n    if refund <= 0:\n        return "no refund"\n    return "Refund of " + @c0@ + " issued"\n',
             calls=[dict(cents="refund", cur=[None, 'order["cur"]'], sep=[None, "' '"])],
             args=[[{"refund": 0, "cur": "EUR"}], [{"refund": 123456, "cur": "USD"}], [{"refund": 5, "cur": "GBP"}]]),
        dict(code='def {fn}(a_cents, b_cents):\n    diff = a_cents - b_cents\n    return @c0@ if diff else "even"\n',
             calls=[dict(cents="diff", cur=["'EUR'", "'NOK'"], sep=[None])], args=[[500, 500], [1000, 25], [3, 4000000]]),
    ]
    decoy = dd('''
        class Ledger:
            """A look-alike: this is NOT the deprecated helper and must keep its name."""

            def fmt_money(self, cents):
                return str(cents)


        def {fn}(cents):
            return Ledger().fmt_money(cents)
    ''')


# ------------------------------------------------------------------------------------------------------ dates
class Dates(Mig):
    name = "dates"
    old_mod, old_name, new_mod, new_name = "legacy.dates", "parse_day", "calkit.dates", "parse_or_none"
    alias, modalias = "pd", "ld"
    shim = {
        "legacy/__init__.py": '"""Deprecated helpers; thin wrappers around the new packages."""\n',
        "legacy/dates.py": dd('''
            """Deprecated: use calkit.dates.parse_or_none."""
            from calkit.dates import parse_or_none


            def parse_day(text, fmt="%Y-%m-%d"):
                return parse_or_none(text, fmt=fmt)
        '''),
    }
    newlib = {
        "calkit/__init__.py": "",
        "calkit/dates.py": dd('''
            """Date parsing."""
            from datetime import datetime


            def parse_or_none(text, *, fmt="%Y-%m-%d"):
                """The date for `text` in `fmt`, or None when it does not match."""
                try:
                    return datetime.strptime(text.strip(), fmt).date()
                except (ValueError, AttributeError):
                    return None
        '''),
    }
    tomb = {"legacy/dates.py": 'def parse_day(*a, **k):\n    raise RuntimeError("legacy.dates was removed")\n'}
    doc = dd('''
        ### Date parsing

        `legacy.dates.parse_day(text, fmt="%Y-%m-%d")` is replaced by `calkit.dates.parse_or_none(text, *, fmt="%Y-%m-%d")`
        (`from calkit.dates import parse_or_none`).

        * the function has a new name;
        * `fmt` is keyword-only now: `parse_day(t, "%d/%m/%Y")` becomes `parse_or_none(t, fmt="%d/%m/%Y")`;
        * the result (a `date`, or `None` for text that does not match) is unchanged.
    ''')

    def old_call(self, name, spec, form):
        t, fmt = spec["text"], spec.get("fmt")
        if form == "kw" and fmt:
            return f"{name}({t}, fmt={fmt})"
        args = [t] + ([fmt] if fmt else [])
        if form == "multi":
            return multiline(name, args)
        return f"{name}({', '.join(args)})"

    def new_call(self, spec):
        return f"{self.new_name}({spec['text']}" + (f", fmt={spec['fmt']}" if spec.get("fmt") else "") + ")"

    templates = [
        dict(code='def {fn}(text):\n    day = @c0@\n    return None if day is None else day.isoformat()\n',
             calls=[dict(text="text", fmt=[None, "'%d/%m/%Y'"])], args=[["2024-03-09"], ["31/12/2023"], ["not a date"], [" 2024-01-05 "]]),
        dict(code='def {fn}(first, last):\n    a, b = @c0@, @c1@\n    if a is None or b is None:\n        return -1\n    return (b - a).days\n',
             calls=[dict(text="first", fmt=[None, "'%d.%m.%Y'"]), dict(text="last", fmt=[None, "'%d.%m.%Y'"])],
             args=[["2024-01-01", "2024-03-01"], ["2024-02-30", "2024-03-01"], ["2023-12-31", "2023-12-31"]]),
        dict(code='def {fn}(rows):\n    good = [d for d in (@c0@ for r in rows) if d is not None]\n    return sorted(d.isoformat() for d in good)\n',
             calls=[dict(text="r", fmt=[None, "'%b %d %Y'", "'%Y/%m/%d'"])], args=[[["2024-05-01", "2023-01-09", "bad"]], [[]], [["2024/02/29", "2025/02/29"]]]),
        dict(code='def {fn}(raw):\n    parsed = @c0@\n    if parsed:\n        return "%s (%s)" % (parsed.isoformat(), parsed.strftime("%A"))\n    return "unknown"\n',
             calls=[dict(text="raw", fmt=[None, "'%d %B %Y'"])], args=[["2024-02-29"], ["1 January 2025"], ["??"]]),
        dict(code='def {fn}(expiry, today):\n    when, now = @c0@, @c1@\n    return bool(when and now and when < now)\n',
             calls=[dict(text="expiry", fmt=[None, "'%m/%d/%y'"]), dict(text="today", fmt=[None, "'%m/%d/%y'"])],
             args=[["2024-01-01", "2024-06-01"], ["2025-01-01", "2024-06-01"], ["x", "2024-06-01"]]),
    ]
    decoy = dd('''
        class Calendar:
            """A look-alike that is NOT the deprecated helper."""

            def parse_day(self, text):
                return text.split("-")


        def {fn}(text):
            return Calendar().parse_day(text)
    ''')


# ---------------------------------------------------------------------------------------------------- logging
class Logging(Mig):
    name = "logging"
    old_mod, old_name, new_mod, new_name = "legacy.log", "say", "obslog", "emit"
    alias, modalias = "log_say", "ll"
    capture = True
    shim = {
        "legacy/__init__.py": '"""Deprecated helpers; thin wrappers around the new packages."""\n',
        "legacy/log.py": dd('''
            """Deprecated: use obslog.emit."""
            from obslog import emit


            def say(level, msg, *args):
                emit(msg, *args, level=level)
        '''),
    }
    newlib = {
        "obslog/__init__.py": dd('''
            """Tiny structured log: records are kept in memory (the real sink is configured elsewhere)."""

            RECORDS = []


            def emit(msg, *args, level="info"):
                RECORDS.append((level, msg % args if args else msg))
        '''),
    }
    tomb = {"legacy/log.py": 'def say(*a, **k):\n    raise RuntimeError("legacy.log was removed")\n'}
    doc = dd('''
        ### Logging

        `legacy.log.say(level, msg, *args)` is replaced by `obslog.emit(msg, *args, level="info")`
        (`from obslog import emit`).

        * the level moves from the first positional parameter to the keyword-only `level`, at the end of the call:
          `say("warn", "disk %s full", name)` becomes `emit("disk %s full", name, level="warn")`;
        * the level may be a literal or any expression; keep the expression as it was;
        * `msg` and `args` are unchanged, and so are the records written.
    ''')

    def old_call(self, name, spec, form):
        args = [spec["level"], spec["msg"]] + spec.get("args", [])
        if form == "multi":
            return multiline(name, args)
        return f"{name}({', '.join(args)})"

    def new_call(self, spec):
        return f"{self.new_name}({', '.join([spec['msg']] + spec.get('args', []) + ['level=' + spec['level']])})"

    templates = [
        dict(code='def {fn}(host):\n    @c0@\n    return host.upper()\n',
             calls=[dict(level=["'info'", "'debug'"], msg=['"connecting to %s"'], args=[["host"]])], args=[["db1"], ["cache.internal"]]),
        dict(code='def {fn}(n, limit):\n    if n > limit:\n        @c0@\n        return limit\n    return n\n',
             calls=[dict(level=["'warn'", "'error'"], msg=['"%d is over the limit of %d"'], args=[["n", "limit"]])], args=[[5, 3], [2, 3], [3, 3]]),
        dict(code='def {fn}(level, text):\n    @c0@\n    return len(text)\n',
             calls=[dict(level=["level"], msg=['"message: %s"'], args=[["text"]])], args=[["info", "hello"], ["warn", ""], ["error", "disk full"]]),
        dict(code='def {fn}(items):\n    total = 0\n    for it in items:\n        total += it\n    @c0@\n    return total\n',
             calls=[dict(level=["'info'"], msg=['"summed %d items"'], args=[["len(items)"]])], args=[[[1, 2, 3]], [[]], [[10]]]),
        dict(code='def {fn}(user, ok):\n    if ok:\n        @c0@\n    else:\n        @c1@\n    return ok\n',
             calls=[dict(level=["'info'"], msg=['"login ok for %s"'], args=[["user"]]), dict(level=["'warn'"], msg=['"login failed for %s"'], args=[["user"]])],
             args=[["ann", True], ["bo", False]]),
        dict(code='def {fn}(job):\n    @c0@\n    return job\n',
             calls=[dict(level=["'info'"], msg=['"starting"'], args=[[]])], args=[["nightly"], ["sync"]]),
    ]
    decoy = dd('''
        class Chatter:
            """A look-alike that is NOT the deprecated helper."""

            def say(self, level, msg):
                return level + ":" + msg


        def {fn}(msg):
            return Chatter().say("info", msg)
    ''')


# ------------------------------------------------------------------------------------------------------ net
class Net(Mig):
    name = "net"
    old_mod, old_name, new_mod, new_name = "legacy.net", "connect", "netkit", "dial"
    alias, modalias = "open_conn", "ln"
    shim = {
        "legacy/__init__.py": '"""Deprecated helpers; thin wrappers around the new packages."""\n',
        "legacy/net.py": dd('''
            """Deprecated: use netkit.dial."""
            from netkit import dial


            def connect(host, port=80, timeout=5):
                return dial(host, port, timeout_ms=timeout * 1000)
        '''),
    }
    newlib = {
        "netkit/__init__.py": dd('''
            """A stand-in network layer: dial() just records what it was asked to do."""


            def dial(host, port=80, *, timeout_ms=5000):
                return {"host": host, "port": port, "timeout_ms": int(round(timeout_ms))}
        '''),
    }
    tomb = {"legacy/net.py": 'def connect(*a, **k):\n    raise RuntimeError("legacy.net was removed")\n'}
    doc = dd('''
        ### Network connections

        `legacy.net.connect(host, port=80, timeout=5)` is replaced by `netkit.dial(host, port=80, *, timeout_ms=5000)`
        (`from netkit import dial`).

        * the function has a new name and `timeout` (seconds) became `timeout_ms` (milliseconds), keyword-only: a timeout of
          2.5 seconds is `timeout_ms=2500`, and a timeout held in a variable `t` becomes `timeout_ms=t * 1000`;
        * the port stays positional and keeps its default;
        * a call that does not pass a timeout does not pass `timeout_ms` either (the new default, 5000, is the old 5 seconds);
        * `dial` accepts ints or floats and returns the same dictionary the old call produced.
    ''')

    def old_call(self, name, spec, form):
        h, port, t = spec["host"], spec.get("port"), spec.get("timeout")
        if form == "kw":
            parts = [h] + ([f"port={port}"] if port else []) + ([f"timeout={t}"] if t else [])
            return f"{name}({', '.join(parts)})"
        if t and not port:
            return f"{name}({h}, timeout={t})" if form != "pos3" else f"{name}({h}, 80, {t})"
        args = [h] + ([port] if port else []) + ([t] if t else [])
        if form == "multi":
            return multiline(name, args)
        return f"{name}({', '.join(args)})"

    def new_call(self, spec):
        h, port, t = spec["host"], spec.get("port"), spec.get("timeout")
        args = [h] + ([port] if port else [])
        if t:
            if re.fullmatch(r"[0-9]+(\.[0-9]+)?", t):
                ms = int(round(float(t) * 1000))
                args.append(f"timeout_ms={ms}")
            else:
                args.append(f"timeout_ms={t} * 1000")
        return f"{self.new_name}({', '.join(args)})"

    templates = [
        dict(code='def {fn}(host):\n    return @c0@\n', calls=[dict(host="host", port=[None, "8080"], timeout=[None, "2.5", "10"])], args=[["a.example"], ["b.example"]]),
        dict(code='def {fn}(host, t):\n    conn = @c0@\n    conn["via"] = "fast"\n    return conn\n',
             calls=[dict(host="host", port=[None, "443"], timeout=["t"])], args=[["a", 1.5], ["b", 0.25], ["c", 7]]),
        dict(code='def {fn}(hosts):\n    return [@c0@ for h in hosts]\n', calls=[dict(host="h", port=[None], timeout=["0.5", "3"])], args=[[["x", "y"]], [[]]]),
        dict(code='def {fn}(cfg):\n    return @c0@\n', calls=[dict(host='cfg["host"]', port=['cfg["port"]'], timeout=['cfg["timeout"]'])],
             args=[[{"host": "h1", "port": 22, "timeout": 2.5}], [{"host": "h2", "port": 8, "timeout": 12}]]),
        dict(code='def {fn}(primary, backup, t):\n    first = @c0@\n    second = @c1@\n    return [first, second]\n',
             calls=[dict(host="primary", port=[None], timeout=["t"]), dict(host="backup", port=["2222"], timeout=[None])],
             args=[["p", "b", 1.25], ["p2", "b2", 4]]),
    ]
    decoy = dd('''
        class Pool:
            """A look-alike that is NOT the deprecated helper."""

            def connect(self, host, timeout=1):
                return (host, timeout)


        def {fn}(host):
            return Pool().connect(host, timeout=3)
    ''')


MIGS = {m.name: m for m in (Money(), Dates(), Logging(), Net())}

# ================================================================================================= generation
def build_dir(rng, mig, svc, nfiles, style, fn_counter):
    """Returns (old files, new files, cases) for one service directory."""
    files_old, files_new, cases = {}, {}, []
    names = list(FILES[svc])
    rng.shuffle(names)
    for fi in range(nfiles):
        mod_name = names[fi % len(names)]
        tpls = list(mig.templates)
        rng.shuffle(tpls)
        chosen = tpls[: rng.randint(2, 4)]
        old_imp, old_callee = mig.old_import(style)
        body_old, body_new, fnames = [], [], []
        forms = ["pos", "kw", "multi", "posfull", "pos3"]
        for t in chosen:
            fn_counter[0] += 1
            fn = f"{rng.choice(['render', 'build', 'make', 'format', 'prepare', 'compute', 'show'])}_{mod_name}_{fn_counter[0]}"
            calls_old, calls_new = {}, {}
            for ci, spec_opts in enumerate(t["calls"]):
                spec = {k: (rng.choice(v) if isinstance(v, list) else v) for k, v in spec_opts.items()}
                if mig.name == "logging":
                    spec["args"] = list(spec.get("args") or [])
                    spec["msg"] = spec["msg"]
                    spec["args"] = spec["args"] if isinstance(spec["args"], list) else []
                form = rng.choice(forms)
                if t.get("fstring") and form == "multi":
                    form = "pos"
                if "@c%d@" % ci in t["code"] and t["code"].count("\n") and form == "multi":
                    # a multi-line call needs a statement context that allows it: all templates do, except f-strings
                    pass
                calls_old[f"c{ci}"] = mig.old_call(old_callee, spec, form)
                calls_new[f"c{ci}"] = mig.new_call(spec)
            code = t["code"].replace("{fn}", fn)
            body_old.append(render(code, calls_old))
            body_new.append(render(code, calls_new))
            fnames.append((fn, t["args"]))
        header_doc = f'"""{svc}: {mod_name} helpers."""\n'
        decoy_src = ""
        decoy_fn = None
        if rng.random() < 0.45:
            fn_counter[0] += 1
            decoy_fn = f"plain_{mod_name}_{fn_counter[0]}"
            decoy_src = "\n\n" + mig.decoy.replace("{fn}", decoy_fn)
        old_text = header_doc + old_imp + "\n\n\n" + "\n\n".join(body_old).rstrip("\n") + "\n" + (decoy_src if decoy_src else "")
        new_text = header_doc + mig.new_import() + "\n\n\n" + "\n\n".join(body_new).rstrip("\n") + "\n" + (decoy_src if decoy_src else "")
        path = f"{svc}/{mod_name}.py"
        files_old[path] = old_text
        files_new[path] = new_text
        for fn, arglists in fnames:
            for a in arglists:
                cases.append({"module": f"{svc}.{mod_name}", "fn": fn, "args": a})
        if decoy_fn:
            cases.append({"module": f"{svc}.{mod_name}", "fn": decoy_fn, "args": [{"money": 1234, "dates": "2024-05-06", "logging": "hello", "net": "h"}[mig.name]]})
    files_old[f"{svc}/__init__.py"] = f'"""{svc} service."""\n'
    files_new[f"{svc}/__init__.py"] = files_old[f"{svc}/__init__.py"]
    return files_old, files_new, cases


RECORD_SCRIPT = '''import base64, importlib, json, sys, zlib
sys.path.insert(0, ".")
cases = json.load(open("_cases.json"))
capture = %(capture)s
out = []
for c in cases:
    mod = importlib.import_module(c["module"])
    if capture:
        import obslog
        obslog.RECORDS.clear()
    res = getattr(mod, c["fn"])(*json.loads(json.dumps(c["args"])))
    rec = {"result": res}
    if capture:
        rec["records"] = [list(r) for r in obslog.RECORDS]
    out.append(json.loads(json.dumps(rec)))
print(base64.b64encode(zlib.compress(json.dumps(out).encode(), 9)).decode())
'''

CHECK = '''import ast
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

DATA = json.loads(%(data)r)
OLD_NAMES = DATA["old_names"]
MODS = DATA["old_modules"]


def fail(msg):
    print("FAILED:", msg, file=sys.stderr)
    sys.exit(1)


def static(root, svc):
    base = os.path.join(root, svc)
    if not os.path.isdir(base):
        fail("directory %%s is missing" %% svc)
    for dirpath, _, files in os.walk(base):
        for f in sorted(files):
            if not f.endswith(".py"):
                continue
            path = os.path.join(dirpath, f)
            tree = ast.parse(open(path, encoding="utf-8").read(), path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and (node.module in MODS or node.module.split(".")[0] == "legacy"):
                    fail("%%s:%%d still imports from %%s" %% (path, node.lineno, node.module))
                if isinstance(node, ast.Import):
                    for a in node.names:
                        if a.name in MODS or a.name.split(".")[0] == "legacy":
                            fail("%%s:%%d still imports %%s" %% (path, node.lineno, a.name))
                if isinstance(node, ast.Name) and node.id in OLD_NAMES + DATA["aliases"]:
                    fail("%%s:%%d still uses the legacy name %%s" %% (path, node.lineno, node.id))


def behaviour(root, svc):
    cases = [c for c in DATA["cases"] if c["module"].split(".")[0] == svc]
    want = [w for c, w in zip(DATA["cases"], DATA["expected"]) if c["module"].split(".")[0] == svc]
    sys.path.insert(0, root)
    capture = DATA["capture"]
    for c, w in zip(cases, want):
        mod = importlib.import_module(c["module"])
        if capture:
            import obslog
            obslog.RECORDS.clear()
        try:
            res = getattr(mod, c["fn"])(*json.loads(json.dumps(c["args"])))
        except Exception as e:  # noqa: BLE001
            fail("%%s.%%s(%%r) raised %%s: %%s" %% (c["module"], c["fn"], c["args"], type(e).__name__, e))
        got = {"result": res}
        if capture:
            got["records"] = [list(r) for r in obslog.RECORDS]
        got = json.loads(json.dumps(got))
        if got != w:
            fail("%%s.%%s(%%r)\\n  got  %%r\\n  want %%r" %% (c["module"], c["fn"], c["args"], got, w))


if __name__ == "__main__":
    what = sys.argv[1]
    if what == "tombstone":
        tmp = tempfile.mkdtemp()
        dst = os.path.join(tmp, "repo")
        shutil.copytree(".", dst, ignore=shutil.ignore_patterns(".git", "__pycache__", ".grade"))
        for rel, text in DATA["tomb"].items():
            with open(os.path.join(dst, rel), "w", encoding="utf-8") as f:
                f.write(text)
        for svc in DATA["services"]:
            p = subprocess.run([sys.executable, os.path.abspath(__file__), "behaviour", svc, dst], cwd=dst, capture_output=True, text=True)
            if p.returncode != 0:
                fail("with the legacy helpers removed, %%s breaks: %%s" %% (svc, p.stderr[-400:]))
    elif what == "behaviour":
        behaviour(sys.argv[3], sys.argv[2])
    else:
        static(os.getcwd(), what)
        behaviour(os.getcwd(), what)
'''


@family("swarm-migration-split", category="swarm", lang="python", kind="refactor", n=14,
        summary="a mechanical API migration spread over k service directories (one worker each); behaviour must stay the same")
def migration_split(rng, n):
    order = ["money", "dates", "logging", "net", "money", "logging", "dates", "net", "money", "dates", "logging", "net", "money", "logging"]
    ks = [3, 3, 4, 4, 5, 5, 3, 6, 6, 4, 7, 5, 8, 4]
    styles = ["from", "alias", "module"]
    for i in range(n):
        mig = MIGS[order[i % len(order)]]
        k = ks[i % len(ks)]
        svcs = list(SERVICES)
        rng.shuffle(svcs)
        svcs = svcs[:k]
        old_tree, new_tree, cases, counter = {}, {}, [], [0]
        base_style = styles[i % 3]
        per_dir = {}
        for svc in svcs:
            style = base_style if rng.random() < 0.6 else rng.choice(styles)
            o, nw, cs = build_dir(rng, mig, svc, rng.randint(2, 4), style, counter)
            old_tree.update(o)
            new_tree.update(nw)
            cases.extend(cs)
            per_dir[svc] = len(cs)
        start = merged(mig.shim, mig.newlib, old_tree)
        start["MIGRATION.md"] = dd(f'''
            # Retiring the legacy helpers

            The `legacy/` package wraps the new packages for old callers and is deleted after this release. Every service
            directory must stop using it. Behaviour must not change: same results, same side effects.

            {{DOC}}

            Things to keep in mind:

            * only calls to the deprecated function are affected; look-alikes (a method with the same name on some class, a
              different helper) are not the deprecated API and keep their names;
            * imports of the old module go away, along with any alias that was only there for it;
            * `python3 tools/find_legacy.py` lists what is left.
        ''').replace("{DOC}", mig.doc.strip("\n"))
        start["tools/find_legacy.py"] = dd(f'''
            """List the places that still use the deprecated helper: python3 tools/find_legacy.py"""
            import ast
            import os
            import sys

            NAMES = {sorted({mig.old_name, mig.alias, mig.modalias})!r}


            def main():
                hits = 0
                for dirpath, _, files in os.walk("."):
                    if dirpath.startswith(("./legacy", "./tools", "./tests", "./.")):
                        continue
                    for f in sorted(files):
                        if f.endswith(".py"):
                            path = os.path.join(dirpath, f)
                            for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
                                legacy_import = (isinstance(node, ast.ImportFrom) and (node.module or "").startswith("legacy")) or (
                                    isinstance(node, ast.Import) and any(a.name.startswith("legacy") for a in node.names))
                                if legacy_import or (isinstance(node, ast.Name) and node.id in NAMES):
                                    print("%s:%d" % (path, node.lineno))
                                    hits += 1
                print(hits, "reference(s) to the legacy helpers")
                return 1 if hits else 0


            if __name__ == "__main__":
                sys.exit(main())
        ''')
        start["README.md"] = dd(f'''
            # Service monorepo

            Small services, each a package in its own directory ({", ".join(svcs)}). `legacy/` holds deprecated wrappers; see `MIGRATION.md`.
            `python3 -m unittest discover -s tests` runs the smoke tests.
        ''')
        first = cases[0]
        # expected behaviour from the ORIGINAL code
        res = run(merged(start, {"_cases.json": json.dumps(cases), "_record.py": RECORD_SCRIPT % {"capture": repr(mig.capture)}}), "python3 _record.py", timeout=60)
        if not res.ok:
            raise RuntimeError("recording failed:\n" + res.out[-1500:])
        expected = json.loads(zlib.decompress(base64.b64decode(res.out.strip().splitlines()[-1])))
        start["tests/test_smoke.py"] = dd(f'''
            import importlib
            import os
            import sys
            import unittest

            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


            class Smoke(unittest.TestCase):
                def test_first_case(self):
                    mod = importlib.import_module({first["module"]!r})
                    self.assertEqual(getattr(mod, {first["fn"]!r})(*{first["args"]!r}), {expected[0]["result"]!r})


            if __name__ == "__main__":
                unittest.main()
        ''')
        data = {"old_names": [mig.old_name], "aliases": [mig.alias, mig.modalias] if mig.alias else [], "old_modules": [mig.old_mod],
                "cases": cases, "expected": expected, "capture": mig.capture, "services": svcs, "tomb": mig.tomb}
        hidden = {".grade/mig_check.py": CHECK % {"data": json.dumps(data, sort_keys=True)}}
        units = [{"name": f"directory {s}", "cmd": ["python3", ".grade/mig_check.py", s], "weight": 1} for s in svcs]
        units.append({"name": "legacy helpers removed", "cmd": ["python3", ".grade/mig_check.py", "tombstone"], "weight": max(1, k // 3)})
        hidden[".grade/score.py"] = score_script(units)
        solution = dict(new_tree)
        for p in list(solution):
            if p.endswith("__init__.py") and p in start and start[p] == solution[p]:
                del solution[p]
        d = 3 if k <= 3 else 4 if k <= 5 else 5
        if mig.name in ("net", "logging") and d < 5:
            d += 1 if k >= 4 else 0
        voices = [
            f"We're deleting the legacy/ package after this release and {len(svcs)} service directories still depend on it ({oxford(svcs)}). "
            f"MIGRATION.md explains the {mig.name} change. Please move every caller over; behaviour must stay exactly the same.",
            f"Mechanical but wide: migrate all uses of the deprecated {mig.name} helper in {oxford(svcs)} to the new API from MIGRATION.md. "
            f"`python3 tools/find_legacy.py` shows what is left. Careful with look-alike names.",
            f"The legacy shim has to go. Every directory under the repo root that still imports from legacy/ needs updating according to MIGRATION.md "
            f"({len(svcs)} of them). Split it however you like; the results must be identical to before.",
            f"Retire legacy.{mig.old_mod.split('.')[-1]}: update each caller in {oxford(svcs)} per MIGRATION.md and make sure nothing breaks when the shim is finally removed.",
        ]
        yield Task(
            slug=f"{i + 1:02d}-{mig.name}-k{k}",
            prompt=voices[i % len(voices)], difficulty=min(5, d),
            start=start, hidden=hidden, solution=solution,
            verify=GRADE_CMD, pass_mode="json-score",
            team=team(rng, min(k, 6)),
            tags=["migration", "mechanical", mig.name],
            notes={"migration": mig.name, "directories": svcs, "cases": len(cases)},
        )
