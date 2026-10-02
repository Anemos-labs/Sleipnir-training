"""DevOps tasks: GitHub-Actions-style CI workflows with a policy validator (job graph, matrices, caching, pinning, permissions)."""
import copy
from dataclasses import dataclass

from fx import dd, family
from generators.devops import _dokit as K
from generators.devops import _yamlw as Y

CHECK_CI = r'''
from dolib import *

R = json.load(open("tests/rules.json", encoding="utf-8"))
PATH = R["path"]
wf = yaml_one(PATH)
rep = Report()
rules = R["rules"]
jobs = wf.get("jobs")
if not isinstance(jobs, dict) or not jobs:
    die(f"{PATH} defines no jobs")


def needs_of(j):
    return [str(x) for x in as_list(jobs[j].get("needs"))] if isinstance(jobs[j], dict) else []


def closure(j):
    out, stack = set(), list(needs_of(j))
    while stack:
        n = stack.pop()
        if n in out or n not in jobs:
            continue
        out.add(n)
        stack.extend(needs_of(n))
    return out


def steps_of(j):
    return [s for s in as_list(jobs[j].get("steps")) if isinstance(s, dict)]


def expand(m):
    m = dict(m)
    inc, exc = as_list(m.pop("include", None)), as_list(m.pop("exclude", None))
    axes = {k: as_list(v) for k, v in m.items()}
    combos = [dict()]
    for k, vs in axes.items():
        combos = [dict(c, **{k: v}) for c in combos for v in vs]
    combos = [c for c in combos if not any(all(k in c and c[k] == v for k, v in e.items()) for e in exc)]
    for i in inc:
        base = {k: v for k, v in i.items() if k in axes}
        hit = [c for c in combos if base and all(c[k] == v for k, v in base.items())]
        if hit:
            for c in hit:
                c.update({k: v for k, v in i.items() if k not in axes})
        else:
            combos.append(dict(i))
    return combos


# --- the work must be preserved
for j in R["jobs"]:
    if not rep.check(j in jobs and isinstance(jobs[j], dict), f"job {j!r} is missing"):
        continue
    runs = [str(s.get("run", "")) for s in steps_of(j)]
    pos = 0
    for cmd in R["runs"].get(j, []):
        idx = next((i for i in range(pos, len(runs)) if cmd in runs[i]), None)
        if idx is None:
            rep.check(False, f"job {j!r} no longer runs `{cmd}` (or runs it out of order)")
        else:
            pos = idx + 1
if R.get("exact_jobs"):
    rep.check(set(jobs) == set(R["jobs"]), f"the workflow must have exactly the jobs {sorted(R['jobs'])}")

# --- job graph
if rules.get("graph"):
    for j in jobs:
        for n in needs_of(j):
            rep.check(n in jobs, f"job {j!r} needs {n!r}, which is not a job of this workflow")
    color = {}

    def dfs(j):
        color[j] = 1
        for n in needs_of(j):
            if n not in jobs:
                continue
            if color.get(n) == 1:
                return True
            if n not in color and dfs(n):
                return True
        color[j] = 2
        return False
    cyc = any(dfs(j) for j in jobs if j not in color)
    rep.check(not cyc, "the `needs` graph contains a cycle")
    if not cyc:
        for a, b in rules.get("order", []):
            if a in jobs and b in jobs:
                rep.check(a in closure(b), f"job {b!r} must run after {a!r} (directly or through other jobs)")

# --- matrices
for j, spec in rules.get("matrix", {}).items():
    if j not in jobs:
        continue
    strat = jobs[j].get("strategy") if isinstance(jobs[j], dict) else None
    m = strat.get("matrix") if isinstance(strat, dict) else None
    if not rep.check(isinstance(m, dict), f"job {j!r} has no strategy.matrix"):
        continue
    for k, v in m.items():
        for x in as_list(v) if k not in ("include", "exclude") else []:
            rep.check(not isinstance(x, float), f"job {j!r}: matrix value {x!r} of {k!r} is a float; quote version numbers such as \"3.10\"")
    combos = expand(m)
    if "count" in spec:
        rep.check(len(combos) == spec["count"], f"job {j!r}: the matrix expands to {len(combos)} combinations, expected {spec['count']}")
    for f in spec.get("forbid", []):
        rep.check(not any(all(c.get(k) == v for k, v in f.items()) for c in combos), f"job {j!r}: the combination {f} must not run")
    for f in spec.get("require", []):
        rep.check(any(all(c.get(k) == v for k, v in f.items()) for c in combos), f"job {j!r}: the combination {f} must run")

# --- caching
if "cache" in rules:
    c = rules["cache"]
    for j in c["jobs"]:
        if j not in jobs:
            continue
        cs = [s for s in steps_of(j) if str(s.get("uses", "")).startswith("actions/cache@")]
        if not rep.check(cs, f"job {j!r} has no actions/cache step"):
            continue
        w = cs[0].get("with") or {}
        rep.check(bool(w.get("path")), f"job {j!r}: the cache step needs a `path`")
        key = str(w.get("key", ""))
        rep.check(f"hashFiles('{c['lock']}')" in key or f'hashFiles("{c["lock"]}")' in key, f"job {j!r}: the cache key must include hashFiles('{c['lock']}') (got {key!r})")

# --- pinned actions
if rules.get("pinned"):
    for j in jobs:
        for s in steps_of(j):
            u = s.get("uses")
            if u is None or str(u).startswith("./"):
                continue
            ok = re.match(r"^[\w.-]+/[\w.-]+(/[\w./-]+)?@(v\d+(\.\d+){0,2}|[0-9a-f]{40})$", str(u))
            rep.check(ok, f"job {j!r}: `uses: {u}` is not pinned to a version tag or commit SHA")

# --- permissions
if rules.get("permissions"):
    p = wf.get("permissions")
    if rep.check(isinstance(p, dict) and p, "the workflow needs a top-level `permissions:` mapping"):
        rep.check(p.get("contents") == "read", "top-level permissions must grant `contents: read`")
        rep.check(all(v in ("read", "none") for v in p.values()), "top-level permissions must only grant read (or none)")
    for j in jobs:
        jp = jobs[j].get("permissions") if isinstance(jobs[j], dict) else None
        if jp is not None:
            rep.check(isinstance(jp, dict) and all(v in ("read", "none") for v in jp.values()), f"job {j!r} must not grant write permissions")

# --- timeouts
if "timeouts" in rules:
    for j in jobs:
        t = jobs[j].get("timeout-minutes") if isinstance(jobs[j], dict) else None
        rep.check(isinstance(t, int) and not isinstance(t, bool) and 1 <= t <= rules["timeouts"], f"job {j!r}: `timeout-minutes` must be an integer between 1 and {rules['timeouts']}")

# --- deploy guard
if "deploy" in rules:
    d = rules["deploy"]
    j = d["job"]
    if j in jobs:
        rep.check("refs/heads/main" in str(jobs[j].get("if", "")), f"job {j!r} must only run for the main branch (`if:` mentioning refs/heads/main)")
        env = jobs[j].get("environment")
        name = env.get("name") if isinstance(env, dict) else env
        rep.check(name == d["environment"], f"job {j!r} must declare environment {d['environment']!r}")

# --- artifacts
if rules.get("artifacts"):
    for j in jobs:
        for s in steps_of(j):
            if str(s.get("uses", "")).startswith("actions/download-artifact@"):
                name = (s.get("with") or {}).get("name")
                if not rep.check(name, f"job {j!r}: a download-artifact step must say which artifact it wants (`name`)"):
                    continue
                ups = [(s2.get("with") or {}).get("name") for j2 in closure(j) if j2 in jobs for s2 in steps_of(j2) if str(s2.get("uses", "")).startswith("actions/upload-artifact@")]
                rep.check(name in ups, f"job {j!r} downloads artifact {name!r}, but no job it depends on uploads it")

# --- secrets
if "secrets" in rules:
    allowed = set(rules["secrets"])

    def walk(o, path, j):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, path + [str(k)], j)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, path + [str(i)], j)
        elif isinstance(o, str) and "secrets." in o:
            where_ok = j in allowed and "env" in path and "run" not in path
            rep.check(where_ok, f"a secret is used in {'/'.join(path)}: secrets may only appear in `env:` of {sorted(allowed)}, never in scripts")
    for j in jobs:
        walk(jobs[j], ["jobs", j], j)
    walk({k: v for k, v in wf.items() if k != "jobs"}, [], None)

# --- triggers
if "triggers" in rules:
    on = wf.get("on", wf.get("true"))
    ev = {}
    if isinstance(on, str):
        ev = {on: None}
    elif isinstance(on, list):
        ev = {str(x): None for x in on}
    elif isinstance(on, dict):
        ev = on
    for e in rules["triggers"]:
        rep.check(e in ev, f"the workflow must run on `{e}`")
    if "push" in ev and isinstance(ev["push"], dict) and ev["push"].get("branches"):
        rep.check("main" in as_list(ev["push"]["branches"]), "pushes to `main` must run the workflow")

# --- concurrency
if rules.get("concurrency"):
    c = wf.get("concurrency")
    if rep.check(isinstance(c, dict), "the workflow needs a top-level `concurrency:` mapping"):
        rep.check("github.ref" in str(c.get("group", "")), "concurrency.group must contain github.ref")
        rep.check(c.get("cancel-in-progress") is True, "concurrency.cancel-in-progress must be true")

# --- runners
for j in jobs:
    ro = jobs[j].get("runs-on") if isinstance(jobs[j], dict) else None
    if not rep.check(ro, f"job {j!r} has no runs-on"):
        continue
    for m_ in re.findall(r"matrix\.([A-Za-z_][\w-]*)", str(ro)):
        axes = ((jobs[j].get("strategy") or {}).get("matrix") or {})
        rep.check(m_ in axes, f"job {j!r}: runs-on refers to matrix.{m_}, which the matrix does not define")

rep.finish()
'''


