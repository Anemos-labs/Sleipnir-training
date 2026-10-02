"""DevOps tasks: Dockerfile hygiene. A semantic validator parses the Dockerfile (stages, instructions, layer order) and a .dockerignore."""
import json
import copy

from fx import dd, family
from generators.devops import _dokit as K

CHECK_DOCKER = r'''
from dolib import *

R = json.load(open("tests/rules.json", encoding="utf-8"))
rep = Report()
INSTR = {"FROM", "RUN", "CMD", "LABEL", "EXPOSE", "ENV", "ADD", "COPY", "ENTRYPOINT", "VOLUME", "USER", "WORKDIR", "ARG", "ONBUILD", "STOPSIGNAL", "HEALTHCHECK", "SHELL", "MAINTAINER"}


def parse(text):
    """Return a list of (lineno, INSTRUCTION, argument text) joining backslash continuations; comment lines inside continuations are skipped."""
    out, buf, start = [], "", 0
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.rstrip()
        if not buf and (not line.strip() or line.lstrip().startswith("#")):
            continue
        if buf and line.lstrip().startswith("#"):
            continue
        if not buf:
            start = n
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        buf += line
        out.append((start, buf.strip()))
        buf = ""
    if buf:
        out.append((start, buf.strip()))
    res = []
    for n, s in out:
        word, _, rest = s.partition(" ")
        if word.upper() not in INSTR:
            die(f"Dockerfile line {n}: unknown instruction {word!r}")
        res.append((n, word.upper(), rest.strip()))
    return res


def exec_form(arg):
    try:
        v = json.loads(arg)
        return v if isinstance(v, list) and all(isinstance(x, str) for x in v) else None
    except ValueError:
        return None


df = parse(read("Dockerfile"))
if not df or df[0][1] not in ("FROM", "ARG"):
    die("a Dockerfile must start with FROM (or ARG)")
stages = []
for n, ins, arg in df:
    if ins == "FROM":
        parts = arg.split()
        flags = [p for p in parts if p.startswith("--")]
        parts = [p for p in parts if not p.startswith("--")]
        name = parts[2] if len(parts) >= 3 and parts[1].upper() == "AS" else None
        stages.append({"line": n, "image": parts[0], "name": name, "ins": []})
    elif stages:
        stages[-1]["ins"].append((n, ins, arg))
if not stages:
    die("no FROM instruction")
final = stages[-1]
names = {s["name"] for s in stages if s["name"]}

# R1 stages and kept content
rep.check(len(stages) >= 2, "use a multi-stage build: at least a build stage and a runtime stage")
rep.check(final["image"].split(":")[0].split("@")[0] in R["runtime_repos"], f"the final stage must be based on one of {R['runtime_repos']} (got {final['image']!r})")
if len(stages) >= 2:
    b = stages[0]
    runs = " ; ".join(a for _, i, a in b["ins"] if i == "RUN")
    rep.check(R["build_cmd"] in runs, f"the build stage must still run `{R['build_cmd']}`")
    rep.check(R["build_cmd"] not in " ; ".join(a for _, i, a in final["ins"] if i == "RUN"), f"`{R['build_cmd']}` belongs to the build stage, not to the runtime image")
cmds = [(n, a) for n, i, a in final["ins"] if i == "CMD"]
if rep.check(len(cmds) == 1, "the final stage needs exactly one CMD"):
    rep.check(exec_form(cmds[0][1]) == R["cmd"], f"CMD must stay {json.dumps(R['cmd'])} in exec (JSON array) form (got {cmds[0][1]!r})")
ep = [(n, a) for n, i, a in final["ins"] if i == "ENTRYPOINT"]
if R.get("entrypoint"):
    rep.check(len(ep) == 1 and exec_form(ep[0][1]) == R["entrypoint"], f"ENTRYPOINT must be {json.dumps(R['entrypoint'])} in exec form")
rep.check(any(i == "EXPOSE" and R["port"] in re.findall(r"\d+", a) for _, i, a in final["ins"]), f"the final stage must EXPOSE {R['port']}")

# R2 pinned base images
for s in stages:
    img = s["image"]
    if img in names or img == "scratch":
        continue
    last = img.rsplit("/", 1)[-1]
    tag = last.split(":", 1)[1] if ":" in last else ("@" if "@" in img else "")
    rep.check(tag not in ("", "latest") and (tag == "@" or re.search(r"\d", tag) or tag == "nonroot"), f"line {s['line']}: base image {img!r} needs a pinned version tag (not latest, not missing)")

# R3 non-root runtime
users = [a for _, i, a in final["ins"] if i == "USER"]
rep.check(bool(users) and users[-1].split(":")[0].strip() not in ("root", "0"), "the final stage must switch to a non-root USER")
if users:
    last_user = max(n for n, i, a in final["ins"] if i == "USER")
    for n, i, a in final["ins"]:
        if i in ("CMD", "ENTRYPOINT"):
            rep.check(n > last_user, f"line {n}: {i} comes before the USER instruction")

# R4 package managers
for s in stages:
    for n, i, a in s["ins"]:
        if i != "RUN":
            continue
        if re.search(r"apt-get\s+(?:-\S+\s+)*install", a):
            rep.check("apt-get update" in a and a.index("apt-get update") < a.index("install"), f"line {n}: `apt-get update` and `apt-get install` must be in the same RUN (a cached update layer goes stale)")
            rep.check("--no-install-recommends" in a, f"line {n}: apt-get install needs --no-install-recommends")
            rep.check(re.search(r"rm\s+-rf\s+/var/lib/apt/lists", a), f"line {n}: remove /var/lib/apt/lists in the same RUN that installs packages")
        if re.search(r"\bapk\s+add\b", a):
            rep.check("--no-cache" in a, f"line {n}: apk add needs --no-cache")
        if re.search(r"\bcd\s", a):
            rep.check(False, f"line {n}: do not `cd` in RUN; use WORKDIR")
        if "pip install" in a and R["lang"] == "python":
            rep.check("--no-cache-dir" in a, f"line {n}: pip install needs --no-cache-dir")
        if R["lang"] == "node" and re.search(r"\bnpm\s+install\b", a):
            rep.check(False, f"line {n}: use `npm ci` for reproducible installs, not `npm install`")

# R5 layer order for dependency installs
for si, s in enumerate(stages):
    ins = s["ins"]
    inst = [k for k, (n, i, a) in enumerate(ins) if i == "RUN" and re.search(R["install_re"], a)]
    if not inst:
        continue
    k = inst[0]
    srccopy = [j for j, (n, i, a) in enumerate(ins) if i == "COPY" and "--from" not in a and re.search(r"(^|\s)\.(/)?\s+\S+\s*$", a) and not any(m in a for m in R["manifests"])]
    mancopy = [j for j, (n, i, a) in enumerate(ins) if i == "COPY" and "--from" not in a and any(m in a for m in R["manifests"])]
    rep.check(any(j < k for j in mancopy), f"stage {s['name'] or si}: copy the dependency manifests ({', '.join(R['manifests'])}) before the install step so the layer is cached")
    rep.check(all(j > k for j in srccopy), f"stage {s['name'] or si}: `COPY . .` must come after the dependency install, or every source change re-installs everything")

# R6 exec forms, ADD, WORKDIR, secrets
for s in stages:
    for n, i, a in s["ins"]:
        if i in ("CMD", "ENTRYPOINT"):
            rep.check(exec_form(a) is not None, f"line {n}: {i} must use the exec (JSON array) form")
        if i == "ADD" and not re.search(r"^(--\S+\s+)*(https?://|\S+\.(tar|tar\.gz|tgz)\s)", a):
            rep.check(False, f"line {n}: use COPY instead of ADD for plain files")
        if i == "WORKDIR":
            rep.check(a.startswith("/") or a.startswith("$"), f"line {n}: WORKDIR must be an absolute path")
        if i in ("ENV", "ARG"):
            for k, v in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=(\S*)", a):
                if re.search(r"PASSWORD|SECRET|TOKEN|KEY", k) and v and not v.startswith("$"):
                    rep.check(False, f"line {n}: {k} carries a literal secret; pass it at run time")
hc = [(n, a) for n, i, a in final["ins"] if i == "HEALTHCHECK"]
if rep.check(len(hc) == 1, "the final stage needs a HEALTHCHECK"):
    m = re.match(r"((?:--\S+\s+)*)CMD\s+(.*)$", hc[0][1])
    if rep.check(m, "HEALTHCHECK must be `HEALTHCHECK [--interval=..] CMD [...]`"):
        rep.check("--interval=" in m.group(1), "HEALTHCHECK needs an --interval")
        rep.check(exec_form(m.group(2)) is not None, "the HEALTHCHECK command must be in exec (JSON array) form")

# R7 build tools out of the runtime stage
for n, i, a in final["ins"]:
    if i == "RUN" and re.search(R["toolchain"], a):
        rep.check(False, f"line {n}: build tooling in the runtime stage ({R['toolchain']})")

# R8 .dockerignore
ig = [l.strip() for l in read(".dockerignore").split("\n") if l.strip() and not l.strip().startswith("#")]
for e in R["ignore"]:
    rep.check(e in ig, f".dockerignore must list {e!r}")

rep.finish()
'''

