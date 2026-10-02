"""DevOps tasks: GitLab CI pipelines repaired against a mechanical policy (stages and needs, string variables, rules syntax, artifacts, caches, protected deploys, YAML traps)."""
import json

from fx import dd, family
from generators.devops import _dokit as K
from generators.devops import _yamlw as Y

CHECK_GITLAB = r'''
from dolib import *

R = json.load(open("tests/rules.json", encoding="utf-8"))
PATH = R["path"]
text = read(PATH)
doc = yaml_one(PATH)
rep = Report()

RESERVED = {"stages", "variables", "default", "include", "workflow", "image", "services", "cache", "before_script", "after_script"}
jobs = {k: v for k, v in doc.items() if k not in RESERVED and not k.startswith(".") and isinstance(v, dict)}
templates = {k: v for k, v in doc.items() if k.startswith(".") and isinstance(v, dict)}

# R1 the file keeps its shape
names = re.findall(r"^([A-Za-z0-9_.-]+):", text, re.M)
dups = sorted({n for n in names if names.count(n) > 1})
rep.check(not dups, f"top-level key(s) {dups} appear twice: the later definition silently replaces the earlier one")
rep.check(doc.get("stages") == R["stages"], f"`stages` must stay exactly {R['stages']}")
rep.check(set(jobs) == set(R["scripts"]), f"the pipeline must have exactly the jobs {sorted(R['scripts'])}")
for j, scr in R["scripts"].items():
    rep.check((jobs.get(j) or {}).get("script") == scr, f"job {j!r}: `script` must stay {scr!r}")
stages = doc.get("stages") if isinstance(doc.get("stages"), list) else []
order = {s: i for i, s in enumerate(stages)}


def stage_of(j):
    return jobs[j].get("stage", "test")


# R2 stages and scripts
for j, s in jobs.items():
    rep.check(stage_of(j) in order, f"job {j!r}: stage {stage_of(j)!r} is not one of the declared stages")
    sc = s.get("script")
    rep.check(isinstance(sc, list) and bool(sc) and all(isinstance(x, str) for x in sc), f"job {j!r}: `script` must be a non-empty list of strings (an unquoted command containing `: ` becomes a mapping)")

# R3 needs and dependencies
for j, s in jobs.items():
    mine = order.get(stage_of(j), -1)
    seen = []
    for n in as_list(s.get("needs")):
        name = n if isinstance(n, str) else (n.get("job") if isinstance(n, dict) else None)
        if not rep.check(name in jobs, f"job {j!r}: needs {name!r}, which is not a job"):
            continue
        rep.check(name != j and name not in seen, f"job {j!r}: needs lists {name!r} twice or itself")
        seen.append(name)
        rep.check(order.get(stage_of(name), 99) < mine, f"job {j!r} (stage {stage_of(j)}) needs {name!r} (stage {stage_of(name)}): a needed job must be in an earlier stage")
    for d in as_list(s.get("dependencies")):
        if not rep.check(d in jobs, f"job {j!r}: dependencies names {d!r}, which is not a job"):
            continue
        rep.check(order.get(stage_of(d), 99) < mine, f"job {j!r}: dependency {d!r} must be in an earlier stage")
        arts = jobs[d].get("artifacts")
        rep.check(isinstance(arts, dict) and bool(arts.get("paths")), f"job {j!r}: depends on {d!r}, which produces no artifacts")

# R4 variables
def check_vars(where, vs):
    if vs is None:
        return
    if not rep.check(isinstance(vs, dict), f"{where}: `variables` must be a mapping"):
        return
    for k, v in vs.items():
        if isinstance(v, dict):
            v = v.get("value")
        rep.check(isinstance(v, str), f"{where}: variable {k} must be a string (quote true/false and numbers), got {v!r}")
        rep.check(not re.search(r"TOKEN|PASSWORD|SECRET|PRIVATE_KEY", k), f"{where}: variable {k} looks like a secret; define it in the project's CI/CD settings, not in the file")

check_vars("top level", doc.get("variables"))
for j, s in jobs.items():
    check_vars(f"job {j!r}", s.get("variables"))

# R5 rules
COND_TERM = r"""\$[A-Za-z_][A-Za-z0-9_]*(?:\s*(?:==|!=|=~|!~)\s*(?:"[^"]*"|'[^']*'|/[^/]+/[a-z]*|null))?"""
COND = re.compile(rf"^{COND_TERM}(?:\s*(?:&&|\|\|)\s*{COND_TERM})*$")
for j, s in jobs.items():
    rep.check("only" not in s and "except" not in s, f"job {j!r}: `only`/`except` are not allowed, use `rules`")
    for r in as_list(s.get("rules")):
        if not rep.check(isinstance(r, dict), f"job {j!r}: every rules entry must be a mapping"):
            continue
        c = r.get("if")
        if c is not None:
            rep.check(isinstance(c, str) and COND.match(c.strip()), f"job {j!r}: rules `if: {c}` is not a valid expression (`$VAR`, optionally with ==, !=, =~ or !~ and a quoted string or /regex/)")
        rep.check(r.get("when") in (None, "on_success", "manual", "always", "never", "delayed"), f"job {j!r}: rules `when: {r.get('when')}` is not valid")

# R6 images, caches, artifacts, retry, coverage, extends
def check_image(where, im):
    if im is None:
        return
    name = im.get("name") if isinstance(im, dict) else im
    if not rep.check(isinstance(name, str), f"{where}: image must be a string"):
        return
    last = name.rsplit("/", 1)[-1]
    tag = last.split(":", 1)[1] if ":" in last else ("@" if "@" in name else "")
    rep.check(tag not in ("", "latest"), f"{where}: image {name!r} must carry an explicit version tag (not `latest`, not missing)")

check_image("default", (doc.get("default") or {}).get("image") if isinstance(doc.get("default"), dict) else None)
rep.check(isinstance(doc.get("default"), dict) and "image" in doc["default"] or all("image" in s for s in jobs.values()), "every job needs an image (set `default: image:` or one per job)")
for where, s in list(jobs.items()) + list(templates.items()):
    check_image(f"job {where!r}", s.get("image"))
    if "cache" in s:
        c = s["cache"]
        ok = isinstance(c, dict) and isinstance(c.get("key"), str) and isinstance(c.get("paths"), list) and bool(c["paths"])
        rep.check(ok, f"{where!r}: `cache` needs a `key` (string) and a non-empty `paths` list")
EXPIRE = re.compile(r"^\d+ (second|minute|hour|day|week)s?$|^never$")
for j, s in jobs.items():
    a = s.get("artifacts")
    if a is not None:
        rep.check(isinstance(a, dict) and isinstance(a.get("paths"), list) and bool(a["paths"]), f"job {j!r}: artifacts needs a `paths` list")
        if isinstance(a, dict):
            rep.check(isinstance(a.get("expire_in"), str) and EXPIRE.match(a["expire_in"]), f"job {j!r}: artifacts.expire_in must look like `1 week` (a number, a unit: seconds, minutes, hours, days, weeks) or `never`, got {a.get('expire_in')!r}")
    rt = s.get("retry")
    if rt is not None:
        m = rt.get("max") if isinstance(rt, dict) else rt
        rep.check(isinstance(m, int) and not isinstance(m, bool) and 0 <= m <= 2, f"job {j!r}: retry must be 0, 1 or 2 (got {m!r})")
    cov = s.get("coverage")
    if cov is not None:
        rep.check(isinstance(cov, str) and len(cov) > 2 and cov.startswith("/") and cov.endswith("/"), f"job {j!r}: coverage must be a regular expression enclosed in slashes, got {cov!r}")
    for e in as_list(s.get("extends")):
        rep.check(e in templates or e in jobs, f"job {j!r}: extends {e!r}, which does not exist")

# R7 deploys
for j, env in R["envs"].items():
    s = jobs.get(j) or {}
    e = s.get("environment")
    en = e.get("name") if isinstance(e, dict) else e
    rep.check(en == env, f"job {j!r}: environment must be {env!r} (got {en!r})")
prod = jobs.get(R["prod"]) or {}
rules = as_list(prod.get("rules"))
if rules:
    for r in rules:
        if isinstance(r, dict) and r.get("when") != "never":
            rep.check(r.get("when") == "manual", f"{R['prod']!r}: every rule that lets it run needs `when: manual`")
            rep.check(r.get("allow_failure") is False, f"{R['prod']!r}: a manual rule needs `allow_failure: false` (manual jobs are allowed to fail by default, which would let the pipeline go green without the deploy)")
else:
    rep.check(prod.get("when") == "manual" and prod.get("allow_failure") is False, f"{R['prod']!r} must be `when: manual` with `allow_failure: false`")

rep.finish()
'''

