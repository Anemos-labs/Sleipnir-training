"""Security family: protocol-level and identity flaws that need a redesign of the parsing or state handling (user-name spoofing, an OAuth authorization server, HTTP request framing)."""
from fx import dd, family

from . import _sec
from ._sec import readme

SC = []

# ---------------------------------------------------------------------------------------------------------------------------------
# user name spoofing
ACC_START = dd(r'''
    """User directory: registration and lookup by user name (see README.md)."""
    import re

    RESERVED = {"admin", "administrator", "root", "support", "postmaster", "security", "ceo"}
    NAME = re.compile(r"[\w.-]{3,32}")


    class RegistrationError(ValueError):
        pass


    def canonical(username):
        """Comparison key of a user name."""
        return username.strip().lower()


    class Directory:
        def __init__(self):
            self.users = {}  # canonical name -> {"name": display name, "email": e-mail}

        def register(self, username, email):
            """Create an account and return its canonical name. RegistrationError for invalid, reserved or taken names and for an e-mail address that is invalid or already used."""
            if not isinstance(username, str) or not NAME.fullmatch(username.strip()):
                raise RegistrationError("invalid user name")
            key = canonical(username)
            if key in RESERVED:
                raise RegistrationError("reserved name")
            if key in self.users:
                raise RegistrationError("name taken")
            if not isinstance(email, str) or email.count("@") != 1:
                raise RegistrationError("invalid e-mail address")
            if any(u["email"] == email for u in self.users.values()):
                raise RegistrationError("e-mail address already registered")
            self.users[key] = {"name": username.strip(), "email": email}
            return key

        def find(self, username):
            """The record of a user, or None."""
            return self.users.get(canonical(username))
''')

ACC_SOL = dd(r'''
    """User directory: registration and lookup by user name (see README.md)."""
    import re
    import unicodedata

    from confusables import CONFUSABLES

    RESERVED = {"admin", "administrator", "root", "support", "postmaster", "security", "ceo"}
    MIN_LEN, MAX_LEN = 3, 32
    MAIL_BAD = re.compile(r"[\s\x00-\x1f\x7f]")


    class RegistrationError(ValueError):
        pass


    def _nfkc(text):
        return unicodedata.normalize("NFKC", text)


    def canonical(username):
        """Comparison key of a user name: NFKC, case-folded, NFKC again."""
        return _nfkc(_nfkc(username.strip()).casefold())


    def skeleton(username):
        """The key with look-alike letters mapped to Latin ones (and the combining dot of a Turkish capital I removed)."""
        key = canonical(username).replace("\u0307", "")
        return "".join(CONFUSABLES.get(c, c) for c in key)


    RESERVED_SKELETONS = {skeleton(r) for r in RESERVED}


    def _script(ch):
        name = unicodedata.name(ch, "")
        return name.split()[0] if name else "UNKNOWN"


    def _check_name(display):
        if not MIN_LEN <= len(display) <= MAX_LEN:
            raise RegistrationError("a user name has 3 to 32 characters")
        scripts = set()
        for ch in display:
            if ch in "._-" or unicodedata.category(ch) == "Nd":
                continue
            if not unicodedata.category(ch).startswith("L"):
                raise RegistrationError("invalid character in user name")
            scripts.add(_script(ch))
        if len(scripts) > 1:
            raise RegistrationError("user names may not mix scripts")


    def _check_email(email):
        mail = email.strip().lower()
        local, at, domain = mail.partition("@")
        if not at or "@" in domain or not local or not domain or MAIL_BAD.search(mail):
            raise RegistrationError("invalid e-mail address")
        return mail


    class Directory:
        def __init__(self):
            self.users = {}  # canonical name -> {"name": display name, "email": e-mail}
            self.skeletons = {}  # skeleton -> canonical name

        def register(self, username, email):
            """Create an account and return its canonical name. RegistrationError for invalid, reserved or taken names and for an e-mail address that is invalid or already used."""
            if not isinstance(username, str) or not isinstance(email, str):
                raise RegistrationError("user name and e-mail address must be text")
            display = _nfkc(username.strip())
            _check_name(display)
            key = canonical(display)
            skel = skeleton(display)
            if skel in RESERVED_SKELETONS:
                raise RegistrationError("reserved name")
            if key in self.users or skel in self.skeletons:
                raise RegistrationError("name taken")
            mail = _check_email(email)
            if any(u["email"] == mail for u in self.users.values()):
                raise RegistrationError("e-mail address already registered")
            self.users[key] = {"name": display, "email": mail}
            self.skeletons[skel] = key
            return key

        def find(self, username):
            """The record of a user, or None."""
            if not isinstance(username, str):
                return None
            return self.users.get(canonical(username))
''')

CONFUSABLES = dd(r'''
    """Letters that look like Latin letters (all lower case: names are case-folded before they are looked up here)."""

    CONFUSABLES = {
        "\u0430": "a", "\u0441": "c", "\u0435": "e", "\u043e": "o", "\u0440": "p", "\u0445": "x", "\u0443": "y", "\u0456": "i", "\u0458": "j", "\u0455": "s",
        "\u0501": "d", "\u051b": "q", "\u051d": "w", "\u04bb": "h", "\u04cf": "l",
        "\u03bf": "o", "\u03b1": "a", "\u03bd": "v", "\u03b9": "i", "\u03c5": "u", "\u03c1": "p",
        "\u0261": "g", "\u0131": "i", "\u0251": "a", "\u0237": "j",
    }
''')

ACC_README = readme("user directory", """
`Directory` keeps the accounts of the community site. `register(username, email)` creates one and returns its canonical name; every problem is a `RegistrationError` (a `ValueError`) and a failed call changes nothing.
`canonical(username)` returns the comparison key described below. `find(username)` returns the record `{"name", "email"}` of the user whose name has the same canonical key, or `None` (it never raises: non-strings and unknown names give `None`).

**User names.** Surrounding white space is ignored and the rest is converted to NFKC (so full-width letters become ordinary ones); that text is the display `name` of the record. It must have 3 to 32 characters, each a letter (Unicode category L*), a decimal digit (Nd), or one of `.` `_` `-`.
Everything else is invalid: white space, control and format characters (zero-width space and joiner, bidi marks), combining marks, symbols, emoji. The letters of one name must all be from one script (the script of a letter is the first word of its Unicode name: LATIN, CYRILLIC, GREEK, CJK, ...); digits and `.` `_` `-` belong to every script.

**Collisions.** The canonical key is `NFKC(casefold(NFKC(name)))`: names that differ only by case, width or compatibility forms are the same name (`ALICE`, `alice`, full-width `alice`, `Stra\u00dfe` and `strasse`).
A second, looser comparison uses the *skeleton* of the key: the key with U+0307 (the dot that a Turkish capital `\u0130` leaves after case folding) removed and every letter listed in `confusables.py` replaced by the Latin look-alike. A name is **taken** when its key is already registered or
its skeleton equals the skeleton of a registered name, and it is **reserved** when its skeleton equals the skeleton of one of `RESERVED` (`admin`, `administrator`, `root`, `support`, `postmaster`, `security`, `ceo`). Both give a `RegistrationError`.

**E-mail.** Surrounding white space is ignored and the address is lower-cased; it needs exactly one `@` with something before and after it and no white space or control characters. Two accounts cannot have the same address (after that normalisation). The record stores the normalised address.
""")

