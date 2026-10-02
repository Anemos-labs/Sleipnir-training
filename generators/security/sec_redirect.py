"""Security family: open redirects (login `next`, return URLs, trailing-slash redirects, OAuth redirect URIs, double decoding)."""
from fx import dd, family

from . import _sec
from ._sec import patched, readme

P = _sec.PY_PRELUDE + dd(r'''
    import re
    from urllib.parse import urlsplit


    def local_only(loc):
        """True when a browser would treat `loc` as a path on the current site (tabs and line feeds are dropped by browsers, `\` counts as `/`)."""
        flat = re.sub(r"[\t\r\n]", "", loc.strip()).replace("\\", "/")
        return flat.startswith("/") and not flat.startswith("//") and urlsplit(flat).netloc == ""


''')

SC = []

# ---------------------------------------------------------------------------------------------------------------------------------
LOGIN = dd(r'''
    """Where to send the user after a successful login."""


    def after_login(next_url):
        """The URL to redirect to after login: the `next` parameter the login page was opened with, or "/" when it is missing or empty.
        Only paths inside this site are allowed (they start with a single `/`); anything else is replaced by "/"."""
        return next_url or "/"
''')

SC.append(dict(
    slug="login-next", d=1, product="the login page", func="after_login", cwe="CWE-601",
    finding="`after_login` redirects to whatever `next` contains, so a phishing mail with `/login?next=https://evil.io/fake-dashboard` sends users to an attacker's site right after they typed their real password.",
    start={"login_redirect.py": LOGIN, "README.md": readme("login redirect", "`after_login(next_url)` returns `next_url` when it is a path on this site: it starts with exactly one `/` (so `/dashboard`, `/a/b?x=1&y=2#frag` and `/search?q=//x` are fine). Everything else - absolute URLs, `//host`, `/\\host`, other schemes, plain words, control characters, `None`, the empty string - gives `\"/\"`.")},
    solution={"login_redirect.py": patched(LOGIN, (
        '    return next_url or "/"\n',
        '''    if not next_url or any(ord(c) < 32 or ord(c) == 127 for c in next_url):
        return "/"
    if not next_url.startswith("/") or next_url.startswith(("//", "/\\\\")):
        return "/"
    return next_url
'''))},
    hidden={"tests/test_login_redirect_security.py": P + dd(r'''
        import login_redirect as m


        class LoginTest(unittest.TestCase):
            def test_local_paths(self):
                for url in ["/dashboard", "/a/b?x=1&y=2#frag", "/search?q=//x", "/", "/a//b", "/~user/page", "/%2F/not-a-host"]:
                    self.assertEqual(m.after_login(url), url)
                self.assertEqual(m.after_login(""), "/")
                self.assertEqual(m.after_login(None), "/")

            def test_off_site(self):
                for url in ["https://evil.io/", "http://evil.io", "//evil.io", "/\\evil.io", "\\\\evil.io", "\\/evil.io", "/\t/evil.io", "///evil.io", "http:evil.io", "https:/evil.io",
                            "javascript:alert(1)", " //evil.io", "evil.io", "data:text/html,x", "/\r\n/evil.io", "/\n/evil.io", "\t//evil.io", "mailto:a@b.c", "dashboard"]:
                    self.assertEqual(m.after_login(url), "/", repr(url))
                    self.assertTrue(local_only(m.after_login(url)))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------------------------
RETURN = dd(r'''
    """Return URLs after logout and after the consent screen."""

    SITE_HOST = "app.example.com"


    def safe_return_to(url):
        """The URL to send the user back to: a path on this site (`/x?y=1`) or an absolute http(s) URL on SITE_HOST (any port, any letter case). Everything else becomes "/"."""
        if not url:
            return "/"
        if url.startswith("/") or SITE_HOST in url:
            return url
        return "/"
''')

SC.append(dict(
    slug="return-to-host", d=2, product="the logout and consent screens", func="safe_return_to", cwe="CWE-601",
    finding="`safe_return_to` accepts anything that starts with `/` or merely *contains* the site's host name, so `//evil.io`, `https://app.example.com.evil.io/`, `https://evil.io/?app.example.com` and `https://app.example.com@evil.io/` all redirect off-site.",
    start={"returnto.py": RETURN, "README.md": readme("return urls", "`safe_return_to(url)` returns `url` unchanged for a path on this site (a single leading `/`, not `//` or `/\\`) and for an absolute `http`/`https` URL whose host is exactly `app.example.com` (any port, any letter case, no user info); for everything else, and for empty input, it returns `\"/\"`.")},
    solution={"returnto.py": patched(RETURN, (
        '"""Return URLs after logout and after the consent screen."""\n',
        '"""Return URLs after logout and after the consent screen."""\nfrom urllib.parse import urlsplit\n'), (
        '''    if url.startswith("/") or SITE_HOST in url:
        return url
    return "/"
''', '''    if any(ord(c) < 32 or ord(c) == 127 or c == "\\\\" for c in url) or url != url.strip():
        return "/"
    if url.startswith("/") and not url.startswith("//"):
        return url
    try:
        parts = urlsplit(url)
        parts.port
    except ValueError:
        return "/"
    if parts.scheme in ("http", "https") and parts.hostname == SITE_HOST and parts.username is None:
        return url
    return "/"
'''))},
    hidden={"tests/test_returnto_security.py": P + dd(r'''
        import returnto as m


        def acceptable(result):
            if result == "/" or local_only(result):
                return True
            p = urlsplit(result)
            return p.scheme in ("http", "https") and p.hostname == "app.example.com" and p.username is None and "\\" not in result


        class ReturnToTest(unittest.TestCase):
            def test_site_urls(self):
                for url in ["https://app.example.com/home", "http://APP.example.com:8443/z?q=1", "/x", "/a?b=c#d", "/", "https://app.example.com", "/a/b/c.html"]:
                    self.assertEqual(m.safe_return_to(url), url)
                self.assertEqual(m.safe_return_to(""), "/")
                self.assertEqual(m.safe_return_to(None), "/")

            def test_off_site(self):
                for url in ["https://app.example.com.evil.io/", "https://evil.io/?next=app.example.com", "https://evil.io/app.example.com", "https://app.example.com@evil.io/", "//evil.io",
                            "https://evilapp.example.com/", "http://evil.io#app.example.com", "/\\evil.io", "https://evil.io\\@app.example.com/", "javascript:alert('app.example.com')",
                            "https://app.example.com:pw@evil.io/", "/\t/evil.io", " //evil.io", "ftp://app.example.com/", "https://sub.app.example.com/"]:
                    res = m.safe_return_to(url)
                    self.assertTrue(acceptable(res), (url, res))
                    self.assertEqual(res, "/", url)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------------------------
SLASH = dd(r'''
    """Directory-style routing of the documentation server."""

    FILES = {"/index.html", "/favicon.ico", "/robots.txt"}


    def slash_redirect(path):
        """What the server answers for a request target `path` (always starts with `/`; may carry a query string such as `/blog/2024?page=2`).

        Known files (FILES) and paths that already end with a slash are served: `(200, None)`. Every other path is a directory route that lacks its slash: `(301, location)` where
        location is the same path with a slash added at the end of the path part (before the query string)."""
        target, sep, query = path.partition("?")
        if target in FILES or target.endswith("/"):
            return 200, None
        return 301, target + "/" + sep + query
''')

SC.append(dict(
    slug="slash-redirect", d=3, product="the documentation server", func="slash_redirect", cwe="CWE-601",
    finding="`slash_redirect` echoes the request path into `Location`; a request for `//evil.io` (or `/\\evil.io`) is answered with `Location: //evil.io/`, which browsers read as a link to another site, so any link to the docs server can be turned into a redirector.",
    start={"slashes.py": SLASH, "README.md": readme("directory routes", "`slash_redirect(path)` returns `(200, None)` for FILES and for paths ending in `/`, otherwise `(301, location)` with the slash added before the query string: `/docs` gives `/docs/`, `/blog/2024?page=2` gives `/blog/2024/?page=2`. The location must always be a path on this server: whatever the request looks like, browsers must not be able to read the `Location` as another site (`//host`, `/\\host`, with tabs or line feeds inside, and so on); such requests are answered with a same-site location (leading slashes collapsed to one) or with `(200, None)`.")},
    solution={"slashes.py": patched(SLASH, (
        '    target, sep, query = path.partition("?")\n',
        '    path = "".join(c for c in path if c >= " " and c != "\\x7f")\n    path = "/" + path.lstrip("/\\\\")\n    target, sep, query = path.partition("?")\n'))},
    hidden={"tests/test_slashes_security.py": P + dd(r'''
        import slashes as m


        class SlashTest(unittest.TestCase):
            def test_directories(self):
                self.assertEqual(m.slash_redirect("/docs"), (301, "/docs/"))
                self.assertEqual(m.slash_redirect("/blog/2024?page=2"), (301, "/blog/2024/?page=2"))
                self.assertEqual(m.slash_redirect("/a/b/c"), (301, "/a/b/c/"))
                self.assertEqual(m.slash_redirect("/docs/"), (200, None))
                self.assertEqual(m.slash_redirect("/docs/?x=1"), (200, None))
                self.assertEqual(m.slash_redirect("/robots.txt"), (200, None))
                self.assertEqual(m.slash_redirect("/"), (200, None))
                self.assertEqual(m.slash_redirect("/a//b"), (301, "/a//b/"))

            def test_off_site(self):
                for path in ["//evil.io", "///evil.io", "/\\evil.io", "/\\\\evil.io", "//evil.io/x/y", "//evil.io?x=1", "/\t/evil.io", "/\r\n/evil.io", "/\\/evil.io", "////evil.io/a"]:
                    status, loc = m.slash_redirect(path)
                    self.assertTrue(status == 200 or local_only(loc), (path, status, loc))
                    if status == 301:
                        self.assertTrue(loc.endswith("/") or "/?" in loc, (path, loc))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------------------------
CONT = dd(r'''
    """The `continue` parameter of the account pages."""
    from urllib.parse import urlparse


    def safe_redirect(target, default="/home"):
        """Where the `continue` parameter may send the user: only to pages of this site, i.e. relative references that stay on the current origin (`/a/b?c=d`, `page.html`, `?tab=2`, `#top`, `../up`).
        Anything that could leave the site (absolute URLs, `//host`, any scheme, backslash tricks, control characters, empty input) gives `default`."""
        parts = urlparse(target or "")
        if parts.netloc == "" and target:
            return target
        return default
''')

SC.append(dict(
    slug="continue-netloc", d=3, product="the account pages", func="safe_redirect", cwe="CWE-601",
    finding="`safe_redirect` only checks that `urlparse` finds no network location, which `/\\evil.io`, `\\\\evil.io`, `https:evil.io`, `javascript:alert(1)` and a tab in `/\t/evil.io` all satisfy, although browsers read each of them as a link to another site (or to script).",
    start={"cont.py": CONT, "README.md": readme("continue parameter", "`safe_redirect(target, default=\"/home\")` returns `target` for same-site relative references and `default` for everything else. Same-site references: paths (`/a/b?c=d`, `/search?q=a:b`), relative paths without a scheme (`page.html`, `../up/page.html`, `sub/dir/`), and bare queries or fragments (`?tab=2`, `#top`). Not allowed: anything with a scheme, anything starting with `//`, backslashes anywhere, control characters, leading or trailing whitespace, and empty input.")},
    solution={"cont.py": patched(CONT, (
        '''    parts = urlparse(target or "")
    if parts.netloc == "" and target:
        return target
    return default
''', '''    if not target or target != target.strip() or "\\\\" in target or any(ord(c) < 32 or ord(c) == 127 for c in target):
        return default
    parts = urlparse(target)
    if parts.scheme or parts.netloc or target.startswith("//"):
        return default
    return target
'''))},
    hidden={"tests/test_cont_security.py": P + dd(r'''
        import cont as m


        class ContinueTest(unittest.TestCase):
            def test_relative(self):
                for url in ["/a/b?c=d", "page.html", "?tab=2", "#top", "../up/page.html", "sub/dir/", "/search?q=a:b", "/", "./x", "a/b:c"]:
                    self.assertEqual(m.safe_redirect(url), url, url)
                self.assertEqual(m.safe_redirect("", "/else"), "/else")
                self.assertEqual(m.safe_redirect(None), "/home")

            def test_leaving_the_site(self):
                for url in ["https://evil.io", "//evil.io", "/\\evil.io", "\\\\evil.io", "\\/evil.io", "/\t/evil.io", "javascript:alert(1)", "JaVaScRiPt:alert(1)", "https:evil.io", "http:evil.io",
                            "data:text/html,x", "/\n/evil.io", "mailto:a@b.c", " //evil.io", "//evil.io ", "vbscript:x", "HTTP://evil.io", "/\x00/evil.io"]:
                    self.assertEqual(m.safe_redirect(url, "/fallback"), "/fallback", repr(url))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------------------------
OAUTH = dd(r'''
    """Authorization responses of the identity provider."""
    from urllib.parse import urlencode

    CLIENTS = {
        "web-app": ["https://app.example.net/oauth/callback", "https://app.example.net/oauth/silent"],
        "mobile": ["com.example.mobile:/callback"],
        "partner": ["https://partner.example.org/cb"],
    }


    def validate_redirect_uri(client_id, redirect_uri):
        """The redirect URI to use for `client_id`: it must be one of the client's registered URIs, compared as exact strings (RFC 6749 section 3.1.2.3, OAuth security BCP).
        ValueError for an unknown client or an unregistered URI."""
        registered = CLIENTS.get(client_id)
        if registered is None:
            raise ValueError("unknown client")
        for uri in registered:
            if redirect_uri.startswith(uri):
                return redirect_uri
        raise ValueError("redirect_uri is not registered")


    def authorization_response(client_id, redirect_uri, code, state):
        """The URL the user agent is sent to after consent: the validated redirect URI with `code` and `state` appended as query parameters (in this order, percent-encoded)."""
        uri = validate_redirect_uri(client_id, redirect_uri)
        return uri + ("&" if "?" in uri else "?") + urlencode([("code", code), ("state", state)])
''')

SC.append(dict(
    slug="oauth-redirect-uri", d=2, product="the identity provider", func="validate_redirect_uri", cwe="CWE-601",
    finding="`validate_redirect_uri` accepts any URI that merely *starts with* a registered one, so `https://app.example.net/oauth/callback/../../evil` and `https://app.example.net/oauth/callback?next=https://evil.io` pass, and an authorization code can be delivered to a page the client never registered (open redirect, account takeover).",
    start={"oauth.py": OAUTH, "README.md": readme("authorization responses", "`validate_redirect_uri(client_id, redirect_uri)` returns the URI only when it is *exactly* one of the client's registered strings, otherwise raises `ValueError` (unknown clients too). `authorization_response` builds the redirect from a validated URI: `code` and `state` are added with `?` or `&`.")},
    solution={"oauth.py": patched(OAUTH, ('if redirect_uri.startswith(uri):', 'if redirect_uri == uri:'))},
    hidden={"tests/test_oauth_security.py": P + dd(r'''
        import oauth as m


        class OauthTest(unittest.TestCase):
            def test_registered(self):
                for client, uris in m.CLIENTS.items():
                    for uri in uris:
                        self.assertEqual(m.validate_redirect_uri(client, uri), uri)
                self.assertEqual(m.authorization_response("web-app", "https://app.example.net/oauth/silent", "c d", "s&1"), "https://app.example.net/oauth/silent?code=c+d&state=s%261")
                self.assertEqual(m.authorization_response("mobile", "com.example.mobile:/callback", "abc", "xyz"), "com.example.mobile:/callback?code=abc&state=xyz")

            def test_unregistered(self):
                for client, uri in [("web-app", "https://app.example.net/oauth/callback/../../evil"), ("web-app", "https://app.example.net/oauth/callback?next=https://evil.io"),
                                    ("web-app", "https://app.example.net/oauth/callbackx"), ("web-app", "https://app.example.net/oauth/callback#frag"), ("web-app", "https://partner.example.org/cb"),
                                    ("partner", "https://partner.example.org/cb/../admin"), ("partner", "https://partner.example.org/cb@evil.io"), ("mobile", "com.example.mobile:/callback/../x"),
                                    ("mobile", "com.example.mobile:/callback?x=1"), ("web-app", "https://app.example.net/oauth/silent&x=https://evil.io"), ("ghost", "https://app.example.net/oauth/callback"),
                                    ("web-app", ""), ("web-app", "HTTPS://APP.EXAMPLE.NET/OAUTH/CALLBACK")]:
                    self.assertIsNone(attempt(m.validate_redirect_uri, client, uri), (client, uri))
                    self.assertIsNone(attempt(m.authorization_response, client, uri, "c", "s"), (client, uri))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------------------------
DOUBLE = dd(r'''
    """Post-login redirect of the customer portal."""
    from urllib.parse import parse_qs, unquote


    def login_target(query_string):
        """Where to send the user after login. `query_string` is the raw query of the login URL (`next=%252Fdashboard&x=1`).

        The login page puts the destination into its form percent-encoded, and the browser encodes the form field once more, so `next` arrives encoded twice: decode both layers
        (a `next` that was encoded only once also works). Only paths on this site may be returned (a single leading `/`); anything else, and a missing `next`, gives `/`."""
        values = parse_qs(query_string).get("next")
        if not values:
            return "/"
        raw = values[0]
        lowered = raw.lower()
        if lowered.startswith(("http", "//")) or "://" in lowered:
            return "/"
        target = unquote(raw)
        if not target.startswith("/"):
            return "/"
        return target
''')

SC.append(dict(
    slug="double-decode", d=3, product="the customer portal", func="login_target", cwe="CWE-601",
    finding="`login_target` screens the value of `next` for `http`, `//` and `://` and decodes it afterwards: `next=%252F%252Fevil.io` (or `/%252Fevil.io`) passes the screening and becomes `//evil.io` after the second decoding, an open redirect.",
    start={"portal.py": DOUBLE, "README.md": readme("portal login", "`login_target(query_string)` decodes the doubly encoded `next` (`%252Fdashboard%253Ftab%253D2` gives `/dashboard?tab=2`; `next=/dashboard` works too) and returns it if it is a path on this site - a single leading `/`, so not `//host`, not `/\\host`, no control characters in the leading part - otherwise `/`. The check applies to what the browser will finally receive.")},
    solution={"portal.py": patched(DOUBLE, (
        '''    raw = values[0]
    lowered = raw.lower()
    if lowered.startswith(("http", "//")) or "://" in lowered:
        return "/"
    target = unquote(raw)
    if not target.startswith("/"):
        return "/"
    return target
''', '''    target = unquote(values[0])
    if not target.startswith("/") or target.startswith(("//", "/\\\\")):
        return "/"
    if any(ord(c) < 32 or ord(c) == 127 for c in target):
        return "/"
    return target
'''))},
    hidden={"tests/test_portal_security.py": P + dd(r'''
        import portal as m


        class PortalTest(unittest.TestCase):
            def test_paths(self):
                self.assertEqual(m.login_target("next=%252Fdashboard%253Ftab%253D2"), "/dashboard?tab=2")
                self.assertEqual(m.login_target("x=1&next=%252Fa%252Fb%253Fx%253D1%2526y%253D2%2523frag&z=2"), "/a/b?x=1&y=2#frag")
                self.assertEqual(m.login_target("next=%252F"), "/")
                self.assertEqual(m.login_target("next=/dashboard"), "/dashboard")
                self.assertEqual(m.login_target("next=%2Fdashboard"), "/dashboard")
                self.assertEqual(m.login_target("x=1"), "/")
                self.assertEqual(m.login_target(""), "/")
                self.assertEqual(m.login_target("next=%252Fhttp%252Fdocs"), "/http/docs")

            def test_off_site(self):
                for q in ["next=%252F%252Fevil.io", "next=/%252Fevil.io", "next=%2F%252Fevil.io", "next=%252F%255Cevil.io", "next=%252F%2509%252Fevil.io", "next=%252F%250D%250A%252Fevil.io",
                          "next=https%253A%252F%252Fevil.io", "next=%252568ttps%25253A%25252F%25252Fevil.io", "next=%252F%252F%252Fevil.io", "next=//evil.io", "next=%2F%2Fevil.io", "next=%255Cevil.io",
                          "next=javascript%253Aalert(1)", "next=evil.io", "next=%2568ttps%253A%252F%252Fevil.io"]:
                    res = m.login_target(q)
                    self.assertTrue(local_only(res), (q, res))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

ORDER = ["login-next", "oauth-redirect-uri", "return-to-host", "slash-redirect", "continue-netloc", "double-decode"]
SC.sort(key=lambda s: (s["d"], ORDER.index(s["slug"])))


@family("security-open-redirect", category="security", lang="python", kind="fix", n=6,
        summary="open redirects: login next, return URLs, trailing-slash redirects, OAuth redirect URIs, double decoding")
def gen_redirect(rng, n):
    return list(_sec.emit(rng, SC[:n], tags=["redirect"]))
