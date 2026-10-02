"""A small cron simulator (shipped to the agent as tools/cronsim.py, used by the hidden checker)."""

CRONSIM = r'''#!/usr/bin/env python3
"""cronsim.py - parse a crontab the way Vixie cron / cronie do (documented subset) and list when each job runs.

    python3 tools/cronsim.py CRONTAB START END [--system]

START and END are local times like 2024-03-01T00:00 (END excluded); the machine's clock is UTC. With --system the file is an
/etc/cron.d style file whose lines have a user name before the command.

Rules (all of them are checked):
  * five time fields minute hour day-of-month month day-of-week, or one of @yearly @annually @monthly @weekly @daily @midnight @hourly @reboot;
  * a field is a comma separated list of `*`, `N`, `A-B`, `*/S` or `A-B/S` (steps count from the start of the range: */7 on minutes is 0,7,...,56 and restarts every hour);
  * ranges: minute 0-59, hour 0-23, day of month 1-31, month 1-12, day of week 0-7 (0 and 7 are Sunday);
  * month and weekday may be written as three-letter names (jan..dec, sun..sat) but ONLY as a single value: names inside ranges or lists are rejected (`mon-fri` is an error);
  * if both day-of-month and day-of-week are restricted (neither field starts with `*`) the job runs when EITHER matches; if one of them starts with `*` (even `*/2`), BOTH conditions must hold;
  * lines `NAME=value` set environment variables; blank lines and `#` comments are ignored;
  * a `%` in the command that is not written `\\%` is an error (cron would turn it into a newline);
  * a command may start with a shell guard `[ ... ] && /path/job` (or `test ... && /path/job`): the guard is evaluated for every candidate run time, with `date` answering for that time
    (so `date +%d` is the day of that run and `date -d tomorrow +%d` the day after); the job only runs when the guard lets the rest of the command run.
    Only `date` substitutions are allowed inside the guard; commands that do not start with `[` or `test` are not executed by the simulator.
"""
import datetime as dt
import os
import re
import subprocess
import sys
import tempfile

MACROS = {"@yearly": "0 0 1 1 *", "@annually": "0 0 1 1 *", "@monthly": "0 0 1 * *", "@weekly": "0 0 * * 0", "@daily": "0 0 * * *", "@midnight": "0 0 * * *", "@hourly": "0 * * * *"}
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]


class CronError(Exception):
    pass


def field(text, lo, hi, names=None):
    out = set()
    if names and text.lower() in names:
        v = names.index(text.lower()) + (1 if lo == 1 else 0)
        return {v}, False
    for part in text.split(","):
        if not part:
            raise CronError(f"empty element in field {text!r}")
        if names and re.search(r"[A-Za-z]", part):
            raise CronError(f"names are not allowed in ranges or lists: {text!r}")
        m = re.fullmatch(r"(\*|(\d+)(?:-(\d+))?)(?:/(\d+))?", part)
        if not m:
            raise CronError(f"bad field {text!r}")
        step = int(m.group(4)) if m.group(4) else 1
        if step < 1:
            raise CronError(f"step must be at least 1 in {text!r}")
        if m.group(1) == "*":
            a, b = lo, hi
        else:
            a = int(m.group(2))
            b = int(m.group(3)) if m.group(3) is not None else (hi if m.group(4) else a)
            if not (lo <= a <= hi and lo <= b <= hi) or a > b:
                raise CronError(f"value out of range in {text!r} (allowed {lo}-{hi})")
        out.update(range(a, b + 1, step))
    return out, text.startswith("*")


def parse(text, system=False):
    env, jobs = {}, []
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
        if m:
            env[m.group(1)] = m.group(2).strip("\"'")
            continue
        parts = line.split(None, 5 if not line.startswith("@") else 1)
        try:
            if line.startswith("@"):
                macro = parts[0].lower()
                if macro == "@reboot":
                    spec, rest = None, parts[1:]
                elif macro in MACROS:
                    spec, rest = MACROS[macro].split(), parts[1:]
                else:
                    raise CronError(f"unknown macro {parts[0]!r}")
                rest = rest[0] if rest else ""
            else:
                if len(parts) < 6:
                    raise CronError("a job line needs five time fields and a command")
                spec, rest = parts[:5], parts[5]
            user = None
            if system:
                bits = rest.split(None, 1)
                if len(bits) < 2 or not re.fullmatch(r"[a-z_][a-z0-9_-]*\$?", bits[0]):
                    raise CronError("system crontab lines need a user name after the time fields (got %r)" % (bits[0] if bits else ""))
                user, rest = bits
            if not rest.strip():
                raise CronError("missing command")
            if re.search(r"(?<!\\)%", rest):
                raise CronError("unescaped % in the command (write \\%)")
            job = {"line": n, "text": line, "command": rest.strip(), "user": user, "reboot": spec is None}
            if spec is not None:
                mi, _ = field(spec[0], 0, 59)
                ho, _ = field(spec[1], 0, 23)
                dom, dstar = field(spec[2], 1, 31)
                mo, _ = field(spec[3], 1, 12, MONTHS)
                dow, wstar = field(spec[4], 0, 7, DAYS)
                dow = {d % 7 for d in dow}
                job.update(minute=mi, hour=ho, dom=dom, month=mo, dow=dow, dom_star=dstar, dow_star=wstar)
            jobs.append(job)
        except CronError as e:
            raise CronError(f"line {n}: {e}")
    return env, jobs


def day_ok(job, d):
    if d.month not in job["month"]:
        return False
    dm, dw = d.day in job["dom"], ((d.weekday() + 1) % 7) in job["dow"]
    if job["dom_star"] or job["dow_star"]:
        return dm and dw
    return dm or dw


def candidates(job, start, end):
    if job["reboot"]:
        return
    d = start.replace(hour=0, minute=0)
    while d < end:
        if day_ok(job, d):
            for h in sorted(job["hour"]):
                for mi in sorted(job["minute"]):
                    t = d.replace(hour=h, minute=mi)
                    if start <= t < end:
                        yield t
        d += dt.timedelta(days=1)


FAKE_DATE = """#!/bin/sh
ref="$FAKE_NOW"; d=""; fmt=""
while [ $# -gt 0 ]; do case "$1" in -d) d="$2"; shift 2;; -u) shift;; *) fmt="$1"; shift;; esac; done
if [ -n "$d" ]; then ref="$ref $d"; fi
if [ -n "$fmt" ]; then exec /bin/date -u -d "$ref" "$fmt"; else exec /bin/date -u -d "$ref"; fi
"""
_fake = {}


def fakebin():
    if "dir" not in _fake:
        d = tempfile.mkdtemp(prefix="cronsim-")
        p = os.path.join(d, "date")
        open(p, "w").write(FAKE_DATE)
        os.chmod(p, 0o755)
        _fake["dir"] = d
    return _fake["dir"]


def guard_runs(job, token, t):
    """Does the command of `job` reach `token` (the program path) at time t? A command that starts with `[` or `test` is a guarded command:
    the text before the program is run by sh with a `date` that answers for time t. Any other command always reaches its program."""
    cmd = job["command"].replace("\\%", "%")
    if token not in cmd:
        return False
    if not re.match(r"\s*(\[|test)\s", cmd):
        return True
    prefix = cmd[:cmd.index(token)]
    if re.search(r"[;`]|\|\||\$\((?!date\b)", prefix) or not re.search(r"&&\s*$", prefix):
        raise CronError(f"line {job['line']}: unsupported guard (use `[ ... ] && program`, with only date substitutions inside)")
    env = {"PATH": fakebin() + ":/usr/bin:/bin", "FAKE_NOW": t.strftime("%Y-%m-%d %H:%M:%S"), "TZ": "UTC", "HOME": "/nonexistent"}
    try:
        r = subprocess.run(["sh", "-c", prefix + "echo RAN"], capture_output=True, text=True, timeout=5, env=env, cwd=tempfile.gettempdir())
    except subprocess.TimeoutExpired:
        return False
    return "RAN" in r.stdout


def fires(job, token, start, end, limit=4000):
    cands = list(candidates(job, start, end))
    if len(cands) > limit and re.match(r"\s*(\[|test)\s", job["command"]):
        raise CronError(f"line {job['line']}: the guard would have to be evaluated {len(cands)} times in the window; narrow the time fields")
    return [t for t in cands if guard_runs(job, token, t)]


def guess_token(cmd):
    """The program a job runs: the last absolute path that follows `&&`, `;`, `||` or starts the command (else the first word)."""
    hits = re.findall(r"(?:^|&&|;|\|\|)\s*(/[^\s;&|]+)", cmd)
    return hits[-1] if hits else cmd.split()[0]


def main(argv):
    system = "--system" in argv
    args = [a for a in argv[1:] if a != "--system"]
    if len(args) != 3:
        print(__doc__)
        return 2
    try:
        env, jobs = parse(open(args[0], encoding="utf-8").read(), system)
    except CronError as e:
        print(f"crontab error: {e}")
        return 1
    except OSError as e:
        print(f"cannot read {args[0]}: {e.strerror}")
        return 1
    start, end = dt.datetime.fromisoformat(args[1]), dt.datetime.fromisoformat(args[2])
    for j in jobs:
        if j["reboot"]:
            print(f"line {j['line']}: {j['text']}\n    runs at boot only")
            continue
        tok = guess_token(j["command"])
        ts = fires(j, tok, start, end)
        shown = ", ".join(t.strftime("%Y-%m-%d %H:%M") for t in ts[:8]) + (f", ... ({len(ts)} runs)" if len(ts) > 8 else f" ({len(ts)} runs)")
        print(f"line {j['line']}: {j['text']}\n    {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
'''
