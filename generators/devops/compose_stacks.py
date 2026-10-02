"""DevOps tasks: docker-compose stacks repaired against a mechanical policy (pinned images, health-gated startup, port exposure, volumes, secrets, networks)."""
import json

from fx import dd, family
from generators.devops import _dokit as K
from generators.devops import _yamlw as Y

CHECK_COMPOSE = r'''
from dolib import *

R = json.load(open("tests/rules.json", encoding="utf-8"))
PATH = R["path"]
doc = yaml_one(PATH)
rep = Report()
svcs = doc.get("services")
if not isinstance(svcs, dict) or not svcs:
    die(f"{PATH} has no `services` mapping")
svcs = {k: (v if isinstance(v, dict) else {}) for k, v in svcs.items()}

# R1 the work is kept
rep.check("version" not in doc, "the top-level `version:` key is obsolete and must be removed")
for name, keep in R["keep"].items():
    s = svcs.get(name)
    if not rep.check(s is not None, f"service {name!r} is missing"):
        continue
    for k, v in keep.items():
        rep.check(s.get(k) == v, f"service {name!r}: `{k}` must stay {v!r} (got {s.get(k)!r})")
rep.check(set(svcs) == set(R["keep"]), f"the stack must have exactly the services {sorted(R['keep'])}")

# R2 pinned images
for name, s in svcs.items():
    img = s.get("image")
    if img is None:
        rep.check("build" in s, f"service {name!r} has neither `image` nor `build`")
        continue
    img = str(img)
    last = img.rsplit("/", 1)[-1]
    tag = last.split(":", 1)[1] if ":" in last else ("@" if "@" in img else "")
    rep.check(tag not in ("", "latest"), f"service {name!r}: image {img!r} must carry an explicit version tag (not `latest`, not missing)")

# R3 depends_on
deps = {}
for name, s in svcs.items():
    d = s.get("depends_on")
    if isinstance(d, list):
        deps[name] = {str(x): None for x in d}
    elif isinstance(d, dict):
        deps[name] = {str(k): (v or {}).get("condition") if isinstance(v, dict) else None for k, v in d.items()}
    else:
        deps[name] = {}
    for t in deps[name]:
        rep.check(t in svcs, f"service {name!r} depends_on {t!r}, which is not a service")
color = {}


def cyc(x):
    color[x] = 1
    for t in deps.get(x, {}):
        if color.get(t) == 1 or (t in deps and t not in color and cyc(t)):
            return True
    color[x] = 2
    return False


rep.check(not any(cyc(x) for x in list(deps) if x not in color), "depends_on contains a cycle")
for name, want in R["deps"].items():
    for t, cond in want.items():
        got = deps.get(name, {})
        if rep.check(t in got, f"service {name!r} must depend_on {t!r}"):
            rep.check(got[t] == cond, f"service {name!r}: depends_on {t!r} needs `condition: {cond}` (long form), got {got[t]!r}")

# R4 healthchecks
for name in R["health"]:
    h = (svcs.get(name) or {}).get("healthcheck")
    if not rep.check(isinstance(h, dict), f"service {name!r} needs a healthcheck"):
        continue
    t = h.get("test")
    rep.check(isinstance(t, list) and t and t[0] in ("CMD", "CMD-SHELL") and len(t) > 1, f"service {name!r}: healthcheck.test must be a list starting with CMD or CMD-SHELL")
    rep.check(isinstance(h.get("retries"), int) and h["retries"] >= 3, f"service {name!r}: healthcheck.retries must be an integer >= 3")
    rep.check(isinstance(h.get("interval"), str) and re.fullmatch(r"\d+[sm]", h["interval"]), f"service {name!r}: healthcheck.interval must be a duration string like 10s")

# R5 ports
seen = {}
for name, s in svcs.items():
    ports = as_list(s.get("ports"))
    if name in R["no_ports"]:
        rep.check(not ports, f"service {name!r} must not publish any port")
    for p in ports:
        if not rep.check(isinstance(p, str), f"service {name!r}: port {p!r} must be a quoted string (an unquoted HOST:CONTAINER pair can be read as a base-60 number)"):
            continue
        m = re.fullmatch(r"(?:(\d+\.\d+\.\d+\.\d+):)?(\d+):(\d+)(?:/(tcp|udp))?", p)
        if not rep.check(m, f"service {name!r}: port {p!r} is not [IP:]HOST:CONTAINER[/proto]"):
            continue
        ip, host, cont, proto = m.groups()
        key = (host, proto or "tcp", ip or "*")
        rep.check(key not in seen, f"host port {host} is published by both {seen.get(key)!r} and {name!r}")
        seen[key] = name
        if name not in R["public"]:
            rep.check(ip == "127.0.0.1", f"service {name!r}: port {p!r} is exposed on every interface; only {sorted(R['public'])} may do that, others must bind 127.0.0.1")
for name in R["public"]:
    rep.check(bool(as_list((svcs.get(name) or {}).get("ports"))), f"service {name!r} must publish its port")
by_host = {}
for (host, proto, ip), name in seen.items():
    by_host.setdefault((host, proto), []).append((ip, name))
for k, v in by_host.items():
    if len(v) > 1 and any(i == "*" for i, _ in v):
        rep.check(False, f"host port {k[0]}/{k[1]} is published twice ({', '.join(n for _, n in v)})")

# R6 volumes
declared = doc.get("volumes") if isinstance(doc.get("volumes"), dict) else {}
for name, s in svcs.items():
    for v in as_list(s.get("volumes")):
        src = v.split(":")[0] if isinstance(v, str) else (v.get("source") if isinstance(v, dict) else None)
        if not src:
            continue
        rep.check("docker.sock" not in str(src), f"service {name!r} mounts the Docker socket")
        if not src.startswith(("/", ".", "~")):
            rep.check(src in declared, f"service {name!r} uses the named volume {src!r}, which is not declared under top-level `volumes:`")
for name, path in R["data"].items():
    vs = [v for v in as_list((svcs.get(name) or {}).get("volumes")) if isinstance(v, str)]
    ok = any(v.split(":")[1:2] == [path] and not v.split(":")[0].startswith(("/", ".", "~")) for v in vs)
    rep.check(ok, f"service {name!r}: {path} must be backed by a named volume")

# R7 secrets
for name, s in svcs.items():
    env = s.get("environment")
    pairs = list(env.items()) if isinstance(env, dict) else [tuple(str(x).split("=", 1)) + ("",) * (2 - len(str(x).split("=", 1))) for x in as_list(env)]
    for k, v in pairs:
        if re.search(r"PASSWORD|SECRET|TOKEN|KEY", str(k)) and not str(k).endswith("_FILE"):
            rep.check(re.fullmatch(r"\$\{[A-Z_][A-Z0-9_]*(:?[-?][^}]*)?\}", str(v)), f"service {name!r}: {k} must be an interpolation like ${{VAR}}, not a literal value")

# R8 restart
for name, s in svcs.items():
    want = "no" if name in R["oneshot"] else "unless-stopped"
    rep.check(s.get("restart") == want, f"service {name!r}: `restart` must be the string {want!r} (got {s.get('restart')!r})")

# R9 networks
nets = doc.get("networks") if isinstance(doc.get("networks"), dict) else {}
for name, want in R["networks"].items():
    s = svcs.get(name) or {}
    n = s.get("networks")
    got = sorted(n.keys() if isinstance(n, dict) else as_list(n))
    rep.check(got == sorted(want), f"service {name!r}: networks must be exactly {sorted(want)} (got {got})")
for nn in R["internal"]:
    rep.check(isinstance(nets.get(nn), dict) and nets[nn].get("internal") is True, f"network {nn!r} must be declared with `internal: true`")
for name, s in svcs.items():
    n = s.get("networks")
    for x in (n.keys() if isinstance(n, dict) else as_list(n)):
        rep.check(x in nets, f"service {name!r} uses the network {x!r}, which is not declared")

# R10 memory limits
for name, s in svcs.items():
    lim = (((s.get("deploy") or {}).get("resources") or {}).get("limits") or {}).get("memory") if isinstance(s.get("deploy"), dict) else None
    rep.check(bool(lim) or bool(s.get("mem_limit")), f"service {name!r} needs a memory limit (deploy.resources.limits.memory or mem_limit)")

rep.finish()
'''

