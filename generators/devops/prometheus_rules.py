"""DevOps tasks: Prometheus alerting and recording rules repaired against a mechanical policy (PromQL sanity, durations, severities, annotations, naming, YAML template traps)."""
import json

from fx import dd, family
from generators.devops import _dokit as K
from generators.devops import _yamlw as Y

CHECK_PROM = r'''
from dolib import *

R = json.load(open("tests/rules.json", encoding="utf-8"))
PATH = R["path"]
doc = yaml_one(PATH)
rep = Report()
DUR = re.compile(r"^(\d+(ms|s|m|h|d|w|y))+$")
RANGE_FUNCS = r"(?:rate|irate|increase|delta|idelta|deriv|predict_linear|resets|changes|[a-z]+_over_time)"


def dur_seconds(s):
    unit = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800, "y": 31536000}
    return sum(int(n) * unit[u] for n, u in re.findall(r"(\d+)(ms|s|m|h|d|w|y)", s))


def strip_strings(e):
    return re.sub(r'"(?:[^"\\]|\\.)*"', '""', e)


def balanced(e):
    stack = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for ch in strip_strings(e):
        if ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            if not stack or stack.pop() != pairs[ch]:
                return False
    return not stack and e.count('"') % 2 == 0


def call_args(e, fn):
    """argument texts of every call of fn(...) in e (after strings are blanked)"""
    s, out = strip_strings(e), []
    for m in re.finditer(rf"\b{fn}\(", s):
        depth, i = 1, m.end()
        while i < len(s) and depth:
            depth += {"(": 1, ")": -1}.get(s[i], 0)
            i += 1
        out.append(s[m.end():i - 1])
    return out


def promql_problems(e):
    p = []
    if not isinstance(e, str) or not e.strip():
        return ["`expr` must be a non-empty string"]
    if not balanced(e):
        return ["unbalanced parentheses, brackets, braces or quotes"]
    for a in call_args(e, RANGE_FUNCS):
        if not re.search(r"\[\d+(ms|s|m|h|d|w|y)\]", a):
            p.append("a range function (rate, increase, *_over_time, predict_linear ...) needs a range selector like [5m]")
            break
    for body in re.findall(r"\{([^{}]*)\}", e):
        for part in re.split(r",(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", body):
            part = part.strip()
            if not part:
                continue
            m = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)\s*(=~|!~|!=|=)\s*(.*)', part)
            if not m:
                p.append(f"label matcher {part!r} is not name<op>\"value\"")
            elif not re.fullmatch(r'"(?:[^"\\]|\\.)*"', m.group(3).strip()):
                p.append(f"label matcher value in {part!r} must be a double-quoted string")
    flat = re.sub(r"\{[^{}]*\}", "{}", strip_strings(e))
    if re.search(r"(?<![=!<>~])=(?![=~])", flat):
        p.append("a single `=` outside a label matcher; comparisons are written ==, !=, <, >, <=, >=")
    for a in call_args(e, "histogram_quantile"):
        first = a.split(",", 1)[0].strip()
        try:
            ok = 0 <= float(first) <= 1
        except ValueError:
            ok = False
        if not ok:
            p.append("histogram_quantile needs a quantile between 0 and 1 as its first argument")
    return p


groups = doc.get("groups")
if not rep.check(isinstance(groups, list) and groups, "top level `groups` must be a non-empty list"):
    rep.finish()
names, alerts_seen, kept = set(), {}, {}
for gi, g in enumerate(groups):
    if not rep.check(isinstance(g, dict) and isinstance(g.get("name"), str) and g["name"], f"group #{gi + 1} needs a `name`"):
        continue
    gn = g["name"]
    rep.check(gn not in names, f"group name {gn!r} is used twice")
    names.add(gn)
    if "interval" in g:
        rep.check(isinstance(g["interval"], str) and DUR.match(g["interval"]), f"group {gn!r}: interval {g['interval']!r} is not a duration like 1m")
    rules = g.get("rules")
    if not rep.check(isinstance(rules, list) and rules, f"group {gn!r} has no rules"):
        continue
    for r in rules:
        if not rep.check(isinstance(r, dict), f"group {gn!r}: every rule must be a mapping"):
            continue
        is_alert = "alert" in r
        is_rec = "record" in r
        if not rep.check(is_alert != is_rec, f"group {gn!r}: a rule has either `alert` or `record` (exactly one)"):
            continue
        name = r.get("alert") if is_alert else r.get("record")
        who = f"{'alert' if is_alert else 'record'} {name!r}"
        if not rep.check(isinstance(name, str) and name, f"group {gn!r}: rule without a name"):
            continue
        for pr in promql_problems(r.get("expr")):
            rep.check(False, f"{who}: {pr}")
        for lk, lv in (r.get("labels") or {}).items() if isinstance(r.get("labels"), dict) else []:
            rep.check(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(lk)) and isinstance(lv, str), f"{who}: label {lk} must have a string value (quote numbers and booleans), got {lv!r}")
        kept[name] = (gn, r)
        if is_rec:
            rep.check(re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*(:[a-zA-Z_][a-zA-Z0-9_]*)+", name) is not None, f"{who}: recording rule names are `level:metric:operations`, so they contain a colon")
            continue
        rep.check(re.fullmatch(r"[A-Z][A-Za-z0-9]*", name) is not None, f"{who}: alert names are CamelCase (letters and digits, starting with a capital)")
        rep.check(name not in alerts_seen, f"{who} is defined twice (groups {alerts_seen.get(name)!r} and {gn!r})")
        alerts_seen[name] = gn
        f = r.get("for")
        if f is not None:
            rep.check(isinstance(f, str) and DUR.match(f), f"{who}: `for: {f}` is not a duration such as 5m or 1h30m")
        labels = r.get("labels") if isinstance(r.get("labels"), dict) else {}
        sev = labels.get("severity")
        rep.check(sev in ("page", "ticket", "info"), f"{who}: labels.severity must be page, ticket or info (got {sev!r})")
        ann = r.get("annotations") if isinstance(r.get("annotations"), dict) else {}
        for k in ("summary", "description"):
            rep.check(isinstance(ann.get(k), str) and bool(ann[k].strip()), f"{who}: annotations.{k} is required")
            v = ann.get(k)
            if isinstance(v, str):
                rep.check(v.count("{{") == v.count("}}"), f"{who}: unbalanced template braces in annotations.{k}")
        if sev == "page":
            rep.check(isinstance(f, str) and DUR.match(f) and dur_seconds(f) >= 300, f"{who}: a page alert needs `for` of at least 5m")
            ru = ann.get("runbook_url")
            rep.check(isinstance(ru, str) and ru.startswith("https://"), f"{who}: a page alert needs annotations.runbook_url starting with https://")
        elif "runbook_url" in ann:
            rep.check(isinstance(ann["runbook_url"], str) and ann["runbook_url"].startswith("https://"), f"{who}: runbook_url must start with https://")

# the work is kept
for name, want in R["rules"].items():
    got = kept.get(name)
    if not rep.check(got is not None, f"{name!r} is missing: do not delete rules"):
        continue
    gn, r = got
    rep.check(gn == want["group"], f"{name!r} must stay in group {want['group']!r}")
    e = str(r.get("expr"))
    for tok in want["tokens"]:
        rep.check(tok in e, f"{name!r}: the expression must keep `{tok}` (do not change what is measured)")
    if "severity" in want:
        rep.check((r.get("labels") or {}).get("severity") == want["severity"], f"{name!r}: severity must stay {want['severity']!r}")
rep.check(set(kept) == set(R["rules"]), f"the rule files must define exactly the rules {sorted(R['rules'])}")
rep.finish()
'''

