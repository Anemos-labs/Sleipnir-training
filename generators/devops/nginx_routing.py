"""DevOps tasks: nginx request routing. The agent writes or repairs a configuration; a documented nginx simulator (given to the agent as
tools/ngsim.py) decides what each request would get, on requests the agent has not seen."""
import json
import tempfile
import types
from dataclasses import dataclass, field

from fx import dd, family
from generators.devops import _dokit as K
from generators.devops._ngsim import NGSIM

_mod = types.ModuleType("ngsim")
exec(compile(NGSIM, "ngsim.py", "exec"), _mod.__dict__)
ng = _mod

CHECK_NG = r'''
from dolib import *
sys.path.insert(0, "tests")
import ngsim

spec = json.load(open("tests/cases.json", encoding="utf-8"))
try:
    servers, ups = ngsim.load(spec["path"])
except ngsim.ConfError as e:
    die(f"nginx: configuration error in {spec['path']}: {e}")
files = set(spec["files"])
rep = Report()
for c in spec["cases"]:
    r = c["req"]
    label = f"{r.get('method', 'GET')} {r.get('scheme', 'http')}://{r['host']}{r['uri']}" + (f" (ip {r['ip']})" if "ip" in r else "") + (f" headers {r['headers']}" if "headers" in r else "")
    try:
        res = ngsim.simulate(servers, ups, files, r)
    except ngsim.ConfError as e:
        rep.check(False, f"{label}: configuration error: {e}")
        continue
    bad = ngsim.matches(res, c["expect"])
    rep.check(not bad, f"{label}: " + "; ".join(bad))
rep.finish()
'''

SUBSET_DOC = dd('''
    # The nginx subset understood by `tools/ngsim.py`

    The checker does not run nginx: it simulates it with `tools/ngsim.py` (the same program you have here) on requests you have not seen.
    Run `python3 tools/ngsim.py <conf> examples.json` to see what your configuration answers for the example requests.

    **File.** Regular expressions that contain `{` or `}` (like `\d{4}`) must be quoted, as in real nginx. The `Location` of a redirect is reported exactly as the configuration produces it (relative or absolute). The configuration file holds `upstream`, `map` and `server` blocks at the top level, as if it were included inside `http { }`
    (a surrounding `http { }` is accepted). Syntax errors (a missing `;`, an unbalanced brace, an unknown directive) are reported like `nginx -t` would.
    Understood directives: `listen`, `server_name`, `location`, `return`, `rewrite`, `if`, `set`, `proxy_pass`, `root`, `alias`, `try_files`, `index`, `add_header`, `allow`, `deny`,
    `limit_except`, `map`, `upstream`/`server`. These are accepted and ignored: `proxy_set_header`, `error_page`, `access_log`, `error_log`, `ssl_certificate`,
    `ssl_certificate_key`, `expires`, `client_max_body_size`, `gzip`, `charset`, `keepalive_timeout`, `include`.

    **Choosing a server.** Among the servers that `listen` on the request's port (80 for `http`, 443 for `https`; `listen 443 ssl;` is fine, a bare `listen` means 80), the `Host` is matched against
    `server_name`: exact name, then the longest leading wildcard (`*.example.org`, `.example.org` = the name and all its subdomains), then regular expressions (`~^...$`), then the `default_server`
    (or the first server of that port). Parameters `ssl` and `default_server` of `listen` are understood; `http2`, TLS settings etc. are not needed.

    **Choosing a location** (standard nginx rules, on the path without the query string): an exact `=` location wins; otherwise the longest matching prefix location is remembered; if it is marked
    `^~` it is used; otherwise the regular-expression locations (`~` case-sensitive, `~*` insensitive; Python `re` syntax) are tried in file order and the first match wins; if none matches the remembered prefix
    location is used. If no location matches at all, the server's own directives (`root`, `try_files`, ...) apply, as for an empty `location /`.

    **Request processing** inside the chosen server and location, in this order:
    1. *Rewrite phase*, directives in file order (server level first, then the location): `set $v value;`, `if (...) { ... }`, `rewrite regex replacement [flag];`, `return code [text|url];`.
       `return` ends processing (3xx with a URL gives a `Location` header, other codes a body text). `rewrite` matches the current path: a replacement starting with `http://`, `https://` or `$scheme` redirects (302, or 301 with `permanent`;
       the query string is appended unless the replacement ends in `?`, which is removed); `redirect`/`permanent` flags redirect with 302/301; `last` restarts the location search with the new path (at most 10 times, then 500);
       `break` stops rewriting and stays in the current location; without a flag the next directive runs on the new path. The query string is kept unless the replacement contains `?`.
       Supported conditions of `if`: `($var = value)`, `($var != value)`, `($var ~ regex)`, `($var ~* regex)` and their negations `!~`, `!~*`, and `($var)` (true when not empty and not `0`).
    2. *Access phase*: `allow`/`deny` of the location (or, if it has none, of the server), first match wins, `all` or an address/CIDR; default allow; denied requests get 403. A `limit_except METHODS { deny all; }` block
       applies its rules to requests whose method is not listed (listing GET also allows HEAD).
    3. *Content*: `proxy_pass http://name[/uri];` : if the target has a URI part (even just `/`) the part of the path that matched the (prefix) location is replaced by it, otherwise the path is passed unchanged;
       the query string is always appended. The result is reported as `name` + path (+ `?query`). Otherwise static files: the file is `alias` + (path after the location prefix; with a regex location the alias is used as is,
       so use captures) or `root` + path (default root `html`). With `try_files a b ... last`: each argument is tried in order (`$uri` = the file, `a/` = a directory whose `index` file exists);
       the last argument is a fallback: `=404` answers that status, a `/path` restarts the location search with that path. Without `try_files`: an existing file gives 200; a directory given without a trailing slash is
       redirected (301) to the same path with a slash; a directory with a trailing slash serves its `index` (default `index.html`), else 403; a missing file gives 404.
    4. *Headers*: `add_header Name value [always];` lines apply to the response if its status is 200, 201, 204, 206, 301, 302, 303, 304, 307 or 308 (any status with `always`). As in nginx, a `location` that has
       any `add_header` of its own does not inherit those of its server.

    **Variables**: `$scheme $host $uri $request_uri $args $is_args $request_method $remote_addr $server_name`, captures `$1`..`$9`, `$http_<header>` (lower case, `-` written `_`), `$cookie_<name>`, `$arg_<name>`, and variables defined by
    `set` and `map` (`map $source $target { default x; exact y; ~regex z; ~*regex w; }`, exact strings first, then regular expressions in order, then `default`).

    **Result of a request** (what `examples.json` expectations talk about): `status`; `location` (redirect target); `proxy` (`upstream` + path + query); `file` (the static file served); `body` (text of a `return`); `headers`.
''')


def R(uri, host, scheme="http", method="GET", ip=None, headers=None, port=None, **expect):
    req = {"host": host, "uri": uri}
    if scheme != "http":
        req["scheme"] = scheme
    if method != "GET":
        req["method"] = method
    if ip:
        req["ip"] = ip
    if headers:
        req["headers"] = headers
    if port:
        req["port"] = port
    return {"req": req, **({"expect": expect} if expect else {})}


@dataclass
class NgSpec:
    slug: str
    d: int
    prompt: str
    path: str
    ref: str
    start: str
    files: list
    examples: list  # R(...) with hand-written expectations
    cases: list  # R(...); expectations derived from the reference when missing
    wrong: list = field(default_factory=list)  # confs that must be rejected
    kind: str = "author"


def simulate_conf(conf, files, req):
    with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
        f.write(conf)
    servers, ups = ng.load(f.name)
    return ng.simulate(servers, ups, set(files), req)


def derive(res):
    out = {k: v for k, v in res.items() if k != "note"}
    if out.get("status") != 200:
        out.pop("file", None)
    return out


def make_task(sp: NgSpec):
    for c in sp.examples:
        res = simulate_conf(sp.ref, sp.files, c["req"])
        bad = ng.matches(res, c["expect"])
        if bad:
            raise RuntimeError(f"{sp.slug}: example {c['req']} disagrees with the reference: {bad} (got {res})")
    cases = []
    for c in sp.examples + sp.cases:
        res = simulate_conf(sp.ref, sp.files, c["req"])
        cases.append({"req": c["req"], "expect": derive(res)})
    shown = [dict(c) for c in sp.examples]
    start = {sp.path: sp.start, "tools/ngsim.py": NGSIM, "NGINX_SUBSET.md": SUBSET_DOC, "examples.json": json.dumps({"files": sp.files, "cases": shown}, indent=1) + "\n",
             "README.md": f"# nginx routing exercise\n\nEdit `{sp.path}`. Run `python3 tools/ngsim.py {sp.path} examples.json` to see how the configuration answers the example requests; `NGINX_SUBSET.md` documents the simulator.\n"}
    hidden = {"tests/ngsim.py": "# verifier copy of tools/ngsim.py\n" + NGSIM, "tests/cases.json": json.dumps({"path": sp.path, "files": sp.files, "cases": cases}, indent=1) + "\n"}
    t = K.devops_task(sp.slug, sp.d, sp.prompt, start, {sp.path: sp.ref}, CHECK_NG, hidden, lang="text", kind="fix" if sp.kind == "fix" else "greenfield", tags=["nginx", "routing", "config"])
    return K.finish(t, wrong=[{sp.path: w} for w in sp.wrong])


