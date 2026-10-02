"""Security families: weak randomness, timing-unsafe comparisons, misuse of hashes and ciphers. Tests are deterministic: they forbid the global
Mersenne Twister, freeze clocks, spy on string comparisons and check properties of the output instead of timing anything."""
from fx import dd, family

from . import _sec
from ._sec import patched, readme

RND = _sec.PY_PRELUDE + dd(r'''
    import contextlib
    import random
    import string
    import time
    from collections import Counter


    @contextlib.contextmanager
    def no_global_random():
        """Inside the block the module-level functions of `random` (the predictable Mersenne Twister) raise AssertionError."""
        names = ["random", "randint", "randrange", "choice", "choices", "sample", "shuffle", "getrandbits", "uniform", "randbytes"]
        saved = {n: getattr(random, n) for n in names}

        def boom(*a, **k):
            raise AssertionError("the predictable global PRNG (random.*) was used")

        for n in names:
            setattr(random, n, boom)
        try:
            yield
        finally:
            for n, f in saved.items():
                setattr(random, n, f)


    @contextlib.contextmanager
    def frozen_clock(t=1700000000.25, pid=4242):
        """time.time, time_ns, monotonic, perf_counter and os.getpid return constants inside the block."""
        saved = (time.time, time.time_ns, time.monotonic, time.perf_counter, os.getpid)
        time.time = lambda: t
        time.time_ns = lambda: int(t * 1e9)
        time.monotonic = lambda: t
        time.perf_counter = lambda: t
        os.getpid = lambda: pid
        try:
            yield t
        finally:
            time.time, time.time_ns, time.monotonic, time.perf_counter, os.getpid = saved


''')

SPY = _sec.PY_PRELUDE + dd(r'''
    class Spy(str):
        """A str that records how its content is inspected: `==`, `!=`, indexing, iteration (one entry per character handed out), startswith."""

        def __new__(cls, value, log):
            obj = super().__new__(cls, value)
            obj.log = log
            return obj

        def __eq__(self, other):
            self.log.append("eq")
            return str.__eq__(self, other)

        def __ne__(self, other):
            self.log.append("ne")
            return str.__ne__(self, other)

        __hash__ = str.__hash__

        def __getitem__(self, i):
            self.log.append("item")
            return str.__getitem__(self, i)

        def __iter__(self):
            for ch in str.__iter__(self):
                self.log.append("char")
                yield ch

        def startswith(self, *a):
            self.log.append("startswith")
            return str.startswith(self, *a)

        def endswith(self, *a):
            self.log.append("endswith")
            return str.endswith(self, *a)


    def trace(fn, *args):
        """Result and the inspection log of the spied arguments (the Spy arguments share one log list)."""
        log = []
        wrapped = [Spy(a, log) if isinstance(a, str) else a for a in args]
        return fn(*wrapped), log


''')

# =================================================================================================================================
#  weak randomness
# =================================================================================================================================
WR = []

TOK = dd(r'''
    """Password-reset tokens."""
    import random
    import string

    ALPHABET = string.ascii_letters + string.digits


    def new_reset_token(length=32):
        """A reset token: `length` characters (32 by default) from ALPHABET, impossible to guess."""
        return "".join(random.choice(ALPHABET) for _ in range(length))
''')