ACC_TEST = _sec.PY_PRELUDE + dd(r'''
    import accounts as m


    def fresh():
        d = m.Directory()
        d.register("alice", "alice@example.com")
        return d


    class DirectoryTest(unittest.TestCase):
        def test_ordinary_names(self):
            d = m.Directory()
            for i, name in enumerate(["alice", "Bob_Smith", "user_42", "a.b-c_d", "\u0438\u0432\u0430\u043d", "\u674e\u96f7\u660e", "  carol  ", "x" * 32, "abc"]):
                key = d.register(name, "u%d@example.com" % i)
                self.assertEqual(key, m.canonical(name))
            self.assertEqual(d.find("bob_smith")["name"], "Bob_Smith")
            self.assertEqual(d.find("BOB_SMITH")["email"], "u1@example.com")
            self.assertEqual(d.find("carol")["name"], "carol")
            self.assertEqual(d.register("Stra\u00dfe", "s@example.com"), "strasse")
            self.assertEqual(d.register("e\u0301clair", "e@example.com"), "\u00e9clair")
            self.assertEqual(d.find("\u00c9CLAIR")["name"], "\u00e9clair")
            self.assertEqual(d.find("\u0418\u0412\u0410\u041d")["name"], "\u0438\u0432\u0430\u043d")

        def test_find(self):
            d = fresh()
            self.assertEqual(d.find("alice")["email"], "alice@example.com")
            self.assertEqual(d.find("ALICE")["name"], "alice")
            self.assertEqual(d.find(" alice ")["name"], "alice")
            self.assertEqual(d.find("\uff41\uff4c\uff49\uff43\uff45")["name"], "alice")
            for bad in ["nobody", "", "alic", None, 5, b"alice", ["alice"]]:
                self.assertIsNone(d.find(bad))

        def test_invalid_names(self):
            d = m.Directory()
            for name in ["ab", "a", "", "   ", "x" * 33, "has space", "tab\tname", "new\nline", "emoji\U0001f600name", "bad/char", "semi;colon", "at@sign", "caf\u00e9\u0301", "adm\u200bin", "ad\u200dmin", "\u202eadmin",
                         "name\u00a0x", "\u2603snow", "plus+sign", None, 5, b"alice", ["alice"]]:
                with self.assertRaises(m.RegistrationError, msg=repr(name)):
                    d.register(name, "x@example.com")
            self.assertEqual(d.users, {})

        def test_reserved_names(self):
            d = m.Directory()
            for i, name in enumerate(["admin", "ADMIN", "Admin", "root", "Support", "postmaster", "security", "administrator", "ceo", "\uff41dmin", "\uff21\uff24\uff2d\uff29\uff2e", "\u017fupport",
                                      "\u0441\u0435\u043e", "\u0421\u0415\u041e", "\u0441eo", "ce\u043e", "\u0430dmin", "adm\u0456n", "\u0430dm\u0456n", "supp\u043ert"]):
                with self.assertRaises(m.RegistrationError, msg=repr(name)):
                    d.register(name, "r%d@example.com" % i)
            self.assertEqual(d.users, {})

        def test_taken_names(self):
            d = fresh()
            d.register("scope", "scope@example.com")
            d.register("istanbul", "ist@example.com")
            for i, name in enumerate(["alice", "Alice", "ALICE", " alice ", "\uff41lice", "\uff21\uff2c\uff29\uff23\uff25", "\u0430lice", "alic\u0435", "\u0455\u0441\u043e\u0440\u0435", "\u0405\u0421\u041e\u0420\u0415", "\u0130stanbul", "\u0131stanbul", "SCOPE"]):
                with self.assertRaises(m.RegistrationError, msg=repr(name)):
                    d.register(name, "t%d@example.com" % i)
            self.assertEqual(sorted(d.users), ["alice", "istanbul", "scope"])

        def test_lookalike_scripts_that_do_not_collide_are_fine(self):
            d = fresh()
            d.register("\u043e\u043b\u0435\u0433", "oleg@example.com")
            d.register("\u0e2a\u0e21\u0e0a\u0e32\u0e22", "thai@example.com")
            d.register("bob2", "bob2@example.com")
            d.register("b0b", "b0b@example.com")
            self.assertEqual(len(d.users), 5)

        def test_email_rules(self):
            d = m.Directory()
            d.register("carol", " Carol@Example.COM ")
            self.assertEqual(d.find("carol")["email"], "carol@example.com")
            for i, mail in enumerate(["carol@example.com", " CAROL@example.com", "Carol@Example.Com\t", "no-at", "a@@b", "@x.com", "x@", "a b@c.com", "a@b@c", "", None, 5]):
                with self.assertRaises(m.RegistrationError, msg=repr(mail)):
                    d.register("dave%d" % i, mail)
            self.assertEqual(sorted(d.users), ["carol"])
            d.register("erin", "erin+tag@example.com")
            self.assertEqual(d.find("erin")["email"], "erin+tag@example.com")

        def test_failed_registrations_change_nothing(self):
            d = fresh()
            before = (dict(d.users), dict(getattr(d, "skeletons", {})))
            for name, mail in [("alice", "new@example.com"), ("newname", "alice@example.com"), ("ab", "x@example.com"), ("\u0430dmin", "x@example.com"), ("fresh", "bad")]:
                with self.assertRaises(m.RegistrationError):
                    d.register(name, mail)
            self.assertEqual((dict(d.users), dict(getattr(d, "skeletons", {}))), before)
            d.register("fresh", "fresh@example.com")
            self.assertEqual(sorted(d.users), ["alice", "fresh"])

        def test_canonical_is_stable(self):
            for name in ["alice", "ALICE", "Stra\u00dfe", "\uff21\uff2c\uff29\uff23\uff25", "\u0130stanbul", "\u0418\u0412\u0410\u041d"]:
                key = m.canonical(name)
                self.assertEqual(m.canonical(key), key)
            self.assertEqual(m.canonical("  ALICE "), "alice")
            self.assertEqual(m.canonical("\uff21\uff2c\uff29\uff23\uff25"), "alice")
            self.assertEqual(m.canonical("Stra\u00dfe"), m.canonical("STRASSE"))


    if __name__ == "__main__":
        unittest.main()
''')

ACC_VISIBLE = {"tests/test_accounts.py": _sec.PY_PRELUDE + dd(r'''
    import accounts as m


    class DirectoryTest(unittest.TestCase):
        def test_register_and_find(self):
            d = m.Directory()
            self.assertEqual(d.register("Alice", "alice@example.com"), "alice")
            self.assertEqual(d.find("ALICE")["email"], "alice@example.com")
            self.assertIsNone(d.find("bob"))

        def test_reserved_and_taken(self):
            d = m.Directory()
            d.register("alice", "alice@example.com")
            with self.assertRaises(m.RegistrationError):
                d.register("Admin", "a@example.com")
            with self.assertRaises(m.RegistrationError):
                d.register("ALICE", "b@example.com")


    if __name__ == "__main__":
        unittest.main()
''')}

SC.append(dict(
    slug="username-spoofing", d=4, product="the community site's user directory", func="Directory.register", cwe="CWE-290",
    finding=("user names are only lower-cased and matched with `\\w`, so `\\uff41dmin` (full-width a), `\\u0430dmin` (Cyrillic a), `\\u017fupport` (long s) or `\\u0441\\u0435\\u043e` (a Cyrillic `ceo`) get past the reserved-name list, a Cyrillic look-alike of an existing "
             "user such as `\\u0455\\u0441\\u043e\\u0440\\u0435` for `scope` can be registered next to it, and the same e-mail address in another letter case opens a second account."),
    extra="README.md defines the comparison rules (NFKC and case folding, single script, look-alike skeletons, e-mail normalisation); `confusables.py` holds the look-alike table.",
    start={"accounts.py": ACC_START, "confusables.py": CONFUSABLES, "README.md": ACC_README},
    solution={"accounts.py": ACC_SOL},
    visible=ACC_VISIBLE,
    hidden={"tests/test_accounts_security.py": ACC_TEST},
    timeout_s=120,
))

# ---------------------------------------------------------------------------------------------------------------------------------
# OAuth authorization server
OA_START = dd(r'''
    """A small OAuth 2.0 authorization server (authorization code flow with PKCE and refresh tokens), in memory (see README.md)."""
    import base64
    import hashlib
    import secrets

    CODE_TTL = 60
    ACCESS_TTL = 3600


    class OAuthError(Exception):
        def __init__(self, error, description=""):
            Exception.__init__(self, "%s: %s" % (error, description))
            self.error = error


    class AuthServer:
        def __init__(self, clients, clock):
            self.clients = clients  # client_id -> {"secret": str or None (public client), "redirect_uris": [...], "scopes": [...]}
            self.clock = clock  # callable returning the time in seconds
            self.codes = {}
            self.access = {}
            self.refresh = {}

        def authorize(self, client_id, redirect_uri, scope, state, user, code_challenge=None, code_challenge_method=None):
            """`user` approved the request: returns the URL to send the browser to."""
            client = self.clients.get(client_id)
            if client is None:
                raise OAuthError("invalid_client")
            if not any(redirect_uri.startswith(u) for u in client["redirect_uris"]):
                raise OAuthError("invalid_request", "redirect_uri is not registered")
            scopes = (scope or "").split()
            for s in scopes:
                if s not in client["scopes"]:
                    raise OAuthError("invalid_scope", s)
            code = secrets.token_urlsafe(24)
            self.codes[code] = {"client_id": client_id, "user": user, "scopes": scopes, "expires": self.clock() + CODE_TTL, "challenge": code_challenge, "method": code_challenge_method}
            return "%s?code=%s&state=%s" % (redirect_uri, code, state)

        def token(self, grant_type, client_id, client_secret=None, code=None, redirect_uri=None, code_verifier=None, refresh_token=None, scope=None):
            """Token endpoint: `authorization_code` and `refresh_token` grants. Returns {"access_token", "refresh_token", "expires_in", "scope"}."""
            client = self.clients.get(client_id)
            if client is None:
                raise OAuthError("invalid_client")
            if client["secret"] is not None and client_secret is not None and client_secret != client["secret"]:
                raise OAuthError("invalid_client", "bad client credentials")
            if grant_type == "authorization_code":
                record = self.codes.get(code)
                if record is None or record["expires"] < self.clock():
                    raise OAuthError("invalid_grant")
                scopes = (scope or " ".join(record["scopes"])).split()
                return self._issue(client_id, record["user"], scopes)
            if grant_type == "refresh_token":
                record = self.refresh.get(refresh_token)
                if record is None:
                    raise OAuthError("invalid_grant")
                scopes = (scope or " ".join(record["scopes"])).split()
                return self._issue(client_id, record["user"], scopes)
            raise OAuthError("unsupported_grant_type")

        def _issue(self, client_id, user, scopes):
            access = secrets.token_urlsafe(24)
            refresh = secrets.token_urlsafe(24)
            self.access[access] = {"client_id": client_id, "user": user, "scopes": scopes, "expires": self.clock() + ACCESS_TTL}
            self.refresh[refresh] = {"client_id": client_id, "user": user, "scopes": scopes}
            return {"access_token": access, "refresh_token": refresh, "expires_in": ACCESS_TTL, "scope": " ".join(scopes)}

        def introspect(self, access_token):
            """{"active": False} or {"active": True, "client_id", "user", "scope"}."""
            record = self.access.get(access_token)
            if record is None:
                return {"active": False}
            return {"active": True, "client_id": record["client_id"], "user": record["user"], "scope": " ".join(record["scopes"])}

        def revoke(self, token):
            self.access.pop(token, None)
            self.refresh.pop(token, None)
''')

