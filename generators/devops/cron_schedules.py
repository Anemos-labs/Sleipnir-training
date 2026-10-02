"""DevOps tasks: crontab files. A documented cron simulator (given to the agent as tools/cronsim.py) decides when every job runs."""
import json
import types
from dataclasses import dataclass, field

from fx import dd, family
from generators.devops import _dokit as K
from generators.devops._cronsim import CRONSIM

_mod = types.ModuleType("cronsim")
exec(compile(CRONSIM, "cronsim.py", "exec"), _mod.__dict__)
cs = _mod

WINDOWS = [("2024-02-26T00:00", "2024-03-04T00:00"), ("2024-04-29T00:00", "2024-06-03T00:00"), ("2024-12-23T00:00", "2025-01-06T00:00")]

CHECK_CRON = r'''
from dolib import *
import datetime as dt
sys.path.insert(0, "tests")
import cronsim

spec = json.load(open("tests/spec.json", encoding="utf-8"))
rep = Report()
system = spec["system"]


def load(path):
    try:
        return cronsim.parse(read(path), system)
    except cronsim.CronError as e:
        die(f"{path}: {e}")


env, jobs = load(spec["path"])
_, ref_jobs = load("tests/reference.cron")
tokens = spec["tokens"]


def token_of(job):
    hits = [t for t in tokens if t in job["command"]]
    return hits[-1] if hits else None


wins = [(dt.datetime.fromisoformat(a), dt.datetime.fromisoformat(b)) for a, b in spec["windows"]]
try:
    for tok in tokens:
        mine = [j for j in jobs if token_of(j) == tok]
        theirs = [j for j in ref_jobs if token_of(j) == tok]
        if not rep.check(mine, f"no entry runs {tok}"):
            continue
        if theirs and theirs[0]["reboot"]:
            rep.check(any(j["reboot"] for j in mine), f"{tok} must run at boot (@reboot)")
            continue
        for wi, (a, b) in enumerate(wins):
            want = set()
            for j in theirs:
                want |= set(cronsim.fires(j, tok, a, b))
            got = set()
            for j in mine:
                got |= set(cronsim.fires(j, tok, a, b))
            if got != want:
                miss, extra = sorted(want - got), sorted(got - want)
                fmt = lambda xs: ", ".join(t.strftime("%a %Y-%m-%d %H:%M") for t in xs[:3]) + (f" (+{len(xs) - 3} more)" if len(xs) > 3 else "")
                rep.check(False, f"{tok}, window {a:%Y-%m-%d}..{b:%Y-%m-%d}: " + (f"missing runs: {fmt(miss)}" if miss else "") + ("; " if miss and extra else "") + (f"unexpected runs: {fmt(extra)}" if extra else ""))
                break
except cronsim.CronError as e:
    rep.check(False, str(e))
for j in jobs:
    rep.check(token_of(j) is not None, f"line {j['line']}: `{j['command'][:50]}` does not run one of the expected programs {tokens}")
    if spec.get("user") and system:
        rep.check(j["user"] == spec["user"], f"line {j['line']}: the job must run as user {spec['user']!r} (got {j['user']!r})")
for k, v in spec.get("env", {}).items():
    rep.check(env.get(k) == v, f"the crontab must set {k}={v!r} (got {env.get(k)!r})")
rep.finish()
'''


@dataclass
class CronSpec:
    slug: str
    d: int
    prompt: str
    path: str
    ref: str
    start: str
    tokens: list
    system: bool = False
    user: str = ""
    env: dict = field(default_factory=dict)
    wrong: list = field(default_factory=list)
    kind: str = "author"
    sanity: list = field(default_factory=list)  # (token, window index, expected number of runs)


def guess(cmd):
    return cs.guess_token(cmd)


