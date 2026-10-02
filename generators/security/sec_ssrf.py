"""Security family: server-side request forgery guards (allow-lists, address checks, redirects, DNS rebinding). Nothing here touches the network:
fetchers, transports and resolvers are injected and replaced by in-process fakes in the hidden tests."""
from fx import dd, family

from . import _sec
from ._sec import patched, readme

P = _sec.PY_PRELUDE + dd(r'''
    import ipaddress
    import socket
    from urllib.parse import urlsplit


    class Recorder:
        """A fake network function: remembers every call and returns a fixed result."""

        def __init__(self, result="ok"):
            self.calls = []
            self.result = result

        def __call__(self, *args):
            self.calls.append(args)
            return self.result


    def fake_resolve(table):
        """A resolver for the tests: names from `table`, otherwise numeric host forms the way inet_aton / ip_address read them."""
        def resolve(host):
            if host in table:
                return list(table[host])
            try:
                return [str(ipaddress.ip_address(host))]
            except ValueError:
                pass
            try:
                return [socket.inet_ntoa(socket.inet_aton(host))]
            except OSError:
                raise OSError("cannot resolve " + host)
        return resolve


    def is_public(addr):
        ip = ipaddress.ip_address(addr)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        return ip.is_global and not ip.is_multicast


''')

SC = []

# ---------------------------------------------------------------------------------------------------------------------------------
HOOKS = dd(r'''
    """Outgoing webhooks of the billing service."""

    ALLOWED_PREFIX = "https://hooks.partner.example"


    def is_allowed(url):
        """True when `url` may receive webhooks: https, on the partner's hook host `hooks.partner.example` (any path or query; port 443 may be written out)."""
        return url.startswith(ALLOWED_PREFIX)


    def deliver(url, payload, post):
        """POST `payload` (bytes) to `url` through `post(url, payload)` and return its result. Raises ValueError for targets that are not allowed."""
        if not is_allowed(url):
            raise ValueError("webhook target not allowed: %s" % url)
        return post(url, payload)
''')

SC.append(dict(
    slug="webhook-prefix", d=2, product="the billing webhooks", func="is_allowed", cwe="CWE-918",
    finding="`is_allowed` only checks that the URL *starts with* the partner's address, so `https://hooks.partner.example.evil.io/`, `https://hooks.partner.example@evil.io/` and `https://hooks.partner.example:8443/` all pass and the service posts payloads wherever an attacker-controlled setting points it.",
    start={"hooks.py": HOOKS, "README.md": readme("webhooks", "`deliver(url, payload, post)` sends the payload only to `https://hooks.partner.example` (path and query are free; port 443 may be spelled out; host name and scheme are case-insensitive). Any other host, scheme (including `http`), port, or a URL with user info is refused with `ValueError` and `post` is not called.")},
    solution={"hooks.py": patched(HOOKS, (
        '"""Outgoing webhooks of the billing service."""\n',
        '"""Outgoing webhooks of the billing service."""\nfrom urllib.parse import urlsplit\n'), (
        '    return url.startswith(ALLOWED_PREFIX)\n',
        '    try:\n        parts = urlsplit(url)\n        port = parts.port\n    except ValueError:\n        return False\n    return (parts.scheme == "https" and parts.hostname == "hooks.partner.example" and port in (None, 443)\n            and parts.username is None and parts.password is None and "\\\\" not in url)\n')),
    },
    hidden={"tests/test_hooks_security.py": P + dd(r'''
        import hooks as m


        class HookTest(unittest.TestCase):
            def test_partner_urls(self):
                for url in ["https://hooks.partner.example", "https://hooks.partner.example/", "https://hooks.partner.example/a/b?x=1&y=2", "https://hooks.partner.example:443/x", "HTTPS://HOOKS.Partner.Example/x"]:
                    rec = Recorder("sent")
                    self.assertEqual(m.deliver(url, b"{}", rec), "sent", url)
                    self.assertEqual(rec.calls, [(url, b"{}")])

            def test_other_targets(self):
                for url in ["https://hooks.partner.example.evil.io/x", "https://hooks.partner.example@evil.io/", "https://hooks.partner.exampleevil.io/", "http://hooks.partner.example/",
                            "https://hooks.partner.example:8443/", "https://hooks.partner.example:pw@evil.io/", "https://evil.io\\@hooks.partner.example/", "//hooks.partner.example/x",
                            "https://evil.io/https://hooks.partner.example", "ftp://hooks.partner.example/", "https://hooks.partner.example:80@evil.io/", "https://hooks.partner.example:99999/"]:
                    rec = Recorder()
                    attempt(m.deliver, url, b"{}", rec)
                    self.assertEqual(rec.calls, [], url)


        if __name__ == "__main__":
            unittest.main()
    '''), },
))

