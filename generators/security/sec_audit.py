"""Security audit tasks: a bundle of small modules, some with planted vulnerabilities, some already fixed (decoys). The agent writes `findings.json`;
a hidden checker scores recall minus a penalty for false positives (the review scoring), matching findings by file, line window and category.

The modules are the vulnerable (and fixed) reference code of the fix families of this section, composed differently for every task."""
import ast
import json

from fx import Task, family

from . import _sec, sec_auth, sec_authz, sec_crypto, sec_deser, sec_files, sec_http, sec_redirect, sec_secrets, sec_ssrf

CATEGORIES = ["path-traversal", "sql-injection", "command-injection", "code-injection", "xss", "header-injection", "log-injection", "ssrf", "open-redirect", "deserialization",
              "weak-random", "weak-crypto", "timing-attack", "hardcoded-secret", "password-storage", "jwt", "session", "authz", "csrf", "mass-assignment", "redos", "race-condition",
              "resource-exhaustion", "insecure-permissions", "file-upload"]

GROUPS = {
    "injection": ({"command-injection", "code-injection", "header-injection", "log-injection", "sql-injection", "xss", "path-traversal"}, "injection-type problems (anything where untrusted text ends up interpreted as code, a command, a header, a log line, markup or a path)"),
    "access": ({"authz", "csrf", "mass-assignment", "jwt", "session", "password-storage", "open-redirect"}, "authentication and access-control problems (who may do what, tokens, passwords, redirects and request forgery)"),
    "crypto": ({"weak-random", "weak-crypto", "timing-attack", "hardcoded-secret", "insecure-permissions", "deserialization"}, "cryptography, secrets and unsafe-data-handling problems"),
}

# (module of the scenario, slug, file in the scenario, function containing the flaw or None, marker text of the flawed line, category)
POOL_SPEC = [
    (sec_ssrf, "webhook-prefix", "hooks.py", "is_allowed", "return url.startswith(ALLOWED_PREFIX)", "ssrf"),
    (sec_ssrf, "playlist-suffix", "playlists.py", "is_trusted", "host.endswith(d)", "ssrf"),
    (sec_ssrf, "ipv6-blind-spot", "guard.py", "is_internal", "ipaddress.IPv4Address(address)", "ssrf"),
    (sec_redirect, "login-next", "login_redirect.py", "after_login", 'return next_url or "/"', "open-redirect"),
    (sec_redirect, "continue-netloc", "cont.py", "safe_redirect", 'if parts.netloc == "" and target:', "open-redirect"),
    (sec_http, "redirect-crlf", "responses.py", "redirect_response", "% (status, REASONS[status], location)", "header-injection"),
    (sec_http, "cookie-attributes", "cookies.py", "set_cookie_header", 'header = "%s=%s; Path=/; HttpOnly" % (name, value)', "header-injection"),
    (sec_http, "get-mutates", "bank.py", "handle", 'if path == "/transfer":', "csrf"),
    (sec_crypto, "reset-token", "tokens.py", "new_reset_token", "random.choice(ALPHABET)", "weak-random"),
    (sec_crypto, "session-id", "sessions.py", "new_session_id", "hashlib.md5(", "weak-random"),
    (sec_crypto, "token-compare", "tokencheck.py", "verify_token", "return supplied == expected", "timing-attack"),
    (sec_crypto, "hash-prefix-mac", "links.py", "sign", "hashlib.sha256(secret + message)", "weak-crypto"),
    (sec_crypto, "stream-cipher-reuse", "notes_crypto.py", "encrypt", "ks = _keystream(key, len(plaintext))", "weak-crypto"),
    (sec_auth, "plaintext-passwords", "accounts.py", "register", "self.users[name] = password", "password-storage"),
    (sec_auth, "legacy-md5", "passwords.py", "hash_password", "hashlib.md5(password.encode", "password-storage"),
    (sec_auth, "alg-none", "minijwt.py", "decode", 'if header.get("alg") != "none":', "jwt"),
    (sec_auth, "expiry-ignored", "minijwt.py", "decode", "return json.loads(_b64d(body))", "jwt"),
    (sec_auth, "logout-keeps-session", "sessions.py", "logout", "return CLEAR", "session"),
    (sec_authz, "invoice-owner", "billing.py", "get_invoice", "return self.invoices[invoice_id]", "authz"),
    (sec_authz, "bulk-delete", "notes.py", "delete_many", "if not any(", "authz"),
    (sec_authz, "profile-form", "profiles.py", "update_profile", "user.update(fields)", "mass-assignment"),
    (sec_secrets, "hardcoded-api-key", "payments.py", None, 'API_KEY = "pgw_', "hardcoded-secret"),
    (sec_secrets, "unbounded-upload", "uploads.py", "read_body", "return stream.read()", "resource-exhaustion"),
    (sec_deser, "session-pickle", "sessions.py", "load_session", "return pickle.loads(", "deserialization"),
    (sec_deser, "calculator-eval", "calc.py", "calculate", "return eval(expression)", "code-injection"),
    (sec_deser, "getattr-dispatch", "console.py", "run", "return getattr(self, name)(*args)", "code-injection"),
    (sec_deser, "trailing-whitespace", "clean.py", "strip_trailing", 're.sub(r"\\s+$", "", text)', "redos"),
    (sec_files, "symlink-swap", "reports.py", "save_report", "if os.path.islink(path):", "race-condition"),
    (sec_files, "chmod-after-write", "secretstore.py", "save_secret", "os.chmod(path, 0o600)", "insecure-permissions"),
    (sec_files, "extension-filter", "filters.py", "is_allowed_upload", 'return filename.lower().split(".")[-1] in ALLOWED', "file-upload"),
    (sec_files, "forged-log-lines", "auditlog.py", "log_login_failure", 'logger.warning("login failed for user %s from %s", username, ip)', "log-injection"),
]