PROJECTS = [
    dict(name="tallybot", lang="python", what="a chat bot that tallies votes", build_cmd="python -m compileall -q app", port="8080", cmd=["gunicorn", "-b", "0.0.0.0:8080", "app:create_app()"], entrypoint=["tini", "--"],
         runtime_repos=["python"], manifests=["requirements.txt"], install_re=r"pip install", toolchain=r"pip install|gcc|build-essential|compileall", ignore=[".git", "__pycache__", "*.pyc", ".env", "venv"], user="app"),
    dict(name="quillhub", lang="node", what="a document publishing service", build_cmd="npm run build", port="3000", cmd=["node", "dist/server.js"], entrypoint=None,
         runtime_repos=["node"], manifests=["package.json", "package-lock.json"], install_re=r"npm (ci|install)", toolchain=r"npm run build|tsc|webpack", ignore=[".git", "node_modules", "*.log", ".env", "coverage"], user="node"),
    dict(name="brinegate", lang="go", what="an HTTP gateway", build_cmd="go build", port="9090", cmd=["/brinegate", "serve", "--addr", ":9090"], entrypoint=None,
         runtime_repos=["gcr.io/distroless/static-debian12", "alpine"], manifests=["go.mod", "go.sum"], install_re=r"go mod download", toolchain=r"go build|go install|apk add .*(gcc|musl-dev)", ignore=[".git", "*.test", "bin", ".env"], user="65532:65532"),
    dict(name="embertask", lang="python", what="a job scheduler", build_cmd="python -m compileall -q src", port="7000", cmd=["python", "-m", "embertask", "--port", "7000"], entrypoint=None,
         runtime_repos=["python"], manifests=["requirements.txt"], install_re=r"pip install", toolchain=r"pip install|gcc|build-essential|compileall", ignore=[".git", "__pycache__", "*.pyc", ".env", ".venv"], user="runner"),
]


