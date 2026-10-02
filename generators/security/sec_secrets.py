"""Security families: secrets in repositories, logs and scanners; and abuse limits (throttling, size limits, forwarded headers, code attempts).
All secrets that appear in these tasks are made up; the tests build token-shaped strings at run time from fragments."""
from fx import dd, family

from . import _sec
from ._sec import patched, readme

P = _sec.PY_PRELUDE

SCAN = P + dd(r'''
    def repo_files():
        """(relative path, text) of every file of the repository except tests, caches and VCS data."""
        out = []
        for dirpath, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in ("tests", ".git", "__pycache__", "node_modules")]
            for name in files:
                path = os.path.join(dirpath, name)
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as fh:
                        out.append((os.path.relpath(path, ROOT), fh.read()))
                except OSError:
                    pass
        return out


    def leaked(values):
        """[(path, value)] for every secret value that still appears in a repository file."""
        return [(path, v) for path, text in repo_files() for v in values if v in text]


''')

# =================================================================================================================================
#  secrets in repositories, logs and scanners
# =================================================================================================================================
SK = []

KEY = "pgw_9f2c71ab33de4c0b8a17e5d6"
PAYMENTS = dd(r'''
    """Client of the payment gateway."""

    API_KEY = "KEYVALUE"
    BASE_URL = "https://pay.example.net/api"


    def auth_header():
        """Headers for gateway requests: `{"Authorization": "Bearer <key>"}`."""
        return {"Authorization": "Bearer " + API_KEY}
'''.replace("KEYVALUE", KEY))

