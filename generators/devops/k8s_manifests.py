"""DevOps tasks: Kubernetes manifests (Deployment, Service, ConfigMap, HPA, PDB, Ingress) repaired against a mechanical policy."""
import copy
import json

from fx import dd, family
from generators.devops import _dokit as K
from generators.devops import _yamlw as Y

CHECK_K8S = r'''
from dolib import *

R = json.load(open("tests/rules.json", encoding="utf-8"))
PATH = R["path"]
try:
    docs = [d for d in yaml_docs(PATH) if d is not None]
except ValueError as e:
    die(f"{PATH} is not valid YAML: {e}")
rep = Report()
if not all(isinstance(d, dict) for d in docs):
    die("every YAML document must be a mapping")
by = {}
for d in docs:
    by.setdefault(d.get("kind"), []).append(d)
API = {"Deployment": "apps/v1", "Service": "v1", "ConfigMap": "v1", "HorizontalPodAutoscaler": "autoscaling/v2", "PodDisruptionBudget": "policy/v1", "Ingress": "networking.k8s.io/v1"}


def one(kind):
    xs = by.get(kind, [])
    if kind not in R["kinds"]:
        return None
    rep.check(len(xs) == 1, f"expected exactly one {kind}, found {len(xs)}")
    return xs[0] if xs else None


def g(o, *path, default=None):
    for p in path:
        if isinstance(o, dict):
            o = o.get(p)
        elif isinstance(o, list) and isinstance(p, int) and p < len(o):
            o = o[p]
        else:
            return default
    return default if o is None else o


def qty(s, kind):
    s = str(s)
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(m|Ki|Mi|Gi|Ti|k|M|G|T)?", s)
    if not m:
        return None
    n, u = float(m.group(1)), m.group(2)
    if kind == "cpu":
        return n / 1000 if u == "m" else (n if u is None else None)
    mult = {None: 1, "k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12, "Ki": 1024, "Mi": 1024 ** 2, "Gi": 1024 ** 3, "Ti": 1024 ** 4}
    return None if u == "m" else n * mult[u]


# R1 kinds, API versions, names, namespace
rep.check(sorted(k for k in by) == sorted(R["kinds"]), f"the file must contain exactly these kinds: {sorted(R['kinds'])} (found {sorted(by)})")
for d in docs:
    k = d.get("kind")
    if k in API:
        rep.check(d.get("apiVersion") == API[k], f"{k} must use apiVersion {API[k]} (got {d.get('apiVersion')!r})")
    ns = g(d, "metadata", "namespace")
    rep.check(ns == R["namespace"], f"{k} {g(d, 'metadata', 'name')!r}: metadata.namespace must be {R['namespace']!r} (got {ns!r})")
dep, svc, cm, hpa, pdb, ing = (one(k) for k in ("Deployment", "Service", "ConfigMap", "HorizontalPodAutoscaler", "PodDisruptionBudget", "Ingress"))
if not dep:
    rep.finish()
tl = g(dep, "spec", "template", "metadata", "labels", default={})
sel = g(dep, "spec", "selector", "matchLabels", default={})
rep.check(g(dep, "metadata", "name") == R["name"], f"the Deployment must be called {R['name']!r}")

# R2 selectors and labels
rep.check(bool(sel) and all(tl.get(k) == v for k, v in sel.items()), f"Deployment selector.matchLabels {sel} must match the pod template labels {tl}")
rep.check(tl.get("app.kubernetes.io/name") == R["app"], f"pod template labels need app.kubernetes.io/name: {R['app']}")
if svc:
    ss = g(svc, "spec", "selector", default={})
    rep.check(bool(ss) and all(tl.get(k) == v for k, v in ss.items()), f"Service selector {ss} does not select the pods (labels {tl})")
if pdb:
    ps = g(pdb, "spec", "selector", "matchLabels", default={})
    rep.check(bool(ps) and all(tl.get(k) == v for k, v in ps.items()), f"PodDisruptionBudget selector {ps} does not select the pods")

# R3 containers
cons = g(dep, "spec", "template", "spec", "containers", default=[])
if not rep.check(len(cons) == 1 and isinstance(cons[0], dict), "the pod needs exactly one container"):
    rep.finish()
c = cons[0]
rep.check(c.get("name") == R["container"], f"the container must be called {R['container']!r}")
img = str(c.get("image", ""))
rep.check(img.startswith(R["image_repo"] + ":") and not img.endswith(":latest"), f"the image must be {R['image_repo']}:<version> with a fixed version (got {img!r})")
ports = {p.get("name"): p.get("containerPort") for p in g(c, "ports", default=[]) if isinstance(p, dict)}
rep.check(ports.get(R["port_name"]) == R["port"], f"the container must declare port {R['port']} named {R['port_name']!r}")
res = c.get("resources") or {}
for kind in ("cpu", "memory"):
    rq, lm = g(res, "requests", kind), g(res, "limits", kind)
    if rep.check(rq is not None and lm is not None, f"resources.requests.{kind} and resources.limits.{kind} are both required"):
        a, b = qty(rq, kind), qty(lm, kind)
        if rep.check(a is not None and b is not None, f"{kind} quantities {rq!r}/{lm!r} are not valid Kubernetes quantities (memory: Ki/Mi/Gi/K/M/G, cpu: 500m or 0.5)"):
            rep.check(a <= b, f"{kind} request {rq} is larger than the limit {lm}")
for probe in ("readinessProbe", "livenessProbe"):
    p = c.get(probe)
    if rep.check(isinstance(p, dict), f"the container needs a {probe}"):
        hg = p.get("httpGet") or {}
        rep.check(hg.get("path", "").startswith("/"), f"{probe}.httpGet.path is required")
        rep.check(hg.get("port") in (R["port_name"], R["port"]), f"{probe}.httpGet.port must be the container port ({R['port_name']} or {R['port']}), got {hg.get('port')!r}")
sc = c.get("securityContext") or {}
rep.check(sc.get("runAsNonRoot") is True, "securityContext.runAsNonRoot must be true")
rep.check(sc.get("allowPrivilegeEscalation") is False, "securityContext.allowPrivilegeEscalation must be false")
rep.check(sc.get("readOnlyRootFilesystem") is True, "securityContext.readOnlyRootFilesystem must be true")
rep.check(not sc.get("privileged"), "the container must not be privileged")

# R4 configuration wiring
if cm:
    keys = set((cm.get("data") or {}).keys())
    rep.check(g(cm, "metadata", "name") == R["configmap"], f"the ConfigMap must be called {R['configmap']!r}")
    for e in g(c, "env", default=[]):
        ref = g(e, "valueFrom", "configMapKeyRef")
        if ref:
            rep.check(ref.get("name") == R["configmap"] and ref.get("key") in keys, f"env {e.get('name')}: configMapKeyRef {ref} does not point to an existing ConfigMap key (keys: {sorted(keys)})")
        ref = g(e, "valueFrom", "secretKeyRef")
        if ref:
            rep.check(ref.get("name") in R["secrets"], f"env {e.get('name')}: the Secret {ref.get('name')!r} is not one of {R['secrets']}")
vols = {v.get("name"): v for v in g(dep, "spec", "template", "spec", "volumes", default=[]) if isinstance(v, dict)}
for vm in g(c, "volumeMounts", default=[]):
    rep.check(vm.get("name") in vols, f"volumeMount {vm.get('name')!r} has no matching volume in the pod")
for n, v in vols.items():
    ref = g(v, "configMap", "name")
    if ref is not None:
        rep.check(ref == R["configmap"], f"volume {n!r} references the ConfigMap {ref!r}, which does not exist")
rep.check("tmp" in {vm.get("name") for vm in g(c, "volumeMounts", default=[])} or not sc.get("readOnlyRootFilesystem"), "a read-only root file system needs a writable /tmp (an emptyDir volume mounted at /tmp)")

# R5 service
if svc:
    sp = g(svc, "spec", "ports", default=[])
    if rep.check(len(sp) == 1, "the Service needs exactly one port"):
        p = sp[0]
        rep.check(p.get("port") == R["svc_port"], f"the Service must expose port {R['svc_port']} (got {p.get('port')!r})")
        rep.check(p.get("targetPort") in (R["port_name"], R["port"]), f"Service targetPort {p.get('targetPort')!r} does not match the container port ({R['port_name']} / {R['port']})")
    rep.check(g(svc, "metadata", "name") == R["name"], f"the Service must be called {R['name']!r}")

# R6 autoscaling and disruption budget
reps = g(dep, "spec", "replicas")
if hpa:
    t = g(hpa, "spec", "scaleTargetRef", default={})
    rep.check(t.get("kind") == "Deployment" and t.get("name") == R["name"], f"HPA scaleTargetRef must point at Deployment {R['name']!r} (got {t})")
    lo, hi = g(hpa, "spec", "minReplicas"), g(hpa, "spec", "maxReplicas")
    rep.check(isinstance(lo, int) and isinstance(hi, int) and 1 <= lo <= hi, f"HPA minReplicas/maxReplicas must be integers with 1 <= min <= max (got {lo!r}/{hi!r})")
    rep.check(reps is None, "the Deployment must not set `replicas` when an HPA manages it")
    ms = g(hpa, "spec", "metrics", default=[])
    rep.check(bool(ms) and all(g(m, "type") == "Resource" and g(m, "resource", "target", "averageUtilization") for m in ms), "the HPA metrics must be Resource metrics with target.averageUtilization (autoscaling/v2)")
else:
    rep.check(isinstance(reps, int) and reps >= 2, "the Deployment needs replicas >= 2")
if pdb:
    ma = g(pdb, "spec", "minAvailable")
    rep.check(ma is not None and g(pdb, "spec", "maxUnavailable") is None, "the PodDisruptionBudget sets minAvailable (and not maxUnavailable)")
    floor = g(hpa, "spec", "minReplicas") if hpa else reps
    if isinstance(ma, int) and isinstance(floor, int):
        rep.check(ma < floor, f"minAvailable ({ma}) must be smaller than the minimum replica count ({floor}), otherwise no pod can ever be evicted")

# R7 ingress
if ing:
    rep.check(g(ing, "spec", "ingressClassName") == R["ingress_class"], f"spec.ingressClassName must be {R['ingress_class']!r}")
    rules = g(ing, "spec", "rules", default=[])
    if rep.check(len(rules) == 1 and rules[0].get("host") == R["host"], f"the Ingress needs one rule for host {R['host']}"):
        paths = g(rules[0], "http", "paths", default=[])
        if rep.check(len(paths) >= 1, "the Ingress rule needs a path"):
            for p in paths:
                rep.check(p.get("pathType") in ("Prefix", "Exact", "ImplementationSpecific"), f"path {p.get('path')!r}: pathType is required")
                b = g(p, "backend", "service", default={})
                rep.check(b.get("name") == R["name"], f"path {p.get('path')!r}: backend service must be {R['name']!r} (got {b.get('name')!r}; the old `serviceName` form is not valid)")
                bp = g(b, "port", default={})
                rep.check(bp.get("number") == R["svc_port"] or bp.get("name") == R["svc_port_name"], f"path {p.get('path')!r}: backend port must be the Service port {R['svc_port']}")

rep.finish()
'''

