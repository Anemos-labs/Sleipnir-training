"""Shell tasks: small command-line tools with option parsing (getopts, long options, subcommands, usage errors, exit codes)."""
from fractions import Fraction

from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, Run, scn

S = K.ShellSpec

# ------------------------------------------------------------------------------------------------ 1. greet

REF_GREET = dd('''
    #!/usr/bin/env bash
    usage() { echo "usage: greet.sh [-u] [-c COUNT] [-n NAME]" >&2; exit 2; }
    name=world
    count=1
    upper=0
    while getopts ':n:c:u' o; do
      case $o in
        n) name=$OPTARG ;;
        c) count=$OPTARG ;;
        u) upper=1 ;;
        *) usage ;;
      esac
    done
    shift $((OPTIND - 1))
    [ $# -eq 0 ] || usage
    case $count in ''|*[!0-9]*|0) usage ;; esac
    line="Hello, $name!"
    if [ "$upper" = 1 ]; then line=$(printf '%s' "$line" | tr 'a-z' 'A-Z'); fi
    for ((i = 0; i < count; i++)); do printf '%s\\n' "$line"; done
''')


def make_greet(rng):
    ex = scn("example", {}, Run("-n", "Ann Lee", "-c", "2"))
    return ex, [scn("defaults and flags", {}, Run(), Run("-u"), Run("-n", "x y", "-u"), Run("-c", "3", "-n", "-dash"), Run("-un", "Bob"), Run("-nBob", "-c1")),
                scn("names", {}, Run("-n", "naïve café"), Run("-n", "it's *"), Run("-n", ""), Run("-n", "a b", "-c", "2", "-u")),
                scn("errors", {}, Run("-x", rc=True, stderr="nonempty"), Run("-n", stderr="nonempty"), Run("-c", "0"), Run("-c", "two"), Run("extra"), Run("-c", ""), Run("-n", "a", "--", "x"))]


# ------------------------------------------------------------------------------------------------ 2. unit conversion

REF_CONVERT = dd('''
    #!/usr/bin/env bash
    usage() { echo "usage: convert.sh -f UNIT -t UNIT VALUE..." >&2; exit 2; }
    from= to=
    while getopts ':f:t:' o; do
      case $o in
        f) from=$OPTARG ;;
        t) to=$OPTARG ;;
        *) usage ;;
      esac
    done
    shift $((OPTIND - 1))
    factor() {
      case $1 in
        m) echo 1 ;; km) echo 1000 ;; mi) echo 1609.344 ;; ft) echo 0.3048 ;; in) echo 0.0254 ;;
        *) return 1 ;;
      esac
    }
    a=$(factor "$from") || usage
    b=$(factor "$to") || usage
    [ $# -gt 0 ] || usage
    for v in "$@"; do
      if ! [[ $v =~ ^-?[0-9]+(\\.[0-9]+)?$ ]]; then
        echo "bad value: $v" >&2
        exit 2
      fi
      awk -v v="$v" -v a="$a" -v b="$b" 'BEGIN { printf "%.3f\\n", v * a / b }'
    done
''')

FACT = {"m": Fraction(1), "km": Fraction(1000), "mi": Fraction(1609344, 1000), "ft": Fraction(3048, 10000), "in": Fraction(254, 10000)}