SERVICES = [
    dict(svc="HarbourMaster", slug="harbourmaster", job="harbour-api", metric="ferry_requests", what="the ferry berth allocation API"),
    dict(svc="KilnQueue", slug="kilnqueue", job="kiln-worker", metric="kiln_jobs", what="the pottery kiln scheduler"),
    dict(svc="MothIndex", slug="mothindex", job="moth-search", metric="specimen_lookups", what="the museum specimen search"),
    dict(svc="TideClock", slug="tideclock", job="tide-ingest", metric="tide_samples", what="the tide gauge ingester"),
]


def build_model(rng, i):
    S = SERVICES[i % len(SERVICES)]
    s, j, mt = S["svc"], S["job"], S["metric"]
    base = "https://runbooks.example.test/" + S["slug"]
    q = rng.choice([0.9, 0.95, 0.99])
    thr = rng.choice([0.02, 0.05, 0.1])
    lat = rng.choice([0.8, 1.5, 2.5])
    lab = lambda sev, **kw: {"severity": sev, "team": S["slug"], **kw}
    rules_rec = [
        {"record": f"job:{mt}_total:rate5m", "expr": f'sum by (job) (rate({mt}_total{{job="{j}"}}[5m]))'},
        {"record": f"job:{mt}_errors:ratio_rate5m", "expr": f'sum(rate({mt}_errors_total{{job="{j}"}}[5m])) / sum(rate({mt}_total{{job="{j}"}}[5m]))'},
    ]
    rules_alert = [
        {"alert": f"{s}Down", "expr": f'up{{job="{j}"}} == 0', "for": "5m", "labels": lab("page"),
         "annotations": {"summary": "{{ $labels.instance }} is down", "description": f"{S['what']} instance {{{{ $labels.instance }}}} has not been scraped for 5 minutes.", "runbook_url": f"{base}/down"}},
        {"alert": f"{s}HighErrorRatio", "expr": f'sum(rate({mt}_errors_total{{job="{j}"}}[5m])) / sum(rate({mt}_total{{job="{j}"}}[5m])) > {thr}', "for": "10m", "labels": lab("page"),
         "annotations": {"summary": "error ratio above threshold", "description": f"More than {int(thr * 100)}% of requests to {S['what']} fail.", "runbook_url": f"{base}/errors"}},
        {"alert": f"{s}LatencyHigh", "expr": f'histogram_quantile({q}, sum by (le) (rate({mt}_duration_seconds_bucket{{job="{j}"}}[5m]))) > {lat}', "for": "15m", "labels": lab("ticket"),
         "annotations": {"summary": "p" + str(int(q * 100)) + " latency is high", "description": f"The p{int(q * 100)} latency of {S['what']} is above {lat} s."}},
        {"alert": f"{s}DiskFilling", "expr": 'predict_linear(node_filesystem_avail_bytes{job="node",mountpoint="/data"}[6h], 86400) < 0', "for": "1h", "labels": lab("ticket"),
         "annotations": {"summary": "{{ $labels.instance }} data disk fills within a day", "description": "The data volume is predicted to run out of space in 24 hours."}},
        {"alert": f"{s}QueueBacklog", "expr": f'max_over_time({mt}_queue_depth{{job="{j}"}}[10m]) > 1000', "for": "10m", "labels": lab("info"),
         "annotations": {"summary": "queue backlog", "description": "More than 1000 items waited in the queue during the last 10 minutes."}},
    ]
    model = {"groups": [{"name": f"{S['slug']}.recording", "interval": "1m", "rules": rules_rec}, {"name": f"{S['slug']}.alerts", "rules": rules_alert}]}
    keep = {}
    for g in model["groups"]:
        for r in g["rules"]:
            nm = r.get("alert") or r.get("record")
            toks = sorted(set(__import__("re").findall(r"[a-z]+(?:_[a-z]+)+", r["expr"])) - {"by"})
            nums = sorted(set(__import__("re").findall(r"(?<![\w.])\d+\.\d+|(?<![\w.])\d{3,}", r["expr"])))
            keep[nm] = {"group": g["name"], "tokens": toks + nums, **({"severity": r["labels"]["severity"]} if "labels" in r else {})}
    return model, {"S": S, "rules": {"path": "rules.yml", "rules": keep}}