PROJECTS = [
    dict(name="reefcam", what="an underwater camera image service", image="python:3.12.4-slim", build="pip wheel --no-deps -w dist .", lint="ruff check src", test="pytest -q --cov=reefcam", cov=r"/TOTAL.*\s+(\d+%)$/", pkg="reefcam-${CI_COMMIT_SHORT_SHA}.tgz"),
    dict(name="ledgerline", what="a double-entry ledger daemon", image="golang:1.22.5-bookworm", build="go build -o dist/ledgerline ./cmd/ledgerline", lint="go vet ./...", test="go test -cover ./...", cov=r"/coverage: (\d+\.\d+)% of statements/", pkg="ledgerline-${CI_COMMIT_SHORT_SHA}.tgz"),
    dict(name="loomtrack", what="a textile order tracker", image="node:20.15.1-alpine", build="npm ci && npm run build", lint="npm run lint", test="npm test -- --coverage", cov=r"/All files[^|]*\|\s*([\d.]+)/", pkg="loomtrack-${CI_COMMIT_SHORT_SHA}.tgz"),
    dict(name="stonefold", what="a quarry inventory CLI", image="rust:1.79.0-slim", build="cargo build --release && cp target/release/stonefold dist/", lint="cargo clippy -- -D warnings", test="cargo test", cov=r"/(\d+\.\d+)% coverage/", pkg="stonefold-${CI_COMMIT_SHORT_SHA}.tgz"),
]