def make_task(sp: CronSpec):
    env, jobs = cs.parse(sp.ref, sp.system)
    for tok, wi, n in sp.sanity:
        a, b = (cs.dt.datetime.fromisoformat(x) for x in WINDOWS[wi])
        got = sum(len(cs.fires(j, tok, a, b)) for j in jobs if tok in j["command"])
        if got != n:
            raise RuntimeError(f"{sp.slug}: sanity check for {tok} window {wi}: expected {n} runs, the reference gives {got}")
    start = {sp.path: sp.start, "tools/cronsim.py": CRONSIM,
             "README.md": f"# crontab exercise\n\nEdit `{sp.path}`. `python3 tools/cronsim.py {sp.path} 2024-03-01T00:00 2024-03-08T00:00{' --system' if sp.system else ''}` lists when each job runs in a time window; its docstring (`python3 tools/cronsim.py`) states the cron rules that are checked.\n"}
    spec = {"path": sp.path, "system": sp.system, "tokens": sp.tokens, "windows": WINDOWS, "user": sp.user, "env": sp.env}
    hidden = {"tests/cronsim.py": "# verifier copy of tools/cronsim.py\n" + CRONSIM, "tests/spec.json": json.dumps(spec, indent=1) + "\n", "tests/reference.cron": sp.ref}
    t = K.devops_task(sp.slug, sp.d, sp.prompt, start, {sp.path: sp.ref}, CHECK_CRON, hidden, lang="text", kind="fix" if sp.kind == "fix" else "greenfield", tags=["cron", "schedule", "config"])
    return K.finish(t, wrong=[{sp.path: w} for w in sp.wrong])


SPECS: list[CronSpec] = []


def spec(**kw):
    SPECS.append(CronSpec(**kw))


RULES_NOTE = "`tools/cronsim.py` shows when each job runs and documents the exact cron rules (named months and weekdays only as single values, the day-of-month/day-of-week OR rule, guards, `%`)."

# 1 ------------------------------------------------------------------------------------------------------------------
spec(slug="basic-schedule", d=1, path="crontab", kind="author", tokens=["/opt/jobs/backup.sh", "/opt/jobs/weekly-report.sh", "/opt/jobs/monthly-invoice.sh"], env={"MAILTO": ""},
     prompt=dd('''
        Write the user crontab `crontab` (five time fields then the command; no user column) for these jobs, and set `MAILTO=""` at the top so that no mail is sent:

        - `/opt/jobs/backup.sh` every day at 02:30;
        - `/opt/jobs/weekly-report.sh` every Monday at 08:00;
        - `/opt/jobs/monthly-invoice.sh` on the first day of every month at 00:15.

        ''' + RULES_NOTE),
     start="# user crontab\n", ref='MAILTO=""\n30 2 * * * /opt/jobs/backup.sh\n0 8 * * 1 /opt/jobs/weekly-report.sh\n15 0 1 * * /opt/jobs/monthly-invoice.sh\n',
     sanity=[("/opt/jobs/backup.sh", 0, 7), ("/opt/jobs/weekly-report.sh", 1, 5), ("/opt/jobs/monthly-invoice.sh", 2, 1)],
     wrong=['MAILTO=""\n30 2 * * * /opt/jobs/backup.sh\n0 8 * * 0 /opt/jobs/weekly-report.sh\n15 0 1 * * /opt/jobs/monthly-invoice.sh\n'])

# 2 ------------------------------------------------------------------------------------------------------------------
spec(slug="business-hours", d=2, path="crontab", kind="author", tokens=["/opt/jobs/sync.sh", "/opt/jobs/digest.sh", "/opt/jobs/heartbeat.sh"], env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
     prompt=dd('''
        Write the user crontab `crontab` with `PATH=/usr/local/bin:/usr/bin:/bin` set at the top and these jobs:

        - `/opt/jobs/sync.sh` every 15 minutes from 09:00 to 17:45 inclusive, Monday to Friday (so the last run of a day is 17:45);
        - `/opt/jobs/digest.sh` at 07:30 on Saturdays and Sundays;
        - `/opt/jobs/heartbeat.sh` every hour, at five minutes past.

        ''' + RULES_NOTE),
     start="# user crontab\n", ref="PATH=/usr/local/bin:/usr/bin:/bin\n*/15 9-17 * * 1-5 /opt/jobs/sync.sh\n30 7 * * 0,6 /opt/jobs/digest.sh\n5 * * * * /opt/jobs/heartbeat.sh\n",
     sanity=[("/opt/jobs/sync.sh", 0, 5 * 36), ("/opt/jobs/digest.sh", 0, 2), ("/opt/jobs/heartbeat.sh", 0, 168)],
     wrong=["PATH=/usr/local/bin:/usr/bin:/bin\n*/15 9-17 * * mon-fri /opt/jobs/sync.sh\n30 7 * * 0,6 /opt/jobs/digest.sh\n5 * * * * /opt/jobs/heartbeat.sh\n",
            "PATH=/usr/local/bin:/usr/bin:/bin\n*/15 9-17 * * 1-5 /opt/jobs/sync.sh\n30 7 * * 6 /opt/jobs/digest.sh\n5 * * * * /opt/jobs/heartbeat.sh\n"])