PROJECTS = [
    dict(app="harbor-sync", ns="harbor", image="registry.example.net/harbor/sync", ver="2.9.1", port=8080, port_name="http", svc_port=80, host="sync.harbor.example.net", cls="nginx", cmkeys={"SYNC_INTERVAL": "300s", "LOG_LEVEL": "info", "UPSTREAM": "https://mirror.example.net"}, secret="sync-credentials", hpa=True),
    dict(app="quill-render", ns="docs", image="registry.example.net/docs/quill", ver="0.14.3", port=3000, port_name="web", svc_port=8000, host="render.docs.example.net", cls="traefik", cmkeys={"THEME": "plain", "CACHE_TTL": "600", "PAPER": "a4"}, secret="quill-keys", hpa=False),
    dict(app="brine-gate", ns="edge", image="registry.example.net/edge/brine", ver="5.2.0", port=9090, port_name="api", svc_port=443, host="gate.edge.example.net", cls="nginx", cmkeys={"RATE": "50", "REGION": "north", "TIMEOUT_MS": "2500"}, secret="brine-tls-pin", hpa=True),
    dict(app="ember-queue", ns="jobs", image="registry.example.net/jobs/ember", ver="1.22.0", port=7000, port_name="rpc", svc_port=7000, host="queue.jobs.example.net", cls="haproxy", cmkeys={"WORKERS": "6", "RETRY": "4", "DRAIN": "30"}, secret="ember-token", hpa=False),
    dict(app="sable-index", ns="search", image="registry.example.net/search/sable", ver="3.1.7", port=8983, port_name="query", svc_port=80, host="find.search.example.net", cls="nginx", cmkeys={"SHARDS": "3", "ANALYZER": "standard", "REFRESH": "5s"}, secret="sable-admin", hpa=True),
]