SPECS: list[NgSpec] = []


def spec(**kw):
    SPECS.append(NgSpec(**kw))


# ---------------------------------------------------------------------------------------------------- 1. https redirect

spec(slug="https-redirect-acme", d=2, path="conf.d/quayside.conf", kind="author",
     prompt=dd('''
        Write `conf.d/quayside.conf` (it is included inside `http { }`) for the site quayside.example. Requirements:

        1. Plain HTTP (port 80) for `quayside.example` and `www.quayside.example`: every request gets a permanent redirect (301) to `https://quayside.example` followed by the original request URI (path and query string),
           except requests under `/.well-known/acme-challenge/`, which are served as static files from the web root `/var/lib/acme/www` (so `/.well-known/acme-challenge/tok` is the file `/var/lib/acme/www/.well-known/acme-challenge/tok`).
        2. HTTPS (port 443, `ssl`) for `www.quayside.example`: permanent redirect (301) to `https://quayside.example` plus the original URI.
        3. HTTPS for `quayside.example`: the static site in `/srv/quayside/public` (default index file `index.html`).

        TLS certificates are out of scope. `NGINX_SUBSET.md` documents what the checker simulates; `examples.json` has a few requests with the expected answers.
     '''),
     start="# quayside.example\n", files=["/var/lib/acme/www/.well-known/acme-challenge/tok", "/srv/quayside/public/index.html", "/srv/quayside/public/tides/index.html", "/srv/quayside/public/css/site.css"],
     ref=dd('''
        server {
            listen 80;
            server_name quayside.example www.quayside.example;
            location /.well-known/acme-challenge/ {
                root /var/lib/acme/www;
            }
            location / {
                return 301 https://quayside.example$request_uri;
            }
        }
        server {
            listen 443 ssl;
            server_name www.quayside.example;
            ssl_certificate /etc/ssl/quayside.pem;
            ssl_certificate_key /etc/ssl/quayside.key;
            return 301 https://quayside.example$request_uri;
        }
        server {
            listen 443 ssl;
            server_name quayside.example;
            ssl_certificate /etc/ssl/quayside.pem;
            ssl_certificate_key /etc/ssl/quayside.key;
            root /srv/quayside/public;
            index index.html;
        }
     '''),
     examples=[R("/tides?port=7", "quayside.example", status=301, location="https://quayside.example/tides?port=7"),
               R("/.well-known/acme-challenge/tok", "www.quayside.example", status=200, file="/var/lib/acme/www/.well-known/acme-challenge/tok"),
               R("/", "www.quayside.example", "https", status=301, location="https://quayside.example/"),
               R("/css/site.css", "quayside.example", "https", status=200, file="/srv/quayside/public/css/site.css")],
     cases=[R("/", "quayside.example"), R("/a/b/c?x=1&y=2", "www.quayside.example"), R("/.well-known/acme-challenge/other", "quayside.example"), R("/.well-known/acme-challenge/tok", "quayside.example"),
            R("/.well-known/security.txt", "quayside.example"), R("/", "quayside.example", "https"), R("/tides/", "quayside.example", "https"), R("/tides", "quayside.example", "https"), R("/missing.html", "quayside.example", "https"),
            R("/x/y?z=%20", "www.quayside.example", "https"), R("/", "WWW.Quayside.Example", "https"), R("/css/site.css", "www.quayside.example", "https"), R("/.well-known/acme-challenge/", "www.quayside.example")],
     wrong=[dd('''
        server { listen 80; server_name quayside.example www.quayside.example; return 301 https://quayside.example$request_uri; }
        server { listen 443 ssl; server_name www.quayside.example; return 301 https://quayside.example$request_uri; }
        server { listen 443 ssl; server_name quayside.example; root /srv/quayside/public; }
     '''), dd('''
        server { listen 80; server_name quayside.example www.quayside.example;
          location /.well-known/acme-challenge/ { root /var/lib/acme/www; }
          location / { return 302 https://quayside.example$request_uri; } }
        server { listen 443 ssl; server_name www.quayside.example; return 301 https://quayside.example$request_uri; }
        server { listen 443 ssl; server_name quayside.example; root /srv/quayside/public; }
     ''')])

# ---------------------------------------------------------------------------------------------------- 2. location precedence (fix)

spec(slug="location-precedence-fix", d=3, path="conf.d/tally.conf", kind="fix",
     prompt=dd('''
        `conf.d/tally.conf` should route requests for tally.example like this, but the stylesheets under `/static/` come back from the wrong directory and `/api/chart.png` never reaches the application.
        Fix the configuration (the file is included inside `http { }`; keep the upstream). Required behaviour:

        - Every path under `/api/` goes to the upstream `tally_app` with the path unchanged (even `/api/chart.png`).
        - Every path under `/static/` is served from `/srv/tally/assets/`: `/static/css/site.css` is the file `/srv/tally/assets/css/site.css` (even though it ends in `.css`).
        - Anywhere else, URIs ending in `.css`, `.js`, `.png` or `.svg` (case-insensitively, e.g. `/photo.PNG`) are served from `/srv/tally/assets` with the URI appended (`/logo.svg` is `/srv/tally/assets/logo.svg`).
        - Everything else goes to `tally_app` with the path unchanged.
     '''),
     start=dd('''
        upstream tally_app {
            server 127.0.0.1:9100;
        }
        server {
            listen 80;
            server_name tally.example;
            root /srv/tally;
            location ~* \\.(css|js|png|svg)$ {
                root /srv/tally/assets;
            }
            location /api/ {
                proxy_pass http://tally_app;
            }
            location /static/ {
                alias /srv/tally/assets/;
            }
            location / {
                proxy_pass http://tally_app;
            }
        }
     '''), files=["/srv/tally/assets/css/site.css", "/srv/tally/assets/logo.svg", "/srv/tally/assets/photo.PNG", "/srv/tally/assets/js/app.js", "/srv/tally/assets/img/a.png"],
     ref=dd('''
        upstream tally_app {
            server 127.0.0.1:9100;
        }
        server {
            listen 80;
            server_name tally.example;
            root /srv/tally;
            location ~* \\.(css|js|png|svg)$ {
                root /srv/tally/assets;
            }
            location ^~ /api/ {
                proxy_pass http://tally_app;
            }
            location ^~ /static/ {
                alias /srv/tally/assets/;
            }
            location / {
                proxy_pass http://tally_app;
            }
        }
     '''),
     examples=[R("/api/chart.png", "tally.example", status=200, proxy="tally_app/api/chart.png"), R("/static/css/site.css", "tally.example", status=200, file="/srv/tally/assets/css/site.css"),
               R("/logo.svg", "tally.example", status=200, file="/srv/tally/assets/logo.svg"), R("/reports/2024", "tally.example", proxy="tally_app/reports/2024")],
     cases=[R("/api/", "tally.example"), R("/api/v1/items?id=7", "tally.example"), R("/api/x.js", "tally.example"), R("/static/js/app.js", "tally.example"), R("/static/img/a.png", "tally.example"),
            R("/static/missing.css", "tally.example"), R("/photo.PNG", "tally.example"), R("/js/app.js", "tally.example"), R("/img/a.png", "tally.example"), R("/", "tally.example"), R("/api", "tally.example"),
            R("/staticfile", "tally.example"), R("/dashboard/chart.svg?v=2", "tally.example"), R("/static/", "tally.example"), R("/a.css.map", "tally.example"), R("/apidocs/index.html", "tally.example")],
     wrong=[dd('''
        upstream tally_app { server 127.0.0.1:9100; }
        server { listen 80; server_name tally.example; root /srv/tally;
          location ~* \\.(css|js|png|svg)$ { root /srv/tally/assets; }
          location ^~ /api/ { proxy_pass http://tally_app; }
          location /static/ { alias /srv/tally/assets/; }
          location / { proxy_pass http://tally_app; } }
     '''), dd('''
        upstream tally_app { server 127.0.0.1:9100; }
        server { listen 80; server_name tally.example; root /srv/tally;
          location ~ \\.(css|js|png|svg)$ { root /srv/tally/assets; }
          location ^~ /api/ { proxy_pass http://tally_app; }
          location ^~ /static/ { alias /srv/tally/assets/; }
          location / { proxy_pass http://tally_app; } }
     ''')])

