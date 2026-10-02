"""DevOps tasks: systemd unit files (services, timers, sockets). A policy validator parses the unit files with systemd's rules (repeatable keys, resets, booleans, calendar expressions)."""
import json
from dataclasses import dataclass, field

from fx import dd, family
from generators.devops import _dokit as K

CHECK_UNITS = r'''
from dolib import *
import datetime as dt

R = json.load(open("tests/rules.json", encoding="utf-8"))
rep = Report()
BOOL = {"yes", "no", "true", "false", "on", "off", "1", "0"}
BOOLKEYS = {"NoNewPrivileges", "PrivateTmp", "PrivateDevices", "PrivateNetwork", "ProtectKernelTunables", "ProtectKernelModules", "ProtectControlGroups", "RemainAfterExit", "RestrictSUIDSGID", "LockPersonality",
            "MemoryDenyWriteExecute", "Persistent", "Accept", "StandardInput_", "SyslogLevelPrefix", "RestrictRealtime", "DefaultDependencies", "RemoveIPC", "WakeSystem", "RemainAfterElapse"}
LISTKEYS = {"After", "Before", "Requires", "Wants", "BindsTo", "PartOf", "Conflicts", "WantedBy", "RequiredBy", "Also", "Environment", "EnvironmentFile", "ReadWritePaths", "ReadOnlyPaths", "ExecStartPre", "ExecStartPost", "ExecStopPost",
            "ListenStream", "ListenDatagram", "OnCalendar", "CapabilityBoundingSet", "AmbientCapabilities", "ExecStart", "ExecStop", "ExecReload", "SupplementaryGroups"}
SECTIONS = {"Unit": {"Description", "Documentation", "After", "Before", "Requires", "Wants", "BindsTo", "PartOf", "Conflicts", "ConditionPathExists", "ConditionFileNotEmpty", "OnFailure", "StartLimitIntervalSec", "StartLimitBurst", "DefaultDependencies", "RequiresMountsFor"},
            "Service": {"Type", "ExecStart", "ExecStartPre", "ExecStartPost", "ExecStop", "ExecStopPost", "ExecReload", "Restart", "RestartSec", "User", "Group", "SupplementaryGroups", "WorkingDirectory", "Environment", "EnvironmentFile", "PIDFile", "RemainAfterExit",
                        "TimeoutStartSec", "TimeoutStopSec", "TimeoutSec", "KillMode", "KillSignal", "NoNewPrivileges", "PrivateTmp", "PrivateDevices", "PrivateNetwork", "ProtectSystem", "ProtectHome", "ProtectKernelTunables", "ProtectKernelModules",
                        "ProtectControlGroups", "ReadWritePaths", "ReadOnlyPaths", "CapabilityBoundingSet", "AmbientCapabilities", "RestrictSUIDSGID", "LockPersonality", "MemoryDenyWriteExecute", "RestrictRealtime", "RestrictAddressFamilies", "SystemCallFilter",
                        "StateDirectory", "RuntimeDirectory", "LogsDirectory", "CacheDirectory", "ConfigurationDirectory", "LimitNOFILE", "LimitNPROC", "MemoryMax", "CPUQuota", "TasksMax", "Nice", "UMask", "StandardOutput", "StandardError", "SyslogIdentifier",
                        "WatchdogSec", "OOMScoreAdjust", "DynamicUser", "ProtectProc", "NotifyAccess", "IOSchedulingClass", "SuccessExitStatus", "RestartPreventExitStatus", "RemoveIPC", "Sockets", "StandardInput"},
            "Install": {"WantedBy", "RequiredBy", "Alias", "Also"}, "Timer": {"OnCalendar", "Persistent", "RandomizedDelaySec", "Unit", "AccuracySec", "OnBootSec", "OnUnitActiveSec", "WakeSystem", "RemainAfterElapse", "OnActiveSec"},
            "Socket": {"ListenStream", "ListenDatagram", "Accept", "SocketUser", "SocketGroup", "SocketMode", "Service", "BindIPv6Only", "Backlog", "KeepAlive", "NoDelay", "MaxConnections", "FreeBind", "DirectoryMode"}}
TYPES = {"simple", "exec", "forking", "oneshot", "notify", "dbus", "idle"}
RESTARTS = {"no", "on-success", "on-failure", "on-abnormal", "on-abort", "on-watchdog", "always"}


def seconds(s):
    s = s.strip()
    if re.fullmatch(r"\d+", s):
        return int(s)
    units = {"us": 1e-6, "ms": 1e-3, "s": 1, "sec": 1, "second": 1, "seconds": 1, "m": 60, "min": 60, "minute": 60, "minutes": 60, "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600, "d": 86400, "day": 86400, "days": 86400}
    parts = re.findall(r"(\d+)\s*([a-z]+)", s)
    if not parts or re.sub(r"\d+\s*[a-z]+\s*", "", s):
        return None
    tot = 0
    for n, u in parts:
        if u not in units:
            return None
        tot += int(n) * units[u]
    return tot


def parse_unit(path):
    text = read(path)
    secs, cur, buf = {}, None, ""
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.rstrip()
        if buf:
            line = buf + line.lstrip()
            buf = ""
        if line.endswith("\\"):
            buf = line[:-1] + " "
            continue
        s = line.strip()
        if not s or s[0] in "#;":
            continue
        m = re.fullmatch(r"\[([A-Za-z]+)\]", s)
        if m:
            cur = m.group(1)
            if cur not in SECTIONS:
                die(f"{path} line {n}: unknown section [{cur}]")
            secs.setdefault(cur, [])
            continue
        if "=" not in s:
            die(f"{path} line {n}: missing '=' in line {s!r}")
        if cur is None:
            die(f"{path} line {n}: assignment outside of any section")
        k, _, v = s.partition("=")
        k, v = k.strip(), v.strip()
        if k not in SECTIONS[cur]:
            rep.check(False, f"{path} line {n}: unknown key {k!r} in section [{cur}] (misspelled, or in the wrong section?)")
        if k in BOOLKEYS and v.lower() not in BOOL:
            rep.check(False, f"{path} line {n}: {k}={v} is not a valid boolean (use yes or no)")
        secs[cur].append((k, v, n))
    return secs


def eff(secs, sec, key):
    """Effective values: list keys accumulate and an empty assignment resets them; scalars: the last one wins."""
    vals = []
    for k, v, n in secs.get(sec, []):
        if k != key:
            continue
        if k in LISTKEYS:
            if v == "":
                vals = []
            elif k in ("After", "Before", "Requires", "Wants", "BindsTo", "PartOf", "Conflicts", "WantedBy", "RequiredBy", "ReadWritePaths", "ReadOnlyPaths", "ListenStream", "CapabilityBoundingSet", "AmbientCapabilities", "SupplementaryGroups"):
                vals += v.split()
            else:
                vals.append(v)
        else:
            vals = [v]
    return vals


def one(secs, sec, key, default=None):
    v = eff(secs, sec, key)
    return v[-1] if v else default


# ------------------------------------------------------------------ calendar expressions (a subset of systemd.time(7))
DOWS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def field_set(txt, lo, hi, what):
    out = set()
    for part in txt.split(","):
        m = re.fullmatch(r"(\*|\d+(?:\.\.\d+)?)(?:/(\d+))?", part)
        if not m:
            raise ValueError(f"bad {what} field {part!r}")
        step = int(m.group(2)) if m.group(2) else None
        if m.group(1) == "*":
            a, b = lo, hi
        elif ".." in m.group(1):
            a, b = (int(x) for x in m.group(1).split(".."))
        else:
            a = int(m.group(1))
            b = hi if step else a
        if not (lo <= a <= b <= hi):
            raise ValueError(f"{what} value out of range in {part!r}")
        out.update(range(a, b + 1, step or 1))
    return out


def calendar(expr):
    e = expr.strip().lower()
    short = {"minutely": "*-*-* *:*:00", "hourly": "*-*-* *:00:00", "daily": "*-*-* 00:00:00", "weekly": "mon *-*-* 00:00:00", "monthly": "*-*-01 00:00:00", "yearly": "*-01-01 00:00:00", "quarterly": "*-01,04,07,10-01 00:00:00"}
    if e in short:
        e = short[e]
    toks = e.split()
    dow, date, time = None, "*-*-*", None
    for t in toks:
        if re.search(r"[a-z]", t):
            names = []
            for p in t.split(","):
                if ".." in p:
                    a, b = p.split("..")
                    if a not in DOWS or b not in DOWS:
                        raise ValueError(f"bad weekday {p!r}")
                    i, j = DOWS.index(a), DOWS.index(b)
                    names += DOWS[i:j + 1] if i <= j else DOWS[i:] + DOWS[:j + 1]
                elif p in DOWS:
                    names.append(p)
                else:
                    raise ValueError(f"bad weekday {p!r} (use Mon..Fri, Sat,Sun)")
            dow = {DOWS.index(x) for x in names}
        elif ":" in t:
            time = t
        elif "-" in t:
            date = t
        else:
            raise ValueError(f"cannot parse {t!r}")
    d = date.split("-")
    if len(d) == 2:
        d = ["*"] + d
    if len(d) != 3:
        raise ValueError("bad date part")
    ys, ms, ds = field_set(d[0], 1970, 2200, "year"), field_set(d[1], 1, 12, "month"), field_set(d[2], 1, 31, "day")
    tp = (time or ("00:00:00" if dow is not None or date != "*-*-*" or True else "")).split(":")
    if len(tp) == 2:
        tp.append("0")
    if len(tp) != 3:
        raise ValueError("bad time part")
    hs, mi = field_set(tp[0], 0, 23, "hour"), field_set(tp[1], 0, 59, "minute")
    return dow, ys, ms, ds, hs, mi


def fires(exprs, start, end):
    out = set()
    for e in exprs:
        dow, ys, ms, ds, hs, mi = calendar(e)
        d = start.replace(hour=0, minute=0)
        while d < end:
            if d.year in ys and d.month in ms and d.day in ds and (dow is None or d.weekday() in dow):
                for h in hs:
                    for m in mi:
                        t = d.replace(hour=h, minute=m)
                        if start <= t < end:
                            out.add(t)
            d += dt.timedelta(days=1)
    return out


units = {}
for name in R["units"]:
    units[name] = parse_unit(name)
known = set(R["known"]) | set(R["units"])

for name, rule in R["units"].items():
    secs = units[name]
    kind = name.rsplit(".", 1)[1]
    if kind == "service":
        sv = secs.get("Service")
        if not rep.check(sv is not None, f"{name}: needs a [Service] section"):
            continue
        typ = one(secs, "Service", "Type", "simple")
        rep.check(typ in TYPES, f"{name}: Type={typ} is not a valid service type")
        rep.check(typ == rule.get("type", "simple"), f"{name}: Type must be {rule.get('type', 'simple')} (got {typ})")
        starts = eff(secs, "Service", "ExecStart")
        if typ != "oneshot":
            rep.check(len(starts) == 1, f"{name}: a {typ} service needs exactly one ExecStart= (found {len(starts)}); only Type=oneshot may have several")
        for s in starts:
            first = s.lstrip("@-:+!").split()[0] if s.strip() else ""
            rep.check(first.startswith("/"), f"{name}: ExecStart={s} - the program must be an absolute path")
        if rule.get("exec") is not None:
            rep.check(starts == rule["exec"], f"{name}: ExecStart must be {rule['exec']} in this order (got {starts})")
        for key, dflt in (("pre", "ExecStartPre"), ("post", "ExecStartPost"), ("reload", "ExecReload")):
            if rule.get(key) is not None:
                rep.check(eff(secs, "Service", dflt) == rule[key], f"{name}: {dflt} must be {rule[key]} (got {eff(secs, 'Service', dflt)})")
        if typ == "forking" or rule.get("pidfile"):
            pf = one(secs, "Service", "PIDFile")
            rep.check(bool(pf) and pf.startswith("/"), f"{name}: a forking service needs PIDFile= with an absolute path")
            if rule.get("pidfile"):
                rep.check(pf == rule["pidfile"], f"{name}: PIDFile must be {rule['pidfile']}")
        if rule.get("user") is not None:
            rep.check(one(secs, "Service", "User") == rule["user"], f"{name}: User must be {rule['user']!r} (got {one(secs, 'Service', 'User')!r})")
        if rule.get("restart"):
            pol, lo, hi = rule["restart"]
            r = one(secs, "Service", "Restart", "no")
            rep.check(r in RESTARTS, f"{name}: Restart={r} is not valid")
            rep.check(r == pol, f"{name}: Restart must be {pol} (got {r})")
            rs = one(secs, "Service", "RestartSec")
            sec = seconds(rs) if rs else None
            rep.check(sec is not None and lo <= sec <= hi, f"{name}: RestartSec must be a time span between {lo}s and {hi}s (got {rs!r})")
        for sec_, key in (("Unit", "After"), ("Unit", "Before"), ("Unit", "Requires"), ("Unit", "Wants")):
            want = rule.get(key.lower())
            have = eff(secs, sec_, key)
            if want is not None:
                rep.check(sorted(set(want)) == sorted(set(have)), f"{name}: {key}= must be exactly {sorted(want)} (got {sorted(have)})")
            for u in have:
                rep.check(u in known or u.endswith(".target") and u in known, f"{name}: {key}={u} refers to a unit that does not exist here or on the system ({sorted(known)})")
        for req in eff(secs, "Unit", "Requires") + eff(secs, "Unit", "BindsTo"):
            rep.check(req in eff(secs, "Unit", "After") or req in eff(secs, "Unit", "Before"), f"{name}: Requires={req} does not order the units; add After={req} (or Before=)")
        for w in eff(secs, "Unit", "Wants"):
            if w == "network-online.target":
                rep.check(w in eff(secs, "Unit", "After"), f"{name}: Wants=network-online.target only has an effect together with After=network-online.target")
        if "wantedby" in rule:
            wb = eff(secs, "Install", "WantedBy")
            if rule["wantedby"] is None:
                rep.check(not wb, f"{name}: must not be enabled directly (no WantedBy=); it is started by another unit")
            else:
                rep.check(rule["wantedby"] in wb, f"{name}: [Install] WantedBy= must contain {rule['wantedby']} (got {wb})")
        for key, val in rule.get("harden", {}).items():
            have = eff(secs, "Service", key)
            if key in ("ReadWritePaths", "CapabilityBoundingSet"):
                if key == "CapabilityBoundingSet" and val == []:
                    rep.check(any(k == key and v == "" for k, v, _ in secs.get("Service", [])) or have == [], f"{name}: CapabilityBoundingSet= must be empty (an empty assignment drops all capabilities)")
                else:
                    rep.check(set(val) <= {p.lstrip("-+") for p in have}, f"{name}: {key}= must include {val} (got {have})")
            elif isinstance(val, list):
                rep.check(bool(have) and have[-1].lower() in val, f"{name}: {key} must be one of {val} (got {have[-1] if have else None})")
            else:
                rep.check(bool(have) and have[-1].lower() in ({"yes", "true", "on", "1"} if val == "yes" else {val}), f"{name}: {key} must be {val} (got {have[-1] if have else None})")
        if rule.get("harden", {}).get("ProtectSystem") and one(secs, "Service", "ProtectSystem") == "strict":
            rw = {p.lstrip("-+") for p in eff(secs, "Service", "ReadWritePaths")}
            managed = {"/var/lib/" + d for d in eff(secs, "Service", "StateDirectory")} | {"/var/log/" + d for d in eff(secs, "Service", "LogsDirectory")} | {"/var/cache/" + d for d in eff(secs, "Service", "CacheDirectory")} | {"/run/" + d for d in eff(secs, "Service", "RuntimeDirectory")}
            for p in rule.get("writes", []):
                rep.check(p in rw or p.rstrip("/") in managed, f"{name}: with ProtectSystem=strict the service writes to {p}, which needs ReadWritePaths= (or StateDirectory=/LogsDirectory=/CacheDirectory=)")
        env = {}
        for e in eff(secs, "Service", "Environment"):
            for kv in re.findall(r'"[^"]*"|\S+', e):
                kv = kv.strip('"')
                if "=" not in kv:
                    rep.check(False, f"{name}: Environment={e!r}: every assignment must be KEY=value")
                    continue
                k, _, v = kv.partition("=")
                env[k] = v
        for k, v in rule.get("env", {}).items():
            rep.check(env.get(k) == v, f"{name}: Environment must set {k}={v!r} (got {env.get(k)!r})")
        if rule.get("env_files") is not None:
            rep.check(eff(secs, "Service", "EnvironmentFile") == rule["env_files"], f"{name}: EnvironmentFile must be {rule['env_files']}")
        for k, v in rule.get("extra", {}).items():
            rep.check(one(secs, "Service", k) == v, f"{name}: {k} must be {v!r} (got {one(secs, 'Service', k)!r})")
        if rule.get("remain"):
            rep.check(one(secs, "Service", "RemainAfterExit", "no").lower() in ("yes", "true", "on", "1"), f"{name}: RemainAfterExit=yes is needed so that the unit stays active after the script ran")
    elif kind == "timer":
        tm = secs.get("Timer")
        if not rep.check(tm is not None, f"{name}: needs a [Timer] section"):
            continue
        exprs = eff(secs, "Timer", "OnCalendar")
        if rep.check(bool(exprs), f"{name}: needs OnCalendar="):
            try:
                for w in R["windows"]:
                    a, b = dt.datetime.fromisoformat(w[0]), dt.datetime.fromisoformat(w[1])
                    got, want = fires(exprs, a, b), fires(rule["calendars"], a, b)
                    if got != want:
                        miss, extra = sorted(want - got), sorted(got - want)
                        fm = lambda xs: ", ".join(t.strftime("%a %Y-%m-%d %H:%M") for t in xs[:3]) + (f" (+{len(xs) - 3})" if len(xs) > 3 else "")
                        rep.check(False, f"{name}: OnCalendar={exprs} fires differently in {w[0]}..{w[1]}: " + (f"missing {fm(miss)}" if miss else "") + ("; " if miss and extra else "") + (f"unexpected {fm(extra)}" if extra else ""))
                        break
            except ValueError as e:
                rep.check(False, f"{name}: OnCalendar={exprs}: {e}")
        if rule.get("persistent") is not None:
            rep.check(one(secs, "Timer", "Persistent", "no").lower() in ({"yes", "true", "on", "1"} if rule["persistent"] else {"no", "false", "off", "0"}), f"{name}: Persistent must be {'yes' if rule['persistent'] else 'no'}")
        if rule.get("random_max") is not None:
            rd = one(secs, "Timer", "RandomizedDelaySec")
            sec = seconds(rd) if rd else None
            rep.check(sec is not None and sec == rule["random_max"], f"{name}: RandomizedDelaySec must be {rule['random_max']} seconds (got {rd!r})")
        target = one(secs, "Timer", "Unit", name[:-6] + ".service")
        rep.check(target in R["units"], f"{name}: activates {target}, which is not one of this project's units")
        if "wantedby" in rule:
            rep.check(rule["wantedby"] in eff(secs, "Install", "WantedBy"), f"{name}: [Install] WantedBy= must contain {rule['wantedby']}")
    elif kind == "socket":
        so = secs.get("Socket")
        if not rep.check(so is not None, f"{name}: needs a [Socket] section"):
            continue
        rep.check(sorted(eff(secs, "Socket", "ListenStream")) == sorted(rule["listen"]), f"{name}: ListenStream must be {rule['listen']} (got {eff(secs, 'Socket', 'ListenStream')})")
        if rule.get("accept"):
            rep.check(one(secs, "Socket", "Accept", "no").lower() in ({"no", "false", "off", "0"} if rule["accept"] == "no" else {"yes", "true", "on", "1"}), f"{name}: Accept must be {rule['accept']}")
        if "wantedby" in rule:
            rep.check(rule["wantedby"] in eff(secs, "Install", "WantedBy"), f"{name}: [Install] WantedBy= must contain {rule['wantedby']}")
rep.finish()
'''