def docs_of(rng, i):
    p = PROJECTS[i % len(PROJECTS)]
    app, ns = p["app"], p["ns"]
    labels = {"app.kubernetes.io/name": app, "app.kubernetes.io/part-of": ns}
    cm_name = f"{app}-config"
    keys = list(p["cmkeys"])
    reps = rng.choice([2, 3, 4])
    lo, hi = rng.choice([(2, 6), (3, 9), (2, 10)])
    meta = lambda name, extra=None: {"name": name, "namespace": ns, **({"labels": extra} if extra else {})}
    env = [{"name": k, "valueFrom": {"configMapKeyRef": {"name": cm_name, "key": k}}} for k in keys[:2]]
    env.append({"name": "API_TOKEN", "valueFrom": {"secretKeyRef": {"name": p["secret"], "key": "token"}}})
    container = {"name": app, "image": f"{p['image']}:{p['ver']}", "ports": [{"name": p["port_name"], "containerPort": p["port"]}], "env": env,
                 "resources": {"requests": {"cpu": rng.choice(["100m", "250m", "200m"]), "memory": rng.choice(["128Mi", "256Mi"])}, "limits": {"cpu": rng.choice(["500m", "1"]), "memory": rng.choice(["512Mi", "1Gi"])}},
                 "readinessProbe": {"httpGet": {"path": "/ready", "port": p["port_name"]}, "periodSeconds": 5},
                 "livenessProbe": {"httpGet": {"path": "/healthz", "port": p["port_name"]}, "initialDelaySeconds": 10, "periodSeconds": 10},
                 "securityContext": {"runAsNonRoot": True, "allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True},
                 "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}, {"name": "config", "mountPath": "/etc/" + app, "readOnly": True}]}
    dep = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": meta(app, labels),
           "spec": {**({} if p["hpa"] else {"replicas": reps}), "selector": {"matchLabels": {"app.kubernetes.io/name": app}},
                    "template": {"metadata": {"labels": labels}, "spec": {"containers": [container], "volumes": [{"name": "tmp", "emptyDir": {}}, {"name": "config", "configMap": {"name": cm_name}}]}}}}
    svc = {"apiVersion": "v1", "kind": "Service", "metadata": meta(app, labels), "spec": {"selector": {"app.kubernetes.io/name": app}, "ports": [{"name": "main", "port": p["svc_port"], "targetPort": p["port_name"]}]}}
    cm = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": meta(cm_name), "data": dict(p["cmkeys"])}
    ing = {"apiVersion": "networking.k8s.io/v1", "kind": "Ingress", "metadata": meta(app), "spec": {"ingressClassName": p["cls"], "rules": [{"host": p["host"], "http": {"paths": [{"path": "/", "pathType": "Prefix", "backend": {"service": {"name": app, "port": {"number": p["svc_port"]}}}}]}}]}}
    docs = [cm, dep, svc, ing]
    floor = lo if p["hpa"] else reps
    if p["hpa"]:
        docs.append({"apiVersion": "autoscaling/v2", "kind": "HorizontalPodAutoscaler", "metadata": meta(app),
                     "spec": {"scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": app}, "minReplicas": lo, "maxReplicas": hi,
                              "metrics": [{"type": "Resource", "resource": {"name": "cpu", "target": {"type": "Utilization", "averageUtilization": rng.choice([60, 70, 75])}}}]}})
    docs.append({"apiVersion": "policy/v1", "kind": "PodDisruptionBudget", "metadata": meta(app), "spec": {"minAvailable": floor - 1, "selector": {"matchLabels": {"app.kubernetes.io/name": app}}}})
    return docs, p