# ---------------------------------------------------------------------------------------------------- 3. proxy_pass URI part (fix)

spec(slug="proxy-prefix-fix", d=3, path="conf.d/ledger.conf", kind="fix",
     prompt=dd('''
        The reverse proxy in `conf.d/ledger.conf` forwards requests with the wrong paths: the backends receive the public prefixes they know nothing about. Fix it. Required behaviour for host `ledger.example`
        (all paths are given as public path -> path received by the upstream; the query string is always passed on):

        - `/ledger/<rest>` -> upstream `ledger_v1`, path `/<rest>` (the `/ledger` prefix is removed; `/ledger/` itself becomes `/`).
        - `/reports/<rest>` -> upstream `ledger_v1`, path `/internal/reports/<rest>`.
        - exactly `/ping` -> upstream `ledger_v1`, path `/healthz`.
        - `/legacy/<rest>` -> upstream `ledger_v2`, path unchanged (`/legacy/<rest>`).
        - anything else: 404 (answered by nginx itself, no proxying).
     '''),
     start=dd('''
        upstream ledger_v1 {
            server 10.1.0.11:7000;
        }
        upstream ledger_v2 {
            server 10.1.0.12:7000;
        }
        server {
            listen 80;
            server_name ledger.example;
            location /ledger/ {
                proxy_pass http://ledger_v1;
            }
            location /reports/ {
                proxy_pass http://ledger_v1/internal/reports;
            }
            location = /ping {
                proxy_pass http://ledger_v1/healthz/;
            }
            location /legacy/ {
                proxy_pass http://ledger_v2/;
            }
            location / {
                return 404;
            }
        }
     '''), files=[],
     ref=dd('''
        upstream ledger_v1 {
            server 10.1.0.11:7000;
        }
        upstream ledger_v2 {
            server 10.1.0.12:7000;
        }
        server {
            listen 80;
            server_name ledger.example;
            location /ledger/ {
                proxy_pass http://ledger_v1/;
            }
            location /reports/ {
                proxy_pass http://ledger_v1/internal/reports/;
            }
            location = /ping {
                proxy_pass http://ledger_v1/healthz;
            }
            location /legacy/ {
                proxy_pass http://ledger_v2;
            }
            location / {
                return 404;
            }
        }
     '''),
     examples=[R("/ledger/accounts/7?full=1", "ledger.example", proxy="ledger_v1/accounts/7?full=1"), R("/reports/q3", "ledger.example", proxy="ledger_v1/internal/reports/q3"),
               R("/ping", "ledger.example", proxy="ledger_v1/healthz"), R("/legacy/old/thing", "ledger.example", proxy="ledger_v2/legacy/old/thing"), R("/nothing", "ledger.example", status=404)],
     cases=[R("/ledger/", "ledger.example"), R("/ledger/a/b/c", "ledger.example"), R("/ledger/x?y=1&z=2", "ledger.example"), R("/ledger", "ledger.example"), R("/reports/", "ledger.example"), R("/reports/2024/q1?fmt=csv", "ledger.example"),
            R("/ping?deep=1", "ledger.example"), R("/ping/", "ledger.example"), R("/legacy/", "ledger.example"), R("/legacy/a?b=c", "ledger.example"), R("/", "ledger.example"), R("/ledgerx/a", "ledger.example"), R("/internal/reports/q3", "ledger.example")],
     wrong=[dd('''
        upstream ledger_v1 { server 10.1.0.11:7000; }
        upstream ledger_v2 { server 10.1.0.12:7000; }
        server { listen 80; server_name ledger.example;
          location /ledger/ { proxy_pass http://ledger_v1/; }
          location /reports/ { proxy_pass http://ledger_v1/internal/reports; }
          location = /ping { proxy_pass http://ledger_v1/healthz; }
          location /legacy/ { proxy_pass http://ledger_v2; }
          location / { return 404; } }
     ''')])

# ---------------------------------------------------------------------------------------------------- 4. alias vs root (fix)

spec(slug="alias-root-fix", d=3, path="conf.d/files.conf", kind="fix",
     prompt=dd('''
        `conf.d/files.conf` serves the wrong files: downloads and images 404 although the files exist, and thumbnails are looked up in the wrong place. Fix it so that, for host `files.example`:

        - `/downloads/<name>` is the file `/srv/files/public/<name>`;
        - `/images/<name>` is the file `/srv/files/img/<name>` (the URI prefix does not appear on disk);
        - `/thumb/<size>/<name>`, where `<size>` is digits only, is the file `/srv/files/thumbs/<size>/<name>`;
        - every other path is served from `/srv/files/site` (path appended; default index `index.html`).
     '''),
     start=dd('''
        server {
            listen 80;
            server_name files.example;
            root /srv/files/site;
            location /downloads/ {
                alias /srv/files/public;
            }
            location /images/ {
                root /srv/files/img;
            }
            location ~ ^/thumb/(\\d+)/(.+)$ {
                root /srv/files/thumbs;
            }
        }
     '''), files=["/srv/files/public/a.zip", "/srv/files/public/docs/b.pdf", "/srv/files/img/logo.png", "/srv/files/img/x/y.png", "/srv/files/thumbs/64/logo.png", "/srv/files/thumbs/128/x/y.png", "/srv/files/site/index.html", "/srv/files/site/about/index.html", "/srv/files/site/robots.txt"],
     ref=dd('''
        server {
            listen 80;
            server_name files.example;
            root /srv/files/site;
            location /downloads/ {
                alias /srv/files/public/;
            }
            location /images/ {
                alias /srv/files/img/;
            }
            location ~ ^/thumb/(\\d+)/(.+)$ {
                alias /srv/files/thumbs/$1/$2;
            }
        }
     '''),
     examples=[R("/downloads/a.zip", "files.example", status=200, file="/srv/files/public/a.zip"), R("/images/logo.png", "files.example", status=200, file="/srv/files/img/logo.png"),
               R("/thumb/64/logo.png", "files.example", status=200, file="/srv/files/thumbs/64/logo.png"), R("/robots.txt", "files.example", status=200, file="/srv/files/site/robots.txt")],
     cases=[R("/downloads/docs/b.pdf", "files.example"), R("/downloads/missing.zip", "files.example"), R("/images/x/y.png", "files.example"), R("/images/nope.png", "files.example"), R("/thumb/128/x/y.png", "files.example"),
            R("/thumb/abc/logo.png", "files.example"), R("/thumb/64/missing.png", "files.example"), R("/", "files.example"), R("/about/", "files.example"), R("/about", "files.example"), R("/downloads/", "files.example"),
            R("/downloadsx/a.zip", "files.example"), R("/index.html", "files.example"), R("/images/", "files.example")],
     wrong=[dd('''
        server { listen 80; server_name files.example; root /srv/files/site;
          location /downloads/ { alias /srv/files/public/; }
          location /images/ { alias /srv/files/img/; }
          location ~ ^/thumb/(\\d+)/(.+)$ { alias /srv/files/thumbs/$2; } }
     ''')])

# ---------------------------------------------------------------------------------------------------- 5. dotfiles and methods

