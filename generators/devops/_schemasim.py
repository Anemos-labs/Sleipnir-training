"""A small JSON Schema validator (shipped to the agent as tools/schemacheck.py, used by the hidden checker)."""

SCHEMASIM = r'''#!/usr/bin/env python3
"""schemacheck.py - validate JSON documents against a JSON Schema (documented subset, draft 2019-09 behaviour).

    python3 tools/schemacheck.py SCHEMA.json DIR_VALID DIR_INVALID     # every *.json in DIR_VALID must validate, every *.json in DIR_INVALID must be rejected
    python3 tools/schemacheck.py SCHEMA.json DOC.json                  # validate one document and list the errors

Understood keywords: $schema $id $comment title description default examples (annotations, no effect); $defs definitions $ref (only local references: "#/$defs/name" or "#/definitions/name"; sibling keywords of $ref are applied too);
type (a name or a list: string number integer boolean object array null; 1.0 is an integer, true is not a number); enum const;
objects: properties required additionalProperties (true, false or a schema) patternProperties minProperties maxProperties dependentRequired propertyNames (a schema with `pattern`);
arrays: items (one schema) minItems maxItems uniqueItems contains (a schema; at least one item must match);
numbers: minimum maximum exclusiveMinimum exclusiveMaximum (numbers) multipleOf; strings: minLength maxLength pattern (a regular expression searched anywhere in the string, so anchor it with ^ and $) format (annotation only);
combinations: allOf anyOf oneOf (exactly one) not if then else.
`additionalProperties` only looks at `properties` and `patternProperties` of the SAME schema object (a property declared inside an `allOf` branch is still "additional" there).
A schema that uses another keyword, a wrong value type (`"required": true`, `"type": "int"`), an invalid regular expression or an unresolvable $ref is itself rejected.
"""
import json
import os
import re
import sys

ANNOT = {"$schema", "$id", "$comment", "title", "description", "default", "examples", "format"}
KNOWN = ANNOT | {"$defs", "definitions", "$ref", "type", "enum", "const", "properties", "required", "additionalProperties", "patternProperties", "minProperties", "maxProperties", "dependentRequired", "propertyNames",
                 "items", "minItems", "maxItems", "uniqueItems", "contains", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength", "maxLength", "pattern", "allOf", "anyOf", "oneOf", "not",
                 "if", "then", "else"}
TYPES = {"string", "number", "integer", "boolean", "object", "array", "null"}


class SchemaError(Exception):
    pass


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def check_schema(s, root, path="#"):
    if isinstance(s, bool):
        return
    if not isinstance(s, dict):
        raise SchemaError(f"{path}: a schema must be an object or a boolean")
    for k in s:
        if k not in KNOWN:
            raise SchemaError(f"{path}: unknown keyword {k!r}")
    t = s.get("type")
    if t is not None:
        ts = t if isinstance(t, list) else [t]
        if not ts or not all(isinstance(x, str) and x in TYPES for x in ts):
            raise SchemaError(f"{path}/type: must be one of {sorted(TYPES)} (or a list of them), got {t!r}")
    if "required" in s and not (isinstance(s["required"], list) and all(isinstance(x, str) for x in s["required"])):
        raise SchemaError(f"{path}/required: must be an array of property names (got {s['required']!r})")
    if "enum" in s and not (isinstance(s["enum"], list) and s["enum"]):
        raise SchemaError(f"{path}/enum: must be a non-empty array")
    for k in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"):
        if k in s and not is_num(s[k]):
            raise SchemaError(f"{path}/{k}: must be a number (got {s[k]!r})")
    if "multipleOf" in s and s["multipleOf"] <= 0:
        raise SchemaError(f"{path}/multipleOf: must be greater than 0")
    for k in ("minLength", "maxLength", "minItems", "maxItems", "minProperties", "maxProperties"):
        if k in s and not (isinstance(s[k], int) and not isinstance(s[k], bool) and s[k] >= 0):
            raise SchemaError(f"{path}/{k}: must be a non-negative integer (got {s[k]!r})")
    if "uniqueItems" in s and not isinstance(s["uniqueItems"], bool):
        raise SchemaError(f"{path}/uniqueItems: must be a boolean")
    if "pattern" in s:
        try:
            re.compile(s["pattern"])
        except (re.error, TypeError):
            raise SchemaError(f"{path}/pattern: not a valid regular expression")
    if "$ref" in s:
        resolve(s["$ref"], root, path)
    for k in ("properties", "patternProperties", "$defs", "definitions"):
        if k in s:
            if not isinstance(s[k], dict):
                raise SchemaError(f"{path}/{k}: must be an object")
            for name, sub in s[k].items():
                if k == "patternProperties":
                    try:
                        re.compile(name)
                    except re.error:
                        raise SchemaError(f"{path}/{k}: invalid regular expression {name!r}")
                check_schema(sub, root, f"{path}/{k}/{name}")
    for k in ("items", "contains", "not", "if", "then", "else", "propertyNames"):
        if k in s:
            check_schema(s[k], root, f"{path}/{k}")
    if "additionalProperties" in s:
        check_schema(s["additionalProperties"], root, f"{path}/additionalProperties")
    for k in ("allOf", "anyOf", "oneOf"):
        if k in s:
            if not (isinstance(s[k], list) and s[k]):
                raise SchemaError(f"{path}/{k}: must be a non-empty array")
            for i, sub in enumerate(s[k]):
                check_schema(sub, root, f"{path}/{k}/{i}")
    if "dependentRequired" in s:
        d = s["dependentRequired"]
        if not (isinstance(d, dict) and all(isinstance(v, list) and all(isinstance(x, str) for x in v) for v in d.values())):
            raise SchemaError(f"{path}/dependentRequired: must map property names to arrays of property names")


def resolve(ref, root, path="#"):
    m = re.fullmatch(r"#/(\$defs|definitions)/([^/]+)", ref)
    if not m or not isinstance(root.get(m.group(1)), dict) or m.group(2) not in root[m.group(1)]:
        raise SchemaError(f"{path}: cannot resolve $ref {ref!r}")
    return root[m.group(1)][m.group(2)]


def type_ok(inst, t):
    if t == "string":
        return isinstance(inst, str)
    if t == "boolean":
        return isinstance(inst, bool)
    if t == "null":
        return inst is None
    if t == "array":
        return isinstance(inst, list)
    if t == "object":
        return isinstance(inst, dict)
    if t == "number":
        return is_num(inst)
    if t == "integer":
        return is_num(inst) and (isinstance(inst, int) or float(inst).is_integer())
    return False


def valid(s, inst, root):
    errs = []
    validate(s, inst, root, "", errs)
    return not errs


def validate(s, inst, root, path, errs):
    here = path or "/"
    if s is True:
        return
    if s is False:
        errs.append(f"{here}: no value is allowed here")
        return
    if "$ref" in s:
        validate(resolve(s["$ref"], root), inst, root, path, errs)
    if "type" in s:
        ts = s["type"] if isinstance(s["type"], list) else [s["type"]]
        if not any(type_ok(inst, t) for t in ts):
            errs.append(f"{here}: expected type {'/'.join(ts)}, got {type(inst).__name__}")
            return
    if "enum" in s and not any(inst == e and type(inst) == type(e) or (is_num(inst) and is_num(e) and inst == e) for e in s["enum"]):
        errs.append(f"{here}: {inst!r} is not one of {s['enum']}")
    if "const" in s and not (inst == s["const"] and (type(inst) == type(s["const"]) or (is_num(inst) and is_num(s["const"])))):
        errs.append(f"{here}: must be {s['const']!r}")
    if isinstance(inst, str):
        if "minLength" in s and len(inst) < s["minLength"]:
            errs.append(f"{here}: shorter than {s['minLength']} characters")
        if "maxLength" in s and len(inst) > s["maxLength"]:
            errs.append(f"{here}: longer than {s['maxLength']} characters")
        if "pattern" in s and not re.search(s["pattern"], inst):
            errs.append(f"{here}: {inst!r} does not match the pattern {s['pattern']!r}")
    if is_num(inst):
        if "minimum" in s and inst < s["minimum"]:
            errs.append(f"{here}: {inst} is below the minimum {s['minimum']}")
        if "maximum" in s and inst > s["maximum"]:
            errs.append(f"{here}: {inst} is above the maximum {s['maximum']}")
        if "exclusiveMinimum" in s and inst <= s["exclusiveMinimum"]:
            errs.append(f"{here}: {inst} must be greater than {s['exclusiveMinimum']}")
        if "exclusiveMaximum" in s and inst >= s["exclusiveMaximum"]:
            errs.append(f"{here}: {inst} must be less than {s['exclusiveMaximum']}")
        if "multipleOf" in s:
            q = inst / s["multipleOf"]
            if abs(q - round(q)) > 1e-9:
                errs.append(f"{here}: {inst} is not a multiple of {s['multipleOf']}")
    if isinstance(inst, dict):
        props, pats = s.get("properties", {}), s.get("patternProperties", {})
        for r in s.get("required", []):
            if r not in inst:
                errs.append(f"{here}: missing required property {r!r}")
        for k, v in inst.items():
            sub = []
            if k in props:
                sub.append(props[k])
            sub += [ps for pat, ps in pats.items() if re.search(pat, k)]
            for ps in sub:
                validate(ps, v, root, f"{path}/{k}", errs)
            if not sub and "additionalProperties" in s:
                validate(s["additionalProperties"], v, root, f"{path}/{k}", errs) if s["additionalProperties"] is not False else errs.append(f"{here}: additional property {k!r} is not allowed")
        if "minProperties" in s and len(inst) < s["minProperties"]:
            errs.append(f"{here}: fewer than {s['minProperties']} properties")
        if "maxProperties" in s and len(inst) > s["maxProperties"]:
            errs.append(f"{here}: more than {s['maxProperties']} properties")
        for k, deps in s.get("dependentRequired", {}).items():
            if k in inst:
                for d in deps:
                    if d not in inst:
                        errs.append(f"{here}: property {k!r} requires {d!r}")
        if "propertyNames" in s:
            for k in inst:
                validate(s["propertyNames"], k, root, f"{path}/{k}", errs)
    if isinstance(inst, list):
        if "minItems" in s and len(inst) < s["minItems"]:
            errs.append(f"{here}: fewer than {s['minItems']} items")
        if "maxItems" in s and len(inst) > s["maxItems"]:
            errs.append(f"{here}: more than {s['maxItems']} items")
        if s.get("uniqueItems"):
            seen = [json.dumps(x, sort_keys=True) for x in inst]
            if len(set(seen)) != len(seen):
                errs.append(f"{here}: items are not unique")
        if "items" in s:
            for i, x in enumerate(inst):
                validate(s["items"], x, root, f"{path}/{i}", errs)
        if "contains" in s and not any(valid(s["contains"], x, root) for x in inst):
            errs.append(f"{here}: no item matches the `contains` schema")
    for k in ("allOf",):
        for sub in s.get(k, []):
            validate(sub, inst, root, path, errs)
    if "anyOf" in s and not any(valid(sub, inst, root) for sub in s["anyOf"]):
        errs.append(f"{here}: does not match any of the anyOf alternatives")
    if "oneOf" in s:
        n = sum(valid(sub, inst, root) for sub in s["oneOf"])
        if n != 1:
            errs.append(f"{here}: matches {n} of the oneOf alternatives (exactly 1 required)")
    if "not" in s and valid(s["not"], inst, root):
        errs.append(f"{here}: must not match the `not` schema")
    if "if" in s:
        if valid(s["if"], inst, root):
            if "then" in s:
                validate(s["then"], inst, root, path, errs)
        elif "else" in s:
            validate(s["else"], inst, root, path, errs)


def load_schema(path):
    try:
        root = json.load(open(path, encoding="utf-8"))
    except OSError as e:
        raise SchemaError(f"cannot read {path}: {e.strerror}")
    except ValueError as e:
        raise SchemaError(f"{path} is not valid JSON: {e}")
    check_schema(root, root)
    return root


def main(argv):
    if len(argv) not in (3, 4):
        print(__doc__)
        return 2
    try:
        root = load_schema(argv[1])
    except SchemaError as e:
        print(f"schema error: {e}")
        return 1
    if len(argv) == 3:
        errs = []
        validate(root, json.load(open(argv[2], encoding="utf-8")), root, "", errs)
        print("valid" if not errs else "\n".join(errs))
        return 1 if errs else 0
    bad = 0
    for label, d, want in (("valid", argv[2], True), ("invalid", argv[3], False)):
        for f in sorted(os.listdir(d)):
            if not f.endswith(".json"):
                continue
            errs = []
            validate(root, json.load(open(os.path.join(d, f), encoding="utf-8")), root, "", errs)
            ok = (not errs) == want
            bad += not ok
            print(("ok   " if ok else "FAIL ") + f"{label}/{f}" + ("" if ok or not errs else ": " + errs[0]) + ("" if ok or errs else ": it was accepted but must be rejected"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
'''