OA_SOL = dd(r'''
    """A small OAuth 2.0 authorization server (authorization code flow with PKCE and refresh tokens), in memory (see README.md)."""
    import base64
    import hashlib
    import hmac
    import re
    import secrets
    from urllib.parse import urlencode

    CODE_TTL = 60
    ACCESS_TTL = 3600
    CHALLENGE = re.compile(r"[A-Za-z0-9_-]{43}")
    VERIFIER = re.compile(r"[A-Za-z0-9._~-]{43,128}")


    class OAuthError(Exception):
        def __init__(self, error, description=""):
            Exception.__init__(self, "%s: %s" % (error, description))
            self.error = error


    def _same(a, b):
        return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


    class AuthServer:
        def __init__(self, clients, clock):
            self.clients = clients  # client_id -> {"secret": str or None (public client), "redirect_uris": [...], "scopes": [...]}
            self.clock = clock  # callable returning the time in seconds
            self.codes = {}
            self.used_codes = {}  # redeemed code -> family of the tokens issued for it
            self.access = {}
            self.refresh = {}

        def authorize(self, client_id, redirect_uri, scope, state, user, code_challenge=None, code_challenge_method=None):
            """`user` approved the request: returns the URL to send the browser to."""
            client = self.clients.get(client_id) if isinstance(client_id, str) else None
            if client is None:
                raise OAuthError("invalid_client")
            if not isinstance(redirect_uri, str) or redirect_uri not in client["redirect_uris"]:
                raise OAuthError("invalid_request", "redirect_uri is not registered")
            scopes = []
            for s in (scope or "").split():
                if s not in client["scopes"]:
                    raise OAuthError("invalid_scope", s)
                if s not in scopes:
                    scopes.append(s)
            if not scopes:
                raise OAuthError("invalid_scope", "no scope requested")
            if code_challenge is not None:
                if code_challenge_method != "S256" or not isinstance(code_challenge, str) or not CHALLENGE.fullmatch(code_challenge):
                    raise OAuthError("invalid_request", "bad PKCE challenge")
            elif client["secret"] is None:
                raise OAuthError("invalid_request", "public clients must use PKCE")
            code = secrets.token_urlsafe(24)
            self.codes[code] = {"client_id": client_id, "user": user, "scopes": scopes, "expires": self.clock() + CODE_TTL, "challenge": code_challenge,
                                "redirect_uri": redirect_uri, "family": secrets.token_hex(8)}
            params = [("code", code)]
            if state is not None:
                params.append(("state", state))
            return redirect_uri + ("&" if "?" in redirect_uri else "?") + urlencode(params)

        def _authenticate(self, client_id, client_secret):
            client = self.clients.get(client_id) if isinstance(client_id, str) else None
            if client is None:
                raise OAuthError("invalid_client")
            if client["secret"] is not None and (not isinstance(client_secret, str) or not _same(client_secret, client["secret"])):
                raise OAuthError("invalid_client", "bad client credentials")

        @staticmethod
        def _narrow(granted, requested):
            if requested is None:
                return list(granted)
            scopes = []
            for s in requested.split():
                if s not in granted:
                    raise OAuthError("invalid_scope", s)
                if s not in scopes:
                    scopes.append(s)
            if not scopes:
                raise OAuthError("invalid_scope", "no scope requested")
            return scopes

        def token(self, grant_type, client_id, client_secret=None, code=None, redirect_uri=None, code_verifier=None, refresh_token=None, scope=None):
            """Token endpoint: `authorization_code` and `refresh_token` grants. Returns {"access_token", "refresh_token", "expires_in", "scope"}."""
            self._authenticate(client_id, client_secret)
            if grant_type == "authorization_code":
                record = self.codes.pop(code, None) if isinstance(code, str) else None
                if record is None:
                    family = self.used_codes.get(code) if isinstance(code, str) else None
                    if family is not None:
                        self._revoke_family(family)
                    raise OAuthError("invalid_grant")
                self.used_codes[code] = record["family"]
                if record["expires"] <= self.clock() or record["client_id"] != client_id or record["redirect_uri"] != redirect_uri:
                    raise OAuthError("invalid_grant")
                if record["challenge"] is not None:
                    if not isinstance(code_verifier, str) or not VERIFIER.fullmatch(code_verifier):
                        raise OAuthError("invalid_grant", "bad code verifier")
                    digest = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
                    if not _same(digest, record["challenge"]):
                        raise OAuthError("invalid_grant", "bad code verifier")
                return self._issue(client_id, record["user"], self._narrow(record["scopes"], scope), record["family"])
            if grant_type == "refresh_token":
                record = self.refresh.pop(refresh_token, None) if isinstance(refresh_token, str) else None
                if record is None or record["client_id"] != client_id:
                    raise OAuthError("invalid_grant")
                return self._issue(client_id, record["user"], self._narrow(record["scopes"], scope), record["family"])
            raise OAuthError("unsupported_grant_type")

        def _issue(self, client_id, user, scopes, family):
            access = secrets.token_urlsafe(24)
            refresh = secrets.token_urlsafe(24)
            self.access[access] = {"client_id": client_id, "user": user, "scopes": scopes, "expires": self.clock() + ACCESS_TTL, "family": family}
            self.refresh[refresh] = {"client_id": client_id, "user": user, "scopes": scopes, "family": family}
            return {"access_token": access, "refresh_token": refresh, "expires_in": ACCESS_TTL, "scope": " ".join(scopes)}

        def _revoke_family(self, family):
            for table in (self.access, self.refresh):
                for key in [k for k, v in table.items() if v["family"] == family]:
                    del table[key]

        def introspect(self, access_token):
            """{"active": False} or {"active": True, "client_id", "user", "scope"}."""
            record = self.access.get(access_token) if isinstance(access_token, str) else None
            if record is None or record["expires"] <= self.clock():
                return {"active": False}
            return {"active": True, "client_id": record["client_id"], "user": record["user"], "scope": " ".join(record["scopes"])}

        def revoke(self, token):
            if not isinstance(token, str):
                return
            if token in self.refresh:
                self._revoke_family(self.refresh[token]["family"])
            else:
                self.access.pop(token, None)
''')