def render(model, ctx):
    return {"rules.yml": Y.roundtrip(model)}


def alert(m, name):
    for g in m["groups"]:
        for r in g["rules"]:
            if r.get("alert") == name or r.get("record") == name:
                return r
    raise KeyError(name)


# ---------------------------------------------------------------------------------------------------- defects


def d_no_range(m, ctx, rng):
    s = ctx["S"]["svc"]
    a = alert(m, f"{s}HighErrorRatio")
    a["expr"] = a["expr"].replace("[5m]", "")
    return {}


def d_unquoted(m, ctx, rng):
    s, j = ctx["S"]["svc"], ctx["S"]["job"]
    a = alert(m, f"{s}Down")
    a["expr"] = a["expr"].replace(f'"{j}"', j)
    return {"a": f"{s}Down"}


def d_single_eq(m, ctx, rng):
    s = ctx["S"]["svc"]
    a = alert(m, f"{s}Down")
    a["expr"] = a["expr"].replace("==", "=")
    return {}


def d_paren(m, ctx, rng):
    s = ctx["S"]["svc"]
    a = alert(m, f"{s}LatencyHigh")
    a["expr"] = a["expr"].replace("[5m])))", "[5m]))", 1)
    return {}


def d_bad_for(m, ctx, rng):
    s = ctx["S"]["svc"]
    nm = rng.choice([f"{s}LatencyHigh", f"{s}QueueBacklog", f"{s}DiskFilling"])
    alert(m, nm)["for"] = rng.choice(["10min", "5 m", "1 hour", "15"])
    return {"a": nm}