def kind_of(docs, k):
    return next(d for d in docs if d["kind"] == k)


def build(rng, i):
    docs, p = docs_of(rng, i)
    kinds = [d["kind"] for d in docs]
    rules = {"path": "k8s/app.yaml", "kinds": kinds, "namespace": p["ns"], "name": p["app"], "app": p["app"], "container": p["app"], "image_repo": p["image"], "port": p["port"], "port_name": p["port_name"],
             "svc_port": p["svc_port"], "svc_port_name": "main", "host": p["host"], "ingress_class": p["cls"], "configmap": f"{p['app']}-config", "secrets": [p["secret"]]}
    return docs, {"p": p, "rules": rules}


def render(docs, ctx):
    return {"k8s/app.yaml": "---\n" + "---\n".join(Y.roundtrip(d) for d in docs)}


# ---------------------------------------------------------------------------------------------------- defects


def cont(docs):
    return kind_of(docs, "Deployment")["spec"]["template"]["spec"]["containers"][0]


def d_selector(docs, ctx, rng):
    kind_of(docs, "Service")["spec"]["selector"] = {"app.kubernetes.io/name": ctx["p"]["app"] + "-svc"}
    return {}


def d_match_labels(docs, ctx, rng):
    kind_of(docs, "Deployment")["spec"]["selector"]["matchLabels"] = {"app": ctx["p"]["app"]}
    return {}