# ---------------------------------------------------------------------------------------------------------------------------------
PROXY = dd(r'''
    """Image proxy: downloads remote avatars on behalf of the browser."""
    import socket
    from urllib.parse import urlsplit

    BLOCKED_PREFIXES = ("10.", "192.168.", "127.", "localhost", "169.254.")


    def default_resolve(host):
        """All addresses (as text) the host name resolves to."""
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


    def fetch_avatar(url, fetch, resolve=default_resolve):
        """Download an avatar with `fetch(url)` (the injected HTTP client) and return its result.

        Only public web servers may be contacted. Refuse with ValueError anything that is not an http(s) URL with a host, and anything that reaches the private network,
        this machine or link-local space, however the host is written (names, numbers, IPv6) or resolved. `resolve(host)` lists the addresses of a host name."""
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("not a web URL")
        if parts.hostname.startswith(BLOCKED_PREFIXES):
            raise ValueError("private host")
        return fetch(url)
''')

SC.append(dict(
    slug="avatar-proxy", d=3, product="the avatar proxy", func="fetch_avatar", cwe="CWE-918",
    finding="`fetch_avatar` blocks private targets by looking at the *text* of the host (`10.`, `127.`, `localhost`...); `http://2130706433/`, `http://0x7f000001/`, `http://127.1/`, `http://[::1]/`, `http://172.16.0.5/`, or a public-looking name whose DNS record points at `10.0.0.7` all reach internal services (SSRF).",
    start={"proxy.py": PROXY, "README.md": readme("avatar proxy", "`fetch_avatar(url, fetch, resolve)` returns `fetch(url)` for http(s) URLs whose host is a public server, and raises `ValueError` (without calling `fetch`) otherwise. A host counts as public only when *every* address it has is a globally routable one: not loopback, private (RFC 1918 or IPv6 unique-local), link-local, shared (100.64.0.0/10), unspecified or reserved. IPv4-mapped IPv6 addresses count as the IPv4 address inside. Numeric hosts in any notation the OS accepts (`2130706433`, `0x7f000001`, `0177.0.0.1`, `127.1`) are addresses, and `resolve(host)` is how host names are resolved.")},
    solution={"proxy.py": patched(PROXY, (
        '"""Image proxy: downloads remote avatars on behalf of the browser."""\nimport socket\n',
        '"""Image proxy: downloads remote avatars on behalf of the browser."""\nimport ipaddress\nimport socket\n'), (
        'BLOCKED_PREFIXES = ("10.", "192.168.", "127.", "localhost", "169.254.")\n',
        '''def _public(addr):
    ip = ipaddress.ip_address(addr)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast
'''), (
        '''    if parts.hostname.startswith(BLOCKED_PREFIXES):
        raise ValueError("private host")
''', '''    try:
        addrs = [str(ipaddress.ip_address(parts.hostname))]
    except ValueError:
        addrs = list(resolve(parts.hostname))
    if not addrs or not all(_public(a) for a in addrs):
        raise ValueError("private host")
''')),
    },
    hidden={"tests/test_proxy_security.py": P + dd(r'''
        import proxy as m

        TABLE = {"images.example.org": ["93.184.216.34"], "dual.example.org": ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"], "cdn.example.net": ["151.101.1.1"],
                 "intranet.example.org": ["10.0.0.7"], "metadata.example.org": ["169.254.169.254"], "mixed.example.org": ["93.184.216.34", "10.1.2.3"],
                 "v6only.example.org": ["fd00::5"], "localtest.example.org": ["127.0.0.1"], "mapped.example.org": ["::ffff:10.0.0.1"], "shared.example.org": ["100.64.3.3"],
                 "localhost": ["127.0.0.1", "::1"]}
        resolve = fake_resolve(TABLE)


        class ProxyTest(unittest.TestCase):
            def test_public_servers(self):
                for url in ["http://images.example.org/a.png", "https://dual.example.org:8443/x?y=1", "https://cdn.example.net/", "http://8.8.8.8/x.png", "http://[2606:4700:4700::1111]/x.png", "https://IMAGES.example.org/UP.png"]:
                    rec = Recorder(b"img")
                    self.assertEqual(m.fetch_avatar(url, rec, resolve), b"img", url)
                    self.assertEqual(rec.calls, [(url,)])

            def test_internal_targets(self):
                for url in ["http://127.0.0.1/", "http://127.0.0.1:8080/admin", "http://localhost/", "http://LOCALHOST:5000/", "http://2130706433/", "http://0x7f000001/", "http://0177.0.0.1/", "http://127.1/", "http://0/",
                            "http://0.0.0.0/", "http://[::1]/", "http://[::ffff:127.0.0.1]/", "http://[::ffff:7f00:1]/", "http://169.254.169.254/latest/meta-data/", "http://172.16.0.5/", "http://172.31.255.254/",
                            "http://100.64.0.1/", "http://[fd00::1]/", "http://[fe80::1]/", "http://[::]/", "http://intranet.example.org/", "http://metadata.example.org/", "http://mixed.example.org/",
                            "http://v6only.example.org/", "http://localtest.example.org/", "http://mapped.example.org/", "http://shared.example.org/", "http://user:pw@127.0.0.1/",
                            "ftp://images.example.org/a", "file:///etc/passwd", "http:///x", "gopher://images.example.org/x", "http://unknown.example.org/"]:
                    rec = Recorder(b"img")
                    attempt(m.fetch_avatar, url, rec, resolve)
                    self.assertEqual(rec.calls, [], url)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------------------------
FOLLOW = dd(r'''
    """Link unfurler: fetches a page, following redirects, and returns the final URL and body."""
    import ipaddress
    import socket
    from urllib.parse import urljoin, urlsplit

    MAX_REDIRECTS = 5
    REDIRECT_CODES = (301, 302, 303, 307, 308)


    def default_resolve(host):
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


    def check_target(url, resolve):
        """Raise ValueError unless `url` is an http(s) URL whose host only has public addresses."""
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("not a web URL: %r" % url)
        try:
            addrs = [str(ipaddress.ip_address(parts.hostname))]
        except ValueError:
            addrs = list(resolve(parts.hostname))
        ips = [ipaddress.ip_address(a) for a in addrs]
        if not ips or not all(ip.is_global and not ip.is_multicast for ip in ips):
            raise ValueError("refusing non-public host: %r" % url)


    def unfurl(url, transport, resolve=default_resolve):
        """GET `url` with `transport(url)` -> (status, headers, body) and follow redirects (a status in REDIRECT_CODES with a `Location` header; the location may be relative)
        for at most MAX_REDIRECTS hops. Returns (final_url, body). Every URL that gets requested must pass `check_target`, not just the first one; ValueError for a bad
        target or when there are too many redirects."""
        check_target(url, resolve)
        for _ in range(MAX_REDIRECTS + 1):
            status, headers, body = transport(url)
            if status in REDIRECT_CODES and "Location" in headers:
                url = urljoin(url, headers["Location"])
                continue
            return url, body
        raise ValueError("too many redirects")
''')

SC.append(dict(
    slug="unfurl-redirects", d=4, product="the link unfurler", func="unfurl", cwe="CWE-918",
    finding="`unfurl` validates the URL the user typed but follows `Location` headers blindly, so a public page that answers `302 http://169.254.169.254/latest/meta-data/` (or `//127.0.0.1/admin`, `file:///etc/passwd`) makes the server fetch internal resources: SSRF through redirects.",
    start={"unfurl.py": FOLLOW, "README.md": readme("unfurler", "`unfurl(url, transport, resolve)` follows at most `MAX_REDIRECTS` redirects and returns `(final_url, body)`. Every hop - the first URL and each `Location` after resolving it against the current URL - has to be an http(s) URL with a public host (`check_target`), and the transport must not even be called for a bad one. Too many redirects (including loops) raise `ValueError`. A redirect status without `Location` is a final answer.")},
    solution={"unfurl.py": patched(FOLLOW, (
        '            url = urljoin(url, headers["Location"])\n            continue\n',
        '            url = urljoin(url, headers["Location"])\n            check_target(url, resolve)\n            continue\n'))},
    hidden={"tests/test_unfurl_security.py": P + dd(r'''
        import unfurl as m

        TABLE = {"pub.example": ["93.184.216.34"], "other.example": ["151.101.1.1"], "internal.example": ["10.0.0.9"]}
        resolve = fake_resolve(TABLE)


        class Transport:
            def __init__(self, pages):
                self.pages = pages
                self.calls = []

            def __call__(self, url):
                self.calls.append(url)
                return self.pages.get(url, (404, {}, b"missing"))


        def host_public(url):
            p = urlsplit(url)
            if p.scheme not in ("http", "https") or not p.hostname:
                return False
            try:
                addrs = [p.hostname] if p.hostname.replace(".", "").isdigit() or ":" in p.hostname else TABLE[p.hostname]
                return all(is_public(a) for a in addrs)
            except (KeyError, ValueError):
                return False


        class UnfurlTest(unittest.TestCase):
            def test_redirects_work(self):
                t = Transport({"http://pub.example/a": (302, {"Location": "http://other.example/b"}, b""), "http://other.example/b": (301, {"Location": "/c?x=1"}, b""),
                               "http://other.example/c?x=1": (200, {}, b"page"), "http://pub.example/plain": (200, {}, b"hello"), "http://pub.example/nolocation": (302, {}, b"body")})
                self.assertEqual(m.unfurl("http://pub.example/a", t, resolve), ("http://other.example/c?x=1", b"page"))
                self.assertEqual(t.calls, ["http://pub.example/a", "http://other.example/b", "http://other.example/c?x=1"])
                self.assertEqual(m.unfurl("http://pub.example/plain", t, resolve), ("http://pub.example/plain", b"hello"))
                self.assertEqual(m.unfurl("http://pub.example/nolocation", t, resolve), ("http://pub.example/nolocation", b"body"))

            def test_hop_limit(self):
                pages = {"http://pub.example/%d" % i: (302, {"Location": "/%d" % (i + 1)}, b"") for i in range(10)}
                pages["http://pub.example/5"] = (200, {}, b"end5")
                self.assertEqual(m.unfurl("http://pub.example/0", Transport(pages), resolve), ("http://pub.example/5", b"end5"))
                pages["http://pub.example/6"] = (200, {}, b"end6")
                pages["http://pub.example/5"] = (302, {"Location": "/6"}, b"")
                with self.assertRaises(ValueError):
                    m.unfurl("http://pub.example/0", Transport(pages), resolve)
                t = Transport({"http://pub.example/loop": (302, {"Location": "http://pub.example/loop"}, b"")})
                with self.assertRaises(ValueError):
                    m.unfurl("http://pub.example/loop", t, resolve)
                self.assertLessEqual(len(t.calls), 7)

            def test_redirects_into_the_inside(self):
                for target in ["http://169.254.169.254/latest/meta-data/", "//127.0.0.1/admin", "file:///etc/passwd", "http://internal.example/secret", "http://10.0.0.1/", "http://[::1]:8080/",
                               "gopher://pub.example/x", "http://localhost/", "http://2130706433/", "ftp://other.example/x"]:
                    t = Transport({"http://pub.example/a": (302, {"Location": target}, b""), "http://pub.example/two": (307, {"Location": "http://other.example/hop"}, b""),
                                   "http://other.example/hop": (308, {"Location": target}, b"")})
                    for start in ("http://pub.example/a", "http://pub.example/two"):
                        t.calls.clear()
                        attempt(m.unfurl, start, t, resolve)
                        self.assertTrue(all(host_public(u) for u in t.calls), (target, t.calls))
                        self.assertLessEqual(len(t.calls), 2)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------------------------
REBIND = dd(r'''
    """Webhook sender with an SSRF guard."""
    import ipaddress
    import socket
    from urllib.parse import urlsplit


    def default_resolve(host):
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


    def send(url, body, connect, resolve=default_resolve):
        """POST `body` to a public web server and return what `connect` returns.

        `connect(address, port, host, path, body)` opens a TCP connection to `address` (an IP address - or a host name, which the transport then resolves again by itself), sends
        `POST path` with the header `Host: host` and returns the response. `resolve(host)` lists the addresses (text) of a host name.
        Refuse with ValueError URLs that are not http(s), have no host, or whose host is not public: every address of the host must be globally routable (not loopback,
        private, link-local, shared, unspecified or reserved; IPv4-mapped IPv6 counts as the IPv4 address inside). `port` defaults to 80 (http) or 443 (https); `host` is the netloc of the URL;
        `path` includes the query and is `/` when the URL has no path."""
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("not a web URL")
        name = parts.hostname
        try:
            addrs = [str(ipaddress.ip_address(name))]
        except ValueError:
            addrs = list(resolve(name))
        for a in addrs:
            ip = ipaddress.ip_address(a)
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
                ip = ip.ipv4_mapped
            if not ip.is_global or ip.is_multicast:
                raise ValueError("non-public address %s" % a)
        if not addrs:
            raise ValueError("no address")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        path = (parts.path or "/") + ("?" + parts.query if parts.query else "")
        return connect(name, port, parts.netloc, path, body)
''')

SC.append(dict(
    slug="rebinding-sender", d=5, product="the webhook sender", func="send", cwe="CWE-918",
    finding="`send` checks the addresses a host name resolves to, and then hands the *host name* to the transport, which resolves it a second time. An attacker's DNS server answers the first lookup with a public address and the second with `10.0.0.5` or `169.254.169.254` (DNS rebinding), so the check passes and the request goes inside.",
    start={"sender.py": REBIND, "README.md": readme("sender", "`send(url, body, connect, resolve)` validates the target and then calls `connect(address, port, host, path, body)` exactly once and returns its result (see the docstring for the arguments). The connection must be made to an address that was validated: the transport does its own name resolution when it is given a host name, and a hostile DNS server may answer differently every time it is asked, so the address that was checked has to be the address that is used. `Host` stays the original netloc.")},
    solution={"sender.py": patched(REBIND, (
        "    return connect(name, port, parts.netloc, path, body)\n",
        "    return connect(addrs[0], port, parts.netloc, path, body)\n"))},
    hidden={"tests/test_sender_security.py": P + dd(r'''
        import sender as m


        class Dns:
            """The n-th lookup of a name gets the n-th answer (the last one repeats): a DNS server that changes its mind."""

            def __init__(self, answers):
                self.answers = answers
                self.count = {}

            def lookup(self, host):
                if host not in self.answers:
                    raise OSError("NXDOMAIN " + host)
                n = self.count.get(host, 0)
                self.count[host] = n + 1
                seq = self.answers[host]
                return list(seq[min(n, len(seq) - 1)])


        class Net:
            def __init__(self, dns):
                self.dns = dns
                self.connections = []

            def connect(self, address, port, host, path, body):
                try:
                    ip = str(ipaddress.ip_address(address))
                except ValueError:
                    ip = self.dns.lookup(address)[0]
                self.connections.append((ip, port, host, path, body))
                return "resp:" + ip


        class SenderTest(unittest.TestCase):
            def test_normal(self):
                dns = Dns({"hooks.example": [["93.184.216.34"]], "dual.example": [["2606:2800:220:1:248:1893:25c8:1946", "93.184.216.34"]]})
                net = Net(dns)
                self.assertEqual(m.send("https://hooks.example/a/b?x=1", b"body", net.connect, dns.lookup), "resp:93.184.216.34")
                self.assertEqual(net.connections[-1], ("93.184.216.34", 443, "hooks.example", "/a/b?x=1", b"body"))
                m.send("http://hooks.example:8080", b"b2", net.connect, dns.lookup)
                self.assertEqual(net.connections[-1], ("93.184.216.34", 8080, "hooks.example:8080", "/", b"b2"))
                m.send("http://93.184.216.34/x", b"b3", net.connect, dns.lookup)
                self.assertEqual(net.connections[-1], ("93.184.216.34", 80, "93.184.216.34", "/x", b"b3"))
                m.send("https://dual.example/p", b"b4", net.connect, dns.lookup)
                self.assertIn(net.connections[-1][0], {"2606:2800:220:1:248:1893:25c8:1946", "93.184.216.34"})
                self.assertEqual(len(net.connections), 4)

            def test_rebinding(self):
                dns = Dns({"rebind.example": [["93.184.216.34"], ["10.0.0.5"]], "late.example": [["93.184.216.34"], ["93.184.216.34"], ["127.0.0.1"]],
                           "flip.example": [["1.2.3.4"], ["169.254.169.254"]], "v6flip.example": [["2606:4700:4700::1111"], ["::1"]]})
                for name in ["rebind", "late", "flip", "v6flip"]:
                    net = Net(dns)
                    for _ in range(3):
                        attempt(m.send, "http://%s.example/hook" % name, b"x", net.connect, dns.lookup)
                    self.assertTrue(net.connections, name)
                    for ip, *_ in net.connections:
                        self.assertTrue(is_public(ip), (name, ip))

            def test_refused(self):
                dns = Dns({"internal.example": [["10.0.0.8"]], "mixed.example": [["93.184.216.34", "192.168.1.5"]]})
                for url in ["http://127.0.0.1/", "http://[::1]:8080/", "http://internal.example/", "http://mixed.example/", "ftp://hooks.example/", "http://[::ffff:10.0.0.1]/", "http:///x"]:
                    net = Net(dns)
                    attempt(m.send, url, b"x", net.connect, dns.lookup)
                    self.assertEqual(net.connections, [], url)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------------------------
PREVIEW = dd(r'''
    """Link previews for the chat."""
    import re
    from urllib.parse import urlsplit


    def link_title(url, fetch):
        """The `<title>` text of the page at `url`, fetched with `fetch(url)` (it returns the HTML as text; the real fetcher also understands file:, ftp:, gopher: and dict: URLs).
        Only http and https URLs are previewed; anything else raises ValueError. Pages without a title give an empty string."""
        if not urlsplit(url).netloc:
            raise ValueError("not a URL")
        html = fetch(url)
        m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
        return m.group(1).strip() if m else ""
''')

SC.append(dict(
    slug="preview-schemes", d=1, product="the chat link previews", func="link_title", cwe="CWE-918",
    finding="`link_title` accepts every URL that has a host part, so `file://localhost/etc/passwd`, `gopher://127.0.0.1:6379/_INFO`, `dict://...` and `ftp://...` are handed to the fetcher and the server reads local files or talks to internal services for whoever posts a link.",
    start={"preview.py": PREVIEW, "README.md": readme("previews", "`link_title(url, fetch)` returns the title (stripped) of an http(s) page, or `\"\"` when there is none. Any URL whose scheme is not `http` or `https` (any letter case) raises `ValueError`, as does a URL without a host. `fetch` must not be called for refused URLs.")},
    solution={"preview.py": patched(PREVIEW, (
        '    if not urlsplit(url).netloc:\n',
        '    parts = urlsplit(url)\n    if parts.scheme not in ("http", "https") or not parts.hostname:\n'))},
    hidden={"tests/test_preview_security.py": P + dd(r'''
        import preview as m


        class PreviewTest(unittest.TestCase):
            def test_titles(self):
                rec = Recorder("<html><head><TITLE>\n  Hello  </TITLE></head></html>")
                self.assertEqual(m.link_title("http://news.example/a", rec), "Hello")
                self.assertEqual(m.link_title("HTTPS://News.Example/b?x=1#frag", rec), "Hello")
                self.assertEqual(rec.calls, [("http://news.example/a",), ("HTTPS://News.Example/b?x=1#frag",)])
                self.assertEqual(m.link_title("https://x.example/", Recorder("<p>no title</p>")), "")

            def test_other_schemes(self):
                for url in ["file:///etc/passwd", "FILE://localhost/etc/hosts", "ftp://files.example/readme", "gopher://127.0.0.1:6379/_INFO", "dict://127.0.0.1:11211/stats", "jar:http://x.example/a.jar!/b",
                            "data:text/html,<title>x</title>", "javascript:alert(1)", "ldap://127.0.0.1/", "sftp://u@h.example/x", "http:///nohost", "//news.example/a", "news.example/a", ""]:
                    rec = Recorder("<title>t</title>")
                    attempt(m.link_title, url, rec)
                    self.assertEqual(rec.calls, [], url)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------------------------
SUFFIX = dd(r'''
    """Importer for shared playlists."""
    from urllib.parse import urlsplit

    TRUSTED_DOMAINS = ["example.com", "playlists.partner.net"]


    def is_trusted(url):
        """True for http(s) URLs whose host is one of TRUSTED_DOMAINS or a subdomain of one (names compare case-insensitively; an explicit port is fine)."""
        parts = urlsplit(url)
        host = parts.hostname or ""
        return parts.scheme in ("http", "https") and any(host.endswith(d) for d in TRUSTED_DOMAINS)


    def import_playlist(url, fetch):
        """Download a playlist with `fetch(url)` and return its lines. Untrusted URLs raise ValueError."""
        if not is_trusted(url):
            raise ValueError("untrusted source: %s" % url)
        return fetch(url).splitlines()
''')

SC.append(dict(
    slug="playlist-suffix", d=2, product="the playlist importer", func="is_trusted", cwe="CWE-918",
    finding="`is_trusted` compares the end of the host name with `str.endswith`, without a label boundary: `evilexample.com` and `notplaylists.partner.net` are \"trusted\", and anyone can register those, so the importer can be pointed at servers the allow-list was meant to exclude.",
    start={"playlists.py": SUFFIX, "README.md": readme("playlists", "`import_playlist(url, fetch)` only downloads from `example.com`, `playlists.partner.net` and their subdomains at any depth (http or https, any letter case, optional port). `evilexample.com`, `example.com.evil.io` and look-alikes are untrusted: `ValueError`, and `fetch` is not called. URLs with user info (`user@host`) or backslashes are never trusted, because different parsers disagree about where their host is.")},
    solution={"playlists.py": patched(SUFFIX, (
        'any(host.endswith(d) for d in TRUSTED_DOMAINS)', 'any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS) and parts.username is None and "\\\\" not in url'))},
    hidden={"tests/test_playlists_security.py": P + dd(r'''
        import playlists as m


        class PlaylistTest(unittest.TestCase):
            def test_trusted(self):
                for url in ["https://example.com/p.m3u", "https://cdn.example.com:8443/p", "http://a.b.example.com/p", "https://EXAMPLE.COM/p", "https://playlists.partner.net/x", "https://eu.playlists.partner.net/x"]:
                    rec = Recorder("one\ntwo\n")
                    self.assertEqual(m.import_playlist(url, rec), ["one", "two"], url)
                    self.assertEqual(rec.calls, [(url,)])

            def test_look_alikes(self):
                for url in ["https://evilexample.com/p", "https://notplaylists.partner.net/x", "https://example.com.evil.io/", "https://example.com@evil.io/", "https://evil.io/?u=example.com",
                            "ftp://example.com/x", "https://xexample.com", "https://playlists.partner.net.evil.io/", "https://partner.net/x", "https://com/x", "https://evil.io\\@example.com/"]:
                    rec = Recorder("x")
                    attempt(m.import_playlist, url, rec)
                    self.assertEqual(rec.calls, [], url)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------------------------
GUARD = dd(r'''
    """Address policy for outbound requests made on behalf of users."""
    import ipaddress


    def is_internal(address):
        """True for addresses that must not be contacted on behalf of users: private, loopback, link-local, unspecified, multicast, reserved and shared (carrier-grade NAT) ranges, IPv4 and IPv6 alike.
        An IPv4-mapped IPv6 address (`::ffff:a.b.c.d`) is judged as the IPv4 address it carries."""
        try:
            ip = ipaddress.IPv4Address(address)
        except ValueError:
            return False
        return ip.is_private or ip.is_loopback or ip.is_link_local


    def pick_address(host, resolve):
        """The first address (text) of `host`, provided that *every* address `resolve(host)` returns is public; ValueError otherwise (also when nothing resolves)."""
        addrs = list(resolve(host))
        if not addrs or any(is_internal(a) for a in addrs):
            raise ValueError("internal address")
        return addrs[0]
''')

SC.append(dict(
    slug="ipv6-blind-spot", d=3, product="the outbound request policy", func="is_internal", cwe="CWE-918",
    finding="`is_internal` only understands IPv4 (anything that is not an IPv4 address is reported as safe) and misses the shared 100.64.0.0/10 and multicast/reserved ranges, so `::1`, `fe80::1`, `fd00::1`, `::ffff:127.0.0.1` or a host name with an AAAA record into the private network pass the guard.",
    start={"guard.py": GUARD, "README.md": readme("address policy", "`is_internal(address)` says whether an address (text, IPv4 or IPv6) is off limits; the ranges are listed in its docstring, and `::ffff:8.8.8.8` is public because `8.8.8.8` is. `pick_address(host, resolve)` returns the first address of a host if all of them are public and raises `ValueError` otherwise or when `resolve` returns nothing.")},
    solution={"guard.py": patched(GUARD, (
        '''    try:
        ip = ipaddress.IPv4Address(address)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local
''', '''    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (not ip.is_global) or ip.is_multicast or ip.is_reserved or ip.is_unspecified
'''))},
    hidden={"tests/test_guard_security.py": P + dd(r'''
        import guard as m

        INTERNAL = ["127.0.0.1", "10.1.1.1", "172.20.0.1", "192.168.1.1", "169.254.169.254", "0.0.0.0", "100.64.0.9", "224.0.0.1", "240.0.0.1", "255.255.255.255", "::1", "::", "fe80::1", "fc00::1",
                    "fd12:3456::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254", "ff02::1", "100.127.255.255", "192.0.0.1"]
        PUBLIC = ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111", "2001:4860:4860::8888", "::ffff:8.8.8.8", "151.101.1.1"]


        class GuardTest(unittest.TestCase):
            def test_classification(self):
                for a in PUBLIC:
                    self.assertFalse(m.is_internal(a), a)
                for a in INTERNAL:
                    self.assertTrue(m.is_internal(a), a)

            def test_pick(self):
                res = fake_resolve({"ok.example": ["93.184.216.34", "2606:4700:4700::1111"], "v6.example": ["fd00::7"], "mix.example": ["8.8.8.8", "::1"], "cg.example": ["100.64.1.1"], "none.example": []})
                self.assertEqual(m.pick_address("ok.example", res), "93.184.216.34")
                self.assertEqual(m.pick_address("8.8.4.4", res), "8.8.4.4")
                for host in ["v6.example", "mix.example", "cg.example", "none.example", "::1", "127.0.0.1", "[::1]", "nx.example"]:
                    self.assertIsNone(attempt(m.pick_address, host, res), host)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------------------------
WILD = dd(r'''
    """Per-tenant outbound allow-lists."""
    import re
    from urllib.parse import urlsplit


    def host_allowed(url, patterns):
        """True when the host of the http(s) URL matches one of the allow-list `patterns`. A pattern is a host name (exact match) or `*.domain` (any host below the domain, at any depth,
        but not the bare domain). Case-insensitive; the port is ignored."""
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return False
        host = parts.hostname.lower()
        for pattern in patterns:
            if re.match(pattern.lower().replace("*", ".*"), host):
                return True
        return False
''')

SC.append(dict(
    slug="tenant-wildcards", d=3, product="the tenant allow-lists", func="host_allowed", cwe="CWE-918",
    finding="`host_allowed` turns the tenant's wildcard pattern into an unanchored regular expression with unescaped dots, so `api.partner.net` also admits `api.partner.net.evil.io` and `apixpartner.net`, and `*.example.com` admits `evilexample.com`.",
    start={"allow.py": WILD, "README.md": readme("allow-lists", "`host_allowed(url, patterns)`: exact host names, or `*.domain` for any host strictly below `domain` (at any depth, not the apex). The whole host has to match; dots are literal; letter case and ports are ignored; non-http(s) URLs never match.")},
    solution={"allow.py": patched(WILD, (
        '"""Per-tenant outbound allow-lists."""\nimport re\n', '"""Per-tenant outbound allow-lists."""\n'), (
        '        if re.match(pattern.lower().replace("*", ".*"), host):\n            return True\n',
        '        p = pattern.lower()\n        if p.startswith("*."):\n            if host.endswith(p[1:]) and len(host) > len(p) - 1:\n                return True\n        elif host == p:\n            return True\n'))},
    hidden={"tests/test_allow_security.py": P + dd(r'''
        import allow as m

        PATTERNS = ["*.example.com", "api.partner.net", "shop.example.org"]


        class AllowTest(unittest.TestCase):
            def test_allowed(self):
                for url in ["https://a.example.com/x", "http://a.b.example.com:8443/x", "https://API.Partner.NET/v1", "https://shop.example.org/", "http://shop.example.org:81/a?b=c"]:
                    self.assertTrue(m.host_allowed(url, PATTERNS), url)

            def test_not_allowed(self):
                for url in ["https://evilexample.com/", "https://example.com.evil.io/", "https://a.example.com.evil.io/", "https://apixpartner.net/", "https://api.partner.net.evil.io/", "https://example.com/",
                            "https://xapi.partner.net/", "https://shop.example.org.evil.io/", "ftp://a.example.com/", "https://evil.io/a.example.com", "https://a.example.com@evil.io/", "https://shopxexample.org/", "https://.example.com/"]:
                    self.assertFalse(m.host_allowed(url, PATTERNS), url)
                self.assertFalse(m.host_allowed("https://a.example.com/", []))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

ORDER = ["preview-schemes", "webhook-prefix", "playlist-suffix", "avatar-proxy", "ipv6-blind-spot", "tenant-wildcards", "unfurl-redirects", "rebinding-sender"]
SC.sort(key=lambda s: (s["d"], ORDER.index(s["slug"])))


@family("security-ssrf", category="security", lang="python", kind="fix", n=8,
        summary="server-side request forgery: allow-list checks, address policy, redirects, DNS rebinding")
def gen_ssrf(rng, n):
    return list(_sec.emit(rng, SC[:n], tags=["ssrf"]))
