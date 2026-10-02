"""Version compatibility across the release notes of three fictional components: each release declares requirements on the
others (ranges, wildcards, exact pins), some releases are yanked, and requirements are checked in both directions."""
from __future__ import annotations

import datetime as dt

from fx import dd, family

from . import _world as W

SUFFIX_NAMES = ["Fenwick", "Lathe", "Pyre", "Quillon", "Marram", "Tessel", "Brindle", "Corrach", "Dunnock", "Skerry", "Nacre", "Umber", "Kestrel", "Loam"]


def vs(v):
    return ".".join(map(str, v))


def make_versions(rng, count: int):
    out = []
    major, minor, patch = rng.randint(1, 2), rng.randint(0, 3), 0
    for _ in range(count):
        out.append((major, minor, patch))
        r = rng.random()
        if r < 0.2:
            major, minor, patch = major + 1, 0, 0
        elif r < 0.6:
            minor, patch = minor + 1, 0
        else:
            patch += rng.randint(1, 2)
    return out


def make_constraint(rng, target_versions):
    """(text for prose, list of terms) where a term is (op, ver) with op in >=, <, ==, minor"""
    kind = rng.choice(["ge", "range", "range", "minor", "eq"])
    vlist = target_versions
    a = rng.choice(vlist)
    if kind == "ge":
        return [(">=", a)]
    if kind == "range":
        later = [v for v in vlist if v > a]
        b = rng.choice(later) if later else (a[0] + 1, 0, 0)
        return [(">=", a), ("<", b)]
    if kind == "minor":
        return [("minor", (a[0], a[1]))]
    return [("==", a)]


def holds(terms, v) -> bool:
    for op, a in terms:
        if op == ">=" and not v >= a:
            return False
        if op == "<" and not v < a:
            return False
        if op == "==" and v != a:
            return False
        if op == "minor" and v[:2] != a:
            return False
    return True


def term_text(terms, style: str, name: str = "") -> str:
    parts = []
    for op, a in terms:
        if op == "minor":
            parts.append(f"{a[0]}.{a[1]}.*")
        elif op == "==":
            parts.append(f"=={vs(a)}")
        else:
            parts.append(f"{op}{vs(a)}")
    return ", ".join(parts)


def build(rng):
    names = rng.sample(SUFFIX_NAMES, 3)
    comps = {}
    base = W.base_date(rng)
    for n in names:
        vers = make_versions(rng, rng.randint(4, 9))
        d = base
        dates = []
        for _ in vers:
            d += dt.timedelta(days=rng.randint(10, 60))
            dates.append(d)
        comps[n] = dict(versions=vers, dates=dates, yanked=set(), reqs={})
    for n, c in comps.items():
        for i in range(len(c["versions"])):
            if rng.random() < 0.12:
                c["yanked"].add(i)
        others = [m for m in names if m != n]
        for i in range(len(c["versions"])):
            for m in others:
                p = 0.85 if n == names[0] else 0.4
                if rng.random() < p:
                    c["reqs"].setdefault(i, {})[m] = make_constraint(rng, comps[m]["versions"] if m in comps else [])
    return names, comps


def installable(names, comps, target, inst):
    """versions (indexes) of ``target`` compatible with the installed versions in ``inst`` (name -> version tuple)"""
    out = []
    t = comps[target]
    for i, v in enumerate(t["versions"]):
        if i in t["yanked"]:
            continue
        ok = True
        for m, ver in inst.items():
            # the candidate's own requirements on m
            terms = t["reqs"].get(i, {}).get(m)
            if terms and not holds(terms, ver):
                ok = False
            # the installed version's requirements on the candidate
            mc = comps[m]
            mi = mc["versions"].index(ver)
            terms2 = mc["reqs"].get(mi, {}).get(target)
            if terms2 and not holds(terms2, v):
                ok = False
        if ok:
            out.append(i)
    return out