def d_api_ing(docs, ctx, rng):
    ing = kind_of(docs, "Ingress")
    ing["apiVersion"] = "networking.k8s.io/v1beta1"
    return {}


def d_hpa_api(docs, ctx, rng):
    for d in docs:
        if d["kind"] == "HorizontalPodAutoscaler":
            d["apiVersion"] = "autoscaling/v2beta1"
        elif d["kind"] == "PodDisruptionBudget":
            d["apiVersion"] = "policy/v1beta1"
    return {}


def d_target_port(docs, ctx, rng):
    kind_of(docs, "Service")["spec"]["ports"][0]["targetPort"] = ctx["p"]["port"] + 1
    return {}


def d_no_resources(docs, ctx, rng):
    del cont(docs)["resources"]["limits"]
    return {}


def d_req_gt_lim(docs, ctx, rng):
    cont(docs)["resources"]["requests"]["memory"] = "2Gi"
    cont(docs)["resources"]["limits"]["memory"] = "512Mi"
    return {}


def d_bad_qty(docs, ctx, rng):
    cont(docs)["resources"]["limits"]["memory"] = "512MB"
    return {}


def d_no_probe(docs, ctx, rng):
    del cont(docs)["readinessProbe"]
    return {}


def d_probe_port(docs, ctx, rng):
    cont(docs)["livenessProbe"]["httpGet"]["port"] = 8081 if ctx["p"]["port"] != 8081 else 8082
    return {}


def d_root(docs, ctx, rng):
    cont(docs)["securityContext"] = {"runAsNonRoot": False, "privileged": True}
    return {}


def d_latest(docs, ctx, rng):
    cont(docs)["image"] = ctx["p"]["image"] + ":latest"
    return {}


def d_cm_key(docs, ctx, rng):
    cont(docs)["env"][0]["valueFrom"]["configMapKeyRef"]["key"] = list(ctx["p"]["cmkeys"])[0].lower()
    return {}


def d_cm_name(docs, ctx, rng):
    vols = kind_of(docs, "Deployment")["spec"]["template"]["spec"]["volumes"]
    vols[1]["configMap"]["name"] = ctx["p"]["app"] + "-settings"
    return {}


def d_hpa_target(docs, ctx, rng):
    h = [d for d in docs if d["kind"] == "HorizontalPodAutoscaler"]
    if not h:
        kind_of(docs, "PodDisruptionBudget")["spec"]["minAvailable"] = 9
        return {"_phr": [1]}
    h[0]["spec"]["scaleTargetRef"]["name"] = ctx["p"]["app"] + "-deploy"
    return {"_phr": [0]}


def d_hpa_range(docs, ctx, rng):
    h = [d for d in docs if d["kind"] == "HorizontalPodAutoscaler"]
    if h:
        h[0]["spec"]["minReplicas"], h[0]["spec"]["maxReplicas"] = h[0]["spec"]["maxReplicas"], h[0]["spec"]["minReplicas"]
        return {"_phr": [0]}
    kind_of(docs, "Deployment")["spec"]["replicas"] = 1
    kind_of(docs, "PodDisruptionBudget")["spec"]["minAvailable"] = 1
    return {"_phr": [1]}