def stage(name, base, ins):
    return {"name": name, "base": base, "ins": [list(i) for i in ins]}


def model_for(p, rng):
    port = p["port"]
    if p["lang"] == "python":
        py = rng.choice(["3.12.4", "3.11.9"])
        src = "app" if p["name"] == "tallybot" else "src"
        b = stage("build", f"python:{py}-slim", [("WORKDIR", "/src"), ("RUN", "python -m venv /opt/venv"), ("ENV", "PATH=/opt/venv/bin:$PATH"), ("COPY", "requirements.txt ./"),
                                                  ("RUN", "pip install --no-cache-dir -r requirements.txt"), ("COPY", ". ."), ("RUN", p["build_cmd"])])
        f = stage(None, f"python:{py}-slim", [("RUN", "apt-get update && apt-get install -y --no-install-recommends tini curl && rm -rf /var/lib/apt/lists/*"), ("RUN", f"useradd --system --uid 10001 {p['user']}"), ("WORKDIR", "/app"),
                                              ("COPY", "--from=build /opt/venv /opt/venv"), ("COPY", f"--from=build /src/{src} ./{src}"), ("ENV", "PATH=/opt/venv/bin:$PATH"), ("USER", p["user"]), ("EXPOSE", port),
                                              ("HEALTHCHECK", f'--interval=30s --timeout=3s CMD ["curl", "-fsS", "http://localhost:{port}/healthz"]')])
        if p["entrypoint"]:
            f["ins"].append(["ENTRYPOINT", json.dumps(p["entrypoint"])])
        f["ins"].append(["CMD", json.dumps(p["cmd"])])
    elif p["lang"] == "node":
        nv = rng.choice(["20.15.0", "22.4.1"])
        b = stage("build", f"node:{nv}-alpine", [("WORKDIR", "/src"), ("COPY", "package.json package-lock.json ./"), ("RUN", "npm ci"), ("COPY", ". ."), ("RUN", p["build_cmd"])])
        f = stage(None, f"node:{nv}-alpine", [("RUN", "apk add --no-cache tini"), ("WORKDIR", "/app"), ("COPY", "package.json package-lock.json ./"), ("RUN", "npm ci --omit=dev"), ("COPY", "--from=build /src/dist ./dist"),
                                              ("ENV", "NODE_ENV=production"), ("USER", p["user"]), ("EXPOSE", port),
                                              ("HEALTHCHECK", f'--interval=30s --timeout=3s CMD ["wget", "-qO-", "http://localhost:{port}/healthz"]'), ("CMD", json.dumps(p["cmd"]))])
    else:
        gv = rng.choice(["1.22.5", "1.21.12"])
        b = stage("build", f"golang:{gv}-alpine", [("WORKDIR", "/src"), ("COPY", "go.mod go.sum ./"), ("RUN", "go mod download"), ("COPY", ". ."), ("RUN", f"CGO_ENABLED=0 {p['build_cmd']} -trimpath -o /out/brinegate ./cmd/brinegate")])
        f = stage(None, "gcr.io/distroless/static-debian12:nonroot", [("COPY", "--from=build /out/brinegate /brinegate"), ("USER", p["user"]), ("EXPOSE", port),
                                                                     ("HEALTHCHECK", '--interval=30s --timeout=3s CMD ["/brinegate", "healthcheck"]'), ("CMD", json.dumps(p["cmd"]))])
    return {"stages": [b, f], "ignore": list(p["ignore"])}