def render(rng, names, comps):
    files: dict[str, str] = {}
    styles = ["md", "table", "news"]
    rng.shuffle(styles)
    for n, st in zip(names, styles):
        c = comps[n]
        rows = []
        for i, v in reversed(list(enumerate(c["versions"]))):
            req = c["reqs"].get(i, {})
            if st == "md":
                lines = [f"## {n} {vs(v)} ({W.d_iso(c['dates'][i])})"]
                if req:
                    lines.append("Requires: " + "; ".join(f"{m} {term_text(t, 'md')}" for m, t in sorted(req.items())))
                else:
                    lines.append("Requires: nothing else")
                if i in c["yanked"]:
                    lines.append("**YANKED**: withdrawn after release, do not install.")
                lines.append(rng.choice(["Bug fixes.", "Performance work.", "Documentation updates.", "Internal cleanups.", "Improved error messages."]))
                rows.append("\n".join(lines) + "\n")
            elif st == "news":
                req_s = ("needs " + " and ".join(f"{m} {term_text(t, 'news')}" for m, t in sorted(req.items()))) if req else "has no outside requirements"
                y = " [YANKED - do not install]" if i in c["yanked"] else ""
                rows.append(f"{vs(v)}  {W.d_long(c['dates'][i])}{y}\n    This release {req_s}.\n")
        if st == "table":
            trows = []
            for i, v in enumerate(c["versions"]):
                req = c["reqs"].get(i, {})
                r_ = ";".join(f"{m} {term_text(t, 'md').replace(', ', ',')}" for m, t in sorted(req.items()))
                trows.append([vs(v), W.d_iso(c["dates"][i]), r_, "yanked" if i in c["yanked"] else "ok"])
            files[f"releases/{n.lower()}.csv"] = W.csv_text(["version", "released", "requires", "status"], trows)
        elif st == "md":
            files[f"releases/{n.lower()}-CHANGELOG.md"] = f"# {n} changelog\n\n" + "\n".join(rows)
        else:
            files[f"releases/{n.lower()}-NEWS.txt"] = f"{n.upper()} RELEASE NEWS\n\n" + "\n".join(rows)
    files["README.md"] = dd("""
        # Component release notes

        Three components, each with its own release notes in `releases/` (formats differ). A release's requirements name other
        components and a version condition:

        * `>=2.1.0`, `<3.0.0`, `==1.4.2`; a list like `>=2.1.0, <3.0.0` means all of them;
        * `1.4.*` means any 1.4.x release (at least 1.4.0 and below 1.5.0).

        Releases marked yanked or "do not install" can never be used. Two components work together if, for the versions chosen, each
        one's requirements on the other (if it states any) are satisfied. A requirement a release does not state means no restriction.
        Versions compare number by number (1.10.0 is newer than 1.9.0).
    """)
    return files


@family("research-compat-matrix", category="research", lang="text", kind="lookup", n=16, mode="answer",
        summary="newest installable release of a component given installed versions of the others, with two-way requirements and yanked releases")
def gen(rng, n):
    made = 0
    while made < n:
        names, comps = build(rng)
        target = names[0]
        t = comps[target]
        others = names[1:]
        inst = {}
        for m in others:
            cands = [v for i, v in enumerate(comps[m]["versions"]) if i not in comps[m]["yanked"]]
            inst[m] = rng.choice(cands)
        # the installed components must already work with each other, or "no stated requirement broken" has no answer
        a_, b_ = others
        ia = comps[a_]["versions"].index(inst[a_])
        ib = comps[b_]["versions"].index(inst[b_])
        t1 = comps[a_]["reqs"].get(ia, {}).get(b_)
        t2 = comps[b_]["reqs"].get(ib, {}).get(a_)
        if (t1 and not holds(t1, inst[b_])) or (t2 and not holds(t2, inst[a_])):
            continue
        ok = installable(names, comps, target, inst)
        if not ok:
            continue
        newest_overall = max(i for i in range(len(t["versions"])) if i not in t["yanked"])
        qk = rng.choice(["newest", "newest", "count"])
        files = render(rng, names, comps)
        org = W.make_org(rng, "software", n_people=4)
        ins_s = " and ".join(f"{m} {vs(v)}" for m, v in inst.items())
        if qk == "newest":
            best = max(ok)
            ans = vs(t["versions"][best])
            if best == newest_overall and rng.random() < 0.7:
                continue
            ph = [f"We run {ins_s}. What is the newest {target} release we can install without breaking any stated requirement? Give the version number.",
                  f"Our setup has {ins_s} installed. Which is the latest {target} that is compatible with that? (Remember to check the requirements both ways, and skip withdrawn releases.)",
                  f"Can you work out the highest {target} version that works alongside {ins_s}? Just the version string."]
            prompt, contains, gold = rng.choice(ph), [ans], f"{target} {ans} is the newest compatible release."
            if ans in prompt:
                continue
            diff = 3 + (best != newest_overall) + (len(t["versions"]) >= 7)
        else:
            k = len(ok)
            ins, c = W.numfmt(rng, k, ("Count", "Total", "Answer"))
            ph = [f"With {ins_s} installed, how many different {target} releases could we install (excluding yanked ones, and respecting requirements in both directions)?{ins}",
                  f"Count the {target} releases that are compatible with {ins_s} (not yanked; both sides' requirements satisfied).{ins}"]
            prompt, contains, gold = rng.choice(ph), [c], f"{k} releases. {c}"
            diff = 3 + (len(t["versions"]) >= 7)
        made += 1
        yield W.say_task(slug=f"{made:02d}-{qk}", prompt=W.voice(rng, org, prompt), difficulty=diff, start=files, contains=contains, gold=gold,
                         tags=["versions", "dependencies"], notes={"target": target, "installed": {m: vs(v) for m, v in inst.items()}, "question": qk})
