"""A fleet of service configs sharing scarce resources (ports, cron minutes): the manager has to hand out disjoint allocations."""
from __future__ import annotations

import json

from fx import Task, dd, family

from ._kit import GRADE_CMD, oxford, score_script, team

NAMES = ["gateway", "billing", "catalog", "search", "mailer", "reports", "ledger", "sessions", "uploads", "notifier", "exporter", "cleaner",
         "indexer", "scheduler", "auditor", "thumbs", "rollup", "mirror", "beacon", "courier"]
TIERS = ["edge", "core", "batch"]
HELPER_KEYS = ("needs_admin", "upstream_service", "pinned")

CHECK_BODY = r'''import json
import os
import sys

RULES = json.loads(__RULES__)
NAMES = RULES["names"]
HELPER = ("needs_admin", "upstream_service", "pinned")


def load(name):
    with open(os.path.join("services", name, "service.json"), encoding="utf-8") as f:
        return json.load(f)


def problems_for(name, cfgs):
    out = []
    cfg = {k: v for k, v in cfgs[name].items() if k not in HELPER}
    meta = RULES["services"][name]
    tier = meta["tier"]
    lo, hi = RULES["ranges"][tier]
    if cfg.get("name") != name or cfg.get("tier") != tier:
        out.append("name and tier must stay %s / %s" % (name, tier))
    ports = cfg.get("ports")
    if not isinstance(ports, dict):
        return out + ["ports are missing"]
    want_keys = {"http", "metrics"} | ({"admin"} if meta["admin"] else set())
    if set(ports) != want_keys:
        return out + ["ports must be exactly %s, found %s" % (sorted(want_keys), sorted(ports))]
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in ports.values()):
        return out + ["ports must be integers"]
    if ports["metrics"] != ports["http"] + RULES["metrics_offset"]:
        out.append("metrics must be http + %d" % RULES["metrics_offset"])
    if meta["admin"] and ports["admin"] != ports["http"] + RULES["admin_offset"]:
        out.append("admin must be http + %d" % RULES["admin_offset"])
    for kind, v in ports.items():
        if not lo <= v <= hi:
            out.append("%s port %d is outside the %s range %d-%d" % (kind, v, tier, lo, hi))
        if v in RULES["reserved"]:
            out.append("%s port %d is reserved" % (kind, v))
        for other in NAMES:
            others = cfgs[other].get("ports") if other != name else None
            if isinstance(others, dict) and v in others.values():
                out.append("%s port %d is also used by %s" % (kind, v, other))
    if meta["pinned"] and cfg != meta["pinned"]:
        out.append("this service is pinned and must not change")
    if tier == "batch":
        m = cfg.get("cron_minute")
        if not isinstance(m, int) or isinstance(m, bool) or not 0 <= m <= 59:
            out.append("cron_minute must be an integer from 0 to 59")
        else:
            for other in NAMES:
                if other != name and RULES["services"][other]["tier"] == "batch":
                    om = cfgs[other].get("cron_minute")
                    if isinstance(om, int) and abs(om - m) < RULES["spacing"]:
                        out.append("cron_minute %d is closer than %d minutes to %s (%d)" % (m, RULES["spacing"], other, om))
    up = meta["upstream"]
    if up:
        up_ports = cfgs[up].get("ports")
        want = "http://%s:%s" % (up, up_ports.get("http") if isinstance(up_ports, dict) else None)
        if cfg.get("upstream") != want:
            out.append("upstream must be %r (the http port of %s), found %r" % (want, up, cfg.get("upstream")))
    elif "upstream" in cfg:
        out.append("this service has no upstream")
    return out
'''

VISIBLE_MAIN = r'''

def main():
    try:
        cfgs = {n: load(n) for n in NAMES}
    except (OSError, ValueError) as e:
        print("cannot read the service files:", e)
        return 1
    only = sys.argv[1:] or NAMES
    bad = 0
    for n in only:
        for line in problems_for(n, cfgs):
            print("%s: %s" % (n, line))
            bad += 1
    print("ok" if not bad else "%d problem(s)" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
'''

HIDDEN_MAIN = r'''

def helper_keys_intact(cfgs):
    for n in NAMES:
        meta = RULES["services"][n]
        cfg = cfgs[n]
        if cfg.get("needs_admin") != meta["admin"]:
            return ["%s: needs_admin was changed" % n]
        if meta["upstream"] and cfg.get("upstream_service") != meta["upstream"]:
            return ["%s: upstream_service was changed" % n]
    return []


if __name__ == "__main__":
    what = sys.argv[1]
    try:
        cfgs = {n: load(n) for n in NAMES}
    except (OSError, ValueError) as e:
        print("FAILED: cannot read the service files:", e, file=sys.stderr)
        sys.exit(1)
    if what == "fleet":
        probs = helper_keys_intact(cfgs)
        for n in NAMES:
            probs += ["%s: %s" % (n, p) for p in problems_for(n, cfgs)]
    else:
        probs = ["%s: %s" % (what, p) for p in problems_for(what, cfgs)]
    for p in probs:
        print(p, file=sys.stderr)
    sys.exit(1 if probs else 0)
'''