@dataclass
class Proj:
    name: str
    lang: str
    lock: str
    cache_path: str
    install: str
    lint: str
    test: str
    build: str
    artifact_path: str
    axis: str
    versions: list
    setup_uses: str
    setup_with: str
    deploy: str


PROJECTS = [
    Proj("tidewatch", "node", "package-lock.json", "~/.npm", "npm ci", "npm run lint", "npm test", "npm run build", "dist/", "node", ["18", "20", "22"], "actions/setup-node@v4", "node-version", "./scripts/deploy.sh dist"),
    Proj("lumen-api", "python", "requirements.lock", "~/.cache/pip", "pip install -r requirements.lock", "python -m pyflakes src", "python -m unittest discover -s tests", "python -m build", "dist/", "python", ["3.9", "3.10", "3.11", "3.12"], "actions/setup-python@v5", "python-version", "./scripts/publish.sh dist"),
    Proj("quarry-cli", "go", "go.sum", "~/go/pkg/mod", "go mod download", "go vet ./...", "go test ./...", "go build -o bin/quarry ./cmd/quarry", "bin/", "go", ["1.22", "1.23"], "actions/setup-go@v5", "go-version", "./scripts/release.sh bin/quarry"),
    Proj("kelp-sync", "rust", "Cargo.lock", "~/.cargo/registry", "cargo fetch --locked", "cargo clippy --all-targets", "cargo test --locked", "cargo build --release --locked", "target/release/", "toolchain", ["stable", "beta"], "actions-rust-lang/setup-rust-toolchain@v1", "toolchain", "./ci/ship.sh target/release/kelp-sync"),
    Proj("harbor-ledger", "java", "gradle.lockfile", "~/.gradle/caches", "./gradlew dependencies --write-locks", "./gradlew check -x test", "./gradlew test", "./gradlew assemble", "build/libs/", "java", ["17", "21"], "actions/setup-java@v4", "java-version", "./deploy/push.sh build/libs"),
    Proj("moth-notes", "node", "pnpm-lock.yaml", "~/.local/share/pnpm/store", "pnpm install --frozen-lockfile", "pnpm lint", "pnpm test", "pnpm build", "out/", "node", ["20", "22"], "actions/setup-node@v4", "node-version", "./bin/upload.sh out"),
]
OSES = ["ubuntu-latest", "macos-latest", "windows-latest"]
SEC = "DEPLOY_TOKEN"