@dataclass
class UnitSpec:
    slug: str
    d: int
    prompt: str
    rules: dict  # per-unit rules
    ref: dict  # filename -> text
    start: dict  # filename -> text
    wrong: list = field(default_factory=list)
    kind: str = "author"


KNOWN = ["network.target", "network-online.target", "multi-user.target", "timers.target", "sockets.target", "postgresql.service", "redis.service", "nginx.service", "docker.service", "local-fs.target", "remote-fs.target"]
WINDOWS = [("2024-02-26T00:00", "2024-03-11T00:00"), ("2024-04-29T00:00", "2024-06-03T00:00"), ("2024-12-23T00:00", "2025-01-06T00:00")]


def rules_doc(rules):
    lines = ["# Unit rules", "", "The unit files are parsed with systemd's rules (sections, `Key=value`, `\\` continuations; list settings such as `After=`, `Environment=` and `ExecStart=` of oneshot services accumulate and an empty assignment resets them) and checked against the following. An unknown section or key, a misspelled boolean or a relative program path is an error.", ""]
    n = 1
    for name, r in rules["units"].items():
        kind = name.rsplit(".", 1)[1]
        items = []
        if kind == "service":
            items.append(f"`Type={r.get('type', 'simple')}`" + ("; exactly one `ExecStart=` unless the type is `oneshot`; the program of every `ExecStart=` is an absolute path" if r.get("type", "simple") != "oneshot" else "; every `ExecStart=` program is an absolute path"))
            if r.get("exec"):
                items.append("effective `ExecStart=` (in this order): " + "; ".join(f"`{e}`" for e in r["exec"]))
            if r.get("pre"):
                items.append("`ExecStartPre=`: " + "; ".join(f"`{e}`" for e in r["pre"]))
            if r.get("reload"):
                items.append("`ExecReload=`: " + "; ".join(f"`{e}`" for e in r["reload"]))
            if r.get("pidfile"):
                items.append(f"`PIDFile={r['pidfile']}` (forking services need an absolute `PIDFile=`)")
            if r.get("user"):
                items.append(f"`User={r['user']}`")
            if r.get("restart"):
                items.append(f"`Restart={r['restart'][0]}` and `RestartSec=` a time span between {r['restart'][1]} s and {r['restart'][2]} s (`5`, `5s`, `1min 30s` are all fine)")
            for key in ("after", "before", "requires", "wants"):
                if r.get(key) is not None:
                    items.append(f"`{key.capitalize()}=` is exactly {{{', '.join(r[key])}}}" if r[key] else f"no `{key.capitalize()}=`")
            items.append("every unit named in `After=`/`Before=`/`Requires=`/`Wants=` exists in the project or on the system (known system units: " + ", ".join(f"`{k}`" for k in KNOWN) + "); `Requires=X` also needs `After=X`; `Wants=network-online.target` only works with `After=network-online.target`")
            if "wantedby" in r:
                items.append("`[Install] WantedBy=" + r["wantedby"] + "`" if r["wantedby"] else "no `[Install] WantedBy=` (another unit starts it)")
            for k, v in r.get("harden", {}).items():
                if isinstance(v, list):
                    items.append(f"`{k}=` " + ("includes " if k in ("ReadWritePaths", "CapabilityBoundingSet") else "is one of ") + ", ".join(f"`{x}`" for x in v) if v else "`CapabilityBoundingSet=` is empty (drops every capability)")
                else:
                    items.append(f"`{k}={v}`")
            if r.get("writes"):
                items.append("with `ProtectSystem=strict` the file system is read-only except `ReadWritePaths=` and the managed directories (`StateDirectory=x` is `/var/lib/x`, `LogsDirectory=x` is `/var/log/x`, `CacheDirectory=x` is `/var/cache/x`); the service writes to " + ", ".join(f"`{p}`" for p in r["writes"]))
            for k, v in r.get("env", {}).items():
                items.append(f"`Environment=` sets `{k}={v}`")
            if r.get("env_files") is not None:
                items.append("`EnvironmentFile=` " + ("is " + ", ".join(f"`{e}`" for e in r["env_files"]) if r["env_files"] else "is not used"))
            for k, v in r.get("extra", {}).items():
                items.append(f"`{k}={v}`")
            if r.get("remain"):
                items.append("`RemainAfterExit=yes`")
        elif kind == "timer":
            items.append("`OnCalendar=` fires at exactly the same moments as the intended schedule (the checker compares the firing minutes over several weeks; this is not cron: a weekday list is `Mon..Fri`, `Sat,Sun`; the day-of-week and the date must both match)")
            if r.get("persistent") is not None:
                items.append(f"`Persistent={'yes' if r['persistent'] else 'no'}`")
            if r.get("random_max") is not None:
                items.append(f"`RandomizedDelaySec={r['random_max']}` seconds")
            items.append("the unit it activates (`Unit=`, or the service of the same name) is one of the project's units")
            if "wantedby" in r:
                items.append(f"`[Install] WantedBy={r['wantedby']}`")
        elif kind == "socket":
            items.append("`ListenStream=` " + ", ".join(f"`{x}`" for x in r["listen"]))
            if r.get("accept"):
                items.append(f"`Accept={r['accept']}`")
            if "wantedby" in r:
                items.append(f"`[Install] WantedBy={r['wantedby']}`")
        lines.append(f"{n}. **`{name}`**: " + "; ".join(items) + ".")
        n += 1
    return "\n".join(lines) + "\n"