def render(model, ctx):
    out = []
    for s in model["stages"]:
        out.append(f"FROM {s['base']}" + (f" AS {s['name']}" if s["name"] else ""))
        for ins, arg in s["ins"]:
            if ins == "RUN" and "apt-get" in arg and "&&" in arg:
                arg = " \\\n    && ".join(x.strip() for x in arg.split("&&"))
            out.append(f"{ins} {arg}")
        out.append("")
    files = {"Dockerfile": "\n".join(out).rstrip() + "\n", ".dockerignore": "\n".join(model["ignore"]) + "\n"}
    for k, v in model.get("_text", {}).items():
        files[k] = v
    return files


# ---------------------------------------------------------------------------------------------------- defects


def ix(s, ins, pred=lambda a: True):
    return next(k for k, (i, a) in enumerate(s["ins"]) if i == ins and pred(a))


def d_latest(m, ctx, rng):
    s = rng.choice(m["stages"][:1] if ctx["p"]["lang"] == "go" else m["stages"])
    s["base"] = s["base"].split(":")[0] + rng.choice([":latest", ""])
    return {}


def d_root(m, ctx, rng):
    f = m["stages"][-1]
    f["ins"][ix(f, "USER")][1] = "root"
    return {}


def d_no_user(m, ctx, rng):
    f = m["stages"][-1]
    del f["ins"][ix(f, "USER")]
    return {}


def d_apt_clean(m, ctx, rng):
    f = m["stages"][-1]
    k = ix(f, "RUN", lambda a: "apt-get" in a)
    f["ins"][k][1] = f["ins"][k][1].replace(" && rm -rf /var/lib/apt/lists/*", "")
    return {}


def d_apt_recs(m, ctx, rng):
    f = m["stages"][-1]
    k = ix(f, "RUN", lambda a: "apt-get" in a)
    f["ins"][k][1] = f["ins"][k][1].replace(" --no-install-recommends", "")
    return {}


def d_apt_split(m, ctx, rng):
    f = m["stages"][-1]
    k = ix(f, "RUN", lambda a: "apt-get" in a)
    pre, rest = f["ins"][k][1].split(" && ", 1)
    f["ins"][k:k + 1] = [["RUN", pre], ["RUN", rest]]
    return {}


def d_apk(m, ctx, rng):
    f = m["stages"][-1]
    k = ix(f, "RUN", lambda a: "apk add" in a)
    f["ins"][k][1] = f["ins"][k][1].replace(" --no-cache", "")
    return {}