def build_model(rng, p: Proj) -> dict:
    chk = {"uses": "actions/checkout@v4"}
    ver_ref = f"${{{{ matrix.{p.axis} }}}}"
    cache = {"name": "Cache dependencies", "uses": "actions/cache@v4", "with": {"path": p.cache_path, "key": f"${{{{ runner.os }}}}-{p.lang}-${{{{ hashFiles('{p.lock}') }}}}",
                                                                          "restore-keys": f"${{{{ runner.os }}}}-{p.lang}-"}}
    oses = rng.sample(OSES, rng.choice([2, 3]))
    vers = p.versions
    excl = {"os": oses[-1], p.axis: vers[0]}
    setup = {"uses": p.setup_uses, "with": {p.setup_with: ver_ref}}
    wf = {
        "name": f"{p.name} ci",
        "on": {"push": {"branches": ["main"]}, "pull_request": None},
        "permissions": {"contents": "read"},
        "concurrency": {"group": "ci-${{ github.ref }}", "cancel-in-progress": True},
        "jobs": {
            "lint": {"runs-on": "ubuntu-latest", "timeout-minutes": 10,
                     "steps": [chk, copy.deepcopy(cache), {"name": "Install", "run": p.install}, {"name": "Lint", "run": p.lint}]},
            "test": {"needs": ["lint"], "runs-on": "${{ matrix.os }}", "timeout-minutes": 25,
                     "strategy": {"fail-fast": False, "matrix": {"os": oses, p.axis: list(vers), "exclude": [excl]}},
                     "steps": [chk, copy.deepcopy(cache), setup, {"name": "Install", "run": p.install}, {"name": "Test", "run": p.test}]},
            "build": {"needs": ["test"], "runs-on": "ubuntu-latest", "timeout-minutes": 15,
                      "steps": [chk, copy.deepcopy(cache), {"name": "Install", "run": p.install}, {"name": "Build", "run": p.build},
                                {"name": "Keep the build", "uses": "actions/upload-artifact@v4", "with": {"name": "release-files", "path": p.artifact_path}}]},
            "deploy": {"needs": ["build"], "if": "github.ref == 'refs/heads/main'", "runs-on": "ubuntu-latest", "environment": "production", "timeout-minutes": 10,
                       "env": {SEC: f"${{{{ secrets.{SEC} }}}}"},
                       "steps": [{"uses": "actions/download-artifact@v4", "with": {"name": "release-files", "path": p.artifact_path}}, {"name": "Deploy", "run": p.deploy}]},
        },
    }
    rules = {
        "path": ".github/workflows/ci.yml",
        "jobs": ["lint", "test", "build", "deploy"],
        "runs": {"lint": [p.lint], "test": [p.test], "build": [p.build], "deploy": [p.deploy]},
        "rules": {
            "graph": True, "order": [["lint", "test"], ["test", "build"], ["build", "deploy"]],
            "matrix": {"test": {"count": len(oses) * len(vers) - 1, "forbid": [excl], "require": [{"os": oses[0], p.axis: vers[-1]}]}},
            "cache": {"jobs": ["lint", "test", "build"], "lock": p.lock}, "pinned": True, "permissions": True, "timeouts": 30,
            "deploy": {"job": "deploy", "environment": "production"}, "artifacts": True, "secrets": ["deploy"],
            "triggers": ["push", "pull_request"], "concurrency": True,
        },
    }
    return wf, rules