def build_model(rng, i):
    P = PROJECTS[i % len(PROJECTS)]
    mr = '$CI_PIPELINE_SOURCE == "merge_request_event"'
    main = '$CI_COMMIT_BRANCH == "main"'
    m = {
        "stages": ["build", "test", "package", "deploy"],
        "variables": {"APP_NAME": P["name"], "ARTIFACT_DIR": "dist", "FF_USE_FASTZIP": "true", "KEEP_DAYS": str(rng.choice([7, 14, 30]))},
        "default": {"image": P["image"]},
        ".cached": {"cache": {"key": "$CI_COMMIT_REF_SLUG", "paths": [".cache/"]}},
        "build": {"extends": ".cached", "stage": "build", "script": ["mkdir -p dist", P["build"]], "artifacts": {"paths": ["dist/"], "expire_in": "1 week"}},
        "lint": {"stage": "test", "script": [P["lint"]], "rules": [{"if": mr}, {"if": main}]},
        "unit": {"stage": "test", "needs": ["build"], "script": [P["test"]], "coverage": P["cov"], "retry": 1, "rules": [{"if": mr}, {"if": main}]},
        "package": {"stage": "package", "needs": ["build", "unit"], "dependencies": ["build"], "script": [f"tar -czf {P['pkg']} dist", "ls -l *.tgz"], "artifacts": {"paths": ["*.tgz"], "expire_in": "2 weeks"}, "rules": [{"if": main}, {"if": "$CI_COMMIT_TAG"}]},
        "deploy-staging": {"stage": "deploy", "needs": ["package"], "dependencies": ["package"], "environment": {"name": "staging", "url": f"https://staging.{P['name']}.example.test"}, "script": ["./scripts/deploy.sh staging", 'echo "Deploy finished: staging"'], "rules": [{"if": main}]},
        "deploy-prod": {"stage": "deploy", "needs": ["package"], "dependencies": ["package"], "environment": {"name": "production"}, "script": ["./scripts/deploy.sh production", 'echo "Deploy finished: production"'], "rules": [{"if": "$CI_COMMIT_TAG", "when": "manual", "allow_failure": False}]},
    }
    jobs = [k for k in m if k not in ("stages", "variables", "default", ".cached")]
    rules = {"path": ".gitlab-ci.yml", "stages": m["stages"], "scripts": {j: m[j]["script"] for j in jobs}, "envs": {"deploy-staging": "staging", "deploy-prod": "production"}, "prod": "deploy-prod"}
    return m, {"P": P, "rules": rules}