OA_README = readme("authorization server", r"""
`AuthServer(clients, clock)` is the in-memory authorization server of the developer platform. `clients` maps a client id to `{"secret": str or None, "redirect_uris": [...], "scopes": [...]}` (`secret` is `None` for public clients such as single-page apps);
`clock()` returns the current time in seconds. Failures raise `OAuthError` (its `error` attribute holds the OAuth error code).

* `authorize(client_id, redirect_uri, scope, state, user, code_challenge=None, code_challenge_method=None)`: the user has approved the request. The client must exist and `redirect_uri` must be **exactly** one of its registered URIs (no prefix or case-insensitive matching).
  `scope` is space separated and each name must be one of the client's scopes (at least one; duplicates collapse). A PKCE challenge needs the method `S256` and a 43-character base64url value; public clients (`secret` is `None`) must always send one.
  The result is `redirect_uri` followed by the query `code=...` and, when `state` is not `None`, `state=...`, joined with `?` (or `&` when the registered URI already has a query), with every value percent-encoded: the browser must always see exactly the `state` that was passed in.
  The code expires after `CODE_TTL` (60) seconds: it is valid while `clock() < expires`.
* `token(grant_type, client_id, client_secret=None, code=None, redirect_uri=None, code_verifier=None, refresh_token=None, scope=None)`: confidential clients must authenticate with their secret (compared in constant time); a missing or wrong secret is `invalid_client`.
  **authorization_code**: the code must exist, be unexpired, belong to the same `client_id` and to the same `redirect_uri` that was used at `authorize` (the parameter is required), and, if it was issued with a PKCE challenge, `code_verifier` (43 to 128 characters of `A-Z a-z 0-9 - . _ ~`) must hash
  (SHA-256, base64url without padding, constant-time comparison) to the challenge; otherwise `invalid_grant`. A code can be redeemed once: redeeming it again fails with `invalid_grant` and also revokes every token issued from its first redemption.
  `scope` may be given to ask for **less**: it must be a non-empty subset of what the user granted (`invalid_scope` otherwise); the result lists the scopes in the order requested (granted ones when omitted).
  **refresh_token**: the token must exist and have been issued to this client; it is used up (a new pair is issued, the old refresh token is dead) and the new tokens keep the scopes of the old (or a narrower subset), never more. Any other grant type is `unsupported_grant_type`, an unknown client `invalid_client`.
* `introspect(access_token)` is `{"active": False}` for unknown, revoked and expired tokens (an access token lives `ACCESS_TTL` = 3600 seconds, valid while `clock() < expires`), otherwise `{"active": True, "client_id", "user", "scope"}`.
* `revoke(token)` ignores unknown tokens. Revoking a refresh token also revokes the access tokens issued with it (all tokens of that grant); revoking an access token only removes that token.
""")

OA_TEST = _sec.PY_PRELUDE + dd(r'''
    import base64
    import hashlib
    from urllib.parse import parse_qs, urlsplit

    import authserver as m

    CLIENTS = {
        "web": {"secret": "s3cret-web", "redirect_uris": ["https://app.example.com/cb"], "scopes": ["read", "write"]},
        "mailer": {"secret": "s3cret-mail", "redirect_uris": ["https://app.example.com/cb?src=mail"], "scopes": ["read"]},
        "spa": {"secret": None, "redirect_uris": ["https://spa.example.com/"], "scopes": ["read", "write"]},
        "other": {"secret": "s3cret-other", "redirect_uris": ["https://other.example.com/cb"], "scopes": ["read", "write"]},
    }
    CB = "https://app.example.com/cb"
    VERIFIER = "v" * 43


    def challenge_of(verifier):
        return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


    class Clock:
        def __init__(self):
            self.now = 1000.0

        def __call__(self):
            return self.now


    def fresh():
        clock = Clock()
        return m.AuthServer({k: dict(v, redirect_uris=list(v["redirect_uris"]), scopes=list(v["scopes"])) for k, v in CLIENTS.items()}, clock), clock


    def code_from(url):
        q = parse_qs(urlsplit(url).query, keep_blank_values=True)
        assert len(q["code"]) == 1, url
        return q["code"][0]


    class OAuthTest(unittest.TestCase):
        def web_code(self, srv, scope="read write", state="xyz", user="ann", **kw):
            return code_from(srv.authorize("web", CB, scope, state, user, **kw))

        def test_authorization_code_flow(self):
            srv, clock = fresh()
            url = srv.authorize("web", CB, "read write", "st-1", "ann")
            parts = urlsplit(url)
            self.assertEqual("%s://%s%s" % (parts.scheme, parts.netloc, parts.path), CB)
            q = parse_qs(parts.query)
            self.assertEqual(q["state"], ["st-1"])
            tok = srv.token("authorization_code", "web", "s3cret-web", code=q["code"][0], redirect_uri=CB)
            self.assertEqual(tok["scope"], "read write")
            self.assertEqual(tok["expires_in"], 3600)
            info = srv.introspect(tok["access_token"])
            self.assertEqual(info, {"active": True, "client_id": "web", "user": "ann", "scope": "read write"})
            self.assertEqual(srv.introspect("nope"), {"active": False})
            self.assertEqual(srv.introspect(None), {"active": False})

        def test_refresh_rotates_and_can_narrow(self):
            srv, clock = fresh()
            tok = srv.token("authorization_code", "web", "s3cret-web", code=self.web_code(srv), redirect_uri=CB)
            new = srv.token("refresh_token", "web", "s3cret-web", refresh_token=tok["refresh_token"], scope="read")
            self.assertEqual(new["scope"], "read")
            self.assertEqual(srv.introspect(new["access_token"])["scope"], "read")
            with self.assertRaises(m.OAuthError):
                srv.token("refresh_token", "web", "s3cret-web", refresh_token=tok["refresh_token"])
            third = srv.token("refresh_token", "web", "s3cret-web", refresh_token=new["refresh_token"])
            self.assertEqual(third["scope"], "read")

        def test_public_client_with_pkce(self):
            srv, clock = fresh()
            url = srv.authorize("spa", "https://spa.example.com/", "read", None, "bo", code_challenge=challenge_of(VERIFIER), code_challenge_method="S256")
            self.assertNotIn("state", parse_qs(urlsplit(url).query))
            tok = srv.token("authorization_code", "spa", code=code_from(url), redirect_uri="https://spa.example.com/", code_verifier=VERIFIER)
            self.assertTrue(srv.introspect(tok["access_token"])["active"])

        def test_redirect_uri_must_match_exactly(self):
            srv, clock = fresh()
            for uri in [CB + "/evil", CB + "x", CB + "?x=1", "https://app.example.com.evil.io/cb", "https://evil.io/?https://app.example.com/cb", "HTTPS://APP.EXAMPLE.COM/cb", CB + "/", "https://app.example.com/cb#frag",
                        "https://app.example.com/cb/../cb", "", None, "https://other.example.com/cb"]:
                with self.assertRaises(m.OAuthError, msg=repr(uri)):
                    srv.authorize("web", uri, "read", "s", "ann")
            srv.authorize("mailer", "https://app.example.com/cb?src=mail", "read", "s", "ann")
            with self.assertRaises(m.OAuthError):
                srv.authorize("mailer", "https://app.example.com/cb?src=mail&x=1", "read", "s", "ann")

        def test_state_and_query_are_encoded(self):
            srv, clock = fresh()
            for state in ["x&code=attacker", "a b#c", "\u00e9&=?", "%26", "line\r\nbreak", "", "a=b&c=d&state=e"]:
                url = srv.authorize("web", CB, "read", state, "ann")
                parts = urlsplit(url)
                q = parse_qs(parts.query, keep_blank_values=True)
                self.assertEqual(sorted(q), ["code", "state"], url)
                self.assertEqual(q["state"], [state], url)
                self.assertEqual(len(q["code"]), 1)
                self.assertEqual(parts.fragment, "")
                self.assertNotIn("\r", url)
                self.assertNotIn("\n", url)
            url = srv.authorize("mailer", "https://app.example.com/cb?src=mail", "read", "s&t", "ann")
            q = parse_qs(urlsplit(url).query)
            self.assertEqual(q["src"], ["mail"])
            self.assertEqual(q["state"], ["s&t"])
            self.assertEqual(urlsplit(url).path, "/cb")
            self.assertEqual(len(q["code"]), 1)

        def test_codes_are_single_use(self):
            srv, clock = fresh()
            code = self.web_code(srv)
            tok = srv.token("authorization_code", "web", "s3cret-web", code=code, redirect_uri=CB)
            self.assertTrue(srv.introspect(tok["access_token"])["active"])
            with self.assertRaises(m.OAuthError):
                srv.token("authorization_code", "web", "s3cret-web", code=code, redirect_uri=CB)
            self.assertFalse(srv.introspect(tok["access_token"])["active"])
            with self.assertRaises(m.OAuthError):
                srv.token("refresh_token", "web", "s3cret-web", refresh_token=tok["refresh_token"])

        def test_codes_are_bound_to_client_and_redirect_uri(self):
            srv, clock = fresh()
            for kwargs in [dict(client="other", secret="s3cret-other", redirect=CB), dict(client="web", secret="s3cret-web", redirect="https://other.example.com/cb"), dict(client="web", secret="s3cret-web", redirect=None),
                           dict(client="web", secret="s3cret-web", redirect=CB + "/"), dict(client="mailer", secret="s3cret-mail", redirect=CB)]:
                code = self.web_code(srv)
                with self.assertRaises(m.OAuthError, msg=repr(kwargs)):
                    srv.token("authorization_code", kwargs["client"], kwargs["secret"], code=code, redirect_uri=kwargs["redirect"])
            for bad in [None, "", "nope", 5, ["x"]]:
                with self.assertRaises(m.OAuthError):
                    srv.token("authorization_code", "web", "s3cret-web", code=bad, redirect_uri=CB)

        def test_lifetimes(self):
            srv, clock = fresh()
            code = self.web_code(srv)
            clock.now += 59
            tok = srv.token("authorization_code", "web", "s3cret-web", code=code, redirect_uri=CB)
            code = self.web_code(srv)
            clock.now += 60
            with self.assertRaises(m.OAuthError):
                srv.token("authorization_code", "web", "s3cret-web", code=code, redirect_uri=CB)
            self.assertTrue(srv.introspect(tok["access_token"])["active"])
            clock.now = 1059 + 3600 - 1
            self.assertTrue(srv.introspect(tok["access_token"])["active"])
            clock.now = 1059 + 3600
            self.assertFalse(srv.introspect(tok["access_token"])["active"])

        def test_client_authentication(self):
            srv, clock = fresh()
            for secret in [None, "", "wrong", "s3cret-web ", "S3CRET-WEB", 5, "s3cret-mail"]:
                code = self.web_code(srv)
                with self.assertRaises(m.OAuthError, msg=repr(secret)):
                    srv.token("authorization_code", "web", secret, code=code, redirect_uri=CB)
            with self.assertRaises(m.OAuthError):
                srv.token("authorization_code", "nobody", "x", code="c", redirect_uri=CB)
            with self.assertRaises(m.OAuthError):
                srv.token("authorization_code", None, None, code="c", redirect_uri=CB)
            tok = srv.token("authorization_code", "web", "s3cret-web", code=self.web_code(srv), redirect_uri=CB)
            for secret in [None, "wrong"]:
                with self.assertRaises(m.OAuthError):
                    srv.token("refresh_token", "web", secret, refresh_token=tok["refresh_token"])
            self.assertTrue(srv.token("refresh_token", "web", "s3cret-web", refresh_token=tok["refresh_token"])["access_token"])

        def test_pkce(self):
            srv, clock = fresh()
            good = challenge_of(VERIFIER)
            for verifier in [None, "", "w" * 43, VERIFIER + "x", "short", 5, VERIFIER.upper()]:
                code = self.web_code(srv, code_challenge=good, code_challenge_method="S256")
                with self.assertRaises(m.OAuthError, msg=repr(verifier)):
                    srv.token("authorization_code", "web", "s3cret-web", code=code, redirect_uri=CB, code_verifier=verifier)
            code = self.web_code(srv, code_challenge=good, code_challenge_method="S256")
            self.assertTrue(srv.token("authorization_code", "web", "s3cret-web", code=code, redirect_uri=CB, code_verifier=VERIFIER)["access_token"])
            for kw in [dict(code_challenge=VERIFIER, code_challenge_method="plain"), dict(code_challenge=good), dict(code_challenge=good, code_challenge_method="s256"), dict(code_challenge="x" * 42, code_challenge_method="S256"),
                       dict(code_challenge=good + "=", code_challenge_method="S256"), dict(code_challenge="", code_challenge_method="S256")]:
                with self.assertRaises(m.OAuthError, msg=repr(kw)):
                    srv.authorize("web", CB, "read", "s", "ann", **kw)
            with self.assertRaises(m.OAuthError):
                srv.authorize("spa", "https://spa.example.com/", "read", "s", "ann")
            with self.assertRaises(m.OAuthError):
                srv.authorize("spa", "https://spa.example.com/", "read", "s", "ann", code_challenge=VERIFIER, code_challenge_method="plain")

        def test_scopes_cannot_be_widened(self):
            srv, clock = fresh()
            code = self.web_code(srv, scope="read")
            with self.assertRaises(m.OAuthError):
                srv.token("authorization_code", "web", "s3cret-web", code=code, redirect_uri=CB, scope="read write")
            code = self.web_code(srv, scope="read")
            tok = srv.token("authorization_code", "web", "s3cret-web", code=code, redirect_uri=CB, scope="read")
            self.assertEqual(tok["scope"], "read")
            for scope in ["read write", "write", "admin", "read admin"]:
                fresh_tok = srv.token("authorization_code", "web", "s3cret-web", code=self.web_code(srv, scope="read"), redirect_uri=CB)
                with self.assertRaises(m.OAuthError, msg=scope):
                    srv.token("refresh_token", "web", "s3cret-web", refresh_token=fresh_tok["refresh_token"], scope=scope)
            for scope in ["admin", "read admin", "", "   "]:
                with self.assertRaises(m.OAuthError, msg=repr(scope)):
                    srv.authorize("web", CB, scope, "s", "ann")
            with self.assertRaises(m.OAuthError):
                srv.authorize("mailer", "https://app.example.com/cb?src=mail", "read write", "s", "ann")
            code = self.web_code(srv, scope="write read read")
            tok = srv.token("authorization_code", "web", "s3cret-web", code=code, redirect_uri=CB, scope="write")
            self.assertEqual(tok["scope"], "write")
            self.assertEqual(srv.introspect(tok["access_token"])["scope"], "write")

        def test_refresh_tokens_belong_to_their_client(self):
            srv, clock = fresh()
            tok = srv.token("authorization_code", "web", "s3cret-web", code=self.web_code(srv), redirect_uri=CB)
            with self.assertRaises(m.OAuthError):
                srv.token("refresh_token", "other", "s3cret-other", refresh_token=tok["refresh_token"])
            for bad in [None, "", "nope", 5]:
                with self.assertRaises(m.OAuthError):
                    srv.token("refresh_token", "web", "s3cret-web", refresh_token=bad)
            with self.assertRaises(m.OAuthError):
                srv.token("password", "web", "s3cret-web")

        def test_revocation(self):
            srv, clock = fresh()
            tok = srv.token("authorization_code", "web", "s3cret-web", code=self.web_code(srv), redirect_uri=CB)
            newer = srv.token("refresh_token", "web", "s3cret-web", refresh_token=tok["refresh_token"])
            srv.revoke("unknown")
            srv.revoke(None)
            self.assertTrue(srv.introspect(newer["access_token"])["active"])
            srv.revoke(newer["access_token"])
            self.assertFalse(srv.introspect(newer["access_token"])["active"])
            again = srv.token("refresh_token", "web", "s3cret-web", refresh_token=newer["refresh_token"])
            self.assertTrue(srv.introspect(again["access_token"])["active"])
            srv.revoke(again["refresh_token"])
            self.assertFalse(srv.introspect(again["access_token"])["active"])
            with self.assertRaises(m.OAuthError):
                srv.token("refresh_token", "web", "s3cret-web", refresh_token=again["refresh_token"])

        def test_unknown_client_and_empty_requests(self):
            srv, clock = fresh()
            with self.assertRaises(m.OAuthError):
                srv.authorize("ghost", CB, "read", "s", "ann")
            with self.assertRaises(m.OAuthError):
                srv.authorize("web", CB, None, "s", "ann")


    if __name__ == "__main__":
        unittest.main()
''')