# ---------------------------------------------------------------------------------------------------------------- defects


def d_needs_typo(wf, p, rng):
    j = rng.choice(["test", "build", "deploy"])
    old = wf["jobs"][j]["needs"][0]
    bad = old[:-1] + rng.choice(["s", "x"]) if rng.random() < 0.5 else old.upper()
    wf["jobs"][j]["needs"] = [bad]
    return {"job": j, "bad": bad}


def d_cycle(wf, p, rng):
    wf["jobs"]["lint"]["needs"] = ["deploy"]
    return {}


def d_matrix_exclude(wf, p, rng):
    ex = wf["jobs"]["test"]["strategy"]["matrix"]["exclude"][0]
    wf["jobs"]["test"]["strategy"]["matrix"]["exclude"] = [{"os": ex["os"], "version": ex[p.axis]}]
    return {"os": ex["os"], "ver": ex[p.axis]}


def d_matrix_float(wf, p, rng):
    if p.lang != "python":
        raise KeyError
    m = wf["jobs"]["test"]["strategy"]["matrix"]
    m[p.axis] = [Y.Raw(v, float(v)) for v in m[p.axis]]
    return {}


def d_cache_key(wf, p, rng):
    j = rng.choice(["lint", "test", "build"])
    st = [s for s in wf["jobs"][j]["steps"] if str(s.get("uses", "")).startswith("actions/cache")][0]
    if rng.random() < 0.5:
        st["with"]["key"] = f"${{{{ runner.os }}}}-{p.lang}-deps"
    else:
        st["with"]["key"] = f"${{{{ runner.os }}}}-{p.lang}-${{{{ hashFiles('**/*.md') }}}}"
    return {"job": j}


