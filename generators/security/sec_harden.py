"""Security family: hardening tasks. Functions that produce security-relevant HTTP / TLS / error behaviour, and configuration files (Dockerfile, compose, CI workflow, nginx,
sshd) that must be brought in line with a written baseline while the service keeps working. Tests check the outcome, not the way it was reached."""
from fx import dd, family

from . import _sec
from ._sec import patched, readme

P = _sec.PY_PRELUDE

HD = []

# ---------------------------------------------------------------------------------------------------------------------------------
HEADERS = dd(r'''
    """Response hardening of the web framework."""


    def apply_security_headers(headers, https):
        """The response headers with the security baseline applied; returns a NEW dict (the argument is not modified). `headers` maps header names (any letter case) to values; `https` says
        whether the response goes out over TLS.

        * always set (replacing whatever the application put there, matching names case-insensitively and writing them in the canonical spelling below):
          `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: geolocation=(), camera=(), microphone=()`,
          `Cross-Origin-Opener-Policy: same-origin`;
        * `Content-Security-Policy`: `default-src 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'`, unless the application already set a policy (any letter case of the name):
          that one is kept untouched;
        * `Strict-Transport-Security: max-age=31536000; includeSubDomains` only when `https` is true (never over plain HTTP);
        * the headers `Server` and `X-Powered-By` (any letter case) are removed;
        * every other header is passed through unchanged."""
        return dict(headers)
''')
HD.append(dict(
    slug="response-headers", d=2, product="the web framework", func="apply_security_headers", cwe="CWE-693",
    finding="`apply_security_headers` returns the headers as they are: responses go out without a content-type guard, framing protection, CSP, referrer or HSTS policy, and they advertise the server software (`Server`, `X-Powered-By`), which makes clickjacking, MIME sniffing attacks and downgrade attacks easy.",
    start={"hardening.py": HEADERS, "README.md": readme("response hardening", "`apply_security_headers(headers, https)` implements the baseline of its docstring: a new dict, canonical spellings, an existing CSP is kept, HSTS only over HTTPS, the two fingerprinting headers are dropped, everything else is untouched (including its spelling).")},
    solution={"hardening.py": patched(HEADERS, ('    return dict(headers)\n', '''    lowered = {name.lower(): name for name in headers}
    out = {name: value for name, value in headers.items() if name.lower() not in ALWAYS_LOWER and name.lower() not in REMOVED}
    out.update(ALWAYS)
    if "content-security-policy" not in lowered:
        out["Content-Security-Policy"] = DEFAULT_CSP
    if https:
        out["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return out
'''), ('"""Response hardening of the web framework."""\n', '''"""Response hardening of the web framework."""

ALWAYS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "strict-origin-when-cross-origin",
          "Permissions-Policy": "geolocation=(), camera=(), microphone=()", "Cross-Origin-Opener-Policy": "same-origin"}
ALWAYS_LOWER = {name.lower() for name in ALWAYS} | {"strict-transport-security"}
REMOVED = {"server", "x-powered-by"}
DEFAULT_CSP = "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'"
'''))},
    hidden={"tests/test_hardening_security.py": P + dd(r'''
        import hardening as m

        ALWAYS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "strict-origin-when-cross-origin", "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
                  "Cross-Origin-Opener-Policy": "same-origin"}
        CSP = "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'"
        HSTS = "max-age=31536000; includeSubDomains"


        class HeadersTest(unittest.TestCase):
            def test_plain_response(self):
                got = m.apply_security_headers({"Content-Type": "text/html"}, False)
                self.assertEqual(got, dict(ALWAYS, **{"Content-Type": "text/html", "Content-Security-Policy": CSP}))
                got = m.apply_security_headers({"Content-Type": "text/html"}, True)
                self.assertEqual(got, dict(ALWAYS, **{"Content-Type": "text/html", "Content-Security-Policy": CSP, "Strict-Transport-Security": HSTS}))
                self.assertEqual(m.apply_security_headers({}, False), dict(ALWAYS, **{"Content-Security-Policy": CSP}))

            def test_application_headers(self):
                src = {"server": "gunicorn/20", "X-POWERED-BY": "Flask", "content-security-policy": "default-src https://cdn.example", "x-frame-options": "SAMEORIGIN", "Set-Cookie": "a=b",
                       "x-content-type-options": "other", "Strict-Transport-Security": "max-age=1", "X-Custom": "1"}
                before = dict(src)
                got = m.apply_security_headers(src, False)
                self.assertEqual(src, before)
                lowered = {k.lower(): (k, v) for k, v in got.items()}
                self.assertEqual(len(lowered), len(got), got)
                self.assertNotIn("server", lowered)
                self.assertNotIn("x-powered-by", lowered)
                self.assertEqual(got["content-security-policy"], "default-src https://cdn.example")
                self.assertNotIn("Content-Security-Policy", got)
                self.assertEqual(got["X-Frame-Options"], "DENY")
                self.assertEqual(got["X-Content-Type-Options"], "nosniff")
                self.assertNotIn("strict-transport-security", lowered)
                self.assertEqual(got["Set-Cookie"], "a=b")
                self.assertEqual(got["X-Custom"], "1")
                https = m.apply_security_headers({"Strict-Transport-Security": "max-age=1"}, True)
                self.assertEqual(https["Strict-Transport-Security"], HSTS)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

CORS = dd(r'''
    """Cross-origin resource sharing for the API."""

    ALLOWED_ORIGINS = {"https://app.example.com", "https://admin.example.com"}
    ALLOWED_METHODS = ("GET", "POST", "PUT", "DELETE")
    ALLOWED_HEADERS = ("Content-Type", "Authorization", "X-Requested-With")


    def cors_headers(origin, method, request_method=None, request_headers=None):
        """The CORS response headers (a dict) for a request.

        `origin` is the Origin header (None when absent), `method` the HTTP method, and for preflights (`method == "OPTIONS"` with a `request_method`) `request_method` is the
        Access-Control-Request-Method and `request_headers` the Access-Control-Request-Headers value (comma separated names, any letter case, may be None).

        * no Origin: `{}`;
        * an Origin that is not exactly one of ALLOWED_ORIGINS (including `null`, look-alike hosts, other schemes or ports): only `{"Vary": "Origin"}`;
        * an allowed Origin: `Access-Control-Allow-Origin` (that origin, never `*`), `Access-Control-Allow-Credentials: true` and `Vary: Origin`;
        * an allowed preflight (request_method in ALLOWED_METHODS, any letter case) adds `Access-Control-Allow-Methods` (ALLOWED_METHODS joined with ", "), `Access-Control-Max-Age: 600` and
          `Access-Control-Allow-Headers`: the requested names that are in ALLOWED_HEADERS (case-insensitive), in the requested order, without duplicates, in the canonical spelling, joined with
          ", " (the header is left out when none qualifies); a preflight for a method that is not allowed gets only `{"Vary": "Origin"}`."""
        headers = {"Access-Control-Allow-Origin": origin or "*", "Access-Control-Allow-Credentials": "true", "Access-Control-Allow-Headers": "*",
                   "Access-Control-Allow-Methods": "*"}
        return headers
''')
HD.append(dict(
    slug="cors-policy", d=3, product="the API gateway", func="cors_headers", cwe="CWE-942",
    finding="`cors_headers` reflects whatever Origin the browser sends together with `Access-Control-Allow-Credentials: true` (and allows all methods and headers): any website a logged-in user visits can read authenticated API responses, `null` origins from sandboxed iframes included.",
    start={"cors.py": CORS, "README.md": readme("CORS", "`cors_headers` follows its docstring exactly. Two legitimate front ends (`https://app.example.com`, `https://admin.example.com`) may call the API with cookies; nobody else may. The exact header names and values matter, including `Vary: Origin` on every answer to a request that has an Origin.")},
    solution={"cors.py": patched(CORS, (
        '''    headers = {"Access-Control-Allow-Origin": origin or "*", "Access-Control-Allow-Credentials": "true", "Access-Control-Allow-Headers": "*",
               "Access-Control-Allow-Methods": "*"}
    return headers
''', '''    if origin is None:
        return {}
    if origin not in ALLOWED_ORIGINS:
        return {"Vary": "Origin"}
    headers = {"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true", "Vary": "Origin"}
    if method == "OPTIONS" and request_method is not None:
        if str(request_method).upper() not in ALLOWED_METHODS:
            return {"Vary": "Origin"}
        headers["Access-Control-Allow-Methods"] = ", ".join(ALLOWED_METHODS)
        headers["Access-Control-Max-Age"] = "600"
        canonical = {h.lower(): h for h in ALLOWED_HEADERS}
        wanted = []
        for name in (request_headers or "").split(","):
            name = canonical.get(name.strip().lower())
            if name and name not in wanted:
                wanted.append(name)
        if wanted:
            headers["Access-Control-Allow-Headers"] = ", ".join(wanted)
    return headers
'''))},
    hidden={"tests/test_cors_security.py": P + dd(r'''
        import cors as m

        APP, ADMIN = "https://app.example.com", "https://admin.example.com"
        BASE = {"Access-Control-Allow-Credentials": "true", "Vary": "Origin"}


        class CorsTest(unittest.TestCase):
            def test_simple_requests(self):
                self.assertEqual(m.cors_headers(None, "GET"), {})
                self.assertEqual(m.cors_headers(APP, "GET"), dict(BASE, **{"Access-Control-Allow-Origin": APP}))
                self.assertEqual(m.cors_headers(ADMIN, "POST"), dict(BASE, **{"Access-Control-Allow-Origin": ADMIN}))

            def test_foreign_origins(self):
                for origin in ["https://evil.example", "null", "https://app.example.com.evil.io", "http://app.example.com", "https://app.example.com:8443", "https://APP.example.com", "https://sub.app.example.com",
                               "", "*", "https://app.example.com/", "https://app.example.comevil.io"]:
                    self.assertEqual(m.cors_headers(origin, "GET"), {"Vary": "Origin"}, origin)
                    self.assertEqual(m.cors_headers(origin, "OPTIONS", "GET", "Content-Type"), {"Vary": "Origin"}, origin)

            def test_preflights(self):
                got = m.cors_headers(APP, "OPTIONS", "PUT", "content-type, AUTHORIZATION,X-Requested-With, content-type, X-Evil, ")
                self.assertEqual(got, dict(BASE, **{"Access-Control-Allow-Origin": APP, "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE", "Access-Control-Max-Age": "600",
                                                    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With"}))
                got = m.cors_headers(ADMIN, "OPTIONS", "delete", None)
                self.assertEqual(got, dict(BASE, **{"Access-Control-Allow-Origin": ADMIN, "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE", "Access-Control-Max-Age": "600"}))
                got = m.cors_headers(APP, "OPTIONS", "POST", "X-Evil, X-Other")
                self.assertNotIn("Access-Control-Allow-Headers", got)
                for bad in ["PATCH", "TRACE", "CONNECT"]:
                    self.assertEqual(m.cors_headers(APP, "OPTIONS", bad, "Content-Type"), {"Vary": "Origin"}, bad)
                self.assertEqual(m.cors_headers(APP, "OPTIONS"), dict(BASE, **{"Access-Control-Allow-Origin": APP}))
                self.assertNotIn("*", "".join(m.cors_headers("https://evil.example", "OPTIONS", "GET", "x").values()))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

TLS = dd(r'''
    """TLS settings of the HTTP client used for partner calls."""
    import ssl


    def make_client_context(cafile=None):
        """The `ssl.SSLContext` for outgoing HTTPS connections. Server certificates are verified against the system trust store (or against `cafile`, a PEM bundle, when given - a
        missing file raises an OSError) and the host name must match the certificate; protocols older than TLS 1.2 are not offered; compression is disabled."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.minimum_version = ssl.TLSVersion.TLSv1
        return ctx
''')
HD.append(dict(
    slug="tls-client-context", d=2, product="the partner API client", func="make_client_context", cwe="CWE-295",
    finding="`make_client_context` turns certificate verification and host name checking off and allows TLS 1.0: anybody on the network path can impersonate the partner's server, read the API keys sent to it and alter the responses (man-in-the-middle).",
    start={"tlsconfig.py": TLS, "README.md": readme("TLS client", "`make_client_context(cafile=None)` returns a context that verifies certificates (`CERT_REQUIRED`), checks host names, requires TLS 1.2 or newer and disables compression; with `cafile` it trusts that bundle only, and a missing file raises `OSError` (`FileNotFoundError`).")},
    solution={"tlsconfig.py": patched(TLS, (
        '''    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1
    return ctx
''', '''    ctx = ssl.create_default_context(cafile=cafile)
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.options |= ssl.OP_NO_COMPRESSION
    return ctx
'''))},
    hidden={"tests/test_tlsconfig_security.py": P + dd(r'''
        import ssl

        import tlsconfig as m


        class TlsTest(unittest.TestCase):
            def test_default_context(self):
                ctx = m.make_client_context()
                self.assertIsInstance(ctx, ssl.SSLContext)
                self.assertEqual(ctx.protocol, ssl.PROTOCOL_TLS_CLIENT)
                self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
                self.assertIs(ctx.check_hostname, True)
                self.assertGreaterEqual(ctx.minimum_version, ssl.TLSVersion.TLSv1_2)
                self.assertTrue(ctx.options & ssl.OP_NO_COMPRESSION)
                self.assertTrue(ctx.get_ca_certs() or ctx.cert_store_stats() is not None)

            def test_cafile(self):
                with self.assertRaises(OSError):
                    m.make_client_context("/nonexistent/ca-bundle.pem")
                ctx = m.make_client_context(None)
                self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
                self.assertIsNot(m.make_client_context(), m.make_client_context())


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

ERRORS = dd(r'''
    """Error handling of the web app."""
    import os
    import traceback

    DEBUG = True


    class HTTPError(Exception):
        """An error the client is allowed to see: a status code and a public message."""

        def __init__(self, status, message):
            super().__init__(message)
            self.status = status
            self.public_message = message


    def secret_key():
        """The signing key of the app: the environment variable APP_SECRET_KEY. When it is missing or empty RuntimeError("APP_SECRET_KEY is not set") is raised - there is no default."""
        return os.environ.get("APP_SECRET_KEY") or "dev-secret"


    def render_error(exc):
        """`(status, body)` for an exception that escaped a request handler. An HTTPError gives its status and `{"error": public_message}`. Every other exception gives status 500 and the body
        `{"error": "internal error", "id": <12 lower-case hex characters, different each time>}`: nothing else - no message, traceback, paths, environment or configuration. The details
        (repr of the exception and its traceback) are logged at ERROR level on the logger `app`, with the same id in the log message (`id=<id>`). DEBUG is False unless the environment variable
        APP_DEBUG is "1" when the module is imported."""
        return 500, {"error": str(exc), "traceback": traceback.format_exception(type(exc), exc, exc.__traceback__), "env": dict(os.environ)}
''')
HD.append(dict(
    slug="error-pages", d=2, product="the web app", func="render_error", cwe="CWE-209",
    finding="`render_error` sends the exception message, the full traceback and the process environment (database URLs, API keys) to whoever triggered the error, `DEBUG` is on by default, and `secret_key()` silently falls back to the public default `dev-secret`, with which sessions can be forged.",
    start={"errors.py": ERRORS, "README.md": readme("error handling", "`render_error`, `secret_key` and `DEBUG` behave exactly as their docstrings say: production-safe by default, details only in the log (with a correlation id), client errors still show their own message and status, and no insecure secret fallback.")},
    solution={"errors.py": patched(ERRORS, ('import os\nimport traceback\n\nDEBUG = True\n', 'import logging\nimport os\nimport secrets\nimport traceback\n\nDEBUG = os.environ.get("APP_DEBUG") == "1"\nlog = logging.getLogger("app")\n'), (
        '    return os.environ.get("APP_SECRET_KEY") or "dev-secret"\n', '''    key = os.environ.get("APP_SECRET_KEY")
    if not key:
        raise RuntimeError("APP_SECRET_KEY is not set")
    return key
'''), (
        '    return 500, {"error": str(exc), "traceback": traceback.format_exception(type(exc), exc, exc.__traceback__), "env": dict(os.environ)}\n', '''    if isinstance(exc, HTTPError):
        return exc.status, {"error": exc.public_message}
    error_id = secrets.token_hex(6)
    log.error("unhandled %r id=%s\\n%s", exc, error_id, "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    return 500, {"error": "internal error", "id": error_id}
'''))},
    hidden={"tests/test_errors_security.py": P + dd(r'''
        import logging
        import re

        import errors as m


        class Capture(logging.Handler):
            def __init__(self):
                super().__init__(logging.DEBUG)
                self.records = []

            def emit(self, record):
                self.records.append(record)


        def failing():
            try:
                raise ValueError("connection to postgres://app:hunter2@db.internal failed")
            except ValueError as exc:
                return exc


        class ErrorTest(unittest.TestCase):
            def setUp(self):
                self.logger = logging.getLogger("app")
                self.handler = Capture()
                self.logger.addHandler(self.handler)
                self.logger.setLevel(logging.DEBUG)
                self.addCleanup(self.logger.removeHandler, self.handler)
                os.environ["SECRET_ENV_FOR_TEST"] = "env-leak-canary"
                self.addCleanup(os.environ.pop, "SECRET_ENV_FOR_TEST", None)

            def test_client_errors(self):
                self.assertEqual(m.render_error(m.HTTPError(404, "no such page")), (404, {"error": "no such page"}))
                self.assertEqual(m.render_error(m.HTTPError(403, "forbidden")), (403, {"error": "forbidden"}))
                self.assertEqual(self.handler.records, [])

            def test_internal_errors_are_opaque(self):
                exc = failing()
                status, body = m.render_error(exc)
                self.assertEqual(status, 500)
                self.assertEqual(set(body), {"error", "id"})
                self.assertEqual(body["error"], "internal error")
                self.assertRegex(body["id"], r"^[0-9a-f]{12}$")
                text = repr(body)
                for secret in ("hunter2", "postgres://", "ValueError", "Traceback", "env-leak-canary", "errors.py", "failed"):
                    self.assertNotIn(secret, text)
                errors = [r for r in self.handler.records if r.levelno >= logging.ERROR]
                self.assertEqual(len(errors), 1)
                logged = errors[0].getMessage()
                self.assertIn("id=" + body["id"], logged)
                self.assertIn("hunter2", logged)
                self.assertIn("ValueError", logged)
                self.assertIn("Traceback", logged)
                self.assertNotEqual(m.render_error(failing())[1]["id"], body["id"])

            def test_defaults(self):
                self.assertIs(m.DEBUG, os.environ.get("APP_DEBUG") == "1")
                old = os.environ.pop("APP_SECRET_KEY", None)
                self.addCleanup(lambda: os.environ.__setitem__("APP_SECRET_KEY", old) if old is not None else os.environ.pop("APP_SECRET_KEY", None))
                with self.assertRaises(RuntimeError) as ctx:
                    m.secret_key()
                self.assertIn("APP_SECRET_KEY", str(ctx.exception))
                os.environ["APP_SECRET_KEY"] = ""
                self.assertRaises(RuntimeError, m.secret_key)
                os.environ["APP_SECRET_KEY"] = "k3y"
                self.assertEqual(m.secret_key(), "k3y")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------------------------
DOCKERFILE = dd(r'''
    FROM python:latest
    ENV FLASK_ENV=production
    ENV DB_PASSWORD=changeme123
    ENV API_TOKEN=abc123def456
    ADD https://downloads.example.net/tools/helper.tar.gz /opt/helper.tar.gz
    RUN curl -sSL https://downloads.example.net/get-deps.sh | bash
    RUN apt-get update && apt-get install -y gcc libpq-dev
    WORKDIR /app
    COPY requirements.txt .
    RUN pip install -r requirements.txt
    COPY . .
    EXPOSE 22 8000
    CMD ["python", "app.py"]
''')
COMPOSE = dd(r'''
    services:
      web:
        build: .
        privileged: true
        network_mode: host
        ports:
          - "8000:8000"
        environment:
          - DB_PASSWORD=changeme123
          - API_TOKEN=abc123def456
          - LOG_LEVEL=info
        volumes:
          - /var/run/docker.sock:/var/run/docker.sock
          - ./data:/app/data
''')
HD.append(dict(
    slug="container-setup", d=3, product="the container deployment", func="Dockerfile", cwe="CWE-1188",
    finding="the image runs as root from a floating `python:latest` base, bakes a database password and an API token into environment variables, downloads and pipes an unreviewed script into bash, and the compose file runs the container privileged, on the host network, with the Docker socket mounted: a bug in the app means the host is gone.",
    start={"Dockerfile": DOCKERFILE, "docker-compose.yml": COMPOSE, "requirements.txt": "flask>=2.0\nrequests\npsycopg2-binary~=2.9\n", "scripts/get-deps.sh": "#!/bin/sh\n# vendored copy of the dependency installer (reviewed)\nset -eu\napt-get install -y --no-install-recommends libpq5\n",
           "app.py": "from flask import Flask\n\napp = Flask(__name__)\n\n\n@app.get('/')\ndef index():\n    return 'ok'\n\n\nif __name__ == '__main__':\n    app.run(host='0.0.0.0', port=8000)\n",
           "README.md": readme("container setup", "Baseline for `Dockerfile`, `docker-compose.yml` and `requirements.txt` (the service keeps listening on port 8000 and starting with `python app.py`):\n\n"
                              "* The base image is pinned to a version tag (`python:3.12-slim` style, never `latest` and never untagged) or a digest.\n* The image runs as a non-root user: a `USER` instruction naming one (not `root`, not `0`) comes before `CMD`.\n"
                              "* No `ADD` (use `COPY`), no `curl | sh` / `wget | bash` pipes: the vendored `scripts/get-deps.sh` is copied and run instead.\n* No `ENV`/`ARG` with a literal value for names containing PASSWORD, SECRET, TOKEN or KEY.\n"
                              "* `pip install` uses `--no-cache-dir` and `requirements.txt` pins every package with `==`; `apt-get install` uses `--no-install-recommends` and the same `RUN` removes `/var/lib/apt/lists/*`.\n"
                              "* There is a `HEALTHCHECK`; port 22 is not exposed.\n* Compose: no `privileged`, no `network_mode: host`, the port is published on `127.0.0.1` only, secrets come from the environment of the host (`${DB_PASSWORD}` style references) or an `env_file`, "
                              "the Docker socket is not mounted, `./data` stays mounted, and the service has `read_only: true`, `cap_drop` with `ALL` and `security_opt` with `no-new-privileges:true`.")},
    solution={"Dockerfile": dd(r'''
        FROM python:3.12-slim
        ENV FLASK_ENV=production
        RUN useradd --create-home --shell /usr/sbin/nologin appuser
        WORKDIR /app
        COPY scripts/get-deps.sh /tmp/get-deps.sh
        RUN apt-get update && sh /tmp/get-deps.sh && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/* /tmp/get-deps.sh
        COPY requirements.txt .
        RUN pip install --no-cache-dir -r requirements.txt
        COPY . .
        USER appuser
        EXPOSE 8000
        HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/')"
        CMD ["python", "app.py"]
    '''), "requirements.txt": "flask==3.0.3\nrequests==2.32.3\npsycopg2-binary==2.9.9\n", "docker-compose.yml": dd(r'''
        services:
          web:
            build: .
            ports:
              - "127.0.0.1:8000:8000"
            environment:
              - DB_PASSWORD=${DB_PASSWORD}
              - API_TOKEN=${API_TOKEN}
              - LOG_LEVEL=info
            volumes:
              - ./data:/app/data
            read_only: true
            cap_drop:
              - ALL
            security_opt:
              - no-new-privileges:true
    ''')},
    hidden={"tests/test_container_security.py": P + dd(r'''
        import re


        def text(name):
            with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
                return fh.read()


        def instructions(source):
            """[(INSTRUCTION, args)] of a Dockerfile: continuation lines joined, comments and blank lines dropped."""
            out, buf = [], ""
            for raw in source.splitlines():
                line = raw.rstrip()
                if not buf and (not line.strip() or line.lstrip().startswith("#")):
                    continue
                if line.endswith("\\"):
                    buf += line[:-1] + " "
                    continue
                buf += line
                inst, _, args = buf.strip().partition(" ")
                out.append((inst.upper(), args.strip()))
                buf = ""
            return out


        class DockerfileTest(unittest.TestCase):
            def setUp(self):
                self.ins = instructions(text("Dockerfile"))

            def args(self, name):
                return [a for i, a in self.ins if i == name]

            def test_base_image(self):
                froms = self.args("FROM")
                self.assertTrue(froms)
                for image in froms:
                    ref = image.split()[0]
                    self.assertTrue("@sha256:" in ref or re.search(r":[0-9][A-Za-z0-9._-]*$", ref), ref)
                    self.assertFalse(ref.endswith(":latest") or ":" not in ref.split("/")[-1] and "@" not in ref, ref)

            def test_user_and_command(self):
                names = [i for i, _ in self.ins]
                users = self.args("USER")
                self.assertTrue(users, "no USER instruction")
                self.assertNotIn(users[-1].split(":")[0].strip(), ("root", "0"))
                self.assertLess(max(i for i, (n, a) in enumerate(self.ins) if n == "USER"), max(i for i, n in enumerate(names) if n in ("CMD", "ENTRYPOINT")))
                cmd = self.args("CMD")
                self.assertEqual(len(cmd), 1)
                self.assertIn("app.py", cmd[0])
                self.assertIn("python", cmd[0])
                self.assertTrue(any("8000" in a.split() for a in self.args("EXPOSE")))
                self.assertFalse(any("22" in a.split() for a in self.args("EXPOSE")))
                self.assertTrue(self.args("HEALTHCHECK"))
                self.assertTrue(any("requirements.txt" in a for a in self.args("COPY")))

            def test_no_dangerous_instructions(self):
                self.assertEqual(self.args("ADD"), [])
                for inst, args in self.ins:
                    if inst == "RUN":
                        self.assertIsNone(re.search(r"(curl|wget)[^|;&]*\|\s*(sudo\s+)?(ba|z)?sh\b", args), args)
                    if inst in ("ENV", "ARG"):
                        for pair in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=(\S*)", args) or ([tuple(args.split(None, 1))] if len(args.split(None, 1)) == 2 else []):
                            name, value = pair
                            if re.search(r"PASSWORD|SECRET|TOKEN|KEY", name.upper()):
                                self.assertEqual(value.strip('"\''), "", name)
                self.assertTrue(any("get-deps.sh" in a for a in self.args("COPY")))
                self.assertTrue(any("get-deps.sh" in a for a in self.args("RUN")))

            def test_package_installs(self):
                runs = self.args("RUN")
                for r in runs:
                    if "pip install" in r:
                        self.assertIn("--no-cache-dir", r)
                    if "apt-get install" in r:
                        self.assertIn("--no-install-recommends", r)
                        self.assertIn("rm -rf /var/lib/apt/lists", r)
                reqs = [ln.strip() for ln in text("requirements.txt").splitlines() if ln.strip() and not ln.startswith("#")]
                self.assertEqual({ln.split("==")[0].lower() for ln in reqs}, {"flask", "requests", "psycopg2-binary"})
                for ln in reqs:
                    self.assertRegex(ln, r"^[A-Za-z0-9._-]+==\d+(\.\d+)*$")


        class ComposeTest(unittest.TestCase):
            def setUp(self):
                self.src = text("docker-compose.yml")

            def test_isolation(self):
                self.assertNotRegex(self.src, r"(?m)^\s*privileged:\s*true")
                self.assertNotRegex(self.src, r"(?m)^\s*network_mode:\s*[\"']?host")
                self.assertNotIn("docker.sock", self.src)
                self.assertRegex(self.src, r"(?m)^\s*read_only:\s*true\s*$")
                self.assertRegex(self.src, r"(?ms)^\s*cap_drop:\s*\n\s*-\s*ALL\s*$")
                self.assertRegex(self.src, r"(?ms)^\s*security_opt:\s*\n(\s*-\s*\S+\s*\n)*?\s*-\s*[\"']?no-new-privileges:true")
                self.assertIn("./data:/app/data", self.src)

            def test_ports_and_secrets(self):
                ports = re.findall(r"(?m)^\s*-\s*[\"']?(\d[^\s\"']*:\d+(?::\d+)?)[\"']?\s*$", self.src)
                self.assertTrue(ports)
                for p in ports:
                    self.assertTrue(p.startswith("127.0.0.1:"), p)
                self.assertIn("8000", "".join(ports))
                for line in self.src.splitlines():
                    m = re.match(r"^\s*-?\s*([A-Za-z_]*(PASSWORD|SECRET|TOKEN|KEY)[A-Za-z_]*)\s*[=:]\s*(.*)$", line)
                    if m:
                        value = m.group(3).strip().strip("\"'")
                        self.assertTrue(value == "" or re.fullmatch(r"\$\{[A-Za-z_]+(:?[-?][^}]*)?\}", value), line)
                self.assertIn("LOG_LEVEL=info", self.src)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

WORKFLOW = dd(r'''
    name: ci
    on:
      pull_request_target:
        types: [opened, synchronize]
    permissions: write-all
    jobs:
      test:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@main
            with:
              ref: ${{ github.event.pull_request.head.sha }}
          - uses: actions/setup-python@v5
          - name: Announce
            run: echo "Testing PR ${{ github.event.pull_request.title }} by ${{ github.head_ref }}"
          - name: Install tools
            run: curl -sSL https://tools.example.net/setup.sh | bash
          - name: Test
            run: python -m unittest discover -s tests
            env:
              API_TOKEN: ${{ secrets.API_TOKEN }}
          - run: echo "deploy key is ${{ secrets.DEPLOY_KEY }}"
''')
HD.append(dict(
    slug="ci-workflow", d=3, product="the CI pipeline", func="ci.yml", cwe="CWE-1395",
    finding="the CI workflow uses `pull_request_target` to check out and run code of the pull request with a write-all token and the repository's secrets, interpolates the PR title and branch name into a shell command (script injection), pipes a downloaded script into bash, echoes a secret, and uses unpinned actions.",
    start={".github/workflows/ci.yml": WORKFLOW, "tests/test_smoke.py": "import unittest\n\n\nclass Smoke(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n",
           "README.md": readme("CI pipeline", "Baseline for `.github/workflows/ci.yml`: the workflow runs on `pull_request` and on pushes to `main` - never `pull_request_target`; the top-level `permissions` grant `contents: read` and nothing else; every `uses:` is pinned to a full version (`@v4.1.7` style or a 40-character commit SHA, no branches, no floating majors); no `${{ github.event... }}`, `${{ github.head_ref }}` or other attacker-controlled expression inside a `run:` command (pass them through `env:` and quote the variable); no `curl | bash` pipes; no `secrets.` anywhere in the unit-test job (the tests do not need them) and nothing echoes a secret. The job `test` still runs `python -m unittest discover -s tests` and has `timeout-minutes`.")},
    solution={".github/workflows/ci.yml": dd(r'''
        name: ci
        on:
          pull_request:
          push:
            branches: [main]
        permissions:
          contents: read
        jobs:
          test:
            runs-on: ubuntu-latest
            timeout-minutes: 10
            steps:
              - uses: actions/checkout@v4.1.7
              - uses: actions/setup-python@v5.1.1
              - name: Announce
                env:
                  PR_TITLE: ${{ github.event.pull_request.title }}
                  BRANCH: ${{ github.head_ref }}
                run: echo "Testing PR $PR_TITLE on $BRANCH"
              - name: Test
                run: python -m unittest discover -s tests
    ''')},
    hidden={"tests/test_workflow_security.py": P + dd(r'''
        import re

        with open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8") as fh:
            SRC = fh.read()


        class WorkflowTest(unittest.TestCase):
            def test_trigger_and_permissions(self):
                self.assertNotIn("pull_request_target", SRC)
                self.assertRegex(SRC, r"(?m)^\s{2}pull_request:")
                self.assertRegex(SRC, r"(?m)^\s{2}push:")
                self.assertRegex(SRC, r"(?ms)^permissions:\s*\n\s+contents:\s*read\s*$")
                self.assertNotRegex(SRC, r"(?m)^permissions:\s*(write-all|read-all)")
                self.assertNotRegex(SRC, r"(?i):\s*write\b")
                self.assertRegex(SRC, r"(?m)^\s*timeout-minutes:\s*\d+")

            def test_actions_are_pinned(self):
                uses = re.findall(r"(?m)^\s*-?\s*uses:\s*(\S+)", SRC)
                self.assertGreaterEqual(len(uses), 2)
                for ref in uses:
                    self.assertRegex(ref, r"@(v\d+\.\d+\.\d+|[0-9a-f]{40})$", ref)

            def test_no_script_injection_or_secrets(self):
                for line in SRC.splitlines():
                    stripped = line.strip()
                    if stripped.startswith(("run:", "- run:")):
                        self.assertNotIn("${{", stripped, line)
                        self.assertIsNone(re.search(r"(curl|wget)[^|]*\|\s*(sudo\s+)?(ba|z)?sh\b", stripped), line)
                self.assertNotIn("secrets.", SRC)
                self.assertNotRegex(SRC, r"(?i)echo[^\n]*(secret|token|key)s?\.")

            def test_still_runs_the_tests(self):
                self.assertIn("python -m unittest discover -s tests", SRC)
                self.assertRegex(SRC, r"(?m)^\s{2}test:")
                self.assertIn("actions/checkout@", SRC)
                self.assertIn("runs-on: ubuntu-latest", SRC)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

NGINX = dd(r'''
    user www-data;
    worker_processes auto;

    events {
        worker_connections 1024;
    }

    http {
        include mime.types;
        server_tokens on;
        client_max_body_size 0;

        server {
            listen 80;
            server_name shop.example.com;

            location / {
                proxy_pass http://127.0.0.1:8000;
                proxy_set_header Host $host;
            }

            location /static {
                alias /srv/shop/static/;
                autoindex on;
            }
        }

        server {
            listen 443 ssl;
            server_name shop.example.com;
            ssl_certificate /etc/ssl/shop.crt;
            ssl_certificate_key /etc/ssl/shop.key;
            ssl_protocols TLSv1 TLSv1.1 TLSv1.2;
            ssl_ciphers ALL;

            location / {
                proxy_pass http://127.0.0.1:8000;
                proxy_set_header Host $host;
            }

            location /static {
                alias /srv/shop/static/;
                autoindex on;
            }
        }
    }
''')
HD.append(dict(
    slug="nginx-config", d=3, product="the reverse proxy", func="nginx.conf", cwe="CWE-16",
    finding="the nginx configuration announces its version, serves the app over plain HTTP, offers TLS 1.0/1.1 and every cipher, lists directory contents under `/static`, has an `alias` without the matching trailing slash on its `location` (so `/static../secrets` walks out of the directory), allows unlimited request bodies and sends none of the security headers.",
    start={"nginx.conf": NGINX, "README.md": readme("reverse proxy", "Baseline for `nginx.conf` (it keeps proxying to `http://127.0.0.1:8000` with `Host $host`, serving `/static/` from `/srv/shop/static/` and listening on 80 and 443): `server_tokens off`; `client_max_body_size` of at most 10m (never 0); the port 80 server does nothing but `return 301 https://$host$request_uri;`; "
                                       "the 443 server allows exactly `ssl_protocols TLSv1.2 TLSv1.3;`, sends `Strict-Transport-Security \"max-age=31536000; includeSubDomains\"`, `X-Content-Type-Options \"nosniff\"` and `X-Frame-Options \"DENY\"` with `add_header ... always;`, "
                                       "has `location /static/` (slash on both the location and the alias) and no `autoindex on` anywhere, and denies hidden files with `location ~ /\\. { deny all; }`.")},
    solution={"nginx.conf": dd(r'''
        user www-data;
        worker_processes auto;

        events {
            worker_connections 1024;
        }

        http {
            include mime.types;
            server_tokens off;
            client_max_body_size 10m;

            server {
                listen 80;
                server_name shop.example.com;
                return 301 https://$host$request_uri;
            }

            server {
                listen 443 ssl;
                server_name shop.example.com;
                ssl_certificate /etc/ssl/shop.crt;
                ssl_certificate_key /etc/ssl/shop.key;
                ssl_protocols TLSv1.2 TLSv1.3;
                ssl_ciphers HIGH:!aNULL:!MD5;
                add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
                add_header X-Content-Type-Options "nosniff" always;
                add_header X-Frame-Options "DENY" always;

                location ~ /\. {
                    deny all;
                }

                location / {
                    proxy_pass http://127.0.0.1:8000;
                    proxy_set_header Host $host;
                }

                location /static/ {
                    alias /srv/shop/static/;
                }
            }
        }
    ''')},
    hidden={"tests/test_nginx_security.py": P + dd(r'''
        import re

        with open(os.path.join(ROOT, "nginx.conf"), encoding="utf-8") as fh:
            SRC = "\n".join(line.split("#", 1)[0] for line in fh.read().splitlines())


        def blocks(source, name):
            """The bodies of every `<name> ... { ... }` block (brace matching, no nesting inside the match of the same name)."""
            out = []
            for m in re.finditer(r"(?m)^\s*" + name + r"\b[^{;]*\{", source):
                depth, i = 1, m.end()
                while depth and i < len(source):
                    depth += {"{": 1, "}": -1}.get(source[i], 0)
                    i += 1
                out.append(source[m.end():i - 1])
            return out


        class NginxTest(unittest.TestCase):
            def setUp(self):
                self.servers = blocks(SRC, "server")
                self.plain = [s for s in self.servers if re.search(r"listen\s+80\b", s)]
                self.tls = [s for s in self.servers if re.search(r"listen\s+443\s+ssl\b", s)]

            def test_global_settings(self):
                self.assertRegex(SRC, r"server_tokens\s+off\s*;")
                self.assertNotRegex(SRC, r"server_tokens\s+on")
                sizes = re.findall(r"client_max_body_size\s+(\S+)\s*;", SRC)
                self.assertTrue(sizes)
                for s in sizes:
                    match = re.fullmatch(r"(\d+)([kKmM]?)", s)
                    self.assertTrue(match and int(match.group(1)) > 0, s)
                    mult = {"": 1, "k": 1024, "m": 1024 * 1024}[match.group(2).lower()]
                    self.assertLessEqual(int(match.group(1)) * mult, 10 * 1024 * 1024, s)
                self.assertNotRegex(SRC, r"autoindex\s+on")

            def test_port_80_only_redirects(self):
                self.assertEqual(len(self.plain), 1)
                body = self.plain[0]
                self.assertRegex(body, r"return\s+301\s+https://\$host\$request_uri\s*;")
                self.assertNotIn("proxy_pass", body)
                self.assertNotIn("alias", body)

            def test_tls_server(self):
                self.assertEqual(len(self.tls), 1)
                body = self.tls[0]
                protocols = re.findall(r"ssl_protocols\s+([^;]+);", body)
                self.assertEqual(len(protocols), 1)
                self.assertEqual(sorted(protocols[0].split()), ["TLSv1.2", "TLSv1.3"])
                ciphers = re.findall(r"ssl_ciphers\s+([^;]+);", body)
                self.assertTrue(ciphers and ciphers[0].strip() != "ALL")
                for header, value in (("Strict-Transport-Security", "max-age=31536000; includeSubDomains"), ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY")):
                    self.assertRegex(body, r"add_header\s+" + header + r'\s+"' + re.escape(value) + r'"\s+always\s*;')

            def test_locations(self):
                body = self.tls[0]
                self.assertRegex(body, r"proxy_pass\s+http://127\.0\.0\.1:8000\s*;")
                self.assertRegex(body, r"proxy_set_header\s+Host\s+\$host\s*;")
                self.assertRegex(body, r"location\s+/static/\s*\{[^}]*alias\s+/srv/shop/static/\s*;")
                self.assertNotRegex(body, r"location\s+/static\s*\{")
                for m in re.finditer(r"location\s+(\^~\s+)?(/[^\s{]*)\s*\{[^}]*alias\s+(\S+?);", SRC):
                    self.assertEqual(m.group(2).endswith("/"), m.group(3).endswith("/"), m.group(0))
                self.assertRegex(body, r"location\s+~\s+/\\\.\s*\{\s*deny\s+all\s*;\s*\}")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SSHD = dd(r'''
    # OpenSSH server configuration
    Port 22
    Protocol 2
    PermitRootLogin yes
    PasswordAuthentication yes
    PermitEmptyPasswords yes
    PubkeyAuthentication yes
    X11Forwarding yes
    AllowTcpForwarding yes
    MaxAuthTries 10
    LoginGraceTime 2m
    ClientAliveInterval 0
    ClientAliveCountMax 3
    Ciphers aes128-cbc,aes256-cbc,aes256-ctr,3des-cbc
    MACs hmac-md5,hmac-sha1,hmac-sha2-256
    KexAlgorithms diffie-hellman-group1-sha1,diffie-hellman-group14-sha1,curve25519-sha256
    Subsystem sftp /usr/lib/openssh/sftp-server
''')
HD.append(dict(
    slug="sshd-config", d=2, product="the bastion host", func="sshd_config", cwe="CWE-16",
    finding="`sshd_config` allows root logins and password authentication (also with empty passwords), unlimited-ish guesses, X11 and TCP forwarding, never drops idle sessions, and offers CBC ciphers, MD5 MACs and the 1024-bit group1 key exchange.",
    start={"sshd_config": SSHD, "README.md": readme("bastion host", "Baseline for `sshd_config` (read the way sshd does: the first occurrence of a keyword wins, keywords are case-insensitive, `#` starts a comment): `PermitRootLogin no`; `PasswordAuthentication no`; `PermitEmptyPasswords no`; `X11Forwarding no`; `AllowTcpForwarding no`; `MaxAuthTries` at most 4; `LoginGraceTime` at most 30 seconds; "
                                         "`ClientAliveInterval` between 1 and 300 and `ClientAliveCountMax` at most 3; `Ciphers` only from aes256-gcm@openssh.com, aes128-gcm@openssh.com, chacha20-poly1305@openssh.com, aes256-ctr, aes128-ctr; `MACs` only from hmac-sha2-512-etm@openssh.com, hmac-sha2-256-etm@openssh.com; "
                                         "`KexAlgorithms` only from curve25519-sha256, curve25519-sha256@libssh.org, diffie-hellman-group16-sha512, diffie-hellman-group18-sha512. Port 22, `Protocol 2`, public-key authentication and the sftp subsystem stay.")},
    solution={"sshd_config": dd(r'''
        # OpenSSH server configuration
        Port 22
        Protocol 2
        PermitRootLogin no
        PasswordAuthentication no
        PermitEmptyPasswords no
        PubkeyAuthentication yes
        X11Forwarding no
        AllowTcpForwarding no
        MaxAuthTries 3
        LoginGraceTime 30
        ClientAliveInterval 300
        ClientAliveCountMax 2
        Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr,aes128-ctr
        MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com
        KexAlgorithms curve25519-sha256,curve25519-sha256@libssh.org,diffie-hellman-group16-sha512,diffie-hellman-group18-sha512
        Subsystem sftp /usr/lib/openssh/sftp-server
    ''')},
    hidden={"tests/test_sshd_security.py": P + dd(r'''
        import re


        def parse():
            """keyword (lower case) -> value of its first occurrence, the way sshd reads the file (Match blocks are not used here)."""
            out = {}
            with open(os.path.join(ROOT, "sshd_config"), encoding="utf-8") as fh:
                for raw in fh:
                    line = raw.split("#", 1)[0].strip()
                    if not line:
                        continue
                    parts = line.split(None, 1) if "=" not in line.split()[0] else re.split(r"\s*=\s*", line, maxsplit=1)
                    if len(parts) == 2:
                        out.setdefault(parts[0].lower(), parts[1].strip().strip('"'))
            return out


        def seconds(value):
            m = re.fullmatch(r"(\d+)([smhdw]?)", value.lower())
            return int(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[m.group(2)]


        class SshdTest(unittest.TestCase):
            def setUp(self):
                self.c = parse()

            def test_authentication(self):
                self.assertEqual(self.c["permitrootlogin"].lower(), "no")
                self.assertEqual(self.c["passwordauthentication"].lower(), "no")
                self.assertEqual(self.c["permitemptypasswords"].lower(), "no")
                self.assertEqual(self.c["pubkeyauthentication"].lower(), "yes")
                self.assertLessEqual(int(self.c["maxauthtries"]), 4)
                self.assertLessEqual(seconds(self.c["logingracetime"]), 30)
                self.assertGreater(seconds(self.c["logingracetime"]), 0)

            def test_forwarding_and_sessions(self):
                self.assertEqual(self.c["x11forwarding"].lower(), "no")
                self.assertEqual(self.c["allowtcpforwarding"].lower(), "no")
                self.assertTrue(1 <= int(self.c["clientaliveinterval"]) <= 300)
                self.assertLessEqual(int(self.c["clientalivecountmax"]), 3)

            def test_crypto(self):
                allowed = {"ciphers": {"aes256-gcm@openssh.com", "aes128-gcm@openssh.com", "chacha20-poly1305@openssh.com", "aes256-ctr", "aes128-ctr"},
                           "macs": {"hmac-sha2-512-etm@openssh.com", "hmac-sha2-256-etm@openssh.com"},
                           "kexalgorithms": {"curve25519-sha256", "curve25519-sha256@libssh.org", "diffie-hellman-group16-sha512", "diffie-hellman-group18-sha512"}}
                for key, ok in allowed.items():
                    values = {v.strip() for v in self.c[key].split(",") if v.strip()}
                    self.assertTrue(values, key)
                    self.assertLessEqual(values, ok, (key, values - ok))

            def test_unchanged_settings(self):
                self.assertEqual(self.c["port"], "22")
                self.assertEqual(self.c["protocol"], "2")
                self.assertEqual(self.c["subsystem"], "sftp /usr/lib/openssh/sftp-server")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

ORDER = ["response-headers", "tls-client-context", "error-pages", "sshd-config", "cors-policy", "container-setup", "ci-workflow", "nginx-config"]
HD.sort(key=lambda s: (s["d"], ORDER.index(s["slug"])))


@family("security-harden", category="security", lang="python", kind="fix", n=8,
        summary="hardening to a written baseline: security headers, CORS, TLS client context, error pages, container, CI workflow, nginx and sshd configuration")
def gen_harden(rng, n):
    return list(_sec.emit(rng, HD[:n], tags=["hardening", "configuration"]))