OA_VISIBLE = {"tests/test_authserver.py": _sec.PY_PRELUDE + dd(r'''
    from urllib.parse import parse_qs, urlsplit

    import authserver as m

    CLIENTS = {"web": {"secret": "s3cret-web", "redirect_uris": ["https://app.example.com/cb"], "scopes": ["read", "write"]}}


    class FlowTest(unittest.TestCase):
        def test_code_flow(self):
            srv = m.AuthServer(CLIENTS, lambda: 1000.0)
            url = srv.authorize("web", "https://app.example.com/cb", "read", "abc", "ann")
            q = parse_qs(urlsplit(url).query)
            self.assertEqual(q["state"], ["abc"])
            tok = srv.token("authorization_code", "web", "s3cret-web", code=q["code"][0], redirect_uri="https://app.example.com/cb")
            self.assertEqual(tok["scope"], "read")
            self.assertTrue(srv.introspect(tok["access_token"])["active"])

        def test_unknown_client(self):
            srv = m.AuthServer(CLIENTS, lambda: 1000.0)
            with self.assertRaises(m.OAuthError):
                srv.authorize("nobody", "https://app.example.com/cb", "read", "abc", "ann")


    if __name__ == "__main__":
        unittest.main()
''')}

SC.append(dict(
    slug="oauth-server", d=5, product="the developer platform's authorization server", func="AuthServer", cwe="CWE-287",
    finding=("the authorization-code flow can be abused in several ways: redirect URIs are matched by prefix (`https://app.example.com/cb/../evil`, `.../cbx`), `state` is pasted into the redirect URL unencoded, codes can be redeemed twice and by other clients or for other "
             "redirect URIs, PKCE is ignored, confidential clients may omit their secret, the token request can ask for more scopes than the user granted (also on refresh), refresh tokens are neither rotated nor bound to a client, and expired access tokens still introspect as active."),
    extra="README.md specifies the endpoints exactly (matching, encoding, binding, PKCE, scopes, rotation, revocation).",
    start={"authserver.py": OA_START, "README.md": OA_README},
    solution={"authserver.py": OA_SOL},
    visible=OA_VISIBLE,
    hidden={"tests/test_authserver_security.py": OA_TEST},
    timeout_s=150,
))