def allocate(rules, services, rng):
    used = set(rules["reserved"])
    for m in services.values():
        if m["pinned"]:
            used.update(m["pinned"]["ports"].values())
    out = {}
    minutes = {n: m["pinned"]["cron_minute"] for n, m in services.items() if m["pinned"] and m["tier"] == "batch"}
    order = [n for n in rules["names"] if not services[n]["pinned"]]
    rng.shuffle(order)
    for n in order:
        m = services[n]
        lo, hi = rules["ranges"][m["tier"]]
        offs = [0, rules["metrics_offset"]] + ([rules["admin_offset"]] if m["admin"] else [])
        port = next((c for c in range(lo, hi + 1) if all(lo <= c + o <= hi and c + o not in used for o in offs)), None)
        if port is None:
            raise RuntimeError("cannot allocate " + n)
        used.update(port + o for o in offs)
        cfg = {"name": n, "tier": m["tier"], "ports": {"http": port, "metrics": port + rules["metrics_offset"]}}
        if m["admin"]:
            cfg["ports"]["admin"] = port + rules["admin_offset"]
        if m["tier"] == "batch":
            slot = next((c for c in range(60) if all(abs(c - o) >= rules["spacing"] for o in minutes.values())), None)
            if slot is None:
                raise RuntimeError("no cron slot")
            cfg["cron_minute"] = slot
            minutes[n] = slot
        out[n] = cfg
    for n, cfg in out.items():
        up = services[n]["upstream"]
        if up:
            http = (out.get(up) or services[up]["pinned"])["ports"]["http"]
            cfg["upstream"] = f"http://{up}:{http}"
    return out


@family("swarm-port-allocation", category="swarm", lang="mixed", kind="feature", n=8,
        summary="k service configs that must draw disjoint ports and cron slots from shared ranges and reference each other's ports")