def d_unpinned(wf, p, rng):
    j = rng.choice(["lint", "build"])
    wf["jobs"][j]["steps"][0] = {"uses": rng.choice(["actions/checkout@main", "actions/checkout@master", "actions/checkout"])}
    return {"job": j}


def d_permissions(wf, p, rng):
    if rng.random() < 0.5:
        del wf["permissions"]
    else:
        wf["permissions"] = {"contents": "write"}
    return {}


def d_timeout(wf, p, rng):
    j = rng.choice(["lint", "test", "build", "deploy"])
    if rng.random() < 0.5:
        del wf["jobs"][j]["timeout-minutes"]
    else:
        wf["jobs"][j]["timeout-minutes"] = 360
    return {"job": j}


def d_deploy_unguarded(wf, p, rng):
    del wf["jobs"]["deploy"]["if"]
    return {}


def d_artifact_name(wf, p, rng):
    wf["jobs"]["deploy"]["steps"][0]["with"]["name"] = rng.choice(["dist", "release", "release_files"])
    return {}


def d_secret_echo(wf, p, rng):
    steps = wf["jobs"]["deploy"]["steps"]
    steps[-1] = {"name": "Deploy", "run": f"{p.deploy} --token ${{{{ secrets.{SEC} }}}}"}
    return {}


def d_no_pr(wf, p, rng):
    wf["on"] = {"push": {"branches": ["main"]}}
    return {}


def d_no_concurrency(wf, p, rng):
    del wf["concurrency"]
    return {}


DEFECTS = {
    "needs-typo": (d_needs_typo, ["the {job} job refuses to start; GitHub complains that it needs `{bad}`", "validation error on `{job}`: it waits for a job called `{bad}`", "the workflow doesn't even load (something about `needs` in `{job}`)"]),
    "cycle": (d_cycle, ["GitHub says there is a circular dependency between the jobs", "the workflow won't start: a dependency cycle between jobs was reported"]),
    "matrix-exclude": (d_matrix_exclude, ["the {os} + {ver} combination still runs in the test matrix although we dropped it", "we dropped {os} on {ver} but the test job keeps launching it"]),
    "matrix-float": (d_matrix_float, ["the test job claims to run Python 3.10 but the log says 3.1", "CI never tests the Python 3.10 we think it does"]),
    "cache-key": (d_cache_key, ["the dependency cache in `{job}` is never refreshed when the lock file changes", "cache hits in `{job}` are stale: the key doesn't change with the lock file"]),
    "unpinned": (d_unpinned, ["the security audit complains about an unpinned action in `{job}`", "somebody left a floating action reference in `{job}`"]),
    "permissions": (d_permissions, ["the GITHUB_TOKEN of this workflow is not read-only", "the audit says the workflow has no explicit read-only permissions"]),
    "timeout": (d_timeout, ["`{job}` has no sane timeout (a hung run kept a runner busy for hours)", "the `{job}` job can run forever"]),
    "deploy-unguarded": (d_deploy_unguarded, ["the deploy job ran for a pull request", "deploys are not restricted to the main branch"]),
    "artifact-name": (d_artifact_name, ["deploy can't find the build files", "the deploy job fails downloading the artifact"]),
    "secret-echo": (d_secret_echo, ["the deploy token now appears in a command line in the logs", "somebody interpolated a secret straight into a `run:` script"]),
    "no-pr": (d_no_pr, ["pull requests don't trigger CI", "PRs get no checks at all"]),
    "no-concurrency": (d_no_concurrency, ["old runs for the same branch are not cancelled when a new push arrives", "runs pile up on busy branches"]),
}