def make_task(sp: UnitSpec):
    rules = {"units": sp.rules, "known": KNOWN, "windows": WINDOWS}
    start = dict(sp.start)
    start["UNIT_RULES.md"] = rules_doc(rules)
    start["README.md"] = "# systemd units\n\nThe unit files of this directory are checked against `UNIT_RULES.md`.\n"
    hidden = {"tests/rules.json": json.dumps(rules, indent=1) + "\n"}
    t = K.devops_task(sp.slug, sp.d, sp.prompt, start, sp.ref, CHECK_UNITS, hidden, lang="text", kind="fix" if sp.kind == "fix" else "greenfield", tags=["systemd", "unit", "timer", "linux", "config"])
    return K.finish(t, wrong=sp.wrong)


SPECS: list[UnitSpec] = []


def spec(**kw):
    SPECS.append(UnitSpec(**kw))


NOTE = " `UNIT_RULES.md` lists what the unit files are checked against."

# 1 ------------------------------------------------------------------------------------------------------------------
spec(slug="service-basics", d=2, kind="author",
     prompt="Write `sluice.service` for the queue worker `/usr/local/bin/sluice --queue jobs --workers 4`: it runs as the user `sluice`, is restarted when it fails (wait 5 seconds between attempts), needs the network to be really up before it starts, and is enabled in the normal multi-user boot." + NOTE,
     rules={"sluice.service": {"type": "simple", "exec": ["/usr/local/bin/sluice --queue jobs --workers 4"], "user": "sluice", "restart": ["on-failure", 1, 60], "after": ["network-online.target"], "wants": ["network-online.target"], "wantedby": "multi-user.target"}},
     start={"sluice.service": "# TODO\n"},
     ref={"sluice.service": dd('''
        [Unit]
        Description=Sluice queue worker
        After=network-online.target
        Wants=network-online.target

        [Service]
        Type=simple
        ExecStart=/usr/local/bin/sluice --queue jobs --workers 4
        User=sluice
        Restart=on-failure
        RestartSec=5

        [Install]
        WantedBy=multi-user.target
     ''')},
     wrong=[{"sluice.service": "[Unit]\nDescription=x\nAfter=network.target\n\n[Service]\nExecStart=/usr/local/bin/sluice --queue jobs --workers 4\nUser=sluice\nRestart=always\nRestartSec=5\n\n[Install]\nWantedBy=multi-user.target\n"}])