# 3 ------------------------------------------------------------------------------------------------------------------
spec(slug="steps-and-lists", d=3, path="crontab", kind="author", tokens=["/srv/ops/poll.sh", "/srv/ops/rotate.sh", "/srv/ops/shift.sh", "/srv/ops/quarter.sh", "/srv/ops/nightly.sh"],
     prompt=dd('''
        Write the user crontab `crontab` for these jobs (the cron rules are in `tools/cronsim.py`; remember that steps restart with every new unit, e.g. `*/7` in the minute field is :00, :07, ..., :56 of every hour):

        - `/srv/ops/poll.sh` every 7 minutes (at minutes 0, 7, 14, ... 56 of every hour);
        - `/srv/ops/rotate.sh` every second hour on the hour, at 01:00, 03:00, ..., 23:00;
        - `/srv/ops/shift.sh` at 06:45 and at 18:45 on Mondays, Wednesdays and Fridays;
        - `/srv/ops/quarter.sh` at 04:00 on the first day of January, April, July and October;
        - `/srv/ops/nightly.sh` at midnight every day except Sundays (so Monday to Saturday, 00:00).
     '''),
     start="# user crontab\n", ref="*/7 * * * * /srv/ops/poll.sh\n0 1-23/2 * * * /srv/ops/rotate.sh\n45 6,18 * * 1,3,5 /srv/ops/shift.sh\n0 4 1 1,4,7,10 * /srv/ops/quarter.sh\n0 0 * * 1-6 /srv/ops/nightly.sh\n",
     sanity=[("/srv/ops/poll.sh", 0, 7 * 24 * 9), ("/srv/ops/rotate.sh", 0, 7 * 12), ("/srv/ops/shift.sh", 0, 3 * 2 + 0), ("/srv/ops/quarter.sh", 1, 0), ("/srv/ops/nightly.sh", 0, 6)],
     wrong=["*/7 * * * * /srv/ops/poll.sh\n0 */2 * * * /srv/ops/rotate.sh\n45 6,18 * * 1,3,5 /srv/ops/shift.sh\n0 4 1 */3 * /srv/ops/quarter.sh\n0 0 * * 1-6 /srv/ops/nightly.sh\n"])

# 4 ------------------------------------------------------------------------------------------------------------------
spec(slug="dom-dow-trap", d=3, path="crontab", kind="fix", tokens=["/srv/pay/payroll.sh", "/srv/pay/cleanup.sh", "/srv/pay/audit.sh"],
     prompt=dd('''
        `crontab` is the payroll team's crontab. Payroll ran on far too many days last month. The intended schedule:

        - `/srv/pay/payroll.sh` at 06:00 on the 1st and the 15th of each month, but **only when that day is a weekday** (Monday to Friday); nothing on weekends;
        - `/srv/pay/cleanup.sh` at 03:00 on the 1st of every month **and** on every Sunday (both conditions; this one is already right);
        - `/srv/pay/audit.sh` at 22:00 on the 28th of every month (already right).

        Fix the file. ''' + RULES_NOTE),
     start=dd('''
        # payroll team crontab
        0 6 1,15 * 1-5 /srv/pay/payroll.sh
        0 3 1 * 0 /srv/pay/cleanup.sh
        0 22 28 * * /srv/pay/audit.sh
     '''),
     ref=dd('''
        # payroll team crontab
        0 6 1,15 * * [ "$(date +\\%u)" -le 5 ] && /srv/pay/payroll.sh
        0 3 1 * 0 /srv/pay/cleanup.sh
        0 22 28 * * /srv/pay/audit.sh
     '''), sanity=[("/srv/pay/payroll.sh", 0, 1), ("/srv/pay/payroll.sh", 1, 2), ("/srv/pay/payroll.sh", 2, 1), ("/srv/pay/cleanup.sh", 0, 2)],
     wrong=['0 6 1,15 * * /srv/pay/payroll.sh\n0 3 1 * 0 /srv/pay/cleanup.sh\n0 22 28 * * /srv/pay/audit.sh\n'])