WR.append(dict(
    slug="reset-token", d=1, product="the password-reset flow", func="new_reset_token", cwe="CWE-338",
    finding="`new_reset_token` draws the token from Python's `random` module, a Mersenne Twister whose state can be recovered from a few hundred outputs; whoever can request resets for their own account can then predict the tokens issued to others.",
    start={"tokens.py": TOK, "README.md": readme("reset tokens", "`new_reset_token(length=32)` returns `length` characters taken from `ALPHABET`, each uniformly and independently. The tokens protect account takeover, so they must come from a cryptographically secure source.")},
    solution={"tokens.py": patched(TOK, ('import random\n', 'import secrets\n'), ('random.choice(ALPHABET)', 'secrets.choice(ALPHABET)'))},
    hidden={"tests/test_tokens_security.py": RND + dd(r'''
        import tokens as m


        class TokenTest(unittest.TestCase):
            def test_format(self):
                for n in (1, 8, 32, 64):
                    t = m.new_reset_token(n)
                    self.assertEqual(len(t), n)
                    self.assertTrue(set(t) <= set(m.ALPHABET))
                self.assertEqual(len(m.new_reset_token()), 32)
                self.assertEqual(m.new_reset_token(0), "")

            def test_not_from_the_global_prng(self):
                with no_global_random():
                    tokens = [m.new_reset_token() for _ in range(300)]
                self.assertEqual(len(set(tokens)), 300)
                random.seed(1234)
                a = m.new_reset_token()
                random.seed(1234)
                b = m.new_reset_token()
                self.assertNotEqual(a, b)

            def test_whole_alphabet_is_used(self):
                seen = set()
                for _ in range(300):
                    seen |= set(m.new_reset_token())
                self.assertEqual(seen, set(m.ALPHABET))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SID = dd(r'''
    """Session identifiers."""
    import hashlib
    import time


    def new_session_id(username):
        """A new session id: exactly 32 lowercase hexadecimal characters (128 bits) that nobody can predict or derive from the user name, the time or earlier ids."""
        return hashlib.md5(("%s:%f" % (username, time.time())).encode()).hexdigest()
''')

WR.append(dict(
    slug="session-id", d=2, product="the session layer", func="new_session_id", cwe="CWE-330",
    finding="`new_session_id` is the MD5 of the user name and the current time, so session ids of other users can be reconstructed by trying the few thousand timestamps around a known login (and two logins in the same instant collide), which is session hijacking.",
    start={"sessions.py": SID, "README.md": readme("sessions", "`new_session_id(username)` returns 32 lowercase hex characters made of 128 random bits from a secure source. The user name is not an input of the id; ids never repeat and cannot be recomputed from public information.")},
    solution={"sessions.py": patched(SID, ('import hashlib\nimport time\n', 'import secrets\n'), (
        '    return hashlib.md5(("%s:%f" % (username, time.time())).encode()).hexdigest()\n', '    return secrets.token_hex(16)\n'))},
    hidden={"tests/test_sessions_security.py": RND + dd(r'''
        import hashlib
        import re

        import sessions as m


        class SessionTest(unittest.TestCase):
            def test_ids(self):
                for _ in range(20):
                    self.assertRegex(m.new_session_id("ann"), r"^[0-9a-f]{32}$")

            def test_unpredictable(self):
                with frozen_clock() as now, no_global_random():
                    ids = [m.new_session_id("ann") for _ in range(300)] + [m.new_session_id("bob") for _ in range(300)]
                    self.assertEqual(len(set(ids)), 600)
                    guesses = set()
                    for user in ("ann", "bob"):
                        for text in ["%s:%f" % (user, now), "%s:%s" % (user, now), "%s%d" % (user, now), "%s:%d" % (user, now), "%s" % user, "%d" % now, "%s-%f" % (user, now)]:
                            for algo in (hashlib.md5, hashlib.sha1, hashlib.sha256):
                                guesses.add(algo(text.encode()).hexdigest()[:32])
                    self.assertFalse(set(ids) & guesses)
                random.seed(7)
                a = m.new_session_id("ann")
                random.seed(7)
                self.assertNotEqual(a, m.new_session_id("ann"))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

OTP = dd(r'''
    """One-time codes for two-factor login."""
    import random


    def new_otp():
        """A one-time code: exactly six decimal digits (leading zeros are allowed and common), uniformly random and unpredictable."""
        return str(random.randint(0, 999999))
''')

WR.append(dict(
    slug="otp-code", d=2, product="the two-factor login", func="new_otp", cwe="CWE-338",
    finding="`new_otp` uses the predictable `random` module, and formats the number without padding, so about one code in ten has fewer than six digits and users cannot enter it.",
    start={"otp.py": OTP, "README.md": readme("one-time codes", "`new_otp()` returns a string of exactly six digits, `000000` to `999999`, each code equally likely, from a cryptographically secure source.")},
    solution={"otp.py": patched(OTP, ('import random\n', 'import secrets\n'), ('    return str(random.randint(0, 999999))\n', '    return "%06d" % secrets.randbelow(1000000)\n'))},
    hidden={"tests/test_otp_security.py": RND + dd(r'''
        import otp as m


        class OtpTest(unittest.TestCase):
            def test_format(self):
                with no_global_random():
                    codes = [m.new_otp() for _ in range(3000)]
                for c in codes:
                    self.assertRegex(c, r"^[0-9]{6}$")
                self.assertTrue(any(c.startswith("0") for c in codes))
                self.assertGreater(len(set(codes)), 2900)
                first = Counter(c[0] for c in codes)
                self.assertEqual(set(first), set(string.digits))

            def test_not_reproducible(self):
                random.seed(99)
                a = [m.new_otp() for _ in range(5)]
                random.seed(99)
                b = [m.new_otp() for _ in range(5)]
                self.assertNotEqual(a, b)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

PWG = dd(r'''
    """Generated passwords for new accounts."""
    import random
    import string

    SYMBOLS = "!@#$%^&*-_"
    ALL = string.ascii_letters + string.digits + SYMBOLS


    def generate_password(length=16):
        """A random password of `length` characters (8 to 128, otherwise ValueError) from lowercase letters, uppercase letters, digits and SYMBOLS, containing at least one of each kind.
        Every position is equally unpredictable: nothing about the layout (which kind of character comes where) may be fixed."""
        if not 8 <= length <= 128:
            raise ValueError("length must be between 8 and 128")
        chars = [random.choice(string.ascii_lowercase), random.choice(string.ascii_uppercase), random.choice(string.digits), random.choice(SYMBOLS)]
        chars += [random.choice(ALL) for _ in range(length - 4)]
        return "".join(chars)
''')

WR.append(dict(
    slug="password-generator", d=3, product="the account provisioning tool", func="generate_password", cwe="CWE-338",
    finding="`generate_password` uses the Mersenne Twister from `random`, and always puts one lowercase letter, one uppercase letter, one digit and one symbol in the first four positions, which both makes the password predictable from other outputs and removes entropy from the pattern.",
    start={"passwords.py": PWG, "README.md": readme("generated passwords", "`generate_password(length=16)` returns a password of exactly `length` characters (8..128, else `ValueError`) with at least one lowercase letter, one uppercase letter, one digit and one symbol from `SYMBOLS`, and no other characters. It must use a cryptographically secure source, and the positions of the required characters must be random too.")},
    solution={"passwords.py": patched(PWG, ('import random\nimport string\n', 'import random\nimport secrets\nimport string\n'), (
        '''    chars = [random.choice(string.ascii_lowercase), random.choice(string.ascii_uppercase), random.choice(string.digits), random.choice(SYMBOLS)]
    chars += [random.choice(ALL) for _ in range(length - 4)]
    return "".join(chars)
''', '''    chars = [secrets.choice(string.ascii_lowercase), secrets.choice(string.ascii_uppercase), secrets.choice(string.digits), secrets.choice(SYMBOLS)]
    chars += [secrets.choice(ALL) for _ in range(length - 4)]
    random.SystemRandom().shuffle(chars)
    return "".join(chars)
'''))},
    hidden={"tests/test_passwords_security.py": RND + dd(r'''
        import passwords as m

        KINDS = [string.ascii_lowercase, string.ascii_uppercase, string.digits, m.SYMBOLS]


        def kind(ch):
            return [i for i, k in enumerate(KINDS) if ch in k][0]


        class PasswordTest(unittest.TestCase):
            def test_rules(self):
                for n in (8, 9, 12, 16, 40, 128):
                    for _ in range(20):
                        pw = m.generate_password(n)
                        self.assertEqual(len(pw), n)
                        self.assertTrue(all(any(c in k for k in KINDS) for c in pw))
                        self.assertEqual({kind(c) for c in pw}, {0, 1, 2, 3})
                self.assertEqual(len(m.generate_password()), 16)
                for bad in (7, 0, 129, -1):
                    self.assertIsNone(attempt(m.generate_password, bad))

            def test_layout_is_random(self):
                with no_global_random():
                    pws = [m.generate_password(16) for _ in range(300)]
                self.assertEqual(len(set(pws)), 300)
                self.assertGreaterEqual(len({kind(p[0]) for p in pws}), 3)
                self.assertGreater(len({tuple(kind(c) for c in p[:4]) for p in pws}), 10)

            def test_not_reproducible(self):
                random.seed(5)
                a = m.generate_password()
                random.seed(5)
                self.assertNotEqual(a, m.generate_password())


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

APIK = dd(r'''
    """API key issuing."""
    import os
    import random
    import string
    import time

    BASE62 = string.ascii_letters + string.digits


    def new_api_key():
        """An API key: `sk_` followed by 40 characters from BASE62, unpredictable even for someone who knows when and where (which process) it was issued."""
        random.seed(os.getpid() ^ int(time.time()))
        return "sk_" + "".join(random.choice(BASE62) for _ in range(40))
''')

WR.append(dict(
    slug="api-key", d=3, product="the developer portal", func="new_api_key", cwe="CWE-337",
    finding="`new_api_key` re-seeds the global Mersenne Twister with `pid ^ time` before every key, so the whole key is determined by a seed with only a few thousand plausible values: anyone who knows roughly when a key was issued can regenerate it (and the re-seeding also makes every other user of `random` predictable).",
    start={"apikeys.py": APIK, "README.md": readme("API keys", "`new_api_key()` returns `sk_` plus 40 characters from `BASE62`, each uniformly and independently random from a secure source. Nothing about process ids or clocks may influence the key, and the function must not touch the global `random` state.")},
    solution={"apikeys.py": patched(APIK, ('import os\nimport random\nimport string\nimport time\n', 'import secrets\nimport string\n'), (
        '    random.seed(os.getpid() ^ int(time.time()))\n    return "sk_" + "".join(random.choice(BASE62) for _ in range(40))\n',
        '    return "sk_" + "".join(secrets.choice(BASE62) for _ in range(40))\n'))},
    hidden={"tests/test_apikeys_security.py": RND + dd(r'''
        import apikeys as m


        class ApiKeyTest(unittest.TestCase):
            def test_format(self):
                for _ in range(20):
                    self.assertRegex(m.new_api_key(), r"^sk_[A-Za-z0-9]{40}$")

            def test_independent_of_time_and_pid(self):
                with frozen_clock(), no_global_random():
                    keys = [m.new_api_key() for _ in range(200)]
                self.assertEqual(len(set(keys)), 200)

            def test_global_state_untouched(self):
                random.seed(321)
                expected = random.random()
                random.seed(321)
                m.new_api_key()
                self.assertEqual(random.random(), expected)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

DRAW = dd(r'''
    """Prize draws for the newsletter."""
    import os


    def pick_winner(entries):
        """One entry chosen uniformly at random from the list `entries` (any length, any entry may win with equal probability), unpredictably: the draw decides a prize, so it must use a cryptographically secure
        source. ValueError for an empty list."""
        if not entries:
            raise ValueError("no entries")
        return entries[os.urandom(1)[0] % len(entries)]
''')

WR.append(dict(
    slug="prize-draw", d=4, product="the newsletter prize draw", func="pick_winner", cwe="CWE-338",
    finding="`pick_winner` turns one random byte into an index with `% len(entries)`: with more than 256 entries the later ones can never win, and with any list length that is not a divisor of 256 the first entries are favoured (modulo bias). The draw is only random in name.",
    start={"draw.py": DRAW, "README.md": readme("prize draw", "`pick_winner(entries)` returns a uniformly chosen element: every position of the list has the same probability, whatever its length (1 to millions), and the choice comes from a cryptographically secure generator (not `random.*`). An empty list raises `ValueError`.")},
    solution={"draw.py": patched(DRAW, ('import os\n', 'import secrets\n'), ('    return entries[os.urandom(1)[0] % len(entries)]\n', '    return entries[secrets.randbelow(len(entries))]\n'))},
    hidden={"tests/test_draw_security.py": RND + dd(r'''
        import draw as m


        class DrawTest(unittest.TestCase):
            def test_small_lists(self):
                with no_global_random():
                    self.assertEqual(m.pick_winner(["only"]), "only")
                    self.assertEqual({m.pick_winner([1, 2, 3]) for _ in range(200)}, {1, 2, 3})
                self.assertIsNone(attempt(m.pick_winner, []))
                self.assertEqual(m.pick_winner(("x",)), "x")

            def test_every_entry_can_win(self):
                entries = list(range(1000))
                with no_global_random():
                    wins = Counter(m.pick_winner(entries) for _ in range(30000))
                self.assertGreater(len(wins), 940)

            def test_no_modulo_bias(self):
                entries = list(range(200))
                n = 40000
                with no_global_random():
                    wins = Counter(m.pick_winner(entries) for _ in range(n))
                low = sum(wins[i] for i in range(56)) / n
                self.assertLess(abs(low - 56 / 200), 0.02)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

WR_ORDER = ["reset-token", "session-id", "otp-code", "password-generator", "api-key", "prize-draw"]
WR.sort(key=lambda s: (s["d"], WR_ORDER.index(s["slug"])))


@family("security-weak-random", category="security", lang="python", kind="fix", n=6,
        summary="predictable randomness: Mersenne Twister tokens, time-derived ids, modulo bias, re-seeding")
def gen_weak_random(rng, n):
    return list(_sec.emit(rng, WR[:n], tags=["randomness"]))


# =================================================================================================================================
#  timing-unsafe comparisons
# =================================================================================================================================
TM = []

TOKCHK = dd(r'''
    """Bearer-token check of the internal API."""


    def verify_token(supplied, expected):
        """True when the token the client sent equals the configured one. Anything that is not a string (None, bytes, numbers) or does not match is False - never an exception, also for non-ASCII text."""
        if not isinstance(supplied, str) or not isinstance(expected, str):
            return False
        return supplied == expected
''')

TM.append(dict(
    slug="token-compare", d=2, product="the internal API", func="verify_token", cwe="CWE-208",
    finding="`verify_token` compares the secret with `==`, which stops at the first differing character; the response time reveals how long a correct prefix is, so a patient attacker can recover the token one character at a time.",
    start={"tokencheck.py": TOKCHK, "README.md": readme("token check", "`verify_token(supplied, expected)` is True only for equal strings. The comparison must not leak where two strings differ (use a constant-time comparison); inputs that are not `str`, and non-ASCII strings, give `False` without raising.")},
    solution={"tokencheck.py": patched(TOKCHK, ('"""Bearer-token check of the internal API."""\n', '"""Bearer-token check of the internal API."""\nimport hmac\n'), (
        '    return supplied == expected\n', '    return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))\n'))},
    hidden={"tests/test_tokencheck_security.py": SPY + dd(r'''
        import tokencheck as m

        SECRET = "k9X2-mQ7p-Zt41-vB8c"


        class TokenTest(unittest.TestCase):
            def test_results(self):
                self.assertIs(m.verify_token(SECRET, SECRET), True)
                for bad in [SECRET[:-1], SECRET + "x", "", "K9X2-mQ7p-Zt41-vB8c", "x" * 19, None, 5, SECRET.encode(), "k9X2-mQ7p-Zt41-vB8é", "über"]:
                    self.assertIs(m.verify_token(bad, SECRET), False, repr(bad))
                self.assertIs(m.verify_token("tökén", "tökén"), True)

            def test_comparison_does_not_leak_position(self):
                logs = {}
                for label, supplied in [("equal", SECRET), ("first", "X" + SECRET[1:]), ("middle", SECRET[:9] + "X" + SECRET[10:]), ("last", SECRET[:-1] + "X")]:
                    result, log = trace(m.verify_token, supplied, SECRET)
                    self.assertEqual(result, label == "equal")
                    logs[label] = log
                for log in logs.values():
                    self.assertNotIn("eq", log)
                    self.assertNotIn("ne", log)
                    self.assertNotIn("startswith", log)
                self.assertEqual(len({tuple(v) for v in logs.values()}), 1, logs)
                for label, expected_pos in [("first", 0), ("last", 18)]:
                    _, log = trace(m.verify_token, SECRET, SECRET[:expected_pos] + "X" + SECRET[expected_pos + 1:])
                    self.assertNotIn("eq", log)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SIGV = dd(r'''
    """Webhook signature check."""
    import hashlib
    import hmac


    def verify_signature(body, signature, secret):
        """True when `signature` (hex text, upper or lower case) is the HMAC-SHA256 of `body` (bytes) under `secret` (bytes). Anything that cannot be a signature (None, wrong type, non-ASCII, wrong length)
        is simply False; the comparison must not reveal how many leading characters were right."""
        expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
        return signature == expected
''')

TM.append(dict(
    slug="hmac-compare", d=2, product="the webhook receiver", func="verify_signature", cwe="CWE-208",
    finding="`verify_signature` compares the expected HMAC with `==`: the comparison time depends on the number of matching leading characters, which lets an attacker forge a valid signature for a payload of their choice by guessing it character by character (and upper-case hex signatures from some senders are rejected).",
    start={"signature.py": SIGV, "README.md": readme("webhook signatures", "`verify_signature(body, signature, secret)` accepts the lower- or upper-case hex HMAC-SHA256 of the body and nothing else; malformed signatures give `False` (no exception). The comparison is constant-time.")},
    solution={"signature.py": patched(SIGV, (
        '    return signature == expected\n',
        '    if not isinstance(signature, str):\n        return False\n    return hmac.compare_digest(signature.lower().encode("utf-8"), expected.encode("utf-8"))\n'))},
    hidden={"tests/test_signature_security.py": SPY + dd(r'''
        import hashlib
        import hmac

        import signature as m

        SECRET = b"whsec_test_secret"
        BODY = b'{"event":"paid","id":42}'
        GOOD = hmac.new(SECRET, BODY, hashlib.sha256).hexdigest()


        class SignatureTest(unittest.TestCase):
            def test_results(self):
                self.assertIs(m.verify_signature(BODY, GOOD, SECRET), True)
                self.assertIs(m.verify_signature(BODY, GOOD.upper(), SECRET), True)
                for bad in [GOOD[:-1], GOOD + "0", "", None, 5, GOOD.encode(), "é" * 64, GOOD[:-1] + ("0" if GOOD[-1] != "0" else "1"), GOOD.replace(GOOD[0], "z", 1)]:
                    self.assertIs(m.verify_signature(BODY, bad, SECRET), False, repr(bad))
                self.assertIs(m.verify_signature(BODY + b" ", GOOD, SECRET), False)
                self.assertIs(m.verify_signature(BODY, GOOD, b"other"), False)

            def test_no_early_exit(self):
                flip = lambda i: GOOD[:i] + ("0" if GOOD[i] != "0" else "1") + GOOD[i + 1:]
                logs = []
                for sig in [GOOD, flip(0), flip(31), flip(63)]:
                    result, log = trace(m.verify_signature, BODY, sig, SECRET)
                    self.assertEqual(result, sig == GOOD)
                    self.assertFalse({"eq", "ne", "startswith", "endswith"} & set(log), log)
                    logs.append(tuple(log))
                self.assertEqual(len(set(logs)), 1, logs)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

ORACLE = dd(r'''
    """Login check of the admin console."""
    import hashlib
    import hmac


    def slow_hash(password, salt):
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 1000).hex()


    class Auth:
        DUMMY_SALT = b"\x00" * 16

        def __init__(self, users, hasher=slow_hash):
            """`users` maps a name to `(salt, hash_hex)`; `hasher(password, salt)` is the (deliberately slow) password hash."""
            self.users = users
            self.hasher = hasher

        def login(self, username, password):
            """True when `username` exists and `password` is right. Unknown users and wrong passwords must cost the same: the hasher runs exactly once in every case, so the response time does not tell
            an attacker which user names exist."""
            entry = self.users.get(username)
            if entry is None:
                return False
            salt, expected = entry
            return hmac.compare_digest(self.hasher(password, salt), expected)
''')

TM.append(dict(
    slug="login-oracle", d=3, product="the admin console login", func="Auth.login", cwe="CWE-208",
    finding="`Auth.login` returns immediately for unknown user names and only runs the slow password hash for existing accounts, so response times reveal which names are valid (user enumeration through a timing side channel) and narrow down password-spraying targets.",
    start={"console.py": ORACLE, "README.md": readme("admin login", "`Auth(users, hasher)` and `login(username, password)` keep their behaviour: True only for a known user with the right password. The hasher is called exactly once per login attempt, with the user's salt, or with `DUMMY_SALT` for unknown users (the result is then discarded), so all failures cost the same.")},
    solution={"console.py": patched(ORACLE, (
        '''        entry = self.users.get(username)
        if entry is None:
            return False
        salt, expected = entry
        return hmac.compare_digest(self.hasher(password, salt), expected)
''', '''        entry = self.users.get(username)
        salt, expected = entry if entry is not None else (self.DUMMY_SALT, "0" * 64)
        ok = hmac.compare_digest(self.hasher(password, salt), expected)
        return ok and entry is not None
'''))},
    hidden={"tests/test_console_security.py": _sec.PY_PRELUDE + dd(r'''
        import console as m


        class CountingHasher:
            def __init__(self):
                self.calls = []

            def __call__(self, password, salt):
                self.calls.append((password, salt))
                return m.slow_hash(password, salt)


        class LoginTest(unittest.TestCase):
            def setUp(self):
                salt = b"s" * 16
                self.users = {"ann": (salt, m.slow_hash("correct horse", salt)), "bob": (b"t" * 16, m.slow_hash("tr0ub4dor", b"t" * 16))}

            def test_results(self):
                auth = m.Auth(self.users)
                self.assertTrue(auth.login("ann", "correct horse"))
                self.assertTrue(auth.login("bob", "tr0ub4dor"))
                self.assertFalse(auth.login("ann", "wrong"))
                self.assertFalse(auth.login("ann", "tr0ub4dor"))
                self.assertFalse(auth.login("mallory", "correct horse"))
                self.assertFalse(auth.login("", ""))

            def test_every_attempt_costs_one_hash(self):
                for user, pw in [("ann", "correct horse"), ("ann", "wrong"), ("mallory", "correct horse"), ("nobody", ""), ("", "x")]:
                    hasher = CountingHasher()
                    m.Auth(self.users, hasher).login(user, pw)
                    self.assertEqual(len(hasher.calls), 1, (user, pw))
                    self.assertEqual(hasher.calls[0][0], pw)
                    self.assertEqual(len(hasher.calls[0][1]), 16)

            def test_unknown_user_never_passes(self):
                # even when the hasher happens to return the dummy comparison value
                auth = m.Auth(self.users, lambda password, salt: "0" * 64)
                self.assertFalse(auth.login("mallory", "anything"))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SAFEEQ = dd(r'''
    """Signed cookies."""
    import hashlib
    import hmac


    def safe_equals(a, b):
        """True when the two strings are equal. The time taken must not depend on where they differ (only on their lengths): this guards secret values such as cookie signatures."""
        if len(a) != len(b):
            return False
        for x, y in zip(a, b):
            if x != y:
                return False
        return True


    def sign(value, secret):
        """`value` + "." + the hex HMAC-SHA256 of `value` under `secret` (bytes)."""
        return value + "." + hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()


    def unsign(cookie, secret):
        """The original value when the cookie's signature is valid, else None."""
        value, dot, signature = cookie.rpartition(".")
        if not dot:
            return None
        expected = hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()
        return value if safe_equals(signature, expected) else None
''')

TM.append(dict(
    slug="hand-rolled-compare", d=3, product="the cookie signer", func="safe_equals", cwe="CWE-208",
    finding="`safe_equals` is meant to be the constant-time comparison for cookie signatures, but it returns at the first differing character, so its running time leaks the length of the correct prefix: the signature of a forged cookie can be guessed one character at a time.",
    start={"cookies.py": SAFEEQ, "README.md": readme("signed cookies", "`safe_equals(a, b)` is the comparison used for secrets: equal strings give True; its work must not depend on where the strings differ (the length may be compared up front). Non-ASCII strings compare normally (no exception). `sign` and `unsign` keep their behaviour.")},
    solution={"cookies.py": patched(SAFEEQ, (
        '''    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x != y:
            return False
    return True
''', '''    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
'''))},
    hidden={"tests/test_cookies_security.py": SPY + dd(r'''
        import cookies as m

        SECRET = b"cookie-secret"


        class CookieTest(unittest.TestCase):
            def test_roundtrip(self):
                for value in ["ann", "a.b.c", "", "café"]:
                    self.assertEqual(m.unsign(m.sign(value, SECRET), SECRET), value)
                cookie = m.sign("ann", SECRET)
                for bad in [cookie[:-1] + ("0" if cookie[-1] != "0" else "1"), cookie + "0", "ann", "ann.", "ann." + "0" * 64, m.sign("ann", b"other"), "bob" + cookie[3:]]:
                    self.assertIsNone(m.unsign(bad, SECRET), bad)

            def test_safe_equals_results(self):
                self.assertIs(m.safe_equals("abc", "abc"), True)
                self.assertIs(m.safe_equals("", ""), True)
                self.assertIs(m.safe_equals("éa", "éa"), True)
                for a, b in [("abc", "abd"), ("abc", "ab"), ("", "a"), ("é", "e"), ("abc", "ABC")]:
                    self.assertIs(m.safe_equals(a, b), False, (a, b))

            def test_no_early_exit(self):
                good = "0123456789abcdef0123456789abcdef"
                logs = []
                for other in [good, "X" + good[1:], good[:15] + "X" + good[16:], good[:-1] + "X"]:
                    result, log = trace(m.safe_equals, other, good)
                    self.assertEqual(result, other == good)
                    self.assertFalse({"eq", "ne", "startswith", "endswith"} & set(log), log)
                    logs.append(tuple(log))
                self.assertEqual(len(set(logs)), 1, logs)
                logs = []
                for other in [good, "X" + good[1:], good[:-1] + "X"]:
                    result, log = trace(m.safe_equals, good, other)
                    logs.append(tuple(log))
                self.assertEqual(len(set(logs)), 1, logs)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

TM_ORDER = ["token-compare", "hmac-compare", "login-oracle", "hand-rolled-compare"]
TM.sort(key=lambda s: (s["d"], TM_ORDER.index(s["slug"])))


@family("security-timing-compare", category="security", lang="python", kind="fix", n=4,
        summary="timing side channels: early-exit comparisons of secrets and user enumeration by response cost")
def gen_timing(rng, n):
    return list(_sec.emit(rng, TM[:n], tags=["timing"]))


# =================================================================================================================================
#  cryptographic misuse
# =================================================================================================================================
CM = []

PREFIX = dd(r'''
    """Signed download links."""
    import hashlib
    import hmac


    def sign(secret, message):
        """The signature of `message` (bytes) under `secret` (bytes): the lowercase hex HMAC-SHA256."""
        return hashlib.sha256(secret + message).hexdigest()


    def verify(secret, message, signature):
        """True when `signature` is the right signature of `message`; malformed signatures (None, non-ASCII, wrong length) are just False."""
        return hmac.compare_digest(sign(secret, message), signature)
''')

CM.append(dict(
    slug="hash-prefix-mac", d=2, product="the signed download links", func="sign", cwe="CWE-328",
    finding="`sign` builds the signature as `sha256(secret + message)` although the docstring promises an HMAC: that construction is vulnerable to length extension (anyone holding one valid link can append data and compute the matching signature without knowing the secret), and `verify` raises on non-ASCII signatures.",
    start={"links.py": PREFIX, "README.md": readme("signed links", "`sign(secret, message)` is the lowercase hex HMAC-SHA256 (RFC 2104 / 4231) of the message, so for key `0x0b * 20` and message `Hi There` it is `b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7`. `verify` is True only for that value (constant-time compare); anything else, including `None`, bytes or non-ASCII text, is False and never raises.")},
    solution={"links.py": patched(PREFIX, (
        '    return hashlib.sha256(secret + message).hexdigest()\n', '    return hmac.new(secret, message, hashlib.sha256).hexdigest()\n'), (
        '    return hmac.compare_digest(sign(secret, message), signature)\n',
        '    if not isinstance(signature, str):\n        return False\n    try:\n        return hmac.compare_digest(sign(secret, message).encode(), signature.encode("ascii"))\n    except UnicodeEncodeError:\n        return False\n'))},
    hidden={"tests/test_links_security.py": _sec.PY_PRELUDE + dd(r'''
        import hashlib
        import hmac

        import links as m


        class LinkTest(unittest.TestCase):
            def test_vectors(self):
                self.assertEqual(m.sign(b"\x0b" * 20, b"Hi There"), "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7")
                self.assertEqual(m.sign(b"Jefe", b"what do ya want for nothing?"), "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843")
                key = b"k" * 100
                self.assertEqual(m.sign(key, b"msg"), hmac.new(key, b"msg", hashlib.sha256).hexdigest())
                self.assertEqual(m.sign(b"", b""), hmac.new(b"", b"", hashlib.sha256).hexdigest())

            def test_not_a_prefix_hash(self):
                for secret, msg in [(b"s3cret", b"/download/42"), (b"a", b"b")]:
                    self.assertNotEqual(m.sign(secret, msg), hashlib.sha256(secret + msg).hexdigest())
                    self.assertNotEqual(m.sign(secret, msg), hashlib.sha256(msg + secret).hexdigest())

            def test_verify(self):
                sig = m.sign(b"s3cret", b"/download/42")
                self.assertIs(m.verify(b"s3cret", b"/download/42", sig), True)
                for bad in [sig[:-1], sig + "0", "", None, 7, "é" * 64, sig.upper(), b"x" * 64, sig[:-1] + ("0" if sig[-1] != "0" else "1")]:
                    self.assertIs(m.verify(b"s3cret", b"/download/42", bad), False, repr(bad))
                self.assertIs(m.verify(b"s3cret", b"/download/43", sig), False)
                self.assertIs(m.verify(b"other", b"/download/42", sig), False)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

WEBHOOK = dd(r'''
    """Receiving signed webhooks."""
    import hashlib
    import hmac


    def sign_webhook(secret, timestamp, body):
        """The signature a sender attaches: lowercase hex HMAC-SHA256 under `secret` (bytes) over `body` (bytes). `timestamp` (int, seconds) travels in the `X-Timestamp` header."""
        return hmac.new(secret, body, hashlib.sha256).hexdigest()


    def verify_webhook(secret, timestamp, body, signature, now, tolerance=300):
        """True when the request is genuine and fresh: the signature is valid *and covers the timestamp*, and `timestamp` is within `tolerance` seconds of `now` (either direction, limit included),
        so a captured request cannot be replayed later and its timestamp cannot be refreshed. A timestamp that is not an int, or a malformed signature, gives False."""
        expected = sign_webhook(secret, timestamp, body)
        return hmac.compare_digest(expected, signature)
''')

CM.append(dict(
    slug="replayable-webhook", d=3, product="the webhook receiver", func="verify_webhook", cwe="CWE-294",
    finding="`verify_webhook` takes a timestamp but neither signs it nor checks it against the clock, so a captured request can be replayed forever (or with a refreshed `X-Timestamp`), and the freshness guarantee the senders believe in does not exist.",
    start={"hooks.py": WEBHOOK, "README.md": readme("webhooks", "The signed message is `str(timestamp)`, a dot, and the body: `HMAC-SHA256(secret, b\"%d.\" % timestamp + body)` as lowercase hex, which `sign_webhook` returns. `verify_webhook` checks that signature in constant time and that `abs(now - timestamp) <= tolerance`; `bool`, floats, strings and other types as timestamp, and malformed signatures (None, non-ASCII), give False.")},
    solution={"hooks.py": patched(WEBHOOK, (
        '    return hmac.new(secret, body, hashlib.sha256).hexdigest()\n', '    return hmac.new(secret, b"%d." % timestamp + body, hashlib.sha256).hexdigest()\n'), (
        '''    expected = sign_webhook(secret, timestamp, body)
    return hmac.compare_digest(expected, signature)
''', '''    if not isinstance(timestamp, int) or isinstance(timestamp, bool) or not isinstance(signature, str):
        return False
    if abs(now - timestamp) > tolerance:
        return False
    expected = sign_webhook(secret, timestamp, body)
    try:
        return hmac.compare_digest(expected.encode(), signature.encode("ascii"))
    except UnicodeEncodeError:
        return False
'''))},
    hidden={"tests/test_hooks_security.py": _sec.PY_PRELUDE + dd(r'''
        import hashlib
        import hmac

        import hooks as m

        SECRET = b"whsec_abc"
        BODY = b'{"event":"invoice.paid"}'
        NOW = 1_700_000_000


        def reference(ts, body=BODY, secret=SECRET):
            return hmac.new(secret, b"%d." % ts + body, hashlib.sha256).hexdigest()


        class HookTest(unittest.TestCase):
            def test_signing(self):
                self.assertEqual(m.sign_webhook(SECRET, NOW, BODY), reference(NOW))
                self.assertNotEqual(m.sign_webhook(SECRET, NOW, BODY), m.sign_webhook(SECRET, NOW + 1, BODY))

            def test_fresh_requests(self):
                for ts in (NOW, NOW - 1, NOW - 300, NOW + 300, NOW + 5):
                    self.assertIs(m.verify_webhook(SECRET, ts, BODY, reference(ts), NOW), True, ts)
                self.assertIs(m.verify_webhook(SECRET, NOW - 600, BODY, reference(NOW - 600), NOW, tolerance=900), True)

            def test_replays_and_forgeries(self):
                old = NOW - 3600
                self.assertIs(m.verify_webhook(SECRET, old, BODY, reference(old), NOW), False)
                self.assertIs(m.verify_webhook(SECRET, NOW - 301, BODY, reference(NOW - 301), NOW), False)
                self.assertIs(m.verify_webhook(SECRET, NOW + 301, BODY, reference(NOW + 301), NOW), False)
                # the attacker refreshes the timestamp of a captured request
                self.assertIs(m.verify_webhook(SECRET, NOW, BODY, reference(old), NOW), False)
                # a signature over the body alone (what unfixed senders compute) is not enough
                self.assertIs(m.verify_webhook(SECRET, NOW, BODY, hmac.new(SECRET, BODY, hashlib.sha256).hexdigest(), NOW), False)
                self.assertIs(m.verify_webhook(SECRET, NOW, BODY + b" ", reference(NOW), NOW), False)
                self.assertIs(m.verify_webhook(b"other", NOW, BODY, reference(NOW), NOW), False)
                for ts in (str(NOW), float(NOW), None, True):
                    self.assertIs(m.verify_webhook(SECRET, ts, BODY, reference(NOW), NOW), False, repr(ts))
                for sig in (None, "", "é" * 64, reference(NOW)[:-1], 5):
                    self.assertIs(m.verify_webhook(SECRET, NOW, BODY, sig, NOW), False, repr(sig))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

STREAM = dd(r'''
    """Encrypted notes (standard library only)."""
    import hashlib


    def _keystream(key, n):
        block = hashlib.sha256(key).digest()
        return (block * (n // len(block) + 1))[:n]


    def encrypt(key, plaintext):
        """Encrypt the bytes `plaintext` under `key` (bytes); the returned blob is what `decrypt` turns back into the plaintext.

        Required properties: the same message encrypted twice gives different blobs (a fresh random 16-byte nonce is stored at the start of the blob); the blob is authenticated (a 32-byte tag at its end,
        so `len(blob) == len(plaintext) + 48`); the keystream never repeats within a message and is never reused between messages."""
        ks = _keystream(key, len(plaintext))
        return bytes(a ^ b for a, b in zip(plaintext, ks))


    def decrypt(key, blob):
        """The plaintext; ValueError when the blob is too short, was modified in any way, or was made with another key."""
        ks = _keystream(key, len(blob))
        return bytes(a ^ b for a, b in zip(blob, ks))
''')

CM.append(dict(
    slug="stream-cipher-reuse", d=4, product="the encrypted notes store", func="encrypt", cwe="CWE-323",
    finding="`encrypt` XORs every note with the same repeating SHA-256 block of the key: two notes encrypted under one key reveal `p1 xor p2` (two-time pad, one known note decrypts all others), the keystream repeats every 32 bytes, identical notes give identical blobs, and nothing authenticates the blob, so ciphertext can be edited bit by bit.",
    start={"notes_crypto.py": STREAM, "README.md": readme("encrypted notes", "`encrypt(key, plaintext)` / `decrypt(key, blob)` keep their signatures. The blob layout is `nonce (16 random bytes) + ciphertext (same length as the plaintext) + tag (32 bytes)`. Build it encrypt-then-MAC from the standard library only: derive independent encryption and MAC keys from `key` (e.g. with HMAC), generate keystream blocks as `HMAC-SHA256(enc_key, nonce + counter)` (or any other keyed stream construction that never repeats), and compute the tag over nonce and ciphertext with HMAC-SHA256, compared in constant time. `decrypt` raises `ValueError` for blobs shorter than 48 bytes, for any modified byte, and for a wrong key.")},
    solution={"notes_crypto.py": dd(r'''
        """Encrypted notes (standard library only)."""
        import hashlib
        import hmac
        import secrets


        def _keys(key):
            return hmac.new(key, b"enc", hashlib.sha256).digest(), hmac.new(key, b"mac", hashlib.sha256).digest()


        def _keystream(enc_key, nonce, n):
            out = bytearray()
            counter = 0
            while len(out) < n:
                out += hmac.new(enc_key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
                counter += 1
            return bytes(out[:n])


        def encrypt(key, plaintext):
            """Encrypt the bytes `plaintext` under `key` (bytes); the returned blob is what `decrypt` turns back into the plaintext.

            Required properties: the same message encrypted twice gives different blobs (a fresh random 16-byte nonce is stored at the start of the blob); the blob is authenticated (a 32-byte tag at its end,
            so `len(blob) == len(plaintext) + 48`); the keystream never repeats within a message and is never reused between messages."""
            enc_key, mac_key = _keys(key)
            nonce = secrets.token_bytes(16)
            body = bytes(a ^ b for a, b in zip(plaintext, _keystream(enc_key, nonce, len(plaintext))))
            tag = hmac.new(mac_key, nonce + body, hashlib.sha256).digest()
            return nonce + body + tag


        def decrypt(key, blob):
            """The plaintext; ValueError when the blob is too short, was modified in any way, or was made with another key."""
            if len(blob) < 48:
                raise ValueError("blob too short")
            enc_key, mac_key = _keys(key)
            nonce, body, tag = blob[:16], blob[16:-32], blob[-32:]
            if not hmac.compare_digest(tag, hmac.new(mac_key, nonce + body, hashlib.sha256).digest()):
                raise ValueError("authentication failed")
            return bytes(a ^ b for a, b in zip(body, _keystream(enc_key, nonce, len(body))))
    ''')},
    hidden={"tests/test_notes_crypto_security.py": _sec.PY_PRELUDE + dd(r'''
        import notes_crypto as m

        KEY = b"0123456789abcdef0123456789abcdef"


        def xor(a, b):
            return bytes(x ^ y for x, y in zip(a, b))


        class CryptoTest(unittest.TestCase):
            def test_roundtrip_and_layout(self):
                for n in (0, 1, 15, 16, 17, 31, 32, 33, 64, 100, 1000):
                    pt = bytes(range(256)) * (n // 256 + 1)
                    pt = pt[:n]
                    blob = m.encrypt(KEY, pt)
                    self.assertEqual(len(blob), n + 48, n)
                    self.assertEqual(m.decrypt(KEY, blob), pt)

            def test_fresh_nonce_each_time(self):
                a, b = m.encrypt(KEY, b"same message"), m.encrypt(KEY, b"same message")
                self.assertNotEqual(a, b)
                self.assertNotEqual(a[:16], b[:16])
                self.assertNotEqual(a[16:-32], b[16:-32])

            def test_no_two_time_pad(self):
                p1, p2 = b"A" * 200, b"B" * 200
                c1, c2 = m.encrypt(KEY, p1)[16:-32], m.encrypt(KEY, p2)[16:-32]
                self.assertNotEqual(xor(c1, c2), xor(p1, p2))

            def test_keystream_does_not_repeat(self):
                ct = m.encrypt(KEY, b"\x00" * 320)[16:-32]
                blocks = [ct[i:i + 32] for i in range(0, 320, 32)]
                self.assertEqual(len(set(blocks)), 10)
                self.assertGreater(len(set(ct)), 100)

            def test_tampering_is_detected(self):
                blob = m.encrypt(KEY, b"transfer 100 to bob")
                for pos in [0, 7, 15, 16, 20, len(blob) - 33, len(blob) - 32, len(blob) - 17, len(blob) - 1]:
                    bad = bytearray(blob)
                    bad[pos] ^= 0x01
                    self.assertIsNone(attempt(m.decrypt, KEY, bytes(bad)), pos)
                self.assertIsNone(attempt(m.decrypt, KEY, blob[:-1]))
                self.assertIsNone(attempt(m.decrypt, KEY, blob + b"\x00"))
                self.assertIsNone(attempt(m.decrypt, b"other key", blob))
                for short in (b"", b"x" * 47):
                    self.assertIsNone(attempt(m.decrypt, KEY, short))
                self.assertEqual(m.decrypt(KEY, blob), b"transfer 100 to bob")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

CM_ORDER = ["hash-prefix-mac", "replayable-webhook", "stream-cipher-reuse"]
CM.sort(key=lambda s: (s["d"], CM_ORDER.index(s["slug"])))


@family("security-crypto-misuse", category="security", lang="python", kind="fix", n=3,
        summary="cryptographic misuse: hash(secret+msg) MACs, unsigned timestamps, stream cipher nonce reuse without authentication")
def gen_crypto(rng, n):
    return list(_sec.emit(rng, CM[:n], tags=["crypto"]))
