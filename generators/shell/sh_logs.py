"""Shell tasks: log retention and rotation (dates in file names, retention tiers, caps, compression)."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec

LOGDATE = dd('''
    # prints the epoch of the first valid YYYY-MM-DD found in a name; fails when there is none
    logdate() {
      local d
      [[ $1 =~ ([0-9]{4}-[0-9]{2}-[0-9]{2}) ]] || return 1
      d=${BASH_REMATCH[1]}
      [ "$(date -u -d "$d" +%F 2>/dev/null)" = "$d" ] || return 1
      date -u -d "$d" +%s
    }
''')


LD = "".join(("    " + l) if l.strip() else l for l in LOGDATE.splitlines(True))


def L_(name, lines=3, m=None, gz=False):
    return F((f"{name}: entry\n") * lines, m=m, gz=gz)


def logs(names, lines=3):
    return {n: L_(n, lines) for n in names}


def nm(prefix, y, mo, d, ext=".log"):
    return f"{prefix}{y:04d}-{mo:02d}-{d:02d}{ext}"


# ------------------------------------------------------------------------------------------------ 1. keep newest N

REF_KEEP = dd('''
    #!/usr/bin/env bash
    # prune.sh N DIR : keep the N newest *.log files (names carry the date), delete the others
    n=${1:-}
    dir=${2:-}
    case $n in ''|*[!0-9]*|0) echo "usage: prune.sh N DIR" >&2; exit 2 ;; esac
    cd -- "$dir" 2>/dev/null || { echo "no such directory: $dir" >&2; exit 2; }
    shopt -s nullglob
    files=(*.log)
    [ "${#files[@]}" -gt 0 ] || exit 0
    mapfile -d '' -t sorted < <(printf '%s\\0' "${files[@]}" | LC_ALL=C sort -z -r)
    del=()
    for ((i = n; i < ${#sorted[@]}; i++)); do
      rm -- "${sorted[i]}"
      del+=("${sorted[i]}")
    done
    [ "${#del[@]}" -gt 0 ] || exit 0
    printf '%s\\0' "${del[@]}" | LC_ALL=C sort -z | while IFS= read -r -d '' f; do echo "deleted: $f"; done
''')


def make_keep(rng):
    ex = scn("example", logs(["app-2031-03-01.log", "app-2031-03-02.log", "app-2031-03-03.log", "notes.txt"]), Run("2", "."))
    a = logs([nm("web access ", 2031, 5, d) for d in (1, 2, 3, 9, 10, 11, 30)] + ["-odd-2031-01-01.log", "it's 2031-01-02.log", "ünï-2031-01-03.log", "keep.txt", "log"])
    a["sub/app-2031-01-01.log"] = L_("sub")
    return ex, [scn("awkward names", a, Run("3", ".")), scn("fewer than N", logs(["a.log", "b.log"]), Run("5", ".")), scn("directory argument", {**logs(["d/x-1.log", "d/x-2.log", "d/x-3.log"])}, Run("1", "d")),
                scn("bad usage", logs(["a.log"]), Run("0", "."), Run("two", "."), Run("1", "nope"), Run())]


# ------------------------------------------------------------------------------------------------ 2. age from the file name

REF_AGE = dd('''
    #!/usr/bin/env bash
    # prune.sh --today DATE --days N DIR : delete *.log files whose name date is more than N days before DATE
    today= days= dir=
    while [ $# -gt 0 ]; do
      case $1 in
        --today) today=${2:-}; shift 2 ;;
        --days) days=${2:-}; shift 2 ;;
        -*) echo "unknown option: $1" >&2; exit 2 ;;
        *) dir=$1; shift ;;
      esac
    done
    case $days in ''|*[!0-9]*) days= ;; esac
    if [ -z "$today" ] || [ -z "$days" ] || [ -z "$dir" ]; then echo "usage: prune.sh --today DATE --days N DIR" >&2; exit 2; fi
    t=$(date -u -d "$today" +%s 2>/dev/null) || { echo "bad date: $today" >&2; exit 2; }
    ''' + LD + '''
    cd -- "$dir" || exit 1
    shopt -s nullglob
    for f in *.log; do
      e=$(logdate "$f") || continue
      if [ $(( (t - e) / 86400 )) -gt "$days" ]; then
        rm -- "$f"
        echo "deleted: $f"
      fi
    done
''')


def make_age(rng):
    ex = scn("example", logs(["app-2031-03-01.log", "app-2031-03-20.log", "readme.log"]), Run("--today", "2031-03-25", "--days", "10", "."))
    a = logs(["x 2031-02-27.log", "x 2031-03-01.log", "x 2031-03-02.log", "x 2031-03-03.log", "y-2031-02-30.log", "-lead 2031-01-01.log", "ünï 2030-12-31.log", "no date.log", "late-2031-04-01.log", "2031-03-02-name.log", "2031-03-02.txt", "20310101.log"])
    return ex, [scn("boundaries and bad dates", a, Run("--today", "2031-03-12", "--days", "9", ".")), scn("options in another order", a, Run(".", "--days", "30", "--today", "2031-03-12")),
                scn("bad usage", a, Run("--days", "3", "."), Run("--today", "2031-13-40", "--days", "3", "."), Run("--bogus", "."))]


# ------------------------------------------------------------------------------------------------ 3. numbered rotation

REF_ROTATE = dd('''
    #!/usr/bin/env bash
    # rotate.sh FILE KEEP : FILE -> FILE.1 -> FILE.2 ... keeping KEEP old copies, then start an empty FILE
    f=${1:-}
    keep=${2:-}
    case $keep in ''|*[!0-9]*|0) echo "usage: rotate.sh FILE KEEP" >&2; exit 2 ;; esac
    [ -n "$f" ] || { echo "usage: rotate.sh FILE KEEP" >&2; exit 2; }
    rm -f -- "$f.$keep"
    for ((i = keep - 1; i >= 1; i--)); do
      if [ -e "$f.$i" ]; then mv -- "$f.$i" "$f.$((i + 1))"; fi
    done
    [ -e "$f" ] && mv -- "$f" "$f.1"
    : > "$f"
''')


def make_rotate(rng):
    ex = scn("example", {"app.log": F("current\n"), "app.log.1": F("one\n"), "app.log.2": F("two\n")}, Run("app.log", "3"))
    full = {"my app.log": F("now\n"), "my app.log.1": F("1\n"), "my app.log.2": F("2\n"), "my app.log.3": F("3\n"), "my app.log.4": F("4\n"), "other.log": F("o\n")}
    return ex, [scn("full chain", full, Run("my app.log", "3")), scn("sparse chain", {"-x.log": F("c\n"), "-x.log.2": F("two\n")}, Run("-x.log", "4")),
                scn("run twice", {"logs/a b.log": F("v1\n")}, Run("logs/a b.log", "2"), Run("logs/a b.log", "2", ops=[{"op": "write", "path": "logs/a b.log", "c": "v2\n"}]), Run("logs/a b.log", "2", ops=[{"op": "write", "path": "logs/a b.log", "c": "v3\n"}])),
                scn("no current file", {"x.log.1": F("old\n")}, Run("x.log", "2")), scn("keep one", {"y.log": F("y\n"), "y.log.1": F("y1\n")}, Run("y.log", "1")),
                scn("bad usage", {"z.log": F("z\n")}, Run("z.log", "0"), Run("z.log", "x"), Run())]


# ------------------------------------------------------------------------------------------------ 4. tiered retention

REF_TIER = dd('''
    #!/usr/bin/env bash
    # retain.sh --today DATE DIR : daily/weekly/monthly retention of *.log files by the date in their names
    today=
    dir=
    while [ $# -gt 0 ]; do
      case $1 in
        --today) today=${2:-}; shift 2 ;;
        *) dir=$1; shift ;;
      esac
    done
    [ -n "$today" ] && [ -n "$dir" ] || { echo "usage: retain.sh --today DATE DIR" >&2; exit 2; }
    t=$(date -u -d "$today" +%s) || exit 2
    ''' + LD + '''
    tab=$(printf '\\t')
    cd -- "$dir" || exit 1
    shopt -s nullglob
    tmp=$(mktemp)
    for f in *.log; do
      e=$(logdate "$f") || continue
      age=$(( (t - e) / 86400 ))
      if [ "$age" -le 6 ]; then continue; fi
      if [ "$age" -le 34 ]; then
        printf 'weekly\\t%s\\t%s\\t%s\\n' "$(date -u -d "@$e" +%G-%V)" "$e" "$f"
      elif [ "$age" -le 180 ]; then
        printf 'monthly\\t%s\\t%s\\t%s\\n' "$(date -u -d "@$e" +%Y-%m)" "$e" "$f"
      else
        printf 'drop\\t-\\t%s\\t%s\\n' "$e" "$f"
      fi
    done > "$tmp"
    LC_ALL=C sort -t"$tab" -k1,1 -k2,2 -k3,3nr -k4,4r "$tmp" | awk -F'\\t' '{ k = $1 "\\t" $2; if ($1 == "drop" || (k in seen)) print $4; else seen[k] = 1 }' | LC_ALL=C sort |
      while IFS= read -r f; do rm -- "$f"; echo "deleted: $f"; done
    rm -f "$tmp"
''')


def make_tier(rng):
    import datetime
    today = datetime.date(2031, 6, 30)

    def mk(days_ago, prefix="svc-"):
        d = today - datetime.timedelta(days=days_ago)
        return f"{prefix}{d.isoformat()}.log"
    ex = scn("example", logs([mk(a) for a in (0, 1, 2, 8, 9, 15, 16, 40, 41, 200)]), Run("--today", "2031-06-30", "."))
    ages = list(range(0, 12)) + [13, 14, 15, 20, 21, 27, 28, 29, 33, 34, 35, 36, 50, 60, 63, 64, 90, 120, 150, 179, 180, 181, 200, 400]
    a = logs([mk(x, "app log ") for x in ages] + ["undated.log", "app log 2031-02-30.log", "notes.txt"])
    b = logs([mk(x, "-b-") for x in (7, 8, 9, 10, 11, 12, 13, 33, 34, 35, 36, 37)] + [mk(x, "-b-") for x in (34, 35)])
    # week boundary and year boundary
    c = logs([f"y-{d}.log" for d in ("2030-12-29", "2030-12-30", "2030-12-31", "2031-01-01", "2031-01-02", "2031-01-03", "2031-01-04", "2031-01-05", "2031-01-06", "2031-01-07", "2031-01-31", "2031-02-01", "2031-02-28")])
    return ex, [scn("all tiers", a, Run("--today", "2031-06-30", ".")), scn("tier edges", b, Run("--today", "2031-06-30", ".")), scn("ISO weeks across the new year", c, Run("--today", "2031-02-06", "."))]


# ------------------------------------------------------------------------------------------------ 5. compress old

REF_GZ = dd('''
    #!/usr/bin/env bash
    # compress.sh --today DATE --days N DIR : gzip *.log files older than N days (by name date)
    today= days= dir=
    while [ $# -gt 0 ]; do
      case $1 in
        --today) today=${2:-}; shift 2 ;;
        --days) days=${2:-}; shift 2 ;;
        *) dir=$1; shift ;;
      esac
    done
    [ -n "$today" ] && [ -n "$days" ] && [ -n "$dir" ] || { echo "usage: compress.sh --today DATE --days N DIR" >&2; exit 2; }
    t=$(date -u -d "$today" +%s) || exit 2
    ''' + LD + '''
    cd -- "$dir" || exit 1
    shopt -s nullglob
    for f in *.log; do
      e=$(logdate "$f") || continue
      [ $(( (t - e) / 86400 )) -gt "$days" ] || continue
      if [ -e "$f.gz" ]; then
        echo "skip: $f"
        continue
      fi
      gzip -n -- "$f"
      echo "compressed: $f"
    done
''')


def make_gz(rng):
    ex = scn("example", {"a-2031-01-01.log": L_("a", 4), "a-2031-03-01.log": L_("b", 4)}, Run("--today", "2031-03-10", "--days", "30", "."))
    a = {"old 2031-01-05.log": L_("o1", 20), "-dash-2031-01-06.log": L_("o2", 20), "recent 2031-03-09.log": L_("r", 5), "ünï 2030-11-11.log": L_("u", 8), "no-date.log": L_("n", 2),
         "dup 2031-01-01.log": L_("d", 3), "dup 2031-01-01.log.gz": F("old archive\n", gz=True), "already-2031-01-02.log.gz": F("zip\n", gz=True), "boundary 2031-02-08.log": L_("b1", 2), "boundary 2031-02-07.log": L_("b2", 2)}
    return ex, [scn("awkward names", a, Run("--today", "2031-03-10", "--days", "30", ".")), scn("nothing old", {"x-2031-03-01.log": L_("x")}, Run("--today", "2031-03-02", "--days", "30", "."))]


# ------------------------------------------------------------------------------------------------ 6. size cap

REF_CAP = dd('''
    #!/usr/bin/env bash
    # cap.sh BYTES DIR : delete the oldest *.log files until the total size is at most BYTES (never the newest)
    cap=${1:-}
    dir=${2:-}
    case $cap in ''|*[!0-9]*) echo "usage: cap.sh BYTES DIR" >&2; exit 2 ;; esac
    cd -- "$dir" 2>/dev/null || { echo "no such directory: $dir" >&2; exit 2; }
    shopt -s nullglob
    files=(*.log)
    [ "${#files[@]}" -gt 0 ] || exit 0
    mapfile -d '' -t files < <(printf '%s\\0' "${files[@]}" | LC_ALL=C sort -z)
    total=0
    for f in "${files[@]}"; do total=$((total + $(stat -c %s -- "$f"))); done
    last=$(( ${#files[@]} - 1 ))
    for ((i = 0; i < last && total > cap; i++)); do
      s=$(stat -c %s -- "${files[i]}")
      rm -- "${files[i]}"
      total=$((total - s))
      echo "deleted: ${files[i]}"
    done
''')


def make_cap(rng):
    def sized(n, ch="x"):
        return F(ch * n)
    ex = scn("example", {"a-1.log": sized(100), "a-2.log": sized(100), "a-3.log": sized(100)}, Run("250", "."))
    a = {"app 01.log": sized(400), "app 02.log": sized(300), "app 03.log": sized(50), "app 04.log": sized(10), "-app 05.log": sized(1000), "z.txt": sized(5000), "app 06.log": sized(20)}
    return ex, [scn("deletes oldest first", {k: v for k, v in a.items() if k != "-app 05.log"}, Run("200", ".")), scn("newest alone exceeds the cap", a, Run("100", ".")),
                scn("already under cap", {"a.log": sized(5), "b.log": sized(5)}, Run("10", ".")), scn("bad usage", {"a.log": sized(5)}, Run("big", "."), Run("5", "missing"))]


# ------------------------------------------------------------------------------------------------ 7. archive by month

REF_ARCH = dd('''
    #!/usr/bin/env bash
    # archive.sh --today DATE DIR : move *.log files of earlier months into DIR/archive/YYYY/MM/
    today=
    dir=
    while [ $# -gt 0 ]; do
      case $1 in
        --today) today=${2:-}; shift 2 ;;
        *) dir=$1; shift ;;
      esac
    done
    [ -n "$today" ] && [ -n "$dir" ] || { echo "usage: archive.sh --today DATE DIR" >&2; exit 2; }
    cur=$(date -u -d "$today" +%Y-%m) || exit 2
    cd -- "$dir" || exit 1
    shopt -s nullglob
    for f in *.log; do
      [[ $f =~ ([0-9]{4})-([0-9]{2})-([0-9]{2}) ]] || continue
      y=${BASH_REMATCH[1]} m=${BASH_REMATCH[2]} d=${BASH_REMATCH[3]}
      [ "$(date -u -d "$y-$m-$d" +%F 2>/dev/null)" = "$y-$m-$d" ] || continue
      [ "$y-$m" \\< "$cur" ] || continue
      mkdir -p -- "archive/$y/$m"
      mv -- "$f" "archive/$y/$m/$f"
    done
''')


def make_arch(rng):
    ex = scn("example", logs(["app-2031-01-15.log", "app-2031-02-03.log", "app-2031-03-01.log"]), Run("--today", "2031-03-10", "."))
    a = logs(["svc 2030-12-31.log", "svc 2031-01-01.log", "-x-2031-02-28.log", "ünï 2031-03-01.log", "cur 2031-03-31.log", "future-2031-04-01.log", "bad-2031-02-30.log", "plain.log", "w 2031-03-05.txt"])
    a["archive/2031/02/old.log"] = L_("pre-existing")
    return ex, [scn("awkward names", a, Run("--today", "2031-03-15", "."), dirs="all"), scn("year rollover", logs(["j-2030-12-31.log", "j-2031-01-01.log"]), Run("--today", "2031-01-02", "."), dirs="all")]


# ------------------------------------------------------------------------------------------------ 8. trim big logs

REF_TRIM = dd('''
    #!/usr/bin/env bash
    # trim.sh LIMIT KEEP DIR : shrink *.log files bigger than LIMIT bytes to a marker line plus their last KEEP lines
    limit=${1:-}
    keep=${2:-}
    dir=${3:-}
    case $limit in ''|*[!0-9]*) echo "usage: trim.sh LIMIT KEEP DIR" >&2; exit 2 ;; esac
    case $keep in ''|*[!0-9]*) echo "usage: trim.sh LIMIT KEEP DIR" >&2; exit 2 ;; esac
    cd -- "$dir" 2>/dev/null || { echo "no such directory: $dir" >&2; exit 2; }
    shopt -s nullglob
    for f in *.log; do
      [ -f "$f" ] || continue
      [ "$(stat -c %s -- "$f")" -gt "$limit" ] || continue
      lines=$(wc -l < "$f")
      [ "$lines" -gt "$keep" ] || continue
      { printf '[trimmed %d lines]\\n' $((lines - keep)); tail -n "$keep" -- "$f"; } > "$f.tmp.$$"
      mv -- "$f.tmp.$$" "$f"
      echo "trimmed: $f"
    done
''')


def make_trim(rng):
    def lines(n, w=6):
        return F("".join(f"line {i:0{w}d}\n" for i in range(1, n + 1)))
    ex = scn("example", {"a.log": lines(10), "b.log": lines(2)}, Run("50", "3", "."))
    a = {"big one.log": lines(100), "-med.log": lines(30), "few long lines.log": F(("x" * 500 + "\n") * 3), "small.log": lines(3), "keep.txt": lines(500), "exact.log": lines(5)}
    return ex, [scn("awkward names", a, Run("200", "4", ".")), scn("keep zero", {"z.log": lines(20)}, Run("10", "0", ".")), scn("bad usage", a, Run("x", "4", "."), Run("200", ".", "."), Run("1", "2"))]


# ------------------------------------------------------------------------------------------------ 9. fix rotate

BUGGY_ROT = dd('''
    #!/bin/bash
    # rotate.sh FILE : keep three old copies of FILE (FILE.1 newest ... FILE.3 oldest)
    for i in 1 2 3; do
      mv $1.$i $1.$((i+1))
    done
    mv $1 $1.1
    touch $1
''')

REF_ROT3 = dd('''
    #!/bin/bash
    # rotate.sh FILE : keep three old copies of FILE (FILE.1 newest ... FILE.3 oldest)
    f=${1:?usage: rotate.sh FILE}
    rm -f -- "$f.3"
    for i in 2 1; do
      [ -e "$f.$i" ] && mv -- "$f.$i" "$f.$((i + 1))"
    done
    [ -e "$f" ] && mv -- "$f" "$f.1"
    : > "$f"
    exit 0
''')


def make_rot3(rng):
    ex = scn("example", {"app.log": F("now\n"), "app.log.1": F("one\n"), "app.log.2": F("two\n")}, Run("app.log"))
    full = {"my app.log": F("now\n"), "my app.log.1": F("1\n"), "my app.log.2": F("2\n"), "my app.log.3": F("3\n")}
    return ex, [scn("full chain", full, Run("my app.log")), scn("sparse", {"-x.log": F("c\n"), "-x.log.2": F("two\n")}, Run("-x.log")),
                scn("three runs", {"a b.log": F("v0\n")}, Run("a b.log"), Run("a b.log", ops=[{"op": "write", "path": "a b.log", "c": "v1\n"}]), Run("a b.log", ops=[{"op": "write", "path": "a b.log", "c": "v2\n"}]), Run("a b.log", ops=[{"op": "write", "path": "a b.log", "c": "v3\n"}])),
                scn("missing log", {"q.log.1": F("old\n")}, Run("q.log"))]


# ------------------------------------------------------------------------------------------------ 10. plan from rules

REF_PLAN = dd('''
    #!/usr/bin/env bash
    # plan.sh --today DATE DIR RULES : dry-run of a retention policy; rules are "<glob> <days|forever>"
    today= dir= rules=
    while [ $# -gt 0 ]; do
      case $1 in
        --today) today=${2:-}; shift 2 ;;
        *) if [ -z "$dir" ]; then dir=$1; else rules=$1; fi; shift ;;
      esac
    done
    [ -n "$today" ] && [ -n "$dir" ] && [ -f "$rules" ] || { echo "usage: plan.sh --today DATE DIR RULES" >&2; exit 2; }
    t=$(date -u -d "$today" +%s) || exit 2
    ''' + LD + '''
    rules=$(cd "$(dirname -- "$rules")" && pwd)/$(basename -- "$rules")
    cd -- "$dir" || exit 1
    shopt -s nullglob
    for f in *; do
      [ -f "$f" ] || continue
      rule=
      while IFS= read -r line || [ -n "$line" ]; do
        case $line in ''|'#'*) continue ;; esac
        pat=${line% *}
        val=${line##* }
        # shellcheck disable=SC2254
        case $f in $pat) rule=$val; break ;; esac
      done < "$rules"
      if [ -z "$rule" ]; then
        echo "skip $f"
      elif [ "$rule" = forever ]; then
        echo "keep $f"
      else
        e=$(logdate "$f") || { echo "keep $f"; continue; }
        if [ $(( (t - e) / 86400 )) -gt "$rule" ]; then echo "delete $f"; else echo "keep $f"; fi
      fi
    done
''')


def make_plan(rng):
    ex = scn("example", {**logs(["app-2031-01-01.log", "app-2031-03-01.log", "audit-2020-01-01.log", "other.dat"]), "rules.txt": F("audit-*.log forever\napp-*.log 30\n")}, Run("--today", "2031-03-10", ".", "rules.txt"))
    rules = "# retention rules, first match wins\n\nweb *.log 7\n-*.log 3\n*audit* forever\n*.log 90\n"
    a = {**logs(["web a 2031-03-01.log", "web b 2031-03-09.log", "web c 2031-03-03.log", "-odd 2031-03-01.log", "audit web 2031-01-01.log", "sys 2031-03-05.log", "sys 2030-01-01.log", "sys nodate.log", "notes.dat"]), "r/rules": F(rules)}
    # note: the rule "web *.log 7" has a space inside the pattern: the pattern is everything before the LAST space
    return ex, [scn("first match wins", a, Run("--today", "2031-03-10", ".", "r/rules")), scn("empty rules", {**logs(["a-2031-01-01.log"]), "e": F("")}, Run("--today", "2031-03-10", ".", "e")),
                scn("bad usage", a, Run("--today", "2031-03-10", "."), Run("--today", "2031-03-10", ".", "missing"))]


# ------------------------------------------------------------------------------------------------ 11. newest by name

REF_NEWEST = dd('''
    #!/usr/bin/env bash
    # newest.sh DIR : the file whose name carries the latest valid date (YYYY-MM-DD or YYYYMMDD)
    dir=${1:?usage: newest.sh DIR}
    cd -- "$dir" || exit 1
    tab=$(printf '\\t')
    shopt -s nullglob
    tmp=$(mktemp)
    for f in *; do
      [ -f "$f" ] || continue
      [[ $f =~ ([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{8}) ]] || continue
      d=${BASH_REMATCH[1]}
      if [[ $d == *-* ]]; then iso=$d; else iso=${d:0:4}-${d:4:2}-${d:6:2}; fi
      [ "$(date -u -d "$iso" +%F 2>/dev/null)" = "$iso" ] || continue
      printf '%s\\t%s\\n' "$iso" "$f"
    done > "$tmp"
    [ -s "$tmp" ] || { rm -f "$tmp"; exit 1; }
    LC_ALL=C sort -t"$tab" -k1,1 -k2,2 "$tmp" | tail -n 1 | cut -f2-
    rm -f "$tmp"
''')


def make_newest(rng):
    ex = scn("example", logs(["app-2031-03-01.log", "app-2031-03-09.log", "db-20310305.log"]), Run("."))
    a = logs(["web 2031-03-01.log", "web 20310302.log", "db_20310302_b.log", "db_20310302_a.log", "-x 2030-12-31.log", "bad-2031-02-30.log", "build-12345678.log", "notes.txt", "ünï-20310228.log", "phone 5551234567.log"])
    return ex, [scn("mixed formats", a, Run(".")), scn("ties by name", logs(["a-20310101.log", "b-2031-01-01.log", "A-20310101.log"]), Run(".")), scn("no dated file", logs(["plain.log", "x-2031-13-01.log"]), Run("."))]


SPECS = [
    S("keep-newest-n", 1,
      "Write `prune.sh N DIR` that keeps the N newest `.log` files in DIR (their names start with or contain the date, so name order is date order) and deletes the rest. See the README for output and errors.",
      "`bash prune.sh N DIR` looks at the files matching `*.log` directly in `DIR` (hidden files too are not considered; subdirectories are ignored). Because the names contain an ISO date, byte-wise name order is chronological: keep the `N` last names and delete all others. "
      "Print `deleted: <name>` for each deleted file in byte-wise ascending order. `N` must be a positive integer and `DIR` an existing directory, otherwise print a usage message on stderr and exit with status 2 (nothing deleted). Nothing is printed when nothing is deleted.",
      REF_KEEP, make_keep, script="prune.sh", title="Keep the N newest logs",
      wrong=("""#!/bin/bash
