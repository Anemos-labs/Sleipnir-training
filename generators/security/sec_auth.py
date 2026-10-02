"""Security families: token (JWT-style) verification, password storage and policy, session management. In-process models only."""
from fx import dd, family

from . import _sec
from ._sec import patched, readme

P = _sec.PY_PRELUDE

# =================================================================================================================================
#  JWT-style tokens
# =================================================================================================================================
JW = []

JT = P + dd(r'''
    import base64
    import hashlib
    import hmac
    import json


    def b64(raw):
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


    def forge(header, claims, secret=None, sig=None, algo=hashlib.sha256):
        """A token assembled by hand: any header, any claims; signed with `secret` (HMAC over header.body) unless `sig` bytes are given; unsigned when neither is."""
        h = b64(json.dumps(header).encode())
        p = b64(json.dumps(claims).encode())
        if sig is None:
            sig = hmac.new(secret, (h + "." + p).encode(), algo).digest() if secret is not None else b""
        return h + "." + p + "." + b64(sig)


''')

BASE = dd(r'''
    import base64
    import hashlib
    import hmac
    import json


    def _b64e(raw):
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


    def _b64d(text):
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


    def encode(claims, secret):
        """HS256 token for the dict `claims`; `secret` is bytes."""
        head = _b64e(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        body = _b64e(json.dumps(claims).encode())
        sig = hmac.new(secret, (head + "." + body).encode(), hashlib.sha256).digest()
        return head + "." + body + "." + _b64e(sig)
''')

SIGLESS = '"""Minimal HS256 tokens for the session service."""\n' + BASE + dd(r'''


    def decode(token, secret):
        """The claims of a token made by `encode` with the same secret. ValueError for anything else: wrong shape, wrong or missing signature, bad encoding."""
        head, body, sig = token.split(".")
        expected = hmac.new(secret, (head + "." + body).encode(), hashlib.sha256).digest()
        if sig and not hmac.compare_digest(_b64d(sig), expected):
            raise ValueError("bad signature")
        return json.loads(_b64d(body))
''')