def d_copy_order(m, ctx, rng):
    b = m["stages"][0]
    k = ix(b, "COPY", lambda a: a == ". .")
    b["ins"].pop(k)
    w = ix(b, "WORKDIR")
    b["ins"].insert(w + 1, ["COPY", ". ."])
    return {}


def d_shell_cmd(m, ctx, rng):
    f = m["stages"][-1]
    k = ix(f, "CMD")
    f["ins"][k][1] = " ".join(json.loads(f["ins"][k][1]))
    return {}


def d_add(m, ctx, rng):
    b = m["stages"][0]
    k = ix(b, "COPY", lambda a: a == ". .")
    b["ins"][k][0] = "ADD"
    return {}


def d_no_health(m, ctx, rng):
    f = m["stages"][-1]
    del f["ins"][ix(f, "HEALTHCHECK")]
    return {}


def d_cd(m, ctx, rng):
    b = m["stages"][0]
    k = ix(b, "RUN", lambda a: a == ctx["p"]["build_cmd"] or a.endswith(ctx["p"]["build_cmd"] + " -trimpath -o /out/brinegate ./cmd/brinegate") or ctx["p"]["build_cmd"] in a)
    b["ins"][k][1] = "cd /src && " + b["ins"][k][1]
    return {}


def d_workdir_rel(m, ctx, rng):
    f = m["stages"][-1]
    k = ix(f, "WORKDIR") if any(i == "WORKDIR" for i, _ in f["ins"]) else None
    if k is None:
        b = m["stages"][0]
        b["ins"][ix(b, "WORKDIR")][1] = "src"
    else:
        f["ins"][k][1] = "app"
    return {}


def d_build_in_final(m, ctx, rng):
    f = m["stages"][-1]
    p = ctx["p"]
    if p["lang"] == "go":
        f["base"] = "golang:1.22.5-alpine"
        f["ins"].insert(0, ["RUN", "go build -o /brinegate ./cmd/brinegate"])
    else:
        f["ins"].insert(len(f["ins"]) - 3, ["RUN", p["build_cmd"]])
    return {}


def d_env_secret(m, ctx, rng):
    f = m["stages"][-1]
    f["ins"].insert(ix(f, "USER"), ["ENV", rng.choice(["DB_PASSWORD=hunter2", "API_TOKEN=abc123def456", "SECRET_KEY=changeme"])])
    return {}


def d_pip(m, ctx, rng):
    b = m["stages"][0]
    k = ix(b, "RUN", lambda a: "pip install" in a)
    b["ins"][k][1] = b["ins"][k][1].replace(" --no-cache-dir", "")
    return {}


def d_npm(m, ctx, rng):
    b = m["stages"][0]
    k = ix(b, "RUN", lambda a: a == "npm ci")
    b["ins"][k][1] = "npm install"
    return {}


def d_ignore(m, ctx, rng):
    drop = rng.sample([e for e in m["ignore"] if e not in (".git",)] + [".git"], 2)
    m["ignore"] = [e for e in m["ignore"] if e not in drop]
    return {}


def d_no_expose(m, ctx, rng):
    f = m["stages"][-1]
    del f["ins"][ix(f, "EXPOSE")]
    return {}


def d_continuation(m, ctx, rng):
    def post(files):
        t = files["Dockerfile"]
        if "\\\n    && rm -rf" not in t:
            raise RuntimeError("no continuation to break")
        files["Dockerfile"] = t.replace("\\\n    && rm -rf", "\n    && rm -rf", 1)
        return files
    return {"_post": post}


def d_single(m, ctx, rng):
    # collapse to one stage: the runtime image is built from the builder (toolchain included)
    m["stages"] = [m["stages"][0]] + [m["stages"][1]]
    m["stages"][1]["base"] = m["stages"][0]["base"]
    return {}


