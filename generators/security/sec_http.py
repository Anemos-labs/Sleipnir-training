"""Security families: HTTP header / e-mail header injection and cross-site request forgery, all modelled by pure functions and in-process objects."""
import re  # noqa: F401  (kept for readability of the embedded sources)

from fx import dd, family

from . import _sec
from ._sec import patched, readme

P = _sec.PY_PRELUDE

# =================================================================================================================================
#  header injection
# =================================================================================================================================
HI = []

REDIR = dd(r'''
    """Raw HTTP responses written by the tiny embedded server."""

    REASONS = {301: "Moved Permanently", 302: "Found"}


    def redirect_response(location, status=302):
        """The head of a redirect, exactly `HTTP/1.1 302 Found\r\nLocation: <location>\r\nContent-Length: 0\r\n\r\n` (status 301 gives `Moved Permanently`)."""
        return "HTTP/1.1 %d %s\r\nLocation: %s\r\nContent-Length: 0\r\n\r\n" % (status, REASONS[status], location)
''')

HI.append(dict(
    slug="redirect-crlf", d=2, product="the embedded HTTP server", func="redirect_response", cwe="CWE-113",
    finding="`redirect_response` pastes the location into the raw response; a location such as `/x\\r\\nSet-Cookie: admin=1` (or one with a blank line and a script) adds headers or a body to the response (HTTP response splitting), and locations come from request parameters.",
    start={"responses.py": REDIR, "README.md": readme("raw responses", "`redirect_response(location, status=302)` returns the exact head shown in the docstring (`status` 301 or 302). Locations may contain any printable characters (spaces, `?`, `&`, `%0d%0a` as literal text, non-ASCII); a location with a CR or LF in it must be refused with `ValueError` - it can never be a legitimate URL.")},
    solution={"responses.py": patched(REDIR, (
        '    return "HTTP/1.1 %d',
        '    if any(c in location for c in "\\r\\n\\x00"):\n        raise ValueError("control characters in location")\n    return "HTTP/1.1 %d'))},
    hidden={"tests/test_responses_security.py": P + dd(r'''
        import responses as m


        def lenient_parse(raw):
            """(status line, headers, rest) where CR and LF each end a line, like lenient servers and proxies read it."""
            norm = raw.replace("\r\n", "\n").replace("\r", "\n")
            head, _, rest = norm.partition("\n\n")
            lines = head.split("\n")
            return lines[0], [tuple(x.split(":", 1)) for x in lines[1:]], rest


        class ResponseTest(unittest.TestCase):
            def test_redirects(self):
                for loc in ["/dashboard", "https://example.com/a?b=c&d=e%20f", "/path with space", "/search?q=%0d%0aSet-Cookie:x", "/caf\u00e9", ""]:
                    self.assertEqual(m.redirect_response(loc), "HTTP/1.1 302 Found\r\nLocation: %s\r\nContent-Length: 0\r\n\r\n" % loc)
                self.assertEqual(m.redirect_response("/x", 301), "HTTP/1.1 301 Moved Permanently\r\nLocation: /x\r\nContent-Length: 0\r\n\r\n")

            def test_injection(self):
                for loc in ["/x\r\nSet-Cookie: admin=1", "/x\nSet-Cookie: a=b", "/x\r\n\r\n<script>alert(1)</script>", "/x\rX-Evil: y", "/x\n\n<html>", "\r\nSet-Cookie: a=b", "/x\x00y"]:
                    raw = attempt(m.redirect_response, loc)
                    if raw is None:
                        continue
                    status, headers, rest = lenient_parse(raw)
                    self.assertEqual(status, "HTTP/1.1 302 Found", repr(loc))
                    self.assertEqual([h[0] for h in headers], ["Location", "Content-Length"], repr(loc))
                    self.assertEqual(rest, "", repr(loc))
                    self.assertNotIn("\x00", raw)
                self.assertIsNone(attempt(m.redirect_response, "/x\r\nSet-Cookie: admin=1"))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

COOKIE = dd(r'''
    """Cookie helpers of the session layer."""


    def set_cookie_header(name, value, max_age=None, secure=True):
        """The value of a `Set-Cookie` header: `NAME=VALUE; Path=/; HttpOnly`, then `; Secure` when `secure`, then `; Max-Age=N` when `max_age` is not None - in that order, for example
        `theme=dark; Path=/; HttpOnly; Secure; Max-Age=60`.

        Cookie names are tokens made of ASCII letters, digits, `_` and `-` (anything else: ValueError). Values may be any text: they are percent-encoded as UTF-8, everything except letters,
        digits and `_.-~` (so `a b;c` is sent as `a%20b%3Bc`)."""
        header = "%s=%s; Path=/; HttpOnly" % (name, value)
        if secure:
            header += "; Secure"
        if max_age is not None:
            header += "; Max-Age=%d" % max_age
        return header
''')

HI.append(dict(
    slug="cookie-attributes", d=2, product="the session layer", func="set_cookie_header", cwe="CWE-113",
    finding="`set_cookie_header` writes the cookie name and value into the header unchecked: a value like `x; Domain=evil.io` or `x; Path=/admin` adds attributes, and one with `\\r\\nSet-Cookie: admin=1` adds a second header, while names such as `a=b` or `na me` produce broken cookies.",
    start={"cookies.py": COOKIE, "README.md": readme("cookies", "`set_cookie_header(name, value, max_age=None, secure=True)` returns the header value described in the docstring. The value is always percent-encoded (UTF-8; only letters, digits and `_.-~` stay as they are), the name must match `[A-Za-z0-9_-]+` or `ValueError` is raised, and the attributes never change with the value.")},
    solution={"cookies.py": patched(COOKIE, (
        '"""Cookie helpers of the session layer."""\n', '"""Cookie helpers of the session layer."""\nimport re\nfrom urllib.parse import quote\n'), (
        '    header = "%s=%s; Path=/; HttpOnly" % (name, value)\n',
        '    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):\n        raise ValueError("bad cookie name")\n    header = "%s=%s; Path=/; HttpOnly" % (name, quote(value, safe=""))\n'))},
    hidden={"tests/test_cookies_security.py": P + dd(r'''
        from urllib.parse import quote, unquote

        import cookies as m


        class CookieTest(unittest.TestCase):
            def test_normal(self):
                self.assertEqual(m.set_cookie_header("session", "abc123"), "session=abc123; Path=/; HttpOnly; Secure")
                self.assertEqual(m.set_cookie_header("prefs", "a b;c=d,\u00e9"), "prefs=a%20b%3Bc%3Dd%2C%C3%A9; Path=/; HttpOnly; Secure")
                self.assertEqual(m.set_cookie_header("t_1-x", "v", max_age=60, secure=False), "t_1-x=v; Path=/; HttpOnly; Max-Age=60")
                self.assertEqual(m.set_cookie_header("k", "", max_age=0), "k=; Path=/; HttpOnly; Secure; Max-Age=0")
                self.assertEqual(m.set_cookie_header("k", "~._-"), "k=~._-; Path=/; HttpOnly; Secure")

            def test_values_cannot_add_attributes(self):
                for value in ["x; Domain=evil.io", "x; Path=/admin", "x\r\nSet-Cookie: admin=1", "x\nSet-Cookie: a=b", "x, y=z", 'x"; Secure', "x; SameSite=None", "\u00e9\u4e2d\U0001f600"]:
                    header = m.set_cookie_header("sid", value, max_age=5)
                    self.assertNotIn("\r", header)
                    self.assertNotIn("\n", header)
                    parts = header.split("; ")
                    self.assertEqual(parts[1:], ["Path=/", "HttpOnly", "Secure", "Max-Age=5"], repr(value))
                    self.assertEqual(unquote(parts[0].split("=", 1)[1]), value)
                    self.assertEqual(parts[0], "sid=" + quote(value, safe=""))

            def test_bad_names(self):
                for name in ["a=b", "a; Secure", "na me", "x\r\nSet-Cookie: z", "", "caf\u00e9", "a,b", "a\tb", "a;"]:
                    self.assertIsNone(attempt(m.set_cookie_header, name, "v"), repr(name))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

DISP = dd(r'''
    """Download headers."""


    def content_disposition(filename):
        """The `Content-Disposition` value for downloading a file called `filename`.

        A name made only of ASCII letters, digits, spaces and `._-()` gives `attachment; filename="NAME"`. Any other name gives
        `attachment; filename="FALLBACK"; filename*=UTF-8''ENCODED`, where FALLBACK is the name with every character that is not in that set replaced by `_` (one `_` per character, not per byte)
        and ENCODED is the whole name encoded as UTF-8 and percent-encoded (everything except letters, digits and `_.-~` is encoded). Names containing CR, LF or NUL raise ValueError."""
        return 'attachment; filename="%s"' % filename
''')

HI.append(dict(
    slug="download-filename", d=3, product="the file download endpoint", func="content_disposition", cwe="CWE-113",
    finding="`content_disposition` pastes the user-chosen file name between quotes: a name with a quote closes the parameter (`a\"; filename=\"evil.exe` rewrites the download name), one with a line break injects headers, and names with non-ASCII characters are sent in no standard-compliant form.",
    start={"disposition.py": DISP, "README.md": readme("downloads", "`content_disposition(filename)` follows the rules in its docstring exactly (they are RFC 6266 / 5987 in miniature): plain names stay `attachment; filename=\"NAME\"`, other names add an ASCII fallback and a `filename*=UTF-8''...` parameter, names with CR, LF or NUL are refused with `ValueError`.")},
    solution={"disposition.py": patched(DISP, (
        '"""Download headers."""\n', '"""Download headers."""\nimport re\nfrom urllib.parse import quote\n'), (
        '''    return 'attachment; filename="%s"' % filename\n''',
        '''    if any(c in filename for c in "\\r\\n\\x00"):
        raise ValueError("control characters in file name")
    if re.fullmatch(r"[A-Za-z0-9 ._()-]*", filename):
        return 'attachment; filename="%s"' % filename
    fallback = re.sub(r"[^A-Za-z0-9 ._()-]", "_", filename)
    return 'attachment; filename="%s"; filename*=UTF-8\\'\\'%s' % (fallback, quote(filename, safe=""))
'''))},
    hidden={"tests/test_disposition_security.py": P + dd(r'''
        import disposition as m


        def parse_params(value):
            """Split `attachment; a="x"; b=y` into the disposition type and a list of (name, value); quoted strings may hold `;` and escaped quotes."""
            out, cur, quoted, esc = [], "", False, False
            for ch in value:
                if esc:
                    cur += ch
                    esc = False
                elif ch == "\\" and quoted:
                    cur += ch
                    esc = True
                elif ch == '"':
                    quoted = not quoted
                    cur += ch
                elif ch == ";" and not quoted:
                    out.append(cur.strip())
                    cur = ""
                else:
                    cur += ch
            out.append(cur.strip())
            return out[0], [tuple(p.split("=", 1)) for p in out[1:]]


        class DispositionTest(unittest.TestCase):
            def test_plain(self):
                for name in ["report.pdf", "my report (1).pdf", "a-b_c.tar.gz", "", "UPPER lower 123"]:
                    self.assertEqual(m.content_disposition(name), 'attachment; filename="%s"' % name)

            def test_other_names(self):
                self.assertEqual(m.content_disposition("r\u00e9sum\u00e9.pdf"), "attachment; filename=\"r_sum_.pdf\"; filename*=UTF-8''r%C3%A9sum%C3%A9.pdf")
                self.assertEqual(m.content_disposition('a"b.txt'), "attachment; filename=\"a_b.txt\"; filename*=UTF-8''a%22b.txt")
                self.assertEqual(m.content_disposition("my report (1)\u00e9.pdf"), "attachment; filename=\"my report (1)_.pdf\"; filename*=UTF-8''my%20report%20%281%29%C3%A9.pdf")
                self.assertEqual(m.content_disposition("\u4e2d\u6587.txt"), "attachment; filename=\"__.txt\"; filename*=UTF-8''%E4%B8%AD%E6%96%87.txt")
                self.assertEqual(m.content_disposition("a/b\\c;d.txt"), "attachment; filename=\"a_b_c_d.txt\"; filename*=UTF-8''a%2Fb%5Cc%3Bd.txt")

            def test_injection(self):
                for name in ['x"; filename="evil.exe', 'report.pdf"; x=y', "a\\b.txt", "na;me.txt"]:
                    value = m.content_disposition(name)
                    kind, params = parse_params(value)
                    self.assertEqual(kind, "attachment", name)
                    self.assertEqual([k for k, _ in params], ["filename", "filename*"], name)
                for name in ["a\r\nSet-Cookie: x=y", "a\nb", "a\rb", "a\x00b", "\r\n\r\n<html>"]:
                    self.assertIsNone(attempt(m.content_disposition, name), repr(name))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

RESET = dd(r'''
    """Password-reset e-mails."""

    ALLOWED_HOSTS = {"accounts.example.com", "www.example.com"}
    CANONICAL_HOST = "accounts.example.com"


    def reset_link(headers, token):
        """The link that goes into the reset e-mail: `https://HOST/reset?token=TOKEN`.

        HOST is the site name the user reached us under (header `Host`, or `X-Forwarded-Host` when the reverse proxy sets it - that one wins). It is written in lower case without a port, and only
        names in ALLOWED_HOSTS are used: for any other value the link uses CANONICAL_HOST. TOKEN is percent-encoded (everything except letters, digits and `_.-~`)."""
        host = headers.get("X-Forwarded-Host") or headers.get("Host") or CANONICAL_HOST
        return "https://%s/reset?token=%s" % (host, token)
''')

HI.append(dict(
    slug="reset-link-host", d=3, product="the password-reset e-mails", func="reset_link", cwe="CWE-640",
    finding="`reset_link` builds the link from the request's `Host` / `X-Forwarded-Host` header, which the sender controls: a forged `Host: evil.io` makes the victim receive a genuine reset e-mail whose link goes to the attacker's server, handing over the token (host header poisoning).",
    start={"mailer.py": RESET, "README.md": readme("reset e-mails", "`reset_link(headers, token)` returns `https://HOST/reset?token=TOKEN` as the docstring describes: HOST comes from `X-Forwarded-Host` (preferred) or `Host`, lower-cased, port removed, and must be in `ALLOWED_HOSTS`, else `CANONICAL_HOST` is used. The token is percent-encoded.")},
    solution={"mailer.py": patched(RESET, (
        '"""Password-reset e-mails."""\n', '"""Password-reset e-mails."""\nfrom urllib.parse import quote\n'), (
        '''    host = headers.get("X-Forwarded-Host") or headers.get("Host") or CANONICAL_HOST
    return "https://%s/reset?token=%s" % (host, token)
''', '''    host = (headers.get("X-Forwarded-Host") or headers.get("Host") or "").strip().lower()
    host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    if host not in ALLOWED_HOSTS:
        host = CANONICAL_HOST
    return "https://%s/reset?token=%s" % (host, quote(token, safe=""))
'''))},
    hidden={"tests/test_mailer_security.py": P + dd(r'''
        from urllib.parse import quote, urlsplit

        import mailer as m

        ALLOWED = {"accounts.example.com", "www.example.com"}


        class ResetTest(unittest.TestCase):
            def test_normal(self):
                self.assertEqual(m.reset_link({"Host": "www.example.com"}, "abc"), "https://www.example.com/reset?token=abc")
                self.assertEqual(m.reset_link({"Host": "ACCOUNTS.example.com:443"}, "abc"), "https://accounts.example.com/reset?token=abc")
                self.assertEqual(m.reset_link({"Host": "www.example.com", "X-Forwarded-Host": "accounts.example.com"}, "t"), "https://accounts.example.com/reset?token=t")
                self.assertEqual(m.reset_link({}, "t"), "https://accounts.example.com/reset?token=t")
                self.assertEqual(m.reset_link({"Host": "www.example.com"}, "a b&c=d/\u00e9"), "https://www.example.com/reset?token=" + quote("a b&c=d/\u00e9", safe=""))

            def test_poisoned_headers(self):
                for headers in [{"Host": "evil.io"}, {"Host": "accounts.example.com.evil.io"}, {"Host": "accounts.example.com", "X-Forwarded-Host": "evil.io"}, {"Host": "accounts.example.com@evil.io"},
                                {"Host": "evil.io/accounts.example.com"}, {"Host": "accounts.example.com:80@evil.io"}, {"Host": "evil.io#accounts.example.com"}, {"Host": "evil.io\r\nX: y"},
                                {"X-Forwarded-Host": "www.example.com.evil.io"}, {"Host": "www.example.com:8080/evil"}, {"Host": "evil.io:443"}, {"Host": "accounts.example.com\\@evil.io"}]:
                    link = m.reset_link(headers, "tok")
                    p = urlsplit(link)
                    self.assertEqual(p.scheme, "https", headers)
                    self.assertIn(p.hostname, ALLOWED, (headers, link))
                    self.assertEqual(link, "https://%s/reset?token=tok" % p.hostname, headers)
                    self.assertIsNone(p.username)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

MAIL = dd(r'''
    """Outgoing notification e-mail."""


    def build_message(sender, recipients, subject, body):
        """The text of a plain e-mail: the headers `From`, `To` (the recipients joined with `, `) and `Subject`, in this order, one per line, then an empty line and the body; every line break written
        by this function is `\r\n`, the body is added as it is. Header values may contain any printable text (`Ann <ann@example.com>`, non-ASCII subjects) but never line breaks:
        a value with CR or LF raises ValueError."""
        return "From: %s\r\nTo: %s\r\nSubject: %s\r\n\r\n%s" % (sender, ", ".join(recipients), subject, body)
''')

HI.append(dict(
    slug="mail-headers", d=3, product="the notification mailer", func="build_message", cwe="CWE-93",
    finding="`build_message` writes the subject, sender and recipients into the message as they are, so a subject such as `Hi\\r\\nBcc: attacker@evil.io` (typed into a contact form) adds recipients or header lines, and a blank line in it replaces the body with attacker text (e-mail header injection).",
    start={"outbox.py": MAIL, "README.md": readme("mailer", "`build_message(sender, recipients, subject, body)` returns the message described in the docstring; parsed with the standard e-mail parser it has exactly the headers `From`, `To`, `Subject` and the unchanged body. A header value containing CR or LF is refused with `ValueError` (the message is not built).")},
    solution={"outbox.py": patched(MAIL, (
        '    return "From: %s',
        '    for value in [sender, subject, *recipients]:\n        if "\\r" in value or "\\n" in value:\n            raise ValueError("line break in header value")\n    return "From: %s'))},
    hidden={"tests/test_outbox_security.py": P + dd(r'''
        from email.parser import Parser

        import outbox as m


        def parsed(text):
            return Parser().parsestr(text)


        class MailTest(unittest.TestCase):
            def test_normal(self):
                text = m.build_message("Ann <ann@example.com>", ["bob@example.com", "Carol C <carol@example.com>"], "Re: caf\u00e9, 100% ready", "Hello,\r\n\r\nsecond paragraph\r\n")
                msg = parsed(text)
                self.assertEqual(msg.keys(), ["From", "To", "Subject"])
                self.assertEqual(msg["From"], "Ann <ann@example.com>")
                self.assertEqual(msg["To"], "bob@example.com, Carol C <carol@example.com>")
                self.assertEqual(msg["Subject"], "Re: caf\u00e9, 100% ready")
                self.assertEqual(msg.get_payload(), "Hello,\r\n\r\nsecond paragraph\r\n")
                self.assertEqual(text, "From: Ann <ann@example.com>\r\nTo: bob@example.com, Carol C <carol@example.com>\r\nSubject: Re: caf\u00e9, 100% ready\r\n\r\nHello,\r\n\r\nsecond paragraph\r\n")

            def test_injection(self):
                body = "the real body"
                for sender, rcpts, subject in [
                        ("a@x.example", ["b@x.example"], "Hi\r\nBcc: attacker@evil.io"), ("a@x.example", ["b@x.example"], "Hi\nBcc: attacker@evil.io"),
                        ("a@x.example", ["b@x.example"], "Hi\r\n\r\nInjected body"), ("a@x.example", ["b@x.example\r\nBcc: attacker@evil.io"], "s"),
                        ("a@x.example\r\nBcc: attacker@evil.io", ["b@x.example"], "s"), ("a@x.example", ["b@x.example", "c@x.example\nCc: z@evil.io"], "s"),
                        ("a@x.example", ["b@x.example"], "x\rBcc: attacker@evil.io")]:
                    text = attempt(m.build_message, sender, rcpts, subject, body)
                    if text is None:
                        continue
                    msg = parsed(text)
                    self.assertEqual(msg.keys(), ["From", "To", "Subject"], repr(subject))
                    self.assertEqual(msg.get_payload(), body)
                    self.assertNotIn("Bcc", msg.keys())
                self.assertIsNone(attempt(m.build_message, "a@x.example", ["b@x.example"], "Hi\r\nBcc: attacker@evil.io", "x"))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

HI_ORDER = ["redirect-crlf", "cookie-attributes", "download-filename", "reset-link-host", "mail-headers"]
HI.sort(key=lambda s: (s["d"], HI_ORDER.index(s["slug"])))


@family("security-header-injection", category="security", lang="python", kind="fix", n=5,
        summary="CR/LF and attribute injection into HTTP and e-mail headers, cookies, download names, host-header poisoning")
def gen_header_injection(rng, n):
    return list(_sec.emit(rng, HI[:n], tags=["headers"]))


# =================================================================================================================================
#  CSRF
# =================================================================================================================================
CS = []


def _d4(text):
    return "\n".join(line[4:] if line.startswith("    ") else line for line in text.split("\n"))


def cpatched(text, *pairs):
    """`patched` for the CSRF scenarios, whose pairs are written with 4 extra spaces of indentation (class bodies)."""
    return patched(text, *[(_d4(o), _d4(n)) for o, n in pairs])


BANK = dd(r'''
    """A tiny online bank (in-process model of the request handler)."""


    class Bank:
        """`handle(method, path, session, params)` -> (status, body). `params` is the query string (GET) or the posted form (POST) as a dict of strings."""

        def __init__(self):
            self.balances = {"ann": 100, "bob": 50}
            self.sessions = {"sid-ann": "ann", "sid-bob": "bob"}
            self.closed = set()

        def handle(self, method, path, session, params):
            user = self.sessions.get(session)
            if user is None:
                return 401, "login required"
            if path == "/balance":
                return 200, str(self.balances[user])
            if path == "/transfer":
                to, amount = params.get("to"), int(params.get("amount", "0"))
                if to not in self.balances or amount <= 0 or amount > self.balances[user]:
                    return 400, "bad transfer"
                self.balances[user] -= amount
                self.balances[to] += amount
                return 200, "ok"
            if path == "/close-account":
                self.closed.add(user)
                return 200, "closed"
            return 404, "not found"
''')

CS.append(dict(
    slug="get-mutates", d=1, product="the online bank", func="Bank.handle", cwe="CWE-352",
    finding="`/transfer` and `/close-account` act on plain GET requests, so any web page can move money or close an account just by embedding `<img src=\"https://bank.example/transfer?to=mallory&amount=50\">` (cross-site request forgery; links also end up in logs, prefetchers and crawlers).",
    start={"bank.py": BANK, "README.md": readme("bank", "`/balance` is a read-only page (GET or HEAD). `/transfer` and `/close-account` change state: they only accept POST and answer every other method (GET, HEAD, PUT, DELETE...) with status 405 without doing anything. Login (status 401) and the transfer rules (400 for bad transfers) stay as they are.")},
    solution={"bank.py": cpatched(BANK, (
        '            if path == "/transfer":\n',
        '            if path in ("/transfer", "/close-account") and method != "POST":\n                return 405, "use POST"\n            if path == "/transfer":\n'))},
    hidden={"tests/test_bank_security.py": P + dd(r'''
        import bank as m


        class BankTest(unittest.TestCase):
            def test_posts(self):
                b = m.Bank()
                self.assertEqual(b.handle("GET", "/balance", "sid-ann", {}), (200, "100"))
                self.assertEqual(b.handle("HEAD", "/balance", "sid-bob", {})[0], 200)
                self.assertEqual(b.handle("POST", "/transfer", "sid-ann", {"to": "bob", "amount": "30"}), (200, "ok"))
                self.assertEqual(b.balances, {"ann": 70, "bob": 80})
                self.assertEqual(b.handle("POST", "/transfer", "sid-ann", {"to": "bob", "amount": "500"})[0], 400)
                self.assertEqual(b.handle("POST", "/transfer", "nope", {"to": "bob", "amount": "1"})[0], 401)
                self.assertEqual(b.handle("POST", "/close-account", "sid-bob", {}), (200, "closed"))
                self.assertEqual(b.closed, {"bob"})
                self.assertEqual(b.handle("GET", "/missing", "sid-ann", {})[0], 404)

            def test_other_methods_do_nothing(self):
                for method in ["GET", "HEAD", "PUT", "DELETE", "PATCH", "OPTIONS", "get"]:
                    b = m.Bank()
                    status, _ = b.handle(method, "/transfer", "sid-ann", {"to": "bob", "amount": "30"})
                    self.assertEqual(status, 405, method)
                    status, _ = b.handle(method, "/close-account", "sid-ann", {})
                    self.assertEqual(status, 405, method)
                    self.assertEqual(b.balances, {"ann": 100, "bob": 50})
                    self.assertEqual(b.closed, set())


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

FORM = dd(r'''
    """Account settings page (in-process model)."""
    import html


    class SettingsApp:
        def __init__(self):
            self.sessions = {"sid-ann": "ann", "sid-bob": "bob"}
            self.emails = {"ann": "ann@example.com", "bob": "bob@example.com"}

        def _user(self, session_id):
            if session_id not in self.sessions:
                raise PermissionError("login required")
            return self.sessions[session_id]

        def settings_form(self, session_id):
            """HTML of the settings form for the logged-in user."""
            user = self._user(session_id)
            return ('<form method="post" action="/settings"><input name="email" value="%s"><button>Save</button></form>'
                    % html.escape(self.emails[user], quote=True))

        def post_settings(self, session_id, form):
            """Handle the posted form: store `form["email"]` for the logged-in user and return 200."""
            user = self._user(session_id)
            self.emails[user] = form["email"]
            return 200
''')

CS.append(dict(
    slug="settings-token", d=2, product="the account settings page", func="post_settings", cwe="CWE-352",
    finding="The settings form can be submitted by any site the user visits: `post_settings` trusts the session cookie alone, so a hidden auto-submitting form on another page changes the victim's e-mail address (and from there the password-reset address): cross-site request forgery.",
    start={"settings.py": FORM, "README.md": readme("settings", "`settings_form(session_id)` renders the form; `post_settings(session_id, form)` stores the e-mail. Add CSRF protection with a synchronizer token: every session has its own unguessable token, the rendered form carries it in a hidden input named `csrf_token` (the rest of the markup stays), and `post_settings` raises `PermissionError` - changing nothing - when the posted `csrf_token` is missing, empty, wrong, or belongs to another session. The token stays the same for a session, so forms opened in several tabs keep working. Unknown sessions still raise `PermissionError`.")},
    solution={"settings.py": cpatched(FORM, (
        'import html\n', 'import hmac\nimport html\nimport secrets\n'), (
        '            self.emails = {"ann": "ann@example.com", "bob": "bob@example.com"}\n',
        '            self.emails = {"ann": "ann@example.com", "bob": "bob@example.com"}\n            self.tokens = {}\n'), (
        '        def settings_form(self, session_id):',
        '        def _token(self, session_id):\n            self._user(session_id)\n            if session_id not in self.tokens:\n                self.tokens[session_id] = secrets.token_urlsafe(32)\n            return self.tokens[session_id]\n\n        def settings_form(self, session_id):'), (
        '''<form method="post" action="/settings"><input name="email" value="%s"><button>Save</button></form>\'
                    % html.escape(self.emails[user], quote=True))''',
        '''<form method="post" action="/settings"><input type="hidden" name="csrf_token" value="%s"><input name="email" value="%s"><button>Save</button></form>\'
                    % (html.escape(self._token(session_id), quote=True), html.escape(self.emails[user], quote=True)))'''), (
        '            user = self._user(session_id)\n            self.emails[user] = form["email"]\n',
        '            user = self._user(session_id)\n            sent = str(form.get("csrf_token") or "")\n            if not sent or not hmac.compare_digest(sent.encode(), self._token(session_id).encode()):\n                raise PermissionError("bad csrf token")\n            self.emails[user] = form["email"]\n'))},
    hidden={"tests/test_settings_security.py": P + dd(r'''
        import re

        import settings as m


        def token_of(page):
            found = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page) or re.search(r'value="([^"]+)"[^>]*name="csrf_token"', page)
            return found.group(1) if found else None


        class SettingsTest(unittest.TestCase):
            def test_flow(self):
                app = m.SettingsApp()
                page = app.settings_form("sid-ann")
                tok = token_of(page)
                self.assertTrue(tok and len(tok) >= 16)
                self.assertIn('value="ann@example.com"', page)
                self.assertIn('action="/settings"', page)
                self.assertEqual(app.post_settings("sid-ann", {"email": "ann2@example.com", "csrf_token": tok}), 200)
                self.assertEqual(app.emails["ann"], "ann2@example.com")
                self.assertEqual(token_of(app.settings_form("sid-ann")), tok)
                self.assertEqual(app.post_settings("sid-ann", {"email": "ann3@example.com", "csrf_token": tok}), 200)
                self.assertEqual(app.emails["ann"], "ann3@example.com")
                other = token_of(app.settings_form("sid-bob"))
                self.assertNotEqual(other, tok)

            def test_forged(self):
                app = m.SettingsApp()
                tok_ann, tok_bob = token_of(app.settings_form("sid-ann")), token_of(app.settings_form("sid-bob"))
                for form in [{"email": "x@evil.io"}, {"email": "x@evil.io", "csrf_token": ""}, {"email": "x@evil.io", "csrf_token": "guess"}, {"email": "x@evil.io", "csrf_token": tok_bob},
                             {"email": "x@evil.io", "csrf_token": None}, {"email": "x@evil.io", "csrf_token": tok_ann + "x"}, {"email": "x@evil.io", "csrf_token": tok_ann[:-1]}]:
                    self.assertIsNone(attempt(app.post_settings, "sid-ann", form), form)
                    self.assertEqual(app.emails["ann"], "ann@example.com", form)
                self.assertIsNone(attempt(app.post_settings, "nope", {"email": "x@evil.io", "csrf_token": tok_ann}))
                self.assertIsNone(attempt(app.settings_form, "nope"))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

API = dd(r'''
    """JSON preferences API (in-process model)."""


    class PrefsApi:
        SITE_ORIGIN = "https://app.example.com"

        def __init__(self):
            self.sessions = {"sid-ann": "ann"}
            self.prefs = {"ann": {"theme": "light"}}

        def post_prefs(self, session_id, headers, prefs):
            """Update the logged-in user's preferences with the dict `prefs` and return the status code.

            This API has no form tokens; it relies on the browser's `Origin` / `Referer` headers instead (`headers` is a dict with those canonical names). A state-changing request is only accepted
            when it comes from the site itself: `Origin` must be exactly SITE_ORIGIN; when there is no `Origin`, `Referer` must be a URL whose scheme and host (and port) are exactly those of SITE_ORIGIN;
            when neither header is present, or the value is `null` or anything else, the answer is 403. Unknown sessions get 401."""
            user = self.sessions.get(session_id)
            if user is None:
                return 401
            origin = headers.get("Origin")
            if origin is not None and not origin.startswith(self.SITE_ORIGIN):
                return 403
            self.prefs[user].update(prefs)
            return 200
''')

CS.append(dict(
    slug="origin-check", d=3, product="the preferences API", func="PrefsApi.post_prefs", cwe="CWE-352",
    finding="`post_prefs` only rejects requests whose `Origin` is present *and* does not start with the site's origin: requests with no `Origin` header (and a foreign `Referer`) are accepted, and `https://app.example.com.evil.io` passes the prefix test, so other sites can change a logged-in user's preferences.",
    start={"prefs_api.py": API, "README.md": readme("preferences API", "`post_prefs(session_id, headers, prefs)` applies the rules in its docstring: exact `Origin` match, else exact origin of `Referer` when `Origin` is absent, else 403 and nothing changes. `https://app.example.com` and `https://app.example.com/settings?x=1` pass; look-alike hosts, other ports or schemes, `null`, and requests with neither header do not. An `Origin` that is present always decides, whatever the `Referer` says.")},
    solution={"prefs_api.py": cpatched(API, (
        '"""JSON preferences API (in-process model)."""\n', '"""JSON preferences API (in-process model)."""\nfrom urllib.parse import urlsplit\n'), (
        '''            if origin is not None and not origin.startswith(self.SITE_ORIGIN):
                return 403
''', '''            if origin is None:
                referer = headers.get("Referer")
                if not referer:
                    return 403
                p = urlsplit(referer)
                origin = "%s://%s" % (p.scheme, p.netloc)
            if origin != self.SITE_ORIGIN:
                return 403
'''))},
    hidden={"tests/test_prefs_security.py": P + dd(r'''
        import prefs_api as m

        SITE = "https://app.example.com"


        class PrefsTest(unittest.TestCase):
            def test_site_requests(self):
                for headers in [{"Origin": SITE}, {"Referer": SITE + "/settings/page?x=1"}, {"Referer": SITE}, {"Origin": SITE, "Referer": "https://evil.io/"}]:
                    api = m.PrefsApi()
                    self.assertEqual(api.post_prefs("sid-ann", headers, {"theme": "dark"}), 200, headers)
                    self.assertEqual(api.prefs["ann"], {"theme": "dark"})
                self.assertEqual(m.PrefsApi().post_prefs("nope", {"Origin": SITE}, {"theme": "dark"}), 401)

            def test_cross_site(self):
                for headers in [{"Origin": "https://app.example.com.evil.io"}, {"Origin": "null"}, {"Origin": "http://app.example.com"}, {"Origin": "https://evil.io"}, {},
                                {"Referer": "https://app.example.com.evil.io/x"}, {"Referer": "https://evil.io/https://app.example.com/"}, {"Referer": "https://app.example.com@evil.io/"},
                                {"Origin": "https://app.example.com:8443"}, {"Origin": "https://app.example.comevil.io"}, {"Origin": "https://evil.io", "Referer": SITE + "/x"},
                                {"Origin": ""}, {"Referer": ""}, {"Referer": "http://app.example.com/x"}, {"Referer": "app.example.com"}]:
                    api = m.PrefsApi()
                    self.assertEqual(api.post_prefs("sid-ann", headers, {"theme": "evil"}), 403, headers)
                    self.assertEqual(api.prefs["ann"], {"theme": "light"}, headers)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

PRED = dd(r'''
    """Profile page with CSRF protection (in-process model)."""
    import hashlib
    import hmac
    import secrets


    class Portal:
        def __init__(self):
            self.users = {"ann": 1, "bob": 2, "carol": 3}
            self.emails = {"ann": "ann@example.com", "bob": "bob@example.com", "carol": "carol@example.com"}
            self.sessions = {}

        def login(self, user):
            """Start a session for `user` and return the session id."""
            sid = secrets.token_hex(16)
            self.sessions[sid] = user
            return sid

        def csrf_token(self, sid):
            """The anti-CSRF token for this session (it is put into every form)."""
            user = self.sessions[sid]
            return hashlib.md5(("csrf-%d" % self.users[user]).encode()).hexdigest()

        def change_email(self, sid, token, email):
            """Change the e-mail address of the session's user; PermissionError when the token is not the session's token."""
            user = self.sessions[sid]
            if not hmac.compare_digest(str(token), self.csrf_token(sid)):
                raise PermissionError("bad csrf token")
            self.emails[user] = email
''')

CS.append(dict(
    slug="predictable-token", d=3, product="the profile page", func="Portal.csrf_token", cwe="CWE-352",
    finding="`csrf_token` is `md5` of a constant and the numeric user id, so anyone who knows (or guesses) a victim's user id can compute their anti-CSRF token and forge requests; the token is also identical in every session of a user.",
    start={"portal.py": PRED, "README.md": readme("profile portal", "`csrf_token(sid)` returns the token of a session: random (at least 128 bits from a secure source), different for every session (also for two sessions of the same user), stable during one session, and not derivable from anything an attacker knows (user names or ids, hashes of them, time). `change_email` raises `PermissionError`, changing nothing, unless the token is the session's own.")},
    solution={"portal.py": cpatched(PRED, (
        '            self.sessions = {}\n', '            self.sessions = {}\n            self.tokens = {}\n'), (
        '''            user = self.sessions[sid]
            return hashlib.md5(("csrf-%d" % self.users[user]).encode()).hexdigest()
''', '''            if sid not in self.sessions:
                raise KeyError(sid)
            if sid not in self.tokens:
                self.tokens[sid] = secrets.token_urlsafe(32)
            return self.tokens[sid]
'''), ('import hashlib\n', ''))},
    hidden={"tests/test_portal_security.py": P + dd(r'''
        import hashlib
        import time

        import portal as m


        def guesses(users):
            out = set()
            for name, uid in users.items():
                for text in [name, str(uid), "csrf-%d" % uid, "csrf%d" % uid, "csrf-" + name, name + "csrf", "%s:%d" % (name, uid), "csrf_%d" % uid, "token-%d" % uid, hex(uid), "%d" % (uid * 1000)]:
                    for algo in (hashlib.md5, hashlib.sha1, hashlib.sha256):
                        out.add(algo(text.encode()).hexdigest())
                    out.add(text)
            now = int(time.time())
            for k in range(-5, 400):
                for algo in (hashlib.md5, hashlib.sha1, hashlib.sha256):
                    out.add(algo(str(now - k).encode()).hexdigest())
            return out


        class PortalTest(unittest.TestCase):
            def test_flow(self):
                p = m.Portal()
                sid = p.login("ann")
                tok = p.csrf_token(sid)
                self.assertEqual(p.csrf_token(sid), tok)
                self.assertGreaterEqual(len(tok), 22)
                p.change_email(sid, tok, "ann2@example.com")
                self.assertEqual(p.emails["ann"], "ann2@example.com")
                sid2 = p.login("ann")
                self.assertNotEqual(p.csrf_token(sid2), tok)
                self.assertNotEqual(p.csrf_token(p.login("bob")), tok)

            def test_forgery(self):
                p = m.Portal()
                victim = p.login("carol")
                real = p.csrf_token(victim)
                for guess in sorted(guesses(p.users)) + ["", "None", real[:-1], real + "0"]:
                    self.assertNotEqual(guess, real)
                    self.assertIsNone(attempt(p.change_email, victim, guess, "x@evil.io"))
                self.assertEqual(p.emails["carol"], "carol@example.com")
                mine = p.login("ann")
                self.assertIsNone(attempt(p.change_email, victim, p.csrf_token(mine), "x@evil.io"))
                self.assertEqual(p.emails["carol"], "carol@example.com")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

DBL = dd(r'''
    """Notes page with double-submit CSRF protection (in-process model)."""
    import secrets


    class NotesApp:
        """Cookies are plain dicts: the browser sends `cookies` (name -> value) with every request and stores what the app returns in `set_cookies`.
        `sid` is the session cookie (session ids map to users in `self.sessions`)."""

        def __init__(self):
            self.sessions = {"sid-ann": "ann", "sid-bob": "bob"}
            self.notes = {"ann": "", "bob": ""}
            self.secret = secrets.token_bytes(32)

        def form(self, cookies):
            """(html, set_cookies): the notes form. The anti-CSRF token is sent twice: as the cookie `csrf` and in the hidden input `<input type="hidden" name="csrf" value="TOKEN">`
            (double-submit pattern). PermissionError when not logged in."""
            if cookies.get("sid") not in self.sessions:
                raise PermissionError("login required")
            token = secrets.token_urlsafe(24)
            html = '<form method="post"><input type="hidden" name="csrf" value="%s"><textarea name="note"></textarea></form>' % token
            return html, {"csrf": token}

        def post(self, cookies, form):
            """Save `form["note"]` for the logged-in user and return 200, or 403 when the request fails the CSRF check (the note is then not saved)."""
            user = self.sessions.get(cookies.get("sid"))
            if user is None:
                return 401
            if form.get("csrf") != cookies.get("csrf"):
                return 403
            self.notes[user] = form["note"]
            return 200
''')

CS.append(dict(
    slug="double-submit", d=4, product="the notes page", func="NotesApp.post", cwe="CWE-352",
    finding="The double-submit check compares the form field with the cookie, and `None == None`: a forged post that carries neither (or two empty values, or two values the attacker chose after planting a cookie from a sibling sub-domain) passes. The token is not tied to the session or signed, so the server cannot tell whether it ever issued it.",
    start={"notes.py": DBL, "README.md": readme("notes", "`form(cookies)` and `post(cookies, form)` keep their signatures and return shapes (`form` still returns `(html, set_cookies)` with the token in cookie `csrf` and in the hidden input `csrf`). `post` must answer 403 and save nothing unless the posted token equals the cookie token **and** is a token this server issued for *this* session (sign it with a server secret over the session id, e.g. HMAC; the secret exists as `self.secret`). Missing, empty, mismatching, self-chosen and other-session tokens are all rejected; a token stays valid for repeated posts in its session. Unknown sessions still get 401.")},
    solution={"notes.py": cpatched(DBL, (
        'import secrets\n', 'import hashlib\nimport hmac\nimport secrets\n'), (
        '            token = secrets.token_urlsafe(24)\n',
        '            nonce = secrets.token_urlsafe(18)\n            token = nonce + "." + self._sign(cookies["sid"], nonce)\n'), (
        '        def form(self, cookies):',
        '''        def _sign(self, sid, nonce):
            return hmac.new(self.secret, ("%s|%s" % (sid, nonce)).encode(), hashlib.sha256).hexdigest()

        def _valid(self, sid, token):
            nonce, dot, sig = (token or "").partition(".")
            return bool(dot and nonce and hmac.compare_digest(sig, self._sign(sid, nonce)))

        def form(self, cookies):'''), (
        '            if form.get("csrf") != cookies.get("csrf"):\n                return 403\n',
        '            sent, stored = form.get("csrf"), cookies.get("csrf")\n            if not sent or not stored or not hmac.compare_digest(str(sent), str(stored)) or not self._valid(cookies["sid"], sent):\n                return 403\n'))},
    hidden={"tests/test_notes_security.py": P + dd(r'''
        import re

        import notes as m


        class Browser:
            def __init__(self, app, sid):
                self.app = app
                self.cookies = {"sid": sid}

            def open_form(self):
                html, set_cookies = self.app.form(self.cookies)
                self.cookies.update(set_cookies)
                return re.search(r'name="csrf" value="([^"]+)"', html).group(1)

            def post(self, note, token="auto", cookies=None):
                if token == "auto":
                    token = self.cookies.get("csrf")
                form = {"note": note}
                if token is not None:
                    form["csrf"] = token
                return self.app.post(self.cookies if cookies is None else cookies, form)


        class NotesTest(unittest.TestCase):
            def test_flow(self):
                app = m.NotesApp()
                b = Browser(app, "sid-ann")
                tok = b.open_form()
                self.assertEqual(b.cookies["csrf"], tok)
                self.assertEqual(b.post("hello"), 200)
                self.assertEqual(app.notes["ann"], "hello")
                self.assertEqual(b.post("again"), 200)
                self.assertEqual(app.notes["ann"], "again")
                self.assertEqual(Browser(app, "nope").post("x", token="t", cookies={"sid": "nope", "csrf": "t"}), 401)
                self.assertRaises(PermissionError, app.form, {"sid": "nope"})

            def test_forged_posts(self):
                app = m.NotesApp()
                victim = Browser(app, "sid-ann")
                real = victim.open_form()
                attacker = Browser(app, "sid-bob")
                mine = attacker.open_form()
                cases = [
                    ("no token anywhere", {"sid": "sid-ann"}, None),
                    ("both empty", {"sid": "sid-ann", "csrf": ""}, ""),
                    ("form only", {"sid": "sid-ann"}, real),
                    ("cookie only", {"sid": "sid-ann", "csrf": real}, None),
                    ("mismatch", {"sid": "sid-ann", "csrf": real}, real + "x"),
                    ("self chosen", {"sid": "sid-ann", "csrf": "attacker"}, "attacker"),
                    ("self chosen dotted", {"sid": "sid-ann", "csrf": "abc.def"}, "abc.def"),
                    ("attacker's own valid token, planted", {"sid": "sid-ann", "csrf": mine}, mine),
                    ("empty nonce", {"sid": "sid-ann", "csrf": ".00"}, ".00"),
                ]
                for label, cookies, token in cases:
                    form = {"note": "pwned"}
                    if token is not None:
                        form["csrf"] = token
                    self.assertEqual(app.post(cookies, form), 403, label)
                    self.assertEqual(app.notes["ann"], "", label)
                self.assertEqual(victim.post("legit"), 200)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

CS_ORDER = ["get-mutates", "settings-token", "origin-check", "predictable-token", "double-submit"]
CS.sort(key=lambda s: (s["d"], CS_ORDER.index(s["slug"])))


@family("security-csrf", category="security", lang="python", kind="fix", n=5,
        summary="cross-site request forgery: unsafe GET, synchronizer tokens, Origin checks, predictable and double-submit tokens")
def gen_csrf(rng, n):
    return list(_sec.emit(rng, CS[:n], tags=["csrf"]))