cd "$2" && ls -t *.log | tail -n +$(($1 + 1)) | xargs rm -f
""",)),
    S("age-from-name", 2,
      "Delete log files older than N days, where age comes from the date in the file name rather than the modification time. Write `prune.sh --today DATE --days N DIR` as the README describes.",
      "`bash prune.sh --today DATE --days N DIR` (options may come in any order, `DIR` is the one argument that is not an option value) deletes every `*.log` file directly in `DIR` whose name contains a valid `YYYY-MM-DD` date "
      "that lies **more than `N` days** before `DATE` (so a file exactly `N` days old stays). If a name contains several dates the first one counts; names with no valid calendar date (`2031-02-30`) or `*.log` files without any date are never touched, nor are files that do not end in `.log`. "
      "Print `deleted: <name>` per deleted file in byte-wise order. A missing option, a non-numeric `N`, an invalid `DATE` or an unknown option prints a usage line on stderr and exits with status 2 without deleting anything.",
      REF_AGE, make_age, script="prune.sh", title="Delete logs by the date in their names",
      wrong=("""#!/bin/bash
while [ $# -gt 0 ]; do case $1 in --today) t=$2; shift 2;; --days) n=$2; shift 2;; *) d=$1; shift;; esac; done
find "$d" -name '*.log' -mtime +$n -delete
""",)),
    S("numbered-rotation", 3,
      "Write `rotate.sh FILE KEEP`: classic numbered rotation (`app.log` becomes `app.log.1`, `app.log.1` becomes `app.log.2`, and so on) keeping KEEP old copies and leaving a fresh empty `FILE`. Check the README for the corner cases.",
      "`bash rotate.sh FILE KEEP` (`FILE` may include directories): delete `FILE.KEEP` if it exists, shift every existing `FILE.i` to `FILE.(i+1)` for `i` from `KEEP-1` down to 1 (missing numbers are simply skipped, gaps stay gaps), "
      "move `FILE` to `FILE.1` if it exists, and finally create an empty `FILE` (also when there was none). Nothing is printed. `KEEP` must be a positive integer and `FILE` non-empty, otherwise print a usage line on stderr and exit 2 without changing anything. No data may be overwritten except the dropped `FILE.KEEP`.",
      REF_ROTATE, make_rotate, script="rotate.sh", title="Numbered log rotation",
      wrong=(BUGGY_ROT,)),
    S("tiered-retention", 5,
      "Our log directory needs grandfather-father-son retention driven by the dates in the file names. Write `retain.sh --today DATE DIR`; the README spells out the daily, weekly and monthly tiers precisely.",
      "`bash retain.sh --today DATE DIR` considers `*.log` files directly in `DIR` whose name contains a valid `YYYY-MM-DD` (first date in the name; others are never touched). The age in days is `DATE` minus that date. "
      "Tiers: **age 6 or less** (including future dates): keep everything. **Age 7 to 34**: group the files by ISO week (`date +%G-%V` of the file's date) and keep only the newest file of each group (latest date; on a tie the byte-wise last name). "
      "**Age 35 to 180**: group by calendar month (`YYYY-MM`) and keep the newest of each group, same tie rule. **Age over 180**: delete. Groups are formed within a tier only (a week that straddles two tiers gives one group in each). "
      "Delete everything else in these tiers and print `deleted: <name>` for each, byte-wise sorted. Dates are UTC; file names contain no line breaks. Missing or malformed arguments: usage line on stderr, exit status 2.",
      REF_TIER, make_tier, script="retain.sh", title="Daily, weekly and monthly log retention",
      wrong=("""#!/bin/bash
echo
""",)),
    S("compress-old-logs", 3,
      "Write `compress.sh --today DATE --days N DIR` that gzips log files older than N days (by the date in the name) and reports what it did. Details are in the README.",
      "`bash compress.sh --today DATE --days N DIR` compresses every `*.log` file directly in `DIR` whose name has a valid `YYYY-MM-DD` date more than `N` days before `DATE`, using `gzip -n` so that `NAME.log` becomes `NAME.log.gz` (the original is removed). "
      "If `NAME.log.gz` already exists nothing is done for that file and `skip: <name>` is printed. Otherwise print `compressed: <name>`. Output in byte-wise order of the file names. Files without a valid date, files that are not `*.log`, and already compressed files are untouched. "
      "The tests compare the *decompressed* content of `.gz` files.",
      REF_GZ, make_gz, script="compress.sh", title="Compress old logs",
      wrong=("""#!/bin/bash
cd "$6" && for f in *.log; do gzip "$f"; done
""",)),
    S("total-size-cap", 3,
      "Write `cap.sh BYTES DIR`: delete the oldest logs until the total size of `*.log` files in DIR is at most BYTES, but never the newest one. README has the exact rules.",
      "`bash cap.sh BYTES DIR` sums the sizes of `*.log` files directly in `DIR`. While the total exceeds `BYTES`, delete the file that comes first in byte-wise name order (names are date-sorted) and print `deleted: <name>`, "
      "but never delete the last file in that order, even when it alone exceeds the cap. Other files are ignored. `BYTES` must be a non-negative integer and `DIR` an existing directory; otherwise print a usage line on stderr and exit with status 2.",
      REF_CAP, make_cap, script="cap.sh", title="Cap the total size of logs",
      wrong=("""#!/bin/bash
cd "$2" && du -sb . | cut -f1
""",)),
    S("archive-by-month", 3,
      "Write `archive.sh --today DATE DIR` which moves logs from earlier months into `DIR/archive/YYYY/MM/`. Details in the README.",
      "`bash archive.sh --today DATE DIR` moves every `*.log` file directly in `DIR` whose name contains a valid `YYYY-MM-DD` date in a month **earlier than** the month of `DATE` into `DIR/archive/YYYY/MM/` (created as needed), keeping the file name. "
      "The first valid date in the name counts. Files from the current month or later, files without a valid date and files that are not `*.log` stay. Nothing is printed. Missing arguments: usage line on stderr and exit 2.",
      REF_ARCH, make_arch, script="archive.sh", title="Archive logs by month",
      wrong=("""#!/bin/bash
cd "$3" && mkdir -p archive && mv *.log archive/
""",)),
    S("trim-oversized-logs", 3,
      "Write `trim.sh LIMIT KEEP DIR`: logs bigger than LIMIT bytes are cut down to their last KEEP lines with a marker on top. The README has the marker format and the edge cases.",
      "`bash trim.sh LIMIT KEEP DIR` processes `*.log` files directly in `DIR` that are larger than `LIMIT` bytes **and** have more than `KEEP` lines (lines = newline characters; test files end with a newline). "
      "Such a file is replaced by the single line `[trimmed N lines]`, where `N` is how many lines were dropped, followed by its last `KEEP` lines unchanged. Print `trimmed: <name>` for each processed file in byte-wise order. "
      "Other files stay byte-for-byte as they are. Non-numeric `LIMIT` or `KEEP`, or a missing directory: usage line on stderr and exit 2.",
      REF_TRIM, make_trim, script="trim.sh", title="Trim oversized logs",
      wrong=("""#!/bin/bash
cd "$3" && for f in *.log; do tail -n "$2" "$f" > "$f.new" && mv "$f.new" "$f"; done
""",)),
    S("fix-rotate-three", 2,
      "`rotate.sh` is meant to keep three old copies of a log, but it overwrites copies, creates `.4` files, errors out on missing ones and breaks on names with spaces. Fix it.",
      "`bash rotate.sh FILE` keeps three old copies of `FILE`: `FILE.1` is the most recent, `FILE.3` the oldest. A run deletes `FILE.3` (if any), shifts `FILE.2` to `FILE.3` and `FILE.1` to `FILE.2` (only those that exist), "
      "moves `FILE` to `FILE.1` if it exists and creates a new empty `FILE`. It must never create `FILE.4`, never lose a copy that should survive, print nothing and exit 0 even when some copies are missing; it must work for any file name.",
      REF_ROT3, make_rot3, script="rotate.sh", buggy=BUGGY_ROT, title="Three-copy rotation", wrong=(BUGGY_ROT,)),
    S("retention-dry-run", 4,
      "Write `plan.sh --today DATE DIR RULES`: a dry-run that says which files a retention rules file would keep or delete. The rule file syntax and the output are described in the README.",
      "`bash plan.sh --today DATE DIR RULES` prints one line per regular file directly in `DIR` (hidden files included is not required: plain `*` order), in byte-wise order, and deletes nothing. "
      "`RULES` is a text file; blank lines and lines starting with `#` are ignored; every other line is `<glob> <days>` or `<glob> forever`, where the glob is **everything before the last space** of the line (it may itself contain spaces) "
      "and is matched against the whole file name with shell glob rules. The first rule whose glob matches decides. No matching rule: `skip <name>`. `forever`: `keep <name>`. A number of days: if the name contains a valid `YYYY-MM-DD` date more than that many days before `DATE` print `delete <name>`, otherwise (younger, or no valid date) `keep <name>`. "
      "Missing arguments or a missing rules file: usage line on stderr and exit status 2.",
      REF_PLAN, make_plan, script="plan.sh", title="Retention policy dry run",
      wrong=("""#!/bin/bash
echo
""",)),
    S("newest-by-date-in-name", 3,
      "Write `newest.sh DIR` that prints the name of the file with the latest date in its name; dates appear as `YYYY-MM-DD` or `YYYYMMDD` and not every name has one. README has the tie rule and exit codes.",
      "`bash newest.sh DIR` inspects the regular files directly in `DIR`. A file is dated if its name contains a valid calendar date written `YYYY-MM-DD` or `YYYYMMDD` (the first such match, leftmost, counts; an eight-digit number that is not a real date, like a phone number, does not). "
      "Print the name of the file with the latest date; if several share it, print the byte-wise last name. Nothing else is printed. If no file is dated, print nothing and exit with status 1.",
      REF_NEWEST, make_newest, script="newest.sh", title="Newest file by date in the name",
      wrong=("""#!/bin/bash
cd "$1" && ls | sort | tail -1
""",)),
]


@family("shell-log-retention", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="log rotation and retention scripts: dates in names, tiers, caps, compression, dry runs, with deterministic --today")
def log_retention(rng, n):
    return K.shell_tasks("log-retention", SPECS, rng, n)