# 5 ------------------------------------------------------------------------------------------------------------------
spec(slug="calendar-edge-cases", d=4, path="crontab", kind="author", tokens=["/srv/fin/board-pack.sh", "/srv/fin/month-end.sh", "/srv/fin/leap-day.sh"],
     prompt=dd('''
        Write the user crontab `crontab` for these jobs. Cron cannot say "first Monday" or "last day" directly; use the standard technique of a guard in front of the command
        (`[ ... ] && /path/to/job`, where `date` may be used; remember to write `%` as `\\%` in crontab). `tools/cronsim.py` evaluates guards for every candidate time.

        - `/srv/fin/board-pack.sh` at 09:00 on the first Monday of every month;
        - `/srv/fin/month-end.sh` at 23:50 on the last day of every month (28, 29, 30 or 31, whichever it is);
        - `/srv/fin/leap-day.sh` at 12:00 on 29 February only.
     '''),
     start="# user crontab\n",
     ref=dd('''
        0 9 * * 1 [ "$(date +\\%d)" -le 7 ] && /srv/fin/board-pack.sh
        50 23 28-31 * * [ "$(date -d tomorrow +\\%d)" = 01 ] && /srv/fin/month-end.sh
        0 12 29 2 * /srv/fin/leap-day.sh
     '''), sanity=[("/srv/fin/board-pack.sh", 0, 0), ("/srv/fin/board-pack.sh", 1, 1), ("/srv/fin/board-pack.sh", 2, 0), ("/srv/fin/month-end.sh", 0, 1), ("/srv/fin/month-end.sh", 1, 2), ("/srv/fin/month-end.sh", 2, 1), ("/srv/fin/leap-day.sh", 0, 1), ("/srv/fin/leap-day.sh", 1, 0)],
     wrong=['0 9 1-7 * 1 /srv/fin/board-pack.sh\n50 23 28-31 * * [ "$(date -d tomorrow +\\%d)" = 01 ] && /srv/fin/month-end.sh\n0 12 29 2 * /srv/fin/leap-day.sh\n',
            '0 9 * * 1 [ "$(date +\\%d)" -le 7 ] && /srv/fin/board-pack.sh\n50 23 31 * * /srv/fin/month-end.sh\n0 12 29 2 * /srv/fin/leap-day.sh\n'])

# 6 ------------------------------------------------------------------------------------------------------------------
spec(slug="system-crontab-user", d=2, path="cron.d/shipping", kind="fix", system=True, user="shipper", tokens=["/opt/shipping/export.sh", "/opt/shipping/poll.sh", "/opt/shipping/prune.sh"], env={"SHELL": "/bin/sh"},
     prompt=dd('''
        `cron.d/shipping` is a system crontab (`/etc/cron.d` format): it has the same time fields as a user crontab plus a **user name between the time fields and the command**. The daemon rejects the file. The three jobs must run as the user
        `shipper`, with the same schedules as now. Fix `cron.d/shipping` (use `python3 tools/cronsim.py cron.d/shipping START END --system` to check it). ''' + RULES_NOTE),
     start="SHELL=/bin/sh\n15 3 * * * /opt/shipping/export.sh\n*/10 * * * * /opt/shipping/poll.sh\n@hourly /opt/shipping/prune.sh\n",
     ref="SHELL=/bin/sh\n15 3 * * * shipper /opt/shipping/export.sh\n*/10 * * * * shipper /opt/shipping/poll.sh\n@hourly shipper /opt/shipping/prune.sh\n",
     sanity=[("/opt/shipping/export.sh", 0, 7), ("/opt/shipping/prune.sh", 0, 168)],
     wrong=["SHELL=/bin/sh\n15 3 * * * root /opt/shipping/export.sh\n*/10 * * * * root /opt/shipping/poll.sh\n@hourly root /opt/shipping/prune.sh\n"])

