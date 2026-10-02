"""Slot modules (python), part 3: care-home rosters, webhook relay."""
from fx import dd

from ._slots import Bad, Module, Slot, validate_module

# ---------------------------------------------------------------------------------------------------------------------
# care home shift roster
# ---------------------------------------------------------------------------------------------------------------------

ROSTER_TEMPLATE = dd('''
    """Shift roster rules for a care home: overnight shifts, rest periods, overtime and the night premium."""
    import json
    import re
    from datetime import date

    SHIFT_RE = re.compile(r"(\\d{4})-(\\d{2})-(\\d{2}) (\\d{2}):(\\d{2})-(\\d{2}):(\\d{2})")

    @@consts@@


    @@parse@@


    @@night@@


    @@overtime@@


    @@rest@@


    @@overlap@@


    @@pay@@


    @@save@@


    @@load@@
''')

_R_CONSTS = dd('''
    DAY = 24 * 60  # minutes
    NIGHT_START = 22 * 60  # the night premium applies from 22:00 ...
    NIGHT_END = 6 * 60  # ... until 06:00
''')
_R_PARSE = dd('''
    def parse_shift(text):
        """"YYYY-MM-DD HH:MM-HH:MM" -> (start, end) in minutes; an end at or before the start means the next day."""
        m = SHIFT_RE.fullmatch(text.strip())
        if not m:
            raise ValueError(f"bad shift: {text!r}")
        y, mo, d, h1, m1, h2, m2 = map(int, m.groups())
        if h1 > 23 or h2 > 23 or m1 > 59 or m2 > 59:
            raise ValueError(f"bad time in shift: {text!r}")
        base = date(y, mo, d).toordinal() * DAY
        start, end = base + h1 * 60 + m1, base + h2 * 60 + m2
        if end <= start:
            end += DAY
        return start, end
''')
_R_NIGHT = dd('''
    def night_minutes(shift):
        """Minutes of the shift that fall between NIGHT_START and NIGHT_END."""
        start, end = shift
        total = 0
        day = start // DAY
        while day * DAY < end:
            for lo, hi in ((day * DAY, day * DAY + NIGHT_END), (day * DAY + NIGHT_START, (day + 1) * DAY)):
                total += max(0, min(end, hi) - max(start, lo))
            day += 1
        return total
''')
_R_OVERTIME = dd('''
    def overtime_minutes(shifts, limit_hours=40):
        """Minutes worked beyond the weekly limit."""
        worked = sum(end - start for start, end in shifts)
        return max(0, worked - limit_hours * 60)
''')
_R_REST = dd('''
    def rest_violations(shifts, min_rest_hours=11):
        """Consecutive shifts (by start time) with less than the minimum rest between them, as (earlier, later) pairs."""
        ordered = sorted(shifts)
        found = []
        for a, b in zip(ordered, ordered[1:]):
            if b[0] - a[1] < min_rest_hours * 60:
                found.append((a, b))
        return found
''')
_R_OVERLAP = dd('''
    def overlapping(shifts):
        """Every pair of shifts that overlap in time (touching end to start is not an overlap)."""
        ordered = sorted(shifts)
        return [(a, b) for i, a in enumerate(ordered) for b in ordered[i + 1:] if b[0] < a[1]]
''')
_R_PAY = dd('''
    def pay_cents(shifts, rate_cents, night_premium_pct=25):
        """Pay in cents for hourly `rate_cents`: base pay by the minute plus the premium on night minutes, rounded half up once."""
        minutes = sum(end - start for start, end in shifts)
        night = sum(night_minutes(s) for s in shifts)
        numer = rate_cents * (minutes * 100 + night * night_premium_pct)
        denom = 60 * 100
        return (2 * numer + denom) // (2 * denom)
''')
_R_SAVE = dd('''
    def save_roster(path, shifts):
        """Store the shifts as JSON, sorted."""
        with open(path, "w") as fh:
            json.dump(sorted(shifts), fh)
''')
_R_LOAD = dd('''
    def load_roster(path):
        """Read shifts written by save_roster."""
        with open(path) as fh:
            return [tuple(s) for s in json.load(fh)]
''')