def vals(rng, k, f, t):
    out = []
    while len(out) < k:
        v = Fraction(rng.randint(1, 99999), rng.choice([1, 10, 100]))
        r = v * FACT[f] / FACT[t] * 1000
        if (r - r.numerator // r.denominator) == Fraction(1, 2) or abs(float(r) - round(float(r))) < 1e-6 and False:
            continue
        # keep clear of rounding ties: distance of the fractional part from .5 must be sizeable
        frac = float(r - (r.numerator // r.denominator))
        if abs(frac - 0.5) < 0.01:
            continue
        out.append(f"{float(v):g}" if v.denominator != 1 else str(int(v)))
    return out


def make_convert(rng):
    ex = scn("example", {}, Run("-f", "mi", "-t", "km", "1", "26.2"))
    runs = []
    for f, t in (("km", "mi"), ("ft", "m"), ("in", "ft"), ("m", "in"), ("mi", "ft"), ("ft", "ft")):
        runs.append(Run("-f", f, "-t", t, *vals(rng, 4, f, t)))
    return ex, [scn("conversions", {}, *runs), scn("errors", {}, Run("-f", "yd", "-t", "m", "1", rc=True, stderr="nonempty"), Run("-f", "m", "-t", "km"), Run("-t", "m", "1"),
                                                    Run("-f", "m", "-t", "km", "10", "abc", "20"), Run("-f", "m", "-t", "km", "1e3"))]


# ------------------------------------------------------------------------------------------------ 3. lines

REF_LINES = dd('''
    #!/usr/bin/env bash
    usage() { echo "usage: lines.sh [-n N] [-s] [-r] [FILE...]" >&2; exit 2; }
    n= skip=0 rev=0
    while getopts ':n:sr' o; do
      case $o in
        n) n=$OPTARG ;;
        s) skip=1 ;;
        r) rev=1 ;;
        *) usage ;;
      esac
    done
    shift $((OPTIND - 1))
    case $n in '') ;; *[!0-9]*) usage ;; esac
    for f in "$@"; do
      if [ "$f" != - ] && [ ! -f "$f" ]; then
        echo "lines.sh: $f: no such file" >&2
        exit 1
      fi
    done
    if [ $# -eq 0 ]; then set -- -; fi
    for f in "$@"; do
      if [ "$f" = - ]; then cat; else cat -- "$f"; fi
    done | {
      if [ "$skip" = 1 ]; then grep -v '^[[:space:]]*$'; else cat; fi
    } | {
      if [ -n "$n" ]; then head -n "$n"; else cat; fi
    } | {
      if [ "$rev" = 1 ]; then tac; else cat; fi
    }
    exit 0
''')


def make_lines(rng):
    ex = scn("example", {"a.txt": F("one\n\ntwo\nthree\n")}, Run("-s", "-n", "2", "a.txt"))
    f = {"a b.txt": F("alpha\n\nbeta\n   \ngamma\ndelta\n"), "-dash": F("x1\nx2\n"), "empty": F("")}
    return ex, [scn("options and files", f, Run("a b.txt"), Run("-s", "a b.txt"), Run("-r", "a b.txt"), Run("-n", "2", "a b.txt"), Run("-sn", "3", "a b.txt"), Run("-srn", "2", "a b.txt"), Run("-n", "0", "a b.txt")),
                scn("several files and stdin", f, Run("-r", "--", "-dash", "a b.txt"), Run("-n", "3", "-", "-dash", stdin="from stdin\n\nmore\n"), Run("-s", stdin="a\n\n b\n\n"), Run(stdin="")),
                scn("errors", f, Run("-n", "x", "a b.txt", stderr="nonempty"), Run("nope.txt", "a b.txt", stderr="nonempty"), Run("-q"))]


# ------------------------------------------------------------------------------------------------ 4. tag names

REF_TAG = dd('''
    #!/usr/bin/env bash
    usage() { echo "usage: tagname.sh [-p PREFIX] [-s SUFFIX] [-v] [-l] NAME..." >&2; exit 2; }
    prefix= suffix= strip=0 lower=0
    while getopts ':p:s:vl' o; do
      case $o in
        p) prefix=$OPTARG ;;
        s) suffix=$OPTARG ;;
        v) strip=1 ;;
        l) lower=1 ;;
        *) usage ;;
      esac
    done
    shift $((OPTIND - 1))
    [ $# -gt 0 ] || usage
    for name in "$@"; do
      if [ "$strip" = 1 ]; then
        case $name in v*|V*) name=${name#?} ;; esac
      fi
      if [ "$lower" = 1 ]; then name=$(printf '%s' "$name" | tr 'A-Z' 'a-z'); fi
      printf '%s%s%s\\n' "$prefix" "$name" "$suffix"
    done
''')


def make_tag(rng):
    ex = scn("example", {}, Run("-v", "-p", "rel-", "v1.2.0", "v1.3.0-rc1"))
    return ex, [scn("combinations", {}, Run("1.0", "2.0"), Run("-p", "release/", "v1.0.0", "V2.0.0", "3.0.0"), Run("-s", "-final", "-l", "RC-1", "Beta"), Run("-vl", "-p", "R-", "-s", "_X", "VERSION", "v"),
                          Run("-p", "a b ", "-s", " c", "x y")),
                scn("only the first v", {}, Run("-v", "vv1", "v", "version", "xv1", "-v")),
                scn("errors", {}, Run(), Run("-p"), Run("-z", "a", stderr="nonempty"), Run("-p", "x"))]


# ------------------------------------------------------------------------------------------------ 5. env check

REF_ENV = dd('''
    #!/usr/bin/env bash
    usage() { echo "usage: envcheck.sh [-q] [-e] -r VAR [-r VAR ...]" >&2; exit 2; }
    quiet=0 exp=0 req=()
    while getopts ':r:qe' o; do
      case $o in
        r) req+=("$OPTARG") ;;
        q) quiet=1 ;;
        e) exp=1 ;;
        *) usage ;;
      esac
    done
    shift $((OPTIND - 1))
    [ $# -eq 0 ] && [ ${#req[@]} -gt 0 ] || usage
    for v in "${req[@]}"; do
      [[ $v =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || usage
    done
    rc=0
    for v in "${req[@]}"; do
      if [ -z "${!v:-}" ]; then
        rc=1
        [ "$quiet" = 1 ] || echo "missing: $v"
      elif [ "$exp" = 1 ]; then
        printf 'export %s=%q\\n' "$v" "${!v}"
      fi
    done
    exit $rc
''')


def make_env(rng):
    ex = scn("example", {}, Run("-r", "HOME", "-r", "NOPE_VAR", env={"APP_MODE": "dev"}))
    env = {"APP_MODE": "production", "APP_NAME": "two words", "EMPTY_ONE": "", "QUOTE": "it's \"x\" $HOME", "PATHS": "a:b:c", "NL": "line1\nline2"}
    return ex, [scn("missing and present", {}, Run("-r", "APP_MODE", "-r", "NOPE", "-r", "EMPTY_ONE", "-r", "APP_NAME", env=env), Run("-q", "-r", "NOPE", "-r", "EMPTY_ONE", env=env), Run("-r", "APP_MODE", "-r", "APP_NAME", env=env)),
                scn("export lines", {}, Run("-e", "-r", "APP_NAME", "-r", "QUOTE", "-r", "PATHS", "-r", "MISSING", env=env), Run("-er", "NL", "-r", "APP_MODE", env=env), Run("-qe", "-r", "APP_MODE", env=env)),
                scn("usage errors", {}, Run(), Run("-q"), Run("-r", "A-B", env=env), Run("-r", "APP_MODE", "extra", env=env), Run("-r", "1X", env=env))]


# ------------------------------------------------------------------------------------------------ 6. retry

REF_RETRY = dd('''
    #!/usr/bin/env bash
    usage() { echo "usage: retry.sh [-n TRIES] [-d SECONDS] [-q] COMMAND [ARG...]" >&2; exit 2; }
    tries=3 delay=0 quiet=0
    while getopts ':n:d:q' o; do
      case $o in
        n) tries=$OPTARG ;;
        d) delay=$OPTARG ;;
        q) quiet=1 ;;
        *) usage ;;
      esac
    done
    shift $((OPTIND - 1))
    [ $# -gt 0 ] || usage
    case $tries in ''|*[!0-9]*|0) usage ;; esac
    [[ $delay =~ ^[0-9]+(\\.[0-9]+)?$ ]] || usage
    rc=0
    for ((k = 1; k <= tries; k++)); do
      "$@"
      rc=$?
      [ "$rc" -eq 0 ] && exit 0
      [ "$quiet" = 1 ] || echo "attempt $k/$tries failed with status $rc" >&2
      [ "$k" -lt "$tries" ] && sleep "$delay"
    done
    exit "$rc"
''')

COUNT = "n=$(cat count 2>/dev/null || echo 0); n=$((n+1)); echo $n > count; "


def make_retry(rng):
    ex = scn("example", {}, Run("-n", "5", "sh", "-c", COUNT + "[ $n -ge 3 ]"))
    return ex, [scn("succeeds on the third try", {}, Run("sh", "-c", COUNT + "echo try $n; [ $n -ge 3 ]")),
                scn("gives up with the last status", {}, Run("-n", "4", "sh", "-c", COUNT + "echo try $n; exit $((n + 10))", stderr="nonempty")),
                scn("first try works", {}, Run("-q", "sh", "-c", COUNT + "echo ok")),
                scn("arguments are passed through untouched", {}, Run("-n", "2", "printf", "[%s]\\n", "a b", "-n", "*", "$HOME")),
                scn("quiet and delay", {}, Run("-q", "-d", "0", "-n", "2", "sh", "-c", COUNT + "exit 7", stderr="empty")),
                scn("usage", {}, Run(), Run("-n", "0", "true"), Run("-n", "x", "true"), Run("-d", "soon", "true"), Run("-n", "2"), Run("-z", "true")),
                scn("command not found", {}, Run("-n", "2", "definitely-not-a-command-xyz", stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 7. column picker

REF_COLS = dd('''
    #!/usr/bin/env bash
    usage() { echo "usage: cols.sh [-d DELIM] [-H] SPEC   (SPEC: 1,3-4,2 or names with -H)" >&2; exit 2; }
    delim=, hdr=0
    while getopts ':d:H' o; do
      case $o in
        d) delim=$OPTARG ;;
        H) hdr=1 ;;
        *) usage ;;
      esac
    done
    shift $((OPTIND - 1))
    [ $# -eq 1 ] || usage
    [ "${#delim}" -eq 1 ] || usage
    spec=$1
    awk -F"$delim" -v OFS="$delim" -v spec="$spec" -v hdr="$hdr" '
      function fail(m) { print m > "/dev/stderr"; bad = 1; exit 2 }
      function resolve(   n, i, items, it, a, b, k) {
        n = split(spec, items, ",")
        cnt = 0
        for (i = 1; i <= n; i++) {
          it = items[i]
          if (it ~ /^[0-9]+$/) { cols[++cnt] = it + 0 }
          else if (it ~ /^[0-9]+-[0-9]+$/) { split(it, ab, "-"); for (k = ab[1] + 0; k <= ab[2] + 0; k++) cols[++cnt] = k }
          else if (hdr && (it in idx)) { cols[++cnt] = idx[it] }
          else fail("unknown column: " it)
        }
      }
      NR == 1 { for (i = 1; i <= NF; i++) if (!($i in idx)) idx[$i] = i; resolve() }
      { out = ""; for (i = 1; i <= cnt; i++) out = out (i > 1 ? OFS : "") $(cols[i]); print out }
      END { if (NR == 0 && !bad) resolve() }
    ' | cat
    exit "${PIPESTATUS[0]}"
''')


def make_cols(rng):
    ex = scn("example", {}, Run("1,3", stdin="a,b,c\n1,2,3\n"))
    data = "id,name,city,score\n1,Ann,Oslo,10\n2,Bob,Rome,20\n3,Cy,,30\n"
    pipe = "id|name|city\n1|Ann|Oslo\n2|Bo b|Rome\n"
    return ex, [scn("numeric specs", {}, Run("1", stdin=data), Run("4,1", stdin=data), Run("2-4", stdin=data), Run("3,1-2,3", stdin=data), Run("1,6,2", stdin=data)),
                scn("names with -H", {}, Run("-H", "name,score", stdin=data), Run("-H", "city,id,2", stdin=data), Run("-H", "name-id", stdin=data, stderr="nonempty"), Run("name", stdin=data, stderr="nonempty")),
                scn("other delimiters", {}, Run("-d", "|", "-H", "city,name", stdin=pipe), Run("-d", "|", "1-2", stdin=pipe), Run("-d", ";", "2", stdin="a;b;c\n;;\n")),
                scn("usage", {}, Run(stdin=data), Run("-d", "ab", "1", stdin=data), Run("1", "2", stdin=data), Run("-x", "1", stdin=data))]


# ------------------------------------------------------------------------------------------------ 8. long options

REF_LONG = dd('''
    #!/usr/bin/env bash
    usage() { echo "usage: cfg.sh [-v|--verbose] [-q|--quiet] [-o|--output FILE] [-I|--include DIR]... [--] [OPERAND...]" >&2; exit 2; }
    verbose=0 quiet=0 output= includes=() operands=()
    while [ $# -gt 0 ]; do
      case $1 in
        --) shift; operands+=("$@"); break ;;
        --verbose) verbose=1 ;;
        --quiet) quiet=1 ;;
        --output=*) output=${1#--output=} ;;
        --output) [ $# -ge 2 ] || usage; output=$2; shift ;;
        --include=*) includes+=("${1#--include=}") ;;
        --include) [ $# -ge 2 ] || usage; includes+=("$2"); shift ;;
        --*) usage ;;
        -?*)
          rest=${1#-}
          while [ -n "$rest" ]; do
            c=${rest:0:1}
            rest=${rest:1}
            case $c in
              v) verbose=1 ;;
              q) quiet=1 ;;
              o|I)
                if [ -n "$rest" ]; then val=$rest; rest=; else [ $# -ge 2 ] || usage; val=$2; shift; fi
                if [ "$c" = o ]; then output=$val; else includes+=("$val"); fi
                ;;
              *) usage ;;
            esac
          done
          ;;
        *) operands+=("$1") ;;
      esac
      shift
    done
    echo "verbose=$verbose"
    echo "quiet=$quiet"
    echo "output=$output"
    echo "include=$(IFS=:; echo "${includes[*]}")"
    echo "operands=${#operands[@]}"
    for o in "${operands[@]}"; do echo "operand: $o"; done
''')


def make_long(rng):
    ex = scn("example", {}, Run("-v", "--output=out.txt", "-I", "src", "--include", "lib", "file one"))
    return ex, [scn("long and short forms", {}, Run(), Run("--verbose", "--quiet"), Run("-vq"), Run("-o", "a b"), Run("-oattached"), Run("--output", "x", "--output=y"), Run("-I", "a", "-Ib", "--include=c", "--include", "d")),
                scn("operands and terminator", {}, Run("one", "-v", "two"), Run("--", "-v", "--quiet", "three"), Run("-", "x", "--", "--"), Run("-vo", "f", "arg", "-q")),
                scn("errors", {}, Run("--nope"), Run("-x"), Run("-o"), Run("--output"), Run("-vI"), Run("-vz"), Run("--include"))]


# ------------------------------------------------------------------------------------------------ 9. fix getopts

BUGGY_MSG = dd('''
    #!/bin/bash
    # sendmsg.sh [-t TO] [-s SUBJECT] [-v] BODY...
    to=postmaster
    subject="(no subject)"
    verbose=no
    while getopts "t:s:v" opt; do
      case $opt in
        t) to=$OPTARG ;;
        s) subject=$OPTARG ;;
        v) verbose=yes ;;
      esac
    done
    body=$@
    if [ -z $body ]; then
      echo "empty message" >&2
      exit 2
    fi
    echo "To: $to"
    echo "Subject: $subject"
    echo "Body: $body"
    echo "Verbose: $verbose"
''')

REF_MSG = dd('''
    #!/bin/bash
    # sendmsg.sh [-t TO] [-s SUBJECT] [-v] BODY...
    usage() { echo "usage: sendmsg.sh [-t TO] [-s SUBJECT] [-v] BODY..." >&2; exit 2; }
    to=postmaster
    subject="(no subject)"
    verbose=no
    while getopts ":t:s:v" opt; do
      case $opt in
        t) to=$OPTARG ;;
        s) subject=$OPTARG ;;
        v) verbose=yes ;;
        *) usage ;;
      esac
    done
    shift $((OPTIND - 1))
    body="$*"
    if [ -z "$body" ]; then
      echo "empty message" >&2
      exit 2
    fi
    echo "To: $to"
    echo "Subject: $subject"
    echo "Body: $body"
    echo "Verbose: $verbose"
''')


def make_msg(rng):
    ex = scn("example", {}, Run("-t", "ops@example.org", "-s", "Disk almost full", "check", "the", "NAS"))
    return ex, [scn("normal use", {}, Run("hello"), Run("-v", "hello", "world"), Run("-t", "a b", "-s", "x y", "-v", "multi word", "body"), Run("-s", "*", "star *"), Run("-vt", "root", "up"), Run("-s", "-v", "dash subject", "text")),
                scn("body that looks like an option after --", {}, Run("--", "-v", "is", "text"), Run("-t", "x", "--", "-t")),
                scn("errors", {}, Run(), Run("-t", "x"), Run("-q", "body", stderr="nonempty"), Run("-t", stderr="nonempty"), Run("-v"), Run("", ""))]


# ------------------------------------------------------------------------------------------------ 10. subcommands

REF_SUB = dd('''
    #!/usr/bin/env bash
    usage() { echo "usage: chores.sh [-f FILE] [-v] add [-p 1-5] TEXT... | list [-p N] | rm N" >&2; exit 2; }
    file=items.txt verbose=0
    while getopts ':f:v' o; do
      case $o in
        f) file=$OPTARG ;;
        v) verbose=1 ;;
        *) usage ;;
      esac
    done
    shift $((OPTIND - 1))
    [ $# -gt 0 ] || usage
    cmd=$1
    shift
    OPTIND=1
    tab=$(printf '\\t')
    case $cmd in
      add)
        prio=3
        while getopts ':p:' o; do
          case $o in p) prio=$OPTARG ;; *) usage ;; esac
        done
        shift $((OPTIND - 1))
        [ $# -gt 0 ] || usage
        case $prio in [1-5]) ;; *) usage ;; esac
        printf '%s\\t%s\\n' "$prio" "$*" >> "$file"
        [ "$verbose" = 1 ] && echo "added: $*"
        exit 0
        ;;
      list)
        filter=
        while getopts ':p:' o; do
          case $o in p) filter=$OPTARG ;; *) usage ;; esac
        done
        shift $((OPTIND - 1))
        [ $# -eq 0 ] || usage
        [ -f "$file" ] || exit 0
        n=0
        while IFS="$tab" read -r p text || [ -n "$p" ]; do
          n=$((n + 1))
          if [ -n "$filter" ] && [ "$p" != "$filter" ]; then continue; fi
          printf '%d. [%s] %s\\n' "$n" "$p" "$text"
        done < "$file"
        exit 0
        ;;
      rm)
        [ $# -eq 1 ] || usage
        case $1 in ''|*[!0-9]*|0) usage ;; esac
        total=0
        [ -f "$file" ] && total=$(wc -l < "$file")
        if [ "$1" -gt "$total" ]; then echo "no item $1" >&2; exit 1; fi
        text=$(sed -n "${1}p" "$file" | cut -f2-)
        sed "${1}d" "$file" > "$file.tmp" && mv -- "$file.tmp" "$file"
        echo "removed: $text"
        exit 0
        ;;
      *) usage ;;
    esac
''')


def make_sub(rng):
    ex = scn("example", {}, Run("add", "-p", "1", "pay", "rent"), Run("add", "water plants"), Run("list"))
    base = "5\tbuy milk\n3\twrite report\n1\tcall the bank\n3\tfix bike\n"
    return ex, [scn("add and list", {}, Run("add", "first"), Run("add", "-p", "5", "second", "item"), Run("-v", "add", "-p", "2", "third"), Run("list"), Run("list", "-p", "3"), Run("list", "-p", "9")),
                scn("custom file with awkward name", {"my todo.txt": F(base)}, Run("-f", "my todo.txt", "list"), Run("-f", "my todo.txt", "rm", "2"), Run("-f", "my todo.txt", "list", "-p", "3"), Run("-f", "my todo.txt", "add", "-p", "4", "new * item")),
                scn("rm errors", {"items.txt": F(base)}, Run("rm", "9", stderr="nonempty"), Run("rm", "0"), Run("rm"), Run("rm", "x"), Run("rm", "1", "2"), Run("list")),
                scn("usage", {}, Run(), Run("frob"), Run("add"), Run("add", "-p", "7", "x"), Run("-x", "list"), Run("add", "-z", "x"), Run("list", "extra"), Run("list"))]


# ------------------------------------------------------------------------------------------------ 11. humanize

REF_HUMAN = dd('''
    #!/usr/bin/env bash
    usage() { echo "usage: human.sh [-b 1000|1024] [-p DECIMALS]  (byte counts on stdin)" >&2; exit 2; }
    base=1024 prec=1
    while getopts ':b:p:' o; do
      case $o in
        b) base=$OPTARG ;;
        p) prec=$OPTARG ;;
        *) usage ;;
      esac
    done
    shift $((OPTIND - 1))
    [ $# -eq 0 ] || usage
    case $base in 1000|1024) ;; *) usage ;; esac
    case $prec in [0-9]) ;; *) usage ;; esac
    awk -v base="$base" -v prec="$prec" '
      BEGIN { if (base == 1024) split("B KiB MiB GiB TiB", u, " "); else split("B kB MB GB TB", u, " ") }
      /^[0-9]+$/ {
        v = $1 + 0; i = 1
        while (v >= base && i < 5) { v /= base; i++ }
        if (i == 1) printf "%d %s\\n", v, u[1]; else printf("%." prec "f %s\\n", v, u[i])
        next
      }
      { print "skipped: " $0 > "/dev/stderr" }
    '
''')


def make_human(rng):
    ex = scn("example", {}, Run(stdin="512\n2048\n1572864\n"))

    def nums(k, base, prec):
        out = []
        while len(out) < k:
            v = rng.choice([rng.randint(0, 999), rng.randint(1000, 10 ** 6), rng.randint(10 ** 6, 10 ** 10), rng.randint(10 ** 10, 10 ** 13)])
            x, i = Fraction(v), 0
            while x >= base and i < 4:
                x /= base
                i += 1
            r = x * 10 ** prec
            frac = float(r - r.numerator // r.denominator)
            if i > 0 and abs(frac - 0.5) < 0.02:
                continue
            out.append(str(v))
        return "\n".join(out) + "\n"
    return ex, [scn("binary units", {}, Run(stdin=nums(10, 1024, 1)), Run("-p", "2", stdin=nums(8, 1024, 2)), Run("-p", "0", stdin=nums(8, 1024, 0))),
                scn("decimal units", {}, Run("-b", "1000", stdin=nums(10, 1000, 1)), Run("-b", "1000", "-p", "3", stdin=nums(8, 1000, 3))),
                scn("edges", {}, Run(stdin="0\n1023\n1024\n1048576\n1099511627776\n1125899906842624\n"), Run("-b", "1000", stdin="999\n1000\n999000\n1000000\n"), Run(stdin="12\nabc\n\n34\n")),
                scn("usage", {}, Run("-b", "10"), Run("-p", "x"), Run("-p", "10"), Run("extra"), Run("-z"))]


SPECS = [
    S("greeter-flags", 1,
      "Write `greet.sh`, a tiny CLI that greets someone: `-n NAME`, `-c COUNT`, `-u`. The README lists the exact output and what counts as a usage error.",
      "`bash greet.sh [-u] [-c COUNT] [-n NAME]` prints the line `Hello, NAME!` `COUNT` times (default name `world`, default count 1). With `-u` the whole line is converted to upper case (ASCII letters). "
      "Options may be combined (`-un Bob`, `-nBob`). Usage errors print a usage line on stderr, nothing on stdout, and exit with status 2: an unknown option, an option missing its argument, a count that is not a positive integer, or any non-option argument left over.",
      REF_GREET, make_greet, script="greet.sh", title="A greeting CLI",
      wrong=("""#!/bin/bash
echo "Hello, ${2:-world}!"
""",)),
    S("unit-converter", 2,
      "Write `convert.sh -f UNIT -t UNIT VALUE...` which converts lengths between metres, kilometres, miles, feet and inches. Exact format and error handling are in the README.",
      "`bash convert.sh -f FROM -t TO VALUE...` converts each `VALUE` from unit `FROM` to unit `TO`, one result per line with exactly three decimals (rounding of exact ties never occurs in the tests). Units: `m` (1 m), `km` (1000 m), `mi` (1609.344 m), `ft` (0.3048 m), `in` (0.0254 m). "
      "A value is an optional minus sign, digits, optionally a dot and digits (no exponents). Values are processed in order; at the first bad value print `bad value: <value>` on stderr and exit 2 (results printed earlier stay). "
      "An unknown or missing unit, or no value at all, prints a usage line on stderr and exits 2 before printing anything.",
      REF_CONVERT, make_convert, script="convert.sh", title="Length converter",
      wrong=("""#!/bin/bash
echo "0.000"
""",)),
    S("lines-filter", 2,
      "Write `lines.sh [-n N] [-s] [-r] [FILE...]`: take the first N lines, skip blank ones, reverse the result; reads stdin when no file is given. README has the order of operations.",
      "`bash lines.sh [-n N] [-s] [-r] [FILE...]` concatenates the given files in order (`-` means standard input; with no file operand it reads standard input), then applies in this order: "
      "`-s` drops lines that are empty or contain only blanks; `-n N` keeps only the first `N` lines of what is left (`N` may be 0); `-r` reverses the order of the remaining lines. "
      "A missing file prints `lines.sh: FILE: no such file` on stderr and exits 1 before any output. A non-numeric `N` or an unknown option prints a usage line on stderr and exits 2. Options may be combined (`-srn 2`).",
      REF_LINES, make_lines, script="lines.sh", title="Line filter",
      wrong=("""#!/bin/bash
while getopts n:sr o; do case $o in n) n=$OPTARG;; s) s=1;; r) r=1;; esac; done
shift $((OPTIND-1))
cat "$@" | head -n ${n:-1000000}
""",)),
    S("tag-names", 2,
      "Write `tagname.sh` that turns version strings into tag names: optional prefix and suffix, optional removal of a leading `v`, optional lower-casing. README has the order of the steps.",
      "`bash tagname.sh [-p PREFIX] [-s SUFFIX] [-v] [-l] NAME...` prints one line per `NAME`: first, with `-v`, remove **one** leading `v` or `V` from the name (only if the name starts with it, and `v` alone becomes empty); then with `-l` lower-case the ASCII letters of the name; "
      "finally put `PREFIX` in front and `SUFFIX` behind (these two are never changed). Prefix and suffix default to empty and may contain spaces. No NAME, an unknown option or an option without argument: usage line on stderr, exit status 2, nothing on stdout.",
      REF_TAG, make_tag, script="tagname.sh", title="Tag name normaliser",
      wrong=("""#!/bin/bash
while getopts p:s:vl o; do case $o in p) p=$OPTARG;; s) s=$OPTARG;; v) v=1;; l) l=1;; esac; done
shift $((OPTIND-1))
for n in $@; do [ -n "$v" ] && n=${n#v}; echo "$p$n$s"; done
""",)),
    S("required-env", 3,
      "Write `envcheck.sh`, a pre-flight check that verifies required environment variables are set and non-empty, and can print `export` lines for the good ones. The README has the exact rules.",
      "`bash envcheck.sh [-q] [-e] -r VAR [-r VAR ...]` checks each `VAR` given with `-r`, in the order given. A variable is *missing* when it is unset or empty: unless `-q`, print `missing: VAR`. "
      "A present variable is printed as `export VAR=<value>` when `-e` is given, with the value quoted exactly as `printf %q` would. Exit status 0 if nothing is missing, 1 otherwise. "
      "Usage errors (no `-r`, a name that is not a valid shell variable name `[A-Za-z_][A-Za-z0-9_]*`, leftover non-option arguments, unknown option) print a usage line on stderr and exit with status 2 before printing anything.",
      REF_ENV, make_env, script="envcheck.sh", title="Required environment variables",
      wrong=("""#!/bin/bash
for v in "$@"; do [ -z "${!v}" ] && echo "missing: $v"; done
""",)),
    S("retry-wrapper", 4,
      "Write `retry.sh [-n TRIES] [-d SECONDS] [-q] COMMAND [ARG...]`, a wrapper that re-runs a flaky command. README describes the messages, exit status and argument handling.",
      "`bash retry.sh [-n TRIES] [-d SECONDS] [-q] COMMAND [ARG...]` runs `COMMAND ARG...` (everything after the options is the command, passed on untouched: arguments such as `-n` or `*` must reach it as they are). "
      "If it exits 0, `retry.sh` exits 0 at once. Otherwise, unless `-q`, it prints `attempt K/TRIES failed with status S` on stderr, waits `SECONDS` seconds (default 0; not after the last attempt) and tries again, up to `TRIES` attempts in total (default 3). "
      "After the last failure it exits with the status of the last attempt (127 when the command does not exist). `TRIES` must be a positive integer and `SECONDS` a non-negative number, no command or an unknown option means: usage line on stderr and exit status 2 (nothing is run). The command's stdout passes through.",
      REF_RETRY, make_retry, script="retry.sh", title="Retry wrapper",
      wrong=("""#!/bin/bash
n=3; while getopts n:d:q o; do case $o in n) n=$OPTARG;; esac; done; shift $((OPTIND-1))
for i in $(seq $n); do $@ && exit 0; done; exit 1
""",)),
    S("column-picker", 4,
      "Write `cols.sh [-d DELIM] [-H] SPEC` which prints selected columns of delimited text from stdin; with `-H` the first line holds column names that SPEC can use. The README defines SPEC.",
      "`bash cols.sh [-d DELIM] [-H] SPEC` reads delimited text on standard input and prints, for every line, the columns named by `SPEC` joined with the delimiter (default `,`; `-d` takes exactly one character, which is neither a regex nor a blank issue: plain character). "
      "`SPEC` is a comma-separated list of items printed in the order given: a column number (`3`, 1-based), a range `2-4` (ascending), or - only with `-H` - a column name taken from the first line (the first line itself is processed like any other line, so the header is printed too). "
      "A number beyond the end of a line gives an empty field. An unknown name (or any name without `-H`) prints `unknown column: <item>` on stderr and exits with status 2 without printing any line. Wrong usage (missing or extra SPEC, a delimiter that is not one character, unknown option) prints a usage line on stderr and exits 2.",
      REF_COLS, make_cols, script="cols.sh", title="Column picker",
      wrong=("""#!/bin/bash
while getopts d:H o; do case $o in d) d=$OPTARG;; esac; done; shift $((OPTIND-1))
cut -d"${d:-,}" -f"$1"
""",)),
    S("long-options-parser", 4,
      "Write `cfg.sh`: an argument parser that understands both short and GNU-style long options (including `--name=value`, bundled short flags and `--`) and prints the parsed configuration. The README lists the options and the output lines.",
      "`bash cfg.sh [options] [operands]` accepts `-v`/`--verbose`, `-q`/`--quiet` (flags), `-o FILE`/`--output FILE`/`--output=FILE` (last one wins) and the repeatable `-I DIR`/`--include DIR`/`--include=DIR`. "
      "Short options can be bundled (`-vq`), a short option's value may be attached (`-ofile`) or be the next argument (`-vo file`). Options and operands may be mixed; `--` ends option parsing, and a lone `-` is an operand. "
      "It then prints: `verbose=0|1`, `quiet=0|1`, `output=<value or empty>`, `include=<values joined with ':'>`, `operands=<count>` and one line `operand: <text>` per operand in order. "
      "An unknown option or an option missing its value prints a usage line on stderr, nothing on stdout, and exits with status 2.",
      REF_LONG, make_long, script="cfg.sh", title="Short and long option parser",
      wrong=("""#!/bin/bash
v=0; q=0
while getopts vqo:I: o; do case $o in v) v=1;; q) q=1;; o) out=$OPTARG;; I) inc="$inc:$OPTARG";; esac; done
echo "verbose=$v"; echo "quiet=$q"; echo "output=$out"
""",)),
    S("fix-sendmsg-options", 2,
      "`sendmsg.sh` mishandles its options: the options leak into the message body, it chokes on bodies with spaces, and unknown options are silently ignored. Fix the argument handling.",
      "`bash sendmsg.sh [-t TO] [-s SUBJECT] [-v] BODY...` prints four lines: `To: <to>` (default `postmaster`), `Subject: <subject>` (default `(no subject)`), `Body: <all body words joined by single spaces>` and `Verbose: yes|no`. "
      "Options may be bundled and may use attached values (`-vt root`). Everything after the options (and after a `--`) is the body. If the body is empty print `empty message` on stderr and exit 2; an unknown option or an option missing its argument prints a usage line on stderr and exits 2. Nothing is printed on stdout in error cases.",
      REF_MSG, make_msg, script="sendmsg.sh", buggy=BUGGY_MSG, title="Send a message", wrong=(BUGGY_MSG,)),
    S("todo-subcommands", 4,
      "Write `chores.sh`, a tiny chore-list manager with subcommands (`add`, `list`, `rm`), a global `-f FILE` and `-v`, and per-subcommand options. README has the file format and every message.",
      "`bash chores.sh [-f FILE] [-v] COMMAND ...` stores items in `FILE` (default `items.txt` in the current directory), one per line as `<priority>`, a TAB and the text. "
      "`add [-p PRIO] TEXT...` appends an item (the words joined by spaces; priority 1-5, default 3; with the global `-v` also print `added: <text>`). "
      "`list [-p PRIO]` prints `N. [PRIO] TEXT` for each item, where `N` is the item's position in the file (also when a priority filter hides others); a missing file prints nothing. "
      "`rm N` deletes item number `N` and prints `removed: <text>`; an `N` beyond the last item prints `no item N` on stderr and exits 1. "
      "Any other problem (no command, unknown command, unknown option, bad priority, missing text, `N` not a positive integer, extra arguments) prints a usage line on stderr and exits with status 2.",
      REF_SUB, make_sub, script="chores.sh", title="Chore list manager",
      wrong=("""#!/bin/bash
echo "$@" >> items.txt
""",)),
    S("humanize-sizes", 3,
      "Write `human.sh [-b 1000|1024] [-p N]`: read byte counts from stdin and print them as `1.5 KiB`-style strings. The README gives the unit names, rounding and the treatment of bad lines.",
      "`bash human.sh [-b BASE] [-p DECIMALS]` reads one non-negative integer per line from standard input and prints it with the largest unit for which the value is at least 1. With base 1024 (default) the units are `B KiB MiB GiB TiB`, with `-b 1000` they are `B kB MB GB TB` (no unit above `TB`). "
      "Plain bytes are printed as an integer (`512 B`); larger units use `DECIMALS` decimals (`-p`, a single digit 0-9, default 1), rounded like C `printf` (the tests avoid exact ties), e.g. `1.5 KiB`. "
      "A line that is not a non-negative integer is reported as `skipped: <line>` on stderr and processing continues. Invalid options (`-b` other than 1000 or 1024, `-p` not a digit, unknown option, leftover arguments) print a usage line on stderr and exit with status 2.",
      REF_HUMAN, make_human, script="human.sh", title="Human-readable sizes",
      wrong=("""#!/bin/bash
awk '{ printf "%.1f KiB\\n", $1 / 1024 }'
""",)),
]


@family("shell-cli-options", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="small command-line tools in bash: getopts, long options, subcommands, usage errors and exit codes")
def cli_options(rng, n):
    return K.shell_tasks("cli-options", SPECS, rng, n)