# 7 ------------------------------------------------------------------------------------------------------------------
spec(slug="percent-escape", d=2, path="crontab", kind="fix", tokens=["/opt/jobs/dump.sh", "/opt/jobs/notify.sh"],
     prompt=dd('''
        Two backup jobs in `crontab` never produce the right files: cron treats an unescaped `%` in the command as a line break and feeds the rest to the command's standard input, so the date in the file name is cut off. Fix `crontab`
        (the schedules and commands stay: `dump.sh` at 01:00 and a tar of /srv/data at 01:30 followed by `notify.sh`, daily). ''' + RULES_NOTE),
     start="0 1 * * * /opt/jobs/dump.sh > /var/backups/db-$(date +%F).sql\n30 1 * * * tar czf /var/backups/files-$(date +%Y%m%d).tgz /srv/data && /opt/jobs/notify.sh\n",
     ref="0 1 * * * /opt/jobs/dump.sh > /var/backups/db-$(date +\\%F).sql\n30 1 * * * tar czf /var/backups/files-$(date +\\%Y\\%m\\%d).tgz /srv/data && /opt/jobs/notify.sh\n",
     wrong=["0 1 * * * /opt/jobs/dump.sh > /var/backups/db-$(date +\\%F).sql\n"])

# 8 ------------------------------------------------------------------------------------------------------------------
spec(slug="names-and-ranges", d=2, path="crontab", kind="fix", tokens=["/opt/jobs/open.sh", "/opt/jobs/close.sh", "/opt/jobs/seasonal.sh", "/opt/jobs/audit.sh"],
     prompt=dd('''
        `crontab` is rejected by cron. The intended schedule:

        - `/opt/jobs/open.sh` at 08:00 Monday to Friday;
        - `/opt/jobs/close.sh` at 17:30 Monday to Friday;
        - `/opt/jobs/seasonal.sh` at 03:00 on the 1st day of January and of July;
        - `/opt/jobs/audit.sh` at 23:00 on Sundays (any of the usual spellings of Sunday).

        Fix the file without changing the schedule. ''' + RULES_NOTE),
     start="0 8 * * mon-fri /opt/jobs/open.sh\n30 17 * * mon-fri /opt/jobs/close.sh\n0 3 1 jan,jul * /opt/jobs/seasonal.sh\n0 23 * * sun /opt/jobs/audit.sh\n",
     ref="0 8 * * 1-5 /opt/jobs/open.sh\n30 17 * * 1-5 /opt/jobs/close.sh\n0 3 1 1,7 * /opt/jobs/seasonal.sh\n0 23 * * sun /opt/jobs/audit.sh\n",
     sanity=[("/opt/jobs/open.sh", 0, 5), ("/opt/jobs/seasonal.sh", 2, 1), ("/opt/jobs/audit.sh", 0, 1)],
     wrong=["0 8 * * 1-5 /opt/jobs/open.sh\n30 17 * * 1-5 /opt/jobs/close.sh\n0 3 1 1,7 * /opt/jobs/seasonal.sh\n0 23 * * 6 /opt/jobs/audit.sh\n"])

# 9 ------------------------------------------------------------------------------------------------------------------
spec(slug="macros-and-boot", d=1, path="crontab", kind="author", tokens=["/opt/jobs/warmup.sh", "/opt/jobs/hourly.sh", "/opt/jobs/daily.sh", "/opt/jobs/weekly.sh", "/opt/jobs/five.sh"],
     prompt=dd('''
        Write the user crontab `crontab`:

        - `/opt/jobs/warmup.sh` once when the machine boots;
        - `/opt/jobs/hourly.sh` at the start of every hour;
        - `/opt/jobs/daily.sh` every day at midnight (00:00);
        - `/opt/jobs/weekly.sh` every Sunday at midnight (00:00);
        - `/opt/jobs/five.sh` every five minutes.

        Cron's `@` shortcuts (`@reboot`, `@hourly`, `@daily`, `@weekly`) are fine, and so are the plain five-field forms.
     '''),
     start="# user crontab\n", ref="@reboot /opt/jobs/warmup.sh\n@hourly /opt/jobs/hourly.sh\n@daily /opt/jobs/daily.sh\n@weekly /opt/jobs/weekly.sh\n*/5 * * * * /opt/jobs/five.sh\n",
     sanity=[("/opt/jobs/weekly.sh", 0, 1), ("/opt/jobs/daily.sh", 0, 7)],
     wrong=["@reboot /opt/jobs/warmup.sh\n@hourly /opt/jobs/hourly.sh\n@daily /opt/jobs/daily.sh\n@weekly /opt/jobs/weekly.sh\n"])