spec(slug="dotfiles-and-admin", d=3, path="conf.d/notebook.conf", kind="author",
     prompt=dd('''
        Write `conf.d/notebook.conf` for `notebook.example` (port 80), a static site in `/srv/notebook` (default index file). Rules:

        - Any request whose path contains a segment starting with a dot (`/.git/config`, `/a/.env`, `/admin/.secret`) is answered 403, except paths under `/.well-known/`, which are served normally from the site.
        - A request whose path ends in `~` or in `.bak` is answered 404 (without looking at the disk).
        - Paths under `/admin/` are only available to clients in `10.0.0.0/8` or `127.0.0.1`; everybody else gets 403. (Dotfiles under `/admin/` stay forbidden for everybody.)
        - Everywhere only GET and HEAD are allowed: other methods are answered 403 (use `limit_except`) - except for paths under `/guestbook/`, which also accept POST.
     '''),
     start="# notebook.example\n", files=["/srv/notebook/index.html", "/srv/notebook/.well-known/security.txt", "/srv/notebook/admin/index.html", "/srv/notebook/admin/stats.html", "/srv/notebook/guestbook/index.html", "/srv/notebook/posts/one.html", "/srv/notebook/.git/config"],
     ref=dd('''
        server {
            listen 80;
            server_name notebook.example;
            root /srv/notebook;
            location / {
                limit_except GET {
                    deny all;
                }
            }
            location ^~ /.well-known/ {
                limit_except GET {
                    deny all;
                }
            }
            location ~ /\\. {
                return 403;
            }
            location ~ (~|\\.bak)$ {
                return 404;
            }
            location /admin/ {
                limit_except GET {
                    deny all;
                }
                allow 10.0.0.0/8;
                allow 127.0.0.1;
                deny all;
            }
            location /guestbook/ {
                limit_except GET POST {
                    deny all;
                }
            }
        }
     '''),
     examples=[R("/.git/config", "notebook.example", status=403), R("/.well-known/security.txt", "notebook.example", status=200, file="/srv/notebook/.well-known/security.txt"),
               R("/posts/one.html~", "notebook.example", status=404), R("/admin/stats.html", "notebook.example", status=403, ip="203.0.113.7"), R("/admin/stats.html", "notebook.example", status=200, ip="10.2.3.4", file="/srv/notebook/admin/stats.html"),
               R("/posts/one.html", "notebook.example", method="POST", status=403), R("/guestbook/", "notebook.example", method="POST", status=200)],
     cases=[R("/", "notebook.example"), R("/a/.env", "notebook.example"), R("/admin/.secret", "notebook.example", ip="10.0.0.1"), R("/admin/.secret", "notebook.example", ip="127.0.0.1"), R("/.well-known/", "notebook.example"),
            R("/.well-known/nothing.txt", "notebook.example"), R("/index.html.bak", "notebook.example"), R("/posts/one.html.bak", "notebook.example"), R("/.hidden/page.html", "notebook.example"), R("/admin/", "notebook.example", ip="127.0.0.1"),
            R("/admin/", "notebook.example", ip="192.168.1.1"), R("/admin/stats.html", "notebook.example", ip="11.0.0.1"), R("/admin/stats.html", "notebook.example", ip="10.255.255.254"),
            R("/admin/stats.html", "notebook.example", method="POST", ip="10.0.0.1"), R("/posts/one.html", "notebook.example", method="HEAD"), R("/posts/one.html", "notebook.example", method="PUT"), R("/guestbook/", "notebook.example", method="PUT"),
            R("/guestbook/", "notebook.example", method="GET"), R("/guestbook/", "notebook.example", method="POST"), R("/guestbook/entry~", "notebook.example", method="POST"), R("/posts/.draft/one.html", "notebook.example", method="DELETE")],
     wrong=[dd('''
        server { listen 80; server_name notebook.example; root /srv/notebook;
          location ~ /\\. { return 403; }
          location ~ (~|\\.bak)$ { return 404; }
          location /admin/ { allow 10.0.0.0/8; allow 127.0.0.1; deny all; }
          location / { limit_except GET { deny all; } } }
     ''')])


# ---------------------------------------------------------------------------------------------------- 6. SPA fallback

spec(slug="spa-fallback", d=3, path="conf.d/harbourlight.conf", kind="author",
     prompt=dd('''
        Write `conf.d/harbourlight.conf` for `harbourlight.example` (port 80), a single-page application built into `/srv/hl/dist`. An upstream `hl_api` (see below) is provided in the file already; keep it.

        - Exactly `/healthz` answers 200 with the body `ok` (nginx itself).
        - Everything under `/api/` goes to `hl_api`, path unchanged.
        - Everything under `/assets/` is served from `/srv/hl/dist/assets/...`, with the header `Cache-Control: public, max-age=31536000, immutable`. A missing asset is a plain 404 (it must not fall back to the application page).
        - `/index.html` (also when reached as the fallback) carries `Cache-Control: no-cache`.
        - Any other path: the file under `/srv/hl/dist` if it exists (e.g. `/favicon.ico`, `/robots.txt`), a directory with its index, and otherwise the application page `/index.html` (client-side routes such as `/boats/42`).
     '''),
     start="upstream hl_api {\n    server 127.0.0.1:4100;\n}\n", files=["/srv/hl/dist/index.html", "/srv/hl/dist/favicon.ico", "/srv/hl/dist/robots.txt", "/srv/hl/dist/assets/app.3f9a.js", "/srv/hl/dist/assets/logo.png", "/srv/hl/dist/docs/index.html"],
     ref=dd('''
        upstream hl_api {
            server 127.0.0.1:4100;
        }
        server {
            listen 80;
            server_name harbourlight.example;
            root /srv/hl/dist;
            location = /healthz {
                return 200 ok;
            }
            location ^~ /api/ {
                proxy_pass http://hl_api;
            }
            location ^~ /assets/ {
                add_header Cache-Control "public, max-age=31536000, immutable";
                try_files $uri =404;
            }
            location = /index.html {
                add_header Cache-Control "no-cache";
            }
            location / {
                try_files $uri $uri/ /index.html;
            }
        }
     '''),
     examples=[R("/healthz", "harbourlight.example", status=200, body="ok"), R("/api/boats?x=1", "harbourlight.example", proxy="hl_api/api/boats?x=1"),
               R("/assets/logo.png", "harbourlight.example", status=200, file="/srv/hl/dist/assets/logo.png", headers={"Cache-Control": "public, max-age=31536000, immutable"}),
               R("/boats/42", "harbourlight.example", status=200, file="/srv/hl/dist/index.html", headers={"Cache-Control": "no-cache"}), R("/assets/gone.js", "harbourlight.example", status=404)],
     cases=[R("/", "harbourlight.example"), R("/index.html", "harbourlight.example"), R("/favicon.ico", "harbourlight.example"), R("/robots.txt", "harbourlight.example"), R("/docs/", "harbourlight.example"), R("/docs", "harbourlight.example"),
            R("/healthz/", "harbourlight.example"), R("/api/", "harbourlight.example"), R("/api/v2/crew/7?lang=fr", "harbourlight.example"), R("/apiary", "harbourlight.example"), R("/assets/app.3f9a.js", "harbourlight.example"),
            R("/assets/nothing/here.css", "harbourlight.example"), R("/settings/profile?tab=2", "harbourlight.example"), R("/boats/42/crew", "harbourlight.example"), R("/assets", "harbourlight.example")],
     wrong=[dd('''
        upstream hl_api { server 127.0.0.1:4100; }
        server { listen 80; server_name harbourlight.example; root /srv/hl/dist;
          location = /healthz { return 200 ok; }
          location ^~ /api/ { proxy_pass http://hl_api; }
          location ^~ /assets/ { add_header Cache-Control "public, max-age=31536000, immutable"; try_files $uri /index.html; }
          location = /index.html { add_header Cache-Control "no-cache"; }
          location / { try_files $uri $uri/ /index.html; } }
     ''')])

# ---------------------------------------------------------------------------------------------------- 7. virtual hosts

spec(slug="vhosts-default", d=3, path="conf.d/zinc.conf", kind="author",
     prompt=dd('''
        Write `conf.d/zinc.conf` with the name-based virtual hosts of zinc.example (HTTP only, ports 80 and 8080):

        - Port 80, host `shop.zinc.example`: static files from `/srv/zinc/shop`.
        - Port 80, host `blog.zinc.example`: static files from `/srv/zinc/blog`.
        - Port 80, any other host below `zinc.example` (`*.zinc.example`, e.g. `docs.zinc.example`) and `zinc.example` itself: temporary redirect (302) to `http://shop.zinc.example` followed by the original URI.
        - Port 80, every other `Host` (including an IP address or an unknown domain): answer 421.
        - Port 8080, host `ops.zinc.example`: static files from `/srv/zinc/ops`, only for clients in `192.168.0.0/16` (403 for everybody else). Requests on 8080 for another host are answered 421 as well.
     '''),
     start="# zinc.example\n", files=["/srv/zinc/shop/index.html", "/srv/zinc/shop/cart/index.html", "/srv/zinc/blog/index.html", "/srv/zinc/blog/2024/index.html", "/srv/zinc/ops/index.html", "/srv/zinc/ops/status.txt"],
     ref=dd('''
        server {
            listen 80 default_server;
            server_name _;
            return 421;
        }
        server {
            listen 80;
            server_name shop.zinc.example;
            root /srv/zinc/shop;
        }
        server {
            listen 80;
            server_name blog.zinc.example;
            root /srv/zinc/blog;
        }
        server {
            listen 80;
            server_name zinc.example *.zinc.example;
            return 302 http://shop.zinc.example$request_uri;
        }
        server {
            listen 8080 default_server;
            server_name _;
            return 421;
        }
        server {
            listen 8080;
            server_name ops.zinc.example;
            root /srv/zinc/ops;
            allow 192.168.0.0/16;
            deny all;
        }
     '''),
     examples=[R("/cart/", "shop.zinc.example", status=200, file="/srv/zinc/shop/cart/index.html"), R("/2024/", "blog.zinc.example", status=200, file="/srv/zinc/blog/2024/index.html"),
               R("/guide?p=2", "docs.zinc.example", status=302, location="http://shop.zinc.example/guide?p=2"), R("/", "203.0.113.5", status=421),
               R("/status.txt", "ops.zinc.example", port=8080, ip="192.168.4.4", status=200, file="/srv/zinc/ops/status.txt")],
     cases=[R("/", "shop.zinc.example"), R("/", "blog.zinc.example"), R("/", "zinc.example"), R("/a/b?c=d", "zinc.example"), R("/", "www.zinc.example"), R("/x", "a.b.zinc.example"), R("/", "SHOP.ZINC.EXAMPLE"), R("/", "shop.zinc.example:80"),
            R("/", "zinc.example.evil.net"), R("/", "example.org"), R("/", "10.9.8.7"), R("/", "ops.zinc.example"), R("/index.html", "blog.zinc.example"), R("/missing", "shop.zinc.example"), R("/cart", "shop.zinc.example"),
            R("/", "ops.zinc.example", port=8080, ip="192.168.1.1"), R("/status.txt", "ops.zinc.example", port=8080, ip="192.169.0.1"), R("/", "ops.zinc.example", port=8080, ip="10.0.0.1"), R("/", "shop.zinc.example", port=8080, ip="192.168.1.1"),
            R("/", "zinc.example", port=8080), R("/", "ops.zinc.example", port=8080, ip="192.168.255.255")],
     wrong=[dd('''
        server { listen 80 default_server; server_name _; return 421; }
        server { listen 80; server_name shop.zinc.example; root /srv/zinc/shop; }
        server { listen 80; server_name blog.zinc.example; root /srv/zinc/blog; }
        server { listen 80; server_name .zinc.example; return 302 http://shop.zinc.example$request_uri; }
     ''')])

