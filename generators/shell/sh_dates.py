"""Shell tasks: calendar and duration arithmetic with date(1) and bash: day counts, weekdays, business days, calendars, ages, ISO weeks, durations."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec

VALID = dd('''
    isdate() { [[ $1 =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] && [ "$(date -u -d "$1" +%F 2>/dev/null)" = "$1" ]; }
''')
V4 = "".join(("    " + l) if l.strip() else l for l in VALID.splitlines(True))


# ------------------------------------------------------------------------------------------------ 1. days between

REF_BETWEEN = dd('''
    #!/usr/bin/env bash
    # between.sh A B : whole days from date A to date B (negative if B is earlier)
    ''' + V4 + '''
    [ $# -eq 2 ] && isdate "$1" && isdate "$2" || { echo "usage: between.sh YYYY-MM-DD YYYY-MM-DD" >&2; exit 2; }
    echo $(( ($(date -u -d "$2" +%s) - $(date -u -d "$1" +%s)) / 86400 ))
''')


def make_between(rng):
    ex = scn("example", {}, Run("2031-01-01", "2031-03-01"))
    return ex, [scn("pairs", {}, Run("2031-01-01", "2031-01-01"), Run("2028-02-28", "2028-03-01"), Run("2031-02-28", "2031-03-01"), Run("2031-12-31", "2032-01-01"), Run("2031-06-15", "2031-06-01"), Run("1999-12-31", "2100-01-01"), Run("2000-02-29", "2400-02-29")),
                scn("invalid", {}, Run("2031-02-29", "2031-03-01", stderr="nonempty"), Run("2031-1-1", "2031-03-01"), Run("x", "y"), Run("2031-01-01"), Run("2031-13-01", "2031-01-01"), Run("2031-01-01", "2031-01-02", "2031-01-03"))]


# ------------------------------------------------------------------------------------------------ 2. add days

REF_ADD = dd('''
    #!/usr/bin/env bash
    # add.sh DATE N : the date N days after DATE (N may be negative)
    ''' + V4 + '''
    [ $# -eq 2 ] && isdate "$1" && [[ $2 =~ ^[-+]?[0-9]+$ ]] || { echo "usage: add.sh YYYY-MM-DD N" >&2; exit 2; }
    n=$2
    sign=1
    case $n in -*) sign=-1; n=${n#-} ;; +*) n=${n#+} ;; esac
    n=$((10#$n * sign))
    date -u -d "@$(( $(date -u -d "$1" +%s) + n * 86400 ))" +%F
''')


def make_add(rng):
    ex = scn("example", {}, Run("2031-01-30", "3"))
    return ex, [scn("offsets", {}, Run("2031-01-31", "1"), Run("2031-03-01", "-1"), Run("2028-02-28", "1"), Run("2031-12-31", "366"), Run("2031-01-01", "0"), Run("2031-01-01", "-365"), Run("2031-06-15", "+10"), Run("2031-06-15", "007"), Run("2031-06-15", "-007")),
                scn("invalid", {}, Run("2031-02-30", "1", stderr="nonempty"), Run("2031-02-01", "x"), Run("2031-02-01"), Run("2031-02-01", "1.5"))]


# ------------------------------------------------------------------------------------------------ 3. weekdays

REF_WEEKDAY = dd('''
    #!/usr/bin/env bash
    # weekday.sh DATE... : the English weekday name of every date
    ''' + V4 + '''
    [ $# -ge 1 ] || { echo "usage: weekday.sh YYYY-MM-DD..." >&2; exit 2; }
    for d in "$@"; do isdate "$d" || { echo "bad date: $d" >&2; exit 2; }; done
    for d in "$@"; do date -u -d "$d" +%A; done
''')


def make_weekday(rng):
    ex = scn("example", {}, Run("2031-01-01", "2031-01-02"))
    return ex, [scn("dates", {}, Run("2031-03-04", "2000-01-01", "2028-02-29", "1970-01-01", "2099-12-31", "2031-03-09")), scn("one bad date stops everything", {}, Run("2031-03-04", "2031-02-30", stderr="nonempty"), Run(), Run("tomorrow"))]


# ------------------------------------------------------------------------------------------------ 4. business days

REF_BDAYS = dd('''
    #!/usr/bin/env bash
    # bdays.sh A B [HOLIDAYS] : weekdays (Mon-Fri) in [A, B), not counting dates listed in HOLIDAYS (one YYYY-MM-DD per line, # comments allowed)
    ''' + V4 + '''
    [ $# -ge 2 ] && [ $# -le 3 ] && isdate "$1" && isdate "$2" || { echo "usage: bdays.sh A B [HOLIDAYS]" >&2; exit 2; }
    [ "$1" \\> "$2" ] && { echo "error: A is after B" >&2; exit 2; }
    hol=
    if [ $# -eq 3 ]; then
      [ -r "$3" ] || { echo "error: cannot read $3" >&2; exit 2; }
      hol=$(grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}[[:space:]]*$' "$3" | tr -d ' \\t')
    fi
    n=0
    d=$1
    while [ "$d" != "$2" ]; do
      dow=$(date -u -d "$d" +%u)
      if [ "$dow" -le 5 ] && ! printf '%s\\n' "$hol" | grep -qx "$d"; then n=$((n + 1)); fi
      d=$(date -u -d "$d +1 day" +%F)
    done
    echo "$n"
''')


def make_bdays(rng):
    hol = "# 2031 holidays\n2031-01-01\n2031-12-25\n\n2031-01-04  \n2031-03-03\n2031-03-03\nnot a date\n"
    ex = scn("example", {"h.txt": F("2031-03-05\n")}, Run("2031-03-03", "2031-03-10", "h.txt"))
    return ex, [scn("ranges", {"h.txt": F(hol)}, Run("2031-03-03", "2031-03-10"), Run("2031-03-03", "2031-03-10", "h.txt"), Run("2031-03-01", "2031-03-03"), Run("2031-03-03", "2031-03-03"), Run("2030-12-30", "2031-01-06", "h.txt"), Run("2031-01-01", "2032-01-01", "h.txt")),
                scn("errors", {"h.txt": F(hol)}, Run("2031-03-10", "2031-03-03", stderr="nonempty"), Run("2031-03-01", "2031-03-02", "missing.txt"), Run("2031-03-01"), Run("2031-02-30", "2031-03-02"))]


# ------------------------------------------------------------------------------------------------ 5. month calendar

REF_CAL = dd('''
    #!/usr/bin/env bash
    # cal.sh YYYY-MM : a Monday-first calendar of the month
    [ $# -eq 1 ] && [[ $1 =~ ^[0-9]{4}-(0[1-9]|1[0-2])$ ]] || { echo "usage: cal.sh YYYY-MM" >&2; exit 2; }
    first=$(date -u -d "$1-01" +%u)
    last=$(date -u -d "$1-01 +1 month -1 day" +%d)
    last=$((10#$last))
    echo "$1"
    echo "Mo Tu We Th Fr Sa Su"
    line=
    pad=$(( (first - 1) * 3 ))
    printf -v line '%*s' "$pad" ''
    col=$first
    for ((d = 1; d <= last; d++)); do
      printf -v cell '%2d' "$d"
      line+=$cell
      if [ "$col" -eq 7 ]; then echo "$line"; line=; col=1; else line+=' '; col=$((col + 1)); fi
    done
    [ -n "$line" ] && echo "${line% }"
    exit 0
''')


def make_cal(rng):
    ex = scn("example", {}, Run("2031-03"))
    return ex, [scn("months", {}, Run("2031-02"), Run("2028-02"), Run("2031-06"), Run("2031-09"), Run("2030-12"), Run("2032-02"), Run("1999-01")), scn("invalid", {}, Run("2031-13"), Run("2031-3"), Run(), Run("2031-03", "x"), Run("2031-00"))]


# ------------------------------------------------------------------------------------------------ 6. age

REF_AGE = dd('''
    #!/usr/bin/env bash
    # age.sh BIRTH TODAY : "Y years, M months, D days" between two dates (calendar difference)
    ''' + V4 + '''
    [ $# -eq 2 ] && isdate "$1" && isdate "$2" || { echo "usage: age.sh BIRTH TODAY" >&2; exit 2; }
    [ "$1" \\> "$2" ] && { echo "error: BIRTH is after TODAY" >&2; exit 2; }
    by=$((10#${1:0:4})); bm=$((10#${1:5:2})); bd=$((10#${1:8:2}))
    ty=$((10#${2:0:4})); tm=$((10#${2:5:2})); td=$((10#${2:8:2}))
    y=$((ty - by)); m=$((tm - bm)); d=$((td - bd))
    pm=$tm
    py=$ty
    while [ "$d" -lt 0 ]; do
      m=$((m - 1))
      pm=$((pm - 1))
      if [ "$pm" -eq 0 ]; then pm=12; py=$((py - 1)); fi
      dim=$(date -u -d "$(printf '%04d-%02d-01' "$py" "$pm") +1 month -1 day" +%d)
      d=$((d + 10#$dim))
    done
    if [ "$m" -lt 0 ]; then y=$((y - 1)); m=$((m + 12)); fi
    echo "$y years, $m months, $d days"
''')


def make_age(rng):
    ex = scn("example", {}, Run("1990-05-17", "2031-03-04"))
    return ex, [scn("differences", {}, Run("2031-03-04", "2031-03-04"), Run("2000-02-29", "2031-02-28"), Run("2000-02-29", "2032-02-29"), Run("1999-12-31", "2000-01-01"), Run("2031-01-31", "2031-03-01"), Run("2030-12-15", "2031-01-14"), Run("1980-07-01", "2031-06-30"),
                                    Run("2031-03-31", "2031-04-30")),
                scn("invalid", {}, Run("2031-03-04", "2031-03-03", stderr="nonempty"), Run("2031-02-30", "2031-03-03"), Run("2031-03-04"))]


# ------------------------------------------------------------------------------------------------ 7. next weekday

REF_NEXT = dd('''
    #!/usr/bin/env bash
    # next.sh DATE WEEKDAY : the first date strictly after DATE that falls on WEEKDAY (mon, Tuesday, ...)
    ''' + V4 + '''
    [ $# -eq 2 ] && isdate "$1" || { echo "usage: next.sh YYYY-MM-DD WEEKDAY" >&2; exit 2; }
    w=$(printf '%s' "$2" | tr 'A-Z' 'a-z')
    case $w in
      mon|monday) want=1 ;; tue|tues|tuesday) want=2 ;; wed|wednesday) want=3 ;; thu|thur|thurs|thursday) want=4 ;;
      fri|friday) want=5 ;; sat|saturday) want=6 ;; sun|sunday) want=7 ;;
      *) echo "bad weekday: $2" >&2; exit 2 ;;
    esac
    cur=$(date -u -d "$1" +%u)
    delta=$(( (want - cur + 7) % 7 ))
    [ "$delta" -eq 0 ] && delta=7
    date -u -d "$1 +$delta days" +%F
''')


def make_next(rng):
    ex = scn("example", {}, Run("2031-03-04", "friday"))
    return ex, [scn("weekdays", {}, Run("2031-03-04", "tue"), Run("2031-03-04", "Wed"), Run("2031-03-04", "MONDAY"), Run("2031-03-08", "sun"), Run("2031-12-30", "thursday"), Run("2028-02-27", "tues"), Run("2031-03-04", "thurs"), Run("2031-03-04", "sat")),
                scn("invalid", {}, Run("2031-03-04", "someday", stderr="nonempty"), Run("2031-03-04"), Run("2031-04-31", "mon"), Run("2031-03-04", "th"))]


# ------------------------------------------------------------------------------------------------ 8. ISO week

REF_ISO = dd('''
    #!/usr/bin/env bash
    # isoweek.sh DATE... : ISO-8601 week date YYYY-Www-D for each date
    ''' + V4 + '''
    [ $# -ge 1 ] || { echo "usage: isoweek.sh YYYY-MM-DD..." >&2; exit 2; }
    for d in "$@"; do isdate "$d" || { echo "bad date: $d" >&2; exit 2; }; done
    for d in "$@"; do date -u -d "$d" +%G-W%V-%u; done
''')


def make_iso(rng):
    ex = scn("example", {}, Run("2031-03-04"))
    return ex, [scn("year edges", {}, Run("2030-12-29", "2030-12-30", "2031-01-01", "2031-01-05", "2031-01-06", "2032-01-01", "2032-12-31", "2033-01-01", "2027-01-03", "2026-12-31", "2020-12-31", "2021-01-03")), scn("invalid", {}, Run("2031-02-29", stderr="nonempty"), Run())]


# ------------------------------------------------------------------------------------------------ 9. duration formatting

REF_FMT = dd('''
    #!/usr/bin/env bash
    # fmtdur.sh SECONDS... : "HH:MM:SS", with a "Dd " prefix from one day on
    [ $# -ge 1 ] || { echo "usage: fmtdur.sh SECONDS..." >&2; exit 2; }
    for s in "$@"; do [[ $s =~ ^[0-9]{1,15}$ ]] || { echo "bad number of seconds: $s" >&2; exit 2; }; done
    for s in "$@"; do
      s=$((10#$s))
      d=$((s / 86400)); h=$((s % 86400 / 3600)); m=$((s % 3600 / 60)); x=$((s % 60))
      if [ "$d" -gt 0 ]; then printf '%dd %02d:%02d:%02d\\n' "$d" "$h" "$m" "$x"; else printf '%02d:%02d:%02d\\n' "$h" "$m" "$x"; fi
    done
''')


def make_fmt(rng):
    ex = scn("example", {}, Run("59", "3600", "93784"))
    return ex, [scn("values", {}, Run("0", "59", "60", "3599", "3600", "86399", "86400", "90061", "1000000", "0099", "31536000", "99999999999")), scn("invalid", {}, Run("-5", stderr="nonempty"), Run("1.5"), Run("abc"), Run(), Run("10", "x"), Run("1234567890123456"))]


# ------------------------------------------------------------------------------------------------ 10. parse durations

REF_PARSE = dd('''
    #!/usr/bin/env bash
    # parsedur.sh DURATION... : "1d2h3m4s" -> seconds (units in this order, each at most once, at least one)
    [ $# -ge 1 ] || { echo "usage: parsedur.sh DURATION..." >&2; exit 2; }
    re='^([0-9]+d)?([0-9]+h)?([0-9]+m)?([0-9]+s)?$'
    for t in "$@"; do
      [ -n "$t" ] && [[ $t =~ $re ]] || { echo "bad duration: $t" >&2; exit 2; }
    done
    for t in "$@"; do
      [[ $t =~ $re ]]
      total=0
      for i in 1 2 3 4; do
        part=${BASH_REMATCH[i]}
        [ -n "$part" ] || continue
        n=$((10#${part%?}))
        case ${part: -1} in d) total=$((total + n * 86400)) ;; h) total=$((total + n * 3600)) ;; m) total=$((total + n * 60)) ;; s) total=$((total + n)) ;; esac
      done
      echo "$total"
    done
''')


def make_parse(rng):
    ex = scn("example", {}, Run("1h30m", "45s", "2d"))
    return ex, [scn("durations", {}, Run("1d2h3m4s", "90m", "0s", "007m", "15m30s", "1d1s", "100h", "5s")), scn("invalid", {}, Run("1h 30m", stderr="nonempty"), Run("30m1h"), Run(""), Run("1.5h"), Run("h"), Run("1h1h"), Run("10"), Run("5s", "x"), Run())]


# ------------------------------------------------------------------------------------------------ 11. deadline

REF_DEADLINE = dd('''
    #!/usr/bin/env bash
    # deadline.sh START N [HOLIDAYS] : the date N business days after START (Mon-Fri, skipping HOLIDAYS)
    ''' + V4 + '''
    [ $# -ge 2 ] && [ $# -le 3 ] && isdate "$1" && [[ $2 =~ ^[0-9]+$ ]] || { echo "usage: deadline.sh START N [HOLIDAYS]" >&2; exit 2; }
    hol=
    if [ $# -eq 3 ]; then
      [ -r "$3" ] || { echo "error: cannot read $3" >&2; exit 2; }
      hol=$(grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}[[:space:]]*$' "$3" | tr -d ' \\t')
    fi
    d=$1
    left=$((10#$2))
    while [ "$left" -gt 0 ]; do
      d=$(date -u -d "$d +1 day" +%F)
      dow=$(date -u -d "$d" +%u)
      if [ "$dow" -le 5 ] && ! printf '%s\\n' "$hol" | grep -qx "$d"; then left=$((left - 1)); fi
    done
    echo "$d"
''')


def make_deadline(rng):
    ex = scn("example", {}, Run("2031-03-05", "3"))
    hol = "# holidays\n2031-03-10\n2031-03-11\n2031-03-15\n2031-04-18\n"
    return ex, [scn("counting", {"h.txt": F(hol)}, Run("2031-03-05", "0"), Run("2031-03-07", "1"), Run("2031-03-08", "1"), Run("2031-03-05", "10"), Run("2031-03-05", "10", "h.txt"), Run("2031-03-07", "2", "h.txt"), Run("2031-12-30", "3"), Run("2031-03-05", "00007")),
                scn("invalid", {"h.txt": F(hol)}, Run("2031-03-05", "-1", stderr="nonempty"), Run("2031-03-05"), Run("2031-02-30", "1"), Run("2031-03-05", "1", "none.txt"))]


SPECS = [
    S("days-between-dates", 1,
      "Write `between.sh A B`: print how many whole days it is from date A to date B.",
      "`bash between.sh A B` (dates as `YYYY-MM-DD`, validated as real calendar dates) prints the number of days from `A` to `B`: positive if `B` is later, 0 if equal, negative if `B` is earlier. Anything else (wrong number of arguments, malformed or impossible dates such as `2031-02-29`) "
      "prints a usage message on stderr and exits with status 2, with nothing on stdout.",
      REF_BETWEEN, make_between, script="between.sh", title="Days between two dates", wrong=("#!/bin/bash\necho 0\n",)),
    S("add-days-to-date", 2,
      "Write `add.sh DATE N`: the date N days after DATE (N can be negative).",
      "`bash add.sh DATE N` prints `DATE` plus `N` days as `YYYY-MM-DD`. `N` is an integer with an optional sign (`-7`, `+10`, `007`, decimal) and `DATE` a real calendar date; leap years, month and year ends must work. "
      "Invalid input prints a usage message on stderr and exits with status 2.",
      REF_ADD, make_add, script="add.sh", title="Add days to a date", wrong=("#!/bin/bash\ndate -d \"$1 $2 days\" +%F\n",)),
    S("weekday-names", 1,
      "Write `weekday.sh DATE...`: print the English weekday name of each date given.",
      "`bash weekday.sh DATE...` prints for every argument, in order, the full English weekday name (`Monday`, ..., `Sunday`) of that `YYYY-MM-DD` date. All arguments are validated first: if one is not a real calendar date, or none is given, "
      "a message goes to stderr, the exit status is 2 and nothing is printed on stdout.",
      REF_WEEKDAY, make_weekday, script="weekday.sh", title="Weekday names", wrong=("#!/bin/bash\nfor d; do date -d $d +%A; done\n",)),
    S("business-days-between", 3,
      "Write `bdays.sh A B [HOLIDAYS]`: count the working days (Monday to Friday) from A up to but excluding B, optionally skipping dates listed in a holiday file.",
      "`bash bdays.sh A B [HOLIDAYS]` prints the number of dates `D` with `A <= D < B` that fall on Monday to Friday and are not listed in `HOLIDAYS`. The holiday file has one `YYYY-MM-DD` per line; other lines (comments, blanks, garbage) and repeated dates are ignored; a holiday on a weekend changes nothing. "
      "`A` after `B`, invalid dates, a missing or unreadable holiday file or the wrong number of arguments: message on stderr, exit status 2, nothing on stdout.",
      REF_BDAYS, make_bdays, script="bdays.sh", title="Business days between dates", wrong=("#!/bin/bash\necho $(( ($(date -d $2 +%s) - $(date -d $1 +%s)) / 86400 ))\n",)),
    S("month-calendar", 3,
      "Write `cal.sh YYYY-MM`: print a Monday-first text calendar for a month in the exact layout described in the README.",
      "`bash cal.sh YYYY-MM` prints: line 1 the argument itself, line 2 `Mo Tu We Th Fr Sa Su`, then one line per week with the day numbers right-aligned in two columns, separated by single spaces, with the first week padded on the left (three characters per skipped day) and **no trailing spaces**. "
      "A malformed month (not `YYYY-MM` with a month from 01 to 12) or a wrong number of arguments: usage message on stderr, exit status 2.",
      REF_CAL, make_cal, script="cal.sh", title="Month calendar", wrong=("#!/bin/bash\ncal \"${1#*-}\" \"${1%-*}\"\n",)),
    S("calendar-age", 3,
      "Write `age.sh BIRTH TODAY`: the calendar difference between two dates as years, months and days.",
      "`bash age.sh BIRTH TODAY` prints `Y years, M months, D days` computed like this: `Y = year(TODAY) - year(BIRTH)`, `M = month(TODAY) - month(BIRTH)`, `D = day(TODAY) - day(BIRTH)`; while `D < 0` decrease `M` by one and add the number of days of a month, taking first the month that precedes `TODAY`'s month, then the one before that, and so on backwards; "
      "afterwards, if `M < 0`, decrease `Y` by one and add 12 to `M`. (Always plural words, even for 1.) `BIRTH` after `TODAY`, invalid dates or wrong argument count: message on stderr, exit status 2.",
      REF_AGE, make_age, script="age.sh", title="Calendar age", wrong=("#!/bin/bash\necho \"$(( ${2:0:4} - ${1:0:4} )) years, 0 months, 0 days\"\n",)),
    S("next-weekday-after", 3,
      "Write `next.sh DATE WEEKDAY`: the first date strictly after DATE that is the given weekday.",
      "`bash next.sh DATE WEEKDAY` prints the earliest date later than `DATE` (never `DATE` itself) whose weekday is `WEEKDAY`. The weekday is an English name, case-insensitive, either complete (`monday`) or one of the abbreviations `mon tue tues wed thu thur thurs fri sat sun`. "
      "Invalid date or weekday, or wrong argument count: usage message on stderr and exit status 2.",
      REF_NEXT, make_next, script="next.sh", title="Next weekday", wrong=("#!/bin/bash\ndate -d \"$1 next $2\" +%F\n",)),
    S("iso-week-dates", 3,
      "Write `isoweek.sh DATE...`: print the ISO-8601 week date (`YYYY-Www-D`) of each date.",
      "`bash isoweek.sh DATE...` prints, for each `YYYY-MM-DD` argument in order, its ISO-8601 week date `GGGG-Www-D`: week-based year, `W`, two-digit week number and weekday number (Monday=1 ... Sunday=7); near New Year the week-based year can differ from the calendar year. "
      "Invalid dates or no arguments: message on stderr, exit status 2 and nothing on stdout.",
      REF_ISO, make_iso, script="isoweek.sh", title="ISO week dates", wrong=("#!/bin/bash\nfor d; do date -d $d +%Y-W%W-%u; done\n",)),
    S("format-durations", 2,
      "Write `fmtdur.sh SECONDS...`: format second counts as `HH:MM:SS`, with a day count from one day on.",
      "`bash fmtdur.sh SECONDS...` prints one line per argument: `HH:MM:SS` (two digits each, hours below 24) when the duration is under one day, otherwise `Dd HH:MM:SS` with the number of whole days and no padding (`1d 02:03:04`). "
      "Each argument must be a non-negative integer of at most 15 digits (leading zeros allowed, decimal); otherwise, or with no arguments, a message goes to stderr, the exit status is 2 and nothing is printed on stdout.",
      REF_FMT, make_fmt, script="fmtdur.sh", title="Format durations", wrong=("#!/bin/bash\nfor s; do date -u -d @$s +%T; done\n",)),
    S("parse-durations", 3,
      "Write `parsedur.sh DURATION...`: convert strings such as `1d2h3m4s` or `90m` to seconds.",
      "`bash parsedur.sh DURATION...` prints the number of seconds for each argument. A duration is one or more of the parts `Nd`, `Nh`, `Nm`, `Ns` (`N` digits, leading zeros allowed and decimal) written without spaces, **in that order**, each part at most once; the units mean 86400, 3600, 60 and 1 seconds. "
      "All arguments are checked before anything is printed: an empty string, a number without unit, a wrong order, repeated units, spaces or no arguments at all give a message on stderr, exit status 2 and no output.",
      REF_PARSE, make_parse, script="parsedur.sh", title="Parse durations", wrong=("#!/bin/bash\nfor t; do echo $((${t%s})); done\n",)),
    S("deadline-in-business-days", 4,
      "Write `deadline.sh START N [HOLIDAYS]`: the date N working days after START, skipping weekends and a holiday list.",
      "`bash deadline.sh START N [HOLIDAYS]` prints the date reached by moving forward from `START` (a real calendar date) until `N` business days have passed: every following day that is Monday-Friday and not in the holiday file counts as one; `START` itself is never counted, "
      "so `N = 0` prints `START` even if it is a weekend or holiday. The holiday file has one `YYYY-MM-DD` per line; other lines are ignored. `N` is a non-negative decimal integer (leading zeros allowed). Invalid input, a missing holiday file or wrong argument count: message on stderr, exit status 2.",
      REF_DEADLINE, make_deadline, script="deadline.sh", title="Deadline in business days", wrong=("#!/bin/bash\ndate -d \"$1 +$2 days\" +%F\n",)),
]


@family("shell-date-arithmetic", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="calendar and duration arithmetic in bash with date(1): day counts, weekdays, business days, calendars, ages, ISO weeks, durations")
def date_arithmetic(rng, n):
    return K.shell_tasks("date-arithmetic", SPECS, rng, n)