# 2 ------------------------------------------------------------------------------------------------------------------
spec(slug="exec-forking-fix", d=2, kind="fix",
     prompt="`systemctl start pharos` fails with several complaints about `pharos.service`: the daemon double-forks (it is a forking service that writes `/run/pharos/pharos.pid`), and the unit has other mistakes. Fix the unit so that it is valid: keep the daemon command `/opt/pharos/bin/pharosd --daemon`, the user `pharos` and the restart policy (on-failure, 10 seconds)." + NOTE,
     rules={"pharos.service": {"type": "forking", "exec": ["/opt/pharos/bin/pharosd --daemon"], "pidfile": "/run/pharos/pharos.pid", "user": "pharos", "restart": ["on-failure", 1, 60], "harden": {"NoNewPrivileges": "yes"}, "wantedby": "multi-user.target"}},
     start={"pharos.service": dd('''
        [Unit]
        Description=Pharos daemon

        [Service]
        ExecStart=pharosd --daemon
        ExecStart=/opt/pharos/bin/pharosd --daemon
        User=pharos
        Restart=on-failure
        RestartSec=10
        NoNewPrivileges=enabled

        [Install]
        WantedBy=multi-user.target
     ''')},
     ref={"pharos.service": dd('''
        [Unit]
        Description=Pharos daemon

        [Service]
        Type=forking
        PIDFile=/run/pharos/pharos.pid
        ExecStart=/opt/pharos/bin/pharosd --daemon
        User=pharos
        Restart=on-failure
        RestartSec=10
        NoNewPrivileges=yes

        [Install]
        WantedBy=multi-user.target
     ''')},
     wrong=[{"pharos.service": "[Unit]\nDescription=x\n\n[Service]\nType=simple\nExecStart=/opt/pharos/bin/pharosd --daemon\nUser=pharos\nRestart=on-failure\nRestartSec=10\nNoNewPrivileges=yes\n\n[Install]\nWantedBy=multi-user.target\n"}])