def _scenarios(module):
    found = {}
    for value in vars(module).values():
        if isinstance(value, list) and value and isinstance(value[0], dict) and "slug" in value[0]:
            for s in value:
                found[s["slug"]] = s
    return found


def _span(text, func, marker):
    """(first, last) line of the function `func` (or of the marker line when func is None), and the line of the marker."""
    lines = text.split("\n")
    at = next((i + 1 for i, ln in enumerate(lines) if marker in ln), None)
    if at is None:
        raise ValueError(f"marker {marker!r} not found")
    if func is None:
        return at, at, at
    tree = ast.parse(text)
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func and node.lineno <= at <= node.end_lineno:
            best = (node.lineno, node.end_lineno)
    if best is None:
        raise ValueError(f"function {func} does not contain the marker {marker!r}")
    return best[0], best[1], at


def _solution_span(text, func, fallback_marker):
    if func is None:
        return None
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func:
            return node.lineno, node.end_lineno
    return None


def build_pool():
    pool = []
    cache = {}
    for module, slug, file, func, marker, category in POOL_SPEC:
        scenarios = cache.setdefault(module.__name__, _scenarios(module))
        s = scenarios[slug]
        start_text = s["start"][file]
        sol_text = s["solution"].get(file)
        first, last, at = _span(start_text, func, marker)
        entry = {"slug": slug, "file": file, "category": category, "product": s["product"], "start": start_text, "span": (first, last), "line": at, "func": func}
        if sol_text is not None and func is not None:
            sp = _solution_span(sol_text, func, marker)
            if sp:
                entry["fixed"] = sol_text
                entry["fixed_span"] = sp
        pool.append(entry)
    return pool