STYLES = ["list", "para", "terse"]


def prompt_fix(rng, p, applied, vague):
    texts = []
    for key, info in applied:
        texts.append(rng.choice(DEFECTS[key][1]).format(**{"os": "", "ver": "", "job": "", "bad": "", **info}))
    pol = "`CI_POLICY.md` describes what the workflow must satisfy"
    if vague:
        return rng.choice([
            f"The policy audit for {p.name} (`CI_POLICY.md`) fails on `.github/workflows/ci.yml` and I don't have time to dig. Please make the workflow compliant without changing what it builds, tests and deploys.",
            f"`.github/workflows/ci.yml` of {p.name} doesn't pass our CI policy (`CI_POLICY.md`). Find what is wrong and fix it; keep every job and command.",
        ])
    style = rng.choice(STYLES)
    if style == "list":
        return f"The CI workflow of {p.name} (`.github/workflows/ci.yml`) has problems:\n" + "\n".join(f"- {t}" for t in texts) + f"\n\nPlease fix them. {pol}; keep all jobs and the commands they run."
    if style == "para":
        return f"Reports from the team about `.github/workflows/ci.yml`: " + "; ".join(texts) + f". Can you sort the workflow out? {pol}."
    return f"ci.yml: " + "; ".join(texts) + f". Fix it ({pol[0].lower() + pol[1:]})."


def fmt(c):
    return "`" + ", ".join(f"{k}={v}" for k, v in c.items()) + "`"


def policy_doc(p, rules, author=None):
    r = rules["rules"]
    lines = [f"# CI policy for {p.name}", "",
             "`.github/workflows/ci.yml` is checked mechanically against the rules below (YAML is read with the YAML 1.1 rules of Ruby's Psych: the key `on` is fine, but beware of unquoted values that are really numbers).", ""]
    n = 1

    def rule(t):
        nonlocal n
        lines.append(f"{n}. {t}")
        n += 1
    rule(f"**Keep the work.** The jobs {', '.join('`' + j + '`' for j in rules['jobs'])} exist, and each still runs its commands: " +
         "; ".join(f"`{j}`: " + ", ".join(f"`{c}`" for c in cmds) for j, cmds in rules["runs"].items()) + ". A job's commands appear in its steps in the order listed.")
    rule("**Job graph.** Every `needs` entry names an existing job and the graph has no cycle. Ordering that must hold (directly or through a chain of `needs`): " + "; ".join(f"`{b}` after `{a}`" for a, b in r["order"]) + ".")
    for j, m in r["matrix"].items():
        rule(f"**Matrix of `{j}`.** After applying `exclude` and `include` the matrix expands to exactly {m['count']} combinations; the combination {fmt(m['forbid'][0])} must not run and {fmt(m['require'][0])} must. "
             "Expansion: the cross product of the list-valued keys, minus every combination matched by an `exclude` entry (all keys of the entry equal), then each `include` entry whose axis keys all match an existing combination extends those combinations, otherwise it adds a new one. "
             "Matrix values must not be floats: quote versions like `\"3.10\"` (YAML reads an unquoted 3.10 as the number 3.1).")
    rule(f"**Caching.** The jobs {', '.join('`' + j + '`' for j in r['cache']['jobs'])} each have an `actions/cache` step with a `path` and a `key` that contains `hashFiles('{r['cache']['lock']}')`.")
    rule("**Pinned actions.** Every `uses:` (except local `./...` actions) ends in `@vN`, `@vN.M`, `@vN.M.P` or a 40-character commit SHA. `@main`, `@master` or no ref at all are not allowed.")
    rule("**Least privilege.** The workflow has a top-level `permissions:` mapping that grants `contents: read`, and every value (there and in jobs) is `read` or `none`.")
    rule(f"**Timeouts.** Every job sets an integer `timeout-minutes` between 1 and {r['timeouts']}.")
    rule("**Deploy.** The `deploy` job only runs for the main branch (its `if:` mentions `refs/heads/main`) and declares `environment: production`.")
    rule("**Artifacts.** Every `actions/download-artifact` step names the artifact it wants, and an `actions/upload-artifact` step with that name exists in a job that this job (transitively) needs.")
    rule("**Secrets.** `secrets.*` expressions may only appear inside an `env:` mapping of the `deploy` job, never inside `run:` scripts.")
    rule("**Triggers.** The workflow runs on `push` (to `main`) and on `pull_request`.")
    rule("**Concurrency.** A top-level `concurrency:` with a `group` containing `github.ref` and `cancel-in-progress: true`.")
    rule("**Runners.** Every job has `runs-on`; an expression `${{ matrix.X }}` there must refer to an axis the matrix defines.")
    if author:
        lines += ["", author]
    return "\n".join(lines) + "\n"