# 3 ------------------------------------------------------------------------------------------------------------------
spec(slug="ordering-fix", d=3, kind="fix",
     prompt="`ledger.service` starts before its database is up and before the network is usable, and `systemd-analyze verify` complains about a missing unit. The service needs PostgreSQL (`postgresql.service`) and Redis (`redis.service`; it can run without it but should be started with it) and the network to be online. Fix the ordering and the dependencies; the program, user and the rest stay." + NOTE,
     rules={"ledger.service": {"type": "simple", "exec": ["/usr/local/bin/ledgerd --config /etc/ledger.toml"], "user": "ledger", "requires": ["postgresql.service"], "wants": ["redis.service", "network-online.target"], "after": ["network-online.target", "postgresql.service", "redis.service"], "wantedby": "multi-user.target", "restart": ["on-failure", 1, 60]}},
     start={"ledger.service": dd('''
        [Unit]
        Description=Ledger service
        After=network.target
        Requires=postgresql.service
        Wants=redis-server.service

        [Service]
        ExecStart=/usr/local/bin/ledgerd --config /etc/ledger.toml
        User=ledger
        Restart=on-failure
        RestartSec=3

        [Install]
        WantedBy=graphical.target
     ''')},
     ref={"ledger.service": dd('''
        [Unit]
        Description=Ledger service
        After=network-online.target postgresql.service redis.service
        Wants=redis.service network-online.target
        Requires=postgresql.service

        [Service]
        ExecStart=/usr/local/bin/ledgerd --config /etc/ledger.toml
        User=ledger
        Restart=on-failure
        RestartSec=3

        [Install]
        WantedBy=multi-user.target
     ''')},
     wrong=[{"ledger.service": "[Unit]\nDescription=x\nAfter=network-online.target postgresql.service redis.service\nRequires=postgresql.service redis.service\nWants=network-online.target\n\n[Service]\nExecStart=/usr/local/bin/ledgerd --config /etc/ledger.toml\nUser=ledger\nRestart=on-failure\nRestartSec=3\n\n[Install]\nWantedBy=multi-user.target\n"}])