DEFECTS = {
    "latest": (d_latest, ["a base image is unpinned (`latest`/no tag) and builds differ from day to day", "the image scan flags a floating base image tag"]),
    "root": (d_root, ["the container runs as root", "the runtime image switches to `USER root`"]),
    "no-user": (d_no_user, ["the image has no USER instruction, so the process runs as root", "the security scan says the container runs as root (no USER)"]),
    "apt-clean": (d_apt_clean, ["the image is bloated by the apt package lists", "apt lists are left in the image layer"]),
    "apt-recs": (d_apt_recs, ["apt pulls in recommended packages and the image keeps growing", "`apt-get install` is missing --no-install-recommends"]),
    "apt-split": (d_apt_split, ["`apt-get install` fails now and then with 404 because of a stale cached `apt-get update` layer", "package installs break after the base image moves on (update is in its own layer)"]),
    "apk": (d_apk, ["apk leaves its index cache in the image", "`apk add` is used without --no-cache"]),
    "copy-order": (d_copy_order, ["every code change reinstalls all dependencies (the build cache is useless)", "docker build never reuses the dependency layer"]),
    "shell-cmd": (d_shell_cmd, ["the app does not receive SIGTERM on `docker stop` (CMD is in shell form)", "`docker stop` takes 10 seconds and kills the app: the CMD is a shell string"]),
    "add": (d_add, ["the Dockerfile uses ADD where COPY is meant", "the linter complains about ADD for local files"]),
    "no-health": (d_no_health, ["the container has no HEALTHCHECK", "orchestration can't tell whether the app is healthy (no HEALTHCHECK)"]),
    "cd": (d_cd, ["the linter complains about `cd` in a RUN", "a build step uses `cd` instead of WORKDIR"]),
    "workdir-rel": (d_workdir_rel, ["a WORKDIR is relative", "the linter flags a relative WORKDIR"]),
    "build-in-final": (d_build_in_final, ["the runtime image contains the build tooling", "the final image still builds the application (compiler and sources shipped to production)"]),
    "env-secret": (d_env_secret, ["a secret is baked into the image through ENV", "`docker history` shows a password in an ENV line"]),
    "pip": (d_pip, ["pip leaves its download cache in the image", "`pip install` without --no-cache-dir"]),
    "npm": (d_npm, ["installs are not reproducible: the build uses `npm install`", "builds drift because lockfile is not enforced (`npm install`)"]),
    "ignore": (d_ignore, [".dockerignore misses entries, so the build context is huge and leaks files", "the build context contains things that should be ignored"]),
    "no-expose": (d_no_expose, ["the image does not EXPOSE its port", "EXPOSE is missing from the final stage"]),
    "continuation": (d_continuation, ["the build fails with `unknown instruction: &&`", "docker build stops at a line starting with `&&`"]),
}


def build(rng, i):
    p = PROJECTS[PLAN[i]["proj"]] if "proj" in PLAN[i] else PROJECTS[i % len(PROJECTS)]
    m = model_for(p, rng)
    rules = {k: p[k] for k in ("lang", "build_cmd", "port", "cmd", "runtime_repos", "manifests", "install_re", "toolchain", "ignore")}
    rules["entrypoint"] = p["entrypoint"]
    return m, {"p": p, "rules": rules}


def docs(model, ctx):
    p, r = ctx["p"], ctx["rules"]
    md = dd(f'''
        # Image rules for {p["name"]}

        The `Dockerfile` and `.dockerignore` are checked mechanically (the Dockerfile is parsed into stages and instructions; backslash continuations are joined).

        1. **Stages.** At least two stages: a build stage and a runtime stage. The final stage is based on {" or ".join("`" + x + "`" for x in r["runtime_repos"])}; `{r["build_cmd"]}` runs in the build stage and not in the final stage.
           The final `CMD` stays `{json.dumps(r["cmd"])}`{"; the `ENTRYPOINT` stays " + "`" + json.dumps(r["entrypoint"]) + "`" if r["entrypoint"] else ""}; the final stage exposes port {r["port"]}.
        2. **Pinned bases.** Every `FROM` of an external image has a version tag (`latest` and a missing tag are not allowed).
        3. **Non-root.** The final stage has a `USER` that is not root (not `root`, not `0`), set before `CMD`/`ENTRYPOINT`.
        4. **Package managers.** A `RUN` with `apt-get install` also runs `apt-get update` before it, uses `--no-install-recommends`, and ends by removing `/var/lib/apt/lists`, all in the same `RUN`;
           `apk add` uses `--no-cache`; no `cd` in `RUN` (use `WORKDIR`); {"`pip install` uses `--no-cache-dir`" if r["lang"] == "python" else "`npm install` is not allowed (`npm ci`)" if r["lang"] == "node" else "Go modules are fetched with `go mod download` before the sources are copied"}.
        5. **Layer order.** In a stage that installs dependencies ({", ".join("`" + m + "`" for m in r["manifests"])}), those files are copied (alone) before the install step, and the sources (`COPY . .`) come after it.
        6. **Forms.** `CMD`, `ENTRYPOINT` and the `HEALTHCHECK` command use the exec (JSON array) form. `ADD` is only for URLs and tar archives; local files use `COPY`. `WORKDIR` is absolute.
        7. **Secrets.** No `ENV`/`ARG` whose name contains PASSWORD, SECRET, TOKEN or KEY has a literal value.
        8. **Health.** The final stage has exactly one `HEALTHCHECK --interval=... CMD [...]`.
        9. **Runtime stage.** It does not run build tooling (`{r["toolchain"]}` in a `RUN`).
        10. **.dockerignore** has a line for each of: {", ".join("`" + e + "`" for e in r["ignore"])}.
    ''')
    return {"IMAGE_RULES.md": md, "README.md": f"# {p['name']}\n\nContainer image of {p['what']} ({p['lang']}). Only `Dockerfile` and `.dockerignore` matter here; rules: `IMAGE_RULES.md`.\n"}