def d_replicas_hpa(docs, ctx, rng):
    kind_of(docs, "Deployment")["spec"]["replicas"] = 3
    if not any(d["kind"] == "HorizontalPodAutoscaler" for d in docs):
        del kind_of(docs, "Deployment")["spec"]["replicas"]
        return {"_phr": [2]}
    return {"_phr": [0, 1]}


def d_namespace(docs, ctx, rng):
    kind_of(docs, "Service")["metadata"]["namespace"] = "default"
    return {}


def d_pathtype(docs, ctx, rng):
    del kind_of(docs, "Ingress")["spec"]["rules"][0]["http"]["paths"][0]["pathType"]
    return {}


def d_ing_backend(docs, ctx, rng):
    path = kind_of(docs, "Ingress")["spec"]["rules"][0]["http"]["paths"][0]
    path["backend"] = {"serviceName": ctx["p"]["app"], "servicePort": ctx["p"]["svc_port"]}
    return {}


def d_ing_class(docs, ctx, rng):
    ing = kind_of(docs, "Ingress")
    del ing["spec"]["ingressClassName"]
    return {}


def d_mount(docs, ctx, rng):
    kind_of(docs, "Deployment")["spec"]["template"]["spec"]["volumes"].pop(0)
    return {}


def d_pdb(docs, ctx, rng):
    pdb = kind_of(docs, "PodDisruptionBudget")
    floor = next((d["spec"]["minReplicas"] for d in docs if d["kind"] == "HorizontalPodAutoscaler"), kind_of(docs, "Deployment")["spec"].get("replicas"))
    pdb["spec"]["minAvailable"] = floor
    return {}


def d_pdb_sel(docs, ctx, rng):
    kind_of(docs, "PodDisruptionBudget")["spec"]["selector"]["matchLabels"] = {"app.kubernetes.io/name": ctx["p"]["app"] + "-pdb"}
    return {}


def d_indent(docs, ctx, rng):
    def post(files):
        t = files["k8s/app.yaml"]
        t = t.replace("\n      containers:\n", "\n     containers:\n", 1)
        try:
            Y.load_all(t.replace("---\n", "\n---\n"))
        except ValueError:
            files["k8s/app.yaml"] = t
            return files
        raise RuntimeError("indentation defect did not break the YAML")
    return {"_post": post}


