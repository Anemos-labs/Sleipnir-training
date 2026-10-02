"""A small simulator for a subset of nginx configuration (shipped to the agent as `tools/ngsim.py`, and used by the hidden checker)."""

NGSIM = r'''#!/usr/bin/env python3
"""ngsim.py - simulate how nginx would answer a request, for a documented subset of the configuration language.

    python3 tools/ngsim.py CONF REQUESTS.json     # prints one line per request (and the result of each expectation)

REQUESTS.json is a list of {"req": {...}, "expect": {...}} objects (expect is optional):
    req:    {"method": "GET", "scheme": "http"|"https", "host": "example.org", "uri": "/a/b?x=1", "ip": "203.0.113.9", "port": 80}
    expect: any subset of {"status", "location", "proxy", "file", "headers", "body"}
A file system for static content is given as {"files": ["/srv/www/index.html", ...]} next to the list in the form
    {"files": [...], "cases": [...]}
"""
import ipaddress
import json
import re
import sys

KNOWN = {"listen", "server_name", "return", "rewrite", "proxy_pass", "root", "alias", "try_files", "index", "add_header", "deny", "allow", "set", "if", "location", "server", "upstream", "http",
         "proxy_set_header", "error_page", "access_log", "error_log", "ssl_certificate", "ssl_certificate_key", "expires", "client_max_body_size", "gzip", "charset", "keepalive_timeout", "include",
         "map", "limit_except"}


class ConfError(Exception):
    pass


def tokenize(text):
    toks, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == "#":
            while i < n and text[i] != "\n":
                i += 1
        elif c in "{};":
            toks.append((c, False))
            i += 1
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                if text[j] == "\\":
                    j += 1
                j += 1
            if j >= n:
                raise ConfError("unterminated quoted string")
            toks.append((text[i + 1:j].replace("\\" + c, c), True))
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "{};":
                j += 1
            toks.append((text[i:j], False))
            i = j
    return toks


def parse(toks):
    pos = 0

    def block(top, raw=False):
        nonlocal pos
        nodes = []
        while True:
            if pos >= len(toks):
                if top:
                    return nodes
                raise ConfError("unexpected end of file, expecting \"}\"")
            t, q = toks[pos]
            if t == "}" and not q:
                if top:
                    raise ConfError("unexpected \"}\"")
                pos += 1
                return nodes
            if t in ("{", ";") and not q:
                raise ConfError(f"unexpected \"{t}\"")
            name = t
            pos += 1
            args = []
            while pos < len(toks) and (toks[pos][0] not in "{};" or toks[pos][1]):
                args.append(toks[pos][0])
                pos += 1
            if pos >= len(toks):
                raise ConfError(f"directive \"{name}\" is not terminated by \";\"")
            end = toks[pos][0]
            pos += 1
            if name not in KNOWN and not raw:
                raise ConfError(f"unknown directive \"{name}\"")
            if end == ";":
                nodes.append((name, args, None))
            elif end == "{":
                nodes.append((name, args, block(False, raw=(name == "map"))))
            else:
                raise ConfError(f"unexpected \"}}\" after directive \"{name}\"")
    return block(True)


class Loc:
    def __init__(self, args, body):
        mod = ""
        if len(args) == 2 and args[0] in ("=", "^~", "~", "~*"):
            mod, pat = args
        elif len(args) == 1:
            pat = args[0]
        else:
            raise ConfError("invalid location parameters: " + " ".join(args))
        self.mod, self.pat, self.body = mod, pat, body
        self.rx = re.compile(pat, re.I if mod == "~*" else 0) if mod in ("~", "~*") else None


class Server:
    def __init__(self, body):
        self.body = body
        self.listens, self.names, self.locs = [], [], []
        for name, args, sub in body:
            if name == "listen":
                port, ssl, default = 80, False, False
                for a in args:
                    m = re.fullmatch(r"(?:\[?[\w.:]*\]?:)?(\d+)", a)
                    if m:
                        port = int(m.group(1))
                    elif a == "ssl":
                        ssl = True
                    elif a == "default_server":
                        default = True
                self.listens.append((port, ssl, default))
            elif name == "server_name":
                self.names += [a.lower() for a in args]
            elif name == "location":
                self.locs.append(Loc(args, sub))
        if not self.listens:
            self.listens.append((80, False, False))


def load(path):
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as e:
        raise ConfError(f"cannot read {path}: {e.strerror}")
    nodes = parse(tokenize(text))
    while len(nodes) == 1 and nodes[0][0] == "http" and nodes[0][2] is not None:
        nodes = nodes[0][2]
    servers, upstreams = [], {"__maps__": {}}
    for name, args, sub in nodes:
        if name == "server" and sub is not None:
            servers.append(Server(sub))
        elif name == "upstream" and sub is not None:
            upstreams[args[0]] = [a[1] for a in sub if a[0] == "server"]
        elif name == "map" and sub is not None and len(args) == 2:
            upstreams["__maps__"][args[1].lstrip("$")] = (args[0], sub)
        else:
            raise ConfError(f"\"{name}\" directive is not allowed here")
    return servers, upstreams


def pick_server(servers, port, host):
    cands = [s for s in servers if any(l[0] == port for l in s.listens)]
    if not cands:
        return None
    host = host.lower().split(":")[0]
    for s in cands:
        if host in s.names:
            return s
    best, blen = None, -1
    for s in cands:
        for n in s.names:
            pat = None
            if n.startswith("*."):
                pat = n[1:]
            elif n.startswith("."):
                if host == n[1:]:
                    return s
                pat = n
            if pat and host.endswith(pat) and len(pat) > blen:
                best, blen = s, len(pat)
    if best:
        return best
    for s in cands:
        for n in s.names:
            if n.startswith("~") and re.search(n[1:], host):
                return s
    for s in cands:
        if any(l[0] == port and l[2] for l in s.listens):
            return s
    return cands[0]


def pick_location(server, path):
    for l in server.locs:
        if l.mod == "=" and l.pat == path:
            return l, None
    best = None
    for l in server.locs:
        if l.mod in ("", "^~") and path.startswith(l.pat) and (best is None or len(l.pat) > len(best.pat)):
            best = l
    if best is not None and best.mod == "^~":
        return best, None
    for l in server.locs:
        if l.rx is not None:
            m = l.rx.search(path)
            if m:
                return l, m
    return best, None


class Ctx:
    maps = {}

    def __init__(self, req):
        uri = req["uri"]
        self.path, _, self.args = uri.partition("?")
        self.orig = uri
        self.req = req
        self.caps = {}
        self.vars = {}

    def expand(self, s):
        def sub(m):
            name = m.group(1) or m.group(2)
            r = self.req
            if name.isdigit():
                return self.caps.get(int(name), "")
            table = {"scheme": r["scheme"], "host": r["host"].split(":")[0], "request_uri": self.orig, "uri": self.path, "args": self.args, "query_string": self.args,
                     "is_args": "?" if self.args else "", "request_method": r.get("method", "GET"), "remote_addr": r.get("ip", "203.0.113.9"), "server_name": self.server_name}
            if name in table:
                return table[name]
            if name in self.vars:
                return self.vars[name]
            hd = {k.lower(): v for k, v in (r.get("headers") or {}).items()}
            if name.startswith("http_"):
                return hd.get(name[5:].replace("_", "-"), "")
            if name.startswith("arg_"):
                for part in self.args.split("&"):
                    k, _, v = part.partition("=")
                    if k == name[4:]:
                        return v
                return ""
            if name.startswith("cookie_"):
                for part in hd.get("cookie", "").split(";"):
                    k, _, v = part.strip().partition("=")
                    if k == name[7:]:
                        return v
                return ""
            if name in self.maps:
                src, entries = self.maps[name]
                val = self.expand(src)
                default = ""
                for n, a, _ in entries:
                    if n == "default":
                        default = a[0]
                    elif not n.startswith("~") and n == val:
                        return a[0]
                for n, a, _ in entries:
                    if n.startswith("~*") and re.search(n[2:], val, re.I):
                        return a[0]
                    if n.startswith("~") and not n.startswith("~*") and re.search(n[1:], val):
                        return a[0]
                return default
            return ""
        return re.sub(r"\$(?:\{(\w+)\}|(\w+))", sub, s)


def cond_true(ctx, args):
    args = list(args)
    if args and args[0].startswith("("):
        args[0] = args[0][1:]
    if args and args[-1] == ")":
        args.pop()
    elif args and args[-1].endswith(")") and args[-1].count(")") > args[-1].count("("):
        args[-1] = args[-1][:-1]
    if len(args) == 3 and args[1] in ("=", "!="):
        a, b = ctx.expand(args[0].strip("()")), ctx.expand(args[2].strip("()"))
        return (a == b) if args[1] == "=" else (a != b)
    if len(args) == 3 and args[1] in ("~", "~*", "!~", "!~*"):
        a = ctx.expand(args[0].strip("()"))
        m = re.search(args[2].strip("()"), a, re.I if args[1].endswith("*") else 0)
        return bool(m) != args[1].startswith("!")
    if len(args) == 1:
        v = ctx.expand(args[0].strip("()"))
        return v not in ("", "0")
    raise ConfError("unsupported if condition: " + " ".join(args))


def redirect_result(code, target):
    return {"status": code, "location": target}


def rewrite_phase(nodes, ctx, in_location):
    """Run return/rewrite/set/if in order. Returns ("final", result) | ("restart", None) | ("go", None)."""
    for name, args, sub in nodes:
        if name == "set":
            ctx.vars[args[0].lstrip("$")] = ctx.expand(args[1])
        elif name == "return":
            if len(args) == 1 and args[0].isdigit():
                return "final", {"status": int(args[0])}
            code = int(args[0]) if args[0].isdigit() else 302
            rest = ctx.expand(args[1] if args[0].isdigit() else args[0])
            if code in (301, 302, 303, 307, 308):
                return "final", redirect_result(code, rest)
            return "final", {"status": code, "body": rest}
        elif name == "rewrite":
            rx, repl = args[0], args[1]
            flag = args[2] if len(args) > 2 else ""
            m = re.search(rx, ctx.path)
            if not m:
                continue
            ctx.caps = {i + 1: (g or "") for i, g in enumerate(m.groups())}
            new = ctx.expand(repl)
            has_q = "?" in repl
            if flag in ("redirect", "permanent") or re.match(r"https?://", new) or repl.startswith("$scheme"):
                code = 301 if flag == "permanent" else 302
                if new.endswith("?"):
                    new = new[:-1]
                elif not has_q and ctx.args:
                    new += "?" + ctx.args
                return "final", redirect_result(code, new)
            path, _, q = new.partition("?")
            ctx.path = path
            if has_q:
                ctx.args = q
            if flag == "last":
                return "restart", None
            if flag == "break":
                return "break", None
        elif name == "if" and sub is not None:
            if cond_true(ctx, args):
                kind, res = rewrite_phase(sub, ctx, in_location)
                if kind != "go":
                    return kind, res
    return "go", None


def access_ok(nodes, ip):
    for name, args, _ in nodes:
        if name in ("allow", "deny"):
            a = args[0]
            hit = a == "all" or (ipaddress.ip_address(ip) in ipaddress.ip_network(a, strict=False))
            if hit:
                return name == "allow"
    return True


def direct(nodes, name):
    return [(a, s) for n, a, s in nodes if n == name]


def inherit(server, loc, name):
    r = direct(loc.body, name) if loc else []
    return r if r else direct(server.body, name)


def exists(files, p):
    return p in files


def is_dir(files, p):
    p = p.rstrip("/") + "/"
    return any(f.startswith(p) for f in files)


def handle(server, ctx, files, upstreams, count=0):
    loc, m = pick_location(server, ctx.path)
    if loc is None:
        loc = Loc(["/"], [])
    ctx.caps = {i + 1: (g or "") for i, g in enumerate(m.groups())} if m else {}
    kind, res = rewrite_phase(loc.body, ctx, True)
    if kind == "final":
        return res, loc
    if kind == "restart":
        if count >= 10:
            return {"status": 500, "note": "rewrite or internal redirection cycle"}, loc
        return handle(server, ctx, files, upstreams, count + 1)
    acc_nodes = [n for n in loc.body if n[0] in ("allow", "deny")] or [n for n in server.body if n[0] in ("allow", "deny")]
    if not access_ok(acc_nodes, ctx.req.get("ip", "203.0.113.9")):
        return {"status": 403}, loc
    for _, la, lsub in [n for n in loc.body if n[0] == "limit_except"]:
        allowed = {x.upper() for x in la}
        if "GET" in allowed:
            allowed.add("HEAD")
        if ctx.req.get("method", "GET").upper() not in allowed and not access_ok([n for n in (lsub or []) if n[0] in ("allow", "deny")], ctx.req.get("ip", "203.0.113.9")):
            return {"status": 403}, loc
    pp = direct(loc.body, "proxy_pass")
    if pp:
        target = ctx.expand(pp[0][0][0])
        mm = re.fullmatch(r"https?://([^/]+)(/.*)?", target)
        if not mm:
            raise ConfError("proxy_pass needs http://host[/uri]")
        host, uri_part = mm.group(1), mm.group(2)
        if uri_part is not None and loc.mod in ("", "^~", "="):
            path = uri_part + ctx.path[len(loc.pat):]
        else:
            path = ctx.path
        return {"status": 200, "proxy": host + path + (("?" + ctx.args) if ctx.args else "")}, loc
    root = (inherit(server, loc, "root") or [(["html"], None)])[0][0][0]
    alias = direct(loc.body, "alias")
    index = (inherit(server, loc, "index") or [(["index.html"], None)])[0][0]

    def fpath(uri):
        if alias:
            base = ctx.expand(alias[0][0][0])
            return base + uri[len(loc.pat):] if loc.mod in ("", "^~", "=") else base
        return root.rstrip("/") + uri

    tf = direct(loc.body, "try_files")
    if tf:
        args = tf[0][0]
        for a in args[:-1]:
            a = ctx.expand(a)
            if a.endswith("/"):
                base = fpath(a)
                if is_dir(files, base):
                    for ix in index:
                        if exists(files, base + ix):
                            return {"status": 200, "file": base + ix}, loc
            else:
                p = fpath(a)
                if exists(files, p):
                    return {"status": 200, "file": p}, loc
        last = ctx.expand(args[-1])
        if last.startswith("="):
            return {"status": int(last[1:])}, loc
        if count >= 10:
            return {"status": 500, "note": "rewrite or internal redirection cycle"}, loc
        ctx.path = last.partition("?")[0]
        return handle(server, ctx, files, upstreams, count + 1)
    p = fpath(ctx.path)
    if exists(files, p):
        return {"status": 200, "file": p}, loc
    if is_dir(files, p):
        if not ctx.path.endswith("/"):
            return {"status": 301, "location": ctx.path + "/" + (("?" + ctx.args) if ctx.args else "")}, loc
        for ix in index:
            if exists(files, p.rstrip("/") + "/" + ix):
                return {"status": 200, "file": p.rstrip("/") + "/" + ix}, loc
        return {"status": 403}, loc
    return {"status": 404, "file": p}, loc


def simulate(servers, upstreams, files, req):
    req = dict(req)
    req.setdefault("scheme", "http")
    req.setdefault("port", 443 if req["scheme"] == "https" else 80)
    req.setdefault("method", "GET")
    srv = pick_server(servers, req["port"], req["host"])
    if srv is None:
        return {"status": 0, "note": "connection refused"}
    ctx = Ctx(req)
    ctx.maps = upstreams.get("__maps__", {})
    ctx.server_name = srv.names[0] if srv.names else ""
    kind, res = rewrite_phase([n for n in srv.body if n[0] in ("set", "return", "rewrite", "if")], ctx, False)
    loc = None
    if kind == "final":
        pass
    else:
        res, loc = handle(srv, ctx, files, upstreams)
    st = res["status"]
    heads = {}
    adds = []
    if loc is not None:
        adds = direct(loc.body, "add_header") or direct(srv.body, "add_header")
    else:
        adds = direct(srv.body, "add_header")
    for a, _ in adds:
        always = len(a) > 2 and a[2] == "always"
        if always or st in (200, 201, 204, 206, 301, 302, 303, 304, 307, 308):
            heads[a[0].lower()] = a[1]
    if heads:
        res = dict(res, headers=heads)
    return res


def matches(res, expect):
    bad = []
    for k, v in expect.items():
        if k == "headers":
            got = {a.lower(): b for a, b in (res.get("headers") or {}).items()}
            for hk, hv in v.items():
                if got.get(hk.lower()) != hv:
                    bad.append(f"header {hk}: want {hv!r}, got {got.get(hk.lower())!r}")
        elif res.get(k) != v:
            bad.append(f"{k}: want {v!r}, got {res.get(k)!r}")
    return bad


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    try:
        servers, ups = load(argv[1])
    except ConfError as e:
        print(f"nginx: configuration error: {e}")
        return 1
    data = json.load(open(argv[2], encoding="utf-8"))
    files = set(data.get("files", [])) if isinstance(data, dict) else set()
    cases = data["cases"] if isinstance(data, dict) else data
    fails = 0
    for c in cases:
        r = c["req"]
        res = simulate(servers, ups, files, r)
        line = f"{r.get('method', 'GET')} {r.get('scheme', 'http')}://{r['host']}{r['uri']} -> " + json.dumps(res, sort_keys=True)
        if "expect" in c:
            bad = matches(res, c["expect"])
            line += "   OK" if not bad else "   FAIL: " + "; ".join(bad)
            fails += bool(bad)
        print(line)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
'''