# 4 ------------------------------------------------------------------------------------------------------------------
spec(slug="sandboxing", d=3, kind="author",
     prompt="Harden `/etc/systemd/system/quillweb.service` (write the unit `quillweb.service`) for the web app `/opt/quill/bin/quillweb --port 8081`, run as `quill`: no privilege escalation, a private /tmp, the whole file system read-only except where the app has to write (`/var/lib/quill` for its data and `/var/cache/quill` for its cache; `/home` is not accessible, no capabilities at all), restarted on failure after 5 s, enabled in multi-user boot, starting after the network." + NOTE,
     rules={"quillweb.service": {"type": "simple", "exec": ["/opt/quill/bin/quillweb --port 8081"], "user": "quill", "restart": ["on-failure", 1, 60], "after": ["network.target"], "wantedby": "multi-user.target",
                                 "harden": {"NoNewPrivileges": "yes", "PrivateTmp": "yes", "ProtectSystem": ["strict"], "ProtectHome": ["yes", "true"], "CapabilityBoundingSet": []}, "writes": ["/var/lib/quill", "/var/cache/quill"]}},
     start={"quillweb.service": "# TODO\n"},
     ref={"quillweb.service": dd('''
        [Unit]
        Description=Quill web
        After=network.target

        [Service]
        ExecStart=/opt/quill/bin/quillweb --port 8081
        User=quill
        Restart=on-failure
        RestartSec=5
        NoNewPrivileges=yes
        PrivateTmp=yes
        ProtectSystem=strict
        ProtectHome=yes
        StateDirectory=quill
        CacheDirectory=quill
        CapabilityBoundingSet=

        [Install]
        WantedBy=multi-user.target
     ''')},
     wrong=[{"quillweb.service": "[Unit]\nDescription=x\nAfter=network.target\n\n[Service]\nExecStart=/opt/quill/bin/quillweb --port 8081\nUser=quill\nRestart=on-failure\nRestartSec=5\nNoNewPrivileges=yes\nPrivateTmp=yes\nProtectSystem=strict\nProtectHome=yes\nCapabilityBoundingSet=\n\n[Install]\nWantedBy=multi-user.target\n"}])

# 5 ------------------------------------------------------------------------------------------------------------------
spec(slug="backup-timer", d=3, kind="author",
     prompt="Write the pair `backup.service` and `backup.timer`: the service is a one-shot job (`/usr/local/sbin/backup-run --full`, user `backup`) with no `[Install]` section of its own; the timer runs it every day at 02:30, catches up when the machine was off at that time, adds a random delay of up to 15 minutes (900 s), and is enabled with the timers target." + NOTE,
     rules={"backup.service": {"type": "oneshot", "exec": ["/usr/local/sbin/backup-run --full"], "user": "backup", "wantedby": None},
            "backup.timer": {"calendars": ["*-*-* 02:30:00"], "persistent": True, "random_max": 900, "wantedby": "timers.target"}},
     start={"backup.service": "# TODO\n", "backup.timer": "# TODO\n"},
     ref={"backup.service": dd('''
        [Unit]
        Description=Nightly backup

        [Service]
        Type=oneshot
        ExecStart=/usr/local/sbin/backup-run --full
        User=backup
     '''), "backup.timer": dd('''
        [Unit]
        Description=Run the backup every night

        [Timer]
        OnCalendar=*-*-* 02:30:00
        Persistent=true
        RandomizedDelaySec=15min

        [Install]
        WantedBy=timers.target
     ''')},
     wrong=[{"backup.timer": "[Unit]\nDescription=x\n\n[Timer]\nOnCalendar=daily\nPersistent=true\nRandomizedDelaySec=15min\n\n[Install]\nWantedBy=timers.target\n"}])