DEFECTS = {
    "selector": (d_selector, ["the Service has no endpoints: it selects nothing", "traffic to the Service goes nowhere (`kubectl get endpoints` is empty)"]),
    "match-labels": (d_match_labels, ["the Deployment is rejected: its selector does not match the pod template labels", "`kubectl apply` fails with `selector does not match template labels`"]),
    "api-ing": (d_api_ing, ["the Ingress uses an API version that this cluster (1.30) no longer serves", "`kubectl apply` says no matches for kind Ingress in version networking.k8s.io/v1beta1"]),
    "hpa-api": (d_hpa_api, ["the HPA and PDB use API versions that were removed from the cluster", "`autoscaling/v2beta1` and `policy/v1beta1` are not served any more"]),
    "target-port": (d_target_port, ["the Service forwards to a port nothing listens on", "connections through the Service are refused"]),
    "no-resources": (d_no_resources, ["the container has no resource limits (the namespace quota admission rejects it)", "the pod is rejected by the quota admission webhook: limits are missing"]),
    "req-gt-lim": (d_req_gt_lim, ["the pod is rejected: the memory request is bigger than its limit", "validation error: requests.memory must be less than or equal to the limit"]),
    "bad-qty": (d_bad_qty, ["the apply fails with `quantities must match the regular expression` for a memory limit", "a memory limit is written in a unit Kubernetes does not know"]),
    "no-probe": (d_no_probe, ["traffic is sent to pods that are not ready yet", "the readiness probe is gone, so rollouts take down the service"]),
    "probe-port": (d_probe_port, ["the liveness probe keeps killing healthy pods (connection refused)", "pods restart in a loop because of the liveness probe"]),
    "root": (d_root, ["the admission policy rejects the pod: it runs as root and privileged", "the security scan flags the pod: privileged container, may run as root"]),
    "latest": (d_latest, ["the image is `:latest`, so nodes pull different builds", "the deployment uses a floating `latest` image"]),
    "cm-key": (d_cm_key, ["the pod is stuck in CreateContainerConfigError (a config key can't be found)", "an env var points to a ConfigMap key that doesn't exist"]),
    "cm-name": (d_cm_name, ["the pod is stuck in ContainerCreating: a configMap volume is missing", "the config volume refers to a ConfigMap that does not exist"]),
    "hpa-target": (d_hpa_target, ["the autoscaler can't find its target (`scaleTargetRef`)", "the PDB blocks every eviction, including node drains"]),
    "hpa-range": (d_hpa_range, ["the autoscaler is invalid: min and max replicas are in the wrong order", "the Deployment runs a single replica and the PDB requires it to stay up"]),
    "replicas-hpa": (d_replicas_hpa, ["every apply resets the replica count that the HPA set", "the Deployment hard-codes replicas although an HPA scales it", "the Deployment ends up with a single pod: nobody sets the replica count"]),
    "namespace": (d_namespace, ["the Service lands in the `default` namespace instead of the app's", "one object is applied to the wrong namespace"]),
    "pathtype": (d_pathtype, ["the Ingress is invalid: `pathType` is required", "`kubectl apply` fails on the Ingress path (pathType)"]),
    "ing-backend": (d_ing_backend, ["the Ingress backend uses the old `serviceName`/`servicePort` syntax", "the Ingress backend is rejected (unknown field `serviceName`)"]),
    "ing-class": (d_ing_class, ["no ingress controller picks up the Ingress", "the Ingress has no class and is ignored"]),
    "mount": (d_mount, ["the pod is invalid: a volumeMount has no matching volume", "`kubectl apply` complains `volumeMounts[0].name: Not found`"]),
    "pdb": (d_pdb, ["node drains hang forever because of the PDB", "the PodDisruptionBudget does not allow a single pod to be evicted"]),
    "pdb-sel": (d_pdb_sel, ["the PodDisruptionBudget protects no pods", "the PDB selector matches nothing"]),
    "indent": (d_indent, ["`kubectl apply` reports a YAML parse error", "the manifest stopped parsing after an editor reindented a block"]),
}


def docs_files(model, ctx):
    p, r = ctx["p"], ctx["rules"]
    rules_md = dd(f'''
        # Manifest rules for {p["app"]}

        `k8s/app.yaml` (one file, several YAML documents) is validated mechanically against these rules (YAML is read with Ruby's Psych).

        1. **Objects.** The file holds exactly one object of each kind: {", ".join(r["kinds"])}. API versions: Deployment `apps/v1`, Service and ConfigMap `v1`,
           HorizontalPodAutoscaler `autoscaling/v2`, PodDisruptionBudget `policy/v1`, Ingress `networking.k8s.io/v1`. Every object is in the namespace `{p["ns"]}`.
        2. **Names.** The Deployment and the Service are called `{p["app"]}`, the container `{p["app"]}`, the ConfigMap `{r["configmap"]}`.
        3. **Selectors.** The Deployment's `selector.matchLabels` is a subset of the pod template labels, the pod labels include `app.kubernetes.io/name: {p["app"]}`,
           and the selectors of the Service and of the PodDisruptionBudget select those pods.
        4. **Container.** Image `{p["image"]}:<fixed version>` (no `latest`); a port named `{p["port_name"]}` = {p["port"]};
           `resources.requests` and `resources.limits` for both cpu and memory, written as valid quantities (cpu `500m`/`1`/`0.5`; memory with Ki/Mi/Gi or K/M/G; `512MB` is not valid) with request <= limit;
           `readinessProbe` and `livenessProbe` of type httpGet on the container port (by name or number) with a path;
           `securityContext` with `runAsNonRoot: true`, `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, and no `privileged`;
           since the root file system is read-only, an `emptyDir` volume `tmp` is mounted at `/tmp`.
        5. **Wiring.** Every `configMapKeyRef` names the ConfigMap `{r["configmap"]}` and an existing key; every `secretKeyRef` names `{p["secret"]}`;
           every `volumeMount` has a matching pod volume; a `configMap` volume names the ConfigMap above.
        6. **Service.** One port: `{p["svc_port"]}` with a `targetPort` that is the container port (name or number).
        7. **Scaling.** With a HorizontalPodAutoscaler: it targets the Deployment `{p["app"]}`, has integers `1 <= minReplicas <= maxReplicas`, Resource metrics with `target.averageUtilization`,
           and the Deployment must not set `replicas`. Without one: `replicas >= 2`. The PodDisruptionBudget uses `minAvailable` (not maxUnavailable), smaller than the minimum replica count.
        8. **Ingress.** `ingressClassName: {p["cls"]}`, one rule for host `{p["host"]}`, every path has a `pathType` and a backend `service` named `{p["app"]}`
           with port number {p["svc_port"]} (the old `serviceName`/`servicePort` form is not valid in `networking.k8s.io/v1`).
    ''')
    return {"MANIFEST_RULES.md": rules_md, "README.md": f"# {p['app']}\n\nKubernetes manifests for the `{p['app']}` service in namespace `{p['ns']}`; everything is in `k8s/app.yaml`. Rules: `MANIFEST_RULES.md`.\n"}