def render(model, ctx):
    return {".gitlab-ci.yml": Y.roundtrip(model)}


# ---------------------------------------------------------------------------------------------------- defects


def d_stage_typo(m, ctx, rng):
    j = rng.choice(["lint", "unit"])
    m[j]["stage"] = "tests"
    return {"a": j}


def d_needs_later(m, ctx, rng):
    m["unit"]["needs"] = ["build", "package"]
    return {}


def d_needs_missing(m, ctx, rng):
    m["package"]["needs"] = ["build", "unit-tests"]
    return {}


def d_dep_no_art(m, ctx, rng):
    m["package"]["dependencies"] = ["build", "lint"]
    return {}


def d_script_colon(m, ctx, rng):
    j = rng.choice(["deploy-staging", "deploy-prod"])
    env = "staging" if j == "deploy-staging" else "production"
    m[j]["script"][1] = Y.Raw(f"echo Deploy finished: {env}", {f"echo Deploy finished": env})
    return {"a": j}


def d_var_bool(m, ctx, rng):
    m["variables"]["FF_USE_FASTZIP"] = Y.Raw("true", True)
    if rng.random() < 0.5:
        m["variables"]["KEEP_DAYS"] = int(m["variables"]["KEEP_DAYS"])
    return {}


def d_rules_only(m, ctx, rng):
    m["lint"]["only"] = ["merge_requests", "main"]
    return {}


def d_rule_if(m, ctx, rng):
    j = rng.choice(["lint", "unit"])
    m[j]["rules"][1]["if"] = rng.choice(['$CI_COMMIT_BRANCH = "main"', "$CI_COMMIT_BRANCH == main", 'CI_COMMIT_BRANCH == "main"'])
    return {"a": j}


def d_expire(m, ctx, rng):
    j = rng.choice(["build", "package"])
    m[j]["artifacts"]["expire_in"] = rng.choice(["1 wk", "7d", "a week", "one day"])
    return {"a": j}


def d_image(m, ctx, rng):
    img = m["default"]["image"]
    m["default"]["image"] = img.split(":")[0] if rng.random() < 0.5 else img.split(":")[0] + ":latest"
    return {}


def d_manual(m, ctx, rng):
    m["deploy-prod"]["rules"][0].pop("allow_failure")
    return {}


def d_prod_auto(m, ctx, rng):
    m["deploy-prod"]["rules"][0].pop("when")
    return {}


def d_retry(m, ctx, rng):
    m["unit"]["retry"] = rng.choice([3, 5, 10])
    return {}


def d_extends(m, ctx, rng):
    m["build"]["extends"] = ".cashed"
    return {}


def d_secret(m, ctx, rng):
    m["variables"][rng.choice(["REGISTRY_TOKEN", "DEPLOY_PASSWORD"])] = rng.choice(["glpat-4kd9s8d2", "hunter2-prod"])
    return {}


def d_cache(m, ctx, rng):
    m[".cached"]["cache"].pop("key")
    return {}


def d_coverage(m, ctx, rng):
    cov = m["unit"]["coverage"]
    m["unit"]["coverage"] = cov.strip("/")
    return {}


def d_dup(m, ctx, rng):
    def post(files):
        files[".gitlab-ci.yml"] = files[".gitlab-ci.yml"].rstrip("\n") + "\n\nlint:\n  stage: test\n  script:\n    - echo temporary lint\n"
        return files
    return {"_post": post}