CHECKER = '''#!/usr/bin/env python3
"""Hidden checker of the audit tasks: scores findings.json against the planted vulnerabilities in spec.json.

score = max(0, (hits - 0.25 * false_positives) / planted)

* a finding is a hit when it names a planted vulnerability's file, a line inside that vulnerability's window and the right category; several findings on one vulnerability count once;
* a finding that points into the window of a decoy (code that is already safe) or of an out-of-scope vulnerability, or at no vulnerability at all, is a false positive;
* a finding in the window of a planted vulnerability with the wrong category is neither (it is not rewarded, not punished).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = json.load(open(os.path.join(HERE, "spec.json"), encoding="utf-8"))
SLACK = 1


def finish(score, msg=""):
    if msg:
        print(msg)
    print(json.dumps({"score": max(0.0, min(1.0, score))}))
    sys.exit(0)


def norm(p):
    p = p.strip().replace("\\\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def inside(finding, window):
    return norm(finding["file"]) == window["file"] and window["start"] - SLACK <= finding["line"] <= window["end"] + SLACK


def main():
    path = "findings.json"
    if not os.path.exists(path):
        finish(0.0, "findings.json not found")
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        finish(0.0, "findings.json is not valid JSON: %s" % e)
    if not isinstance(data, list):
        finish(0.0, "findings.json must be a JSON list")
    if len(data) > 40:
        finish(0.0, "far too many findings")
    categories = set(SPEC["categories"])
    for i, f in enumerate(data):
        if not isinstance(f, dict) or set(f) != {"file", "line", "category", "summary"}:
            finish(0.0, "finding %d: expected exactly the keys file, line, category, summary" % i)
        if not isinstance(f["file"], str) or not f["file"].strip():
            finish(0.0, "finding %d: file must be a non-empty string" % i)
        if not isinstance(f["line"], int) or isinstance(f["line"], bool) or f["line"] < 1:
            finish(0.0, "finding %d: line must be a positive integer" % i)
        if f["category"] not in categories:
            finish(0.0, "finding %d: category must be one of %s" % (i, ", ".join(sorted(categories))))
        if not isinstance(f["summary"], str) or len(f["summary"].strip()) < 8:
            finish(0.0, "finding %d: summary must be a sentence" % i)
    planted = SPEC["defects"]
    hits, fp = set(), 0
    for f in data:
        matched = [d for d in planted if inside(f, d)]
        if not matched:
            fp += 1                      # decoys, out-of-scope code and everything else
            continue
        for d in matched:
            if d["category"] == f["category"]:
                hits.add(d["id"])
    total = len(planted)
    score = (len(hits) - 0.25 * fp) / total if total else 1.0
    print("planted=%d hits=%d false_positives=%d" % (total, len(hits), fp))
    finish(score)


if __name__ == "__main__":
    main()
'''

VERIFY = "python3 _verify/check.py"

INTROS = [
    "We took over a bundle of small service modules from another team (see `README.md`; every directory under `app/` is independent, standard library only). Nobody has reviewed them for security.",
    "A vendor handed us the helper modules in this repository before the contract ended. Please do a defensive security review of the code under `app/` (`README.md` lists what each module is for).",
    "Before the acquired team's modules go live I need a security audit of `app/`: the README tells what each module does, and your job is to find the weaknesses an attacker could use.",
    "Security review request: the modules below (one directory per module, see `README.md`) are used by several of our internal services and have never been audited.",
    "This repository is a grab bag of small modules inherited from a decommissioned product. Review the code in `app/` as a security engineer would, before we decide what to keep.",
]

SCHEMA = ("Write `findings.json`: a JSON list where every finding is an object with exactly the keys `file` (path as in the repository, for example `app/m03/hooks.py`), `line` (1-based line in that file where the "
          "flaw is - anywhere in the vulnerable function is accepted), `category` (one of: {cats}) and `summary` (a sentence saying what is wrong and how it could be abused). Do not modify any source file.")

TAILS = [
    "Only report real weaknesses: a finding that points at safe code counts against you, and so does a missed vulnerability.",
    "Precision matters as much as coverage - some modules are already fine, and flagging them wastes the team's time.",
    "A hit needs the right file, the right place and the right category; pointing at harmless code costs points.",
    "Not every module is vulnerable. Report what you can substantiate and leave the rest alone.",
]

ASSURANCE = ("Old notes from the previous team (NOTES.md): \"All input is validated by the API gateway before it reaches these modules\" and \"The last pen test found nothing\". "
             "Treat such claims as unverified - the modules are what you review.")

PLAN = [
    # difficulty, vulnerabilities, decoys, assurance note, scope group (None = everything counts)
    (2, 3, 1, False, None),
    (2, 3, 1, False, None),
    (2, 3, 2, False, None),
    (3, 4, 2, False, None),
    (3, 4, 2, True, None),
    (3, 5, 1, False, None),
    (3, 4, 3, False, None),
    (4, 5, 2, True, None),
    (4, 6, 2, False, None),
    (4, 5, 3, True, "injection"),
    (4, 6, 3, False, "access"),
    (5, 7, 3, True, None),
    (5, 6, 3, True, "crypto"),
    (5, 8, 4, True, None),
]