def hidden(model, ctx):
    return {"tests/rules.json": json.dumps(ctx["rules"], indent=1) + "\n"}


def prompt(rng, ctx, texts, vague):
    p = ctx["p"]
    return K.fix_prompt(rng, "k8s/app.yaml", f"manifests of {p['app']}", texts, "MANIFEST_RULES.md", vague, [
        f"`k8s/app.yaml` for {p['app']} fails our manifest review (`MANIFEST_RULES.md`) and the cluster rejects part of it. Fix everything that is wrong; keep all objects and values that are fine.",
        f"The manifests of {p['app']} in `k8s/app.yaml` don't satisfy `MANIFEST_RULES.md`. Make the file compliant without dropping any object.",
    ])


def wrong(docs, ctx):
    w1 = copy.deepcopy(docs)
    w1 = [d for d in w1 if d["kind"] != "PodDisruptionBudget"]
    w2 = copy.deepcopy(docs)
    cont(w2)["securityContext"]["runAsNonRoot"] = False
    return [render(w1, ctx), render(w2, ctx)]


PLAN = [
    {"keys": ["selector"], "d": 2}, {"keys": ["api-ing"], "d": 1}, {"keys": ["indent"], "d": 1}, {"keys": ["no-probe", "latest"], "d": 2}, {"keys": ["req-gt-lim", "namespace"]},
    {"keys": ["cm-key", "ing-backend"]}, {"keys": ["hpa-api", "pathtype"]}, {"keys": ["probe-port", "target-port"]}, {"keys": ["root", "mount", "bad-qty"]}, {"keys": ["match-labels", "pdb"]},
    {"keys": ["hpa-target", "replicas-hpa", "ing-class"]}, {"keys": ["cm-name", "pdb-sel", "no-resources"]}, {"keys": ["indent", "selector", "root", "cm-key"], "d": 4},
    {"keys": ["api-ing", "hpa-api", "ing-backend", "pathtype", "ing-class"], "d": 4}, {"keys": ["hpa-range", "bad-qty", "latest", "namespace", "mount", "target-port"], "vague": True, "d": 5},
    {"keys": ["match-labels", "no-resources", "probe-port", "replicas-hpa", "pdb", "cm-name"], "vague": True, "d": 5}, {"keys": ["latest"], "d": 1}, {"keys": ["no-resources"], "d": 2},
]


@family("devops-k8s-manifests", category="devops", lang="text", kind="fix", n=len(PLAN),
        summary="repair Kubernetes manifests (Deployment/Service/ConfigMap/HPA/PDB/Ingress) against a mechanical policy: selectors, quantities, probes, wiring, removed API versions")
def k8s_manifests(rng, n):
    return K.fix_tasks(rng, n, prefix="k8s", plan=PLAN, build=build, render=render, defects=DEFECTS, docs=docs_files, hidden=hidden, check=CHECK_K8S,
                       prompt=prompt, wrong=wrong, tags=["kubernetes", "k8s", "yaml"])
