"""DevOps tasks: JSON Schema for configuration (Helm-values style). A documented validator (given to the agent as tools/schemacheck.py) accepts or rejects hidden documents."""
import copy
import json
import types
from dataclasses import dataclass, field

from fx import dd, family
from generators.devops import _dokit as K
from generators.devops._schemasim import SCHEMASIM


def pd(text, note):
    """dedent the text first and then append the note (dedenting after the concatenation does nothing)"""
    t = dd(text).rstrip("\n")
    return t + (note if note.startswith("\n") or t.endswith(" ") else " " + note)


_mod = types.ModuleType("schemacheck")
exec(compile(SCHEMASIM, "schemacheck.py", "exec"), _mod.__dict__)
sc = _mod

CHECK_SCHEMA = r'''
from dolib import *
sys.path.insert(0, "tests")
import schemacheck


spec = json.load(open("tests/docs.json", encoding="utf-8"))
try:
    root = schemacheck.load_schema(spec["path"])
except schemacheck.SchemaError as e:
    die(f"{spec['path']}: {e}")
rep = Report()
for name, doc in spec["valid"].items():
    errs = []
    schemacheck.validate(root, doc, root, "", errs)
    rep.check(not errs, f"valid document {name!r} is rejected: {errs[0] if errs else ''}")
for name, doc in spec["invalid"].items():
    errs = []
    schemacheck.validate(root, doc, root, "", errs)
    rep.check(bool(errs), f"invalid document {name!r} ({spec['why'].get(name, '')}) is accepted")
rep.finish()
'''


@dataclass
class SchemaSpec:
    slug: str
    d: int
    prompt: str
    ref: dict
    start: str
    valid: dict  # name -> doc
    invalid: dict  # name -> (doc, why)
    show_valid: list
    show_invalid: list
    wrong: list = field(default_factory=list)
    kind: str = "author"


def dumps(o):
    return json.dumps(o, indent=2) + "\n"


def make_task(sp: SchemaSpec):
    root = sp.ref
    sc.check_schema(root, root)
    for n, doc in sp.valid.items():
        errs = []
        sc.validate(root, doc, root, "", errs)
        if errs:
            raise RuntimeError(f"{sp.slug}: valid doc {n} rejected by the reference: {errs}")
    for n, (doc, why) in sp.invalid.items():
        errs = []
        sc.validate(root, doc, root, "", errs)
        if not errs:
            raise RuntimeError(f"{sp.slug}: invalid doc {n} accepted by the reference")
    start = {"values.schema.json": sp.start, "tools/schemacheck.py": SCHEMASIM, "README.md": "# values schema exercise\n\nEdit `values.schema.json`. `python3 tools/schemacheck.py values.schema.json examples/valid examples/invalid` checks the example documents; `python3 tools/schemacheck.py` prints the supported JSON Schema subset.\n"}
    for n in sp.show_valid:
        start[f"examples/valid/{n}.json"] = dumps(sp.valid[n])
    for n in sp.show_invalid:
        start[f"examples/invalid/{n}.json"] = dumps(sp.invalid[n][0])
    spec = {"path": "values.schema.json", "valid": sp.valid, "invalid": {n: v[0] for n, v in sp.invalid.items()}, "why": {n: v[1] for n, v in sp.invalid.items()}}
    hidden = {"tests/schemacheck.py": "# verifier copy of tools/schemacheck.py\n" + SCHEMASIM, "tests/docs.json": json.dumps(spec, indent=1) + "\n"}
    t = K.devops_task(sp.slug, sp.d, sp.prompt, start, {"values.schema.json": dumps(root)}, CHECK_SCHEMA, hidden, lang="text", kind="fix" if sp.kind == "fix" else "greenfield", tags=["json-schema", "helm", "validation", "config"])
    return K.finish(t, wrong=[{"values.schema.json": dumps(w) if isinstance(w, dict) else w} for w in sp.wrong])


SPECS: list[SchemaSpec] = []


def spec(**kw):
    SPECS.append(SchemaSpec(**kw))


NOTE = "\n\n`tools/schemacheck.py` is the validator that will be used (its docstring lists the supported keywords); `examples/valid` and `examples/invalid` hold a few documents each (the checker uses many more)."
STR, INT, BOOL, OBJ, ARR = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}, {"type": "object"}, {"type": "array"}

# 1 ------------------------------------------------------------------------------------------------------------------
spec(slug="values-basics", d=1, kind="author",
     prompt=pd('''
        Write `values.schema.json` (JSON Schema) for the values file of the chart `lumen`:

        - the document is an object with exactly these properties and no others: `replicaCount` (required, integer, at least 1), `image` (required, object) and `nameOverride` (optional, string);
        - `image` has exactly the properties `repository` (required, string, not empty) and `tag` (required, string).
     ''', NOTE),
     start='{\n  "$schema": "http://json-schema.org/draft-07/schema#",\n  "type": "object"\n}\n',
     ref={"$schema": "http://json-schema.org/draft-07/schema#", "type": "object", "required": ["replicaCount", "image"], "additionalProperties": False,
          "properties": {"replicaCount": {"type": "integer", "minimum": 1}, "nameOverride": STR,
                         "image": {"type": "object", "required": ["repository", "tag"], "additionalProperties": False, "properties": {"repository": {"type": "string", "minLength": 1}, "tag": STR}}}},
     valid={"minimal": {"replicaCount": 1, "image": {"repository": "reg.example/lumen", "tag": "1.4.2"}}, "with-name": {"replicaCount": 3, "nameOverride": "lm", "image": {"repository": "lumen", "tag": "latest"}},
            "float-integer": {"replicaCount": 2.0, "image": {"repository": "a", "tag": "b"}}, "empty-tag": {"replicaCount": 5, "image": {"repository": "x", "tag": ""}}, "empty-name": {"replicaCount": 1, "nameOverride": "", "image": {"repository": "x", "tag": "1"}}},
     invalid={"no-image": ({"replicaCount": 1}, "image is required"), "zero-replicas": ({"replicaCount": 0, "image": {"repository": "x", "tag": "1"}}, "replicaCount below 1"), "string-replicas": ({"replicaCount": "2", "image": {"repository": "x", "tag": "1"}}, "replicaCount is a string"),
              "fractional": ({"replicaCount": 1.5, "image": {"repository": "x", "tag": "1"}}, "replicaCount not an integer"), "numeric-tag": ({"replicaCount": 1, "image": {"repository": "x", "tag": 1}}, "tag must be a string"),
              "extra-root": ({"replicaCount": 1, "image": {"repository": "x", "tag": "1"}, "foo": 1}, "unknown root property"), "extra-image": ({"replicaCount": 1, "image": {"repository": "x", "tag": "1", "pullPolicy": "Always"}}, "unknown image property"),
              "empty-repo": ({"replicaCount": 1, "image": {"repository": "", "tag": "1"}}, "empty repository"), "no-tag": ({"replicaCount": 1, "image": {"repository": "x"}}, "tag is required"), "array-root": ([1], "root must be an object"),
              "bool-replicas": ({"replicaCount": True, "image": {"repository": "x", "tag": "1"}}, "a boolean is not an integer"), "name-number": ({"replicaCount": 1, "nameOverride": 7, "image": {"repository": "x", "tag": "1"}}, "nameOverride must be a string"),
              "no-replicas": ({"image": {"repository": "x", "tag": "1"}}, "replicaCount is required"), "image-string": ({"replicaCount": 1, "image": "x:1"}, "image must be an object")},
     show_valid=["minimal", "with-name"], show_invalid=["no-image", "zero-replicas", "extra-root"],
     wrong=[{"type": "object", "required": ["replicaCount", "image"], "properties": {"replicaCount": {"type": "integer", "minimum": 1}, "nameOverride": STR, "image": {"type": "object", "required": ["repository", "tag"], "properties": {"repository": STR, "tag": STR}}}}])

