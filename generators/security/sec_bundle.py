"""Security incident bundles: several independent components of a service, each with its own reported vulnerability. The agent has to fix every finding; the hidden tests of
the individual fix tasks are combined (one test module per component), so a bundle is solved only when every component is fixed and still works for legitimate input.

The components are the vulnerable reference code of the single-issue families of this section, composed differently for every bundle."""
import re

from fx import Task, family, langs

from . import (_sec, sec_auth, sec_authz, sec_cmd, sec_crypto, sec_deser, sec_files, sec_http, sec_paths, sec_redirect, sec_secrets, sec_sqli, sec_ssrf, sec_web, sec_zip)

SOURCES = [sec_paths, sec_zip, sec_sqli, sec_cmd, sec_web, sec_ssrf, sec_redirect, sec_http, sec_crypto, sec_auth, sec_authz, sec_deser, sec_files, sec_secrets]
ROOT_LINE = 'ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))'

SYSTEMS = ["the customer portal", "the partner API", "the internal admin suite", "the billing platform", "the mobile backend", "the support desk", "the content platform", "the booking service"]

# (difficulty, number of components, minimum number of components with their own difficulty >= 3 / >= 4)
PLAN = [
    (4, 4, 1, 0), (4, 4, 1, 0), (4, 5, 2, 0), (4, 5, 2, 0), (4, 5, 1, 1), (4, 5, 2, 1), (4, 4, 2, 1),
    (5, 7, 3, 1), (5, 7, 3, 2), (5, 8, 3, 2), (5, 8, 4, 2), (5, 8, 3, 3),
]


def eligible():
    out = []
    for module in SOURCES:
        for value in vars(module).values():
            if not (isinstance(value, list) and value and isinstance(value[0], dict) and "slug" in value[0]):
                continue
            for s in value:
                if s.get("lang", "python") != "python" or s["slug"].startswith("scanner-"):
                    continue
                tests = [t for t in s["hidden"].values()]
                visible = dict(s.get("visible") or {})
                texts = tests + list(visible.values())
                if any(ROOT_LINE not in t for t in texts if t):
                    continue
                if any(t.count("ROOT") != 2 for t in texts):          # only the prelude may use ROOT
                    continue
                files = dict(s["start"])
                if any("/" in name for name in files if not name.endswith(".md")):
                    continue
                names = {n[:-3] for n in files if n.endswith(".py")}
                if not names:
                    continue
                out.append({"scenario": s, "module": module.__name__, "names": names, "d": s["d"], "key": (module.__name__, s["slug"])})
    seen, unique = set(), []
    for e in out:
        if e["key"] not in seen:
            seen.add(e["key"])
            unique.append(e)
    return unique


def pick(rng, pool, n, min3, min4):
    for _attempt in range(200):
        order = list(pool)
        rng.shuffle(order)
        chosen, names, per_module = [], set(), {}
        def take(entry):
            if entry["names"] & names or per_module.get(entry["module"], 0) >= 2:
                return False
            chosen.append(entry)
            names.update(entry["names"])
            per_module[entry["module"]] = per_module.get(entry["module"], 0) + 1
            return True
        for threshold, need in ((4, min4), (3, min3)):
            for entry in order:
                if sum(1 for c in chosen if c["d"] >= threshold) >= need:
                    break
                if entry["d"] >= threshold and entry not in chosen:
                    take(entry)
        for entry in order:
            if len(chosen) >= n:
                break
            if entry not in chosen:
                take(entry)
        if len(chosen) == n and sum(1 for c in chosen if c["d"] >= 3) >= min3 and sum(1 for c in chosen if c["d"] >= 4) >= min4:
            return chosen
    raise RuntimeError("cannot compose a bundle")


def relocate(text, directory):
    return text.replace(ROOT_LINE, 'ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "svc", "%s"))' % directory)


def make_task(idx, plan, rng, pool):
    difficulty, n, min3, min4 = plan
    chosen = pick(rng, pool, n, min3, min4)
    rng.shuffle(chosen)
    start, hidden, solution, findings, notes = {}, {}, {}, [], []
    for number, entry in enumerate(chosen, start=1):
        s = entry["scenario"]
        directory = re.sub(r"[^a-z0-9]+", "_", s["slug"].lower()).strip("_")
        for name, text in s["start"].items():
            start[f"svc/{directory}/{name}"] = text
        for name, text in (s.get("visible") or {}).items():
            base = name.rsplit("/", 1)[-1]
            start[f"tests/test_{directory}_{base.removeprefix('test_')}"] = relocate(text, directory)
        for name, text in s["hidden"].items():
            base = name.rsplit("/", 1)[-1]
            hidden[f"tests/test_{directory}_{base.removeprefix('test_')}"] = relocate(text, directory)
        for name, text in s["solution"].items():
            solution[f"svc/{directory}/{name}"] = text
        main = next(n for n in s["start"] if n.endswith(".py"))
        findings.append(f"{number}. `svc/{directory}/{main}` ({s['product']}): {s['finding']}")
        notes.append(f"{s['slug']}: {s['cwe']}")
    system = SYSTEMS[idx % len(SYSTEMS)]
    prompt = (f"A penetration test of {system} reported {len(chosen)} findings in the code under `svc/` (every subdirectory is an independent component with its own `README.md` that says what it is supposed to do; "
              f"there are tests for the normal behaviour and for hostile input). Fix all of them in the code: the whole class of each problem, not just the example payloads, with every documented behaviour for "
              f"legitimate input kept, odd-looking but valid input included. Do not touch the tests.\n\n" + "\n".join(findings))
    slug = f"{idx + 1:02d}-incident-{len(chosen)}-findings"
    return Task(slug=slug, prompt=prompt, difficulty=difficulty, kind="fix", lang="python", start=start, hidden=hidden, solution=solution, verify=langs.VERIFY["python"], timeout_s=240,
                tags=["security", "bundle", "multi-issue"], notes={"components": notes})


@family("security-incident-bundle", category="security", lang="python", kind="fix", n=12,
        summary="penetration-test report with 4 to 8 independent findings across components: every fix needs its own hidden tests to pass")
def gen_bundle(rng, n):
    pool = eligible()
    return [make_task(i, PLAN[i], rng, pool) for i in range(n)]