def d_sev(m, ctx, rng):
    s = ctx["S"]["svc"]
    nm = rng.choice([f"{s}Down", f"{s}DiskFilling"])
    alert(m, nm)["labels"]["severity"] = rng.choice(["critical", "Page", "warning"])
    return {"a": nm}


def d_label_int(m, ctx, rng):
    s = ctx["S"]["svc"]
    alert(m, f"{s}DiskFilling")["labels"]["priority"] = Y.Raw("3", 3)
    return {}


def d_no_runbook(m, ctx, rng):
    s = ctx["S"]["svc"]
    nm = rng.choice([f"{s}Down", f"{s}HighErrorRatio"])
    alert(m, nm)["annotations"].pop("runbook_url")
    return {"a": nm}


def d_no_desc(m, ctx, rng):
    s = ctx["S"]["svc"]
    nm = rng.choice([f"{s}QueueBacklog", f"{s}DiskFilling"])
    alert(m, nm)["annotations"].pop("description")
    return {"a": nm}


def d_name_case(m, ctx, rng):
    s = ctx["S"]["svc"]
    a = alert(m, f"{s}QueueBacklog")
    a["alert"] = "queue_backlog"
    return {}


def d_record_name(m, ctx, rng):
    mt = ctx["S"]["metric"]
    a = alert(m, f"job:{mt}_total:rate5m")
    a["record"] = f"job_{mt}_total_rate5m"
    return {}


def d_dup_alert(m, ctx, rng):
    s = ctx["S"]["svc"]
    import copy
    dup = copy.deepcopy(alert(m, f"{s}QueueBacklog"))
    m["groups"][0]["rules"].append(dup)
    return {}


def d_short_page(m, ctx, rng):
    s = ctx["S"]["svc"]
    alert(m, f"{s}Down")["for"] = rng.choice(["1m", "2m", "30s"])
    return {}


def d_quantile(m, ctx, rng):
    s = ctx["S"]["svc"]
    a = alert(m, f"{s}LatencyHigh")
    import re
    a["expr"] = re.sub(r"histogram_quantile\(0\.\d+", rng.choice(["histogram_quantile(99", "histogram_quantile(95"]), a["expr"])
    return {}


def d_url(m, ctx, rng):
    s = ctx["S"]["svc"]
    a = alert(m, f"{s}HighErrorRatio")
    a["annotations"]["runbook_url"] = a["annotations"]["runbook_url"].replace("https://", "http://")
    return {}


def _edit_line(files, pred, fn, why):
    lines = files["rules.yml"].split("\n")
    idx = [i for i, l in enumerate(lines) if pred(l.strip())]
    if not idx:
        raise RuntimeError("defect: no line to edit (" + why + ")")
    return lines, idx


def d_template_yaml(m, ctx, rng):
    def post(files):
        lines, idx = _edit_line(files, lambda t: t == 'summary: "{{ $labels.instance }} is down"', None, "template")
        k = idx[0]
        lines[k] = lines[k].replace('"{{ $labels.instance }} is down"', "{{ $labels.instance }} is down")
        files["rules.yml"] = "\n".join(lines)
        try:
            Y.load_all(files["rules.yml"])
        except ValueError:
            return files
        raise RuntimeError("the template defect did not break the YAML")
    return {"_post": post}