# ---------------------------------------------------------------------------------------------------------------------------------
# HTTP request framing
HF_START = dd(r'''
    """A small HTTP/1.1 request parser for the edge proxy (see README.md)."""


    class BadRequest(Exception):
        pass


    class Request:
        def __init__(self, method, target, version, headers, body):
            self.method = method
            self.target = target
            self.version = version
            self.headers = headers  # list of (lower-case name, value)
            self.body = body

        def header(self, name):
            """The first value of a header (case-insensitive name) or None."""
            for n, v in self.headers:
                if n == name.lower():
                    return v
            return None

        def header_all(self, name):
            return [v for n, v in self.headers if n == name.lower()]


    def _chunked(buf):
        body = b""
        while True:
            line, sep, buf = buf.partition(b"\n")
            if not sep:
                raise BadRequest("incomplete chunk")
            size = int(line.split(b";")[0], 16)
            if size == 0:
                while True:  # skip the trailer
                    line, sep, buf = buf.partition(b"\n")
                    if not sep:
                        raise BadRequest("incomplete trailer")
                    if line.strip() == b"":
                        return body, buf
            body += buf[:size]
            buf = buf[size:].lstrip(b"\r\n")


    def parse_request(data):
        """Parse one request from the start of `data` (bytes). Returns (Request, rest): `rest` is what follows it (a pipelined request). BadRequest when the data is invalid or incomplete."""
        head, sep, rest = data.partition(b"\r\n\r\n")
        if not sep:
            head, sep, rest = data.partition(b"\n\n")
        if not sep:
            raise BadRequest("incomplete head")
        lines = head.replace(b"\r\n", b"\n").split(b"\n")
        try:
            method, target, version = lines[0].decode("latin-1").split(" ")
        except ValueError:
            raise BadRequest("bad request line")
        headers = []
        for line in lines[1:]:
            if line[:1] in (b" ", b"\t") and headers:
                headers[-1] = (headers[-1][0], headers[-1][1] + " " + line.strip().decode("latin-1"))
                continue
            name, _, value = line.partition(b":")
            headers.append((name.strip().decode("latin-1").lower(), value.strip().decode("latin-1")))
        te = [v for n, v in headers if n == "transfer-encoding"]
        cl = [v for n, v in headers if n == "content-length"]
        if te and "chunked" in te[-1].lower():
            body, rest = _chunked(rest)
        elif cl:
            try:
                n = int(cl[0])
            except ValueError:
                raise BadRequest("bad content-length")
            if len(rest) < n:
                raise BadRequest("incomplete body")
            body, rest = rest[:n], rest[n:]
        else:
            body = b""
        return Request(method, target, version, headers, body), rest
''')

HF_SOL = dd(r'''
    """A small HTTP/1.1 request parser for the edge proxy (see README.md)."""
    import re

    MAX_HEAD = 16384
    MAX_FIELDS = 100
    MAX_BODY = 1 << 20
    MAX_TARGET = 8192
    METHOD = re.compile(rb"[A-Z]{1,20}")
    TARGET = re.compile(rb"/[\x21-\x7e]*|\*")
    TOKEN = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
    VALUE_BAD = re.compile(rb"[\x00-\x08\x0a-\x1f\x7f]")
    LENGTH = re.compile(rb"[0-9]{1,10}")
    CHUNK = re.compile(rb"([0-9A-Fa-f]{1,8})(;[^\r\n\x00]*)?")


    class BadRequest(Exception):
        pass


    class Request:
        def __init__(self, method, target, version, headers, body):
            self.method = method
            self.target = target
            self.version = version
            self.headers = headers  # list of (lower-case name, value)
            self.body = body

        def header(self, name):
            """The first value of a header (case-insensitive name) or None."""
            for n, v in self.headers:
                if n == name.lower():
                    return v
            return None

        def header_all(self, name):
            return [v for n, v in self.headers if n == name.lower()]


    def _chunked(buf):
        parts = []
        total = 0
        pos = 0
        while True:
            end = buf.find(b"\r\n", pos)
            if end < 0:
                raise BadRequest("incomplete chunk header" if len(buf) - pos <= 1024 else "chunk header too long")
            if end - pos > 1024:
                raise BadRequest("chunk header too long")
            m = CHUNK.fullmatch(buf[pos:end])
            if not m:
                raise BadRequest("bad chunk header")
            size = int(m.group(1), 16)
            pos = end + 2
            if size == 0:
                if buf[pos:pos + 2] == b"\r\n":
                    return b"".join(parts), buf[pos + 2:]
                if len(buf) < pos + 2 and b"\r\n".startswith(buf[pos:]):
                    raise BadRequest("incomplete chunked body")
                raise BadRequest("trailers are not supported")
            total += size
            if total > MAX_BODY:
                raise BadRequest("body too large")
            if len(buf) < pos + size + 2:
                raise BadRequest("incomplete chunk")
            if buf[pos + size:pos + size + 2] != b"\r\n":
                raise BadRequest("chunk data is not followed by CRLF")
            parts.append(buf[pos:pos + size])
            pos += size + 2


    def parse_request(data):
        """Parse one request from the start of `data` (bytes). Returns (Request, rest): `rest` is what follows it (a pipelined request). BadRequest when the data is invalid or incomplete."""
        end = data.find(b"\r\n\r\n")
        if end < 0:
            raise BadRequest("head too large" if len(data) > MAX_HEAD else "incomplete head")
        if end + 4 > MAX_HEAD:
            raise BadRequest("head too large")
        head, rest = data[:end], data[end + 4:]
        stripped = head.replace(b"\r\n", b"")
        if b"\r" in stripped or b"\n" in stripped:
            raise BadRequest("bare CR or LF")
        lines = head.split(b"\r\n")
        parts = lines[0].split(b" ")
        if len(parts) != 3:
            raise BadRequest("bad request line")
        method, target, version = parts
        if not METHOD.fullmatch(method) or len(target) > MAX_TARGET or not TARGET.fullmatch(target) or version not in (b"HTTP/1.1", b"HTTP/1.0"):
            raise BadRequest("bad request line")
        if target == b"*" and method != b"OPTIONS":
            raise BadRequest("bad request target")
        if len(lines) - 1 > MAX_FIELDS:
            raise BadRequest("too many header fields")
        headers = []
        for line in lines[1:]:
            name, colon, value = line.partition(b":")
            if not colon or not TOKEN.fullmatch(name):
                raise BadRequest("bad header field")
            value = value.strip(b" \t")
            if VALUE_BAD.search(value):
                raise BadRequest("bad header value")
            headers.append((name.decode("ascii").lower(), value.decode("latin-1")))
        version = version.decode("ascii")
        hosts = [v for n, v in headers if n == "host"]
        if len(hosts) > 1 or (version == "HTTP/1.1" and (len(hosts) != 1 or not hosts[0])):
            raise BadRequest("bad Host header")
        lengths = [v for n, v in headers if n == "content-length"]
        codings = [v for n, v in headers if n == "transfer-encoding"]
        if lengths and codings:
            raise BadRequest("both Content-Length and Transfer-Encoding")
        if len(lengths) > 1:
            raise BadRequest("repeated Content-Length")
        if codings:
            if version != "HTTP/1.1" or len(codings) != 1 or codings[0].lower() != "chunked":
                raise BadRequest("unsupported Transfer-Encoding")
            body, rest = _chunked(rest)
        elif lengths:
            if not LENGTH.fullmatch(lengths[0].encode("latin-1")) or int(lengths[0]) > MAX_BODY:
                raise BadRequest("bad Content-Length")
            n = int(lengths[0])
            if len(rest) < n:
                raise BadRequest("incomplete body")
            body, rest = rest[:n], rest[n:]
        else:
            body = b""
        return Request(method.decode("ascii"), target.decode("ascii"), version, headers, body), rest
''')