# 10 -----------------------------------------------------------------------------------------------------------------
spec(slug="stagger-offsets", d=3, path="crontab", kind="author", tokens=["/srv/db/a.sh", "/srv/db/b.sh", "/srv/db/c.sh", "/srv/db/d.sh", "/srv/db/e.sh", "/srv/db/f.sh"],
     prompt=dd('''
        Six database jobs must not start at the same minute. Write `crontab` with exactly these schedules (cron steps count from the start of the range, so `A-B/S` is how you start at an offset):

        - `/srv/db/a.sh` every 10 minutes at :00, :10, :20, ..., :50;
        - `/srv/db/b.sh` every 10 minutes at :03, :13, :23, ..., :53;
        - `/srv/db/c.sh` every 10 minutes at :06, :16, :26, ..., :56;
        - `/srv/db/d.sh` every 20 minutes at :05, :25 and :45;
        - `/srv/db/e.sh` every 4 hours at :40, at 02:40, 06:40, 10:40, 14:40, 18:40 and 22:40;
        - `/srv/db/f.sh` at 03:00 on days 1, 4, 7, ..., 31 of the month (every third day, restarting each month).
     '''),
     start="# user crontab\n", ref="*/10 * * * * /srv/db/a.sh\n3-59/10 * * * * /srv/db/b.sh\n6-59/10 * * * * /srv/db/c.sh\n5-59/20 * * * * /srv/db/d.sh\n40 2-23/4 * * * /srv/db/e.sh\n0 3 */3 * * /srv/db/f.sh\n",
     sanity=[("/srv/db/b.sh", 0, 7 * 24 * 6), ("/srv/db/d.sh", 0, 7 * 24 * 3), ("/srv/db/e.sh", 0, 7 * 6), ("/srv/db/f.sh", 0, 2)],
     wrong=["*/10 * * * * /srv/db/a.sh\n*/10 * * * * /srv/db/b.sh\n*/10 * * * * /srv/db/c.sh\n*/20 * * * * /srv/db/d.sh\n40 */4 * * * /srv/db/e.sh\n0 3 */3 * * /srv/db/f.sh\n"])

# 11 -----------------------------------------------------------------------------------------------------------------
spec(slug="mixed-crontab-fix", d=4, path="crontab", kind="fix", tokens=["/srv/jobs/ingest.sh", "/srv/jobs/compact.sh", "/srv/jobs/export.sh", "/srv/jobs/report.sh", "/srv/jobs/vacuum.sh"], env={"MAILTO": "ops@example.org"},
     prompt=dd('''
        The data team's `crontab` has several mistakes (cron refuses part of it and some jobs run on the wrong days). Intended behaviour, with `MAILTO` set to `ops@example.org`:

        - `/srv/jobs/ingest.sh` every 5 minutes between 06:00 and 21:55, every day;
        - `/srv/jobs/compact.sh` at 02:10 on Saturdays and Sundays;
        - `/srv/jobs/export.sh > /srv/out/export-<date as YYYY-MM-DD>.csv` at 04:00 every day (the file name carries that day's date);
        - `/srv/jobs/report.sh` at 08:00 on the 10th and the 25th of each month, but only when that day is a weekday;
        - `/srv/jobs/vacuum.sh` at 01:00 on the 1st of every month.

        Fix the file. ''' + RULES_NOTE),
     start=dd('''
        MAILTO=ops@example.org
        */5 6-21 * * * /srv/jobs/ingest.sh
        10 2 * * sat,sun /srv/jobs/compact.sh
        0 4 * * * /srv/jobs/export.sh > /srv/out/export-$(date +%F).csv
        0 8 10,25 * 1-5 /srv/jobs/report.sh
        0 1 1 * * /srv/jobs/vacuum.sh
     '''),
     ref=dd('''
        MAILTO=ops@example.org
        */5 6-21 * * * /srv/jobs/ingest.sh
        10 2 * * 0,6 /srv/jobs/compact.sh
        0 4 * * * /srv/jobs/export.sh > /srv/out/export-$(date +\\%F).csv
        0 8 10,25 * * [ "$(date +\\%u)" -le 5 ] && /srv/jobs/report.sh
        0 1 1 * * /srv/jobs/vacuum.sh
     '''), sanity=[("/srv/jobs/ingest.sh", 0, 7 * 192), ("/srv/jobs/compact.sh", 0, 2), ("/srv/jobs/report.sh", 1, 1)],
     wrong=["MAILTO=ops@example.org\n*/5 6-21 * * * /srv/jobs/ingest.sh\n10 2 * * 0,6 /srv/jobs/compact.sh\n0 4 * * * /srv/jobs/export.sh > /srv/out/export-$(date +\\%F).csv\n0 8 10,25 * 1-5 /srv/jobs/report.sh\n0 1 1 * * /srv/jobs/vacuum.sh\n"])