def d_indent(m, ctx, rng):
    def post(files):
        lines = files[".gitlab-ci.yml"].split("\n")
        idx = [i for i, l in enumerate(lines) if l.startswith("  stage:")]
        k = idx[len(idx) // 2]
        lines[k] = "   " + lines[k].lstrip()
        files[".gitlab-ci.yml"] = "\n".join(lines)
        try:
            Y.load_all(files[".gitlab-ci.yml"])
        except ValueError:
            return files
        raise RuntimeError("the indentation defect did not break the YAML")
    return {"_post": post}


def d_tab(m, ctx, rng):
    def post(files):
        lines = files[".gitlab-ci.yml"].split("\n")
        idx = [i for i, l in enumerate(lines) if l.startswith("  script:")]
        k = idx[1]
        lines[k] = "\t" + lines[k].lstrip()
        files[".gitlab-ci.yml"] = "\n".join(lines)
        return files
    return {"_post": post}


DEFECTS = {
    "stage-typo": (d_stage_typo, ["the pipeline editor says the `{a}` job uses a stage that does not exist", "`{a}` never runs: its stage name does not match any declared stage"]),
    "needs-later": (d_needs_later, ["GitLab refuses the pipeline: `unit` needs a job that runs in a later stage", "`unit` waits for `package`, which comes after it"]),
    "needs-missing": (d_needs_missing, ["the pipeline is invalid: `package` needs a job called `unit-tests`", "lint of the CI file: unknown job in `needs` of `package`"]),
    "dep-no-art": (d_dep_no_art, ["`package` depends on `lint`, which has no artifacts, and the job fails when it starts", "the `dependencies` of `package` point at a job without artifacts"]),
    "script-colon": (d_script_colon, ["the `{a}` job fails with `script config should be a string or a nested array of strings`", "an echo line in `{a}` is read as a key/value pair instead of a command"]),
    "var-bool": (d_var_bool, ["GitLab rejects the global variables: a value is a boolean or number instead of a string", "`variables:` contains values that are not strings"]),
    "rules-only": (d_rules_only, ["`lint` uses both `rules` and `only`", "the pipeline linter complains that `lint` mixes `rules` with `only`"]),
    "rule-if": (d_rule_if, ["the `rules: if:` expression of `{a}` does not parse", "`{a}` has a broken branch condition (the comparison is not valid)"]),
    "expire": (d_expire, ["the artifact lifetime of `{a}` is written in a form GitLab does not accept", "`expire_in` in `{a}` is not a valid duration"]),
    "image": (d_image, ["the default image is not pinned (every pipeline can pull something different)", "someone removed the version from the default image, runs are no longer reproducible"]),
    "manual": (d_manual, ["the manual production deploy can be skipped and the pipeline still turns green", "`deploy-prod` is manual but a skipped manual job does not block the pipeline"]),
    "prod-auto": (d_prod_auto, ["production gets deployed automatically on tags without anyone clicking", "`deploy-prod` is not manual any more"]),
    "retry": (d_retry, ["`unit` is retried far more often than GitLab allows", "the `retry` count of `unit` is rejected"]),
    "extends": (d_extends, ["`build` extends a template that does not exist (typo in the name)", "the pipeline fails with `unknown extends` for `build`"]),
    "secret": (d_secret, ["a token / password is committed in the `variables` of the CI file", "security found a literal credential in `.gitlab-ci.yml`"]),
    "cache": (d_cache, ["the shared cache template has no `key`, so every branch fights over one cache", "the `.cached` template lost its cache key"]),
    "coverage": (d_coverage, ["the coverage badge stays empty: the `coverage` regex is not accepted", "GitLab rejects the `coverage:` value of `unit`"]),
    "dup-job": (d_dup, ["there are two `lint` jobs in the file and the second silently wins", "a duplicated `lint` definition at the bottom overrides the real one"]),
    "indent": (d_indent, ["the CI file stopped parsing after the last edit (indentation)", "the pipeline editor shows a YAML syntax error"]),
    "tab": (d_tab, ["YAML error: found a tab character where indentation was expected", "the CI lint reports `found character that cannot start any token`"]),
}


# ---------------------------------------------------------------------------------------------------- docs


def docs(model, ctx):
    r, P = ctx["rules"], ctx["P"]
    rules_md = dd(f'''
        # Pipeline rules for {P["name"]}

        `.gitlab-ci.yml` is validated mechanically with the rules below. The YAML is read with the YAML 1.1 rules of Ruby's Psych
        (an unquoted `true` or `20` is a boolean or a number, not a string; an unquoted `echo a: b` is a mapping, not a string).

        1. **Keep the work.** The stages stay exactly {", ".join("`" + s + "`" for s in r["stages"])}; the jobs are exactly {", ".join("`" + j + "`" for j in r["scripts"])} and each keeps its `script` unchanged.
           No top-level key appears twice (YAML silently lets the later one win).
        2. **Stages and scripts.** Every job's `stage` (default `test`) is a declared stage. `script` is a non-empty list of strings.
        3. **Needs.** `needs` and `dependencies` name existing jobs of an **earlier** stage, without repeats or self-references; a job named in `dependencies` must produce `artifacts: paths`.
        4. **Variables.** Every variable value is a string (quote `"true"`, `"20"`). Names containing TOKEN, PASSWORD, SECRET or PRIVATE_KEY are never defined in the file (they come from the project settings).
        5. **Rules.** `only` and `except` are not used. Each `rules:` entry is a mapping; `if:` is `$VAR` alone or `$VAR` compared with `==`, `!=`, `=~` or `!~` to a quoted string or a `/regex/` (or `null`), combinable with `&&` and `||`; `when:` is one of
           `on_success`, `manual`, `always`, `never`, `delayed`.
        6. **Images and caches.** Every image (default or per job) has an explicit tag or digest, not `latest`. A `cache:` has a string `key` and a non-empty `paths` list. Every job has an image (through `default`).
        7. **Artifacts, retry, coverage, extends.** `artifacts` needs `paths` and an `expire_in` such as `1 week` (a number and one of seconds, minutes, hours, days, weeks, singular or plural) or `never`. `retry` is 0, 1 or 2. `coverage` is a regular expression enclosed in slashes.
           `extends` names an existing template or job.
        8. **Deploys.** `deploy-staging` deploys to the environment `staging`, `deploy-prod` to `production`. The production deploy is manual: every rule that lets it run has `when: manual` **and** `allow_failure: false` (or, without rules, the job itself has both).
    ''')
    return {"PIPELINE_RULES.md": rules_md, "README.md": f"# {P['name']}\n\nCI pipeline of {P['what']}. Only `.gitlab-ci.yml` is relevant here (the application source is omitted). The rules the pipeline must follow are in `PIPELINE_RULES.md`.\n"}


def hidden(model, ctx):
    return {"tests/rules.json": json.dumps(ctx["rules"], indent=1) + "\n"}


def prompt(rng, ctx, texts, vague):
    P = ctx["P"]
    return K.fix_prompt(rng, ".gitlab-ci.yml", f"CI pipeline of {P['name']} ({P['what']})", texts, "PIPELINE_RULES.md", vague, [
        f"The pipeline of {P['name']} is rejected by our CI policy check (`PIPELINE_RULES.md`). Find the problems in `.gitlab-ci.yml` and fix them without dropping jobs or changing their scripts.",
        f"`.gitlab-ci.yml` of {P['name']} ({P['what']}) does not comply with `PIPELINE_RULES.md`. Repair it; keep every job and every script.",
    ])


def wrong(model, ctx):
    import copy
    w1 = copy.deepcopy(model)
    del w1["lint"]
    w2 = copy.deepcopy(model)
    w2["deploy-prod"]["rules"][0]["allow_failure"] = True
    w3 = copy.deepcopy(model)
    w3["stages"].append("tests")
    return [render(w1, ctx), render(w2, ctx), render(w3, ctx)]


PLAN = [
    {"keys": ["image"], "d": 1}, {"keys": ["tab"], "d": 1}, {"keys": ["stage-typo", "expire"]}, {"keys": ["needs-missing"], "d": 2},
    {"keys": ["var-bool", "cache"]}, {"keys": ["rule-if", "retry"]}, {"keys": ["script-colon", "extends"]}, {"keys": ["dup-job", "dep-no-art"]},
    {"keys": ["needs-later", "manual", "secret"]}, {"keys": ["rules-only", "coverage", "indent"]},
    {"keys": ["stage-typo", "needs-later", "var-bool", "prod-auto", "image", "secret"], "vague": True, "d": 5},
    {"keys": ["script-colon", "dep-no-art", "rule-if", "retry", "dup-job", "cache"], "vague": True, "d": 5},
]


@family("devops-gitlab-pipelines", category="devops", lang="text", kind="fix", n=len(PLAN),
        summary="repair GitLab CI pipelines against a mechanical policy: stages and needs, string variables, rules expressions, artifacts, caches, protected manual deploys, YAML 1.1 traps")
def gitlab_pipelines(rng, n):
    return K.fix_tasks(rng, n, prefix="gitlab", plan=PLAN, build=build_model, render=render, defects=DEFECTS, docs=docs, hidden=hidden, check=CHECK_GITLAB,
                       prompt=prompt, wrong=wrong, tags=["gitlab", "ci", "yaml"])