HF_README = readme("edge request parser", r"""
`parse_request(data)` reads **one** HTTP/1.1 request from the start of `data` (bytes) and returns `(request, rest)`, where `rest` is everything after the request (the next pipelined request, untouched). Anything wrong, ambiguous or unfinished is a `BadRequest`:
the edge proxy sits in front of several back ends, so a request that two parsers could read differently must never be accepted (request smuggling).

`Request` has `method`, `target`, `version` (str), `headers` (a list of `(lower-case name, value)` pairs in order, repeated headers stay separate), `body` (bytes), and `header(name)` / `header_all(name)` (case-insensitive lookup of the first / all values).

Rules:

* **Framing.** Lines end with CRLF only. The head ends at the first CRLF CRLF; a bare LF or bare CR anywhere in the head is an error. The head (up to and including the blank line) is at most 16384 bytes and has at most 100 header fields.
* **Request line**: `METHOD SP target SP version` with single spaces. The method is 1 to 20 capital ASCII letters. The target is origin-form (`/` followed by visible ASCII 0x21-0x7e, at most 8192 bytes, so no spaces, controls or non-ASCII) or the single character `*` (only for `OPTIONS`). The version is `HTTP/1.1` or `HTTP/1.0`.
* **Header fields**: `name: value`; the name is a token (letters, digits and ``!#$%&'*+.^_`|~-``), with nothing between it and the colon (`Name : x` is an error); there is no line folding (a field line that starts with a space or tab is an error);
  the value has its leading and trailing spaces and tabs removed, may be empty and may contain tabs, spaces, visible ASCII and bytes 0x80-0xFF (decoded as Latin-1), but no other control characters (NUL, CR, LF, ...) or DEL.
* **Host**: for `HTTP/1.1` exactly one non-empty `Host` header is required; a repeated `Host` is an error in both versions.
* **Body length**: `Content-Length` must appear at most once and be 1 to 10 ASCII digits (no sign, spaces, `0x`, lists) not larger than 1 MiB (1048576). `Transfer-Encoding` is supported only as a single header whose whole value is `chunked` (any letter case), only for `HTTP/1.1`.
  Sending both `Content-Length` and `Transfer-Encoding` is an error. Without either the body is empty. A `Content-Length` body that has not completely arrived is an error (the caller retries with more data).
* **Chunked bodies**: each chunk is `size[;extension] CRLF data CRLF` with the size 1 to 8 hex digits (no `0x`, sign, spaces or underscores; extensions may not contain CR, LF or NUL and are ignored); the data must be exactly `size` bytes and followed by CRLF. A zero-size chunk ends the body and must be followed
  directly by an empty line (`0 CRLF CRLF`): trailer fields are not supported. The decoded body is at most 1 MiB; incomplete chunked data is an error.
""")

HF_TEST = _sec.PY_PRELUDE + dd(r'''
    import httpframe as m

    OK = [
        (b"GET /index.html HTTP/1.1\r\nHost: example.com\r\nAccept: */*\r\n\r\n", ("GET", "/index.html", "HTTP/1.1", [("host", "example.com"), ("accept", "*/*")], b"", b"")),
        (b"POST /up HTTP/1.1\r\nHost: h\r\nContent-Length: 5\r\n\r\nhelloGET / HTTP/1.1\r\nHost: a\r\n\r\n", ("POST", "/up", "HTTP/1.1", [("host", "h"), ("content-length", "5")], b"hello", b"GET / HTTP/1.1\r\nHost: a\r\n\r\n")),
        (b"POST /up HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n6;ext=1\r\n world\r\n0\r\n\r\n", ("POST", "/up", "HTTP/1.1", [("host", "h"), ("transfer-encoding", "chunked")], b"hello world", b"")),
        (b"GET / HTTP/1.1\r\nHOST:  example.com \t\r\nX-Multi: a\r\nx-multi: b\r\n\r\n", ("GET", "/", "HTTP/1.1", [("host", "example.com"), ("x-multi", "a"), ("x-multi", "b")], b"", b"")),
        (b"GET /old HTTP/1.0\r\n\r\n", ("GET", "/old", "HTTP/1.0", [], b"", b"")),
        (b"OPTIONS * HTTP/1.1\r\nHost: h\r\n\r\n", ("OPTIONS", "*", "HTTP/1.1", [("host", "h")], b"", b"")),
        (b"GET / HTTP/1.1\r\nHost: h\r\nX-Empty:\r\nX-Tab: a\tb\r\nReferer: http://x/y?z=1\r\n\r\n", ("GET", "/", "HTTP/1.1", [("host", "h"), ("x-empty", ""), ("x-tab", "a\tb"), ("referer", "http://x/y?z=1")], b"", b"")),
        (b"POST / HTTP/1.1\r\nHost: h\r\nContent-Length: 0\r\n\r\n", ("POST", "/", "HTTP/1.1", [("host", "h"), ("content-length", "0")], b"", b"")),
        (b"POST / HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: CHUNKED\r\n\r\n0\r\n\r\nGET", ("POST", "/", "HTTP/1.1", [("host", "h"), ("transfer-encoding", "CHUNKED")], b"", b"GET")),
        (b"POST / HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\nA\r\n0123456789\r\nf\r\n012345678901234\r\n0\r\n\r\n", ("POST", "/", "HTTP/1.1", [("host", "h"), ("transfer-encoding", "chunked")], b"0123456789012345678901234", b"")),
        (b"GET / HTTP/1.1\r\nHost: h\r\nX-Name: caf\xe9\r\n\r\n", ("GET", "/", "HTTP/1.1", [("host", "h"), ("x-name", "caf\xe9")], b"", b"")),
        (b"PURGE /cache/x HTTP/1.1\r\nHost: h\r\nContent-Length: 3\r\n\r\nabc", ("PURGE", "/cache/x", "HTTP/1.1", [("host", "h"), ("content-length", "3")], b"abc", b"")),
    ]

    BAD = [
        b"GET / HTTP/1.1\nHost: a\n\n", b"GET / HTTP/1.1\r\nHost: a\n\r\n", b"GET / HTTP/1.1\r\nHost: a\rX: y\r\n\r\n", b"GET / HTTP/1.1\r\nHost: a\r\n\n", b"GET / HTTP/1.1\r\nHost: a\r\n\r",
        b"get / HTTP/1.1\r\nHost: a\r\n\r\n", b"GET  / HTTP/1.1\r\nHost: a\r\n\r\n", b"GET\t/ HTTP/1.1\r\nHost: a\r\n\r\n", b"GET /\r\nHost: a\r\n\r\n", b"GET / HTTP/0.9\r\nHost: a\r\n\r\n", b"GET / HTTP/2.0\r\nHost: a\r\n\r\n", b"GET / HTTP/1.1 \r\nHost: a\r\n\r\n",
        b"GET / HTTP/1.1x\r\nHost: a\r\n\r\n", b"GET /a b HTTP/1.1\r\nHost: a\r\n\r\n", b"GET /a\x00b HTTP/1.1\r\nHost: a\r\n\r\n", b"GET /a\xe9 HTTP/1.1\r\nHost: a\r\n\r\n", b"GET http://evil/ HTTP/1.1\r\nHost: a\r\n\r\n", b"GET a HTTP/1.1\r\nHost: a\r\n\r\n",
        b"GET * HTTP/1.1\r\nHost: a\r\n\r\n", b"GET /" + b"a" * 8200 + b" HTTP/1.1\r\nHost: a\r\n\r\n", b"G3T / HTTP/1.1\r\nHost: a\r\n\r\n", b"\r\nGET / HTTP/1.1\r\nHost: a\r\n\r\n", b" GET / HTTP/1.1\r\nHost: a\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding : chunked\r\n\r\n0\r\n\r\n", b"GET / HTTP/1.1\r\nHost : a\r\n\r\n", b"GET / HTTP/1.1\r\nHost: a\r\n X: folded\r\n\r\n", b"GET / HTTP/1.1\r\nHost: a\r\nX: one\r\n\ttwo\r\n\r\n",
        b"GET / HTTP/1.1\r\nHost: a\r\nNoColon\r\n\r\n", b"GET / HTTP/1.1\r\nHost: a\r\n: empty-name\r\n\r\n", b"GET / HTTP/1.1\r\nHost: a\r\nBad Name: x\r\n\r\n", b"GET / HTTP/1.1\r\nHost: a\r\nBad@Name: x\r\n\r\n",
        b"GET / HTTP/1.1\r\nHost: a\r\nX: a\x00b\r\n\r\n", b"GET / HTTP/1.1\r\nHost: a\r\nX: a\x0bb\r\n\r\n", b"GET / HTTP/1.1\r\nHost: a\r\nX: a\x7fb\r\n\r\n", b"GET / HTTP/1.1\r\nHost: a\r\nX: a\x01b\r\n\r\n",
        b"GET / HTTP/1.1\r\nHost: a\r\nHost: b\r\n\r\n", b"GET / HTTP/1.0\r\nHost: a\r\nHost: b\r\n\r\n", b"GET / HTTP/1.1\r\n\r\n", b"GET / HTTP/1.1\r\nHost:\r\n\r\n", b"GET / HTTP/1.1\r\nHost:   \r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: a\r\nContent-Length: 3\r\nContent-Length: 3\r\n\r\nabc", b"POST / HTTP/1.1\r\nHost: a\r\nContent-Length: 3\r\nContent-Length: 4\r\n\r\nabcd", b"POST / HTTP/1.1\r\nHost: a\r\nContent-Length: +3\r\n\r\nabc",
        b"POST / HTTP/1.1\r\nHost: a\r\nContent-Length: 0x3\r\n\r\nabc", b"POST / HTTP/1.1\r\nHost: a\r\nContent-Length: 3,3\r\n\r\nabc", b"POST / HTTP/1.1\r\nHost: a\r\nContent-Length: -1\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nContent-Length: 1_0\r\n\r\n0123456789",
        b"POST / HTTP/1.1\r\nHost: a\r\nContent-Length: 3 3\r\n\r\nabc", b"POST / HTTP/1.1\r\nHost: a\r\nContent-Length:\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nContent-Length: \xd9\xa3\r\n\r\nabc", b"POST / HTTP/1.1\r\nHost: a\r\nContent-Length: 99999999999\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: a\r\nContent-Length: 1048577\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nContent-Length: 10\r\n\r\nabc", b"POST / HTTP/1.1\r\nHost: a\r\nContent-Length: 6\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\nG",
        b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\nContent-Length: 6\r\n\r\n0\r\n\r\nG", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked, identity\r\n\r\n0\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: identity, chunked\r\n\r\n0\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: identity\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: xchunked\r\n\r\n0\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked;q=1\r\n\r\n0\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunk\r\n\r\n0\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\nTransfer-Encoding: identity\r\n\r\n0\r\n\r\n",
        b"POST / HTTP/1.0\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding:\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n0x5\r\nhello\r\n0\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n+5\r\nhello\r\n0\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n 5\r\nhello\r\n0\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n5 \r\nhello\r\n0\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n1_0\r\n0123456789abcdef\r\n0\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n\r\nhello\r\n0\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n000000005\r\nhello\r\n0\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n-5\r\nhello\r\n0\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhelloXX0\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello0\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n5\nhello\n0\n\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n5;a\nb\r\nhello\r\n0\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n5;a\x00b\r\nhello\r\n0\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n0\r\nX-Evil: 1\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhel", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n5", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n",
        b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n" + b"1\r\nx\r\n" * 1 + b"fffffff\r\n",
        b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n100001\r\n" + b"x" * 1048577 + b"\r\n0\r\n\r\n", b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n" + (b"80000\r\n" + b"x" * 0x80000 + b"\r\n") * 3 + b"0\r\n\r\n",
        b"GET / HTTP/1.1\r\nHost: a", b"GET / HTTP/1.1\r\nHost: a\r\n", b"GET / HTTP/1.1\r\nHost: a\r\n\r", b"", b"GET", b"\r\n\r\n",
        b"GET / HTTP/1.1\r\nHost: a\r\n" + b"X: y\r\n" * 101 + b"\r\n", b"GET / HTTP/1.1\r\nHost: a\r\nX: " + b"y" * 16384 + b"\r\n\r\n", b"GET / HTTP/1.1\r\nHost: a\r\n" + b"X-A: " + b"y" * 20000, b"GET / HTTP/1.1\r\nHost: a\r\nX: " + b"y" * 20000 + b"\r\n\r\n",
    ]


    class FramingTest(unittest.TestCase):
        def test_valid_requests(self):
            for raw, (method, target, version, headers, body, rest) in OK:
                req, left = m.parse_request(raw)
                self.assertEqual((req.method, req.target, req.version, req.headers, req.body, left), (method, target, version, headers, body, rest), raw)

        def test_header_lookup(self):
            req, _ = m.parse_request(b"GET / HTTP/1.1\r\nHost: h\r\nX-Multi: a\r\nx-MULTI: b\r\n\r\n")
            self.assertEqual(req.header("X-MULTI"), "a")
            self.assertEqual(req.header_all("x-multi"), ["a", "b"])
            self.assertEqual(req.header("Host"), "h")
            self.assertIsNone(req.header("missing"))
            self.assertEqual(req.header_all("missing"), [])

        def test_ambiguous_and_invalid_requests_are_rejected(self):
            for raw in BAD:
                with self.assertRaises(m.BadRequest, msg=raw[:120]):
                    m.parse_request(raw)

        def test_pipelining(self):
            one = b"POST /a HTTP/1.1\r\nHost: h\r\nContent-Length: 2\r\n\r\nhi"
            two = b"POST /b HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n"
            three = b"GET /c HTTP/1.1\r\nHost: h\r\n\r\n"
            data = one + two + three
            seen = []
            while data:
                req, data = m.parse_request(data)
                seen.append((req.target, req.body))
            self.assertEqual(seen, [("/a", b"hi"), ("/b", b"abc"), ("/c", b"")])

        def test_limits_at_the_boundary(self):
            body = b"x" * (1 << 20)
            req, rest = m.parse_request(b"POST / HTTP/1.1\r\nHost: h\r\nContent-Length: 1048576\r\n\r\n" + body + b"tail")
            self.assertEqual((len(req.body), rest), (1 << 20, b"tail"))
            req, rest = m.parse_request(b"POST / HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\n100000\r\n" + body + b"\r\n0\r\n\r\n")
            self.assertEqual((len(req.body), rest), (1 << 20, b""))
            head = b"GET / HTTP/1.1\r\nHost: h\r\nX: " + b"y" * (16384 - 4 - len(b"GET / HTTP/1.1\r\nHost: h\r\nX: ")) + b"\r\n\r\n"
            self.assertEqual(len(head), 16384)
            req, _ = m.parse_request(head)
            self.assertEqual(len(req.header("x")), 16384 - 4 - len(b"GET / HTTP/1.1\r\nHost: h\r\nX: "))
            fields = b"".join(b"X%d: y\r\n" % i for i in range(99))
            req, _ = m.parse_request(b"GET / HTTP/1.1\r\nHost: h\r\n" + fields + b"\r\n")
            self.assertEqual(len(req.headers), 100)
            target = b"/" + b"a" * 8191
            req, _ = m.parse_request(b"GET " + target + b" HTTP/1.1\r\nHost: h\r\n\r\n")
            self.assertEqual(len(req.target), 8192)

        def test_sizes_are_cheap(self):
            import time
            start = time.time()
            for raw in [b"GET / HTTP/1.1\r\nHost: a\r\n" + b"X: y\r\n" * 5000, b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n" + b"1\r\nx\r\n" * 100000, b"G" * 3000000, b"GET / HTTP/1.1\r\nHost: a\r\n" + b" " * 3000000]:
                try:
                    m.parse_request(raw)
                except m.BadRequest:
                    pass
            self.assertLess(time.time() - start, 3)


    if __name__ == "__main__":
        unittest.main()
''')

