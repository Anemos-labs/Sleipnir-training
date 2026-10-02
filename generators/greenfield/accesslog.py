"""Access-log digests: a CLI that summarises web-server log lines written in an invented per-instance layout."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

FIELDS = ["ts", "ip", "method", "path", "status", "bytes", "lat"]
SEPS = [" ", "|", "\t", ";"]
SEP_NAMES = {" ": "a single space", "|": "a vertical bar `|`", "\t": "a single tab", ";": "a semicolon `;`"}
PATHS = ["/", "/index", "/api/items", "/api/items/42", "/static/app.js", "/static/logo.png", "/login", "/search", "/admin/panel", "/feed.xml", "/api/orders", "/health"]
SITES = ["the Quillfeather ferry portal", "the Saltmarsh library catalogue", "Brannock Reach town hall", "the tideclock web service", "the Eveningstar radio archive",
         "the Hollin allotment society", "Lower Karrow harbour cams", "the mill-pond weather station"]
LANG_PLAN = ["python", "bash", "ruby", "bash", "python", "ruby", "bash", "python", "ruby", "bash"]


def params(rng, level, i):
    order = FIELDS[:]
    rng.shuffle(order)
    return {
        "level": level, "order": order, "sep": SEPS[(i + rng.randrange(4)) % 4], "lat": rng.choice(["ms", "s"]) if level >= 2 else "ms",
        "has_top": level >= 2, "has_hours": level >= 3, "site": rng.choice(SITES), "by": level >= 3,
    }


PY = r'''
import sys

ORDER = @ORDER_PY@
SEP = "@SEP@"
LAT = "@LAT@"
HAS_TOP = @TOP@
HAS_HOURS = @HOURS@
HAS_BY = @BY@
DG = "0123456789"
METHODS = ("GET", "POST", "PUT", "DELETE", "HEAD")


def digits(s, lo, hi):
    return lo <= len(s) <= hi and all(c in DG for c in s)


def valid_ts(t):
    if len(t) != 20:
        return None
    pat = "dddd-dd-ddTdd:dd:ddZ"
    for c, p in zip(t, pat):
        if p == "d":
            if c not in DG:
                return None
        elif c != p:
            return None
    mo, d, h, mi, s = int(t[5:7]), int(t[8:10]), int(t[11:13]), int(t[14:16]), int(t[17:19])
    if not (1 <= mo <= 12 and 1 <= d <= 31 and h <= 23 and mi <= 59 and s <= 59):
        return None
    return h


def valid_ip(s):
    parts = s.split(".")
    return len(parts) == 4 and all(digits(p, 1, 3) and int(p) <= 255 for p in parts)


def lat_ms(s):
    if LAT == "ms":
        return int(s) if digits(s, 1, 7) else None
    if "." in s:
        a, b = s.split(".", 1)
        if not (digits(a, 1, 4) and digits(b, 1, 9)):
            return None
    else:
        a, b = s, ""
        if not digits(a, 1, 4):
            return None
    b = (b + "0000")[:4]
    return int(a) * 1000 + int(b[:3]) + (1 if b[3] >= "5" else 0)


def parse(line):
    parts = line.split(SEP)
    if len(parts) != 7:
        return None
    f = dict(zip(ORDER, parts))
    h = valid_ts(f["ts"])
    if h is None or not valid_ip(f["ip"]) or f["method"] not in METHODS:
        return None
    path = f["path"]
    if path[:1] != "/" or " " in path or "\t" in path:
        return None
    st = f["status"]
    if not (digits(st, 3, 3) and 100 <= int(st) <= 599):
        return None
    b = f["bytes"]
    if b == "-":
        nb = 0
    elif digits(b, 1, 10):
        nb = int(b)
    else:
        return None
    ms = lat_ms(f["lat"])
    if ms is None:
        return None
    return (h, f["ip"], path.split("?")[0], int(st), nb, ms)


def usage():
    sys.stderr.write("usage: logsum summary | top N [--by hits|bytes] | hours\n")
    sys.exit(2)


def main(argv):
    if not argv:
        usage()
    cmd = argv[0]
    n = 0
    by = "hits"
    if cmd == "summary" and len(argv) == 1:
        pass
    elif HAS_TOP and cmd == "top" and len(argv) in (2, 4):
        if not (digits(argv[1], 1, 2) and int(argv[1]) >= 1):
            usage()
        n = int(argv[1])
        if len(argv) == 4:
            if not HAS_BY or argv[2] != "--by" or argv[3] not in ("hits", "bytes"):
                usage()
            by = argv[3]
    elif HAS_HOURS and cmd == "hours" and len(argv) == 1:
        pass
    else:
        usage()
    recs = []
    skipped = 0
    for line in sys.stdin.read().split("\n"):
        if line == "" or line[0] == "#":
            continue
        r = parse(line)
        if r is None:
            skipped += 1
        else:
            recs.append(r)
    if cmd == "summary":
        total = len(recs)
        errors = sum(1 for r in recs if r[3] >= 500)
        lats = sorted(r[5] for r in recs)
        print("requests %d" % total)
        print("skipped %d" % skipped)
        print("bytes %d" % sum(r[4] for r in recs))
        print("clients %d" % len({r[1] for r in recs}))
        if total:
            tenths = (errors * 2000 + total) // (2 * total)
            print("errors %d %d.%d%%" % (errors, tenths // 10, tenths % 10))
            for q in (50, 95):
                rank = max(1, (q * total + 99) // 100)
                print("p%d %d" % (q, lats[rank - 1]))
        else:
            print("errors 0 0.0%")
            print("p50 -")
            print("p95 -")
    elif cmd == "top":
        agg = {}
        for r in recs:
            h, b = agg.get(r[2], (0, 0))
            agg[r[2]] = (h + 1, b + r[4])
        key = 0 if by == "hits" else 1
        ranked = sorted(agg.items(), key=lambda kv: (-kv[1][key], kv[0]))
        for i, (p, v) in enumerate(ranked[:n], 1):
            print("%d %s %d" % (i, p, v[key]))
    else:
        counts = {}
        for r in recs:
            counts[r[0]] = counts.get(r[0], 0) + 1
        if counts:
            mx = max(counts.values())
            for h in sorted(counts):
                print("%02d %d %s" % (h, counts[h], "#" * ((counts[h] * 20 + mx - 1) // mx)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

RB = r'''
ORDER = @ORDER_RB@
SEP = "@SEP_RB@"
LAT = '@LAT@'
HAS_TOP = @TOP@
HAS_HOURS = @HOURS@
HAS_BY = @BY@
DG = '0123456789'
METHODS = %w[GET POST PUT DELETE HEAD]

def digits?(s, lo, hi)
  s.length >= lo && s.length <= hi && s.each_char.all? { |c| DG.include?(c) }
end

def valid_ts(t)
  return nil if t.length != 20
  pat = 'dddd-dd-ddTdd:dd:ddZ'
  t.each_char.with_index do |c, i|
    if pat[i] == 'd'
      return nil unless DG.include?(c)
    elsif c != pat[i]
      return nil
    end
  end
  mo, d, h, mi, s = t[5, 2].to_i, t[8, 2].to_i, t[11, 2].to_i, t[14, 2].to_i, t[17, 2].to_i
  return nil unless mo >= 1 && mo <= 12 && d >= 1 && d <= 31 && h <= 23 && mi <= 59 && s <= 59
  h
end

def valid_ip?(s)
  parts = s.split('.', -1)
  parts.length == 4 && parts.all? { |p| digits?(p, 1, 3) && p.to_i <= 255 }
end

def lat_ms(s)
  return (digits?(s, 1, 7) ? s.to_i : nil) if LAT == 'ms'
  if s.include?('.')
    a, b = s.split('.', 2)
    return nil unless digits?(a, 1, 4) && digits?(b, 1, 9)
  else
    a = s
    b = ''
    return nil unless digits?(a, 1, 4)
  end
  b = (b + '0000')[0, 4]
  a.to_i * 1000 + b[0, 3].to_i + (b[3] >= '5' ? 1 : 0)
end

def parse(line)
  parts = line.split(SEP, -1)
  return nil if parts.length != 7
  f = ORDER.zip(parts).to_h
  h = valid_ts(f['ts'])
  return nil if h.nil? || !valid_ip?(f['ip']) || !METHODS.include?(f['method'])
  path = f['path']
  return nil if path[0] != '/' || path.include?(' ') || path.include?("\t")
  st = f['status']
  return nil unless digits?(st, 3, 3) && st.to_i >= 100 && st.to_i <= 599
  b = f['bytes']
  if b == '-'
    nb = 0
  elsif digits?(b, 1, 10)
    nb = b.to_i
  else
    return nil
  end
  ms = lat_ms(f['lat'])
  return nil if ms.nil?
  [h, f['ip'], path.split('?', -1)[0], st.to_i, nb, ms]
end

def usage
  $stderr.puts 'usage: logsum summary | top N [--by hits|bytes] | hours'
  exit 2
end

argv = ARGV
usage if argv.empty?
cmd = argv[0]
n = 0
by = 'hits'
if cmd == 'summary' && argv.length == 1
elsif HAS_TOP && cmd == 'top' && [2, 4].include?(argv.length)
  usage unless digits?(argv[1], 1, 2) && argv[1].to_i >= 1
  n = argv[1].to_i
  if argv.length == 4
    usage unless HAS_BY && argv[2] == '--by' && %w[hits bytes].include?(argv[3])
    by = argv[3]
  end
elsif HAS_HOURS && cmd == 'hours' && argv.length == 1
else
  usage
end
recs = []
skipped = 0
$stdin.read.split("\n", -1).each do |line|
  next if line == '' || line[0] == '#'
  r = parse(line)
  if r.nil?
    skipped += 1
  else
    recs << r
  end
end
if cmd == 'summary'
  total = recs.length
  errors = recs.count { |r| r[3] >= 500 }
  lats = recs.map { |r| r[5] }.sort
  puts "requests #{total}"
  puts "skipped #{skipped}"
  puts "bytes #{recs.sum { |r| r[4] }}"
  puts "clients #{recs.map { |r| r[1] }.uniq.length}"
  if total > 0
    tenths = (errors * 2000 + total) / (2 * total)
    puts "errors #{errors} #{tenths / 10}.#{tenths % 10}%"
    [50, 95].each do |q|
      rank = [1, (q * total + 99) / 100].max
      puts "p#{q} #{lats[rank - 1]}"
    end
  else
    puts 'errors 0 0.0%'
    puts 'p50 -'
    puts 'p95 -'
  end
elsif cmd == 'top'
  agg = {}
  recs.each do |r|
    h, b = agg[r[2]] || [0, 0]
    agg[r[2]] = [h + 1, b + r[4]]
  end
  key = by == 'hits' ? 0 : 1
  ranked = agg.to_a.sort_by { |p, v| [-v[key], p] }
  ranked.first(n).each_with_index { |(p, v), i| puts "#{i + 1} #{p} #{v[key]}" }
else
  counts = Hash.new(0)
  recs.each { |r| counts[r[0]] += 1 }
  unless counts.empty?
    mx = counts.values.max
    counts.keys.sort.each { |h| puts format('%02d %d %s', h, counts[h], '#' * ((counts[h] * 20 + mx - 1) / mx)) }
  end
end
exit 0
'''

SH = r'''
#!/usr/bin/env bash
# logsum: digest access-log lines
usage() {
  echo 'usage: logsum summary | top N [--by hits|bytes] | hours' >&2
  exit 2
}

HAS_TOP=@TOP_SH@
HAS_HOURS=@HOURS_SH@
HAS_BY=@BY_SH@
cmd=${1:-}
n=0
by=hits
if [ "$cmd" = summary ] && [ $# -eq 1 ]; then
  :
elif [ "$HAS_TOP" = 1 ] && [ "$cmd" = top ] && { [ $# -eq 2 ] || [ $# -eq 4 ]; }; then
  [[ $2 =~ ^[0-9]{1,2}$ ]] || usage
  n=$((10#$2))
  [ "$n" -ge 1 ] || usage
  if [ $# -eq 4 ]; then
    [ "$HAS_BY" = 1 ] && [ "$3" = "--by" ] || usage
    case "$4" in hits | bytes) by=$4 ;; *) usage ;; esac
  fi
elif [ "$HAS_HOURS" = 1 ] && [ "$cmd" = hours ] && [ $# -eq 1 ]; then
  :
else
  usage
fi

exec awk -v CMD="$cmd" -v N="$n" -v BY="$by" -v SEP='@SEP_SH@' -v LAT=@LAT@ \
  -v F_TS=@F_TS@ -v F_IP=@F_IP@ -v F_METHOD=@F_METHOD@ -v F_PATH=@F_PATH@ -v F_STATUS=@F_STATUS@ -v F_BYTES=@F_BYTES@ -v F_LAT=@F_LAT@ '
function isdig(s,   i, n) {
  n = length(s)
  if (n == 0) return 0
  for (i = 1; i <= n; i++) if (index("0123456789", substr(s, i, 1)) == 0) return 0
  return 1
}
function dig(s, lo, hi) { return (length(s) >= lo && length(s) <= hi && isdig(s)) }
function validts(t,   i, c, p, pat, mo, d, h, mi, s) {
  if (length(t) != 20) return -1
  pat = "dddd-dd-ddTdd:dd:ddZ"
  for (i = 1; i <= 20; i++) {
    c = substr(t, i, 1); p = substr(pat, i, 1)
    if (p == "d") { if (index("0123456789", c) == 0) return -1 }
    else if (c != p) return -1
  }
  mo = substr(t, 6, 2) + 0; d = substr(t, 9, 2) + 0; h = substr(t, 12, 2) + 0; mi = substr(t, 15, 2) + 0; s = substr(t, 18, 2) + 0
  if (mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59 || s > 59) return -1
  return h
}
function validip(s,   parts, n, i) {
  n = split(s, parts, ".")
  if (n != 4) return 0
  for (i = 1; i <= 4; i++) if (!dig(parts[i], 1, 3) || parts[i] + 0 > 255) return 0
  return 1
}
function latms(s,   a, b, n, p) {
  if (LAT == "ms") return dig(s, 1, 7) ? s + 0 : -1
  n = index(s, ".")
  if (n > 0) {
    a = substr(s, 1, n - 1); b = substr(s, n + 1)
    if (!dig(a, 1, 4) || !dig(b, 1, 9)) return -1
  } else {
    a = s; b = ""
    if (!dig(a, 1, 4)) return -1
  }
  b = substr(b "0000", 1, 4)
  return a * 1000 + substr(b, 1, 3) + (substr(b, 4, 1) >= "5" ? 1 : 0)
}
{
  if ($0 == "" || substr($0, 1, 1) == "#") next
  nf = split($0, f, "[" SEP "]")
  ok = (nf == 7)
  if (ok) {
    h = validts(f[F_TS])
    if (h < 0) ok = 0
  }
  if (ok && !validip(f[F_IP])) ok = 0
  if (ok) {
    m = f[F_METHOD]
    if (m != "GET" && m != "POST" && m != "PUT" && m != "DELETE" && m != "HEAD") ok = 0
  }
  if (ok) {
    pth = f[F_PATH]
    if (substr(pth, 1, 1) != "/" || index(pth, " ") > 0 || index(pth, "\t") > 0) ok = 0
  }
  if (ok) {
    st = f[F_STATUS]
    if (!dig(st, 3, 3) || st + 0 < 100 || st + 0 > 599) ok = 0
  }
  if (ok) {
    b = f[F_BYTES]
    if (b == "-") nb = 0
    else if (dig(b, 1, 10)) nb = b + 0
    else ok = 0
  }
  if (ok) {
    ms = latms(f[F_LAT])
    if (ms < 0) ok = 0
  }
  if (!ok) { skipped++; next }
  total++
  q = index(pth, "?")
  if (q > 0) pth = substr(pth, 1, q - 1)
  if (st + 0 >= 500) errors++
  sumbytes += nb
  LATS[total] = ms
  ips[f[F_IP]] = 1
  hits[pth]++
  pbytes[pth] += nb
  hcount[h]++
}
END {
  if (CMD == "summary") {
    clients = 0
    for (k in ips) clients++
    printf "requests %d\n", total
    printf "skipped %d\n", skipped
    printf "bytes %.0f\n", sumbytes
    printf "clients %d\n", clients
    if (total > 0) {
      tenths = int((errors * 2000 + total) / (2 * total))
      printf "errors %d %d.%d%%\n", errors, int(tenths / 10), tenths % 10
      for (i = 2; i <= total; i++) {
        v = LATS[i]; j = i - 1
        while (j >= 1 && LATS[j] > v) { LATS[j + 1] = LATS[j]; j-- }
        LATS[j + 1] = v
      }
      r = int((50 * total + 99) / 100); if (r < 1) r = 1
      printf "p50 %d\n", LATS[r]
      r = int((95 * total + 99) / 100); if (r < 1) r = 1
      printf "p95 %d\n", LATS[r]
    } else {
      print "errors 0 0.0%"
      print "p50 -"
      print "p95 -"
    }
  } else if (CMD == "top") {
    for (k in hits) { val[k] = (BY == "hits") ? hits[k] : pbytes[k]; used[k] = 0 }
    for (rank = 1; rank <= N; rank++) {
      best = ""; found = 0
      for (k in val) {
        if (used[k]) continue
        if (!found || val[k] > val[best] || (val[k] == val[best] && k < best)) { best = k; found = 1 }
      }
      if (!found) break
      used[best] = 1
      printf "%d %s %d\n", rank, best, val[best]
    }
  } else {
    mx = 0
    for (h in hcount) if (hcount[h] > mx) mx = hcount[h]
    for (h = 0; h <= 23; h++) {
      if (!(h in hcount)) continue
      bar = ""
      for (k = 1; k <= int((hcount[h] * 20 + mx - 1) / mx); k++) bar = bar "#"
      printf "%02d %d %s\n", h, hcount[h], bar
    }
  }
}'
'''

SOURCES = {"python": PY, "ruby": RB, "bash": SH}


def _b(lang, v):
    if lang == "python":
        return "True" if v else "False"
    if lang == "bash":
        return "1" if v else "0"
    return "true" if v else "false"


def sol(lang, p):
    o = p["order"]
    sep = p["sep"]
    sep_py = {"\t": "\\t"}.get(sep, sep)
    return K.subst(
        SOURCES[lang], ORDER_PY="[" + ", ".join(f'"{x}"' for x in o) + "]", ORDER_RB="[" + ", ".join(f"'{x}'" for x in o) + "]",
        SEP=sep_py, SEP_RB={"\t": "\\t"}.get(sep, sep), SEP_SH=sep, LAT=p["lat"], TOP=_b(lang, p["has_top"]), HOURS=_b(lang, p["has_hours"]), BY=_b(lang, p["by"]),
        TOP_SH=_b("bash", p["has_top"]), HOURS_SH=_b("bash", p["has_hours"]), BY_SH=_b("bash", p["by"]),
        **{f"F_{f.upper()}": o.index(f) + 1 for f in FIELDS},
    ).lstrip("\n").replace("\r", "")


# ---------------------------------------------------------------------------------------------------------------

def readme(p, spec, lang, examples):
    sep = p["sep"]
    o = p["order"]
    L = [f"# logsum: access-log digests for {p['site']}", ""]
    L.append(f"The operators of {p['site']} keep their web-server log in a home-made layout. `logsum` reads log lines on **standard input** and prints a digest. "
             "Results go to standard output; usage mistakes print a message to standard error (its text is not checked) and exit with status 2.")
    L.append("")
    L.append("## Log lines")
    L.append("")
    L.append(f"A log line has exactly **seven fields separated by {SEP_NAMES[sep]}** (exactly one separator character between fields; two separators in a row mean an empty field, "
             "and an empty field is never valid). In order the fields are:")
    L.append("")
    desc = {
        "ts": "`ts`: UTC timestamp `YYYY-MM-DDThh:mm:ssZ` written with exactly that shape (digits in the `Y M D h m s` places, the literal `-`, `T`, `:` and `Z`); month 01-12, day 01-31 (no per-month check), hour 00-23, minute and second 00-59",
        "ip": "`ip`: client address, four decimal numbers of one to three digits separated by `.`, each at most 255",
        "method": "`method`: one of `GET`, `POST`, `PUT`, `DELETE`, `HEAD`",
        "path": "`path`: starts with `/`, contains no space or tab. Everything from the first `?` on is a query string and is ignored: the **path key** is the text before the first `?`",
        "status": "`status`: HTTP status, exactly three digits, 100 to 599",
        "bytes": "`bytes`: response size, one to ten digits, or a single `-` meaning 0",
        "lat": ("`lat`: latency in whole milliseconds, one to seven digits" if p["lat"] == "ms" else
                "`lat`: latency in **seconds**: one to four digits, optionally followed by `.` and one to nine digits (`2`, `0.231`, `12.5`). It is converted to whole milliseconds, rounding halves up "
                "(only the first four fractional digits matter: `0.2314` is 231 ms, `0.2315` is 232 ms, `0.0004` is 0 ms)"),
    }
    for i, f in enumerate(o, 1):
        L.append(f"{i}. {desc[f]}")
    L.append("")
    L.append("A line that does not meet *all* these rules is **skipped** (counted, but otherwise ignored). Lines that are empty (zero characters) and lines starting with `#` are ignored and not counted. "
             "Lines end with `\\n`; a final line without `\\n` still counts. All other digests only use valid lines (*records*).")
    L.append("")
    L.append("## Commands")
    L.append("")
    L.append("`logsum summary` prints exactly these lines, in this order:")
    L.append("")
    L.append("```")
    L.append("requests N          number of records")
    L.append("skipped K           number of skipped lines")
    L.append("bytes B             sum of the bytes of all records")
    L.append("clients C           number of distinct ip texts among the records")
    L.append("errors E P%         E records have status 500 or more; P = E/N in percent with one decimal, halves rounded up (exact arithmetic)")
    L.append("p50 M               latency percentiles in ms (nearest rank: sort the latencies ascending, take the value at position ceil(q*N/100), at least 1)")
    L.append("p95 M")
    L.append("```")
    L.append("")
    L.append("With no records at all the last three lines are `errors 0 0.0%`, `p50 -` and `p95 -`.")
    L.append("")
    if p["has_top"]:
        L.append("`logsum top N" + (" [--by hits|bytes]" if p["by"] else "") + "`: `N` is one or two digits and at least 1. Groups the records by path key and prints the `N` best paths, one per line as `RANK PATH VALUE` "
                 "(rank counts from 1; fewer lines if there are fewer paths; nothing at all if there are no records). " +
                 ("`--by hits` (the default) ranks by the number of records and shows it; `--by bytes` ranks by the sum of bytes and shows it. " if p["by"] else "Ranking is by the number of records, which is the shown value. ") +
                 "Higher values come first; ties are broken by the path key in ascending byte order.")
        L.append("")
    if p["has_hours"]:
        L.append("`logsum hours`: one line per hour of the day (00 to 23) that has at least one record, in ascending order: `HH COUNT BAR`, where `HH` is the two-digit hour of the timestamps, `COUNT` the number of records "
                 "in that hour and `BAR` is `#` repeated `ceil(COUNT * 20 / MAX)` times, `MAX` being the largest count of any hour. Nothing is printed when there are no records.")
        L.append("")
    L.append("Any other command line - no arguments, an unknown command, extra or missing arguments, an invalid `N`" + (", an unknown option or value" if p["by"] else "") +
             " - is a usage error: nothing on standard output, exit status 2, and standard input is not read. Otherwise the exit status is 0, even when every line was skipped.")
    L.append("")
    L.append("## Where")
    L.append("")
    L.append(f"The program lives in {spec.how(lang)}.")
    L.append("")
    L.append("## Examples")
    L.append("")
    for c, out in examples:
        L.append("```")
        L.append(f"$ logsum {' '.join(c.args)} <<'EOF'")
        L.append(c.stdin.rstrip("\n").replace("\t", "<TAB>"))
        L.append("EOF")
        L.append(out.rstrip("\n"))
        L.append("```")
        L.append("")
    if sep == "\t":
        L.append("(`<TAB>` stands for a tab character in the examples above.)")
        L.append("")
    L.append(K.run_hint("bash"))
    return "\n".join(L) + "\n"


def make_cases(rng, p):
    o = p["order"]
    sep = p["sep"]
    cases = []
    ips = ["10.0.0.1", "10.0.0.2", "192.168.1.77", "203.0.113.9", "198.51.100.23", "8.8.4.4"]

    def ts(h=None, mi=None, s=None, day=None):
        h = rng.randrange(0, 24) if h is None else h
        return f"2025-03-{(day or rng.randrange(1, 29)):02d}T{h:02d}:{(rng.randrange(0, 60) if mi is None else mi):02d}:{(rng.randrange(0, 60) if s is None else s):02d}Z"

    def latv(ms):
        if p["lat"] == "ms":
            return str(ms)
        return f"{ms // 1000}.{ms % 1000:03d}"

    def line(**kw):
        f = {
            "ts": kw.get("ts") or ts(), "ip": kw.get("ip") or rng.choice(ips), "method": kw.get("method") or rng.choice(["GET", "GET", "GET", "POST", "PUT", "HEAD", "DELETE"]),
            "path": kw.get("path") or rng.choice(PATHS) + rng.choice(["", "", "", "?q=1", "?page=2&x=y"]),
            "status": kw.get("status") or str(rng.choice([200, 200, 200, 200, 204, 301, 304, 404, 404, 500, 502, 503, 101, 599])),
            "bytes": kw.get("bytes") or rng.choice(["0", "-", str(rng.randrange(1, 90000)), str(rng.randrange(100, 5000))]),
            "lat": kw.get("lat") or latv(rng.randrange(1, 4000)),
        }
        return sep.join(f[x] for x in o)

    def logn(n, **kw):
        return [line(**kw) for _ in range(n)]

    def bad_variants(base=None):
        f = dict(zip(o, (base or line()).split(sep)))
        out = []
        def with_(k, v):
            g = dict(f)
            g[k] = v
            return sep.join(g[x] for x in o)
        out += [with_("ts", "2025-03-01 10:00:00"), with_("ts", "2025-13-01T10:00:00Z"), with_("ts", "2025-03-32T10:00:00Z"), with_("ts", "2025-03-01T24:00:00Z"), with_("ts", "2025-03-01T10:60:00Z"),
                with_("ts", "2025-03-01T10:00:60Z"), with_("ts", "2025-03-01T10:00:00"), with_("ts", "2025-03-00T10:00:00Z"), with_("ts", "2025-00-01T10:00:00Z"), with_("ts", "25-03-01T10:00:00Z"),
                with_("ip", "10.0.0"), with_("ip", "10.0.0.256"), with_("ip", "10.0.0.1.5"), with_("ip", "10.0..1"), with_("ip", "a.b.c.d"), with_("ip", "1000.0.0.1"),
                with_("method", "get"), with_("method", "PATCH"), with_("method", ""),
                with_("path", "index"), with_("path", ""), with_("path", "/a b"), with_("path", "?q=1"),
                with_("status", "99"), with_("status", "600"), with_("status", "2000"), with_("status", "2o0"), with_("status", "-200"),
                with_("bytes", "abc"), with_("bytes", "-5"), with_("bytes", "12345678901"), with_("bytes", ""), with_("bytes", "1.5"),
                with_("lat", "abc"), with_("lat", ""), with_("lat", "-1"),
                with_("lat", "12345678") if p["lat"] == "ms" else with_("lat", "12345.5"),
                with_("lat", "1.5") if p["lat"] == "ms" else with_("lat", "1."),
                with_("lat", ".5") if p["lat"] == "s" else with_("lat", "0x10"),
                with_("lat", "1.2.3") if p["lat"] == "s" else with_("lat", "1e3"),
                sep.join(f[x] for x in o) + sep + "extra", sep.join(f[x] for x in o[:-1]), "just some text", sep * 6, "x" + sep + "y"]
        return out

    # examples
    ex_log = "\n".join(logn(6))
    cases.append(K.CliCase(["summary"], ex_log + "\n"))
    if p["has_top"]:
        cases.append(K.CliCase(["top", "3"], "\n".join(logn(10, path=None)) + "\n"))
    if p["has_hours"]:
        cases.append(K.CliCase(["hours"], "\n".join(logn(9)) + "\n"))
    elif len(cases) < 3:
        cases.append(K.CliCase(["summary"], "\n".join(logn(4) + bad_variants()[:2]) + "\n"))
    nex = len(cases)
    add = lambda args, text: cases.append(K.CliCase(list(args), text))  # noqa: E731
    # summary
    add(["summary"], "")
    add(["summary"], "\n")
    add(["summary"], "# only a comment\n\n#another\n")
    add(["summary"], "garbage\n")
    add(["summary"], "\n".join(bad_variants()) + "\n")
    add(["summary"], "\n".join(logn(1)))
    add(["summary"], "\n".join(logn(1)) + "\n")
    add(["summary"], "\n".join(logn(2)) + "\n")
    for n in (3, 5, 7, 10, 11, 19, 20, 21, 40, 99, 100, 101):
        lines = logn(n)
        add(["summary"], "\n".join(lines) + "\n")
    mixed = logn(12) + bad_variants()[:8] + ["#c", ""] + logn(5)
    rng.shuffle(mixed)
    add(["summary"], "\n".join(mixed) + "\n")
    # errors percent rounding
    for total, errs in [(3, 1), (3, 2), (8, 1), (16, 1), (7, 3), (40, 1), (200, 1), (9, 9), (1, 1), (1, 0), (6, 1), (2, 1), (33, 1), (13, 5), (80, 3)]:
        lines = [line(status="503") for _ in range(errs)] + [line(status="200") for _ in range(total - errs)]
        rng.shuffle(lines)
        add(["summary"], "\n".join(lines) + "\n")
    add(["summary"], "\n".join([line(status="499"), line(status="500"), line(status="599"), line(status="100"), line(status="404")]) + "\n")
    # latency edge cases
    for lats in [[5], [5, 1], [10, 20, 30, 40], list(range(1, 21)), list(range(1, 22)), [100] * 5 + [1], [3, 1, 2], [9, 7, 5, 3, 1, 8, 6, 4, 2, 10, 11], [0, 0], [4000, 1, 1999, 2000, 2001]]:
        add(["summary"], "\n".join(line(lat=latv(v)) for v in lats) + "\n")
    if p["lat"] == "s":
        ex = ["0.2314", "0.2315", "0.2316", "0.0004", "0.0005", "0.00049", "0.99949", "0.9995", "12.5", "2", "1234", "0.1", "1.0005", "3.14159", "0.000000001", "9999.9999", "0", "0.0", "0.5000"]
        for v in ex:
            add(["summary"], line(lat=v) + "\n" + line(lat="0") + "\n")
        add(["summary"], "\n".join(line(lat=v) for v in ex) + "\n")
    else:
        add(["summary"], "\n".join(line(lat=v) for v in ["0", "00", "0012", "9999999", "1", "007"]) + "\n")
    # bytes, clients
    add(["summary"], "\n".join([line(bytes="-"), line(bytes="0"), line(bytes="1234567890"), line(bytes="0000000001"), line(bytes="5")]) + "\n")
    add(["summary"], "\n".join([line(ip="1.2.3.4"), line(ip="1.2.3.4"), line(ip="01.2.3.4"), line(ip="001.2.3.4"), line(ip="1.2.3.04"), line(ip="255.255.255.255"), line(ip="0.0.0.0")]) + "\n")
    # timestamps
    add(["summary"], "\n".join([line(ts="2025-03-31T23:59:59Z"), line(ts="2025-02-31T00:00:00Z"), line(ts="2025-12-01T00:00:00Z"), line(ts="0000-01-01T00:00:00Z"), line(ts="2025-03-01t10:00:00Z"), line(ts="2025-03-01T10:00:00z")]) + "\n")
    add(["summary"], line() + "\n" + "\n".join(bad_variants()[:3]))
    # space-ish variants
    base = line()
    add(["summary"], " " + base + "\n")
    add(["summary"], base + " \n")
    add(["summary"], base + "\n" + base.replace(sep, sep + sep, 1) + "\n")
    if sep != " ":
        add(["summary"], base.replace(sep, " ") + "\n")
    # top
    if p["has_top"]:
        mk = lambda path, n, **kw: [line(path=path, **kw) for _ in range(n)]  # noqa: E731
        t1 = mk("/a", 3) + mk("/b", 5) + mk("/c", 5) + mk("/d", 1) + mk("/b?x=1", 2) + mk("/z", 5)
        rng.shuffle(t1)
        for n in ("1", "2", "3", "4", "5", "10", "99", "09", "01"):
            add(["top", n], "\n".join(t1) + "\n")
        t2 = [line(path="/q" + str(i), bytes="1") for i in range(6)] + [line(path="/Q1"), line(path="/q"), line(path="/q?"), line(path="/q?a?b")]
        add(["top", "20"], "\n".join(t2) + "\n")
        add(["top", "3"], "")
        add(["top", "3"], "bad\nlines\n")
        add(["top", "1"], "\n".join(logn(30)) + "\n")
        add(["top", "5"], "\n".join(logn(60) + bad_variants()[:6]) + "\n")
        add(["top", "3"], "\n".join(logn(7, path="/same")) + "\n")
        add(["top", "2"], "\n".join([line(path="/a?x"), line(path="/a?y"), line(path="/a"), line(path="/b")]) + "\n")
        add(["top", "5"], "\n".join([line(path="/%s" % c) for c in "aAbB_-~"] + [line(path="/a")]) + "\n")
        if p["by"]:
            t3 = mk("/big", 1, bytes="100000") + mk("/mid", 4, bytes="500") + mk("/small", 9, bytes="-") + mk("/mid2", 4, bytes="500") + mk("/zero", 2, bytes="0")
            rng.shuffle(t3)
            for n in ("1", "3", "5", "9"):
                add(["top", n, "--by", "bytes"], "\n".join(t3) + "\n")
                add(["top", n, "--by", "hits"], "\n".join(t3) + "\n")
            add(["top", "4", "--by", "bytes"], "\n".join(logn(40)) + "\n")
            add(["top", "4", "--by", "hits"], "\n".join(logn(40)) + "\n")
            add(["top", "4", "--by", "bytes"], "")
            for bad in (["top", "3", "--by"], ["top", "3", "--by", "ms"], ["top", "3", "--bye", "hits"], ["top", "3", "hits", "bytes"], ["top", "3", "--by", "hits", "x"], ["top", "--by", "hits", "3"], ["top", "3", "-by", "hits"], ["top", "3", "--by", "HITS"]):
                add(bad, "\n".join(logn(3)) + "\n")
        else:
            add(["top", "3", "--by", "bytes"], "\n".join(logn(3)) + "\n")
            add(["top", "3", "extra", "arg"], "\n".join(logn(3)) + "\n")
        for bad in (["top"], ["top", "0"], ["top", "00"], ["top", "100"], ["top", "-1"], ["top", "x"], ["top", "1.5"], ["top", ""], ["top", " 3"], ["top", "+3"]):
            add(bad, "\n".join(logn(3)) + "\n")
    else:
        add(["top", "3"], "\n".join(logn(3)) + "\n")
    # hours
    if p["has_hours"]:
        for hs in ([5], [5, 5, 5], [0, 23], [1, 1, 2, 2, 2, 3], [7] * 20 + [8], [7] * 21 + [8] * 3, [9] * 3 + [10] * 7 + [11] * 10, list(range(24)), [12] * 40 + [3] * 1 + [4] * 19, [22, 22, 23]):
            lines = [line(ts=ts(h=h)) for h in hs]
            rng.shuffle(lines)
            add(["hours"], "\n".join(lines) + "\n")
        add(["hours"], "")
        add(["hours"], "bad\n")
        add(["hours"], "\n".join(logn(50) + bad_variants()[:5]) + "\n")
        add(["hours"], "\n".join([line(ts=ts(h=7)), line(ts="2025-03-01T07:00:00z"), line(ts=ts(h=8))]) + "\n")
    # general usage errors
    for bad in ([], ["frobnicate"], ["summary", "extra"], ["SUMMARY"], ["--help"], ["summary", "--by", "hits"], [""], ["-h"], ["summary", ""]):
        add(bad, "\n".join(logn(3)) + "\n")
    if not p["has_hours"]:
        add(["hours"], "\n".join(logn(3)) + "\n")
    out, seen = [], set()
    for c in cases:
        if c.key() not in seen:
            seen.add(c.key())
            out.append(c)
    return out, nex


def prompt(rng, p, spec, lang):
    ln = K.LANG_NAME[lang]
    where = spec.short(lang)
    subs = ["`summary`"] + (["`top`"] if p["has_top"] else []) + (["`hours`"] if p["has_hours"] else [])
    st = ", ".join(subs)
    opts = [
        f"Write `logsum` for {p['site']} in {ln} (entry point {where}). It digests the server log from stdin; the log layout is unusual, so read README.md carefully. Subcommands: {st}. {K.closer(rng)}",
        f"Our log lines look like nothing a stock tool understands. README.md specifies the layout and the digests ({st}); please implement the CLI in {ln}, entry point {where}. Exit codes and skipped-line accounting are part of the spec.",
        f"need a {ln} command line tool: `logsum {subs[0].strip('`')}` and friends ({st}), reading stdin. everything is in README.md (field order, units, rounding, tie-breaks). entry point {where}. {K.closer(rng)}",
        f"Greenfield task ({ln}): implement the log digester described in README.md for {p['site']}. Commands: {st}. Entry point {where}. Hidden checks include malformed lines, rounding of percentages and percentile edge cases.",
    ]
    return rng.choice(opts).strip()


@family("greenfield-accesslog", category="greenfield", lang="mixed", kind="greenfield", n=10,
        summary="web-log digest CLI over an invented field order/separator/latency unit: summary, top-N, hourly histogram, strict validation")
def gen(rng, n):
    levels = [1, 2, 2, 3, 3, 2, 3, 3, 1, 3]
    diffs = [1, 2, 2, 3, 3, 2, 3, 4, 1, 3]
    spec = K.CliSpec("logsum")
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level, i)
        sols = {lang: sol(lang, p), "python": sol("python", p)}
        cases, nex = make_cases(rng, p)
        pt = K.merged(spec.skeleton("python"), spec.stub("python"), {spec.path("python"): sols["python"]})
        res = K.record_cli(spec, "python", pt, cases[:nex])
        ex = [(c, o[0]) for c, o in zip(cases[:nex], res)]
        rd = readme(p, spec, lang, ex)
        yield K.cli_task(
            spec=spec, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, spec, lang),
            difficulty=diffs[i % len(diffs)], slug=f"{i + 1:02d}-{lang}-{'tab' if p['sep'] == chr(9) else {' ': 'space', '|': 'pipe', ';': 'semi'}[p['sep']]}-{p['lat']}",
            tags=["cli", "text-processing", "statistics"], notes={"level": level, "order": p["order"], "sep": p["sep"], "lat": p["lat"]},
        )