# ---------------------------------------------------------------------------------------------------- 8. add_header inheritance (fix)

spec(slug="header-inheritance-fix", d=4, path="conf.d/fernlab.conf", kind="fix",
     prompt=dd('''
        Security headers keep disappearing from some responses of `fernlab.example`. Fix `conf.d/fernlab.conf` so that:

        - every successful or redirect response (any location, any upstream) carries `Strict-Transport-Security: max-age=63072000` and `X-Content-Type-Options: nosniff`;
        - error responses produced by nginx itself (404 and 403 from `return` or a missing file) carry both of them too;
        - files under `/downloads/` additionally carry `Content-Disposition: attachment`; files under `/assets/` additionally carry `Cache-Control: public, max-age=86400`;
        - the routing stays as it is (`/api/` -> `fern_api`, `/downloads/` and `/assets/` static from `/srv/fern`, `/old` redirects 301 to `/new`, `/secret/` is 403).

        Remember how nginx inherits `add_header`: a location that declares any `add_header` does not inherit the ones of its server.
     '''),
     start=dd('''
        upstream fern_api {
            server 127.0.0.1:5200;
        }
        server {
            listen 80;
            server_name fernlab.example;
            root /srv/fern;
            add_header Strict-Transport-Security "max-age=63072000";
            add_header X-Content-Type-Options "nosniff";
            location /api/ {
                proxy_pass http://fern_api;
            }
            location /downloads/ {
                add_header Content-Disposition "attachment";
            }
            location /assets/ {
                add_header Cache-Control "public, max-age=86400";
            }
            location = /old {
                return 301 /new;
            }
            location /secret/ {
                return 403;
            }
        }
     '''), files=["/srv/fern/index.html", "/srv/fern/downloads/a.tar", "/srv/fern/assets/app.css", "/srv/fern/new"],
     ref=dd('''
        upstream fern_api {
            server 127.0.0.1:5200;
        }
        server {
            listen 80;
            server_name fernlab.example;
            root /srv/fern;
            add_header Strict-Transport-Security "max-age=63072000" always;
            add_header X-Content-Type-Options "nosniff" always;
            location /api/ {
                proxy_pass http://fern_api;
            }
            location /downloads/ {
                add_header Strict-Transport-Security "max-age=63072000" always;
                add_header X-Content-Type-Options "nosniff" always;
                add_header Content-Disposition "attachment";
            }
            location /assets/ {
                add_header Strict-Transport-Security "max-age=63072000" always;
                add_header X-Content-Type-Options "nosniff" always;
                add_header Cache-Control "public, max-age=86400";
            }
            location = /old {
                return 301 /new;
            }
            location /secret/ {
                return 403;
            }
        }
     '''),
     examples=[R("/assets/app.css", "fernlab.example", status=200, headers={"Strict-Transport-Security": "max-age=63072000", "Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"}),
               R("/downloads/a.tar", "fernlab.example", status=200, headers={"Content-Disposition": "attachment", "Strict-Transport-Security": "max-age=63072000"}),
               R("/nothing", "fernlab.example", status=404, headers={"X-Content-Type-Options": "nosniff"})],
     cases=[R("/", "fernlab.example"), R("/api/x", "fernlab.example"), R("/downloads/a.tar", "fernlab.example"), R("/downloads/missing.tar", "fernlab.example"), R("/assets/app.css", "fernlab.example"), R("/assets/none.css", "fernlab.example"),
            R("/old", "fernlab.example"), R("/secret/", "fernlab.example"), R("/secret/key", "fernlab.example"), R("/new", "fernlab.example"), R("/zzz", "fernlab.example"), R("/index.html", "fernlab.example"), R("/api/", "fernlab.example")],
     wrong=[dd('''
        upstream fern_api { server 127.0.0.1:5200; }
        server { listen 80; server_name fernlab.example; root /srv/fern;
          add_header Strict-Transport-Security "max-age=63072000" always;
          add_header X-Content-Type-Options "nosniff" always;
          location /api/ { proxy_pass http://fern_api; }
          location /downloads/ { add_header Content-Disposition "attachment"; }
          location /assets/ { add_header Cache-Control "public, max-age=86400"; }
          location = /old { return 301 /new; }
          location /secret/ { return 403; } }
     '''), dd('''
        upstream fern_api { server 127.0.0.1:5200; }
        server { listen 80; server_name fernlab.example; root /srv/fern;
          add_header Strict-Transport-Security "max-age=63072000";
          add_header X-Content-Type-Options "nosniff";
          location /api/ { proxy_pass http://fern_api; }
          location /downloads/ { add_header Strict-Transport-Security "max-age=63072000"; add_header X-Content-Type-Options "nosniff"; add_header Content-Disposition "attachment"; }
          location /assets/ { add_header Strict-Transport-Security "max-age=63072000"; add_header X-Content-Type-Options "nosniff"; add_header Cache-Control "public, max-age=86400"; }
          location = /old { return 301 /new; }
          location /secret/ { return 403; } }
     ''')])

# ---------------------------------------------------------------------------------------------------- 9. legacy redirects

spec(slug="legacy-redirects", d=4, path="conf.d/archive.conf", kind="author",
     prompt=dd('''
        Write `conf.d/archive.conf` for `archive.example` (port 80) that keeps old URLs alive. Redirects keep the query string unless said otherwise. Static files live in `/srv/archive/www` (default index).

        1. `/v1/<rest>` -> permanent redirect (301) to `/api/v2/<rest>`.
        2. `/blog/<year>/<month>/<slug>` where year is 4 digits and month 2 digits -> permanent redirect to `/posts/<slug>` (query string dropped).
        3. `/old-docs/` and everything below it -> temporary redirect (302) to `https://docs.example.org/` followed by the rest of the path below `/old-docs/` (`/old-docs/guide/intro` -> `https://docs.example.org/guide/intro`).
        4. A path ending in `/` (except the root `/` itself) -> permanent redirect to the same path without the trailing slash (`/posts/x/` -> `/posts/x`); the query string is kept. This must not apply to the paths of rules 1-3, which use their own redirect.
        5. Anything else is served as static files.
     '''),
     start="# archive.example\n", files=["/srv/archive/www/index.html", "/srv/archive/www/posts/hello", "/srv/archive/www/posts/index.html", "/srv/archive/www/about.html", "/srv/archive/www/api/v2/index.html"],
     ref=dd('''
        server {
            listen 80;
            server_name archive.example;
            root /srv/archive/www;
            location ^~ /v1/ {
                rewrite ^/v1/(.*)$ /api/v2/$1 permanent;
            }
            location ~ "^/blog/\\d{4}/\\d{2}/([^/]+)$" {
                rewrite "^/blog/\\d{4}/\\d{2}/([^/]+)$" /posts/$1? permanent;
            }
            location ^~ /old-docs/ {
                rewrite ^/old-docs/(.*)$ https://docs.example.org/$1 redirect;
            }
            location ~ ^(.+)/$ {
                return 301 $1$is_args$args;
            }
        }
     '''),
     examples=[R("/v1/users?id=3", "archive.example", status=301, location="/api/v2/users?id=3"), R("/blog/2024/03/hello?utm=x", "archive.example", status=301, location="/posts/hello"),
               R("/old-docs/guide/intro", "archive.example", status=302, location="https://docs.example.org/guide/intro"), R("/posts/x/?a=1", "archive.example", status=301, location="/posts/x?a=1"),
               R("/about.html", "archive.example", status=200, file="/srv/archive/www/about.html")],
     cases=[R("/v1/", "archive.example"), R("/v1/a/b/c?x=1", "archive.example"), R("/v1", "archive.example"), R("/blog/2019/12/a-long-slug", "archive.example"), R("/blog/19/12/short", "archive.example"), R("/blog/2019/12/", "archive.example"),
            R("/blog/2019/12/a/b", "archive.example"), R("/old-docs/", "archive.example"), R("/old-docs/", "archive.example"), R("/old-docs/a/b/?c=d", "archive.example"), R("/old-docs", "archive.example"), R("/", "archive.example"),
            R("/posts/", "archive.example"), R("/posts/hello/", "archive.example"), R("/a/b/c/", "archive.example"), R("/posts/hello", "archive.example"), R("/missing", "archive.example"), R("/api/v2/", "archive.example"), R("/v1/x/", "archive.example")],
     wrong=[dd('''
        server { listen 80; server_name archive.example; root /srv/archive/www;
          location ^~ /v1/ { rewrite ^/v1/(.*)$ /api/v2/$1 permanent; }
          location ~ "^/blog/\\d{4}/\\d{2}/([^/]+)$" { rewrite "^/blog/\\d{4}/\\d{2}/([^/]+)$" /posts/$1 permanent; }
          location ^~ /old-docs/ { rewrite ^/old-docs/(.*)$ https://docs.example.org/$1 redirect; }
          location ~ ^(.+)/$ { return 301 $1$is_args$args; } }
     ''')])