def d_tab(m, ctx, rng):
    def post(files):
        lines, idx = _edit_line(files, lambda t: t.startswith("for:"), None, "tab")
        k = idx[0]
        lines[k] = "\t" + lines[k].lstrip()
        files["rules.yml"] = "\n".join(lines)
        return files
    return {"_post": post}


def d_indent(m, ctx, rng):
    def post(files):
        lines, idx = _edit_line(files, lambda t: t.startswith("labels:"), None, "indent")
        k = idx[len(idx) // 2]
        lines[k] = lines[k][:-1 - len(lines[k].lstrip()) + 1][:-1] + lines[k].lstrip()
        files["rules.yml"] = "\n".join(lines)
        try:
            Y.load_all(files["rules.yml"])
        except ValueError:
            return files
        raise RuntimeError("the indentation defect did not break the YAML")
    return {"_post": post}


DEFECTS = {
    "no-range": (d_no_range, ["the error-ratio alert never fires and Prometheus logs `expected type range vector`", "one `rate()` call has no range selector"]),
    "unquoted": (d_unquoted, ["`{a}` fails to load: a label matcher value is not quoted", "promtool says the matcher in `{a}` is malformed"]),
    "single-eq": (d_single_eq, ["the `Down` alert has a parse error in its expression (a comparison is written wrongly)", "`up == 0` was typed as an assignment in one alert"]),
    "paren": (d_paren, ["the latency alert has an unbalanced parenthesis", "promtool reports an unexpected end of input in the latency expression"]),
    "bad-for": (d_bad_for, ["`{a}` has a `for:` duration that Prometheus cannot parse", "the `for` value of `{a}` is not a valid duration"]),
    "sev": (d_sev, ["`{a}` has a severity our alert router does not know", "alertmanager drops `{a}` because the severity label is not one of ours"]),
    "label-int": (d_label_int, ["a label value is a number, and rule loading fails with `cannot unmarshal !!int into string`", "the rule file is rejected: a label is not a string"]),
    "no-runbook": (d_no_runbook, ["the paging alert `{a}` has no runbook link", "on-call complains that `{a}` pages without a runbook_url"]),
    "no-desc": (d_no_desc, ["`{a}` has no description annotation", "the notification for `{a}` renders without a description"]),
    "name-case": (d_name_case, ["one alert is named in snake_case while all the others are CamelCase", "an alert name breaks the naming convention"]),
    "record-name": (d_record_name, ["a recording rule has no colon in its name (naming convention violation)", "the linter rejects a recording rule name"]),
    "dup-alert": (d_dup_alert, ["the same alert is defined twice in the files", "`QueueBacklog` appears in two groups and fires double"]),
    "short-page": (d_short_page, ["the `Down` page fires on a one-minute blip and wakes people up", "paging alert `for` is shorter than our 5 minute minimum"]),
    "quantile": (d_quantile, ["the latency alert asks `histogram_quantile` for a quantile that is not between 0 and 1", "`histogram_quantile` is called with a percentage instead of a fraction"]),
    "url": (d_url, ["a runbook link uses plain http", "one runbook_url is not https"]),
    "template": (d_template_yaml, ["Prometheus fails to load the file: YAML error in an annotation containing `{{ ... }}`", "the rules file stopped parsing after somebody added a template to a summary"]),
    "tab": (d_tab, ["YAML error: a tab character was found in the rules file", "promtool: found character that cannot start any token"]),
    "indent": (d_indent, ["the rules file does not parse after the last edit (indentation)", "YAML error at a `labels:` line"]),
}


# ---------------------------------------------------------------------------------------------------- docs


def docs(model, ctx):
    r, S = ctx["rules"], ctx["S"]
    rules_md = dd(f'''
        # Rule policy for {S["slug"]}

        `rules.yml` is checked mechanically with the rules below. The YAML is read with Ruby's Psych (YAML 1.1: a bare `{{{{ ... }}}}` at the start of a value is a flow mapping, not text; an unquoted `3` is an integer).

        1. **Keep the work.** The file defines exactly the rules {", ".join("`" + n + "`" for n in r["rules"])}, each in its own group, and each expression keeps its metric names and numeric thresholds (only the syntax may change).
        2. **Groups.** Group names are unique; every group has at least one rule; `interval`, when present, is a duration (`1m`). A rule has either `alert` or `record`.
        3. **Expressions.** `expr` is a non-empty string with balanced parentheses, brackets, braces and quotes. Range functions (`rate`, `irate`, `increase`, `delta`, `deriv`, `predict_linear`, `resets`, `changes`, `*_over_time`) get a range selector such as `[5m]`.
           Label matcher values are double-quoted (`job="api"`, operators `=`, `!=`, `=~`, `!~`). Comparisons use `==`, `!=`, `<`, `>`, `<=`, `>=` (a single `=` is not a comparison). `histogram_quantile` takes a quantile between 0 and 1.
        4. **Labels.** Every label has a valid name and a **string** value (quote numbers).
        5. **Recording rules** are named `level:metric:operations`, so the name contains a colon.
        6. **Alerts.** Names are CamelCase and unique across the whole file. `for`, when present, is a duration (`10m`, `1h30m`). `labels.severity` is `page`, `ticket` or `info` and keeps its value.
           `annotations.summary` and `annotations.description` are required non-empty strings with balanced `{{{{ }}}}`. A `page` alert has `for` of at least 5m and `annotations.runbook_url` starting with `https://`; any runbook_url must be https.
    ''')
    return {"RULE_POLICY.md": rules_md, "README.md": f"# {S['slug']}\n\nPrometheus rules for {S['what']}. Only `rules.yml` is relevant here. The policy the file is checked against is in `RULE_POLICY.md`.\n"}


def hidden(model, ctx):
    return {"tests/rules.json": json.dumps(ctx["rules"], indent=1) + "\n"}


def prompt(rng, ctx, texts, vague):
    S = ctx["S"]
    return K.fix_prompt(rng, "rules.yml", f"Prometheus rules for {S['what']}", texts, "RULE_POLICY.md", vague, [
        f"`promtool check rules` and our policy check (`RULE_POLICY.md`) both reject the rules of {S['what']}. Fix `rules.yml` without removing rules or changing what they measure.",
        f"The alert rules for {S['what']} don't load cleanly and break `RULE_POLICY.md`. Repair `rules.yml`; keep every rule and its meaning.",
    ])


def wrong(model, ctx):
    import copy
    s = ctx["S"]["svc"]
    w1 = copy.deepcopy(model)
    w1["groups"][1]["rules"] = [r for r in w1["groups"][1]["rules"] if r.get("alert") != f"{s}QueueBacklog"]
    w2 = copy.deepcopy(model)
    alert(w2, f"{s}Down")["labels"]["severity"] = "ticket"
    w3 = copy.deepcopy(model)
    alert(w3, f"{s}HighErrorRatio")["expr"] = "vector(0) > 1"
    return [render(w1, ctx), render(w2, ctx), render(w3, ctx)]


PLAN = [
    {"keys": ["no-range"], "d": 1}, {"keys": ["template"], "d": 1}, {"keys": ["bad-for", "sev"]}, {"keys": ["unquoted"], "d": 2},
    {"keys": ["single-eq", "no-runbook", "record-name"]}, {"keys": ["quantile", "dup-alert"]}, {"keys": ["paren", "short-page", "name-case", "label-int"]},
    {"keys": ["tab", "url", "no-desc", "bad-for"]},
    {"keys": ["no-range", "single-eq", "bad-for", "sev", "dup-alert", "no-runbook", "quantile"], "vague": True, "d": 5},
    {"keys": ["template", "paren", "short-page", "label-int", "record-name", "url"], "vague": True, "d": 5},
]


@family("devops-prometheus-rules", category="devops", lang="text", kind="fix", n=len(PLAN),
        summary="repair Prometheus alerting and recording rules against a mechanical policy: PromQL sanity checks, durations, severities, annotations, naming, YAML template traps")
def prometheus_rules(rng, n):
    return K.fix_tasks(rng, n, prefix="prom", plan=PLAN, build=build_model, render=render, defects=DEFECTS, docs=docs, hidden=hidden, check=CHECK_PROM,
                       prompt=prompt, wrong=wrong, tags=["prometheus", "alerting", "yaml"])