# 6 ------------------------------------------------------------------------------------------------------------------
spec(slug="calendar-expressions", d=4, kind="author",
     prompt="Write the timers (and a trivial one-shot service for each: `ExecStart=/usr/bin/true`, no `[Install]`): `office.timer` fires hourly on the hour from 09:00 to 17:00 on Monday to Friday (nine times a day); `monthly.timer` at 06:00 on the first day of each month; `quarter.timer` at 00:00 on the first day of January, April, July and October; `weekend.timer` at 06:30 on Saturday and Sunday; `fifteen.timer` every 15 minutes, all day, every day. All timers are enabled with the timers target. Remember it is not cron: use systemd calendar expressions." + NOTE,
     rules={**{f"{n}.service": {"type": "oneshot", "exec": ["/usr/bin/true"], "wantedby": None} for n in ("office", "monthly", "quarter", "weekend", "fifteen")},
            "office.timer": {"calendars": ["Mon..Fri *-*-* 09..17:00:00"], "wantedby": "timers.target"}, "monthly.timer": {"calendars": ["*-*-01 06:00:00"], "wantedby": "timers.target"},
            "quarter.timer": {"calendars": ["*-01,04,07,10-01 00:00:00"], "wantedby": "timers.target"}, "weekend.timer": {"calendars": ["Sat,Sun *-*-* 06:30:00"], "wantedby": "timers.target"}, "fifteen.timer": {"calendars": ["*-*-* *:00/15:00"], "wantedby": "timers.target"}},
     start={f"{n}.{k}": "# TODO\n" for n in ("office", "monthly", "quarter", "weekend", "fifteen") for k in ("service", "timer")},
     ref={**{f"{n}.service": "[Unit]\nDescription=" + n + " job\n\n[Service]\nType=oneshot\nExecStart=/usr/bin/true\n" for n in ("office", "monthly", "quarter", "weekend", "fifteen")},
          "office.timer": "[Unit]\nDescription=office\n\n[Timer]\nOnCalendar=Mon..Fri *-*-* 09..17:00:00\n\n[Install]\nWantedBy=timers.target\n",
          "monthly.timer": "[Unit]\nDescription=monthly\n\n[Timer]\nOnCalendar=*-*-01 06:00:00\n\n[Install]\nWantedBy=timers.target\n",
          "quarter.timer": "[Unit]\nDescription=quarter\n\n[Timer]\nOnCalendar=*-01,04,07,10-01 00:00:00\n\n[Install]\nWantedBy=timers.target\n",
          "weekend.timer": "[Unit]\nDescription=weekend\n\n[Timer]\nOnCalendar=Sat,Sun *-*-* 06:30:00\n\n[Install]\nWantedBy=timers.target\n",
          "fifteen.timer": "[Unit]\nDescription=fifteen\n\n[Timer]\nOnCalendar=*:0/15\n\n[Install]\nWantedBy=timers.target\n"},
     wrong=[{"office.timer": "[Unit]\nDescription=office\n\n[Timer]\nOnCalendar=Mon..Fri *-*-* *:00:00\n\n[Install]\nWantedBy=timers.target\n"}])

# 7 ------------------------------------------------------------------------------------------------------------------
spec(slug="timer-repair", d=3, kind="fix",
     prompt="The timer `report.timer` never fires. It should run `report.service` (a one-shot job, `/opt/report/run`) every weekday (Monday to Friday) at 07:45, catch up after downtime and be enabled with the timers target. Someone wrote it with cron habits. Repair the timer (and anything else wrong in the two files)." + NOTE,
     rules={"report.service": {"type": "oneshot", "exec": ["/opt/report/run"], "user": "report", "wantedby": None}, "report.timer": {"calendars": ["Mon..Fri *-*-* 07:45:00"], "persistent": True, "wantedby": "timers.target"}},
     start={"report.service": dd('''
        [Unit]
        Description=Weekday report

        [Service]
        Type=oneshot
        ExecStart=/opt/report/run
        User=report

        [Install]
        WantedBy=multi-user.target
     '''), "report.timer": dd('''
        [Unit]
        Description=Weekday report timer

        [Timer]
        OnCalendar=45 7 * * 1-5
        Unit=reports.service

        [Install]
        WantedBy=multi-user.target
     ''')},
     ref={"report.service": dd('''
        [Unit]
        Description=Weekday report

        [Service]
        Type=oneshot
        ExecStart=/opt/report/run
        User=report
     '''), "report.timer": dd('''
        [Unit]
        Description=Weekday report timer

        [Timer]
        OnCalendar=Mon..Fri *-*-* 07:45:00
        Persistent=true

        [Install]
        WantedBy=timers.target
     ''')},
     wrong=[{"report.timer": "[Unit]\nDescription=x\n\n[Timer]\nOnCalendar=Mon,Fri *-*-* 07:45:00\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n"}])

# 8 ------------------------------------------------------------------------------------------------------------------
spec(slug="socket-activation", d=4, kind="author",
     prompt="Write socket activation for the echo server: `echo.socket` listens on `127.0.0.1:7007` (TCP stream), a single service instance handles all connections (`Accept=no`), and it is enabled with the sockets target. `echo.service` runs `/opt/echo/bin/echod --systemd` as user `echo` (Type simple), is started by the socket and so has **no** `[Install]` section, requires its socket and is ordered after it." + NOTE,
     rules={"echo.socket": {"listen": ["127.0.0.1:7007"], "accept": "no", "wantedby": "sockets.target"},
            "echo.service": {"type": "simple", "exec": ["/opt/echo/bin/echod --systemd"], "user": "echo", "requires": ["echo.socket"], "after": ["echo.socket"], "wantedby": None}},
     start={"echo.socket": "# TODO\n", "echo.service": "# TODO\n"},
     ref={"echo.socket": dd('''
        [Unit]
        Description=Echo socket

        [Socket]
        ListenStream=127.0.0.1:7007
        Accept=no

        [Install]
        WantedBy=sockets.target
     '''), "echo.service": dd('''
        [Unit]
        Description=Echo server
        Requires=echo.socket
        After=echo.socket

        [Service]
        ExecStart=/opt/echo/bin/echod --systemd
        User=echo
     ''')},
     wrong=[{"echo.service": "[Unit]\nDescription=x\nRequires=echo.socket\nAfter=echo.socket\n\n[Service]\nExecStart=/opt/echo/bin/echod --systemd\nUser=echo\n\n[Install]\nWantedBy=multi-user.target\n"}])