# ---------------------------------------------------------------------------------------------------- 10. maps: canary + mobile

spec(slug="canary-map-routing", d=4, path="conf.d/pulse.conf", kind="author",
     prompt=dd('''
        `conf.d/pulse.conf` already defines the upstreams `pulse_stable` and `pulse_canary`. Add the `map` and `server` blocks for `pulse.example` (port 80), using the request headers and cookies (`$http_...`, `$cookie_...`):

        - Requests are proxied to `pulse_canary` when the header `X-Canary` is exactly `1` or the cookie `canary` is exactly `on` (either one is enough); all other requests go to `pulse_stable`. The path is passed unchanged.
        - Except for static assets: paths under `/assets/` are served from `/srv/pulse/assets/` (alias; `/assets/a.js` is `/srv/pulse/assets/a.js`) whatever the canary state.
        - Only for the path `/` exactly: if the `User-Agent` contains `iPhone` or `Android` (case-insensitive) answer a 302 redirect to `https://m.pulse.example/`; the canary rules do not apply to that redirect.
        - `/healthz` is answered 200 `up` by nginx itself and is never proxied.
     '''),
     start="upstream pulse_stable {\n    server 10.4.0.1:8000;\n}\nupstream pulse_canary {\n    server 10.4.0.2:8000;\n}\n", files=["/srv/pulse/assets/a.js", "/srv/pulse/assets/css/b.css"],
     ref=dd('''
        upstream pulse_stable {
            server 10.4.0.1:8000;
        }
        upstream pulse_canary {
            server 10.4.0.2:8000;
        }
        map $http_x_canary $canary_hdr {
            default 0;
            "1" 1;
        }
        map $cookie_canary $canary_cookie {
            default 0;
            "on" 1;
        }
        map "$canary_hdr$canary_cookie" $pool {
            default pulse_stable;
            "~1" pulse_canary;
        }
        map $http_user_agent $is_mobile {
            default 0;
            "~*(iphone|android)" 1;
        }
        server {
            listen 80;
            server_name pulse.example;
            location = /healthz {
                return 200 up;
            }
            location ^~ /assets/ {
                alias /srv/pulse/assets/;
            }
            location = / {
                if ($is_mobile) {
                    return 302 https://m.pulse.example/;
                }
                proxy_pass http://$pool;
            }
            location / {
                proxy_pass http://$pool;
            }
        }
     '''),
     examples=[R("/orders/7?x=1", "pulse.example", proxy="pulse_stable/orders/7?x=1"), R("/orders/7", "pulse.example", headers={"X-Canary": "1"}, proxy="pulse_canary/orders/7"),
               R("/", "pulse.example", headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)"}, status=302, location="https://m.pulse.example/"), R("/healthz", "pulse.example", status=200, body="up"),
               R("/assets/a.js", "pulse.example", headers={"X-Canary": "1"}, status=200, file="/srv/pulse/assets/a.js")],
     cases=[R("/", "pulse.example"), R("/", "pulse.example", headers={"X-Canary": "1"}), R("/", "pulse.example", headers={"Cookie": "canary=on"}), R("/", "pulse.example", headers={"Cookie": "theme=dark; canary=on; x=1"}),
            R("/", "pulse.example", headers={"Cookie": "canary=off"}), R("/", "pulse.example", headers={"X-Canary": "0"}), R("/", "pulse.example", headers={"X-Canary": "yes"}), R("/", "pulse.example", headers={"X-Canary": "1", "Cookie": "canary=on"}),
            R("/", "pulse.example", headers={"User-Agent": "Mozilla/5.0 (Linux; ANDROID 14)"}), R("/", "pulse.example", headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}), R("/", "pulse.example", headers={"User-Agent": "Dalvik (android)", "X-Canary": "1"}),
            R("/home", "pulse.example", headers={"User-Agent": "iPhone"}), R("/home", "pulse.example", headers={"User-Agent": "iPhone", "X-Canary": "1"}), R("/api/items?q=1", "pulse.example", headers={"Cookie": "canary=on"}),
            R("/assets/css/b.css", "pulse.example", headers={"Cookie": "canary=on"}), R("/assets/missing.js", "pulse.example"), R("/healthz", "pulse.example", headers={"X-Canary": "1"}), R("/healthz/", "pulse.example")],
     wrong=[dd('''
        upstream pulse_stable { server 10.4.0.1:8000; }
        upstream pulse_canary { server 10.4.0.2:8000; }
        map $http_x_canary $pool { default pulse_stable; "1" pulse_canary; }
        map $http_user_agent $is_mobile { default 0; "~*(iphone|android)" 1; }
        server { listen 80; server_name pulse.example;
          location = /healthz { return 200 up; }
          location ^~ /assets/ { alias /srv/pulse/assets/; }
          location = / { if ($is_mobile) { return 302 https://m.pulse.example/; } proxy_pass http://$pool; }
          location / { proxy_pass http://$pool; } }
     ''')])

# ---------------------------------------------------------------------------------------------------- 11. internal rewrites (fix)

spec(slug="rewrite-last-break-fix", d=4, path="conf.d/photos.conf", kind="fix",
     prompt=dd('''
        `conf.d/photos.conf` is supposed to keep an old URL scheme working *without redirecting* (the browser keeps the old URL), but `/shots/...` URLs 404 or loop. Fix it. Required behaviour for `photos.example` (port 80); photo files live in `/srv/photos`:

        - `/media/photos/<name>` is the file `/srv/photos/<name>`.
        - `/shots/<n>.jpg` (n = digits) is served internally as `/media/photos/<n>.jpg`, i.e. the file `/srv/photos/<n>.jpg`, with status 200 when it exists; the response of `/shots/...` carries the header `X-Legacy: 1`.
        - `/photo?id=<n>` (query argument `id`, digits) is served as `/media/photos/<n>.jpg` too (file `/srv/photos/<n>.jpg`); without an `id` (or a non-numeric one) it answers 400.
        - everything else: 404.
     '''),
     start=dd('''
        server {
            listen 80;
            server_name photos.example;
            location /media/photos/ {
                alias /srv/photos;
            }
            location /shots/ {
                rewrite ^/shots/(\\d+)\\.jpg$ /media/photos/$1.jpg;
                add_header X-Legacy 1;
            }
            location = /photo {
                rewrite ^ /media/photos/$arg_id.jpg last;
            }
            location / {
                return 404;
            }
        }
     '''), files=["/srv/photos/7.jpg", "/srv/photos/42.jpg", "/srv/photos/cover.jpg"],
     ref=dd('''
        server {
            listen 80;
            server_name photos.example;
            location /media/photos/ {
                alias /srv/photos/;
            }
            location /shots/ {
                add_header X-Legacy 1;
                root /srv/photos;
                rewrite ^/shots/(\\d+)\\.jpg$ /$1.jpg break;
            }
            location = /photo {
                if ($arg_id !~ "^\\d+$") {
                    return 400;
                }
                rewrite ^ /media/photos/$arg_id.jpg last;
            }
            location / {
                return 404;
            }
        }
     '''),
     examples=[R("/media/photos/7.jpg", "photos.example", status=200, file="/srv/photos/7.jpg"), R("/shots/42.jpg", "photos.example", status=200, file="/srv/photos/42.jpg", headers={"X-Legacy": "1"}),
               R("/photo?id=7", "photos.example", status=200, file="/srv/photos/7.jpg"), R("/photo", "photos.example", status=400)],
     cases=[R("/media/photos/42.jpg", "photos.example"), R("/media/photos/cover.jpg", "photos.example"), R("/media/photos/none.jpg", "photos.example"), R("/shots/7.jpg", "photos.example"), R("/shots/999.jpg", "photos.example"),
            R("/shots/cover.jpg", "photos.example"), R("/shots/7.png", "photos.example"), R("/photo?id=42", "photos.example"), R("/photo?id=abc", "photos.example"), R("/photo?id=", "photos.example"), R("/photo?x=1&id=7", "photos.example"),
            R("/photo?id=555", "photos.example"), R("/", "photos.example"), R("/media/other/7.jpg", "photos.example")],
     wrong=[dd('''
        server { listen 80; server_name photos.example;
          location /media/photos/ { alias /srv/photos/; }
          location /shots/ { add_header X-Legacy 1; rewrite ^/shots/(\\d+)\\.jpg$ /media/photos/$1.jpg last; }
          location = /photo { rewrite ^ /media/photos/$arg_id.jpg last; }
          location / { return 404; } }
     ''')])