DB_KINDS = {
    "postgres": dict(scheme="postgres", image="postgres:16.3-alpine", port=5432, data="/var/lib/postgresql/data", pw="POSTGRES_PASSWORD", test=["CMD-SHELL", "pg_isready -U {user} -d {dbname}"], extra=lambda c: {"POSTGRES_USER": c["user"], "POSTGRES_DB": c["dbname"]}),
    "mariadb": dict(scheme="mysql", image="mariadb:11.4.2", port=3306, data="/var/lib/mysql", pw="MARIADB_ROOT_PASSWORD", test=["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"], extra=lambda c: {"MARIADB_DATABASE": c["dbname"]}),
}
CACHE_KINDS = {
    "redis": dict(image="redis:7.2.5-alpine", port=6379, test=["CMD", "redis-cli", "ping"], cmd=["redis-server", "--save", "", "--appendonly", "no"]),
    "valkey": dict(image="valkey/valkey:7.2.6", port=6379, test=["CMD", "valkey-cli", "ping"], cmd=["valkey-server", "--save", ""]),
    "rabbit": dict(image="rabbitmq:3.13.4-management-alpine", port=5672, test=["CMD", "rabbitmq-diagnostics", "-q", "ping"], cmd=None),
}

STACKS = [
    dict(name="tidewatch", what="a vessel arrival tracker", app="api", worker="poller", proxy="gateway", db="postgres", cache="redis", edge=None, user="tide", dbname="arrivals", app_port=8080, host=8080, proxy_img="caddy:2.8.4-alpine"),
    dict(name="lanternbook", what="a recipe-sharing site", app="web", worker="mailer", proxy="front", db="mariadb", cache="valkey", edge=("relay", "boky/postfix:4.3.0", 25), user="lantern", dbname="recipes", app_port=3000, host=8081, proxy_img="nginx:1.27.0-alpine"),
    dict(name="kilnworks", what="a pottery-studio booking system", app="core", worker="reminders", proxy="edge", db="postgres", cache="rabbit", edge=("dnsmasq", "jpillora/dnsmasq:1.1", 53), user="kiln", dbname="bookings", app_port=9000, host=8082, proxy_img="traefik:v3.1.2"),
    dict(name="mothledger", what="a museum collection ledger", app="ledgerd", worker="indexer", proxy="door", db="mariadb", cache="redis", edge=("sshgate", "linuxserver/openssh-server:9.7_p1-r4-ls178", 22), user="moth", dbname="specimens", app_port=7070, host=8083, proxy_img="haproxy:3.0.3-alpine"),
]