HF_VISIBLE = {"tests/test_httpframe.py": _sec.PY_PRELUDE + dd(r'''
    import httpframe as m


    class ParseTest(unittest.TestCase):
        def test_get(self):
            req, rest = m.parse_request(b"GET /a?b=1 HTTP/1.1\r\nHost: example.com\r\nAccept: text/html\r\n\r\n")
            self.assertEqual((req.method, req.target, req.version), ("GET", "/a?b=1", "HTTP/1.1"))
            self.assertEqual(req.header("accept"), "text/html")
            self.assertEqual((req.body, rest), (b"", b""))

        def test_post_and_chunked(self):
            req, rest = m.parse_request(b"POST /x HTTP/1.1\r\nHost: h\r\nContent-Length: 3\r\n\r\nabcNEXT")
            self.assertEqual((req.body, rest), (b"abc", b"NEXT"))
            req, rest = m.parse_request(b"POST /x HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\n2\r\nhi\r\n0\r\n\r\n")
            self.assertEqual((req.body, rest), (b"hi", b""))

        def test_incomplete(self):
            with self.assertRaises(m.BadRequest):
                m.parse_request(b"GET / HTTP/1.1\r\nHost: h\r\n")


    if __name__ == "__main__":
        unittest.main()
''')}

SC.append(dict(
    slug="http-framing", d=5, product="the edge proxy", func="parse_request", cwe="CWE-444",
    finding=("`parse_request` is lenient in ways that let two parsers disagree about where a request ends (request smuggling): bare LF line ends, folded and `Name : value` header lines, repeated or malformed `Content-Length`, `Content-Length` together with `Transfer-Encoding`, "
             "`chunked, identity` and similar codings, `int()`-style chunk sizes (`0x5`, `+5`, `1_0`), trailers, control characters in values and targets, a missing or repeated `Host`."),
    extra="README.md lists the exact grammar to accept; everything else must be a BadRequest, and valid requests (including pipelined ones) must parse unchanged.",
    start={"httpframe.py": HF_START, "README.md": HF_README},
    solution={"httpframe.py": HF_SOL},
    visible=HF_VISIBLE,
    hidden={"tests/test_httpframe_security.py": HF_TEST},
    timeout_s=150,
))

ORDER = ["username-spoofing", "oauth-server", "http-framing"]
SC.sort(key=lambda s: ORDER.index(s["slug"]))


@family("security-protocols", category="security", lang="python", kind="fix", n=3,
        summary="identity and protocol flaws: Unicode user-name spoofing, an OAuth authorization server with many gaps, lenient HTTP request framing")
def gen_protocols(rng, n):
    return list(_sec.emit(rng, SC[:n], tags=["protocols"]))