# 9 ------------------------------------------------------------------------------------------------------------------
spec(slug="migration-oneshot", d=3, kind="author",
     prompt="Write `migrate.service`: a one-shot unit that must finish before `wharf.service` starts (it runs `/opt/wharf/bin/wharf migrate --up` as `wharf`, after a pre-check `/opt/wharf/bin/wharf check-db`, and has to stay 'active' after it ran so that units depending on it see it as started), needs `postgresql.service`, and is wanted by the multi-user target. Also write `wharf.service` (`/opt/wharf/bin/wharf serve`, user `wharf`, restart on failure after 5 s) that requires and starts after `migrate.service`. Both start after the network is online." + NOTE,
     rules={"migrate.service": {"type": "oneshot", "pre": ["/opt/wharf/bin/wharf check-db"], "exec": ["/opt/wharf/bin/wharf migrate --up"], "user": "wharf", "remain": True, "before": ["wharf.service"], "requires": ["postgresql.service"], "wants": ["network-online.target"], "after": ["postgresql.service", "network-online.target"], "wantedby": "multi-user.target"},
            "wharf.service": {"type": "simple", "exec": ["/opt/wharf/bin/wharf serve"], "user": "wharf", "restart": ["on-failure", 1, 60], "requires": ["migrate.service"], "wants": ["network-online.target"], "after": ["migrate.service", "network-online.target"], "wantedby": "multi-user.target"}},
     start={"migrate.service": "# TODO\n", "wharf.service": "# TODO\n"},
     ref={"migrate.service": dd('''
        [Unit]
        Description=Wharf database migration
        Requires=postgresql.service
        Wants=network-online.target
        After=postgresql.service network-online.target
        Before=wharf.service

        [Service]
        Type=oneshot
        RemainAfterExit=yes
        User=wharf
        ExecStartPre=/opt/wharf/bin/wharf check-db
        ExecStart=/opt/wharf/bin/wharf migrate --up

        [Install]
        WantedBy=multi-user.target
     '''), "wharf.service": dd('''
        [Unit]
        Description=Wharf
        Requires=migrate.service
        Wants=network-online.target
        After=migrate.service network-online.target

        [Service]
        ExecStart=/opt/wharf/bin/wharf serve
        User=wharf
        Restart=on-failure
        RestartSec=5

        [Install]
        WantedBy=multi-user.target
     ''')},
     wrong=[{"migrate.service": "[Unit]\nDescription=x\nRequires=postgresql.service\nWants=network-online.target\nAfter=postgresql.service network-online.target\nBefore=wharf.service\n\n[Service]\nType=oneshot\nUser=wharf\nExecStartPre=/opt/wharf/bin/wharf check-db\nExecStart=/opt/wharf/bin/wharf migrate --up\n\n[Install]\nWantedBy=multi-user.target\n"}])

# 10 -----------------------------------------------------------------------------------------------------------------
spec(slug="service-and-cleanup-timer", d=5, kind="author",
     prompt="Write the units of the `atlas` application. `atlas.service`: `/opt/atlas/bin/atlas serve --config /etc/atlas/atlas.toml`, user `atlas`, `ExecReload=/bin/kill -HUP $MAINPID`, environment `ATLAS_ENV=production` and `ATLAS_WORKERS=8`, optional environment file `/etc/atlas/atlas.env` (the leading `-` makes a missing file fine), restart on failure after 10 s, `LimitNOFILE=65536`; ordering: after `network-online.target`, `postgresql.service` and `redis.service`, requires PostgreSQL, wants Redis and the online network; hardening: `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome=yes`, state in `/var/lib/atlas` and logs in `/var/log/atlas` (managed directories), no capabilities; enabled in multi-user boot. "
            "`atlas-cleanup.service`: a one-shot (`/opt/atlas/bin/atlas cleanup --older-than 30d`, user `atlas`, no `[Install]`) and `atlas-cleanup.timer`: every Sunday at 03:15, persistent, randomized delay up to 30 minutes (1800 s), enabled with the timers target." + NOTE,
     rules={"atlas.service": {"type": "simple", "exec": ["/opt/atlas/bin/atlas serve --config /etc/atlas/atlas.toml"], "reload": ["/bin/kill -HUP $MAINPID"], "user": "atlas", "restart": ["on-failure", 1, 60], "env": {"ATLAS_ENV": "production", "ATLAS_WORKERS": "8"}, "env_files": ["-/etc/atlas/atlas.env"],
                              "extra": {"LimitNOFILE": "65536"}, "after": ["network-online.target", "postgresql.service", "redis.service"], "requires": ["postgresql.service"], "wants": ["redis.service", "network-online.target"], "wantedby": "multi-user.target",
                              "harden": {"NoNewPrivileges": "yes", "PrivateTmp": "yes", "ProtectSystem": ["strict"], "ProtectHome": ["yes", "true"], "CapabilityBoundingSet": []}, "writes": ["/var/lib/atlas", "/var/log/atlas"]},
            "atlas-cleanup.service": {"type": "oneshot", "exec": ["/opt/atlas/bin/atlas cleanup --older-than 30d"], "user": "atlas", "wantedby": None},
            "atlas-cleanup.timer": {"calendars": ["Sun *-*-* 03:15:00"], "persistent": True, "random_max": 1800, "wantedby": "timers.target"}},
     start={"atlas.service": "# TODO\n", "atlas-cleanup.service": "# TODO\n", "atlas-cleanup.timer": "# TODO\n"},
     ref={"atlas.service": dd('''
        [Unit]
        Description=Atlas
        After=network-online.target postgresql.service redis.service
        Wants=redis.service network-online.target
        Requires=postgresql.service

        [Service]
        ExecStart=/opt/atlas/bin/atlas serve --config /etc/atlas/atlas.toml
        ExecReload=/bin/kill -HUP $MAINPID
        User=atlas
        Environment=ATLAS_ENV=production "ATLAS_WORKERS=8"
        EnvironmentFile=-/etc/atlas/atlas.env
        Restart=on-failure
        RestartSec=10
        LimitNOFILE=65536
        NoNewPrivileges=yes
        PrivateTmp=yes
        ProtectSystem=strict
        ProtectHome=yes
        StateDirectory=atlas
        LogsDirectory=atlas
        CapabilityBoundingSet=

        [Install]
        WantedBy=multi-user.target
     '''), "atlas-cleanup.service": dd('''
        [Unit]
        Description=Atlas cleanup

        [Service]
        Type=oneshot
        ExecStart=/opt/atlas/bin/atlas cleanup --older-than 30d
        User=atlas
     '''), "atlas-cleanup.timer": dd('''
        [Unit]
        Description=Weekly Atlas cleanup

        [Timer]
        OnCalendar=Sun *-*-* 03:15:00
        Persistent=true
        RandomizedDelaySec=30min

        [Install]
        WantedBy=timers.target
     ''')},
     wrong=[{"atlas-cleanup.timer": "[Unit]\nDescription=x\n\n[Timer]\nOnCalendar=weekly\nPersistent=true\nRandomizedDelaySec=30min\n\n[Install]\nWantedBy=timers.target\n"}])


def _tasks(rng, n):
    return [make_task(s) for s in SPECS[:n]]


@family("devops-systemd-units", category="devops", lang="text", kind="fix", n=len(SPECS),
        summary="write or repair systemd services, timers and sockets against a parsed-unit policy: ExecStart rules, ordering, hardening, restart policy, calendar expressions compared by firing times")
def systemd_units(rng, n):
    return _tasks(rng, n)