def hidden(model, ctx):
    return {"tests/rules.json": json.dumps(ctx["rules"], indent=1) + "\n"}


def prompt(rng, ctx, texts, vague):
    p = ctx["p"]
    return K.fix_prompt(rng, "Dockerfile", f"container build of {p['name']}, {p['what']}", texts, "IMAGE_RULES.md", vague, [
        f"The `Dockerfile` (and `.dockerignore`) of {p['name']} fail the image review described in `IMAGE_RULES.md`. Fix them without changing what the image builds and runs.",
        f"{p['name']}'s image doesn't pass our container policy (`IMAGE_RULES.md`). Make `Dockerfile` and `.dockerignore` compliant; the application, its port and its start command stay as they are.",
    ], tail=" Keep the application, its start command and port as they are.")


def wrong(model, ctx):
    w1 = copy.deepcopy(model)
    f = w1["stages"][-1]
    f["ins"] = [x for x in f["ins"] if x[0] != "CMD"] + [["CMD", json.dumps(["sh", "-c", "run"])]]
    w2 = copy.deepcopy(model)
    w2["stages"] = w2["stages"][1:]
    return [render(w1, ctx), render(w2, ctx)]


PLAN = [
    {"keys": ["latest"], "d": 1, "proj": 0}, {"keys": ["root"], "d": 1, "proj": 1}, {"keys": ["copy-order"], "d": 2, "proj": 2}, {"keys": ["shell-cmd", "no-health"], "proj": 3}, {"keys": ["apt-clean", "apt-recs"], "proj": 0},
    {"keys": ["apt-split"], "d": 3, "proj": 3}, {"keys": ["npm", "ignore"], "proj": 1}, {"keys": ["build-in-final", "add"], "proj": 2}, {"keys": ["env-secret", "no-user", "cd"], "proj": 0},
    {"keys": ["continuation", "pip"], "proj": 3}, {"keys": ["apk", "workdir-rel", "no-expose"], "proj": 1}, {"keys": ["latest", "copy-order", "root", "env-secret"], "proj": 2}, {"keys": ["apt-split", "shell-cmd", "ignore", "no-health", "cd"], "proj": 0, "vague": True, "d": 5},
    {"keys": ["build-in-final", "npm", "apk", "latest", "no-user"], "proj": 1, "vague": True, "d": 5}, {"keys": ["no-expose"], "d": 1, "proj": 3}, {"keys": ["add", "workdir-rel"], "d": 2, "proj": 0},
]


@family("devops-dockerfile-hygiene", category="devops", lang="text", kind="fix", n=len(PLAN),
        summary="repair Dockerfiles and .dockerignore against a parsed-instruction policy: multi-stage, pinned bases, non-root, apt hygiene, layer order, exec forms, health checks")
def dockerfile_hygiene(rng, n):
    return K.fix_tasks(rng, n, prefix="docker", plan=PLAN, build=build, render=render, defects=DEFECTS, docs=docs, hidden=hidden, check=CHECK_DOCKER, prompt=prompt, wrong=wrong,
                       tags=["docker", "dockerfile", "image"])