def readme(p):
    return dd(f'''
        # {p.name}

        A small {p.lang} project. The CI workflow lives in `.github/workflows/ci.yml`; the rules it has to follow are in
        `CI_POLICY.md`. Source files are omitted: only the workflow matters here.

        Jobs: `lint` -> `test` (matrix) -> `build` -> `deploy` (main branch only).
    ''')


def defect_plan():
    combos = [(["needs-typo"], False), (["cache-key"], False), (["unpinned", "permissions"], False), (["matrix-exclude"], False), (["cycle", "timeout"], False),
              (["deploy-unguarded", "artifact-name"], False), (["secret-echo", "no-concurrency"], False), (["matrix-float", "unpinned", "cache-key"], False),
              (["needs-typo", "matrix-exclude", "secret-echo", "no-pr"], False), (["cycle", "artifact-name", "timeout", "permissions", "unpinned"], True),
              (["no-pr", "deploy-unguarded", "cache-key", "timeout"], True)]
    return combos


def gen_tasks(rng, n):
    tasks = []
    combos = defect_plan()
    for i in range(n):
        if i >= len(combos):
            break
        keys, vague = combos[i]
        p = PROJECTS[i % len(PROJECTS)]
        if "matrix-float" in keys and p.lang != "python":
            p = PROJECTS[1]
        wf, rules = build_model(rng, p)
        good = Y.roundtrip(wf)
        bad = copy.deepcopy(wf)
        applied = []
        for k in keys:
            info = DEFECTS[k][0](bad, p, rng)
            applied.append((k, info))
        bad_text = Y.roundtrip(bad)
        d = {1: 2, 2: 3, 3: 4, 4: 4, 5: 5}[len(keys)]
        if len(keys) == 1 and keys[0] in ("unpinned", "permissions", "timeout", "no-pr"):
            d = 1
        start = {".github/workflows/ci.yml": bad_text, "CI_POLICY.md": policy_doc(p, rules), "README.md": readme(p)}
        sol = {".github/workflows/ci.yml": good}
        import json
        hidden = {"tests/rules.json": json.dumps(rules, indent=1) + "\n"}
        t = K.devops_task(f"{i + 1:02d}-" + "-".join(keys[:2]), d, prompt_fix(rng, p, applied, vague), start, sol, CHECK_CI, hidden, lang="text", kind="fix",
                          tags=["ci", "workflow", "yaml"], notes={"defects": keys, "project": p.name})
        wrong_wf = copy.deepcopy(wf)
        del wrong_wf["jobs"]["deploy"]
        wrong2 = copy.deepcopy(wf)
        wrong2["jobs"]["deploy"].pop("needs")
        tasks.append(K.finish(t, wrong=[{".github/workflows/ci.yml": Y.roundtrip(wrong_wf)}, {".github/workflows/ci.yml": Y.roundtrip(wrong2)}]))
    return tasks


@family("devops-ci-workflow", category="devops", lang="text", kind="fix", n=11,
        summary="repair GitHub-Actions-style workflows against a mechanical policy: job graph, matrix, cache key, pinning, permissions, deploy guards")
def ci_workflow(rng, n):
    return gen_tasks(rng, n)