def port_allocation(rng, n):
    ks = [4, 5, 5, 6, 6, 7, 8, 8]
    for i in range(n):
        k = ks[i % len(ks)]
        names = sorted(rng.sample(NAMES, k))
        tiers = {nm: (TIERS[j % 3] if j < 3 else rng.choice(TIERS)) for j, nm in enumerate(rng.sample(names, k))}
        mo = rng.choice([1, 1, 2, 10, 100])
        ao = rng.choice([2, 3]) if mo < 2 else mo + rng.choice([1, 2])
        edge_lo = rng.choice([8000, 8080, 8400])
        batch_n = sum(1 for t in tiers.values() if t == "batch")
        spacing = min(rng.choice([3, 5, 7]), 59 // max(1, batch_n + 1))
        ranges = {"edge": [edge_lo, edge_lo + 59 + mo], "core": [9000, 9159 + ao], "batch": [9500, 9539 + ao]}
        reserved = sorted(set(rng.sample(range(8000, 9600), 14) + [ranges["core"][0] + 1, ranges["edge"][0], ranges["batch"][0]]))
        rules = {"names": names, "metrics_offset": mo, "admin_offset": ao, "spacing": spacing, "ranges": ranges, "reserved": reserved}
        services = {nm: {"tier": tiers[nm], "admin": rng.random() < 0.5, "upstream": None, "pinned": None} for nm in names}
        for nm in names:
            if rng.random() < 0.55:
                services[nm]["upstream"] = rng.choice([x for x in names if x != nm])
        pins = rng.sample(names, 1 if k < 6 else 2)
        taken = set(reserved)
        pin_minutes = []
        for nm in pins:
            t = tiers[nm]
            lo, hi = ranges[t]
            offs = [0, mo] + ([ao] if services[nm]["admin"] else [])
            while True:
                port = rng.randrange(lo + 3, hi - max(offs) - 3)
                if all(port + o not in taken for o in offs):
                    break
            taken.update(port + o for o in offs)
            cfg = {"name": nm, "tier": t, "ports": {"http": port, "metrics": port + mo}}
            if services[nm]["admin"]:
                cfg["ports"]["admin"] = port + ao
            if t == "batch":
                while True:
                    minute = rng.randrange(0, 60)
                    if all(abs(minute - x) >= spacing for x in pin_minutes):
                        break
                pin_minutes.append(minute)
                cfg["cron_minute"] = minute
            services[nm]["pinned"] = cfg
            services[nm]["upstream"] = None  # a pinned file is complete and has no upstream wiring
        rules["services"] = services
        sol = allocate(rules, services, rng)
        start = {
            "README.md": dd('''
                # Fleet configs

                Every service has a `services/<name>/service.json`. `ALLOCATION.md` lists the rules for the shared resources and what each file needs.
                `python3 tools/check_fleet.py [name ...]` checks the rules for all services or the ones named.
            '''),
            "ALLOCATION.md": dd(f'''
                # Allocation rules

                All services run on the same hosts, so the resources below are shared and must never be handed out twice.

                ## Ports

                * Every service has `http` and `metrics` ports, and an `admin` port if its file says `"needs_admin": true`.
                * `metrics` is always `http + {mo}`; `admin`, when present, is `http + {ao}`.
                * Tier ranges (inclusive; **all** of a service's ports must lie inside its tier's range):
                  edge {ranges["edge"][0]}-{ranges["edge"][1]}, core {ranges["core"][0]}-{ranges["core"][1]}, batch {ranges["batch"][0]}-{ranges["batch"][1]}.
                * No port may be used by two services, whatever kind of port it is.
                * Reserved, never to be used: {", ".join(str(x) for x in reserved)}.

                ## Batch schedules

                * Every `batch` service has an integer `cron_minute` (0-59): the minute of each hour at which it starts. Two batch services must start at least
                  {spacing} minutes apart (the absolute difference of their minutes is at least {spacing}; there is no wrap-around at the hour).

                ## Upstreams

                * A file with `"upstream_service": "<name>"` also needs `"upstream": "http://<name>:<http port of that service>"`, using that service's *final* http port.
                  Files without `upstream_service` have no `upstream` key.

                ## Pinned services

                * Some services are pinned: they are already deployed and their files are complete (`"pinned": true`). They must not change, and no other service may use
                  their ports or batch minutes.
            '''),
            "tools/check_fleet.py": "\n".join(['"""Check the allocation rules: python3 tools/check_fleet.py [service ...]"""']) + "\n" +
                                    CHECK_BODY.replace("__RULES__", repr(json.dumps({**rules, "services": {nm: {**v} for nm, v in services.items()}}, sort_keys=True))) + VISIBLE_MAIN,
        }
        todo = [nm for nm in names if not services[nm]["pinned"]]
        for nm in names:
            m = services[nm]
            if m["pinned"]:
                start[f"services/{nm}/service.json"] = json.dumps({**m["pinned"], "needs_admin": m["admin"], "pinned": True}, indent=2) + "\n"
            else:
                cfg = {"name": nm, "tier": m["tier"], "needs_admin": m["admin"], "ports": {}}
                if m["upstream"]:
                    cfg["upstream_service"] = m["upstream"]
                start[f"services/{nm}/service.json"] = json.dumps(cfg, indent=2) + "\n"
        solution = {}
        for nm in todo:
            cfg = dict(sol[nm])
            cfg["needs_admin"] = services[nm]["admin"]
            if services[nm]["upstream"]:
                cfg["upstream_service"] = services[nm]["upstream"]
            solution[f"services/{nm}/service.json"] = json.dumps(cfg, indent=2) + "\n"
        hidden_src = '"""hidden unit check"""\n' + CHECK_BODY.replace("__RULES__", repr(json.dumps({**rules, "services": {nm: {**v} for nm, v in services.items()}}, sort_keys=True))) + HIDDEN_MAIN
        hidden = {".grade/fleet_unit.py": hidden_src}
        units = [{"name": f"service {nm}", "cmd": ["python3", ".grade/fleet_unit.py", nm], "weight": 1} for nm in todo]
        units.append({"name": "whole fleet", "cmd": ["python3", ".grade/fleet_unit.py", "fleet"], "weight": max(1, k // 3)})
        hidden[".grade/score.py"] = score_script(units)
        voices = [
            f"We're re-laying the port and schedule map for our {k} services and several of the files are empty shells. ALLOCATION.md has the rules. Fill in every unpinned "
            f"service.json so that nothing collides; `tools/check_fleet.py` checks the result. Splitting the work is fine, but nobody must hand out the same port twice.",
            f"Please complete the service configs for {oxford(todo)}. Ports, batch minutes and upstream URLs come from the rules in ALLOCATION.md; the pinned services are already "
            f"live and must not move. Run tools/check_fleet.py when done.",
            f"Each service in services/ needs its ports (and, for batch jobs, a cron minute that does not clash). The rules are in ALLOCATION.md. Several agents will edit "
            f"different files, so agree on who takes which range before anybody writes a number.",
            f"Config chore: allocate ports and schedules for the unpinned services under services/ following ALLOCATION.md, and wire the upstream URLs. "
            f"The shared resources are what makes this fiddly; the check script shows whether it holds.",
        ]
        d = 3 if k <= 5 else 4 if k <= 7 else 5
        yield Task(
            slug=f"{i + 1:02d}-k{k}-mo{mo}",
            prompt=voices[i % len(voices)], difficulty=d,
            start=start, hidden=hidden, solution=solution, protected=[f"services/{nm}/service.json" for nm in pins],
            verify=GRADE_CMD, pass_mode="json-score",
            team=team(rng, min(len(todo), 6), ["backend", "reviewer"] if i % 2 else ["backend", "tester"]),
            tags=["shared-resources", "coordination", "config"],
            notes={"services": k, "pinned": pins, "metrics_offset": mo, "admin_offset": ao, "spacing": spacing},
        )