# 2 ------------------------------------------------------------------------------------------------------------------
spec(slug="values-ranges-enums", d=2, kind="author",
     prompt=pd('''
        Write `values.schema.json` for the chart `kestrel`. All objects below reject properties that are not listed.

        - root properties: `service` (required), `logLevel`, `resources`, `timeoutSeconds`;
        - `service`: `type` (required; one of `ClusterIP`, `NodePort`, `LoadBalancer`), `port` (required; integer 1 to 65535), `nodePort` (optional; integer 30000 to 32767);
        - `logLevel`: one of `debug`, `info`, `warn`, `error`;
        - `resources`: only `limits`, an object with only `cpu` (a string of digits, optionally followed by `m`: `500m`, `2`) and `memory` (digits followed by `Mi` or `Gi`: `512Mi`); both optional;
        - `timeoutSeconds`: a number greater than 0 and at most 300, a multiple of 0.5.
     ''', NOTE),
     start='{\n  "type": "object"\n}\n',
     ref={"type": "object", "required": ["service"], "additionalProperties": False,
          "properties": {"service": {"type": "object", "required": ["type", "port"], "additionalProperties": False, "properties": {"type": {"enum": ["ClusterIP", "NodePort", "LoadBalancer"]}, "port": {"type": "integer", "minimum": 1, "maximum": 65535}, "nodePort": {"type": "integer", "minimum": 30000, "maximum": 32767}}},
                         "logLevel": {"enum": ["debug", "info", "warn", "error"]},
                         "resources": {"type": "object", "additionalProperties": False, "properties": {"limits": {"type": "object", "additionalProperties": False, "properties": {"cpu": {"type": "string", "pattern": "^[0-9]+m?$"}, "memory": {"type": "string", "pattern": "^[0-9]+(Mi|Gi)$"}}}}},
                         "timeoutSeconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 300, "multipleOf": 0.5}}},
     valid={"min": {"service": {"type": "ClusterIP", "port": 80}}, "full": {"service": {"type": "NodePort", "port": 8080, "nodePort": 30080}, "logLevel": "warn", "resources": {"limits": {"cpu": "500m", "memory": "512Mi"}}, "timeoutSeconds": 2.5},
            "edges": {"service": {"type": "LoadBalancer", "port": 65535, "nodePort": 32767}, "logLevel": "error", "timeoutSeconds": 300}, "low-edges": {"service": {"type": "ClusterIP", "port": 1, "nodePort": 30000}, "resources": {"limits": {"cpu": "2", "memory": "1Gi"}}, "timeoutSeconds": 0.5},
            "empty-resources": {"service": {"type": "ClusterIP", "port": 9}, "resources": {}}},
     invalid={"no-service": ({"logLevel": "info"}, "service is required"), "bad-type": ({"service": {"type": "ExternalName", "port": 80}}, "unknown service type"), "port-zero": ({"service": {"type": "ClusterIP", "port": 0}}, "port too low"), "port-high": ({"service": {"type": "ClusterIP", "port": 65536}}, "port too high"),
              "port-string": ({"service": {"type": "ClusterIP", "port": "80"}}, "port must be an integer"), "nodeport-low": ({"service": {"type": "NodePort", "port": 80, "nodePort": 29999}}, "nodePort too low"), "nodeport-high": ({"service": {"type": "NodePort", "port": 80, "nodePort": 32768}}, "nodePort too high"),
              "bad-level": ({"service": {"type": "ClusterIP", "port": 80}, "logLevel": "trace"}, "unknown log level"), "level-case": ({"service": {"type": "ClusterIP", "port": 80}, "logLevel": "INFO"}, "log levels are lower case"), "cpu-unit": ({"service": {"type": "ClusterIP", "port": 80}, "resources": {"limits": {"cpu": "0.5core"}}}, "bad cpu"),
              "mem-unit": ({"service": {"type": "ClusterIP", "port": 80}, "resources": {"limits": {"memory": "512MB"}}}, "bad memory unit"), "mem-lower": ({"service": {"type": "ClusterIP", "port": 80}, "resources": {"limits": {"memory": "512mi"}}}, "unit is case sensitive"),
              "mem-number": ({"service": {"type": "ClusterIP", "port": 80}, "resources": {"limits": {"memory": 512}}}, "memory must be a string"), "requests": ({"service": {"type": "ClusterIP", "port": 80}, "resources": {"requests": {"cpu": "1"}}}, "only limits allowed"),
              "timeout-zero": ({"service": {"type": "ClusterIP", "port": 80}, "timeoutSeconds": 0}, "timeout must be positive"), "timeout-big": ({"service": {"type": "ClusterIP", "port": 80}, "timeoutSeconds": 300.5}, "timeout too large"),
              "timeout-step": ({"service": {"type": "ClusterIP", "port": 80}, "timeoutSeconds": 1.3}, "not a multiple of 0.5"), "extra-service": ({"service": {"type": "ClusterIP", "port": 80, "protocol": "TCP"}}, "unknown service property"), "extra-root": ({"service": {"type": "ClusterIP", "port": 80}, "replicas": 2}, "unknown root property"),
              "cpu-empty": ({"service": {"type": "ClusterIP", "port": 80}, "resources": {"limits": {"cpu": ""}}}, "empty cpu"), "cpu-trailing": ({"service": {"type": "ClusterIP", "port": 80}, "resources": {"limits": {"cpu": "500mm"}}}, "anchored pattern needed")},
     show_valid=["min", "full"], show_invalid=["bad-type", "port-high", "mem-unit", "timeout-step"],
     wrong=[{"type": "object", "required": ["service"], "additionalProperties": False, "properties": {"service": {"type": "object", "required": ["type", "port"], "properties": {"type": {"enum": ["ClusterIP", "NodePort", "LoadBalancer"]}, "port": {"type": "integer", "minimum": 1, "maximum": 65535}, "nodePort": {"type": "integer", "minimum": 30000, "maximum": 32767}}},
                                                                                                   "logLevel": {"enum": ["debug", "info", "warn", "error"]}, "resources": {"type": "object", "properties": {"limits": {"type": "object", "properties": {"cpu": {"type": "string", "pattern": "[0-9]+m?"}, "memory": {"type": "string", "pattern": "[0-9]+(Mi|Gi)"}}}}},
                                                                                                   "timeoutSeconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 300, "multipleOf": 0.5}}}])

# 3 ------------------------------------------------------------------------------------------------------------------
HOST = "^([a-z0-9]([a-z0-9-]*[a-z0-9])?\\.)+[a-z]{2,}$"
spec(slug="values-arrays", d=3, kind="author",
     prompt=pd('''
        Write `values.schema.json` for the chart `marlin`. Objects reject unlisted properties unless stated.

        - `ingress` (optional object with only `hosts`): `hosts` is an array of 1 to 5 objects with exactly `host` (required; a lower-case DNS name such as `shop.example.com`: labels of lower-case letters, digits and inner hyphens separated by dots, ending in a top-level label of at least two letters)
          and `paths` (required; an array with at least one item, all strings starting with `/`, no duplicates);
        - `env` (optional): an array of objects with exactly `name` (required; upper-case letters, digits and underscores, starting with a letter) and `value` (required; string);
        - `args` (optional): an array of at most 10 strings;
        - `nodeSelector` (optional): an object whose property names start with a lower-case letter and consist of letters, digits, `.`, `/` or `-`, and whose values are all strings.
        The root object has only these properties: `ingress`, `env`, `args`, `nodeSelector`.
     ''', NOTE),
     start='{\n  "type": "object"\n}\n',
     ref={"type": "object", "additionalProperties": False,
          "properties": {"ingress": {"type": "object", "additionalProperties": False, "properties": {"hosts": {"type": "array", "minItems": 1, "maxItems": 5, "items": {"type": "object", "required": ["host", "paths"], "additionalProperties": False,
                                                                                                                                                                       "properties": {"host": {"type": "string", "pattern": HOST}, "paths": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "string", "pattern": "^/"}}}}}}},
                         "env": {"type": "array", "items": {"type": "object", "required": ["name", "value"], "additionalProperties": False, "properties": {"name": {"type": "string", "pattern": "^[A-Z][A-Z0-9_]*$"}, "value": STR}}},
                         "args": {"type": "array", "maxItems": 10, "items": STR},
                         "nodeSelector": {"type": "object", "propertyNames": {"pattern": "^[a-z][a-zA-Z0-9./-]*$"}, "additionalProperties": STR}}},
     valid={"empty": {}, "ingress": {"ingress": {"hosts": [{"host": "shop.example.com", "paths": ["/", "/api"]}]}}, "five-hosts": {"ingress": {"hosts": [{"host": f"h{i}.a-b.example.org", "paths": ["/x"]} for i in range(5)]}},
            "env": {"env": [{"name": "LOG_LEVEL", "value": "debug"}, {"name": "A1", "value": ""}]}, "args": {"args": ["--port", "80", ""]}, "ten-args": {"args": [str(i) for i in range(10)]},
            "selector": {"nodeSelector": {"kubernetes.io/os": "linux", "disk": "ssd", "topology.example.com/zone": "a"}}, "all": {"ingress": {"hosts": [{"host": "a.io", "paths": ["/"]}]}, "env": [], "args": [], "nodeSelector": {}}},
     invalid={"no-hosts": ({"ingress": {"hosts": []}}, "at least one host"), "six-hosts": ({"ingress": {"hosts": [{"host": f"h{i}.example.org", "paths": ["/"]} for i in range(6)]}}, "at most 5 hosts"), "upper-host": ({"ingress": {"hosts": [{"host": "Shop.example.com", "paths": ["/"]}]}}, "host must be lower case"),
              "no-tld": ({"ingress": {"hosts": [{"host": "shop", "paths": ["/"]}]}}, "needs a dotted name"), "short-tld": ({"ingress": {"hosts": [{"host": "shop.example.c", "paths": ["/"]}]}}, "tld needs two letters"), "leading-hyphen": ({"ingress": {"hosts": [{"host": "-shop.example.com", "paths": ["/"]}]}}, "label can't start with a hyphen"),
              "trailing-hyphen": ({"ingress": {"hosts": [{"host": "shop-.example.com", "paths": ["/"]}]}}, "label can't end with a hyphen"), "underscore": ({"ingress": {"hosts": [{"host": "my_shop.example.com", "paths": ["/"]}]}}, "underscore not allowed"),
              "no-paths": ({"ingress": {"hosts": [{"host": "a.example.com"}]}}, "paths required"), "empty-paths": ({"ingress": {"hosts": [{"host": "a.example.com", "paths": []}]}}, "at least one path"), "relative-path": ({"ingress": {"hosts": [{"host": "a.example.com", "paths": ["api"]}]}}, "path must start with /"),
              "dup-paths": ({"ingress": {"hosts": [{"host": "a.example.com", "paths": ["/a", "/a"]}]}}, "duplicate paths"), "path-number": ({"ingress": {"hosts": [{"host": "a.example.com", "paths": [1]}]}}, "path must be a string"), "extra-host-prop": ({"ingress": {"hosts": [{"host": "a.example.com", "paths": ["/"], "tls": True}]}}, "unknown host property"),
              "ingress-extra": ({"ingress": {"enabled": True, "hosts": [{"host": "a.example.com", "paths": ["/"]}]}}, "unknown ingress property"), "env-lower": ({"env": [{"name": "log_level", "value": "x"}]}, "env name must be upper case"), "env-digit-first": ({"env": [{"name": "1A", "value": "x"}]}, "env name starts with a letter"),
              "env-no-value": ({"env": [{"name": "A"}]}, "value required"), "env-number": ({"env": [{"name": "A", "value": 1}]}, "value must be a string"), "env-object": ({"env": {"A": "1"}}, "env must be an array"), "eleven-args": ({"args": [str(i) for i in range(11)]}, "at most 10 args"),
              "arg-number": ({"args": ["--port", 80]}, "args are strings"), "selector-number": ({"nodeSelector": {"disk": 1}}, "selector values are strings"), "selector-upper": ({"nodeSelector": {"Disk": "ssd"}}, "selector key lower case first"), "selector-space": ({"nodeSelector": {"my disk": "ssd"}}, "no spaces in keys"),
              "root-extra": ({"replicas": 2}, "unknown root property")},
     show_valid=["empty", "ingress", "selector"], show_invalid=["no-hosts", "upper-host", "dup-paths", "env-lower"],
     wrong=[{"type": "object", "properties": {"ingress": {"type": "object", "properties": {"hosts": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["host", "paths"], "properties": {"host": STR, "paths": {"type": "array", "items": STR}}}}}},
                                              "env": {"type": "array"}, "args": {"type": "array"}, "nodeSelector": {"type": "object"}}}])

# 4 ------------------------------------------------------------------------------------------------------------------
spec(slug="values-conditional", d=4, kind="author",
     prompt=pd('''
        Write `values.schema.json` for the chart `osprey`. Objects reject unlisted properties.

        - root properties (all optional): `ingress`, `autoscaling`, `tls`, `persistence`;
        - `ingress`: `enabled` (required boolean), `hosts` (array of strings), `className` (string); **when `enabled` is true, `hosts` is required and must have at least one item**;
        - `autoscaling`: `enabled` (required boolean), `minReplicas`, `maxReplicas` (integers, at least 1); when `enabled` is true both `minReplicas` and `maxReplicas` are required;
        - `tls`: `enabled` (required boolean), `secretName` (non-empty string); when `enabled` is true `secretName` is required;
        - `persistence`: `size` (string such as `10Gi`: digits then `Mi`, `Gi` or `Ti`) and `storageClass` (string); `storageClass` may only be given together with `size` (use `dependentRequired`).
     ''', NOTE),
     start='{\n  "type": "object"\n}\n',
     ref={"type": "object", "additionalProperties": False, "properties": {
         "ingress": {"type": "object", "required": ["enabled"], "additionalProperties": False, "properties": {"enabled": BOOL, "hosts": {"type": "array", "items": STR}, "className": STR}, "if": {"properties": {"enabled": {"const": True}}, "required": ["enabled"]}, "then": {"required": ["hosts"], "properties": {"hosts": {"minItems": 1}}}},
         "autoscaling": {"type": "object", "required": ["enabled"], "additionalProperties": False, "properties": {"enabled": BOOL, "minReplicas": {"type": "integer", "minimum": 1}, "maxReplicas": {"type": "integer", "minimum": 1}}, "if": {"properties": {"enabled": {"const": True}}, "required": ["enabled"]}, "then": {"required": ["minReplicas", "maxReplicas"]}},
         "tls": {"type": "object", "required": ["enabled"], "additionalProperties": False, "properties": {"enabled": BOOL, "secretName": {"type": "string", "minLength": 1}}, "if": {"properties": {"enabled": {"const": True}}, "required": ["enabled"]}, "then": {"required": ["secretName"]}},
         "persistence": {"type": "object", "additionalProperties": False, "properties": {"size": {"type": "string", "pattern": "^[0-9]+(Mi|Gi|Ti)$"}, "storageClass": STR}, "dependentRequired": {"storageClass": ["size"]}}}},
     valid={"empty": {}, "ingress-off": {"ingress": {"enabled": False}}, "ingress-off-hosts": {"ingress": {"enabled": False, "hosts": []}}, "ingress-on": {"ingress": {"enabled": True, "hosts": ["a.example.com"], "className": "nginx"}}, "hpa-off": {"autoscaling": {"enabled": False}},
            "hpa-off-partial": {"autoscaling": {"enabled": False, "minReplicas": 2}}, "hpa-on": {"autoscaling": {"enabled": True, "minReplicas": 2, "maxReplicas": 8}}, "tls-off": {"tls": {"enabled": False}}, "tls-on": {"tls": {"enabled": True, "secretName": "cert"}},
            "pvc": {"persistence": {"size": "10Gi", "storageClass": "fast"}}, "pvc-size": {"persistence": {"size": "500Mi"}}, "pvc-empty": {"persistence": {}}},
     invalid={"ingress-on-no-hosts": ({"ingress": {"enabled": True}}, "enabled ingress needs hosts"), "ingress-on-empty": ({"ingress": {"enabled": True, "hosts": []}}, "needs at least one host"), "ingress-no-enabled": ({"ingress": {"hosts": ["a.example.com"]}}, "enabled is required"),
              "ingress-enabled-string": ({"ingress": {"enabled": "true", "hosts": ["a"]}}, "enabled must be boolean"), "ingress-host-number": ({"ingress": {"enabled": False, "hosts": [1]}}, "hosts are strings"), "hpa-on-no-min": ({"autoscaling": {"enabled": True, "maxReplicas": 4}}, "min required"),
              "hpa-on-no-max": ({"autoscaling": {"enabled": True, "minReplicas": 1}}, "max required"), "hpa-zero": ({"autoscaling": {"enabled": False, "minReplicas": 0}}, "min at least 1"), "hpa-float": ({"autoscaling": {"enabled": True, "minReplicas": 1.5, "maxReplicas": 4}}, "integers"),
              "tls-on-no-secret": ({"tls": {"enabled": True}}, "secretName required"), "tls-empty-secret": ({"tls": {"enabled": True, "secretName": ""}}, "secretName not empty"), "tls-extra": ({"tls": {"enabled": False, "issuer": "x"}}, "unknown tls property"),
              "pvc-class-only": ({"persistence": {"storageClass": "fast"}}, "storageClass needs size"), "pvc-bad-size": ({"persistence": {"size": "10GB"}}, "bad size unit"), "pvc-lower": ({"persistence": {"size": "10gi"}}, "units are case sensitive"),
              "pvc-no-unit": ({"persistence": {"size": "10"}}, "unit required"), "pvc-extra": ({"persistence": {"size": "1Gi", "accessMode": "RWO"}}, "unknown persistence property"), "root-extra": ({"replicaCount": 1}, "unknown root property"), "ingress-null": ({"ingress": None}, "ingress must be an object")},
     show_valid=["empty", "ingress-off", "ingress-on", "hpa-on"], show_invalid=["ingress-on-no-hosts", "hpa-on-no-min", "pvc-class-only", "tls-on-no-secret"],
     wrong=[{"type": "object", "additionalProperties": False, "properties": {"ingress": {"type": "object", "required": ["enabled", "hosts"], "properties": {"enabled": BOOL, "hosts": {"type": "array", "minItems": 1}, "className": STR}},
                                                                             "autoscaling": {"type": "object", "required": ["enabled", "minReplicas", "maxReplicas"], "properties": {"enabled": BOOL, "minReplicas": INT, "maxReplicas": INT}},
                                                                             "tls": {"type": "object", "required": ["enabled", "secretName"], "properties": {"enabled": BOOL, "secretName": STR}},
                                                                             "persistence": {"type": "object", "properties": {"size": STR, "storageClass": STR}}}}])

# 5 ------------------------------------------------------------------------------------------------------------------
spec(slug="values-oneof-refs", d=4, kind="author",
     prompt=pd('''
        Write `values.schema.json` for the chart `heron`, sharing definitions with `$defs` and `$ref` (the checker accepts any layout that behaves right). Objects reject unlisted properties unless stated.

        - definitions to share: a *port* (integer 1 to 65535), a *quantity* (string: digits then `Mi` or `Gi`), and a *label map* (an object whose property names are made of lower-case letters, digits, `.`, `-` and `/` and whose values are all strings);
        - root properties (all optional): `service` (only `port`, a port, required), `metrics` (only `enabled` boolean required and `port` a port), `podLabels` and `podAnnotations` (label maps), `persistence`;
        - `persistence` must match exactly one of two shapes: `{"enabled": false}` and nothing else, or `enabled` true with `size` (a quantity, required) and optionally `storageClass` (string) and nothing else.
     ''', NOTE),
     start='{\n  "type": "object"\n}\n',
     ref={"$defs": {"port": {"type": "integer", "minimum": 1, "maximum": 65535}, "quantity": {"type": "string", "pattern": "^[0-9]+(Mi|Gi)$"}, "labels": {"type": "object", "patternProperties": {"^[a-z0-9./-]+$": STR}, "additionalProperties": False}},
          "type": "object", "additionalProperties": False, "properties": {
              "service": {"type": "object", "required": ["port"], "additionalProperties": False, "properties": {"port": {"$ref": "#/$defs/port"}}},
              "metrics": {"type": "object", "required": ["enabled"], "additionalProperties": False, "properties": {"enabled": BOOL, "port": {"$ref": "#/$defs/port"}}},
              "podLabels": {"$ref": "#/$defs/labels"}, "podAnnotations": {"$ref": "#/$defs/labels"},
              "persistence": {"oneOf": [{"type": "object", "required": ["enabled"], "additionalProperties": False, "properties": {"enabled": {"const": False}}},
                                        {"type": "object", "required": ["enabled", "size"], "additionalProperties": False, "properties": {"enabled": {"const": True}, "size": {"$ref": "#/$defs/quantity"}, "storageClass": STR}}]}}},
     valid={"empty": {}, "svc": {"service": {"port": 8080}}, "metrics": {"metrics": {"enabled": True, "port": 9090}}, "metrics-off": {"metrics": {"enabled": False}}, "labels": {"podLabels": {"app.kubernetes.io/name": "heron", "tier": "web"}}, "annotations": {"podAnnotations": {"prometheus.io/scrape": "true"}},
            "pvc-off": {"persistence": {"enabled": False}}, "pvc-on": {"persistence": {"enabled": True, "size": "10Gi"}}, "pvc-class": {"persistence": {"enabled": True, "size": "512Mi", "storageClass": "fast"}}, "empty-labels": {"podLabels": {}}},
     invalid={"svc-no-port": ({"service": {}}, "port required"), "svc-port-zero": ({"service": {"port": 0}}, "port range"), "svc-port-high": ({"service": {"port": 70000}}, "port range"), "metrics-port-string": ({"metrics": {"enabled": True, "port": "9090"}}, "port integer"), "metrics-no-enabled": ({"metrics": {"port": 9090}}, "enabled required"),
              "label-upper": ({"podLabels": {"App": "x"}}, "label key lower case"), "label-number": ({"podLabels": {"app": 1}}, "label values are strings"), "label-space": ({"podAnnotations": {"my key": "x"}}, "no spaces in keys"), "label-colon": ({"podAnnotations": {"a:b": "x"}}, "colon not allowed"),
              "pvc-off-extra": ({"persistence": {"enabled": False, "size": "1Gi"}}, "disabled persistence has nothing else"), "pvc-on-no-size": ({"persistence": {"enabled": True}}, "size required"), "pvc-on-bad-size": ({"persistence": {"enabled": True, "size": "10GB"}}, "bad unit"),
              "pvc-on-extra": ({"persistence": {"enabled": True, "size": "1Gi", "mode": "RWO"}}, "unknown property"), "pvc-no-enabled": ({"persistence": {"size": "1Gi"}}, "enabled required"), "pvc-enabled-string": ({"persistence": {"enabled": "yes", "size": "1Gi"}}, "enabled boolean"),
              "root-extra": ({"replicas": 2}, "unknown root property"), "svc-extra": ({"service": {"port": 80, "type": "ClusterIP"}}, "unknown property")},
     show_valid=["empty", "svc", "pvc-off", "pvc-on"], show_invalid=["svc-port-zero", "label-upper", "pvc-off-extra", "pvc-on-no-size"],
     wrong=[{"type": "object", "properties": {"service": {"type": "object", "properties": {"port": INT}}, "metrics": {"type": "object"}, "podLabels": {"type": "object"}, "podAnnotations": {"type": "object"}, "persistence": {"type": "object", "properties": {"enabled": BOOL, "size": STR, "storageClass": STR}}}}])

# 6 ------------------------------------------------------------------------------------------------------------------
BROKEN6 = '''{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "replicaCount": { "type": "int", "minimum": "1" },
    "image": {
      "type": "object",
      "properties": {
        "repository": { "type": "string", "required": true },
        "tag": { "type": "string", "pattern": "^[a-z0-9.-+$" }
      }
    },
    "service": { "$ref": "#/definitions/service" }
  },
  "required": "replicaCount"
}
'''
V6 = {"replicaCount": 2, "image": {"repository": "reg.example/zen", "tag": "1.0.3"}, "service": {"port": 8080}}
spec(slug="broken-schema-fix", d=3, kind="fix",
     prompt=pd('''
        `values.schema.json` for the chart `zen` is rejected by the validator before it can look at any document ("schema error ..."), and once it loads it is far too permissive. Repair it. What it should say:

        - root: an object with only `replicaCount` (required, integer, at least 1), `image` and `service`;
        - `image`: only `repository` (required, non-empty string) and `tag` (required; lower-case letters, digits, `.`, `-` and `+` only; the whole string must match; at least one character);
        - `service`: only `port` (required, integer 1 to 65535).
     ''', NOTE),
     start=BROKEN6,
     ref={"$schema": "http://json-schema.org/draft-07/schema#", "type": "object", "additionalProperties": False, "required": ["replicaCount"], "properties": {
         "replicaCount": {"type": "integer", "minimum": 1},
         "image": {"type": "object", "additionalProperties": False, "required": ["repository", "tag"], "properties": {"repository": {"type": "string", "minLength": 1}, "tag": {"type": "string", "pattern": "^[a-z0-9.+-]+$"}}},
         "service": {"$ref": "#/definitions/service"}}, "definitions": {"service": {"type": "object", "additionalProperties": False, "required": ["port"], "properties": {"port": {"type": "integer", "minimum": 1, "maximum": 65535}}}}},
     valid={"min": {"replicaCount": 1}, "full": V6, "tag-plus": {"replicaCount": 3, "image": {"repository": "z", "tag": "1.0.0+build.7"}}, "port-edge": {"replicaCount": 1, "service": {"port": 65535}}, "float-int": {"replicaCount": 2.0}},
     invalid={"no-replicas": ({"image": {"repository": "x", "tag": "1"}}, "replicaCount required"), "zero": ({"replicaCount": 0}, "at least 1"), "string-replicas": ({"replicaCount": "1"}, "integer"), "no-repo": ({"replicaCount": 1, "image": {"tag": "1"}}, "repository required"),
              "no-tag": ({"replicaCount": 1, "image": {"repository": "x"}}, "tag required"), "empty-repo": ({"replicaCount": 1, "image": {"repository": "", "tag": "1"}}, "empty repository"), "upper-tag": ({"replicaCount": 1, "image": {"repository": "x", "tag": "V1"}}, "lower case tag"),
              "tag-space": ({"replicaCount": 1, "image": {"repository": "x", "tag": "1 0"}}, "no spaces"), "tag-empty": ({"replicaCount": 1, "image": {"repository": "x", "tag": ""}}, "tag not empty"), "tag-slash": ({"replicaCount": 1, "image": {"repository": "x", "tag": "a/b"}}, "no slash in tags"),
              "port-zero": ({"replicaCount": 1, "service": {"port": 0}}, "port range"), "port-big": ({"replicaCount": 1, "service": {"port": 65536}}, "port range"), "svc-no-port": ({"replicaCount": 1, "service": {}}, "port required"), "svc-extra": ({"replicaCount": 1, "service": {"port": 80, "type": "x"}}, "unknown property"),
              "image-extra": ({"replicaCount": 1, "image": {"repository": "x", "tag": "1", "pullPolicy": "Always"}}, "unknown property"), "root-extra": ({"replicaCount": 1, "foo": 1}, "unknown property")},
     show_valid=["min", "full"], show_invalid=["no-replicas", "upper-tag", "root-extra"],
     wrong=[{"type": "object", "required": ["replicaCount"], "properties": {"replicaCount": {"type": "integer", "minimum": 1}, "image": {"type": "object", "required": ["repository", "tag"], "properties": {"repository": STR, "tag": {"type": "string", "pattern": "^[a-z0-9.+-]+$"}}}, "service": {"type": "object", "required": ["port"], "properties": {"port": INT}}}}])

# 7 ------------------------------------------------------------------------------------------------------------------
LAX7 = {"$defs": {"base": {"type": "object", "properties": {"name": {"type": "string", "pattern": "[a-z]+"}, "labels": {"type": "object", "additionalProperties": STR}}, "required": ["name"]}},
        "allOf": [{"$ref": "#/$defs/base"}], "type": "object", "properties": {"replicas": {"type": "integer", "minimum": 1}, "mode": {"enum": ["active", "standby"]}}, "additionalProperties": False}
FIX7 = {"$defs": {"base": {"type": "object", "properties": {"name": {"type": "string", "pattern": "^[a-z]+$"}, "labels": {"type": "object", "additionalProperties": STR}}, "required": ["name"]}},
        "type": "object", "required": ["name"], "additionalProperties": False, "properties": {"name": {"type": "string", "pattern": "^[a-z]+$"}, "labels": {"type": "object", "additionalProperties": STR}, "replicas": {"type": "integer", "minimum": 1}, "mode": {"enum": ["active", "standby"]}}}
spec(slug="allof-additional-fix", d=4, kind="fix",
     prompt=pd('''
        Every document of the chart `finch` is rejected by `values.schema.json`, even the ones that should be fine, and some obviously wrong names are accepted. The schema is meant to say: an object with only the properties
        `name` (required; a string of lower-case letters only, the whole string), `labels` (optional; an object with string values), `replicas` (optional; integer at least 1) and `mode` (optional; `active` or `standby`).
        The author split the properties into a shared definition and the rest. Fix it (it is fine to flatten everything into one object schema).
     ''', NOTE),
     start=dumps(LAX7), ref=FIX7,
     valid={"min": {"name": "finch"}, "full": {"name": "abc", "labels": {"tier": "web"}, "replicas": 2, "mode": "standby"}, "labels-empty": {"name": "z", "labels": {}}, "replicas-only": {"name": "a", "replicas": 10}},
     invalid={"no-name": ({"replicas": 1}, "name required"), "digits-name": ({"name": "abc123"}, "name has digits"), "upper-name": ({"name": "Finch"}, "name has upper case"), "dash-name": ({"name": "a-b"}, "dash in name"), "empty-name": ({"name": ""}, "empty name"), "name-number": ({"name": 5}, "name is a string"),
              "label-number": ({"name": "a", "labels": {"x": 1}}, "labels are strings"), "replicas-zero": ({"name": "a", "replicas": 0}, "at least 1"), "bad-mode": ({"name": "a", "mode": "idle"}, "mode enum"), "extra": ({"name": "a", "color": "red"}, "unknown property"), "name-prefix": ({"name": "ab1"}, "unanchored pattern")},
     show_valid=["min", "full"], show_invalid=["no-name", "digits-name", "extra"],
     wrong=[{"type": "object", "required": ["name"], "properties": {"name": {"type": "string", "pattern": "[a-z]+"}, "labels": {"type": "object"}, "replicas": {"type": "integer", "minimum": 1}, "mode": {"enum": ["active", "standby"]}}}])

# 8 ------------------------------------------------------------------------------------------------------------------
spec(slug="full-chart-schema", d=5, kind="author",
     prompt=dd('''
        Write the complete `values.schema.json` for the chart `tern`. Objects reject unlisted properties. All of these rules apply:

        1. Root properties: `replicaCount` (integer >= 1, required), `image` (required), `service`, `ingress`, `autoscaling`, `resources`, `env`, `persistence`, `podLabels`.
        2. `image`: required `repository` (non-empty string) and `tag` (non-empty string); optional `pullPolicy` (`Always`, `IfNotPresent` or `Never`).
        3. `service`: required `type` (`ClusterIP` or `LoadBalancer`) and `port` (integer 1-65535); `annotations` (optional, only allowed when `type` is `LoadBalancer`; an object with string values).
        4. `ingress`: required `enabled` boolean; when true: `hosts` required with 1 to 3 items, each a string of lower-case letters, digits, dots and hyphens that contains at least one dot; optional `className` string.
        5. `autoscaling`: required `enabled`; when true both `minReplicas` and `maxReplicas` (integers >= 1) are required and `replicaCount` is still present as the root rules say; `targetCPU` optional integer 1 to 100.
        6. `resources`: optional `requests` and `limits`, each an object with only `cpu` (digits with optional `m`) and `memory` (digits followed by Mi or Gi).
        7. `env`: an object whose property names are upper-case letters, digits and underscores starting with a letter, whose values are strings or integers (not booleans or objects).
        8. `persistence`: either `{"enabled": false}` only, or `enabled` true with required `size` (digits followed by Gi or Ti) and optional `storageClass` string; exactly one of these shapes.
        9. `podLabels`: an object with string values, at most 8 properties.
     '''),
     start='{\n  "type": "object"\n}\n',
     ref={"$defs": {"res": {"type": "object", "additionalProperties": False, "properties": {"cpu": {"type": "string", "pattern": "^[0-9]+m?$"}, "memory": {"type": "string", "pattern": "^[0-9]+(Mi|Gi)$"}}}}, "type": "object", "additionalProperties": False, "required": ["replicaCount", "image"], "properties": {
         "replicaCount": {"type": "integer", "minimum": 1},
         "image": {"type": "object", "additionalProperties": False, "required": ["repository", "tag"], "properties": {"repository": {"type": "string", "minLength": 1}, "tag": {"type": "string", "minLength": 1}, "pullPolicy": {"enum": ["Always", "IfNotPresent", "Never"]}}},
         "service": {"type": "object", "additionalProperties": False, "required": ["type", "port"], "properties": {"type": {"enum": ["ClusterIP", "LoadBalancer"]}, "port": {"type": "integer", "minimum": 1, "maximum": 65535}, "annotations": {"type": "object", "additionalProperties": STR}},
                     "if": {"required": ["annotations"]}, "then": {"properties": {"type": {"const": "LoadBalancer"}}}},
         "ingress": {"type": "object", "additionalProperties": False, "required": ["enabled"], "properties": {"enabled": BOOL, "hosts": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string", "pattern": "^[a-z0-9-]*\\.[a-z0-9.-]*$"}}, "className": STR},
                     "if": {"properties": {"enabled": {"const": True}}, "required": ["enabled"]}, "then": {"required": ["hosts"]}},
         "autoscaling": {"type": "object", "additionalProperties": False, "required": ["enabled"], "properties": {"enabled": BOOL, "minReplicas": {"type": "integer", "minimum": 1}, "maxReplicas": {"type": "integer", "minimum": 1}, "targetCPU": {"type": "integer", "minimum": 1, "maximum": 100}},
                         "if": {"properties": {"enabled": {"const": True}}, "required": ["enabled"]}, "then": {"required": ["minReplicas", "maxReplicas"]}},
         "resources": {"type": "object", "additionalProperties": False, "properties": {"requests": {"$ref": "#/$defs/res"}, "limits": {"$ref": "#/$defs/res"}}},
         "env": {"type": "object", "propertyNames": {"pattern": "^[A-Z][A-Z0-9_]*$"}, "additionalProperties": {"type": ["string", "integer"]}},
         "persistence": {"oneOf": [{"type": "object", "required": ["enabled"], "additionalProperties": False, "properties": {"enabled": {"const": False}}},
                                   {"type": "object", "required": ["enabled", "size"], "additionalProperties": False, "properties": {"enabled": {"const": True}, "size": {"type": "string", "pattern": "^[0-9]+(Gi|Ti)$"}, "storageClass": STR}}]},
         "podLabels": {"type": "object", "maxProperties": 8, "additionalProperties": STR}}},
     valid={"min": {"replicaCount": 1, "image": {"repository": "r", "tag": "t"}}, "image-policy": {"replicaCount": 2, "image": {"repository": "r", "tag": "t", "pullPolicy": "Never"}},
            "svc-lb": {"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "service": {"type": "LoadBalancer", "port": 443, "annotations": {"a": "b"}}}, "svc-cip": {"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "service": {"type": "ClusterIP", "port": 80}},
            "ingress-on": {"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "ingress": {"enabled": True, "hosts": ["a.example.com", "b.example.com", "c.example.com"], "className": "nginx"}}, "ingress-off": {"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "ingress": {"enabled": False}},
            "hpa": {"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "autoscaling": {"enabled": True, "minReplicas": 2, "maxReplicas": 5, "targetCPU": 80}}, "resources": {"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}, "limits": {"cpu": "1", "memory": "1Gi"}}},
            "env": {"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "env": {"LOG_LEVEL": "debug", "WORKERS": 4, "A1": ""}}, "pvc-off": {"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "persistence": {"enabled": False}},
            "pvc-on": {"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "persistence": {"enabled": True, "size": "10Gi", "storageClass": "fast"}}, "labels": {"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "podLabels": {f"l{i}": "v" for i in range(8)}}},
     invalid={"no-image": ({"replicaCount": 1}, "image required"), "no-replicas": ({"image": {"repository": "r", "tag": "t"}}, "replicaCount required"), "bad-policy": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t", "pullPolicy": "Sometimes"}}, "pullPolicy enum"), "empty-tag": ({"replicaCount": 1, "image": {"repository": "r", "tag": ""}}, "tag not empty"),
              "svc-nodeport": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "service": {"type": "NodePort", "port": 80}}, "service type enum"), "svc-annotations-cip": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "service": {"type": "ClusterIP", "port": 80, "annotations": {"a": "b"}}}, "annotations only for LoadBalancer"),
              "svc-port": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "service": {"type": "ClusterIP", "port": 0}}, "port range"), "svc-ann-number": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "service": {"type": "LoadBalancer", "port": 80, "annotations": {"a": 1}}}, "annotation values are strings"),
              "ingress-no-hosts": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "ingress": {"enabled": True}}, "hosts required"), "ingress-4-hosts": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "ingress": {"enabled": True, "hosts": ["a.x", "b.x", "c.x", "d.x"]}}, "at most 3 hosts"),
              "ingress-host-nodot": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "ingress": {"enabled": True, "hosts": ["localhost"]}}, "host needs a dot"), "ingress-host-upper": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "ingress": {"enabled": True, "hosts": ["A.example.com"]}}, "host lower case"),
              "hpa-no-max": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "autoscaling": {"enabled": True, "minReplicas": 1}}, "max required"), "hpa-cpu": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "autoscaling": {"enabled": False, "targetCPU": 101}}, "targetCPU range"),
              "res-unit": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "resources": {"limits": {"memory": "1G"}}}, "memory unit"), "res-extra": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "resources": {"limits": {"gpu": "1"}}}, "unknown resource"),
              "env-bool": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "env": {"DEBUG": True}}, "booleans not allowed"), "env-lower": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "env": {"debug": "1"}}, "env names upper case"), "env-object": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "env": {"A": {"b": 1}}}, "no objects"),
              "env-float": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "env": {"A": 1.5}}, "no floats"), "pvc-off-size": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "persistence": {"enabled": False, "size": "1Gi"}}, "disabled has nothing else"),
              "pvc-mi": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "persistence": {"enabled": True, "size": "512Mi"}}, "size units Gi or Ti"), "pvc-no-size": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "persistence": {"enabled": True}}, "size required"),
              "labels-9": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "podLabels": {f"l{i}": "v" for i in range(9)}}, "at most 8 labels"), "label-number": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "podLabels": {"a": 1}}, "label values strings"),
              "root-extra": ({"replicaCount": 1, "image": {"repository": "r", "tag": "t"}, "nodeSelector": {}}, "unknown root property")},
     show_valid=["min", "svc-lb", "ingress-on", "pvc-on"], show_invalid=["no-image", "svc-annotations-cip", "env-bool", "pvc-off-size"],
     wrong=[{"type": "object", "required": ["replicaCount", "image"], "additionalProperties": False, "properties": {"replicaCount": INT, "image": OBJ, "service": OBJ, "ingress": OBJ, "autoscaling": OBJ, "resources": OBJ, "env": OBJ, "persistence": OBJ, "podLabels": OBJ}}])


def _tasks(rng, n):
    return [make_task(s) for s in SPECS[:n]]


@family("devops-config-schema", category="devops", lang="text", kind="fix", n=len(SPECS),
        summary="write or repair JSON Schemas for Helm-style values files, judged on hidden valid and invalid documents: ranges, patterns, arrays, if/then, oneOf, $ref, additionalProperties traps")
def config_schema(rng, n):
    return _tasks(rng, n)
