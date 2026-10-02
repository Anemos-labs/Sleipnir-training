"""Python ETL tasks on text logs and markup (access logs, multi-line records, key=value logs, syslog timestamps, durations, bursts, URLs, templates, markdown tables)."""
import json
from fractions import Fraction

from fx import dd, family
from generators.data import _etlkit as E

PATHS = ["/", "/api/v1/parcels", "/api/v1/rates", "/login", "/static/app.js", "/static/site.css", "/track", "/help/faq", "/account/billing", "/health"]
AGENTS = ["Mozilla/5.0 (X11; Linux x86_64)", "curl/8.4.0", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101", 'bot "crawler" 1.2', "-"]
SERVICES = ["router", "billing", "scanner", "gateway", "notifier"]
NAMES = ["Alma", "Bruno", "Cleo", "Dag", "Esme", "Fynn", "Gita", "Hal", "Ines", "Jory"]
WORDS = ["amber", "birch", "cobalt", "dune", "ember", "fjord", "garnet", "harbor", "indigo", "jade", "kelp", "linen"]


# ---------------------------------------------------------------------------------------------------------------- 1. access log

def make_access(rng, big):
    n = rng.randint(60, 120) if big else 14
    lines = []
    for i in range(n):
        st = rng.choice([200] * 12 + [204, 301, 304, 404, 404, 500, 502])
        size = "-" if st in (204, 304) or rng.random() < 0.05 else str(rng.randint(120, 90000))
        q = rng.choice(["", "", "?page=2", "?q=a+b&x=1"])
        agent = rng.choice(AGENTS).replace('"', '\\"')
        lines.append(f'10.{rng.randint(0, 3)}.{rng.randint(0, 9)}.{rng.randint(1, 250)} - - [14/Jul/2033:{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d} +0000] "{rng.choice(["GET", "GET", "POST", "HEAD"])} {rng.choice(PATHS)}{q} HTTP/1.1" {st} {size} "-" "{agent}"')
    if big:
        lines.insert(5, "this line is not a log entry")
    return {"access.log": "\n".join(lines) + "\n"}


REF_ACCESS = dd('''
    import csv, json, os, re, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    RX = re.compile(r'^(\\S+) \\S+ \\S+ \\[[^\\]]+\\] "(\\S+) (\\S+) [^"]*" (\\d{3}) (\\d+|-) "(?:[^"\\\\]|\\\\.)*" "(?:[^"\\\\]|\\\\.)*"$')
    hits, req, nbytes, classes, bad = {}, 0, 0, {}, 0
    for line in open(os.path.join(indir, "access.log"), encoding="utf-8"):
        line = line.rstrip("\\n")
        m = RX.match(line)
        if not m:
            bad += 1
            continue
        path = m.group(3).split("?", 1)[0]
        hits[path] = hits.get(path, 0) + 1
        req += 1
        nbytes += 0 if m.group(5) == "-" else int(m.group(5))
        c = m.group(4)[0] + "xx"
        classes[c] = classes.get(c, 0) + 1
    top = sorted(hits.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    with open(os.path.join(outdir, "top_paths.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["path", "hits"])
        w.writerows(top)
    json.dump({"requests": req, "bytes": nbytes, "by_class": classes, "malformed": bad}, open(os.path.join(outdir, "summary.json"), "w"), sort_keys=True, indent=1)
''')

DOC_ACCESS = dd('''
    `access.log` is a web server log in the "combined" format:

    `CLIENT - - [DATE] "METHOD TARGET HTTP/1.1" STATUS BYTES "REFERER" "USER-AGENT"`

    where BYTES is a number or `-` (meaning 0), and the quoted fields may contain escaped quotes (`\\"`). A line that does not have this shape is *malformed*.
    The TARGET is a path with an optional `?query`; count requests by the path **without** the query.

    `python3 etl.py IN_DIR OUT_DIR` writes:

    * `top_paths.csv`: header `path,hits`; the five most requested paths, most hits first, ties by path (alphabetical); fewer rows if there are fewer paths;
    * `summary.json`: `{"requests": N, "bytes": B, "by_class": {"2xx": n, ...}, "malformed": M}`: N well-formed lines, total bytes, request count per status class (`"2xx"`, `"3xx"`, `"4xx"`, `"5xx"`; only classes that occur), and the number of malformed lines.
''')


# ---------------------------------------------------------------------------------------------------------------- 2. stack traces

def make_traces(rng, big):
    n = rng.randint(14, 26) if big else 6
    out = []
    t = 0
    for i in range(n):
        t += rng.randint(1, 50)
        ts = f"2033-07-14 10:{t // 60 % 60:02d}:{t % 60:02d}"
        lvl = rng.choice(["INFO", "WARN", "ERROR", "ERROR"])
        out.append(f"{ts} {lvl} {rng.choice(SERVICES)}: {rng.choice(['request failed', 'timeout talking to upstream', 'job aborted', 'ok', 'retrying'])}")
        if lvl == "ERROR" and rng.random() < 0.8:
            ex = rng.choice(["java.io.IOException", "TimeoutError", "net.http.ConnectError", "ValueError", "java.lang.IllegalStateException"])
            out.append(f"{ex}: {rng.choice(['broken pipe', 'deadline exceeded', 'no route', 'bad value 7'])}")
            for _ in range(rng.randint(1, 3)):
                out.append(f"\tat com.example.{rng.choice(WORDS6)}.{rng.choice(WORDS6)}({rng.choice(WORDS6).title()}.java:{rng.randint(10, 400)})")
            if rng.random() < 0.3:
                out.append(f"Caused by: java.net.SocketException: reset")
            if rng.random() < 0.35:
                out.append(f"{rng.choice(['OSError', 'java.io.UncheckedIOException', 'KeyError'])}: while handling the above")
    return {"app.log": "\n".join(out) + "\n"}


WORDS6 = ["pump", "valve", "scan", "route", "ledger", "queue"]

REF_TRACES = dd('''
    import csv, os, re, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    START = re.compile(r"^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2} (INFO|WARN|ERROR) ")
    EX = re.compile(r"^((?:[A-Za-z_][\\w]*\\.)*[A-Za-z_]\\w*(?:Exception|Error))\\b")
    records = []
    for line in open(os.path.join(indir, "app.log"), encoding="utf-8"):
        line = line.rstrip("\\n")
        m = START.match(line)
        if m:
            records.append([m.group(1), []])
        elif records:
            records[-1][1].append(line)
    counts = {}
    for level, cont in records:
        if level != "ERROR":
            continue
        name = "(none)"
        for c in cont:
            m = EX.match(c)
            if m:
                name = m.group(1)
                break
        counts[name] = counts.get(name, 0) + 1
    with open(os.path.join(outdir, "exceptions.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["exception", "records"])
        for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            w.writerow([k, v])
''')

DOC_TRACES = dd('''
    `app.log` mixes one-line records and multi-line records (stack traces). A new record starts at a line that begins with a timestamp `YYYY-MM-DD HH:MM:SS` followed by a level (`INFO`, `WARN` or `ERROR`) and a space;
    every following line that does not start that way belongs to the current record.

    For every `ERROR` record look at its continuation lines in order and take the **first** one that begins with an exception class name: dotted identifiers ending in `Exception` or `Error`
    (`java.io.IOException`, `TimeoutError`) followed by a word boundary (`:` or end of text). Lines such as `\\tat com.example...` or `Caused by: ...` do not begin with a class name.
    An error record without such a line is counted under `(none)`.

    `python3 etl.py IN_DIR OUT_DIR` writes `exceptions.csv`: header `exception,records`; one row per exception name, most records first, ties by name.
''')


# ---------------------------------------------------------------------------------------------------------------- 3. key=value

def make_kv(rng, big):
    n = rng.randint(14, 24) if big else 5
    lines = []
    for _ in range(n):
        parts = [f"level={rng.choice(['info', 'warn', 'error'])}", f"svc={rng.choice(SERVICES)}", f"n={rng.randint(-5, 400)}"]
        if rng.random() < 0.6:
            parts.append('msg="%s"' % rng.choice(["hello world", "disk is 80% full", 'said \\"stop\\" twice', "a=b c=d", ""]))
        if rng.random() < 0.3:
            parts.append(f"ok={rng.choice(['true', 'false'])}")
        if rng.random() < 0.3:
            parts.append(f"ratio={rng.choice(['0.5', '12.25', '007', '1e3'])}")
        if rng.random() < 0.15:
            parts.append(f"n={rng.randint(1, 9)}")  # later duplicate key wins
        lines.append(" ".join(parts))
    return {"kv.log": "\n".join(lines) + "\n"}


REF_KV = dd('''
    import json, os, re, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    PAIR = re.compile(r'([A-Za-z_][\\w.]*)=("(?:[^"\\\\]|\\\\.)*"|\\S*)')


    def conv(v):
        if v.startswith('"'):
            return v[1:-1].replace('\\\\"', '"').replace("\\\\\\\\", "\\\\")
        if re.fullmatch(r"-?\\d+", v):
            return int(v)
        if v in ("true", "false"):
            return v == "true"
        return v


    with open(os.path.join(outdir, "records.jsonl"), "w", encoding="utf-8") as out:
        for line in open(os.path.join(indir, "kv.log"), encoding="utf-8"):
            if not line.strip():
                continue
            rec = {}
            for k, v in PAIR.findall(line):
                rec[k] = conv(v)
            out.write(json.dumps(rec, sort_keys=True) + "\\n")
''')

DOC_KV = dd('''
    `kv.log` has one record per line as space-separated `key=value` pairs. A value is either a double-quoted string (it may contain spaces, `=` and escaped quotes `\\"`; the quotes are removed and `\\"` becomes `"`)
    or a run of non-blank characters. A key that occurs twice in a line: the **last** value wins. Blank lines are skipped.

    Convert values: an unquoted value that is a (possibly negative) decimal integer becomes a JSON number (`007` becomes 7); the unquoted words `true` and `false` become booleans;
    everything else stays a string (this includes `0.5`, `1e3`, and every quoted value, even `"42"`).

    `python3 etl.py IN_DIR OUT_DIR` writes `records.jsonl`: one JSON object per record, keys sorted, in input order.
''')


# ---------------------------------------------------------------------------------------------------------------- 4. syslog years

MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def make_syslog(rng, big):
    n = rng.randint(25, 45) if big else 8
    start = rng.choice([(11, 20), (12, 5), (12, 28)]) if big else (12, 28)
    y, m, d = 2031, start[0], start[1]
    t = 0
    lines = []
    import datetime
    cur = datetime.datetime(2031, m, d, rng.randint(0, 23), 0, 0)
    for _ in range(n):
        cur += datetime.timedelta(hours=rng.randint(1, 30), minutes=rng.randint(0, 59), seconds=rng.randint(0, 59))
        lines.append(f"{MON[cur.month - 1]} {cur.day:2d} {cur:%H:%M:%S} gw{rng.randint(1, 3)} {rng.choice(['sshd', 'cron', 'kernel', 'dhcpd'])}[{rng.randint(100, 9000)}]: {rng.choice(['session opened', 'job done', 'link up', 'lease renewed'])}")
    return {"messages": "\n".join(lines) + "\n", "meta.json": json.dumps({"first_year": 2031})}


REF_SYSLOG = dd('''
    import csv, json, os, re, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    year = json.load(open(os.path.join(indir, "meta.json")))["first_year"]
    MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    RX = re.compile(r"^([A-Z][a-z]{2}) +(\\d{1,2}) (\\d{2}:\\d{2}:\\d{2}) (\\S+) ([^\\s\\[:]+)(?:\\[(\\d+)\\])?: (.*)$")
    prev = 0
    rows = []
    for line in open(os.path.join(indir, "messages"), encoding="utf-8"):
        line = line.rstrip("\\n")
        m = RX.match(line)
        if not m:
            continue
        mon = MON.index(m.group(1)) + 1
        if mon < prev:
            year += 1
        prev = mon
        rows.append([f"{year:04d}-{mon:02d}-{int(m.group(2)):02d}T{m.group(3)}", m.group(4), m.group(5), m.group(6) or "", m.group(7)])
    with open(os.path.join(outdir, "events.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["time", "host", "program", "pid", "message"])
        w.writerows(rows)
''')

DOC_SYSLOG = dd('''
    `messages` is a syslog file: `Mon DD HH:MM:SS host program[pid]: message` (the day is blank-padded to two columns: `Jan  5`; the `[pid]` part is optional) with **no year**. The lines are in chronological order.
    `meta.json` gives `{"first_year": 2031}`, the year of the first line. Whenever the month of a line is *smaller* than the month of the previous line, a new year has begun.
    Lines that do not match this shape are ignored.

    `python3 etl.py IN_DIR OUT_DIR` writes `events.csv`: header `time,host,program,pid,message`, one row per line in input order; `time` is the local time as `YYYY-MM-DDTHH:MM:SS` with the inferred year; `pid` is empty when absent.
''')


# ---------------------------------------------------------------------------------------------------------------- 5. durations

def make_durations(rng, big):
    n = rng.randint(30, 50) if big else 10
    rows = []
    for _ in range(n):
        h, m, s = rng.randint(0, 3), rng.randint(0, 59), rng.randint(0, 59)
        kind = rng.choice(["hms", "secs", "frac", "clock", "mins", "dhm"])
        txt = {"hms": f"{h}h {m}m {s}s", "secs": f"{rng.randint(1, 5000)}s", "frac": f"{rng.choice(['0.5', '1.25', '2.5', '0.75', '3'])}h", "clock": f"{h:02d}:{m:02d}:{s:02d}",
               "mins": f"{rng.randint(1, 300)}m", "dhm": f"{rng.randint(0, 2)}d {h}h {m}m"}[kind]
        if rng.random() < 0.07:
            txt = rng.choice(["5 minutes", "1h5", "abc", "", "1:2", "-3s", "1h 1h"])
        rows.append(f"{rng.choice(SERVICES)},{txt}")
    return {"jobs.csv": "service,duration\n" + "\n".join(rows) + "\n"}


REF_DURATIONS = dd('''
    import csv, os, re, sys
    from fractions import Fraction

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    U = {"d": 86400, "h": 3600, "m": 60, "s": 1}


    def parse(s):
        s = s.strip()
        m = re.fullmatch(r"(\\d{1,2}):(\\d{2}):(\\d{2})", s)
        if m:
            h, mi, se = map(int, m.groups())
            return h * 3600 + mi * 60 + se if mi < 60 and se < 60 else None
        parts = s.split(" ")
        total, seen = Fraction(0), set()
        for p in parts:
            m = re.fullmatch(r"(\\d+(?:\\.\\d+)?)([dhms])", p)
            if not m or m.group(2) in seen:
                return None
            seen.add(m.group(2))
            total += Fraction(m.group(1)) * U[m.group(2)]
        if total.denominator != 1:
            return None
        return int(total)


    per, rejects = {}, []
    for i, r in enumerate(csv.DictReader(open(os.path.join(indir, "jobs.csv"), newline="", encoding="utf-8")), start=2):
        v = parse(r["duration"])
        if v is None:
            rejects.append((i, r["duration"]))
        else:
            per.setdefault(r["service"], []).append(v)
    with open(os.path.join(outdir, "by_service.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["service", "jobs", "total_s", "max_s"])
        for k in sorted(per):
            w.writerow([k, len(per[k]), sum(per[k]), max(per[k])])
    with open(os.path.join(outdir, "rejects.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["line", "raw"])
        w.writerows(rejects)
''')

DOC_DURATIONS = dd('''
    `jobs.csv` (`service,duration`) has durations typed in many styles. Accepted forms:

    * units `d`, `h`, `m`, `s` separated by single blanks, each unit at most once, in any order: `1h 5m 3s`, `90s`, `2d 3h`;
    * a decimal number in front of a unit: `1.25h` (= 4500 s), `0.5h`, `3h`; the total must come out as a whole number of seconds (`0.5h` is fine, `0.3s` is not);
    * a clock form `H:MM:SS` or `HH:MM:SS` (minutes and seconds below 60).

    Anything else (`5 minutes`, `1h5`, empty, `-3s`, the same unit twice, `1:2`) is a reject.

    `python3 etl.py IN_DIR OUT_DIR` writes `by_service.csv` (header `service,jobs,total_s,max_s`: per service the number of good durations, their sum in seconds and the largest; sorted by service) and
    `rejects.csv` (header `line,raw`: the line number in `jobs.csv`, header = line 1, and the original text; input order).
''')


# ---------------------------------------------------------------------------------------------------------------- 6. bursts

def make_bursts(rng, big):
    n = rng.randint(40, 80) if big else 20
    t = 1_790_000_000
    rows = []
    for _ in range(n):
        t += rng.choice([1, 2, 5, 10, 30, 59, 60, 61, 120, 500])
        rows.append((t, rng.choice(SERVICES), rng.choice(["ERROR"] * 3 + ["INFO", "WARN"])))
    rng.shuffle(rows)
    return {"events.csv": "ts,service,level\n" + "\n".join(f"{a},{b},{c}" for a, b, c in rows) + "\n"}


REF_BURSTS = dd('''
    import csv, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    errs = sorted((int(r["ts"]), r["service"]) for r in csv.DictReader(open(os.path.join(indir, "events.csv"), newline="", encoding="utf-8")) if r["level"] == "ERROR")
    clusters = []
    for ts, svc in errs:
        if clusters and ts - clusters[-1][-1][0] <= 60:
            clusters[-1].append((ts, svc))
        else:
            clusters.append([(ts, svc)])
    with open(os.path.join(outdir, "bursts.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["start", "end", "errors", "services"])
        for c in clusters:
            if len(c) >= 4:
                w.writerow([c[0][0], c[-1][0], len(c), "|".join(sorted({s for _, s in c}))])
''')

DOC_BURSTS = dd('''
    `events.csv` (`ts,service,level`, Unix seconds, any order) is a log of events. Only `ERROR` events matter here. Sort them by time and chain them: an error belongs to the same *cluster* as the previous error
    when it is at most **60 seconds** after it (a gap of 61 seconds or more starts a new cluster). A cluster with **4 or more** errors is a *burst*.

    `python3 etl.py IN_DIR OUT_DIR` writes `bursts.csv`: header `start,end,errors,services`; one row per burst in time order: the time (seconds) of its first and last error, the number of errors,
    and the distinct services involved, sorted alphabetically and joined with `|`.
''')


# ---------------------------------------------------------------------------------------------------------------- 7. urls

def make_urls(rng, big):
    n = rng.randint(25, 40) if big else 9
    hosts = ["Example.COM", "example.com", "shop.example.org", "SHOP.example.org:80", "example.com:8443"]
    out = []
    for _ in range(n):
        scheme = rng.choice(["http", "https", "HTTP"])
        host = rng.choice(hosts)
        path = rng.choice(["", "/", "/a/b/../c", "/a/./b", "/x//y", "/p%2fq", "/p%2Fq", "/caf%c3%a9", "/a/b/"])
        q = rng.choice(["", "?b=2&a=1", "?a=1&b=2", "?a=2&a=1", "?", "?z=%2f&y=1", "?a1=1&a=2", "?a=2&a1=1", "?a-b=1&a=1", ""])
        frag = rng.choice(["", "", "#top", "#x"])
        out.append(f"{scheme}://{host}{path}{q}{frag}")
    return {"urls.txt": "\n".join(out) + "\n"}


REF_URLS = dd('''
    import csv, os, re, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)


    def canon(u):
        m = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*)://([^/?#]*)([^?#]*)(?:\\?([^#]*))?(?:#.*)?$", u)
        scheme, host, path, query = m.group(1).lower(), m.group(2).lower(), m.group(3), m.group(4)
        h, _, port = host.partition(":")
        if port and not ((scheme == "http" and port == "80") or (scheme == "https" and port == "443")):
            h = host
        segs = []
        for s in path.split("/")[1:] if path else []:
            if s == ".":
                continue
            if s == "..":
                if segs:
                    segs.pop()
                continue
            segs.append(s)
        p = "/" + "/".join(segs)
        if path.endswith("/") and not p.endswith("/"):
            p += "/"
        p = re.sub(r"%[0-9a-fA-F]{2}", lambda x: x.group(0).upper(), p)
        pairs = sorted(re.sub(r"%[0-9a-fA-F]{2}", lambda x: x.group(0).upper(), kv) for kv in query.split("&")) if query else []
        pairs = sorted(pairs, key=lambda kv: (kv.partition("=")[0], kv.partition("=")[2]))
        return f"{scheme}://{h}{p}" + ("?" + "&".join(pairs) if pairs else "")


    urls = [l.strip() for l in open(os.path.join(indir, "urls.txt"), encoding="utf-8") if l.strip()]
    pairs = [(u, canon(u)) for u in urls]
    with open(os.path.join(outdir, "canonical.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["url", "canonical"])
        w.writerows(pairs)
    counts = {}
    for _, c in pairs:
        counts[c] = counts.get(c, 0) + 1
    with open(os.path.join(outdir, "duplicates.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["canonical", "count"])
        for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            if n > 1:
                w.writerow([c, n])
''')

DOC_URLS = dd('''
    `urls.txt` lists URLs (`scheme://host[:port]/path?query#fragment`). Canonicalise each one:

    1. scheme and host in lower case; the port is dropped when it is the default of the scheme (80 for http, 443 for https), otherwise kept;
    2. the fragment (`#...`) is dropped; an empty query (`?` with nothing after it) is dropped;
    3. the path: `.` segments are removed and `..` segments remove the previous segment (never above the root); empty segments from `//` are kept as they are;
       a trailing slash is kept if the original path ended with a slash; an empty path becomes `/`;
    4. percent-escapes (`%2f`) are written with upper-case hex digits (`%2F`) in the path and in the query; nothing is decoded;
    5. query parameters (the `&`-separated items, without further parsing) are sorted by name (the text before the first `=`), then by value (the text after it), as plain strings.

    `python3 etl.py IN_DIR OUT_DIR` writes `canonical.csv` (header `url,canonical`, one row per non-blank input line, input order) and `duplicates.csv` (header `canonical,count`: canonical URLs that occur at least twice, most frequent first, ties alphabetical).
''')


# ---------------------------------------------------------------------------------------------------------------- 8. csv quirks (fix)

def make_quirks(rng, big):
    n = rng.randint(12, 25) if big else 5
    rows = []
    for i in range(n):
        name = rng.choice(["Alma", 'Bruno "the Bear"', "Cleo, jr.", "Dag", "Esme\nSecond Line", "Fynn"])
        note = rng.choice(["fine", "has, comma", 'says "hi"', "", "multi\nline"])
        rows.append((i + 1, name, rng.randint(1, 99), note))
    text = "id,name,score,note\n"
    for r in rows:
        f = lambda v: '"' + str(v).replace('"', '""') + '"' if any(c in str(v) for c in ',"\n') else str(v)
        text += ",".join(f(v) for v in r) + "\n"
    return {"people.csv": text}


BUGGY_QUIRKS = dd('''
    import json, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    rows = []
    with open(os.path.join(indir, "people.csv"), encoding="utf-8") as f:
        header = f.readline().strip().split(",")
        for line in f:
            cells = line.strip().split(",")
            rows.append(dict(zip(header, cells)))
    json.dump(rows, open(os.path.join(outdir, "people.json"), "w", encoding="utf-8"), indent=1)
''')

REF_QUIRKS = dd('''
    import csv, json, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(indir, "people.csv"), newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["id"] = int(r["id"])
        r["score"] = int(r["score"])
    json.dump(rows, open(os.path.join(outdir, "people.json"), "w", encoding="utf-8"), indent=1)
''')

DOC_QUIRKS = dd('''
    `people.csv` is a standard CSV file (RFC 4180): fields containing commas, double quotes or line breaks are wrapped in double quotes, and a double quote inside a quoted field is written twice (`"says ""hi"""`).
    The first row is the header `id,name,score,note`.

    `python3 etl.py IN_DIR OUT_DIR` writes `people.json`: a list with one object per data row in file order, keys `id` (integer), `name`, `score` (integer), `note` (strings exactly as the CSV encodes them, quotes and line breaks included).
    The script in `etl.py` almost works; it splits lines on commas. Fix it.
''')


# ---------------------------------------------------------------------------------------------------------------- 9. templates

def make_templates(rng, big):
    n = rng.randint(4, 6) if big else 2
    tpls = []
    for i in range(n):
        tpls.append(rng.choice([
            "Dear {{ user.name }}, parcel {{ id }} is {{ status | default(\"on its way\") }}.",
            "Items: {{ items | join(\", \") }} ({{ count }} total)",
            "{{ greeting | default(\"Hello\") }}, {{ user.name | default(\"friend\") }}! Your code is {{ user.code }}.",
            "Ship to {{ address.city }}, {{ address.zip | default(\"-----\") }}{{ note }}",
            "{{user.name}} has {{ items | join(\"/\") }} and {{ missing }}",
        ]))
    ctx = {"user": {"name": rng.choice(NAMES), "code": rng.randint(100, 999)}, "id": rng.randint(1000, 9999), "items": rng.sample(WORDS, 3), "count": 3, "address": {"city": "Oslo"}}
    if rng.random() < 0.5:
        ctx["status"] = "delivered"
    if rng.random() < 0.5:
        ctx["greeting"] = "Hi"
    return {"templates.json": json.dumps(tpls), "context.json": json.dumps(ctx)}


REF_TEMPLATES = dd('''
    import json, os, re, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    tpls = json.load(open(os.path.join(indir, "templates.json"), encoding="utf-8"))
    ctx = json.load(open(os.path.join(indir, "context.json"), encoding="utf-8"))
    RX = re.compile(r"\\{\\{\\s*([A-Za-z_][\\w.]*)\\s*(?:\\|\\s*(default|join)\\(\\"([^\\"]*)\\"\\)\\s*)?\\}\\}")
    missing = []


    def lookup(path):
        cur = ctx
        for p in path.split("."):
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return None
        return cur


    def render(t, i):
        def sub(m):
            v = lookup(m.group(1))
            f, arg = m.group(2), m.group(3)
            if f == "default":
                return str(arg if v is None else v)
            if v is None:
                missing.append(f"{i}:{m.group(1)}")
                return ""
            if f == "join":
                return arg.join(str(x) for x in v)
            return str(v)
        return RX.sub(sub, t)


    out = [render(t, i) for i, t in enumerate(tpls, 1)]
    with open(os.path.join(outdir, "rendered.txt"), "w", encoding="utf-8") as f:
        f.write("".join(o + "\\n" for o in out))
    with open(os.path.join(outdir, "missing.txt"), "w", encoding="utf-8") as f:
        f.write("".join(m + "\\n" for m in missing))
''')

DOC_TEMPLATES = dd('''
    `templates.json` is a list of template strings and `context.json` an object with values. Render each template (one output line each, in order) by replacing every placeholder `{{ expr }}` (blanks inside the braces are optional):

    * `{{ a.b.c }}`: the value reached by following the dotted path in the context; numbers are written as JSON writes them (`7`);
    * `{{ x | default("text") }}`: the value of `x` if it exists, otherwise `text` (the text has no quotes inside);
    * `{{ x | join("sep") }}`: the elements of the list `x` joined with `sep`.
    A path that does not exist (or goes through a non-object) is *missing*. A missing value renders as the empty string and is recorded as `N:path` (N = the template's position, first = 1) in `missing.txt`,
    one line per occurrence in order of appearance, unless a `default` supplies a replacement.

    `python3 etl.py IN_DIR OUT_DIR` writes `rendered.txt` (one rendered line per template) and `missing.txt` (empty when nothing was missing).
''')


# ---------------------------------------------------------------------------------------------------------------- 10. markdown tables

def make_md(rng, big):
    n = rng.randint(2, 4) if big else 2
    out = ["# Release notes", "", "Some prose with a | pipe that is not a table.", ""]
    for t in range(n):
        cols = rng.sample(["Name", "Qty", "Price", "Notes", "Region", "Code"], rng.randint(2, 4))
        aligns = [rng.choice([":---", "---", "---:", ":---:"]) for _ in cols]
        out.append("| " + " | ".join(cols) + " |")
        out.append("|" + "|".join(f" {a} " for a in aligns) + "|")
        for _ in range(rng.randint(1, 4)):
            cells = [rng.choice(["alpha", "7", "12.5", "x \\| y", "`code`", "", "plain text"]) for _ in cols]
            if rng.random() < 0.3:
                cells = cells[:-1]  # short row
            out.append("| " + " | ".join(cells) + " |")
        out += ["", "Text between tables.", ""]
    return {"notes.md": "\n".join(out) + "\n"}


REF_MD = dd('''
    import json, os, re, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    lines = open(os.path.join(indir, "notes.md"), encoding="utf-8").read().split("\\n")
    SEP = re.compile(r"^\\s*\\|?\\s*:?-{3,}:?\\s*(\\|\\s*:?-{3,}:?\\s*)*\\|?\\s*$")


    def cells(line):
        s = line.strip()
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|") and not s.endswith("\\\\|"):
            s = s[:-1]
        parts = re.split(r"(?<!\\\\)\\|", s)
        return [p.strip().replace("\\\\|", "|") for p in parts]


    tables, i = [], 0
    while i < len(lines) - 1:
        if "|" in lines[i] and SEP.match(lines[i + 1]) and len(cells(lines[i])) == len(cells(lines[i + 1])):
            head = cells(lines[i])
            al = []
            for c in cells(lines[i + 1]):
                al.append("center" if c.startswith(":") and c.endswith(":") else "right" if c.endswith(":") else "left" if c.startswith(":") else "none")
            rows, j = [], i + 2
            while j < len(lines) and lines[j].strip() and "|" in lines[j]:
                r = cells(lines[j])[: len(head)]
                rows.append(r + [""] * (len(head) - len(r)))
                j += 1
            tables.append({"header": head, "align": al, "rows": rows})
            i = j
        else:
            i += 1
    json.dump(tables, open(os.path.join(outdir, "tables.json"), "w", encoding="utf-8"), indent=1)
''')

DOC_MD = dd('''
    `notes.md` is a markdown document. Extract its GitHub-style pipe tables. A table is a header row (a line with pipes), immediately followed by a separator row (cells made of at least three dashes, optionally with a colon at
    the left and/or right end: `:---`, `---:`, `:---:`, `---`) with the same number of cells as the header, followed by zero or more body rows (consecutive non-blank lines that contain a pipe). Lines with a pipe elsewhere are just prose.

    Cells: strip the leading and trailing pipe and split on every `|` that is **not** preceded by a backslash; trim blanks around each cell; an escaped pipe `\\|` becomes `|` inside the cell text.
    A body row with fewer cells than the header is padded with empty cells; extra cells are dropped.
    Alignment of a column from the separator cell: `:---:` -> `center`, `---:` -> `right`, `:---` -> `left`, `---` -> `none`.

    `python3 etl.py IN_DIR OUT_DIR` writes `tables.json`: a list (in document order) of `{"header": [...], "align": [...], "rows": [[...], ...]}`.
''')


def spec(slug, d, prompt, doc, make, ref, outputs, **kw):
    return E.EtlSpec(slug=slug, d=d, prompt=prompt, doc=doc, make=make, ref=ref, outputs=outputs, **kw)


SPECS = [
    spec("access-log", 2, "Write `etl.py` that parses the web server log `access.log` and summarises it (top paths, byte total, status classes, malformed lines). Read README.md for the format.", DOC_ACCESS, make_access, REF_ACCESS, {"top_paths.csv": "csv", "summary.json": "json"},
         wrong=(REF_ACCESS.replace('path = m.group(3).split("?", 1)[0]', 'path = m.group(3)'),)),
    spec("stack-traces", 3, "Write `etl.py` that groups the multi-line records of `app.log` and counts the error records per exception class. Read README.md.", DOC_TRACES, make_traces, REF_TRACES, {"exceptions.csv": "csv"},
         wrong=(REF_TRACES.replace("break", "pass"),)),
    spec("key-value-logs", 2, "Write `etl.py` that converts the `key=value` log lines in `kv.log` into JSON records with typed values. Read README.md.", DOC_KV, make_kv, REF_KV, {"records.jsonl": "text"},
         wrong=(REF_KV.replace('if re.fullmatch(r"-?\\d+", v):', 'if False:'),)),
    spec("syslog-years", 3, "Write `etl.py` that gives the year-less syslog lines in `messages` full timestamps, inferring the year across New Year. Read README.md.", DOC_SYSLOG, make_syslog, REF_SYSLOG, {"events.csv": "csv"},
         wrong=(REF_SYSLOG.replace("if mon < prev:", "if mon < prev and False:"),)),
    spec("duration-strings", 2, "Write `etl.py` that converts the free-form durations in `jobs.csv` to seconds and totals them per service. Read README.md.", DOC_DURATIONS, make_durations, REF_DURATIONS, {"by_service.csv": "csv", "rejects.csv": "csv"},
         wrong=(REF_DURATIONS.replace("or m.group(2) in seen", ""),)),
    spec("error-bursts", 4, "Write `etl.py` that finds bursts of ERROR events in `events.csv` (clusters chained by 60-second gaps). Read README.md.", DOC_BURSTS, make_bursts, REF_BURSTS, {"bursts.csv": "csv"},
         wrong=(REF_BURSTS.replace("<= 60", "< 60"),)),
    spec("canonical-urls", 3, "Write `etl.py` that canonicalises the URLs in `urls.txt` and reports which ones collapse into the same address. Read README.md.", DOC_URLS, make_urls, REF_URLS, {"canonical.csv": "csv", "duplicates.csv": "csv"},
         wrong=(REF_URLS.replace("pairs = sorted(pairs, key=lambda kv: (kv.partition(\"=\")[0], kv.partition(\"=\")[2]))", "pass"),)),
    spec("csv-quirks-fix", 3, "`etl.py` converts `people.csv` to JSON but breaks on quoted fields (commas, quotes, line breaks inside values). Fix it; README.md describes the file and the output.", DOC_QUIRKS, make_quirks, REF_QUIRKS, {"people.json": "json"}, buggy=BUGGY_QUIRKS,
         wrong=(BUGGY_QUIRKS,)),
    spec("template-render", 3, "Write `etl.py` that renders the tiny templates in `templates.json` with the values from `context.json` and reports missing values. Read README.md.", DOC_TEMPLATES, make_templates, REF_TEMPLATES, {"rendered.txt": "text", "missing.txt": "text"},
         wrong=(REF_TEMPLATES.replace('return str(arg if v is None else v)', 'return str(arg)'),)),
    spec("markdown-tables", 3, "Write `etl.py` that extracts the pipe tables of `notes.md` into JSON. Read README.md.", DOC_MD, make_md, REF_MD, {"tables.json": "json"},
         wrong=(REF_MD.replace('.replace("\\\\|", "|")', ''),)),
]


@family("data-etl-logbook", category="data", lang="python", kind="feature", n=len(SPECS),
        summary="python ETL on text logs and markup: access logs, multi-line records, key=value parsing, syslog years, duration strings, error bursts, URL canonicalisation, templates, markdown tables")
def etl_logbook(rng, n):
    return E.etl_tasks("etl-logbook", SPECS, rng, n, "Log and text wrangling")