SK.append(dict(
    slug="hardcoded-api-key", d=1, product="the payment gateway client", func="auth_header", cwe="CWE-798",
    finding=f"the live gateway key `{KEY}` is hard-coded in `payments.py`, and pasted into the README and `scripts/smoke.sh` as well; everybody with read access to the repository (and every fork, CI log and backup) holds a working production credential.",
    extra="Remove it from every file in the repository (a rotated key will be issued separately). Importing the module must keep working without the variable being set.",
    start={"payments.py": PAYMENTS,
           "scripts/smoke.sh": f'#!/bin/sh\n# quick check against the gateway\ncurl -s -H "Authorization: Bearer {KEY}" https://pay.example.net/api/ping\n',
           "README.md": readme("payments client", f"`auth_header()` returns the `Authorization` header for gateway requests. Configuration: the API key comes from the environment variable `PAYMENTS_API_KEY`, read each time the header is built (not at import time); if it is missing or empty a `RuntimeError` naming the variable is raised. `.env.example` lists the variable without a value. Example call: `curl -H \"Authorization: Bearer {KEY}\" https://pay.example.net/api/ping`.")},
    solution={"payments.py": dd(r'''
        """Client of the payment gateway."""
        import os

        BASE_URL = "https://pay.example.net/api"


        def auth_header():
            """Headers for gateway requests: `{"Authorization": "Bearer <key>"}`."""
            key = os.environ.get("PAYMENTS_API_KEY", "")
            if not key:
                raise RuntimeError("PAYMENTS_API_KEY is not set")
            return {"Authorization": "Bearer " + key}
    '''),
              "scripts/smoke.sh": '#!/bin/sh\n# quick check against the gateway (needs PAYMENTS_API_KEY in the environment)\ncurl -s -H "Authorization: Bearer ${PAYMENTS_API_KEY}" https://pay.example.net/api/ping\n',
              ".env.example": "PAYMENTS_API_KEY=\n",
              "README.md": readme("payments client", "`auth_header()` returns the `Authorization` header for gateway requests. Configuration: the API key comes from the environment variable `PAYMENTS_API_KEY`, read each time the header is built (not at import time); if it is missing or empty a `RuntimeError` naming the variable is raised. `.env.example` lists the variable without a value. Example call: `curl -H \"Authorization: Bearer $PAYMENTS_API_KEY\" https://pay.example.net/api/ping`.")},
    hidden={"tests/test_payments_security.py": SCAN + dd(r'''
        import payments as m

        KEY = "pgw_9f2c71ab33de4c0b8a17e5d6"


        class PaymentsTest(unittest.TestCase):
            def setUp(self):
                self.saved = os.environ.pop("PAYMENTS_API_KEY", None)

            def tearDown(self):
                os.environ.pop("PAYMENTS_API_KEY", None)
                if self.saved is not None:
                    os.environ["PAYMENTS_API_KEY"] = self.saved

            def test_key_comes_from_the_environment(self):
                os.environ["PAYMENTS_API_KEY"] = "env-key-1"
                self.assertEqual(m.auth_header(), {"Authorization": "Bearer env-key-1"})
                os.environ["PAYMENTS_API_KEY"] = "env-key-2"
                self.assertEqual(m.auth_header(), {"Authorization": "Bearer env-key-2"})

            def test_missing_key_is_an_error(self):
                for value in (None, ""):
                    if value is not None:
                        os.environ["PAYMENTS_API_KEY"] = value
                    with self.assertRaises(RuntimeError) as ctx:
                        m.auth_header()
                    self.assertIn("PAYMENTS_API_KEY", str(ctx.exception))
                    self.assertNotIn(KEY, str(ctx.exception))

            def test_repository_is_clean(self):
                self.assertEqual(leaked([KEY, KEY[4:]]), [])
                example = dict(repo_files()).get(".env.example")
                self.assertIsNotNone(example, ".env.example is missing")
                lines = [ln.strip() for ln in example.splitlines() if ln.strip() and not ln.startswith("#")]
                values = [ln.split("=", 1)[1] for ln in lines if ln.startswith("PAYMENTS_API_KEY=")]
                self.assertEqual(len(values), 1)
                self.assertLessEqual(len(values[0]), 12)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

ENV_VALUES = ["Zq8!mR4vT2xK9pLw", "4f0c9a2e7b1d3c5a8e6f0b2d4c6e8a1b", "smtp-Pa55-9xQ2vL7m"]
ENVFILE = "DEBUG=false\nDB_HOST=db.internal\nDB_PASSWORD=%s\nSECRET_KEY=%s\nSMTP_PASSWORD=%s\n" % tuple(ENV_VALUES)
LOADER = dd(r'''
    """Settings of the web app, read from a `.env` file and the environment (the environment wins)."""


    def parse_env(text):
        """KEY=VALUE lines of an env file as a dict. Blank lines and `#` comments are skipped, an optional `export ` prefix is allowed, and values may be wrapped in single or double quotes."""
        values = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            key, sep, value = line.partition("=")
            if not sep:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            values[key.strip()] = value
        return values


    def load_settings(env_path, environ):
        """The settings dict: values from the env file at `env_path` (if it exists), overridden by `environ`; only the keys DEBUG, DB_HOST, DB_PASSWORD, SECRET_KEY and SMTP_PASSWORD are used.
        DB_PASSWORD, SECRET_KEY and SMTP_PASSWORD are required: a missing or empty one raises RuntimeError naming it. DEBUG is the boolean `value.lower() == "true"` (default False)."""
        try:
            with open(env_path, encoding="utf-8") as fh:
                values = parse_env(fh.read())
        except FileNotFoundError:
            values = {}
        values.update({k: v for k, v in environ.items() if k in KEYS})
        for name in ("DB_PASSWORD", "SECRET_KEY", "SMTP_PASSWORD"):
            if not values.get(name):
                raise RuntimeError(name + " is not set")
        return {"debug": values.get("DEBUG", "").lower() == "true", "db_host": values.get("DB_HOST", "localhost"), "db_password": values["DB_PASSWORD"],
                "secret_key": values["SECRET_KEY"], "smtp_password": values["SMTP_PASSWORD"]}


    KEYS = ("DEBUG", "DB_HOST", "DB_PASSWORD", "SECRET_KEY", "SMTP_PASSWORD")
''')

SK.append(dict(
    slug="committed-env-file", d=2, product="the web app", func="load_settings", cwe="CWE-540",
    finding="the repository contains the production `.env` (database password, signing key and SMTP password) and has no `.gitignore`, so every clone has the secrets and the next `git add .` commits the next ones.",
    extra="Keep the loader's behaviour: it must still read a local `.env` when one exists.",
    start={".env": ENVFILE, "settings_loader.py": LOADER, "README.md": readme("web app settings", "Settings come from a local `.env` file (never committed) and the environment. The repository ships `.env.example` with all five keys - `DEBUG` and `DB_HOST` with their harmless defaults, the three secret keys with empty values - and `.gitignore` lists `.env`, so real secrets cannot be committed by accident. `load_settings` is unchanged.")},
    solution={".env": "DEBUG=false\nDB_HOST=db.internal\nDB_PASSWORD=\nSECRET_KEY=\nSMTP_PASSWORD=\n", ".env.example": "DEBUG=false\nDB_HOST=db.internal\nDB_PASSWORD=\nSECRET_KEY=\nSMTP_PASSWORD=\n", ".gitignore": ".env\n__pycache__/\n"},
    hidden={"tests/test_settings_loader_security.py": SCAN + dd(r'''
        import settings_loader as m

        SECRETS = ["Zq8!mR4vT2xK9pLw", "4f0c9a2e7b1d3c5a8e6f0b2d4c6e8a1b", "smtp-Pa55-9xQ2vL7m"]


        class SettingsTest(unittest.TestCase):
            def test_loader_still_works(self):
                d = tmpdir()
                self.addCleanup(shutil.rmtree, d, True)
                path = os.path.join(d, ".env")
                write(path, "# comment\nexport DEBUG=TRUE\nDB_HOST='db.example'\nDB_PASSWORD=\"p w\"\nSECRET_KEY=k\nSMTP_PASSWORD=s\nJUNK\n")
                got = m.load_settings(path, {"SECRET_KEY": "from-env", "OTHER": "x"})
                self.assertEqual(got, {"debug": True, "db_host": "db.example", "db_password": "p w", "secret_key": "from-env", "smtp_password": "s"})
                got = m.load_settings(os.path.join(d, "missing.env"), {"DB_PASSWORD": "a", "SECRET_KEY": "b", "SMTP_PASSWORD": "c"})
                self.assertEqual(got, {"debug": False, "db_host": "localhost", "db_password": "a", "secret_key": "b", "smtp_password": "c"})
                with self.assertRaises(RuntimeError) as ctx:
                    m.load_settings(os.path.join(d, "missing.env"), {"DB_PASSWORD": "a", "SECRET_KEY": "", "SMTP_PASSWORD": "c"})
                self.assertIn("SECRET_KEY", str(ctx.exception))

            def test_secrets_are_not_in_the_repository(self):
                self.assertEqual(leaked(SECRETS), [])

            def test_gitignore_and_example(self):
                files = dict(repo_files())
                self.assertIn(".gitignore", files)
                self.assertIn(".env", [ln.strip() for ln in files[".gitignore"].splitlines()])
                self.assertIn(".env.example", files)
                example = m.parse_env(files[".env.example"])
                self.assertEqual(set(example), {"DEBUG", "DB_HOST", "DB_PASSWORD", "SECRET_KEY", "SMTP_PASSWORD"})
                for key in ("DB_PASSWORD", "SECRET_KEY", "SMTP_PASSWORD"):
                    self.assertIn(example[key], ("", "changeme"), key)
                self.assertEqual(example["DB_HOST"], "db.internal")
                if ".env" in files:
                    for key in ("DB_PASSWORD", "SECRET_KEY", "SMTP_PASSWORD"):
                        self.assertIn(m.parse_env(files[".env"]).get(key, ""), ("", "changeme"), key)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

INI_PASSWORD = "S3cr3t-Pa55w0rd"
DBCONF = dd(r'''
    """Database configuration of the reporting service."""
    import configparser


    def get_db_url(path, environ=None):
        """The database URL of the `[db] url` entry of the ini file at `path`. The URL in the file carries the user name but *not* the password (`postgres://app@host:5432/shop`): when it has a user
        and no password, the password is taken from `environ["DB_PASSWORD"]` and inserted percent-encoded (everything except letters, digits and `_.-~`) - RuntimeError when it is missing or empty.
        URLs without a user name are returned as they are. `environ` defaults to os.environ."""
        parser = configparser.ConfigParser()
        parser.read(path)
        return parser["db"]["url"]
''')

SK.append(dict(
    slug="password-in-db-url", d=2, product="the reporting service", func="get_db_url", cwe="CWE-798",
    finding=f"`config.ini` (committed) contains the database URL with its password (`postgres://app:{INI_PASSWORD}@db.internal:5432/shop`), so the production database password is in the repository and in every checkout that only needed the host name.",
    start={"config.ini": f"[db]\nurl = postgres://app:{INI_PASSWORD}@db.internal:5432/shop\npool = 5\n", "dbconf.py": DBCONF,
           "README.md": readme("reporting service", "`get_db_url(path, environ=None)` returns the connection URL. The committed `config.ini` holds the URL without the password (`postgres://app@db.internal:5432/shop`); the password is supplied by the deployment in `DB_PASSWORD` and inserted by `get_db_url` as its docstring says.")},
    solution={"config.ini": "[db]\nurl = postgres://app@db.internal:5432/shop\npool = 5\n", "dbconf.py": dd(r'''
        """Database configuration of the reporting service."""
        import configparser
        import os
        from urllib.parse import quote, urlsplit


        def get_db_url(path, environ=None):
            """The database URL of the `[db] url` entry of the ini file at `path`. The URL in the file carries the user name but *not* the password (`postgres://app@host:5432/shop`): when it has a user
            and no password, the password is taken from `environ["DB_PASSWORD"]` and inserted percent-encoded (everything except letters, digits and `_.-~`) - RuntimeError when it is missing or empty.
            URLs without a user name are returned as they are. `environ` defaults to os.environ."""
            environ = os.environ if environ is None else environ
            parser = configparser.ConfigParser()
            parser.read(path)
            url = parser["db"]["url"]
            parts = urlsplit(url)
            if parts.username is None or parts.password is not None:
                return url
            password = environ.get("DB_PASSWORD", "")
            if not password:
                raise RuntimeError("DB_PASSWORD is not set")
            userinfo = parts.username + ":" + quote(password, safe="")
            return url.replace("//" + parts.username + "@", "//" + userinfo + "@", 1)
    ''')},
    hidden={"tests/test_dbconf_security.py": SCAN + dd(r'''
        import dbconf as m

        PASSWORD = "S3cr3t-Pa55w0rd"


        class DbConfTest(unittest.TestCase):
            def make(self, url):
                d = tmpdir()
                self.addCleanup(shutil.rmtree, d, True)
                path = os.path.join(d, "c.ini")
                write(path, "[db]\nurl = %s\npool = 5\n" % url)
                return path

            def test_password_is_injected_encoded(self):
                path = self.make("postgres://app@db.internal:5432/shop")
                self.assertEqual(m.get_db_url(path, {"DB_PASSWORD": "p@ss:w/rd#1 %"}), "postgres://app:p%40ss%3Aw%2Frd%231%20%25@db.internal:5432/shop")
                self.assertEqual(m.get_db_url(path, {"DB_PASSWORD": "simple-1.x_y~"}), "postgres://app:simple-1.x_y~@db.internal:5432/shop")
                for env in ({}, {"DB_PASSWORD": ""}):
                    with self.assertRaises(RuntimeError) as ctx:
                        m.get_db_url(path, env)
                    self.assertIn("DB_PASSWORD", str(ctx.exception))
                os.environ["DB_PASSWORD"] = "from-os"
                try:
                    self.assertEqual(m.get_db_url(path), "postgres://app:from-os@db.internal:5432/shop")
                finally:
                    del os.environ["DB_PASSWORD"]

            def test_urls_without_user_are_untouched(self):
                path = self.make("postgres://db.internal/shop")
                self.assertEqual(m.get_db_url(path, {}), "postgres://db.internal/shop")
                path = self.make("sqlite:///data/app.db")
                self.assertEqual(m.get_db_url(path, {"DB_PASSWORD": "x"}), "sqlite:///data/app.db")

            def test_committed_config(self):
                self.assertEqual(leaked([PASSWORD]), [])
                ini = os.path.join(ROOT, "config.ini")
                self.assertEqual(m.get_db_url(ini, {"DB_PASSWORD": "pw"}), "postgres://app:pw@db.internal:5432/shop")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

REDACT = dd(r'''
    """Startup logging of the effective configuration."""


    def redact(value):
        """A copy of the configuration `value` (dicts, lists, tuples, strings, numbers, None) that is safe to log:

        * the value of every dict key that contains (case-insensitive) `password`, `passwd`, `secret`, `token`, `apikey`, `api_key`, `credential` or `private_key` is replaced by the string `"***"`,
          whatever it is (a string, a dict, a list); other keys are untouched;
        * strings that are URLs with a password (`scheme://user:password@host/...`) keep everything except the password, which becomes `***`;
        * dicts, lists and tuples are processed recursively and keep their type; the input is never modified."""
        return value
''')

SK.append(dict(
    slug="config-in-logs", d=3, product="the service startup log", func="redact", cwe="CWE-532",
    finding="the startup code logs the effective configuration with `log.info(\"config: %s\", config)`; the dump contains the database URL with its password, API tokens and the signing key, and the log files are shipped to a third-party aggregator that every developer can search.",
    start={"redaction.py": REDACT, "README.md": readme("config logging", "`redact(value)` returns the loggable copy of a configuration as described in its docstring: secret-looking keys at any depth have the value `\"***\"`, URL passwords are masked, structure and types are preserved, the argument is not mutated. Strings that are not URLs with passwords, and values under harmless keys, come back unchanged.")},
    solution={"redaction.py": dd(r'''
        """Startup logging of the effective configuration."""
        import re

        SENSITIVE = ("password", "passwd", "secret", "token", "apikey", "api_key", "credential", "private_key")
        URL_PASSWORD = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]*:)[^/\s@]*(@)")


        def redact(value):
            """A copy of the configuration `value` (dicts, lists, tuples, strings, numbers, None) that is safe to log:

            * the value of every dict key that contains (case-insensitive) `password`, `passwd`, `secret`, `token`, `apikey`, `api_key`, `credential` or `private_key` is replaced by the string `"***"`,
              whatever it is (a string, a dict, a list); other keys are untouched;
            * strings that are URLs with a password (`scheme://user:password@host/...`) keep everything except the password, which becomes `***`;
            * dicts, lists and tuples are processed recursively and keep their type; the input is never modified."""
            if isinstance(value, dict):
                return {k: "***" if isinstance(k, str) and any(s in k.lower() for s in SENSITIVE) else redact(v) for k, v in value.items()}
            if isinstance(value, list):
                return [redact(v) for v in value]
            if isinstance(value, tuple):
                return tuple(redact(v) for v in value)
            if isinstance(value, str):
                return URL_PASSWORD.sub(r"\1***\2", value)
            return value
    ''')},
    hidden={"tests/test_redaction_security.py": P + dd(r'''
        import copy

        import redaction as m


        class RedactTest(unittest.TestCase):
            def test_keys(self):
                cfg = {"host": "db", "port": 5432, "DB_PASSWORD": "hunter2", "api_key": "abc", "ApiKey": "x", "auth_token": {"a": 1}, "secrets": ["a", "b"], "Credentials": None, "private_key": "-----", "passwd": 5,
                       "nested": {"smtp": {"password": "p", "user": "u"}, "items": [{"token": "t", "name": "n"}, ("x", {"secret": "s"})]}, "debug": True, "ratio": 0.5, "none": None}
                before = copy.deepcopy(cfg)
                out = m.redact(cfg)
                self.assertEqual(cfg, before)
                self.assertEqual(out["host"], "db")
                self.assertEqual(out["port"], 5432)
                for key in ("DB_PASSWORD", "api_key", "ApiKey", "auth_token", "secrets", "Credentials", "private_key", "passwd"):
                    self.assertEqual(out[key], "***", key)
                self.assertEqual(out["nested"]["smtp"], {"password": "***", "user": "u"})
                self.assertEqual(out["nested"]["items"][0], {"token": "***", "name": "n"})
                self.assertEqual(out["nested"]["items"][1], ("x", {"secret": "***"}))
                self.assertIsInstance(out["nested"]["items"][1], tuple)
                self.assertEqual((out["debug"], out["ratio"], out["none"]), (True, 0.5, None))
                self.assertNotIn("hunter2", repr(out))

            def test_urls(self):
                self.assertEqual(m.redact("postgres://app:S3cr3t@db.internal:5432/shop"), "postgres://app:***@db.internal:5432/shop")
                self.assertEqual(m.redact("amqp://guest:g%40st@mq/vhost?x=1"), "amqp://guest:***@mq/vhost?x=1")
                self.assertEqual(m.redact({"urls": ["redis://:pw@cache:6379/0", "https://user:pw@example.com/a"]}), {"urls": ["redis://:***@cache:6379/0", "https://user:***@example.com/a"]})
                for plain in ["https://example.com/a:b@c", "postgres://app@db/shop", "no url here", "user:pass@host", "", "http://host:8080/path"]:
                    self.assertEqual(m.redact(plain), plain)
                self.assertEqual(m.redact([1, "a", None]), [1, "a", None])
                self.assertEqual(m.redact(7), 7)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SCANNER = dd(r'''
    """Pre-commit secret scanner."""
    import re

    RULES = [("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}"))]


    def scan_text(text):
        """Findings in `text`: a list of `{"line": n, "rule": name}` (line numbers start at 1), sorted by line and then by rule name; at most one finding per rule and line.

        Rules: `aws-access-key` - `AKIA` or `ASIA` followed by 16 upper-case letters or digits; `private-key` - a PEM header `-----BEGIN [<WORDS> ]PRIVATE KEY-----` (RSA, EC, OPENSSH, ENCRYPTED...,
        but not PUBLIC KEY); `github-token` - `ghp_`, `gho_`, `ghu_`, `ghs_` or `ghr_` followed by 36 or more letters and digits; `slack-token` - `xoxb-`, `xoxa-`, `xoxp-`, `xoxr-` or `xoxs-`
        followed by 10 or more letters, digits and hyphens; `generic-password` - an assignment (`=` or `:`) of a quoted string of 8 or more characters to a name that contains (case-insensitive)
        `password`, `passwd`, `secret`, `api_key`, `apikey` or `token`, unless the value is a placeholder: it contains `example`, `changeme`, `placeholder`, `dummy` or `redacted` (any case),
        consists of one repeated character (`xxxxxxxx`, `********`), or is wrapped as `<...>`, `${...}` or `{{...}}`."""
        findings = []
        for number, line in enumerate(text.splitlines(), start=1):
            for name, pattern in RULES:
                if pattern.search(line):
                    findings.append({"line": number, "rule": name})
        return findings
''')

FAKE = dd(r'''
    AWS = "AKIA" + "IOSFODNN7EXAMPLE"
    AWS_TEMP = "ASIA" + "Z7MQ4N2LKW8VXT3R"
    GH = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    SLACK = "xoxb-" + "123456789012-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx"
    PEM = "-----BEGIN RSA " + "PRIVATE KEY-----"
    PEM_PLAIN = "-----BEGIN " + "PRIVATE KEY-----"
    assert len(GH) == 40 and len(AWS) == 20 and len(AWS_TEMP) == 20


    def rules(text):
        return [(f["line"], f["rule"]) for f in scanner.scan_text(text)]


''')

SK.append(dict(
    slug="scanner-rules", d=3, product="the pre-commit secret scanner", func="scan_text", cwe="CWE-798",
    finding="the pre-commit scanner only knows AWS access keys that start with `AKIA`: private keys, GitHub and Slack tokens, temporary `ASIA` credentials and `password = \"...\"` literals sail through, which is how two leaked tokens reached the main branch last quarter.",
    start={"scanner.py": SCANNER, "README.md": readme("secret scanner", "`scan_text(text)` implements every rule listed in its docstring, with those exact rule names. Placeholders such as `changeme`, `<your-token>`, `${DB_PASSWORD}` or `xxxxxxxx`, values shorter than 8 characters, environment lookups (`os.environ[...]`, which are not quoted literals), `PUBLIC KEY` headers and short `ghp_` look-alikes must **not** be reported. The result is deterministic: sorted by line, then rule name.")},
    solution={"scanner.py": dd(r'''
        """Pre-commit secret scanner."""
        import re

        NAME = r"[A-Za-z_][A-Za-z0-9_.-]*"
        SENSITIVE = ("password", "passwd", "secret", "api_key", "apikey", "token")
        ASSIGN = re.compile(r"(" + NAME + r")[\"']?\]?\s*[=:]\s*(?:\"([^\"]*)\"|'([^']*)')")
        PLACEHOLDER_WORDS = ("example", "changeme", "placeholder", "dummy", "redacted")

        RULES = [
            ("aws-access-key", re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}")),
            ("private-key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")),
            ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
            ("slack-token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
        ]


        def _placeholder(value):
            low = value.lower()
            return (any(w in low for w in PLACEHOLDER_WORDS) or len(set(value)) == 1 or (value.startswith("<") and value.endswith(">"))
                    or (value.startswith("${") and value.endswith("}")) or (value.startswith("{{") and value.endswith("}}")))


        def _generic(line):
            for match in ASSIGN.finditer(line):
                name = match.group(1).lower()
                value = match.group(2) if match.group(2) is not None else match.group(3)
                if any(s in name for s in SENSITIVE) and len(value) >= 8 and not _placeholder(value):
                    return True
            return False


        def scan_text(text):
            """Findings in `text`: a list of `{"line": n, "rule": name}` (line numbers start at 1), sorted by line and then by rule name; at most one finding per rule and line.

            Rules: `aws-access-key` - `AKIA` or `ASIA` followed by 16 upper-case letters or digits; `private-key` - a PEM header `-----BEGIN [<WORDS> ]PRIVATE KEY-----` (RSA, EC, OPENSSH, ENCRYPTED...,
            but not PUBLIC KEY); `github-token` - `ghp_`, `gho_`, `ghu_`, `ghs_` or `ghr_` followed by 36 or more letters and digits; `slack-token` - `xoxb-`, `xoxa-`, `xoxp-`, `xoxr-` or `xoxs-`
            followed by 10 or more letters, digits and hyphens; `generic-password` - an assignment (`=` or `:`) of a quoted string of 8 or more characters to a name that contains (case-insensitive)
            `password`, `passwd`, `secret`, `api_key`, `apikey` or `token`, unless the value is a placeholder: it contains `example`, `changeme`, `placeholder`, `dummy` or `redacted` (any case),
            consists of one repeated character (`xxxxxxxx`, `********`), or is wrapped as `<...>`, `${...}` or `{{...}}`."""
            findings = []
            for number, line in enumerate(text.splitlines(), start=1):
                names = [name for name, pattern in RULES if pattern.search(line)]
                if _generic(line):
                    names.append("generic-password")
                for name in sorted(names):
                    findings.append({"line": number, "rule": name})
            return findings
    ''')},
    hidden={"tests/test_scanner_security.py": P + dd(r'''
        import scanner

    ''') + FAKE + dd(r'''
        class ScannerTest(unittest.TestCase):
            def test_token_rules(self):
                self.assertEqual(rules("key = x\nid: %s\n" % AWS), [(2, "aws-access-key")])
                self.assertEqual(rules("export AWS_ACCESS_KEY_ID=%s" % AWS_TEMP), [(1, "aws-access-key")])
                self.assertEqual(rules("%s\nabc\n-----END RSA PRIVATE KEY-----\n" % PEM), [(1, "private-key")])
                self.assertEqual(rules(PEM_PLAIN), [(1, "private-key")])
                self.assertEqual(rules("-----BEGIN OPENSSH " + "PRIVATE KEY-----"), [(1, "private-key")])
                self.assertEqual(rules("token %s end" % GH), [(1, "github-token")])
                for prefix in ("gho_", "ghu_", "ghs_", "ghr_"):
                    self.assertEqual(rules(prefix + GH[4:]), [(1, "github-token")], prefix)
                self.assertEqual(rules("curl -H 'Authorization: %s'" % SLACK), [(1, "slack-token")])
                self.assertEqual(rules("a\n\n" + SLACK.replace("xoxb", "xoxp")), [(3, "slack-token")])

            def test_generic_passwords(self):
                for line in ['password = "hunter2hunter2"', "DB_PASSWORD: 'Zq8!mR4vT2xK'", 'config["api_key"] = "k3y-v4lue-0001"', 'secret_token="abcdefgh1234"', "db.passwd = 'longenough1'",
                             '# password = "hunter2hunter2"', 'ApiKey: "AbCdEf123456"', '{"client_secret": "abcdefgh12345"}']:
                    self.assertEqual(rules(line), [(1, "generic-password")], line)

            def test_things_that_are_not_secrets(self):
                for line in ['password = "changeme"', 'password = "short"', 'password = os.environ["DB_PASSWORD"]', 'api_key: "<your-api-key>"', 'token = "${TOKEN}"', 'secret = "xxxxxxxxxxxx"',
                             'secret = "********"', 'password = "{{ vault_password }}"', "-----BEGIN PUBLIC " + "KEY-----", "ghp_tooshort", "AKIA1234", 'password = "Example-Password-1"', 'name = "hello world, this is long"',
                             'token_count = 12345678', 'username = "administrator"', 'password = "PLACEHOLDER-value"', 'secret = "REDACTED-by-ci"', 'AKIA' + 'x' * 16, "xoxb-short", "gh" + "p_" + "a" * 20, ""]:
                    self.assertEqual(rules(line), [], line)

            def test_multiple_findings_and_order(self):
                text = 'password = "hunter2hunter2"  # %s\nok\ntoken = "%s"\n%s\n' % (AWS, GH, PEM)
                self.assertEqual(rules(text), [(1, "aws-access-key"), (1, "generic-password"), (3, "generic-password"), (3, "github-token"), (4, "private-key")])
                self.assertEqual(scanner.scan_text(""), [])
                self.assertEqual(scanner.scan_text("%s %s" % (AWS, AWS_TEMP)), [{"line": 1, "rule": "aws-access-key"}])


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

ENTROPY_SCANNER = SK[-1]["solution"]["scanner.py"]
SK.append(dict(
    slug="scanner-entropy", d=4, product="the pre-commit secret scanner", func="scan_text", cwe="CWE-798",
    finding="the scanner only matches known token formats and `password = ...` names: randomly generated credentials with other names or formats (`session_key = \"q8Zk3VbN7xLp2WmTr9YdFh4JcAs6GeUo\"`) are never reported, and there is no way to silence a reviewed false positive or to skip vendored files, so people disable the hook.",
    extra="The existing rules and their output format must not change.",
    start={"scanner.py": ENTROPY_SCANNER, "README.md": readme("secret scanner", "`scan_text(text, filename=\"\")` gets three additions on top of the existing rules. (1) Rule `high-entropy`: a quoted string of at least 20 characters made only of letters, digits and `+/=_-`, assigned (`=` or `:`) to a name containing `key`, `secret`, `token`, `password` or `passwd` (any case), whose Shannon entropy is at least 3.5 bits per character, that is not a placeholder (same definition as for `generic-password`) and not a UUID (`8-4-4-4-12` hex digits); it is only reported on lines where no other rule matched. (2) A line containing `nosecret` (for example in a `# nosecret` comment) is never reported. (3) Files are skipped entirely (no findings) when `filename` ends with `.lock`, `.min.js` or `package-lock.json`, or has a path component `tests` or `fixtures`. Entropy is `-sum(p * log2(p))` over the characters of the value.")},
    solution={"scanner.py": ENTROPY_SCANNER.replace('"""Pre-commit secret scanner."""\nimport re\n', '"""Pre-commit secret scanner."""\nimport math\nimport re\nfrom collections import Counter\n').replace(
        'PLACEHOLDER_WORDS = ("example", "changeme", "placeholder", "dummy", "redacted")\n',
        '''PLACEHOLDER_WORDS = ("example", "changeme", "placeholder", "dummy", "redacted")
ENTROPY_NAMES = ("key", "secret", "token", "password", "passwd")
ENTROPY_VALUE = re.compile(r"[A-Za-z0-9+/=_-]{20,}")
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
SKIPPED_SUFFIXES = (".lock", ".min.js", "package-lock.json")
''').replace('def scan_text(text):', '''def _entropy(value):
    counts = Counter(value)
    return -sum(c / len(value) * math.log2(c / len(value)) for c in counts.values())


def _high_entropy(line):
    for match in ASSIGN.finditer(line):
        name = match.group(1).lower()
        value = match.group(2) if match.group(2) is not None else match.group(3)
        if (any(s in name for s in ENTROPY_NAMES) and ENTROPY_VALUE.fullmatch(value) and not UUID.fullmatch(value)
                and not _placeholder(value) and _entropy(value) >= 3.5):
            return True
    return False


def scan_text(text, filename=""):''').replace(
        '''    findings = []
    for number, line in enumerate(text.splitlines(), start=1):
        names = [name for name, pattern in RULES if pattern.search(line)]
        if _generic(line):
            names.append("generic-password")
''', '''    path = filename.replace("\\\\", "/")
    if path.endswith(SKIPPED_SUFFIXES) or {"tests", "fixtures"} & set(path.split("/")):
        return []
    findings = []
    for number, line in enumerate(text.splitlines(), start=1):
        if "nosecret" in line:
            continue
        names = [name for name, pattern in RULES if pattern.search(line)]
        if _generic(line):
            names.append("generic-password")
        if not names and _high_entropy(line):
            names.append("high-entropy")
''')},
    hidden={"tests/test_scanner_security.py": P + dd(r'''
        import math
        from collections import Counter

        import scanner

    ''') + FAKE + dd(r'''
        def entropy(value):
            counts = Counter(value)
            return -sum(c / len(value) * math.log2(c / len(value)) for c in counts.values())


        RANDOM = ["q8Zk3VbN7xLp2WmTr9YdFh4JcAs6GeUo", "3f9a1c7e5b2d8a406e1fb9d37c52a84e", "Xk29+Qm7/Lw4Vt8Zc1Nb6Hy3Rj5Pd0Ga==", "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7_-AbC"]
        UUIDS = ["9b2f6c1e-4d7a-4e83-b5a0-3c8d1f7e6a92", "123E4567-E89B-12D3-A456-426614174000"]


        class EntropyTest(unittest.TestCase):
            def test_fixtures_are_what_they_claim(self):
                for v in RANDOM:
                    self.assertGreaterEqual(len(v), 20)
                    self.assertGreater(entropy(v), 3.6, v)
                for v in UUIDS:
                    self.assertGreater(entropy(v), 3.5, v)

            def test_high_entropy_values(self):
                for name in ["session_key", "signing_key", "private_key", "encryption_key", "MASTER_KEY"]:
                    for v in RANDOM:
                        self.assertEqual(rules('%s = "%s"' % (name, v)), [(1, "high-entropy")], (name, v))
                self.assertEqual(rules("x: 1\n{'session_key': '%s'}\n" % RANDOM[0]), [(2, "high-entropy")])

            def test_not_reported(self):
                for v in UUIDS:
                    self.assertEqual(rules('session_key = "%s"' % v), [], v)
                for line in ['session_key = "abcabcabcabcabcabcabcabc"', 'token = "aaaaaaaaaaaaaaaaaaaaaaaa"', 'session_key = "Xk29Qm7Lw4Vt8Zc1Nb6"', 'commit = "%s"' % RANDOM[1], 'name = "%s"' % RANDOM[0],
                             'session_key = "has spaces in it, so it is prose"', 'secret_key = "<%s>"' % RANDOM[0], 'token = "${%s}"' % RANDOM[0], 'api_key = "%sEXAMPLE"' % RANDOM[0][:20], 'key = os.environ["%s"]' % RANDOM[0]]:
                    self.assertEqual(rules(line), [], line)
                self.assertEqual(rules('password = "hunter2hunter2"'), [(1, "generic-password")])
                self.assertEqual(rules('token = "%s"' % GH), [(1, "generic-password"), (1, "github-token")])

            def test_pragma_and_files(self):
                self.assertEqual(rules('api_key = "%s"  # nosecret' % RANDOM[0]), [])
                self.assertEqual(rules('# nosecret\nkey = "%s"' % AWS), [(2, "aws-access-key")])
                self.assertEqual(rules('password = "hunter2hunter2"  # nosecret: reviewed'), [])
                bad = 'password = "hunter2hunter2"\napi_key = "%s"' % RANDOM[0]
                for name in ["yarn.lock", "app.min.js", "web/package-lock.json", "tests/test_x.py", "src/fixtures/data.json", "a/tests/b/c.py", "fixtures/x"]:
                    self.assertEqual(scanner.scan_text(bad, name), [], name)
                for name in ["", "src/app.py", "latest.py", "contests/x.py", "locks.txt", "min.js"]:
                    self.assertEqual([f["line"] for f in scanner.scan_text(bad, name)], [1, 2], name)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SK_ORDER = ["hardcoded-api-key", "committed-env-file", "password-in-db-url", "config-in-logs", "scanner-rules", "scanner-entropy"]
SK.sort(key=lambda s: (s["d"], SK_ORDER.index(s["slug"])))


@family("security-secrets", category="security", lang="python", kind="fix", n=6,
        summary="secrets in repositories and logs: hard-coded keys, committed env files, URL passwords, log redaction, secret scanners")
def gen_secrets(rng, n):
    return list(_sec.emit(rng, SK[:n], tags=["secrets"]))


# =================================================================================================================================
#  abuse limits
# =================================================================================================================================
AB = []

GUARD = dd(r'''
    """Brute-force protection for the login form."""
    import time


    class LoginGuard:
        MAX_FAILURES = 5
        WINDOW = 900
        LOCKOUT = 900

        def __init__(self, clock=time.time):
            self.clock = clock
            self.failures = {}

        def allowed(self, user):
            """False while `user` is locked out, True otherwise. User names are compared case-insensitively. A user is locked out for LOCKOUT seconds after their MAX_FAILURES-th failed attempt
            within WINDOW seconds (failures older than WINDOW seconds no longer count; a failure exactly WINDOW seconds old still counts). While locked out, further attempts do not extend the lockout;
            when it ends the failure count starts again from zero."""
            return True

        def record(self, user, success):
            """Register the outcome of a login attempt. A success clears the user's failures (it cannot happen during a lockout)."""
            self.failures.setdefault(user, []).append(self.clock())
''')

AB.append(dict(
    slug="login-lockout", d=2, product="the login form", func="LoginGuard.allowed", cwe="CWE-307",
    finding="`LoginGuard` is wired into the login handler but `allowed` always answers True and `record` only appends timestamps forever: there is no limit on password guesses per account, so credential stuffing and brute force run unthrottled.",
    start={"guard.py": GUARD, "README.md": readme("login guard", "Implement the rules in the `allowed` docstring. Time comes from `clock`; a lockout starts at the time of the failing attempt that reached MAX_FAILURES and lasts LOCKOUT seconds (it is over when `now - start >= LOCKOUT`). The login handler calls `allowed(user)` before checking the password and `record(user, success)` afterwards; recording while locked out must not change the lockout.")},
    solution={"guard.py": dd(r'''
        """Brute-force protection for the login form."""
        import time


        class LoginGuard:
            MAX_FAILURES = 5
            WINDOW = 900
            LOCKOUT = 900

            def __init__(self, clock=time.time):
                self.clock = clock
                self.failures = {}
                self.locked_since = {}

            def allowed(self, user):
                """False while `user` is locked out, True otherwise. User names are compared case-insensitively. A user is locked out for LOCKOUT seconds after their MAX_FAILURES-th failed attempt
                within WINDOW seconds (failures older than WINDOW seconds no longer count; a failure exactly WINDOW seconds old still counts). While locked out, further attempts do not extend the lockout;
                when it ends the failure count starts again from zero."""
                user = user.lower()
                since = self.locked_since.get(user)
                if since is None:
                    return True
                if self.clock() - since >= self.LOCKOUT:
                    del self.locked_since[user]
                    self.failures.pop(user, None)
                    return True
                return False

            def record(self, user, success):
                """Register the outcome of a login attempt. A success clears the user's failures (it cannot happen during a lockout)."""
                user = user.lower()
                if not self.allowed(user):
                    return
                if success:
                    self.failures.pop(user, None)
                    return
                now = self.clock()
                recent = [t for t in self.failures.get(user, []) if now - t <= self.WINDOW]
                recent.append(now)
                self.failures[user] = recent
                if len(recent) >= self.MAX_FAILURES:
                    self.locked_since[user] = now
    ''')},
    hidden={"tests/test_guard_security.py": P + dd(r'''
        import guard as m


        class Clock:
            def __init__(self):
                self.t = 5000.0

            def __call__(self):
                return self.t


        class GuardTest(unittest.TestCase):
            def setUp(self):
                self.c = Clock()
                self.g = m.LoginGuard(clock=self.c)

            def fail(self, user, n=1):
                for _ in range(n):
                    self.assertTrue(self.g.allowed(user))
                    self.g.record(user, False)

            def test_lockout_after_five_failures(self):
                self.fail("ann", 4)
                self.assertTrue(self.g.allowed("ann"))
                self.g.record("ann", False)
                self.assertFalse(self.g.allowed("ann"))
                self.assertFalse(self.g.allowed("ANN"))
                self.assertTrue(self.g.allowed("bob"))
                self.c.t += 899
                self.assertFalse(self.g.allowed("ann"))
                self.g.record("ann", False)
                self.g.record("ann", True)
                self.c.t += 1
                self.assertTrue(self.g.allowed("ann"))
                self.fail("ann", 4)
                self.assertTrue(self.g.allowed("ann"))

            def test_window_and_success_reset(self):
                self.fail("ann", 3)
                self.c.t += 901
                self.fail("ann", 4)
                self.assertTrue(self.g.allowed("ann"))
                self.fail("bob", 4)
                self.g.record("bob", True)
                self.fail("bob", 4)
                self.assertTrue(self.g.allowed("bob"))
                self.g.record("bob", False)
                self.assertFalse(self.g.allowed("bob"))
                for user in ("cat", "Dan"):
                    self.fail(user, 2)
                    self.c.t += 450
                    self.fail(user, 2)
                    self.c.t += 450
                    self.assertTrue(self.g.allowed(user))
                    self.g.record(user, False)
                    self.assertFalse(self.g.allowed(user), user)

            def test_case_insensitive(self):
                for name in ["Eve", "eVE", "EVE", "eve", "Eve"]:
                    self.g.record(name, False)
                self.assertFalse(self.g.allowed("eve"))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

UPLOAD = dd(r'''
    """Upload handling of the import endpoint."""
    import csv
    import io

    MAX_BYTES = 1_048_576
    MAX_ROWS = 10_000
    MAX_FIELD = 10_000


    def read_body(stream, max_bytes=MAX_BYTES):
        """The bytes of a request body, read from the file-like `stream` (`stream.read(n)` returns at most n bytes, b"" at the end). Bodies of more than `max_bytes` bytes are refused with
        ValueError("too large") without reading (much) more than `max_bytes + 1` bytes from the stream: the client controls how long the body is."""
        return stream.read()


    def parse_rows(data, max_rows=MAX_ROWS, max_field=MAX_FIELD):
        """The rows (lists of strings) of the CSV text `data`. More than `max_rows` rows, or any field longer than `max_field` characters, raise ValueError("too large")."""
        return list(csv.reader(io.StringIO(data)))
''')

AB.append(dict(
    slug="unbounded-upload", d=2, product="the import endpoint", func="read_body", cwe="CWE-770",
    finding="`read_body` calls `stream.read()` without a limit and `parse_rows` accepts any number of rows and fields of any length: one request with a multi-gigabyte body (or a 100 MB single field) exhausts the memory of the worker and takes the service down.",
    start={"uploads.py": UPLOAD, "README.md": readme("uploads", "`read_body` and `parse_rows` enforce their limits as the docstrings say, raising `ValueError(\"too large\")`. `read_body` must stop reading shortly after the limit (read in chunks; the stream may be endless). Exactly `max_bytes` bytes are fine, one more is not; `max_rows` rows are fine, one more is not; fields of exactly `max_field` characters are fine.")},
    solution={"uploads.py": patched(UPLOAD, (
        '        return stream.read()\n', '''        chunks, total = [], 0
        while True:
            chunk = stream.read(min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("too large")
            chunks.append(chunk)
        return b"".join(chunks)
'''), (
        '        return list(csv.reader(io.StringIO(data)))\n', '''        csv.field_size_limit(max_field)
        rows = []
        try:
            for row in csv.reader(io.StringIO(data)):
                rows.append(row)
                if len(rows) > max_rows:
                    raise ValueError("too large")
        except csv.Error:
            raise ValueError("too large")
        for row in rows:
            if any(len(f) > max_field for f in row):
                raise ValueError("too large")
        return rows
'''))},
    hidden={"tests/test_uploads_security.py": P + dd(r'''
        import uploads as m


        class Stream:
            """A stream that serves `total` bytes (None = endless) in whatever chunk size is asked for and records what was handed out."""

            def __init__(self, total=None):
                self.total = total
                self.served = 0

            def read(self, n=-1):
                if n is None or n < 0:
                    if self.total is None:
                        raise MemoryError("tried to read an endless stream into memory")
                    n = self.total - self.served
                if self.total is not None:
                    n = min(n, self.total - self.served)
                self.served += n
                return b"x" * n


        class UploadTest(unittest.TestCase):
            def test_body_limits(self):
                s = Stream(1000)
                self.assertEqual(m.read_body(s, 1000), b"x" * 1000)
                self.assertEqual(m.read_body(Stream(0), 10), b"")
                self.assertEqual(len(m.read_body(Stream(m.MAX_BYTES))), m.MAX_BYTES)
                for total in (1001, 5000, None):
                    s = Stream(total)
                    with self.assertRaises(ValueError):
                        m.read_body(s, 1000)
                    self.assertLessEqual(s.served, 1000 + 1 + 65536, total)
                s = Stream(None)
                self.assertIsNone(attempt(m.read_body, s))
                self.assertLessEqual(s.served, m.MAX_BYTES + 65537)

            def test_rows_and_fields(self):
                self.assertEqual(m.parse_rows("a,b\n1,\"2,3\"\n"), [["a", "b"], ["1", "2,3"]])
                self.assertEqual(m.parse_rows(""), [])
                self.assertEqual(len(m.parse_rows("x\n" * 100, max_rows=100)), 100)
                with self.assertRaises(ValueError):
                    m.parse_rows("x\n" * 101, max_rows=100)
                self.assertEqual(m.parse_rows("a,%s\n" % ("y" * 50), max_field=50)[0][1], "y" * 50)
                for text in ("a,%s\n" % ("y" * 51), '"%s"\n' % ("z" * 200), "%s\n" % ("q" * 51)):
                    self.assertIsNone(attempt(m.parse_rows, text, max_field=50))
                with self.assertRaises(ValueError):
                    m.parse_rows("a,%s\n" % ("y" * 51), max_field=50)
                self.assertEqual(len(m.parse_rows("a,b\n" * 10000)), 10000)
                self.assertIsNone(attempt(m.parse_rows, "a,b\n" * 10001))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

LIMITER = dd(r'''
    """Rate limiting of the public API (sliding window per client address)."""
    import time

    TRUSTED_PROXIES = {"10.0.0.1", "10.0.0.2"}


    class RateLimiter:
        def __init__(self, limit=5, window=60, clock=time.time):
            self.limit = limit
            self.window = window
            self.clock = clock
            self.hits = {}

        def client_ip(self, peer, headers):
            """The client address the limiter counts: `peer` is the address of the TCP connection, `headers` the request headers. `X-Forwarded-For` (`client, proxy1, proxy2`, each proxy
            appends the address it received the request from) is only believed when `peer` is one of TRUSTED_PROXIES: then the client is the right-most address in the list that is not itself
            a trusted proxy (everything to its left was supplied by the client and can be forged). Without a trusted peer, or when the header is missing, empty or has no untrusted address, the
            client is `peer`."""
            forwarded = headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",")[0].strip()
            return peer

        def allow(self, peer, headers):
            """True when the client may make a request now: at most `limit` requests per `window` seconds per client address (a request exactly `window` seconds old no longer counts)."""
            ip = self.client_ip(peer, headers)
            now = self.clock()
            recent = [t for t in self.hits.get(ip, []) if now - t < self.window]
            if len(recent) >= self.limit:
                self.hits[ip] = recent
                return False
            recent.append(now)
            self.hits[ip] = recent
            return True
''')

AB.append(dict(
    slug="forwarded-for-bypass", d=3, product="the public API rate limiter", func="RateLimiter.client_ip", cwe="CWE-290",
    finding="`client_ip` trusts the left-most entry of `X-Forwarded-For` from any caller, so a client sends a different forged address in the header with every request and is never rate limited; it can also frame another address by sending it as theirs.",
    start={"limiter.py": LIMITER, "README.md": readme("rate limiter", "`client_ip(peer, headers)` follows its docstring: forwarded addresses only count when the TCP peer is a trusted proxy, and then the right-most untrusted entry (not the left-most) is the client. `allow` keeps its sliding-window behaviour per client address.")},
    solution={"limiter.py": patched(LIMITER, (
        '''            forwarded = headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",")[0].strip()
            return peer
''', '''            forwarded = headers.get("X-Forwarded-For")
            if forwarded and peer in TRUSTED_PROXIES:
                for address in reversed([a.strip() for a in forwarded.split(",")]):
                    if address and address not in TRUSTED_PROXIES:
                        return address
            return peer
'''))},
    hidden={"tests/test_limiter_security.py": P + dd(r'''
        import limiter as m


        class Clock:
            def __init__(self):
                self.t = 100.0

            def __call__(self):
                return self.t


        class LimiterTest(unittest.TestCase):
            def test_client_ip(self):
                r = m.RateLimiter()
                cases = [
                    (("203.0.113.9", {}), "203.0.113.9"),
                    (("203.0.113.9", {"X-Forwarded-For": "1.2.3.4"}), "203.0.113.9"),
                    (("203.0.113.9", {"X-Forwarded-For": "1.2.3.4, 10.0.0.1"}), "203.0.113.9"),
                    (("10.0.0.1", {"X-Forwarded-For": "198.51.100.7"}), "198.51.100.7"),
                    (("10.0.0.1", {"X-Forwarded-For": "1.2.3.4, 198.51.100.7"}), "198.51.100.7"),
                    (("10.0.0.1", {"X-Forwarded-For": "1.2.3.4, 198.51.100.7, 10.0.0.2"}), "198.51.100.7"),
                    (("10.0.0.2", {"X-Forwarded-For": "198.51.100.7,10.0.0.1"}), "198.51.100.7"),
                    (("10.0.0.1", {"X-Forwarded-For": ""}), "10.0.0.1"),
                    (("10.0.0.1", {}), "10.0.0.1"),
                    (("10.0.0.1", {"X-Forwarded-For": "10.0.0.2, 10.0.0.1"}), "10.0.0.1"),
                    (("10.0.0.1", {"X-Forwarded-For": " , 198.51.100.7 , "}), "198.51.100.7"),
                ]
                for (peer, headers), expected in cases:
                    self.assertEqual(r.client_ip(peer, headers), expected, (peer, headers))

            def test_rotating_forged_headers_do_not_help(self):
                c = Clock()
                r = m.RateLimiter(limit=5, window=60, clock=c)
                allowed = sum(r.allow("203.0.113.9", {"X-Forwarded-For": "9.9.9.%d" % i}) for i in range(50))
                self.assertEqual(allowed, 5)
                allowed = sum(r.allow("10.0.0.1", {"X-Forwarded-For": "forged-%d, 198.51.100.7" % i}) for i in range(50))
                self.assertEqual(allowed, 5)
                self.assertTrue(r.allow("10.0.0.1", {"X-Forwarded-For": "198.51.100.8"}))

            def test_sliding_window(self):
                c = Clock()
                r = m.RateLimiter(limit=2, window=60, clock=c)
                self.assertTrue(r.allow("1.1.1.1", {}))
                c.t += 30
                self.assertTrue(r.allow("1.1.1.1", {}))
                self.assertFalse(r.allow("1.1.1.1", {}))
                c.t += 30
                self.assertTrue(r.allow("1.1.1.1", {}))
                self.assertFalse(r.allow("1.1.1.1", {}))
                self.assertTrue(r.allow("2.2.2.2", {}))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

OTP2 = dd(r'''
    """One-time codes for step-up authentication."""
    import secrets
    import time


    class OtpService:
        CODE_TTL = 300
        MAX_ATTEMPTS = 5
        MAX_CODES = 3
        CODES_WINDOW = 600

        def __init__(self, clock=time.time, gen=lambda: "%06d" % secrets.randbelow(10 ** 6)):
            self.clock = clock
            self.gen = gen
            self.active = {}        # user -> {"code", "issued", "failures"}
            self.issued = {}        # user -> [issue times]

        def issue(self, user):
            """Create and return a new six-digit code for `user`, replacing the previous one. At most MAX_CODES codes per user within CODES_WINDOW seconds (an issue exactly CODES_WINDOW seconds
            old no longer counts): the next request raises RuntimeError("too many codes") and changes nothing."""
            now = self.clock()
            code = self.gen()
            self.active[user] = {"code": code, "issued": now, "failures": 0}
            self.issued.setdefault(user, []).append(now)
            return code

        def verify(self, user, code):
            """True when `code` is the user's current code, not older than CODE_TTL seconds (valid while `now - issued < CODE_TTL`) and not used up. A correct code is accepted once. After
            MAX_ATTEMPTS wrong guesses the code is dead: even the right code is refused, and a new one must be issued."""
            entry = self.active.get(user)
            if entry is None:
                return False
            if self.clock() - entry["issued"] >= self.CODE_TTL:
                return False
            return entry["code"] == code
''')

AB.append(dict(
    slug="otp-attempts", d=3, product="the step-up authentication", func="OtpService.verify", cwe="CWE-307",
    finding="`verify` has no attempt counter and codes can be requested without limit: a six-digit code falls to brute force in a few hundred thousand guesses (or far fewer, because every new code resets the search), and a correct code can be replayed until it expires.",
    start={"otp_service.py": OTP2, "README.md": readme("step-up codes", "`issue` and `verify` implement the rules of their docstrings: at most MAX_ATTEMPTS wrong guesses per code (the code is dead afterwards, correct or not), codes expire after CODE_TTL seconds, a code works once, at most MAX_CODES codes per user per CODES_WINDOW seconds. State is per user; the generator and the clock are injected so tests are deterministic.")},
    solution={"otp_service.py": patched(OTP2, (
        '''            now = self.clock()
            code = self.gen()
            self.active[user] = {"code": code, "issued": now, "failures": 0}
            self.issued.setdefault(user, []).append(now)
            return code
''', '''            now = self.clock()
            recent = [t for t in self.issued.get(user, []) if now - t < self.CODES_WINDOW]
            self.issued[user] = recent
            if len(recent) >= self.MAX_CODES:
                raise RuntimeError("too many codes")
            code = self.gen()
            self.active[user] = {"code": code, "issued": now, "failures": 0}
            recent.append(now)
            return code
'''), (
        '''            if self.clock() - entry["issued"] >= self.CODE_TTL:
                return False
            return entry["code"] == code
''', '''            if self.clock() - entry["issued"] >= self.CODE_TTL or entry["failures"] >= self.MAX_ATTEMPTS:
                return False
            if isinstance(code, str) and secrets.compare_digest(entry["code"].encode(), code.encode("utf-8")):
                del self.active[user]
                return True
            entry["failures"] += 1
            return False
'''))},
    hidden={"tests/test_otp_service_security.py": P + dd(r'''
        import otp_service as m


        class Clock:
            def __init__(self):
                self.t = 1000.0

            def __call__(self):
                return self.t


        def make(codes):
            c = Clock()
            it = iter(codes)
            return m.OtpService(clock=c, gen=lambda: next(it)), c


        class OtpTest(unittest.TestCase):
            def test_happy_path_and_single_use(self):
                s, c = make(["111111", "222222"])
                self.assertEqual(s.issue("ann"), "111111")
                self.assertFalse(s.verify("ann", "000000"))
                self.assertTrue(s.verify("ann", "111111"))
                self.assertFalse(s.verify("ann", "111111"))
                self.assertFalse(s.verify("bob", "111111"))
                self.assertEqual(s.issue("ann"), "222222")
                c.t += 299
                self.assertTrue(s.verify("ann", "222222"))

            def test_expiry(self):
                s, c = make(["111111"])
                s.issue("ann")
                c.t += 300
                self.assertFalse(s.verify("ann", "111111"))

            def test_attempt_limit(self):
                s, c = make(["111111", "222222"])
                s.issue("ann")
                for guess in ("000001", "000002", "000003", "000004"):
                    self.assertFalse(s.verify("ann", guess))
                s2, _ = make(["111111", "222222"])
                s2.issue("ann")
                for guess in ("000001", "000002", "000003", "000004", "000005"):
                    self.assertFalse(s2.verify("ann", guess))
                self.assertFalse(s2.verify("ann", "111111"))
                self.assertEqual(s2.issue("ann"), "222222")
                self.assertTrue(s2.verify("ann", "222222"))
                s3, _ = make(["111111"])
                s3.issue("ann")
                for guess in ("000001", "000002", "000003", "000004"):
                    s3.verify("ann", guess)
                self.assertTrue(s3.verify("ann", "111111"))

            def test_code_requests_are_limited(self):
                s, c = make(["%06d" % i for i in range(20)])
                for i in range(3):
                    self.assertEqual(s.issue("ann"), "%06d" % i)
                    c.t += 100
                with self.assertRaises(RuntimeError):
                    s.issue("ann")
                self.assertEqual(s.issue("bob"), "000003")
                c.t += 300
                self.assertEqual(s.issue("ann"), "000004")
                self.assertTrue(s.verify("ann", "000004"))

            def test_new_code_does_not_reset_the_search(self):
                s, c = make(["%06d" % i for i in range(20)])
                guesses = 0
                for _ in range(3):
                    s.issue("ann")
                    for g in range(5):
                        self.assertFalse(s.verify("ann", "9%05d" % g))
                        guesses += 1
                    c.t += 10
                self.assertEqual(guesses, 15)
                self.assertIsNone(attempt(s.issue, "ann"))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

AB_ORDER = ["login-lockout", "unbounded-upload", "forwarded-for-bypass", "otp-attempts"]
AB.sort(key=lambda s: (s["d"], AB_ORDER.index(s["slug"])))


@family("security-abuse-limits", category="security", lang="python", kind="fix", n=4,
        summary="abuse limits: login lockout, upload size limits, forwarded-header spoofing in rate limiting, OTP attempts")
def gen_abuse(rng, n):
    return list(_sec.emit(rng, AB[:n], tags=["rate-limit"]))