# ---------------------------------------------------------------------------------------------------- 12. status endpoints (easy)

spec(slug="status-endpoints", d=1, path="conf.d/status.conf", kind="author",
     prompt=dd('''
        Write `conf.d/status.conf`: a server listening on port 8081 (no `server_name` needed) that answers

        - exactly `/healthz` with status 200 and the body `ok`,
        - exactly `/version` with status 200 and the body `2.14.1`,
        - every other request with status 404 (no files are served).
     '''),
     start="# status endpoint\n", files=[],
     ref=dd('''
        server {
            listen 8081;
            location = /healthz {
                return 200 ok;
            }
            location = /version {
                return 200 2.14.1;
            }
            location / {
                return 404;
            }
        }
     '''),
     examples=[R("/healthz", "localhost", port=8081, status=200, body="ok"), R("/version", "localhost", port=8081, status=200, body="2.14.1"), R("/other", "localhost", port=8081, status=404)],
     cases=[R("/healthz", "10.0.0.8", port=8081), R("/healthz/", "localhost", port=8081), R("/version?full=1", "localhost", port=8081), R("/", "localhost", port=8081), R("/healthz/deep", "localhost", port=8081), R("/Healthz", "localhost", port=8081),
            R("/version", "status.internal", port=8081, method="POST")],
     wrong=["server { listen 8081; location /healthz { return 200 ok; } location /version { return 200 2.14.1; } location / { return 404; } }\n"])

# ---------------------------------------------------------------------------------------------------- 13. www canonical (easy)

spec(slug="www-canonical", d=1, path="conf.d/inkwell.conf", kind="author",
     prompt=dd('''
        Write `conf.d/inkwell.conf` for the site inkwell.example on plain HTTP (port 80): requests for `www.inkwell.example` are redirected permanently (301) to `http://inkwell.example` plus the original URI (path and query);
        `inkwell.example` serves the static files in `/srv/inkwell` (default index file); any other host name is answered 444 (so it is closed without a reply; status 444 is all the checker looks at).
     '''),
     start="# inkwell.example\n", files=["/srv/inkwell/index.html", "/srv/inkwell/essays/index.html", "/srv/inkwell/essays/one.html"],
     ref=dd('''
        server {
            listen 80 default_server;
            server_name _;
            return 444;
        }
        server {
            listen 80;
            server_name www.inkwell.example;
            return 301 http://inkwell.example$request_uri;
        }
        server {
            listen 80;
            server_name inkwell.example;
            root /srv/inkwell;
        }
     '''),
     examples=[R("/essays/one.html?ref=feed", "www.inkwell.example", status=301, location="http://inkwell.example/essays/one.html?ref=feed"), R("/", "inkwell.example", status=200, file="/srv/inkwell/index.html"),
               R("/", "evil.example", status=444)],
     cases=[R("/", "www.inkwell.example"), R("/a/b", "www.inkwell.example"), R("/essays/", "inkwell.example"), R("/essays/one.html", "inkwell.example"), R("/essays", "inkwell.example"), R("/nope", "inkwell.example"), R("/", "inkwell.example.evil.com"),
            R("/", "10.0.0.1"), R("/x?y=z", "WWW.INKWELL.EXAMPLE"), R("/", "sub.inkwell.example")],
     wrong=["server { listen 80; server_name www.inkwell.example; return 301 http://inkwell.example$request_uri; }\nserver { listen 80; server_name inkwell.example; root /srv/inkwell; }\n"])

# ---------------------------------------------------------------------------------------------------- 14. maintenance mode with if/set

spec(slug="maintenance-mode", d=4, path="conf.d/loom.conf", kind="author",
     prompt=dd('''
        `loom.example` (port 80) is going into maintenance. `conf.d/loom.conf` already defines the upstream `loom_api`. Write the server so that the site works as below, and while the maintenance is on (it is on in this configuration):

        - Site: `/api/` goes to `loom_api` (path unchanged), `/downloads/<name>` is the file `/srv/loom/dl/<name>`, everything else is a static file below `/srv/loom` (default index).
        - Maintenance: every request is answered 503 with the body `back soon`, **except**
          - `/healthz` (exactly), which answers 200 `ok` as usual,
          - requests from clients in `10.0.0.0/8` (a regular expression on `$remote_addr` is fine), who see the site normally,
          - requests that carry the cookie `bypass=letmein`, who see the site normally.
        - The condition must be decided before any location is chosen (use `set` and `if` at server level), so that no path can slip through.

        Note that a server-level `return` ends the request before location matching.
     '''),
     start="upstream loom_api {\n    server 10.5.0.1:7100;\n}\n", files=["/srv/loom/index.html", "/srv/loom/blog/index.html", "/srv/loom/css/site.css", "/srv/loom/dl/guide.pdf"],
     ref=dd('''
        upstream loom_api {
            server 10.5.0.1:7100;
        }
        server {
            listen 80;
            server_name loom.example;
            root /srv/loom;
            set $maint 1;
            if ($uri = /healthz) {
                set $maint 0;
            }
            if ($remote_addr ~ "^10\\.") {
                set $maint 0;
            }
            if ($cookie_bypass = letmein) {
                set $maint 0;
            }
            if ($maint) {
                return 503 "back soon";
            }
            location = /healthz {
                return 200 ok;
            }
            location /api/ {
                proxy_pass http://loom_api;
            }
            location /downloads/ {
                alias /srv/loom/dl/;
            }
        }
     '''),
     examples=[R("/", "loom.example", ip="203.0.113.9", status=503, body="back soon"), R("/healthz", "loom.example", ip="203.0.113.9", status=200, body="ok"),
               R("/", "loom.example", ip="10.1.2.3", status=200, file="/srv/loom/index.html"), R("/blog/", "loom.example", headers={"Cookie": "bypass=letmein"}, status=200, file="/srv/loom/blog/index.html")],
     cases=[R("/", "loom.example"), R("/css/site.css", "loom.example"), R("/missing", "loom.example"), R("/healthz", "loom.example"), R("/healthz/", "loom.example"), R("/healthz?x=1", "loom.example"), R("/css/site.css", "loom.example", ip="10.200.0.1"),
            R("/css/site.css", "loom.example", ip="110.0.0.1"), R("/", "loom.example", ip="100.64.0.1"), R("/", "loom.example", ip="10.0.0.1", method="POST"), R("/blog/", "loom.example", headers={"Cookie": "a=b; bypass=letmein"}),
            R("/blog/", "loom.example", headers={"Cookie": "bypass=nope"}), R("/css/site.css", "loom.example", headers={"Cookie": "bypass=letmein", "X": "y"}), R("/missing", "loom.example", ip="10.3.3.3"), R("/api/x", "loom.example", ip="8.8.8.8"),
            R("/api/x?y=1", "loom.example", ip="10.9.9.9"), R("/api/x", "loom.example", headers={"Cookie": "bypass=letmein"}), R("/downloads/guide.pdf", "loom.example"), R("/downloads/guide.pdf", "loom.example", ip="10.0.0.2"),
            R("/downloads/guide.pdf", "loom.example", headers={"Cookie": "bypass=letmein"}), R("/downloads/none.pdf", "loom.example", ip="10.0.0.2")],
     wrong=[dd('''
        upstream loom_api { server 10.5.0.1:7100; }
        server { listen 80; server_name loom.example; root /srv/loom;
          location = /healthz { return 200 ok; }
          location /api/ { proxy_pass http://loom_api; }
          location /downloads/ { alias /srv/loom/dl/; }
          location / { set $maint 1; if ($remote_addr ~ "^10\\.") { set $maint 0; } if ($cookie_bypass = letmein) { set $maint 0; } if ($maint) { return 503 "back soon"; } } }
     ''')])