def build_model(rng, i):
    c = STACKS[i % len(STACKS)]
    db, cache = DB_KINDS[c["db"]], CACHE_KINDS[c["cache"]]
    mem = lambda m: {"resources": {"limits": {"memory": m}}}
    health = lambda test, iv="10s": {"test": test, "interval": iv, "timeout": "3s", "retries": rng.choice([3, 5, 6])}
    s = {}
    s[c["proxy"]] = {"image": c["proxy_img"], "ports": ["80:80", "443:443"], "depends_on": [c["app"]], "networks": ["frontend", "backend"], "restart": "unless-stopped", "deploy": mem("128m")}
    s[c["app"]] = {"build": f"./{c['app']}", "environment": {"DATABASE_URL": f"{db['scheme']}://{c['user']}:${{DB_PASSWORD}}@db:{db['port']}/{c['dbname']}", "CACHE_HOST": "cache", "API_TOKEN": "${API_TOKEN:?set API_TOKEN}", "PORT": str(c["app_port"])},
                   "ports": [f"127.0.0.1:{c['host']}:{c['app_port']}"], "depends_on": {"db": {"condition": "service_healthy"}, "cache": {"condition": "service_healthy"}, "migrate": {"condition": "service_completed_successfully"}},
                   "networks": ["frontend", "backend"], "restart": "unless-stopped", "deploy": mem("512m")}
    s[c["worker"]] = {"build": f"./{c['worker']}", "command": [c["worker"], "--concurrency", str(rng.choice([2, 4, 8]))], "environment": {"DATABASE_URL": f"{db['scheme']}://{c['user']}:${{DB_PASSWORD}}@db:{db['port']}/{c['dbname']}", "CACHE_HOST": "cache"},
                      "depends_on": {"db": {"condition": "service_healthy"}, "cache": {"condition": "service_healthy"}}, "networks": ["backend"], "restart": "unless-stopped", "deploy": mem("256m")}
    s["migrate"] = {"build": f"./{c['app']}", "command": [c["app"], "migrate", "--up"], "environment": {"DATABASE_URL": f"{db['scheme']}://{c['user']}:${{DB_PASSWORD}}@db:{db['port']}/{c['dbname']}"}, "depends_on": {"db": {"condition": "service_healthy"}},
                    "networks": ["backend"], "restart": "no", "deploy": mem("128m")}
    env = {db["pw"]: "${DB_PASSWORD}", **db["extra"](c)}
    s["db"] = {"image": db["image"], "environment": env, "volumes": [f"dbdata:{db['data']}"], "healthcheck": health([t.format(**c) for t in db["test"]]), "networks": ["backend"], "restart": "unless-stopped", "deploy": mem("1g")}
    cs = {"image": cache["image"], "healthcheck": health(cache["test"], "5s"), "networks": ["backend"], "restart": "unless-stopped", "deploy": mem("128m")}
    if cache["cmd"]:
        cs["command"] = cache["cmd"]
    s["cache"] = cs
    if c["edge"]:
        n, img, port = c["edge"]
        s[n] = {"image": img, "ports": [f"{port}:{port}"], "networks": ["frontend"], "restart": "unless-stopped", "deploy": mem("64m")}
    model = {"name": c["name"], "services": s, "networks": {"frontend": {}, "backend": {"internal": True}}, "volumes": {"dbdata": {}}}
    rules = {"path": "compose.yaml", "keep": {k: ({"image": v["image"]} if "image" in v else {"build": v["build"]}) for k, v in s.items()},
             "deps": {c["app"]: {"db": "service_healthy", "cache": "service_healthy", "migrate": "service_completed_successfully"}, c["worker"]: {"db": "service_healthy", "cache": "service_healthy"}, "migrate": {"db": "service_healthy"}},
             "health": ["db", "cache"], "no_ports": ["db", "cache", c["worker"], "migrate"], "public": [c["proxy"]] + ([c["edge"][0]] if c["edge"] else []), "data": {"db": db["data"]},
             "oneshot": ["migrate"], "networks": {k: v["networks"] for k, v in s.items() if "networks" in v}, "internal": ["backend"]}
    return model, {"c": c, "rules": rules, "db": db, "cache_kind": cache}