ROSTER = Module(
    name="py-shiftroster", lang="python", path="rosterkit/shifts.py", difficulty=3,
    title="Roster rules: overnight shifts, rest periods, overtime, night premium",
    blurb="The `rosterkit` package checks the weekly staff rosters of a care home against the labour-agreement rules.",
    intro=dd('''
        Payroll currently re-checks every roster by hand. This PR moves the agreement rules into code:
    '''),
    outro=dd('''
        Rosters are saved in the shared `rosters/` folder by the duty managers' desktop tool. Compared against last month's
        payroll run for two wards; the numbers matched.
    '''),
    new_file=True,
    template=ROSTER_TEMPLATE,
    ctx={"README.md": "# rosterkit\n\nRule checks for the care-home rosters.\n", "rosterkit/__init__.py": '"""Roster rules."""\n'},
    scenario=dd('''
        import os
        from datetime import date

        from rosterkit.shifts import (load_roster, night_minutes, overlapping, overtime_minutes, parse_shift, pay_cents, rest_violations,
                                      save_roster)


        def show(shift):
            start, end = shift
            d = date.fromordinal(start // 1440)
            return f"{d:%a %d} {start % 1440 // 60:02d}:{start % 60:02d}-{end % 1440 // 60:02d}:{end % 60:02d}"


        TEXT = ["2025-03-10 22:00-06:00", "2025-03-11 17:00-23:00", "2025-03-12 06:00-18:00", "2025-03-12 12:00-20:00",
                "2025-03-13 08:00-08:00", "2025-03-13 09:00-10:00", "2025-03-13 12:00-16:00", "2025-03-14 06:00-10:00",
                "2025-03-14 10:00-14:00"]
        shifts = [parse_shift(t) for t in TEXT]
        for t in ("2025-03-10 24:00-06:00", "2025-03-10 22:60-06:00", "2025-02-30 08:00-16:00", "2025-03-10 8:00-16:00"):
            try:
                print("parsed", show(parse_shift(t)))
            except ValueError as exc:
                print("refused:", exc)
        print("night minutes:", [night_minutes(s) for s in shifts])
        print("overtime:", overtime_minutes(shifts), overtime_minutes(shifts, 100), overtime_minutes(shifts[:1]))
        print("rest violations:", [(show(a), show(b)) for a, b in rest_violations(shifts)])
        print("rest violations, reversed input:", len(rest_violations(list(reversed(shifts)))))
        print("overlapping:", [(show(a), show(b)) for a, b in overlapping(shifts)])
        print("pay:", pay_cents(shifts[:2], 1475), pay_cents(shifts, 1475), pay_cents(shifts[1:2], 1333, 30))
        os.makedirs("out", exist_ok=True)
        save_roster("out/roster.json", list(reversed(shifts)))
        print("reloaded equal:", load_roster("out/roster.json") == sorted(shifts))
    '''),
    slots=[
        Slot("consts", "<module>", _R_CONSTS, [
            Bad(_R_CONSTS.replace("NIGHT_START = 22 * 60", "NIGHT_START = 20 * 60"), "logic", "the night premium starts at 20:00 instead of the agreed 22:00", ("22", "NIGHT_START", "20", "constant"), kind="config-error"),
            Bad(_R_CONSTS.replace("NIGHT_END = 6 * 60", "NIGHT_END = 6"), "logic", "NIGHT_END is 6 minutes instead of 6 hours (missing * 60)", ("NIGHT_END", "minutes", "hours", "60"), kind="config-error"),
        ], note="adds the agreement constants (day length, night window)"),
        Slot("parse", "parse_shift", _R_PARSE, [
            Bad(_R_PARSE.replace("if end <= start:", "if end < start:"), "off-by-one", "a shift whose end equals its start is treated as zero length instead of a full 24 hours", ("<=", "equal", "24", "next day")),
            Bad(_R_PARSE.replace("h1 > 23 or h2 > 23", "h1 > 24 or h2 > 24"), "off-by-one", "hour 24 is accepted although hours go up to 23", ("24", "23", "hour", "range")),
        ], note="adds `parse_shift()` including overnight shifts"),
        Slot("night", "night_minutes", _R_NIGHT, [
            Bad(_R_NIGHT.replace("total += max(0, min(end, hi) - max(start, lo))", "total += min(end, hi) - max(start, lo)"), "logic", "without the max(0, ...) the periods that do not overlap the shift contribute negative minutes", ("max", "negative", "overlap", "0")),
            Bad(_R_NIGHT.replace("while day * DAY < end:", "while day * DAY < end - DAY:"), "off-by-one", "the day loop stops one day early, so the night part that falls on the shift's last day is never counted", ("loop", "day", "end", "while")),
        ], note="adds `night_minutes()` for the night premium"),
        Slot("overtime", "overtime_minutes", _R_OVERTIME, [
            Bad(_R_OVERTIME.replace("limit_hours * 60", "limit_hours"), "logic", "the limit is in hours but is subtracted from minutes (missing * 60)", ("hours", "minutes", "60", "unit")),
        ], note="adds `overtime_minutes()` against the weekly limit"),
        Slot("rest", "rest_violations", _R_REST, [
            Bad(_R_REST.replace("b[0] - a[1] < min_rest_hours * 60", "b[0] - a[1] <= min_rest_hours * 60"), "off-by-one", "a rest of exactly 11 hours is reported as a violation; the rule is *less than* 11 hours", ("<=", "exactly", "11", "boundary")),
            Bad(_R_REST.replace("ordered = sorted(shifts)", "ordered = list(shifts)"), "logic", "shifts are compared in the order given instead of by start time, so rest violations between unsorted shifts are missed or invented", ("sorted", "order", "start")),
            Bad(_R_REST.replace("b[0] - a[1] <", "b[0] - a[0] <"), "logic", "the rest is measured from the start of the earlier shift instead of its end", ("a[0]", "a[1]", "end", "start")),
        ], note="adds `rest_violations()`: at least 11 hours between consecutive shifts"),
        Slot("overlap", "overlapping", _R_OVERLAP, [
            Bad(_R_OVERLAP.replace("if b[0] < a[1]]", "if b[0] <= a[1]]"), "off-by-one", "shifts that merely touch (one ends when the next starts) are reported as overlapping", ("<=", "touch", "adjacent", "boundary")),
            Bad(_R_OVERLAP.replace("[(a, b) for i, a in enumerate(ordered) for b in ordered[i + 1:] if b[0] < a[1]]", "[(a, b) for a, b in zip(ordered, ordered[1:]) if b[0] < a[1]]"), "logic", "only neighbouring shifts are compared, so a long shift that overlaps a shift further down the list is missed", ("zip", "neighbour", "adjacent", "pairs")),
        ], note="adds `overlapping()`"),
        Slot("pay", "pay_cents", _R_PAY, [
            Bad(_R_PAY.replace("return (2 * numer + denom) // (2 * denom)", "return numer // denom"), "logic", "the result is truncated instead of rounded half up", ("round", "truncat", "//", "half")),
            Bad(_R_PAY.replace("night * night_premium_pct", "minutes * night_premium_pct"), "logic", "the premium is applied to all minutes worked instead of only the night minutes", ("night", "minutes", "premium")),
            Bad(_R_PAY.replace("denom = 60 * 100", "denom = 60"), "logic", "the percentage divisor (100) is missing from the denominator, so pay is 100 times too high", ("denom", "100", "percent", "divisor")),
        ], note="adds `pay_cents()` with the night premium, rounded once"),
        Slot("save", "save_roster", _R_SAVE, [
            Bad(dd('''
                def save_roster(path, shifts):
                    """Store the shifts as JSON, sorted."""
                    fh = open(path, "w")
                    json.dump(sorted(shifts), fh)
            '''), "resource-leak", "the file is never closed (no `with`), so data may stay in the buffer and the descriptor leaks", ("close", "with", "flush", "file")),
        ], note="adds `save_roster()`"),
        Slot("load", "load_roster", _R_LOAD, [
            Bad(dd('''
                def load_roster(path):
                    """Read shifts written by save_roster."""
                    with open(path) as fh:
                        return [tuple(s) for s in eval(fh.read())]
            '''), "security", "eval() on a file from the shared rosters folder executes arbitrary code; json.load is enough", ("eval", "json", "arbitrary", "code execution")),
        ], note="adds `load_roster()` for the shared rosters folder"),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# webhook relay
# ---------------------------------------------------------------------------------------------------------------------

RELAY_TEMPLATE = dd('''
    """Webhook relay: signs outgoing events, verifies incoming ones, and retries failed deliveries with backoff."""
    import hashlib
    import hmac
    import ipaddress
    from urllib.parse import urlparse

    TOLERANCE = 300  # seconds a signed timestamp may differ from our clock
    MAX_ATTEMPTS = 5
    BASE_DELAY = 10  # seconds
    MAX_DELAY = 60


    class RelayError(Exception):
        """Delivery or verification problem."""


    @@sign@@


    @@verify@@


    @@target@@


    @@backoff@@


    class Outbox:
        def __init__(self):
            self.queue = []  # [{"url", "body", "attempts", "due"}], oldest first
            self.dead = []
            self.seen = set()

        @@enqueue@@

        @@drain@@
''')

_W_SIGN = dd('''
    def sign(secret, timestamp, body):
        """Header value "t=<timestamp>,v1=<hex hmac-sha256 of '<timestamp>.<body>'>"."""
        mac = hmac.new(secret, f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()
        return f"t={timestamp},v1={mac}"
''')
_W_VERIFY = dd('''
    def verify(secret, header, body, now):
        """True if the header carries a valid signature and a timestamp within TOLERANCE seconds of `now`."""
        parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
        if "t" not in parts or "v1" not in parts:
            return False
        try:
            stamp = int(parts["t"])
        except ValueError:
            return False
        if abs(now - stamp) > TOLERANCE:
            return False
        expected = hmac.new(secret, f"{stamp}.{body}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, parts["v1"])
''')
_W_TARGET = dd('''
    def check_target(url):
        """Only public https endpoints may be called: no other scheme, no literal private or loopback address, no localhost."""
        u = urlparse(url)
        if u.scheme != "https" or not u.hostname:
            raise RelayError(f"refusing {url!r}")
        host = u.hostname.lower()
        if host == "localhost" or host.endswith(".localhost"):
            raise RelayError(f"refusing {url!r}")
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return url
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise RelayError(f"refusing {url!r}")
        return url
''')
_W_BACKOFF = dd('''
    def retry_delay(attempts):
        """Seconds to wait after the given number of failed attempts (1-based); None once MAX_ATTEMPTS is used up."""
        if attempts >= MAX_ATTEMPTS:
            return None
        return min(MAX_DELAY, BASE_DELAY * 2 ** (attempts - 1))
''')
_W_ENQUEUE = dd('''
    def enqueue(self, url, body, key, now):
        """Queue a delivery; the same idempotency key is accepted only once. Returns True if queued."""
        check_target(url)
        if key in self.seen:
            return False
        self.seen.add(key)
        self.queue.append({"url": url, "body": body, "attempts": 0, "due": now})
        return True
''')
_W_DRAIN = dd('''
    def drain(self, now, send):
        """Try every delivery that is due; send(url, body) returns an HTTP status. 2xx removes the item, anything else
        counts as a failed attempt and is rescheduled, or moved to `dead` when the attempts are used up."""
        pending = []
        for item in self.queue:
            if item["due"] > now:
                pending.append(item)
                continue
            status = send(item["url"], item["body"])
            if 200 <= status < 300:
                continue
            item["attempts"] += 1
            delay = retry_delay(item["attempts"])
            if delay is None:
                self.dead.append(item)
            else:
                item["due"] = now + delay
                pending.append(item)
        self.queue = pending
''')

RELAY = Module(
    name="py-hookrelay", lang="python", path="relay/hooks.py", difficulty=3,
    title="Webhook relay: signatures, SSRF guard, retries with backoff",
    blurb="The `relay` package delivers event notifications from a ticketing system to customers' webhook endpoints.",
    intro=dd('''
        Customers asked for signed webhooks with automatic retries. This PR adds the delivery core:
    '''),
    outro=dd('''
        Endpoint URLs are entered by customers in the admin UI. Verified the signature format against the sample in the
        public API docs.
    '''),
    new_file=True,
    template=RELAY_TEMPLATE,
    ctx={"README.md": "# relay\n\nOutgoing webhook delivery.\n", "relay/__init__.py": '"""Webhook relay."""\n'},
    scenario=dd('''
        from relay.hooks import Outbox, RelayError, check_target, retry_delay, sign, verify

        SECRET = b"whsec_demo"
        NOW = 1_700_000_000
        header = sign(SECRET, NOW, '{"event":"ticket.closed"}')
        print("header:", header[:24], "...")
        print("verify ok:", verify(SECRET, header, '{"event":"ticket.closed"}', NOW + 10))
        print("verify tampered body:", verify(SECRET, header, '{"event":"ticket.opened"}', NOW + 10))
        print("verify wrong secret:", verify(b"other", header, '{"event":"ticket.closed"}', NOW))
        print("verify at +300s:", verify(SECRET, header, '{"event":"ticket.closed"}', NOW + 300))
        print("verify at +301s:", verify(SECRET, header, '{"event":"ticket.closed"}', NOW + 301))
        print("verify at -301s:", verify(SECRET, header, '{"event":"ticket.closed"}', NOW - 301))
        print("verify junk:", verify(SECRET, "v1=abc", "x", NOW), verify(SECRET, "t=abc,v1=abc", "x", NOW))
        forged = header.split(",")[0] + ",v1=" + "0" * 64
        print("verify forged:", verify(SECRET, forged, '{"event":"ticket.closed"}', NOW))
        for url in ("https://hooks.example.org/a", "http://hooks.example.org/a", "https://127.0.0.1/x", "https://10.1.2.3/x",
                    "https://localhost/x", "https://169.254.169.254/latest", "https://app.localhost/x", "ftp://example.org/x", "https:///nohost",
                    "https://[::1]/x", "https://8.8.8.8/dns", "https://192.168.0.5/admin"):
            try:
                check_target(url)
                print("target ok:", url)
            except RelayError as exc:
                print("target refused:", url)
        print("delays:", [retry_delay(n) for n in range(1, 7)])
        box = Outbox()
        print("queued:", box.enqueue("https://hooks.example.org/a", "A", "k1", NOW), box.enqueue("https://hooks.example.org/a", "A", "k1", NOW),
              box.enqueue("https://hooks.example.org/b", "B", "k2", NOW), box.enqueue("https://hooks.example.org/c", "C", "k3", NOW + 5))
        try:
            print("internal queued:", box.enqueue("https://10.0.0.7/hook", "X", "k4", NOW))
        except RelayError as exc:
            print("internal refused")
        calls = []


        def send(url, body):
            calls.append((url[-1], body))
            return 500 if url.endswith("b") else 204 if url.endswith("a") else 300


        for t in (NOW, NOW + 5, NOW + 9, NOW + 10, NOW + 20, NOW + 40, NOW + 80, NOW + 160, NOW + 400):
            box.drain(t, send)
            print(f"t+{t - NOW}: queue={[(i['url'][-1], i['attempts']) for i in box.queue]} dead={[(i['url'][-1], i['attempts']) for i in box.dead]}")
        print("calls:", len(calls))
    '''),
    slots=[
        Slot("sign", "sign", _W_SIGN, [
            Bad(_W_SIGN.replace('f"{timestamp}.{body}".encode()', 'body.encode()'), "security", "the timestamp is not part of the signed message, so a captured request can be replayed with a fresh timestamp header", ("timestamp", "replay", "signed", "message")),
        ], note="adds `sign()` (HMAC-SHA256 over timestamp and body)"),
        Slot("verify", "verify", _W_VERIFY, [
            Bad(_W_VERIFY.replace("return hmac.compare_digest(expected, parts[\"v1\"])", "return expected == parts[\"v1\"]"), "security", "the signature is compared with `==`, which is not constant time; use hmac.compare_digest", ("compare_digest", "timing", "==", "constant")),
            Bad(_W_VERIFY.replace('''    if abs(now - stamp) > TOLERANCE:
        return False
''', ""), "security", "the timestamp is never checked against the clock, so any old signed request can be replayed forever", ("replay", "tolerance", "timestamp", "TOLERANCE")),
            Bad(_W_VERIFY.replace("if abs(now - stamp) > TOLERANCE:", "if now - stamp > TOLERANCE:"), "security", "only timestamps in the past are checked, so a timestamp far in the future is accepted", ("abs", "future", "tolerance", "timestamp")),
            Bad(_W_VERIFY.replace("if abs(now - stamp) > TOLERANCE:", "if abs(now - stamp) >= TOLERANCE:"), "off-by-one", "a timestamp exactly TOLERANCE seconds away is rejected although the window is inclusive", (">=", "inclusive", "boundary", "TOLERANCE")),
        ], note="adds `verify()` with a replay window"),
        Slot("target", "check_target", _W_TARGET, [
            Bad(dd('''
                def check_target(url):
                    """Only public https endpoints may be called: no other scheme, no literal private or loopback address, no localhost."""
                    if not url.startswith("https"):
                        raise RelayError(f"refusing {url!r}")
                    return url
            '''), "security", "the SSRF guard only checks the scheme; https URLs pointing at loopback, link-local (cloud metadata) or private addresses are allowed", ("ssrf", "private", "loopback", "169.254", "metadata")),
            Bad(_W_TARGET.replace("if ip.is_private or ip.is_loopback or ip.is_link_local:", "if ip.is_loopback or ip.is_link_local:"), "security", "private ranges (10.0.0.0/8, 192.168.0.0/16, ...) are no longer refused, only loopback and link-local addresses are", ("private", "10.", "192.168", "ssrf", "internal")),
            Bad(_W_TARGET.replace('if host == "localhost" or host.endswith(".localhost"):', 'if host == "localhost":'), "security", "names under .localhost resolve to loopback but are not refused (only the exact name `localhost` is)", ("localhost", "endswith", "subdomain", "loopback")),
        ], note="adds `check_target()`: customers' endpoint URLs must be public https"),
        Slot("backoff", "retry_delay", _W_BACKOFF, [
            Bad(_W_BACKOFF.replace("if attempts >= MAX_ATTEMPTS:", "if attempts > MAX_ATTEMPTS:"), "off-by-one", "one attempt too many: a sixth delivery is scheduled", (">", "MAX_ATTEMPTS", "attempts", "off by one")),
            Bad(_W_BACKOFF.replace("BASE_DELAY * 2 ** (attempts - 1)", "BASE_DELAY * 2 ** attempts"), "off-by-one", "the exponent is not shifted by one, so the first retry waits 20 s instead of BASE_DELAY", ("exponent", "attempts - 1", "BASE_DELAY", "2 **")),
            Bad(_W_BACKOFF.replace("min(MAX_DELAY, BASE_DELAY * 2 ** (attempts - 1))", "BASE_DELAY * 2 ** (attempts - 1)"), "logic", "the delay is no longer capped at MAX_DELAY", ("cap", "MAX_DELAY", "min")),
        ], note="adds `retry_delay()`: exponential backoff, capped, at most five attempts"),
        Slot("enqueue", "Outbox.enqueue", _W_ENQUEUE, [
            Bad(_W_ENQUEUE.replace("    check_target(url)\n", ""), "security", "the target is not validated when queueing, so internal addresses can be queued", ("check_target", "validate", "ssrf", "enqueue")),
            Bad(_W_ENQUEUE.replace("        return False\n    self.seen.add(key)\n", "        return False\n"), "logic", "the key is never added to `seen`, so duplicates are never detected", ("seen", "idempotency", "duplicate", "add")),
        ], note="adds `Outbox.enqueue()` with idempotency keys"),
        Slot("drain", "Outbox.drain", _W_DRAIN, [
            Bad(_W_DRAIN.replace('if item["due"] > now:', 'if item["due"] >= now:'), "off-by-one", "an item that is due exactly now is postponed (`>=`)", (">=", "due", "now", "boundary")),
            Bad(_W_DRAIN.replace("if 200 <= status < 300:", "if 200 <= status <= 300:"), "off-by-one", "status 300 is treated as success", ("<=", "300", "status", "2xx")),
            Bad(_W_DRAIN.replace('        delay = retry_delay(item["attempts"])\n', '        delay = retry_delay(item["attempts"] - 1)\n'), "off-by-one", "the backoff is computed from attempts - 1, so the first failure is rescheduled with the wrong delay (and `0` attempts would break the exponent)", ("attempts - 1", "retry_delay", "first failure")),
            Bad(dd('''
                def drain(self, now, send):
                    """Try every delivery that is due; send(url, body) returns an HTTP status. 2xx removes the item, anything else
                    counts as a failed attempt and is rescheduled, or moved to `dead` when the attempts are used up."""
                    for item in self.queue:
                        if item["due"] > now:
                            continue
                        status = send(item["url"], item["body"])
                        if 200 <= status < 300:
                            self.queue.remove(item)
                            continue
                        item["attempts"] += 1
                        delay = retry_delay(item["attempts"])
                        if delay is None:
                            self.queue.remove(item)
                            self.dead.append(item)
                        else:
                            item["due"] = now + delay
            '''), "logic", "items are removed from the list while it is being iterated, so the element after each removed one is skipped in this pass", ("remove", "iterat", "skipped", "mutat"), kind="state-mutation"),
        ], note="adds `Outbox.drain()`: deliver what is due, reschedule failures, dead-letter after five"),
    ],
)

MODULES = [ROSTER, RELAY]
for _m in MODULES:
    validate_module(_m)