JW.append(dict(
    slug="unsigned-token", d=1, product="the session service", func="decode", cwe="CWE-347",
    finding="`decode` only checks the signature when the token has one: `header.payload.` (an empty signature part) is accepted as if it were signed, so anyone can mint a token such as `{\"sub\": \"admin\"}` without knowing the secret.",
    start={"minijwt.py": SIGLESS, "README.md": readme("session tokens", "`decode(token, secret)` returns the claims of a token whose HMAC-SHA256 signature is valid for `secret`. Tokens with an empty, missing, truncated or wrong signature, with the wrong number of parts, or with bad encoding raise `ValueError`.")},
    solution={"minijwt.py": patched(SIGLESS, ('        if sig and not hmac.compare_digest(_b64d(sig), expected):\n', '        if not hmac.compare_digest(_b64d(sig), expected):\n'))},
    hidden={"tests/test_minijwt_security.py": JT + dd(r'''
        import minijwt as m

        SECRET = b"s3cret-key"
        HDR = {"alg": "HS256", "typ": "JWT"}


        class JwtTest(unittest.TestCase):
            def test_roundtrip(self):
                claims = {"sub": "ann", "admin": False, "n": [1, 2, {"x": None}], "name": "é中"}
                self.assertEqual(m.decode(m.encode(claims, SECRET), SECRET), claims)
                self.assertEqual(m.decode(forge(HDR, {"sub": "x"}, SECRET), SECRET), {"sub": "x"})

            def test_bad_tokens(self):
                good = m.encode({"sub": "ann"}, SECRET)
                head, body, sig = good.split(".")
                evil = b64(b'{"sub": "admin"}')
                for tok in [forge(HDR, {"sub": "admin"}), head + "." + body + ".", head + "." + body, head + "." + evil + "." + sig, good + "x", good[:-4], forge(HDR, {"sub": "admin"}, b"other"),
                            "..", "", "a.b", head + "." + body + "." + sig + ".extra", head + "." + body + "." + b64(b"\x00" * 32), forge(HDR, {"sub": "admin"}, sig=b"\x00")]:
                    self.assertIsNone(attempt(m.decode, tok, SECRET), tok)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

ALGNONE = '"""Minimal HS256 tokens for the partner API."""\n' + BASE + dd(r'''


    def decode(token, secret):
        """The claims of a valid HS256 token made with `secret`. ValueError for anything else. The algorithm is decided by the server: the token's header has to say `HS256`, exactly."""
        head_b64, body_b64, sig_b64 = token.split(".")
        header = json.loads(_b64d(head_b64))
        if header.get("alg") != "none":
            expected = hmac.new(secret, (head_b64 + "." + body_b64).encode(), hashlib.sha256).digest()
            if not hmac.compare_digest(_b64d(sig_b64), expected):
                raise ValueError("bad signature")
        return json.loads(_b64d(body_b64))
''')

JW.append(dict(
    slug="alg-none", d=2, product="the partner API", func="decode", cwe="CWE-347",
    finding="`decode` lets the token's own header choose the algorithm: `{\"alg\": \"none\"}` skips the signature check completely, so a token with any claims and no signature is accepted (the classic `alg=none` JWT bypass); other `alg` values are quietly treated as HS256.",
    start={"minijwt.py": ALGNONE, "README.md": readme("partner tokens", "`decode(token, secret)` accepts tokens whose header says `alg` = `HS256` (exact, case-sensitive) and whose HMAC-SHA256 signature verifies. A different, missing or `none` algorithm (any spelling) raises `ValueError`, whatever the signature part contains.")},
    solution={"minijwt.py": patched(ALGNONE, (
        '''        if header.get("alg") != "none":
            expected = hmac.new(secret, (head_b64 + "." + body_b64).encode(), hashlib.sha256).digest()
            if not hmac.compare_digest(_b64d(sig_b64), expected):
                raise ValueError("bad signature")
''', '''        if header.get("alg") != "HS256":
            raise ValueError("unsupported algorithm")
        expected = hmac.new(secret, (head_b64 + "." + body_b64).encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64d(sig_b64), expected):
            raise ValueError("bad signature")
'''))},
    hidden={"tests/test_minijwt_security.py": JT + dd(r'''
        import minijwt as m

        SECRET = b"s3cret-key"


        class AlgTest(unittest.TestCase):
            def test_valid(self):
                claims = {"sub": "ann", "scope": ["read", "write"]}
                self.assertEqual(m.decode(m.encode(claims, SECRET), SECRET), claims)
                self.assertEqual(m.decode(forge({"alg": "HS256", "typ": "JWT", "kid": "x"}, claims, SECRET), SECRET), claims)

            def test_algorithm_is_not_negotiable(self):
                claims = {"sub": "admin"}
                for alg in ["none", "None", "NONE", "nOnE", "", None, "HS512", "hs256", "RS256", "HS256 ", ["HS256"]]:
                    header = {"typ": "JWT"} if alg is None else {"alg": alg, "typ": "JWT"}
                    for sig in (b"", b"garbage"):
                        self.assertIsNone(attempt(m.decode, forge(header, claims, sig=sig), SECRET), (alg, sig))
                    self.assertIsNone(attempt(m.decode, forge(header, claims, SECRET), SECRET), alg)
                import hashlib
                self.assertIsNone(attempt(m.decode, forge({"alg": "HS512"}, claims, SECRET, algo=hashlib.sha512), SECRET))
                self.assertIsNone(attempt(m.decode, forge({"typ": "JWT"}, claims, SECRET), SECRET))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

EXPIRY = '"""Minimal HS256 tokens for the mobile API."""\nimport time\n' + BASE + dd(r'''


    def decode(token, secret, now=None):
        """The claims of a valid token. Time claims are in seconds since the epoch (numbers; `now` defaults to the current time): a token with `exp` is expired once `now >= exp`,
        a token with `nbf` is not yet valid while `now < nbf`; both raise ValueError, as does an `exp` or `nbf` that is not a number (bools and strings included). Tokens without
        these claims stay valid. Bad signatures and malformed tokens raise ValueError as well."""
        head, body, sig = token.split(".")
        expected = hmac.new(secret, (head + "." + body).encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64d(sig), expected):
            raise ValueError("bad signature")
        return json.loads(_b64d(body))
''')

JW.append(dict(
    slug="expiry-ignored", d=2, product="the mobile API", func="decode", cwe="CWE-613",
    finding="`decode` verifies the signature but never looks at `exp` or `nbf`, so a token that expired last year (or was stolen from an old backup) is accepted forever, and tokens cannot be revoked by letting them time out.",
    start={"minijwt.py": EXPIRY, "README.md": readme("mobile tokens", "`decode(token, secret, now=None)` enforces `exp` (expired when `now >= exp`) and `nbf` (not valid while `now < nbf`) as described in its docstring; numbers may be ints or floats; anything else in those claims is an error. Tokens without them are fine. `now=None` means the current time.")},
    solution={"minijwt.py": patched(EXPIRY, (
        '        return json.loads(_b64d(body))\n',
        '''        claims = json.loads(_b64d(body))
        now = time.time() if now is None else now
        for name in ("exp", "nbf"):
            if name in claims:
                value = claims[name]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(name + " is not a number")
        if "exp" in claims and now >= claims["exp"]:
            raise ValueError("token expired")
        if "nbf" in claims and now < claims["nbf"]:
            raise ValueError("token not yet valid")
        return claims
'''))},
    hidden={"tests/test_minijwt_security.py": JT + dd(r'''
        import minijwt as m

        SECRET = b"s3cret-key"
        NOW = 1_700_000_000


        class ExpiryTest(unittest.TestCase):
            def test_valid_windows(self):
                for claims in [{"sub": "a"}, {"sub": "a", "exp": NOW + 1}, {"sub": "a", "exp": NOW + 0.5}, {"sub": "a", "nbf": NOW}, {"sub": "a", "nbf": NOW - 100, "exp": NOW + 100}, {"sub": "a", "exp": 4102444800}]:
                    self.assertEqual(m.decode(m.encode(claims, SECRET), SECRET, now=NOW), claims)
                self.assertEqual(m.decode(m.encode({"sub": "a", "exp": 4102444800}, SECRET), SECRET), {"sub": "a", "exp": 4102444800})

            def test_invalid_windows(self):
                for claims in [{"exp": NOW}, {"exp": NOW - 1}, {"exp": 1}, {"exp": NOW - 0.5}, {"nbf": NOW + 1}, {"nbf": NOW + 3600, "exp": NOW + 7200}, {"nbf": NOW - 10, "exp": NOW - 5},
                               {"exp": "9999999999"}, {"exp": True}, {"exp": None}, {"nbf": "0"}, {"exp": [NOW + 100]}, {"nbf": False}]:
                    self.assertIsNone(attempt(m.decode, m.encode(claims, SECRET), SECRET, now=NOW), claims)
                self.assertIsNone(attempt(m.decode, m.encode({"exp": 1}, SECRET), SECRET))
                self.assertIsNone(attempt(m.decode, m.encode({"exp": NOW + 10}, b"x"), SECRET, now=NOW))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

KIDLIB = '"""HS256 tokens with rotating keys stored one per file."""\nimport os\n' + BASE.replace('def encode(claims, secret):\n    """HS256 token for the dict `claims`; `secret` is bytes."""\n    head = _b64e(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())',
                                                                            'def encode(claims, secret, kid=None):\n    """HS256 token for the dict `claims`; `secret` is bytes; `kid` names the key in the header."""\n    header = {"alg": "HS256", "typ": "JWT"}\n    if kid is not None:\n        header["kid"] = kid\n    head = _b64e(json.dumps(header).encode())') + dd(r'''


    def load_key(keydir, kid):
        with open(os.path.join(keydir, kid), "rb") as fh:
            return fh.read().strip()


    def decode(token, keydir):
        """The claims of a valid HS256 token. The signing key is the content of the file `keydir/<kid>` (stripped of surrounding whitespace), where `kid` comes from the token header and defaults to
        `default`. Key ids are plain names of 1 to 64 letters, digits, `_` or `-`. ValueError for bad tokens, unknown or invalid key ids."""
        head, body, sig = token.split(".")
        header = json.loads(_b64d(head))
        key = load_key(keydir, header.get("kid", "default"))
        expected = hmac.new(key, (head + "." + body).encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64d(sig), expected):
            raise ValueError("bad signature")
        return json.loads(_b64d(body))
''')

JW.append(dict(
    slug="kid-traversal", d=3, product="the token service with rotating keys", func="decode", cwe="CWE-22",
    finding="`decode` joins the unchecked `kid` header onto the key directory and reads that file as the HMAC key: `kid: \"../public/robots.txt\"` (or an absolute path, or `/dev/null`) makes the key a file whose content the attacker knows, so any token can be forged and arbitrary readable files are opened.",
    start={"minijwt.py": KIDLIB, "README.md": readme("rotating keys", "`decode(token, keydir)` looks the key up by `kid` (default `default`) in `keydir`; `kid` must match `[A-Za-z0-9_-]{1,64}` and name a file inside `keydir`, otherwise `ValueError` (unknown ids too). `encode(claims, secret, kid=None)` is a helper that writes the `kid` header.")},
    solution={"minijwt.py": patched(KIDLIB, ('"""HS256 tokens with rotating keys stored one per file."""\nimport os\n', '"""HS256 tokens with rotating keys stored one per file."""\nimport os\nimport re\n'), (
        '''def load_key(keydir, kid):
    with open(os.path.join(keydir, kid), "rb") as fh:
        return fh.read().strip()
''', '''def load_key(keydir, kid):
    if not isinstance(kid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", kid):
        raise ValueError("invalid key id")
    try:
        with open(os.path.join(keydir, kid), "rb") as fh:
            return fh.read().strip()
    except OSError:
        raise ValueError("unknown key id")
'''))},
    hidden={"tests/test_minijwt_security.py": JT + dd(r'''
        import minijwt as m


        class KidTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.addCleanup(shutil.rmtree, self.root, True)
                self.keys = os.path.join(self.root, "keys")
                write(os.path.join(self.keys, "default"), "default-key-material\n")
                write(os.path.join(self.keys, "k2"), b"second key")
                write(os.path.join(self.keys, "key-2024_01"), "rotated-2024")
                write(os.path.join(self.root, "public", "robots.txt"), "User-agent: *\n")
                write(os.path.join(self.root, "known.txt"), "known")
                self.known = {"../public/robots.txt": b"User-agent: *", "../known.txt": b"known", os.path.join(self.root, "known.txt"): b"known",
                              "./../known.txt": b"known", "k2/../../known.txt": b"known", "/dev/null": b"", os.path.join(self.root, "public", "robots.txt"): b"User-agent: *"}

            def test_legit_keys(self):
                claims = {"sub": "ann"}
                self.assertEqual(m.decode(m.encode(claims, b"default-key-material"), self.keys), claims)
                self.assertEqual(m.decode(m.encode(claims, b"default-key-material", "default"), self.keys), claims)
                self.assertEqual(m.decode(m.encode(claims, b"second key", "k2"), self.keys), claims)
                self.assertEqual(m.decode(m.encode(claims, b"rotated-2024", "key-2024_01"), self.keys), claims)
                for bad in (m.encode(claims, b"wrong", "k2"), m.encode(claims, b"second key", "k3"), m.encode(claims, b"second key", "K2")):
                    self.assertIsNone(attempt(m.decode, bad, self.keys))

            def test_kid_cannot_leave_the_key_directory(self):
                claims = {"sub": "admin"}
                for kid, content in self.known.items():
                    token = forge({"alg": "HS256", "kid": kid}, claims, content)
                    self.assertIsNone(attempt(m.decode, token, self.keys), kid)
                for kid in ["", ".", "..", "k2\x00", "a/b", "k2/", "x" * 65, 5, None, ["k2"], "k 2"]:
                    token = forge({"alg": "HS256", "kid": kid}, claims, b"second key")
                    self.assertIsNone(attempt(m.decode, token, self.keys), repr(kid))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

AUDLIB = '"""HS256 tokens shared by several internal services."""\n' + BASE + dd(r'''


    def decode(token, secret, audience, issuer):
        """The claims of a valid token meant for this service. Besides a valid HMAC-SHA256 signature, the token must have `iss` equal to `issuer` and `aud` equal to `audience`
        (or a list of audiences that contains it); a missing or different `iss`/`aud` raises ValueError, like every other problem."""
        head, body, sig = token.split(".")
        expected = hmac.new(secret, (head + "." + body).encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64d(sig), expected):
            raise ValueError("bad signature")
        return json.loads(_b64d(body))
''')

JW.append(dict(
    slug="audience-issuer", d=3, product="the internal services", func="decode", cwe="CWE-345",
    finding="`decode` checks the signature only: the services share one signing secret, so a valid token issued by the *login* service for the *search* service (or for another tenant's issuer) is accepted by the billing API as well; a token meant for a low-privilege audience can be replayed against a high-privilege one.",
    start={"minijwt.py": AUDLIB, "README.md": readme("service tokens", "`decode(token, secret, audience, issuer)` additionally requires `iss == issuer` and `aud == audience` or `audience in aud` when `aud` is a list; missing claims, other types (numbers, dicts) and look-alike values fail with `ValueError`.")},
    solution={"minijwt.py": patched(AUDLIB, (
        '        return json.loads(_b64d(body))\n',
        '''        claims = json.loads(_b64d(body))
        aud = claims.get("aud")
        if claims.get("iss") != issuer or not isinstance(claims.get("iss"), str):
            raise ValueError("wrong issuer")
        if not ((isinstance(aud, str) and aud == audience) or (isinstance(aud, list) and any(isinstance(a, str) and a == audience for a in aud))):
            raise ValueError("wrong audience")
        return claims
'''))},
    hidden={"tests/test_minijwt_security.py": JT + dd(r'''
        import minijwt as m

        SECRET = b"shared-secret"


        class AudTest(unittest.TestCase):
            def test_accepted(self):
                for aud in ["billing", ["billing"], ["search", "billing", "mail"]]:
                    claims = {"sub": "ann", "iss": "https://login.example", "aud": aud}
                    self.assertEqual(m.decode(m.encode(claims, SECRET), SECRET, "billing", "https://login.example"), claims)

            def test_rejected(self):
                for claims in [{"iss": "https://login.example", "aud": "search"}, {"iss": "https://login.example", "aud": ["search", "mail"]}, {"iss": "https://login.example"},
                               {"aud": "billing"}, {"iss": "https://other.example", "aud": "billing"}, {"iss": "https://login.example", "aud": "Billing"}, {"iss": "https://login.example", "aud": "billing2"},
                               {"iss": "https://login.example", "aud": 5}, {"iss": "https://login.example", "aud": {"billing": True}}, {"iss": "https://login.example", "aud": []},
                               {"iss": "https://login.example/", "aud": "billing"}, {"iss": ["https://login.example"], "aud": "billing"}, {"iss": None, "aud": None}, {"iss": "https://login.example", "aud": None}]:
                    self.assertIsNone(attempt(m.decode, m.encode(claims, SECRET), SECRET, "billing", "https://login.example"), claims)
                good = {"iss": "https://login.example", "aud": "billing"}
                self.assertIsNone(attempt(m.decode, m.encode(good, b"other"), SECRET, "billing", "https://login.example"))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

RSA_N = "0xebc57d3c6e5fc76b9a91b82e3b6977243d2bccb80579cc443b6ca019b8b11bf2d5c710b0a89856e3ae93b6db03226641608aadfd13f9f489018ec4428964957dd67565a09ad26088f7a6442b4fd8373d25801478c412aa8955e77a99ed8725ba81425469201a367f0da58835a63d8d521ca2fa09597cc5f74b38cdd07024d6db"
RSA_D = "0x99cd3ae5311b49fbe7d9274d0174cb43d8a3b9e851aa2296602d7c434b383e032b71b0718d89d324b3bda88b36803a346bc60bba0c4e02375dccc43aa365fa1ddc3fa2c077ddbb4fc3fcab8b354d952efceaa8d4d0b5c05c8f812e3ce13b781f837897a5f13fa401eaec5972c7275e46ac6369c8ae542f9d648a5a1aef936001"

CONFUSE = dd(r'''
    """Token verification of the API gateway: RS256 tokens, plus a legacy HS256 path."""
    import base64
    import hashlib
    import hmac
    import json


    def _b64d(text):
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


    def _pad(digest, size):
        """Deterministic signature padding: 00 01 FF..FF 00 <sha256 digest>, `size` bytes long, as an integer."""
        return int.from_bytes(b"\x00\x01" + b"\xff" * (size - len(digest) - 3) + b"\x00" + digest, "big")


    def verify_rs256(public_key, signing_input, signature):
        """Textbook RSA signature check (a toy implementation, good enough for this gateway). `public_key` is bytes like `RSA-PUBLIC n=<hex> e=<hex>`."""
        fields = dict(part.split("=") for part in public_key.decode().split()[1:])
        n, e = int(fields["n"], 16), int(fields["e"], 16)
        size = (n.bit_length() + 7) // 8
        if len(signature) != size:
            return False
        return pow(int.from_bytes(signature, "big"), e, n) == _pad(hashlib.sha256(signing_input).digest(), size)


    def verify(token, public_key):
        """The claims of a token signed with the gateway's private key (RS256). ValueError for anything else. Which algorithm applies is the gateway's decision, not the token's."""
        head, body, sig = token.split(".")
        header = json.loads(_b64d(head))
        signing_input = (head + "." + body).encode()
        signature = _b64d(sig)
        alg = header.get("alg")
        if alg == "RS256":
            ok = verify_rs256(public_key, signing_input, signature)
        elif alg == "HS256":
            # legacy clients: the shared secret is the (public) key text
            ok = hmac.compare_digest(hmac.new(public_key, signing_input, hashlib.sha256).digest(), signature)
        else:
            raise ValueError("unsupported algorithm")
        if not ok:
            raise ValueError("bad signature")
        return json.loads(_b64d(body))
''')

JW.append(dict(
    slug="algorithm-confusion", d=4, product="the API gateway", func="verify", cwe="CWE-327",
    finding="`verify` picks the verification method from the token's `alg` header and keeps a legacy `HS256` branch that uses the gateway's *public key* as the HMAC secret; the public key is public, so an attacker signs `{\"role\": \"admin\"}` with HS256 using that key text and the gateway accepts it (key/algorithm confusion).",
    start={"gateway.py": CONFUSE, "README.md": readme("gateway tokens", "`verify(token, public_key)` accepts RS256 tokens signed with the matching private key and nothing else: the algorithm is fixed by the gateway (header `alg` must be `RS256`), the legacy HS256 path is removed, and `none` or other algorithms raise `ValueError`. `verify_rs256` keeps working as it is, including for malformed signatures (wrong length gives False).")},
    solution={"gateway.py": patched(CONFUSE, (
        '''    alg = header.get("alg")
    if alg == "RS256":
        ok = verify_rs256(public_key, signing_input, signature)
    elif alg == "HS256":
        # legacy clients: the shared secret is the (public) key text
        ok = hmac.compare_digest(hmac.new(public_key, signing_input, hashlib.sha256).digest(), signature)
    else:
        raise ValueError("unsupported algorithm")
''', '''    if header.get("alg") != "RS256":
        raise ValueError("unsupported algorithm")
    ok = verify_rs256(public_key, signing_input, signature)
'''))},
    hidden={"tests/test_gateway_security.py": JT + dd(r'''
        import gateway as m

        N = int("RSA_N_HEX", 16)
        D = int("RSA_D_HEX", 16)
        PUBLIC = b"RSA-PUBLIC n=%x e=%x" % (N, 65537)
        SIZE = 128


        def rs_sign(signing_input):
            digest = hashlib.sha256(signing_input).digest()
            padded = int.from_bytes(b"\x00\x01" + b"\xff" * (SIZE - len(digest) - 3) + b"\x00" + digest, "big")
            return pow(padded, D, N).to_bytes(SIZE, "big")


        def rs_token(claims, header=None):
            h = b64(json.dumps(header or {"alg": "RS256", "typ": "JWT"}).encode())
            p = b64(json.dumps(claims).encode())
            return h + "." + p + "." + b64(rs_sign((h + "." + p).encode()))


        class GatewayTest(unittest.TestCase):
            def test_rs256(self):
                claims = {"sub": "ann", "role": "user"}
                self.assertEqual(m.verify(rs_token(claims), PUBLIC), claims)
                good = rs_token(claims)
                head, body, sig = good.split(".")
                self.assertIsNone(attempt(m.verify, head + "." + b64(b'{"sub": "ann", "role": "admin"}') + "." + sig, PUBLIC))
                self.assertIsNone(attempt(m.verify, head + "." + body + "." + b64(b"\x01" * SIZE), PUBLIC))
                self.assertIsNone(attempt(m.verify, head + "." + body + "." + b64(b"short"), PUBLIC))
                self.assertIsNone(attempt(m.verify, head + "." + body + ".", PUBLIC))
                self.assertIs(m.verify_rs256(PUBLIC, b"abc", rs_sign(b"abc")), True)
                self.assertIs(m.verify_rs256(PUBLIC, b"abd", rs_sign(b"abc")), False)
                self.assertIs(m.verify_rs256(PUBLIC, b"abc", b"x"), False)

            def test_confusion_and_none(self):
                claims = {"sub": "mallory", "role": "admin"}
                for header, secret in [({"alg": "HS256", "typ": "JWT"}, PUBLIC), ({"alg": "HS256"}, PUBLIC.strip()), ({"alg": "HS256"}, PUBLIC + b"\n"), ({"alg": "HS256"}, b"RSA-PUBLIC n=%X e=%X" % (N, 65537))]:
                    self.assertIsNone(attempt(m.verify, forge(header, claims, secret), PUBLIC), header)
                for alg in ["none", "None", "HS512", "", "rs256", "RS256 ", None]:
                    header = {"typ": "JWT"} if alg is None else {"alg": alg}
                    self.assertIsNone(attempt(m.verify, forge(header, claims, sig=b""), PUBLIC), alg)
                    self.assertIsNone(attempt(m.verify, rs_token(claims, header), PUBLIC), alg)


        if __name__ == "__main__":
            unittest.main()
    '''.replace("RSA_N_HEX", RSA_N).replace("RSA_D_HEX", RSA_D))},
))

JW_ORDER = ["unsigned-token", "alg-none", "expiry-ignored", "kid-traversal", "audience-issuer", "algorithm-confusion"]
JW.sort(key=lambda s: (s["d"], JW_ORDER.index(s["slug"])))


@family("security-jwt", category="security", lang="python", kind="fix", n=6,
        summary="token verification: missing signatures, alg=none, expiry, key-id traversal, audience/issuer, algorithm confusion")
def gen_jwt(rng, n):
    return list(_sec.emit(rng, JW[:n], tags=["jwt", "tokens"]))


# =================================================================================================================================
#  passwords
# =================================================================================================================================
PW = []

PLAIN = dd(r'''
    """User accounts of the forum. `users` is what gets written to the database."""


    class UserStore:
        def __init__(self):
            self.users = {}

        def register(self, name, password):
            """Create an account. ValueError when the name is taken or the password is empty."""
            if name in self.users or not password:
                raise ValueError("cannot register %r" % name)
            self.users[name] = password

        def check(self, name, password):
            """True for a known user with the right password; False otherwise (also for unknown users)."""
            return name in self.users and self.users[name] == password
''')

PW.append(dict(
    slug="plaintext-passwords", d=1, product="the forum", func="UserStore.register", cwe="CWE-256",
    finding="`register` stores the password itself in `users`: every database dump, backup or debug log of that table hands out working credentials (which users reuse elsewhere).",
    start={"accounts.py": PLAIN, "README.md": readme("forum accounts", "`users[name]` is the stored record of an account. It must never contain the password or anything computed from it without a per-user random salt and a slow key-derivation function (PBKDF2-HMAC-SHA256 with at least 100000 iterations, say); two accounts with the same password have different records. `register` and `check` behave as documented; passwords of any length and any characters (non-ASCII, very long) work.")},
    solution={"accounts.py": patched(PLAIN, (
        '"""User accounts of the forum. `users` is what gets written to the database."""\n',
        '"""User accounts of the forum. `users` is what gets written to the database."""\nimport hashlib\nimport hmac\nimport os\n\nITERATIONS = 200_000\n\n\ndef _hash(password, salt):\n    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)\n'), (
        '            self.users[name] = password\n',
        '            salt = os.urandom(16)\n            self.users[name] = "pbkdf2_sha256$%d$%s$%s" % (ITERATIONS, salt.hex(), _hash(password, salt).hex())\n'), (
        '            return name in self.users and self.users[name] == password\n',
        '''            record = self.users.get(name)
            if record is None:
                return False
            _, iterations, salt, digest = record.split("$")
            candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
            return hmac.compare_digest(candidate.hex(), digest)
'''))},
    hidden={"tests/test_accounts_security.py": P + dd(r'''
        import base64
        import hashlib
        import json

        import accounts as m


        class AccountTest(unittest.TestCase):
            def test_behaviour(self):
                s = m.UserStore()
                s.register("ann", "correct horse")
                s.register("bob", "pässwörd 中" * 50)
                self.assertTrue(s.check("ann", "correct horse"))
                self.assertTrue(s.check("bob", "pässwörd 中" * 50))
                self.assertFalse(s.check("ann", "wrong"))
                self.assertFalse(s.check("ann", ""))
                self.assertFalse(s.check("nobody", "correct horse"))
                self.assertFalse(s.check("ann", "correct horsf"))
                self.assertIsNone(attempt(s.register, "ann", "again"))
                self.assertIsNone(attempt(s.register, "eve", ""))
                self.assertTrue(s.check("ann", "correct horse"))

            def test_records_do_not_contain_the_password(self):
                s = m.UserStore()
                pw = "Tr0ub4dor&3-horse"
                s.register("ann", pw)
                s.register("bob", pw)
                dump = json.dumps(s.users, default=repr)
                self.assertNotIn(pw, dump)
                for algo in (hashlib.md5, hashlib.sha1, hashlib.sha256, hashlib.sha512):
                    digest = algo(pw.encode()).digest()
                    self.assertNotIn(digest.hex(), dump.lower())
                    self.assertNotIn(base64.b64encode(digest).decode(), dump)
                self.assertNotEqual(s.users["ann"], s.users["bob"])
                self.assertNotIn(base64.b64encode(pw.encode()).decode(), dump)
                self.assertTrue(s.check("ann", pw) and s.check("bob", pw))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

POLICY = dd(r'''
    """Password policy of the sign-up form."""

    COMMON = {"password", "123456", "12345678", "qwerty", "letmein", "welcome", "iloveyou", "admin", "abc123", "password1", "password1234", "qwertyuiop12", "iloveyou1234", "correcthorse",
              "welcome12345", "letmein12345"}


    def validate_password(password, username):
        """The list of problems of a candidate password (empty when it is acceptable). Possible entries: "too short" (fewer than 12 characters), "too long" (more than 128), "too common" (in COMMON,
        compared case-insensitively), "contains username" (contains the user name, case-insensitive; only for user names of 3+ characters). Listed in that order. No other rules:
        spaces and long passphrases are welcome, there are no character-class requirements."""
        problems = []
        if len(password) < 8:
            problems.append("too short")
        return problems
''')

PW.append(dict(
    slug="weak-policy", d=1, product="the sign-up form", func="validate_password", cwe="CWE-521",
    finding="`validate_password` only requires 8 characters: `password1`, `12345678` and the user's own name pass, there is no upper bound (a 10 MB password is a cheap denial of service against the hash function) and common passwords are not rejected, so accounts are trivially guessable.",
    start={"policy.py": POLICY, "README.md": readme("password policy", "`validate_password(password, username)` returns the list of problems described in its docstring, in the order \"too short\", \"too long\", \"too common\", \"contains username\". An acceptable password gives `[]`; a passphrase like `correct horse battery staple` is fine, `Password123!` is too short but not common, and `PASSWORD1234` is too common.")},
    solution={"policy.py": patched(POLICY, (
        '''    if len(password) < 8:
        problems.append("too short")
    return problems
''', '''    if len(password) < 12:
        problems.append("too short")
    if len(password) > 128:
        problems.append("too long")
    if password.lower() in COMMON:
        problems.append("too common")
    if len(username) >= 3 and username.lower() in password.lower():
        problems.append("contains username")
    return problems
'''))},
    hidden={"tests/test_policy_security.py": P + dd(r'''
        import policy as m


        class PolicyTest(unittest.TestCase):
            def test_table(self):
                cases = [
                    ("correct horse battery staple", "ann", []),
                    ("Tr0ub4dor&3xx", "ann", []),
                    ("a" * 12, "bob", []),
                    ("x" * 128, "bob", []),
                    ("x" * 129, "bob", ["too long"]),
                    ("short1!", "ann", ["too short"]),
                    ("Pass123!", "ann", ["too short"]),
                    ("12345678", "ann", ["too short", "too common"]),
                    ("password", "ann", ["too short", "too common"]),
                    ("PASSWORD1234", "ann", ["too common"]),
                    ("Qwertyuiop12", "ann", ["too common"]),
                    ("annabelle-is-great", "Ann", ["contains username"]),
                    ("my password is Bobby123", "bobby", ["contains username"]),
                    ("ann-is-fine-here", "an", []),
                    ("ilovebobbytables", "bob", ["contains username"]),
                    ("Welcome12345", "ann", ["too common"]),
                    ("", "ann", ["too short"]),
                    ("correctHorse12", "ann", []),
                ]
                for password, username, expected in cases:
                    self.assertEqual(m.validate_password(password, username), expected, (password, username))

            def test_common_entries_are_rejected(self):
                for word in sorted(m.COMMON):
                    problems = m.validate_password(word.upper(), "someone")
                    self.assertIn("too common", problems, word)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

ENUM = dd(r'''
    """Login and password reset of the shop (in-process model)."""
    import hashlib
    import hmac
    import os


    def hash_pw(password, salt):
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 2000).hex()


    class Accounts:
        def __init__(self):
            self.users = {}
            self.outbox = []

        def add(self, name, password, email):
            salt = os.urandom(16)
            self.users[name] = {"salt": salt, "hash": hash_pw(password, salt), "email": email}

        def login(self, name, password):
            """(status, body). Success: `(200, {"ok": True, "user": name})`. Every failure - unknown user or wrong password - answers exactly `(401, {"error": "invalid credentials"})`."""
            user = self.users.get(name)
            if user is None:
                return 404, {"error": "no such user"}
            if not hmac.compare_digest(hash_pw(password, user["salt"]), user["hash"]):
                return 401, {"error": "wrong password"}
            return 200, {"ok": True, "user": name}

        def request_reset(self, email):
            """Start a password reset for the account with this address. The answer is always `(202, {"message": "if the address is registered, a mail is on its way"})`;
            a mail (an entry `(email, "Reset your password")` in `self.outbox`) is only queued when the address belongs to an account."""
            for user in self.users.values():
                if user["email"] == email:
                    self.outbox.append((email, "Reset your password"))
                    return 200, {"message": "reset mail sent"}
            return 404, {"error": "unknown address"}
''')

PW.append(dict(
    slug="account-enumeration", d=2, product="the shop login", func="Accounts.login", cwe="CWE-204",
    finding="Login answers `404 no such user` for unknown names and `401 wrong password` for known ones, and the reset form answers differently for registered and unknown addresses, so anyone can test which users and e-mail addresses have accounts (account enumeration), the first step of credential stuffing and targeted phishing.",
    start={"shop_auth.py": ENUM, "README.md": readme("shop accounts", "`login` and `request_reset` follow their docstrings: failures are indistinguishable (same status, same body), `request_reset` always answers 202 with the same message and queues a mail only for registered addresses. Successful logins answer `(200, {\"ok\": True, \"user\": name})`.")},
    solution={"shop_auth.py": patched(ENUM, (
        '            return 404, {"error": "no such user"}\n', '            return 401, {"error": "invalid credentials"}\n'), (
        '            return 401, {"error": "wrong password"}\n', '            return 401, {"error": "invalid credentials"}\n'), (
        '''                    self.outbox.append((email, "Reset your password"))
                    return 200, {"message": "reset mail sent"}
            return 404, {"error": "unknown address"}
''', '''                    self.outbox.append((email, "Reset your password"))
                    break
            return 202, {"message": "if the address is registered, a mail is on its way"}
'''))},
    hidden={"tests/test_shop_auth_security.py": P + dd(r'''
        import shop_auth as m


        class ShopTest(unittest.TestCase):
            def setUp(self):
                self.a = m.Accounts()
                self.a.add("ann", "correct horse", "ann@example.com")

            def test_login(self):
                self.assertEqual(self.a.login("ann", "correct horse"), (200, {"ok": True, "user": "ann"}))
                wrong = self.a.login("ann", "nope")
                unknown = self.a.login("mallory", "nope")
                empty = self.a.login("", "")
                self.assertEqual(wrong, (401, {"error": "invalid credentials"}))
                self.assertEqual(unknown, wrong)
                self.assertEqual(empty, wrong)

            def test_reset(self):
                known = self.a.request_reset("ann@example.com")
                unknown = self.a.request_reset("nobody@example.com")
                self.assertEqual(known, unknown)
                self.assertEqual(known[0], 202)
                self.assertEqual(known[1], {"message": "if the address is registered, a mail is on its way"})
                self.assertEqual(self.a.outbox, [("ann@example.com", "Reset your password")])
                self.assertEqual(self.a.request_reset("")[0], 202)
                self.assertEqual(len(self.a.outbox), 1)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

TRUNC = dd(r'''
    """Password hashing for the customer portal."""
    import hashlib
    import hmac
    import os

    ITERATIONS = 100_000


    def hash_password(password):
        """`pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>` for the password (any length and characters), with a fresh random salt."""
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password[:8].encode("utf-8"), salt, ITERATIONS)
        return "pbkdf2_sha256$%d$%s$%s" % (ITERATIONS, salt.hex(), digest.hex())


    def verify_password(stored, password):
        """True when `password` is the one `stored` was made from (every character counts); False for anything else, including malformed records."""
        try:
            _, iterations, salt, digest = stored.split("$")
            candidate = hashlib.pbkdf2_hmac("sha256", password[:8].encode("utf-8"), bytes.fromhex(salt), int(iterations))
        except ValueError:
            return False
        return hmac.compare_digest(candidate.hex(), digest)
''')

PW.append(dict(
    slug="password-truncation", d=2, product="the customer portal", func="hash_password", cwe="CWE-521",
    finding="`hash_password` and `verify_password` cut the password to its first 8 characters (a leftover from the old crypt(3) limit), so `correct horse battery staple` and `correct ` are the same password: long passphrases protect nothing beyond 8 characters and anyone who guesses the prefix gets in.",
    start={"hashing.py": TRUNC, "README.md": readme("password hashing", "Every character of the password takes part in the hash (any length up to several thousand characters, any Unicode); records keep the format `pbkdf2_sha256$iterations$salt$hash`. `verify_password` is False for malformed records and for passwords that differ anywhere.")},
    solution={"hashing.py": patched(TRUNC, ('password[:8].encode', 'password.encode'))},
    hidden={"tests/test_hashing_security.py": P + dd(r'''
        import hashing as m


        class HashingTest(unittest.TestCase):
            def test_roundtrip(self):
                for pw in ["", "a", "correct horse battery staple", "pässö中" * 100, "x" * 5000]:
                    stored = m.hash_password(pw)
                    self.assertTrue(stored.startswith("pbkdf2_sha256$"))
                    self.assertTrue(m.verify_password(stored, pw), pw[:10])
                self.assertNotEqual(m.hash_password("same"), m.hash_password("same"))

            def test_every_character_counts(self):
                stored = m.hash_password("correct horse battery staple")
                for other in ["correct ", "correct h", "correct horse battery stapl", "correct horse battery staplf", "correct horse battery staple ", "Correct horse battery staple", "correct horse"]:
                    self.assertFalse(m.verify_password(stored, other), other)
                self.assertFalse(m.verify_password(m.hash_password("12345678"), "12345678x"))
                self.assertFalse(m.verify_password(m.hash_password("a" * 40), "a" * 41))
                for bad in ["", "plain", "pbkdf2_sha256$x$y$z", "a$b$c", "pbkdf2_sha256$1$zz$00"]:
                    self.assertFalse(m.verify_password(bad, "x"))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

MD5 = dd(r'''
    """Password storage of the intranet."""
    import hashlib


    def hash_password(password):
        """The record to store for a new password."""
        return hashlib.md5(password.encode("utf-8")).hexdigest()


    def verify_password(stored, password):
        """True when `password` matches the stored record."""
        return hash_password(password) == stored


    def needs_rehash(stored):
        """True when a record should be replaced by a fresh `hash_password(...)` the next time the user logs in."""
        return False
''')

PW.append(dict(
    slug="legacy-md5", d=3, product="the intranet", func="hash_password", cwe="CWE-916",
    finding="`hash_password` is a bare, unsalted MD5: a leaked table is cracked at billions of guesses per second with rainbow tables, and equal passwords are visible as equal hashes. The existing users' records are MD5 hex strings, so the fix must migrate without locking them out.",
    start={"passwords.py": MD5, "README.md": readme("password storage", "New records are `pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>`: PBKDF2-HMAC-SHA256 with a fresh 16-byte random salt and `ITERATIONS` (at least 200000, define the constant in the module). `verify_password` still accepts the legacy 32-character MD5 hex records of existing users (and PBKDF2 records with any iteration count) so nobody is locked out; `needs_rehash(stored)` is True for legacy MD5 records and for PBKDF2 records with fewer than `ITERATIONS` iterations, False for current ones. Comparisons are constant-time, malformed records verify as False.")},
    solution={"passwords.py": dd(r'''
        """Password storage of the intranet."""
        import hashlib
        import hmac
        import os

        ITERATIONS = 200_000


        def hash_password(password):
            """The record to store for a new password."""
            salt = os.urandom(16)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
            return "pbkdf2_sha256$%d$%s$%s" % (ITERATIONS, salt.hex(), digest.hex())


        def _legacy(stored):
            return len(stored) == 32 and all(c in "0123456789abcdef" for c in stored)


        def verify_password(stored, password):
            """True when `password` matches the stored record."""
            if not isinstance(stored, str):
                return False
            if _legacy(stored):
                return hmac.compare_digest(hashlib.md5(password.encode("utf-8")).hexdigest(), stored)
            try:
                _, iterations, salt, digest = stored.split("$")
                candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
            except ValueError:
                return False
            return hmac.compare_digest(candidate.hex(), digest)


        def needs_rehash(stored):
            """True when a record should be replaced by a fresh `hash_password(...)` the next time the user logs in."""
            if _legacy(stored):
                return True
            try:
                return int(stored.split("$")[1]) < ITERATIONS
            except (ValueError, IndexError):
                return True
    ''')},
    hidden={"tests/test_passwords_security.py": P + dd(r'''
        import hashlib

        import passwords as m


        class PasswordTest(unittest.TestCase):
            def test_new_records(self):
                rec = m.hash_password("correct horse")
                scheme, iterations, salt, digest = rec.split("$")
                self.assertEqual(scheme, "pbkdf2_sha256")
                self.assertGreaterEqual(int(iterations), 200000)
                self.assertGreaterEqual(m.ITERATIONS, 200000)
                self.assertEqual(len(bytes.fromhex(salt)), 16)
                self.assertEqual(hashlib.pbkdf2_hmac("sha256", b"correct horse", bytes.fromhex(salt), int(iterations)).hex(), digest)
                self.assertNotEqual(rec, m.hash_password("correct horse"))
                self.assertNotIn(hashlib.md5(b"correct horse").hexdigest(), rec)
                self.assertTrue(m.verify_password(rec, "correct horse"))
                self.assertFalse(m.verify_password(rec, "correct horsf"))
                self.assertFalse(m.needs_rehash(rec))

            def test_legacy_and_low_iteration_records(self):
                legacy = hashlib.md5("hunter2".encode()).hexdigest()
                self.assertTrue(m.verify_password(legacy, "hunter2"))
                self.assertFalse(m.verify_password(legacy, "hunter3"))
                self.assertTrue(m.needs_rehash(legacy))
                salt = b"0123456789abcdef"
                low = "pbkdf2_sha256$1000$%s$%s" % (salt.hex(), hashlib.pbkdf2_hmac("sha256", b"old pw", salt, 1000).hex())
                self.assertTrue(m.verify_password(low, "old pw"))
                self.assertFalse(m.verify_password(low, "new pw"))
                self.assertTrue(m.needs_rehash(low))

            def test_malformed(self):
                for bad in ["", "x", "pbkdf2_sha256$a$b$c", "pbkdf2_sha256$1000$zz$00", "$$$", "a" * 32 + "$", "g" * 32, None]:
                    self.assertFalse(m.verify_password(bad, "x"), bad)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

RESETSTORE = dd(r'''
    """Password-reset tokens (in-process model). `rows` is what the database stores."""
    import secrets

    TTL = 3600


    class ResetService:
        def __init__(self):
            self.rows = {}

        def issue(self, user, now):
            """A new single-use reset token for `user`, valid for TTL seconds from `now`."""
            token = secrets.token_urlsafe(24)
            self.rows[token] = {"user": user, "expires": now + TTL}
            return token

        def redeem(self, token, now):
            """The user the token belongs to, once: the token is consumed. ValueError for unknown, used or expired tokens. The database never stores the token itself, only something
            that cannot be turned back into it (a leaked table must not contain working reset links)."""
            row = self.rows.pop(token, None)
            if row is None or now >= row["expires"]:
                raise ValueError("invalid reset token")
            return row["user"]
''')

PW.append(dict(
    slug="reset-token-storage", d=3, product="the password reset service", func="ResetService.issue", cwe="CWE-312",
    finding="`issue` stores the reset token itself as the primary key of the `rows` table: anyone who can read the table (a SQL injection, a backup, a replica) can open every pending reset link and take over those accounts without touching a password.",
    start={"resets.py": RESETSTORE, "README.md": readme("password resets", "`issue(user, now)` returns the token for the e-mail; `rows` (the stored data) must contain neither the token nor any simple encoding of it - store a SHA-256 digest of the token instead and look it up by digest on `redeem`. Behaviour is unchanged: single use, `TTL` seconds validity (expired when `now >= expires`), `ValueError` for anything unknown, used or expired, and tokens of at least 128 bits from a secure source.")},
    solution={"resets.py": patched(RESETSTORE, (
        'import secrets\n', 'import hashlib\nimport secrets\n'), (
        '            self.rows[token] = {"user": user, "expires": now + TTL}\n',
        '            self.rows[hashlib.sha256(token.encode()).hexdigest()] = {"user": user, "expires": now + TTL}\n'), (
        '            row = self.rows.pop(token, None)\n',
        '            row = self.rows.pop(hashlib.sha256(str(token).encode()).hexdigest(), None)\n'))},
    hidden={"tests/test_resets_security.py": P + dd(r'''
        import base64
        import json

        import resets as m

        NOW = 1_700_000_000


        class ResetTest(unittest.TestCase):
            def test_flow(self):
                s = m.ResetService()
                t1, t2 = s.issue("ann", NOW), s.issue("bob", NOW)
                self.assertNotEqual(t1, t2)
                self.assertGreaterEqual(len(t1), 22)
                self.assertEqual(s.redeem(t1, NOW + 10), "ann")
                self.assertIsNone(attempt(s.redeem, t1, NOW + 11))
                self.assertEqual(s.redeem(t2, NOW + m.TTL - 1), "bob")
                t3 = s.issue("carol", NOW)
                self.assertIsNone(attempt(s.redeem, t3, NOW + m.TTL))
                self.assertIsNone(attempt(s.redeem, "unknown", NOW))
                self.assertIsNone(attempt(s.redeem, "", NOW))
                self.assertIsNone(attempt(s.redeem, None, NOW))

            def test_table_does_not_hold_tokens(self):
                s = m.ResetService()
                tokens = [s.issue("u%d" % i, NOW) for i in range(5)]
                dump = json.dumps(s.rows, default=repr)
                for t in tokens:
                    self.assertNotIn(t, dump)
                    self.assertNotIn(t[::-1], dump)
                    self.assertNotIn(base64.b64encode(t.encode()).decode(), dump)
                    self.assertNotIn(t.encode().hex(), dump)
                self.assertEqual(len(s.rows), 5)
                self.assertEqual(s.redeem(tokens[3], NOW + 1), "u3")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

PW_ORDER = ["plaintext-passwords", "weak-policy", "account-enumeration", "password-truncation", "legacy-md5", "reset-token-storage"]
PW.sort(key=lambda s: (s["d"], PW_ORDER.index(s["slug"])))


@family("security-passwords", category="security", lang="python", kind="fix", n=6,
        summary="password handling: plaintext and MD5 storage, truncation, policy, enumeration, reset-token storage")
def gen_passwords(rng, n):
    return list(_sec.emit(rng, PW[:n], tags=["passwords"]))


# =================================================================================================================================
#  sessions
# =================================================================================================================================
SE = []

COOKIEFLAGS = dd(r'''
    """Session cookie of the web shop."""


    def session_cookie(sid, remember=False):
        """The `Set-Cookie` header value for the session id: `sid=<id>; Path=/; HttpOnly; Secure; SameSite=Lax`, followed by `; Max-Age=2592000` (30 days) when `remember` is true,
        so the cookie is hidden from scripts, never sent over plain HTTP and not sent on cross-site sub-requests."""
        return "sid=%s; Path=/" % sid + ("; Max-Age=2592000" if remember else "")
''')

SE.append(dict(
    slug="cookie-flags", d=1, product="the web shop", func="session_cookie", cwe="CWE-1004",
    finding="`session_cookie` sets the session cookie without `HttpOnly`, `Secure` or `SameSite`: any script injected into a page can read it (`document.cookie`), it travels over plain HTTP where it can be sniffed, and it accompanies cross-site requests.",
    start={"cookie.py": COOKIEFLAGS, "README.md": readme("session cookie", "`session_cookie(sid, remember=False)` returns exactly `sid=<id>; Path=/; HttpOnly; Secure; SameSite=Lax` and appends `; Max-Age=2592000` when `remember` is true (attribute order as written).")},
    solution={"cookie.py": patched(COOKIEFLAGS, ('    return "sid=%s; Path=/" % sid +', '    return "sid=%s; Path=/; HttpOnly; Secure; SameSite=Lax" % sid +'))},
    hidden={"tests/test_cookie_security.py": P + dd(r'''
        import cookie as m


        class CookieTest(unittest.TestCase):
            def test_header(self):
                self.assertEqual(m.session_cookie("abc123"), "sid=abc123; Path=/; HttpOnly; Secure; SameSite=Lax")
                self.assertEqual(m.session_cookie("abc123", remember=True), "sid=abc123; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000")
                self.assertEqual(m.session_cookie("abc123", False), m.session_cookie("abc123"))

            def test_flags_present(self):
                for remember in (False, True):
                    attrs = [a.strip() for a in m.session_cookie("x", remember).split(";")[1:]]
                    for flag in ("HttpOnly", "Secure", "SameSite=Lax", "Path=/"):
                        self.assertIn(flag, attrs)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

LOGOUT = dd(r'''
    """Server-side sessions of the dashboard."""
    import secrets

    CLEAR = "sid=; Path=/; Max-Age=0"


    class SessionStore:
        def __init__(self):
            self.sessions = {}

        def create(self, user):
            sid = secrets.token_hex(16)
            self.sessions[sid] = {"user": user}
            return sid

        def user(self, sid):
            """The user of a session, or None when the id is unknown (or no longer valid)."""
            session = self.sessions.get(sid)
            return session["user"] if session else None

        def logout(self, sid):
            """End the session and return the header value that clears the cookie. The session id must stop working immediately, for everybody who knows it (a stolen cookie included)."""
            return CLEAR

        def logout_all(self, user):
            """End every session of `user` (all devices); returns the cookie-clearing header value."""
            return CLEAR
''')

SE.append(dict(
    slug="logout-keeps-session", d=2, product="the dashboard", func="SessionStore.logout", cwe="CWE-613",
    finding="`logout` and `logout_all` only return a cookie-clearing header: the session stays alive in the server's store, so a copied cookie keeps working after the user logged out (and \"log out everywhere\" after a password change does nothing).",
    start={"sessions.py": LOGOUT, "README.md": readme("sessions", "`logout(sid)` removes that session from the store (unknown ids are fine) and returns `CLEAR`; `logout_all(user)` removes every session of the user and leaves other users' sessions alone. After either, `user(sid)` is `None` for the removed sessions.")},
    solution={"sessions.py": patched(LOGOUT, (
        '''            return CLEAR

        def logout_all(self, user):''', '''            self.sessions.pop(sid, None)
            return CLEAR

        def logout_all(self, user):'''), (
        '''            """End every session of `user` (all devices); returns the cookie-clearing header value."""
            return CLEAR
''', '''            """End every session of `user` (all devices); returns the cookie-clearing header value."""
            for sid in [s for s, data in self.sessions.items() if data["user"] == user]:
                del self.sessions[sid]
            return CLEAR
'''))},
    hidden={"tests/test_sessions_security.py": P + dd(r'''
        import sessions as m


        class SessionTest(unittest.TestCase):
            def test_logout(self):
                s = m.SessionStore()
                a1, a2, b = s.create("ann"), s.create("ann"), s.create("bob")
                self.assertEqual((s.user(a1), s.user(a2), s.user(b)), ("ann", "ann", "bob"))
                self.assertEqual(s.logout(a1), m.CLEAR)
                self.assertIsNone(s.user(a1))
                self.assertEqual(s.user(a2), "ann")
                self.assertEqual(s.logout(a1), m.CLEAR)
                self.assertEqual(s.logout("unknown"), m.CLEAR)
                self.assertEqual(s.user(b), "bob")

            def test_logout_all(self):
                s = m.SessionStore()
                ids = [s.create("ann") for _ in range(3)]
                other = s.create("bob")
                self.assertEqual(s.logout_all("ann"), m.CLEAR)
                for sid in ids:
                    self.assertIsNone(s.user(sid))
                self.assertEqual(s.user(other), "bob")
                self.assertEqual(s.logout_all("nobody"), m.CLEAR)
                self.assertEqual(s.user(other), "bob")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

FIX = dd(r'''
    """Login of the web shop (in-process model)."""
    import secrets


    class Site:
        def __init__(self, users):
            self.users = users          # name -> password (toy credential check)
            self.sessions = {}

        def start(self):
            """A new anonymous session (it can already hold a shopping cart); returns its id."""
            sid = secrets.token_hex(16)
            self.sessions[sid] = {"user": None, "data": {}}
            return sid

        def login(self, sid, name, password):
            """Log in inside the anonymous session `sid` and return the session id to use from now on. The cart (`data`) is kept, but the id changes: the old id must stop working and
            must never become an authenticated session. ValueError for bad credentials or an unknown session (nothing changes then)."""
            if sid not in self.sessions or self.users.get(name) != password:
                raise ValueError("login failed")
            self.sessions[sid]["user"] = name
            return sid

        def user(self, sid):
            session = self.sessions.get(sid)
            return session["user"] if session else None

        def data(self, sid):
            return self.sessions[sid]["data"]
''')

SE.append(dict(
    slug="session-fixation", d=3, product="the web shop login", func="Site.login", cwe="CWE-384",
    finding="`login` authenticates the session id it was given and returns the same id: an attacker who plants a known session id in the victim's browser (a link with `?sid=...`, a cookie from a sibling sub-domain) is logged in as soon as the victim signs in (session fixation).",
    start={"shop.py": FIX, "README.md": readme("shop login", "`login(sid, name, password)` returns a *new* random session id (32 hex characters) that carries the same `data` and the user; the old id is deleted, so it works for nobody afterwards. Failed logins raise `ValueError` and change nothing - the anonymous session stays as it was.")},
    solution={"shop.py": patched(FIX, (
        '''            self.sessions[sid]["user"] = name
            return sid
''', '''            session = self.sessions.pop(sid)
            session["user"] = name
            new_sid = secrets.token_hex(16)
            self.sessions[new_sid] = session
            return new_sid
'''))},
    hidden={"tests/test_shop_security.py": P + dd(r'''
        import shop as m


        class ShopTest(unittest.TestCase):
            def test_login_flow(self):
                site = m.Site({"ann": "pw1", "bob": "pw2"})
                sid = site.start()
                site.data(sid)["cart"] = ["book", "pen"]
                self.assertIsNone(site.user(sid))
                new = site.login(sid, "ann", "pw1")
                self.assertRegex(new, r"^[0-9a-f]{32}$")
                self.assertEqual(site.user(new), "ann")
                self.assertEqual(site.data(new)["cart"], ["book", "pen"])

            def test_fixation(self):
                site = m.Site({"ann": "pw1"})
                planted = site.start()
                new = site.login(planted, "ann", "pw1")
                self.assertNotEqual(new, planted)
                self.assertIsNone(site.user(planted))
                self.assertIsNone(attempt(site.data, planted))
                self.assertIsNone(attempt(site.login, planted, "ann", "pw1"))
                self.assertEqual(site.user(new), "ann")
                self.assertEqual(site.user(planted), None)
                self.assertNotIn(planted, site.sessions)

            def test_failed_login_changes_nothing(self):
                site = m.Site({"ann": "pw1"})
                sid = site.start()
                site.data(sid)["cart"] = ["x"]
                for name, pw in [("ann", "bad"), ("bob", "pw1"), ("", "")]:
                    self.assertIsNone(attempt(site.login, sid, name, pw))
                    self.assertIsNone(site.user(sid))
                    self.assertEqual(site.data(sid), {"cart": ["x"]})
                self.assertEqual(set(site.sessions), {sid})
                self.assertIsNone(attempt(site.login, "unknown", "ann", "pw1"))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

TIMEOUT = dd(r'''
    """Server-side sessions with lifetimes (clock injected for testing)."""
    import secrets
    import time


    class SessionStore:
        def __init__(self, idle=1800, absolute=43200, clock=time.time):
            self.idle = idle
            self.absolute = absolute
            self.clock = clock
            self.sessions = {}

        def create(self, user):
            now = self.clock()
            sid = secrets.token_hex(16)
            self.sessions[sid] = {"user": user, "created": now, "seen": now}
            return sid

        def user(self, sid):
            """The user of a live session, or None. A session dies when it has been idle for more than `idle` seconds (time since the last successful lookup) or is older than `absolute` seconds
            (time since it was created) - activity keeps it alive only until then. Dead sessions are removed from the store. A successful lookup counts as activity."""
            session = self.sessions.get(sid)
            if session is None:
                return None
            session["seen"] = self.clock()
            return session["user"]
''')

SE.append(dict(
    slug="session-timeouts", d=3, product="the dashboard sessions", func="SessionStore.user", cwe="CWE-613",
    finding="`user` never looks at the idle or absolute lifetime that `SessionStore` is configured with: a session created last month and last used last week still works, so a cookie left on a shared computer or leaked in a log is valid forever.",
    start={"sessions.py": TIMEOUT, "README.md": readme("session lifetimes", "`user(sid)` implements the rules in its docstring: dead when `now - seen > idle` or `now - created > absolute` (the limits themselves are still alive), removed from `sessions` when found dead, `seen` updated only by successful lookups. `create` is unchanged.")},
    solution={"sessions.py": patched(TIMEOUT, (
        '''            session["seen"] = self.clock()
            return session["user"]
''', '''            now = self.clock()
            if now - session["seen"] > self.idle or now - session["created"] > self.absolute:
                del self.sessions[sid]
                return None
            session["seen"] = now
            return session["user"]
'''))},
    hidden={"tests/test_sessions_security.py": P + dd(r'''
        import sessions as m


        class Clock:
            def __init__(self):
                self.t = 1_000_000.0

            def __call__(self):
                return self.t


        class TimeoutTest(unittest.TestCase):
            def test_activity_keeps_session_alive(self):
                clock = Clock()
                s = m.SessionStore(idle=1800, absolute=43200, clock=clock)
                sid = s.create("ann")
                for _ in range(20):
                    clock.t += 1700
                    self.assertEqual(s.user(sid), "ann")
                clock.t += 1800
                self.assertEqual(s.user(sid), "ann")

            def test_idle_timeout(self):
                clock = Clock()
                s = m.SessionStore(idle=1800, absolute=43200, clock=clock)
                sid = s.create("ann")
                other = s.create("bob")
                clock.t += 1801
                self.assertIsNone(s.user(sid))
                self.assertNotIn(sid, s.sessions)
                self.assertIsNone(s.user(sid))
                self.assertIsNone(s.user(other))
                a, b = s.create("ann"), s.create("bob")
                clock.t += 1800
                self.assertEqual(s.user(a), "ann")
                clock.t += 1801
                self.assertIsNone(s.user(a))
                self.assertIsNone(s.user(b))

            def test_absolute_timeout(self):
                clock = Clock()
                s = m.SessionStore(idle=1800, absolute=7200, clock=clock)
                sid = s.create("ann")
                for _ in range(4):
                    clock.t += 1700
                    self.assertEqual(s.user(sid), "ann")
                clock.t += 400
                self.assertEqual(s.user(sid), "ann")
                clock.t += 1
                self.assertIsNone(s.user(sid))
                self.assertNotIn(sid, s.sessions)

            def test_dead_lookups_do_not_revive(self):
                clock = Clock()
                s = m.SessionStore(idle=100, absolute=1000, clock=clock)
                sid = s.create("ann")
                clock.t += 101
                self.assertIsNone(s.user(sid))
                clock.t += 1
                self.assertIsNone(s.user(sid))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SE_ORDER = ["cookie-flags", "logout-keeps-session", "session-fixation", "session-timeouts"]
SE.sort(key=lambda s: (s["d"], SE_ORDER.index(s["slug"])))


@family("security-sessions", category="security", lang="python", kind="fix", n=4,
        summary="session management: cookie flags, logout that really logs out, fixation, idle and absolute timeouts")
def gen_sessions(rng, n):
    return list(_sec.emit(rng, SE[:n], tags=["sessions"]))