def render(model, ctx):
    m = {k: v for k, v in model.items() if k != "name"}
    return {"compose.yaml": Y.roundtrip(m)}


# ---------------------------------------------------------------------------------------------------- defects


def d_latest(m, ctx, rng):
    svc = rng.choice(["db", "cache", ctx["c"]["proxy"]])
    img = m["services"][svc]["image"]
    if rng.random() < 0.5:
        m["services"][svc]["image"] = img.rsplit(":", 1)[0]
    else:
        m["services"][svc]["image"] = img.rsplit(":", 1)[0] + ":latest"
    return {"a": svc}


def d_dep_typo(m, ctx, rng):
    w = ctx["c"]["worker"]
    dd_ = m["services"][w]["depends_on"]
    dd_["database"] = dd_.pop("db")
    return {"a": w}


def d_dep_short(m, ctx, rng):
    a = ctx["c"]["app"]
    m["services"][a]["depends_on"] = ["db", "cache", "migrate"]
    return {"a": a}


def d_sexa(m, ctx, rng):
    n, img, port = ctx["c"]["edge"]
    m["services"][n]["ports"] = [Y.Raw(f"{port}:{port}", port // 1 * 60 + port)]
    return {"a": n}


def d_clash(m, ctx, rng):
    c = ctx["c"]
    m["services"][c["app"]]["ports"] = [f"127.0.0.1:80:{c['app_port']}"]
    return {"a": c["app"], "b": c["proxy"]}


def d_db_public(m, ctx, rng):
    m["services"]["db"]["ports"] = [f"{ctx['db']['port']}:{ctx['db']['port']}"]
    return {}


def d_vol(m, ctx, rng):
    m["volumes"] = {}
    return {}


def d_inline_secret(m, ctx, rng):
    db = ctx["db"]
    m["services"]["db"]["environment"][db["pw"]] = rng.choice(["hunter2", "changeme", "s3cr3t-pass"])
    return {}


def d_no_health(m, ctx, rng):
    del m["services"]["db"]["healthcheck"]
    return {}


def d_restart(m, ctx, rng):
    svc = rng.choice(["db", ctx["c"]["worker"], "cache"])
    del m["services"][svc]["restart"]
    return {"a": svc}


def d_restart_no(m, ctx, rng):
    m["services"]["migrate"]["restart"] = Y.Raw("no", False)
    return {}


def d_version(m, ctx, rng):
    m2 = {"version": "3.8"}
    m2.update({k: v for k, v in m.items()})
    m.clear()
    m.update(m2)
    return {}


def d_net(m, ctx, rng):
    m["networks"]["backend"] = {}
    return {}


def d_net_svc(m, ctx, rng):
    m["services"][ctx["c"]["worker"]]["networks"] = ["frontend", "backend"]
    return {"a": ctx["c"]["worker"]}


def d_mem(m, ctx, rng):
    svc = rng.choice(["db", ctx["c"]["app"], "cache"])
    del m["services"][svc]["deploy"]
    return {"a": svc}


def d_sock(m, ctx, rng):
    m["services"][ctx["c"]["proxy"]]["volumes"] = ["/var/run/docker.sock:/var/run/docker.sock:ro"]
    return {"a": ctx["c"]["proxy"]}


def d_indent(m, ctx, rng):
    def post(files):
        lines = files["compose.yaml"].split("\n")
        idx = [i for i, l in enumerate(lines) if l.startswith("    restart:")]
        k = idx[len(idx) // 2]
        lines[k] = "   " + lines[k].lstrip()
        files["compose.yaml"] = "\n".join(lines)
        try:
            Y.load_all(files["compose.yaml"])
        except ValueError:
            return files
        raise RuntimeError("the indentation defect did not break the YAML")
    return {"_post": post}


def d_tab(m, ctx, rng):
    def post(files):
        lines = files["compose.yaml"].split("\n")
        idx = [i for i, l in enumerate(lines) if l.startswith("    healthcheck:") or l.startswith("    networks:")]
        k = idx[0]
        lines[k] = "\t" + lines[k].lstrip()
        files["compose.yaml"] = "\n".join(lines)
        return files
    return {"_post": post}


DEFECTS = {
    "latest": (d_latest, ["the `{a}` service floats on whatever image version was published last", "`{a}` has no pinned image version, so redeploys pull surprises", "an unpinned image for `{a}` broke last night's deploy"]),
    "dep-typo": (d_dep_typo, ["`{a}` never waits for the database (compose says it depends on an unknown service)", "`docker compose up` complains about a dependency of `{a}`"]),
    "dep-short": (d_dep_short, ["`{a}` starts before the database and the cache are actually ready and crashes at boot", "the app container races the database on cold starts"]),
    "sexa": (d_sexa, ["the `{a}` port mapping shows up as a strange number instead of what we wrote", "`docker compose config` prints a garbage port for `{a}`"]),
    "clash": (d_clash, ["`{a}` and `{b}` fight over host port 80", "compose refuses to start: port 80 is bound twice"]),
    "db-public": (d_db_public, ["the database port is reachable from the outside network", "security flagged that the DB port is published on all interfaces"]),
    "vol": (d_vol, ["compose rejects the file: the database volume is not defined", "`docker compose up` says a named volume is not declared"]),
    "inline-secret": (d_inline_secret, ["the database password is committed in the compose file", "somebody hard-coded the DB password"]),
    "no-health": (d_no_health, ["the database has no healthcheck, so nothing can wait for it", "no healthcheck is defined for `db`"]),
    "restart": (d_restart, ["`{a}` stays down after a host reboot", "`{a}` is not restarted automatically"]),
    "restart-no": (d_restart_no, ["the migration container keeps restarting forever although it should run once", "`migrate` is brought back every time it exits"]),
    "version": (d_version, ["compose prints a warning that the `version` attribute is obsolete", "every compose command warns about the top-level version key"]),
    "net": (d_net, ["the backend network is reachable from outside; it should be internal", "containers on `backend` can reach the internet but must not"]),
    "net-svc": (d_net_svc, ["`{a}` sits on the public network although it only talks to the database and cache", "`{a}` is attached to too many networks"]),
    "mem": (d_mem, ["`{a}` has no memory limit and once ate the whole host", "an OOM on the host was traced to `{a}` (no limit)"]),
    "sock": (d_sock, ["the proxy container mounts the Docker socket", "the audit found /var/run/docker.sock mounted into `{a}`"]),
    "indent": (d_indent, ["`docker compose config` fails with a YAML error after the last edit", "the file stopped parsing after somebody touched the indentation"]),
    "tab": (d_tab, ["compose reports a YAML syntax error about a tab character", "`docker compose up` fails with `found character that cannot start any token`"]),
}


# ---------------------------------------------------------------------------------------------------- docs


def docs(model, ctx):
    r, c = ctx["rules"], ctx["c"]
    rules_md = dd(f'''
        # Stack rules for {c["name"]}

        `compose.yaml` is validated mechanically with the rules below. The YAML is read with the YAML 1.1 rules of Ruby's Psych
        (so an unquoted `no` is the boolean false, and an unquoted `22:22` is the number 1342, written in base 60).

        1. **Keep the work.** The stack has exactly the services {", ".join("`" + k + "`" for k in r["keep"])}; each keeps its `image` (or `build` context) and
           nothing may be removed. There is no top-level `version:` key (it is obsolete).
        2. **Pinned images.** Every `image:` has an explicit tag or digest; the tag `latest` and a missing tag are not allowed.
        3. **Startup order.** `depends_on` only names services of the stack and has no cycle. Where the stack needs an ordering it must be written in the
           long form with the condition: `service_healthy` for `db` and `cache`, `service_completed_successfully` for `migrate`
           (the ordering is {"; ".join(f"`{n}` needs " + ", ".join(f"`{t}`" for t in w) for n, w in r["deps"].items())}).
        4. **Health.** `db` and `cache` have a `healthcheck` whose `test` is a list starting with `CMD` or `CMD-SHELL`, `interval` is a duration such as `10s`, and `retries` is an integer of at least 3.
        5. **Ports.** Every published port is a quoted string `[IP:]HOST:CONTAINER[/proto]`. A host port is published once. Only {", ".join("`" + x + "`" for x in r["public"])} may publish on all interfaces
           (everything else that publishes must bind `127.0.0.1`); {", ".join("`" + x + "`" for x in r["no_ports"])} publish nothing.
        6. **Volumes.** Every named volume that a service uses is declared under top-level `volumes:`. `db` keeps `{ctx["db"]["data"]}` on a named volume. Nothing mounts the Docker socket.
        7. **Secrets.** Environment variables whose name contains PASSWORD, SECRET, TOKEN or KEY (and does not end in `_FILE`) must be `${{VAR}}`-style interpolations, never literal values.
        8. **Restart.** Every service has `restart: unless-stopped`, except the one-shot `migrate`, which has `restart: "no"` (quoted).
        9. **Networks.** Each service is attached to exactly the networks it has in the reference layout: {"; ".join(f"`{k}`: " + ", ".join(v) for k, v in r["networks"].items())}.
           The `backend` network is declared `internal: true`. Every network a service uses is declared.
        10. **Limits.** Every service has a memory limit (`deploy.resources.limits.memory` or `mem_limit`).
    ''')
    return {"STACK_RULES.md": rules_md, "README.md": f"# {c['name']}\n\nCompose stack for {c['what']}. Only `compose.yaml` is relevant here (the application source is omitted). The rules for the stack are in `STACK_RULES.md`.\n"}


def hidden(model, ctx):
    return {"tests/rules.json": json.dumps(ctx["rules"], indent=1) + "\n"}


def prompt(rng, ctx, texts, vague):
    c = ctx["c"]
    return K.fix_prompt(rng, "compose.yaml", f"compose file of {c['name']} ({c['what']})", texts, "STACK_RULES.md", vague, [
        f"`compose.yaml` of {c['name']} doesn't pass our stack rules (`STACK_RULES.md`). Find what is wrong and fix it without removing or renaming services.",
        f"The platform team's audit rejects the compose file of {c['name']} ({c['what']}). Make `compose.yaml` comply with `STACK_RULES.md`; keep every service.",
    ])


def wrong(model, ctx):
    import copy
    w1 = copy.deepcopy(model)
    del w1["services"][ctx["c"]["worker"]]
    w1["services"]["db"].pop("healthcheck", None)
    w2 = copy.deepcopy(model)
    w2["services"]["db"]["image"] = "postgres:latest"
    return [render(w1, ctx), render(w2, ctx)]


PLAN = [
    {"keys": ["latest"]}, {"keys": ["version"], "d": 1}, {"keys": ["tab"], "d": 1}, {"keys": ["vol", "restart"]}, {"keys": ["sexa"], "d": 3},
    {"keys": ["dep-short", "no-health"]}, {"keys": ["clash", "db-public"]}, {"keys": ["inline-secret", "mem", "sock"]},
    {"keys": ["restart-no", "dep-typo", "net-svc"]}, {"keys": ["net", "latest", "indent"]}, {"keys": ["sexa", "dep-short", "inline-secret", "vol"], "d": 4},
    {"keys": ["dep-typo", "db-public", "restart-no", "mem", "net", "latest"], "vague": True, "d": 5}, {"keys": ["sexa", "clash", "no-health", "sock", "restart"], "vague": True, "d": 5},
    {"keys": ["inline-secret"], "d": 1}, {"keys": ["restart-no"], "d": 2}, {"keys": ["db-public", "net"], "d": 3},
]


def _build(rng, i):
    # the stack that goes with each plan entry; entries that need an edge service use stacks that have one
    need_edge = any(k == "sexa" for k in PLAN[i]["keys"])
    idx = i % len(STACKS)
    if need_edge and not STACKS[idx]["edge"]:
        idx = 1 + (i % 3)
    return build_model(rng, idx)


@family("devops-compose-stacks", category="devops", lang="text", kind="fix", n=len(PLAN),
        summary="repair docker-compose stacks against a mechanical policy: pinned images, health-gated depends_on, port exposure, volumes, secrets, networks, YAML 1.1 traps")
def compose_stacks(rng, n):
    return K.fix_tasks(rng, n, prefix="compose", plan=PLAN, build=_build, render=render, defects=DEFECTS, docs=docs, hidden=hidden, check=CHECK_COMPOSE,
                       prompt=prompt, wrong=wrong, tags=["compose", "docker", "yaml"])