def make_task(idx, plan, rng, pool):
    difficulty, n_vuln, n_decoy, assurance, group = plan
    candidates = list(pool)
    rng.shuffle(candidates)
    in_scope, out_scope = [], []
    scope_cats = GROUPS[group][0] if group else None
    for e in candidates:
        (in_scope if (scope_cats is None or e["category"] in scope_cats) else out_scope).append(e)
    chosen_vuln = in_scope[:n_vuln]
    out_of_scope = out_scope[:2] if group else []
    used = {id(e) for e in chosen_vuln + out_of_scope}
    decoys = [e for e in candidates if "fixed" in e and id(e) not in used][:n_decoy]
    used |= {id(e) for e in decoys}
    # unique file names inside the repo: every module gets its own directory m01, m02, ...
    members = [("vuln", e) for e in chosen_vuln] + [("scope", e) for e in out_of_scope] + [("decoy", e) for e in decoys]
    rng.shuffle(members)
    # the same source file twice (two flawed functions of minijwt, say) would collide only inside one directory, not across directories
    start, defects, decoy_windows, oos_windows, rows = {}, [], [], [], []
    for number, (role, e) in enumerate(members, start=1):
        d = f"m{number:02d}"
        path = f"app/{d}/{e['file']}"
        if role == "decoy":
            start[path] = e["fixed"]
            decoy_windows.append({"file": path, "start": e["fixed_span"][0], "end": e["fixed_span"][1], "category": e["category"]})
        else:
            start[path] = e["start"]
            window = {"file": path, "start": e["span"][0], "end": e["span"][1], "category": e["category"], "line": e["line"]}
            (defects if role == "vuln" else oos_windows).append(window)
        rows.append((path, e["product"]))
    for i, d in enumerate(defects, start=1):
        d["id"] = f"d{i}"
    readme = "# Inherited service modules\n\nSmall, independent helper modules (Python standard library only), one directory each:\n\n" + "\n".join(f"* `{p}` - used by {prod}" for p, prod in sorted(rows)) + "\n"
    start["README.md"] = readme
    if assurance:
        start["NOTES.md"] = ("# Notes from the previous team\n\n* All input is validated by the API gateway before it reaches these modules, so the modules themselves do not need to be defensive.\n"
                             "* The last penetration test (2021) found nothing.\n* Anything marked `fixed` in old tickets really was fixed.\n")
    cats_text = ", ".join(sorted(CATEGORIES))
    scope_text = ""
    if group:
        scope_text = f" Scope: only report {GROUPS[group][1]}; other kinds of weaknesses are known and tracked separately, and reporting them counts as a false positive."
    prompt = INTROS[idx % len(INTROS)] + " " + SCHEMA.format(cats=cats_text) + scope_text + (" " + ASSURANCE if assurance else "") + " " + TAILS[idx % len(TAILS)]
    spec = {"categories": CATEGORIES, "defects": [{k: v for k, v in d.items() if k != "line"} for d in defects],
            "decoys": [{k: v for k, v in w.items() if k != "category"} for w in decoy_windows], "out_of_scope": [{k: v for k, v in w.items() if k not in ("category", "line")} for w in oos_windows]}
    gold = [{"file": d["file"], "line": d["line"], "category": d["category"], "summary": "%s: the flawed code is at this line and can be abused by an attacker." % d["category"]} for d in defects]
    hidden = {"_verify/check.py": CHECKER, "_verify/spec.json": json.dumps(spec, sort_keys=True, indent=1) + "\n"}
    slug = f"{idx + 1:02d}-bundle-{len(defects)}v-{len(decoy_windows)}d" + (f"-{group}" if group else "")
    return Task(slug=slug, prompt=prompt, difficulty=difficulty, kind="feature", lang="python", start=start, hidden=hidden,
                solution={"findings.json": json.dumps(gold, indent=1) + "\n"}, verify=VERIFY, pass_mode="json-score", protected=sorted(start), timeout_s=60,
                tags=["security", "audit", "review", *(["scoped"] if group else []), *(["false-assurance"] if assurance else [])],
                notes={"planted": [f"{d['file']}: {d['category']}" for d in defects], "decoys": [w["file"] for w in decoy_windows], "scope": group or "all"})


@family("security-audit", category="security", lang="python", kind="feature", n=14,
        summary="audit a bundle of inherited modules: write findings.json with file, line and category; planted flaws, safe decoys, scoped and falsely reassured variants")
def gen_audit(rng, n):
    pool = build_pool()
    return [make_task(i, PLAN[i], rng, pool) for i in range(n)]