# ---------------------------------------------------------------------------------------------------- 15. the full site

spec(slug="full-site-policy", d=5, path="conf.d/atlas.conf", kind="author",
     prompt=dd('''
        `conf.d/atlas.conf` contains the upstreams `atlas_api` and `atlas_legacy` and nothing else. Write the servers for `atlas.example` and `www.atlas.example` so that all of the following hold (this is the complete policy; the checker tries many requests):

        1. **HTTP (port 80)**, both hosts: paths under `/.well-known/acme-challenge/` are static files from the web root `/var/lib/acme/atlas`; everything else is redirected with 301 to `https://atlas.example` + the original URI.
        2. **HTTPS (port 443, ssl), `www.atlas.example`**: 301 to `https://atlas.example` + the original URI.
        3. **HTTPS, `atlas.example`**: the application is in `/srv/atlas/app`. Every response from this server, whatever the status (redirects, 403, 404, proxied, static), carries `Strict-Transport-Security: max-age=31536000`.
        4. Exactly `/healthz` answers 200 `ok`.
        5. Paths under `/api/v1/` go to `atlas_legacy` with the path unchanged. Every other path under `/api/` goes to `atlas_api` with the `/api` prefix removed (`/api/users/7?x=1` -> `/users/7?x=1`).
        6. `/files/<name>` is the file `/srv/atlas/files/<name>`. Any path below `/files/` with a segment that starts with a dot is answered 403. Only GET and HEAD are allowed on `/files/` (403 otherwise).
        7. `/old/<rest>` is redirected with 301 to `/new/<rest>`.
        8. `/admin/` and everything below it is only for clients in `10.0.0.0/8` (403 for the others); admins get the application page like everyone else.
        9. Under `/static/` a missing file is 404. Every other path is the file below `/srv/atlas/app` if it exists, a directory's index file, or else the application page `/index.html` (client-side routes).
     '''),
     start="upstream atlas_api {\n    server 10.7.0.1:9000;\n}\nupstream atlas_legacy {\n    server 10.7.0.2:9000;\n}\n",
     files=["/var/lib/acme/atlas/.well-known/acme-challenge/t1", "/srv/atlas/app/index.html", "/srv/atlas/app/static/app.js", "/srv/atlas/app/static/css/a.css", "/srv/atlas/app/favicon.ico", "/srv/atlas/app/docs/index.html",
            "/srv/atlas/files/report.pdf", "/srv/atlas/files/2024/q1.csv", "/srv/atlas/files/.hidden", "/srv/atlas/files/2024/.draft"],
     ref=dd('''
        upstream atlas_api {
            server 10.7.0.1:9000;
        }
        upstream atlas_legacy {
            server 10.7.0.2:9000;
        }
        server {
            listen 80;
            server_name atlas.example www.atlas.example;
            location ^~ /.well-known/acme-challenge/ {
                root /var/lib/acme/atlas;
            }
            location / {
                return 301 https://atlas.example$request_uri;
            }
        }
        server {
            listen 443 ssl;
            server_name www.atlas.example;
            return 301 https://atlas.example$request_uri;
        }
        server {
            listen 443 ssl;
            server_name atlas.example;
            root /srv/atlas/app;
            add_header Strict-Transport-Security "max-age=31536000" always;
            location = /healthz {
                return 200 ok;
            }
            location ^~ /api/v1/ {
                proxy_pass http://atlas_legacy;
            }
            location ^~ /api/ {
                proxy_pass http://atlas_api/;
            }
            location ~ "^/files/(.*/)?\\." {
                return 403;
            }
            location /files/ {
                alias /srv/atlas/files/;
                limit_except GET {
                    deny all;
                }
            }
            location ^~ /old/ {
                rewrite ^/old/(.*)$ /new/$1 permanent;
            }
            location /admin/ {
                allow 10.0.0.0/8;
                deny all;
                try_files $uri $uri/ /index.html;
            }
            location ^~ /static/ {
                try_files $uri =404;
            }
            location / {
                try_files $uri $uri/ /index.html;
            }
        }
     '''),
     examples=[R("/x?y=1", "www.atlas.example", status=301, location="https://atlas.example/x?y=1"), R("/.well-known/acme-challenge/t1", "atlas.example", status=200, file="/var/lib/acme/atlas/.well-known/acme-challenge/t1"),
               R("/api/users/7?x=1", "atlas.example", "https", proxy="atlas_api/users/7?x=1", headers={"Strict-Transport-Security": "max-age=31536000"}), R("/api/v1/users", "atlas.example", "https", proxy="atlas_legacy/api/v1/users"),
               R("/files/.hidden", "atlas.example", "https", status=403), R("/boats/3", "atlas.example", "https", status=200, file="/srv/atlas/app/index.html")],
     cases=[R("/", "atlas.example"), R("/.well-known/acme-challenge/none", "www.atlas.example"), R("/.well-known/acme-challenge/t1", "www.atlas.example"), R("/a/b?c=d", "atlas.example"), R("/", "www.atlas.example", "https"), R("/x/y?z=1", "www.atlas.example", "https"),
            R("/", "atlas.example", "https"), R("/healthz", "atlas.example", "https"), R("/healthz/", "atlas.example", "https"), R("/api/", "atlas.example", "https"), R("/api/v1/", "atlas.example", "https"), R("/api/v1", "atlas.example", "https"),
            R("/api/v2/items?limit=5", "atlas.example", "https"), R("/api/v10/x", "atlas.example", "https"), R("/files/report.pdf", "atlas.example", "https"), R("/files/2024/q1.csv", "atlas.example", "https"), R("/files/missing.txt", "atlas.example", "https"),
            R("/files/2024/.draft", "atlas.example", "https"), R("/files/a/.b/c", "atlas.example", "https"), R("/files/x.tar.gz", "atlas.example", "https"), R("/files/report.pdf", "atlas.example", "https", method="POST"), R("/files/report.pdf", "atlas.example", "https", method="HEAD"),
            R("/old/a/b?c=1", "atlas.example", "https"), R("/old/", "atlas.example", "https"), R("/admin/", "atlas.example", "https", ip="10.1.1.1"), R("/admin/users", "atlas.example", "https", ip="10.1.1.1"), R("/admin/", "atlas.example", "https", ip="198.51.100.4"),
            R("/admin/users", "atlas.example", "https", ip="203.0.113.77"), R("/static/app.js", "atlas.example", "https"), R("/static/css/a.css", "atlas.example", "https"), R("/static/missing.js", "atlas.example", "https"), R("/favicon.ico", "atlas.example", "https"),
            R("/docs/", "atlas.example", "https"), R("/docs", "atlas.example", "https"), R("/settings/profile", "atlas.example", "https"), R("/administrator", "atlas.example", "https", ip="203.0.113.77")],
     wrong=[dd('''
        upstream atlas_api { server 10.7.0.1:9000; }
        upstream atlas_legacy { server 10.7.0.2:9000; }
        server { listen 80; server_name atlas.example www.atlas.example;
          location ^~ /.well-known/acme-challenge/ { root /var/lib/acme/atlas; }
          location / { return 301 https://atlas.example$request_uri; } }
        server { listen 443 ssl; server_name www.atlas.example; return 301 https://atlas.example$request_uri; }
        server { listen 443 ssl; server_name atlas.example; root /srv/atlas/app;
          add_header Strict-Transport-Security "max-age=31536000";
          location = /healthz { return 200 ok; }
          location ^~ /api/v1/ { proxy_pass http://atlas_legacy; }
          location ^~ /api/ { proxy_pass http://atlas_api/; }
          location ~ "^/files/(.*/)?\\." { return 403; }
          location /files/ { alias /srv/atlas/files/; limit_except GET { deny all; } }
          location ^~ /old/ { rewrite ^/old/(.*)$ /new/$1 permanent; }
          location /admin/ { allow 10.0.0.0/8; deny all; try_files $uri $uri/ /index.html; }
          location ^~ /static/ { try_files $uri =404; }
          location / { try_files $uri $uri/ /index.html; } }
     ''')])


def _tasks(rng, n):
    return [make_task(s) for s in SPECS[:n]]


@family("devops-nginx-routing", category="devops", lang="text", kind="fix", n=len(SPECS),
        summary="write or repair nginx configurations judged by a documented request simulator: location precedence, proxy_pass URIs, alias vs root, redirects, access rules")
def nginx_routing(rng, n):
    return _tasks(rng, n)