# 12 -----------------------------------------------------------------------------------------------------------------
spec(slug="quarter-end-guard", d=5, path="cron.d/ledger", kind="author", system=True, user="ledger", tokens=["/opt/ledger/close-books.sh", "/opt/ledger/weekly-recon.sh", "/opt/ledger/payday-check.sh", "/opt/ledger/snapshot.sh"], env={"PATH": "/usr/local/bin:/usr/bin:/bin", "MAILTO": ""},
     prompt=dd('''
        Write the system crontab `cron.d/ledger` (`/etc/cron.d` format: a user column after the five time fields). All jobs run as user `ledger`; set `PATH=/usr/local/bin:/usr/bin:/bin` and `MAILTO=""` at the top.

        - `/opt/ledger/close-books.sh` at 23:55 on the last day of March, June, September and December;
        - `/opt/ledger/weekly-recon.sh` at 05:30 every Tuesday and Thursday, except in the first seven days of any month;
        - `/opt/ledger/payday-check.sh` at 07:00 on the last Friday of every month;
        - `/opt/ledger/snapshot.sh` at 00:05 every day, but only on days whose day of the month is odd.

        Cron cannot express these directly: use guards (`[ ... ] && /path`), `date` is allowed inside, `%` must be written `\\%`. Check with `python3 tools/cronsim.py cron.d/ledger START END --system`. ''' + RULES_NOTE),
     start="# ledger\n",
     ref=dd('''
        PATH=/usr/local/bin:/usr/bin:/bin
        MAILTO=""
        55 23 28-31 3,6,9,12 * ledger [ "$(date -d tomorrow +\\%d)" = 01 ] && /opt/ledger/close-books.sh
        30 5 * * 2,4 ledger [ "$(date +\\%d)" -gt 7 ] && /opt/ledger/weekly-recon.sh
        0 7 * * 5 ledger [ "$(date -d '7 days' +\\%m)" != "$(date +\\%m)" ] && /opt/ledger/payday-check.sh
        5 0 1-31/2 * * ledger /opt/ledger/snapshot.sh
     '''), sanity=[("/opt/ledger/close-books.sh", 1, 0), ("/opt/ledger/close-books.sh", 2, 1), ("/opt/ledger/weekly-recon.sh", 0, 2), ("/opt/ledger/payday-check.sh", 1, 1), ("/opt/ledger/payday-check.sh", 2, 1)],
     wrong=['PATH=/usr/local/bin:/usr/bin:/bin\nMAILTO=""\n55 23 28-31 3,6,9,12 * ledger /opt/ledger/close-books.sh\n30 5 8-31 * 2,4 ledger /opt/ledger/weekly-recon.sh\n0 7 * * 5 ledger [ "$(date -d \'7 days\' +\\%m)" != "$(date +\\%m)" ] && /opt/ledger/payday-check.sh\n5 0 1-31/2 * * ledger /opt/ledger/snapshot.sh\n'])


def _tasks(rng, n):
    return [make_task(s) for s in SPECS[:n]]


@family("devops-cron-schedules", category="devops", lang="text", kind="fix", n=len(SPECS),
        summary="write or repair crontabs judged by a documented cron simulator: steps, ranges, dom/dow OR rule, guards for first/last day, % escaping, system crontab format")
def cron_schedules(rng, n):
    return _tasks(rng, n)
