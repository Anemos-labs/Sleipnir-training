"""Shell tasks: POSIX sh portability (bash-only scripts that must run under dash)."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec
FORBID = (r"\bbash\b",)
SH = "sh"

# ------------------------------------------------------------------------------------------------ 1. upper case

BUG_UP = dd('''
    #!/bin/bash
    # upper.sh WORD... : print each word in upper case
    [ $# -gt 0 ] || { echo "usage: upper.sh WORD..." >&2; exit 2; }
    for w in "$@"; do
      echo "${w^^}"
    done
''')
REF_UP = dd('''
    #!/bin/sh
    # upper.sh WORD... : print each word in upper case
    [ $# -gt 0 ] || { echo "usage: upper.sh WORD..." >&2; exit 2; }
    for w in "$@"; do
      printf '%s\\n' "$w" | tr 'a-z' 'A-Z'
    done
''')


def make_up(rng):
    ex = scn("example", {}, Run("hello", "World 2"))
    return ex, [scn("words", {}, Run("abc"), Run("Mixed Case", "ALREADY", "with-dash", "x*y"), Run("-n", "it's"), Run("")), scn("usage", {}, Run(stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 2. sorted args with count

BUG_SORT = dd('''
    #!/bin/bash
    # sortargs.sh ARG... : print "count: N" and then the arguments in byte-wise sorted order, one per line
    args=("$@")
    echo "count: ${#args[@]}"
    if [ ${#args[@]} -gt 0 ]; then
      printf '%s\\n' "${args[@]}" | LC_ALL=C sort
    fi
''')
REF_SORT = dd('''
    #!/bin/sh
    # sortargs.sh ARG... : print "count: N" and then the arguments in byte-wise sorted order, one per line
    echo "count: $#"
    if [ $# -gt 0 ]; then
      printf '%s\\n' "$@" | LC_ALL=C sort
    fi
''')


def make_sort(rng):
    ex = scn("example", {}, Run("pear", "apple", "fig"))
    return ex, [scn("args", {}, Run(), Run("b", "a", "B", "A"), Run("two words", "one", "-x", "*", "zebra", "10", "9"), Run("same", "same"), Run("é", "e", "f"))]


# ------------------------------------------------------------------------------------------------ 3. media kind

BUG_MEDIA = dd('''
    #!/bin/bash
    # media.sh NAME... : print image, audio, video or other for each file name (by extension, case-insensitive)
    shopt -s extglob nocasematch
    for f in "$@"; do
      if [[ $f == *.@(jpg|jpeg|png|gif) ]]; then
        echo image
      elif [[ $f == *.@(mp3|ogg|flac) ]]; then
        echo audio
      elif [[ $f == *.@(mp4|mkv|webm) ]]; then
        echo video
      else
        echo other
      fi
    done
''')
REF_MEDIA = dd('''
    #!/bin/sh
    # media.sh NAME... : print image, audio, video or other for each file name (by extension, case-insensitive)
    for f in "$@"; do
      case $f in
        *.[jJ][pP][gG]|*.[jJ][pP][eE][gG]|*.[pP][nN][gG]|*.[gG][iI][fF]) echo image ;;
        *.[mM][pP]3|*.[oO][gG][gG]|*.[fF][lL][aA][cC]) echo audio ;;
        *.[mM][pP]4|*.[mM][kK][vV]|*.[wW][eE][bB][mM]) echo video ;;
        *) echo other ;;
      esac
    done
''')


def make_media(rng):
    ex = scn("example", {}, Run("a.JPG", "b.mp3", "c.txt"))
    return ex, [scn("names", {}, Run("photo.jpeg", "My Song.FLAC", "clip.WebM", "x.gif", "noext", ".png", "png", "a.jpg.txt", "archive.tar.gz", "UPPER.MKV", "dot.", "two.dots.ogg", ""))]


# ------------------------------------------------------------------------------------------------ 4. repeat

BUG_REP = dd('''
    #!/bin/bash
    # repeat.sh N TEXT : print TEXT N times, one per line, then "done"
    n=$1
    text=$2
    for ((i = 0; i < n; i++)); do
      echo "$text"
    done
    echo done
''')
REF_REP = dd('''
    #!/bin/sh
    # repeat.sh N TEXT : print TEXT N times, one per line, then "done"
    [ $# -eq 2 ] || { echo "usage: repeat.sh N TEXT" >&2; exit 2; }
    case $1 in ''|*[!0-9]*) echo "usage: repeat.sh N TEXT" >&2; exit 2 ;; esac
    n=$1
    i=0
    while [ "$i" -lt "$n" ]; do
      printf '%s\\n' "$2"
      i=$((i + 1))
    done
    echo done
''')


def make_rep(rng):
    ex = scn("example", {}, Run("3", "ho"))
    return ex, [scn("counts", {}, Run("0", "x"), Run("1", "-n"), Run("4", "two words"), Run("2", "\\n"), Run("12", "*")), scn("usage", {}, Run(stderr="nonempty"), Run("x", "y"), Run("-1", "y"), Run("1"), Run("1", "a", "b"))]


# ------------------------------------------------------------------------------------------------ 5. reverse lines

BUG_REV = dd('''
    #!/bin/bash
    # revlines.sh FILE : print the lines of FILE last to first as "N: text" where N is the original line number
    mapfile -t lines < "$1"
    for ((i = ${#lines[@]} - 1; i >= 0; i--)); do
      echo "$((i + 1)): ${lines[i]}"
    done
''')
REF_REV = dd('''
    #!/bin/sh
    # revlines.sh FILE : print the lines of FILE last to first as "N: text" where N is the original line number
    [ $# -eq 1 ] && [ -r "$1" ] || { echo "usage: revlines.sh FILE" >&2; exit 2; }
    awk '{ l[NR] = $0 } END { for (i = NR; i >= 1; i--) print i ": " l[i] }' "$1"
''')


def make_rev(rng):
    ex = scn("example", {"t.txt": F("one\ntwo\nthree\n")}, Run("t.txt"))
    f = {"plain": F("a\nb\nc\n"), "spaced out": F("  lead\ntrail  \n\ttab\n\nblank above\n"), "no newline": F("x\ny"), "empty": F(""), "slashes": F("back\\slash\n*\n$HOME\n")}
    return ex, [scn("files", f, Run("plain"), Run("spaced out"), Run("no newline"), Run("empty"), Run("slashes")), scn("usage", f, Run(stderr="nonempty"), Run("missing"), Run("plain", "empty"))]


# ------------------------------------------------------------------------------------------------ 6. hashtag frequency

BUG_TAGS = dd('''
    #!/bin/bash
    # tags.sh : read text on stdin and print how often each #hashtag occurs: "<count> #tag", most frequent first, ties by tag
    declare -A count
    while read -ra words; do
      for w in "${words[@]}"; do
        if [[ $w =~ ^#[A-Za-z0-9_]+$ ]]; then
          t=${w,,}
          count[$t]=$(( ${count[$t]:-0} + 1 ))
        fi
      done
    done
    for t in "${!count[@]}"; do
      echo "${count[$t]} $t"
    done | sort -k1,1nr -k2
''')
REF_TAGS = dd('''
    #!/bin/sh
    # tags.sh : read text on stdin and print how often each #hashtag occurs: "<count> #tag", most frequent first, ties by tag
    tr -s ' \\t' '\\n\\n' | grep -E '^#[A-Za-z0-9_]+$' | tr 'A-Z' 'a-z' | LC_ALL=C sort | uniq -c |
      awk '{ print $1, $2 }' | LC_ALL=C sort -k1,1nr -k2
    exit 0
''')


def make_tags(rng):
    ex = scn("example", {}, Run(stdin="loving #Rust and #rust today #go\n#go #go\n"))
    text = "Release day #Launch #launch! thanks all #team_1 #TEAM_1 #team_1\nnot tags: C# #, # alone, a#b ##double #ok-dash\n\ttabbed  #Zed   #zed\n#A #b #a #B #a\n"
    return ex, [scn("tags", {}, Run(stdin=text), Run(stdin="no tags here\n"), Run(stdin=""), Run(stdin="#one\n#two #one"))]


# ------------------------------------------------------------------------------------------------ 7. echo -e table

BUG_TABLE = dd('''
    #!/bin/bash
    # table.sh NAME QTY [NAME QTY...] : print a TAB-separated table with the header "ITEM<TAB>QTY"
    [ $(($# % 2)) -eq 0 ] && [ $# -gt 0 ] || { echo "usage: table.sh NAME QTY [NAME QTY...]" >&2; exit 2; }
    echo -e "ITEM\\tQTY"
    while [ $# -gt 0 ]; do
      echo -e "$1\\t$2"
      shift 2
    done
    echo -n "rows: "
    echo $(( $(echo "$@" | wc -w) ))
''')
REF_TABLE = dd('''
    #!/bin/sh
    # table.sh NAME QTY [NAME QTY...] : print a TAB-separated table with the header "ITEM<TAB>QTY" and then "rows: N"
    [ $(($# % 2)) -eq 0 ] && [ $# -gt 0 ] || { echo "usage: table.sh NAME QTY [NAME QTY...]" >&2; exit 2; }
    rows=$(($# / 2))
    printf 'ITEM\\tQTY\\n'
    while [ $# -gt 0 ]; do
      printf '%s\\t%s\\n' "$1" "$2"
      shift 2
    done
    printf 'rows: %s\\n' "$rows"
''')


def make_table(rng):
    ex = scn("example", {}, Run("apples", "3", "pears", "12"))
    return ex, [scn("tables", {}, Run("a", "1"), Run("two words", "7", "-n", "0", "back\\slash", "2"), Run("x", "1", "y", "2", "z", "3")), scn("usage", {}, Run(stderr="nonempty"), Run("a"), Run("a", "1", "b"))]


# ------------------------------------------------------------------------------------------------ 8. sourcing a library

BUG_LIB = dd('''
    function banner {
      local title=$1
      echo "== $title =="
    }

    function bullet() {
      echo " * $1"
    }
''')
REF_LIB = dd('''
    banner() {
      title=$1
      echo "== $title =="
    }

    bullet() {
      echo " * $1"
    }
''')
BUG_USELIB = dd('''
    #!/bin/bash
    # report.sh TITLE ITEM... : a titled bullet list using lib.sh
    source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
    banner "$1"
    shift
    for i in "$@"; do
      bullet "$i"
    done
''')
REF_USELIB = dd('''
    #!/bin/sh
    # report.sh TITLE ITEM... : a titled bullet list using lib.sh
    [ $# -ge 1 ] || { echo "usage: report.sh TITLE ITEM..." >&2; exit 2; }
    . "$(dirname "$0")/lib.sh"
    banner "$1"
    shift
    for i in "$@"; do
      bullet "$i"
    done
''')


def make_lib(rng):
    ex = scn("example", {}, Run("Shopping", "milk", "eggs"))
    return ex, [scn("lists", {}, Run("Empty list"), Run("Two words", "a b", "*", "-n"), Run("t", "1", "2", "3")), scn("usage", {}, Run(stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 9. substring and replace

BUG_SUB = dd('''
    #!/bin/bash
    # sub.sh cut STRING START LEN   : LEN characters of STRING starting at 0-based offset START
    # sub.sh swap STRING FROM TO    : STRING with every occurrence of the literal text FROM replaced by TO
    case ${1:-} in
      cut) echo "${2:$3:$4}" ;;
      swap) echo "${2//"$3"/$4}" ;;
      *) echo "usage: sub.sh cut STRING START LEN | swap STRING FROM TO" >&2; exit 2 ;;
    esac
''')
REF_SUB = dd('''
    #!/bin/sh
    # sub.sh cut STRING START LEN   : LEN characters of STRING starting at 0-based offset START
    # sub.sh swap STRING FROM TO    : STRING with every occurrence of the literal text FROM replaced by TO
    usage() { echo "usage: sub.sh cut STRING START LEN | swap STRING FROM TO" >&2; exit 2; }
    case ${1:-} in
      cut)
        [ $# -eq 4 ] || usage
        case $3$4 in ''|*[!0-9]*) usage ;; esac
        s=$2
        skip=$3
        len=$4
        while [ "$skip" -gt 0 ] && [ -n "$s" ]; do s=${s#?}; skip=$((skip - 1)); done
        out=
        while [ "$len" -gt 0 ] && [ -n "$s" ]; do
          rest=${s#?}
          out=$out${s%"$rest"}
          s=$rest
          len=$((len - 1))
        done
        printf '%s\\n' "$out"
        ;;
      swap)
        [ $# -eq 4 ] || usage
        s=$2
        from=$3
        to=$4
        if [ -z "$from" ]; then printf '%s\\n' "$s"; exit 0; fi
        out=
        while :; do
          case $s in
            *"$from"*) out=$out${s%%"$from"*}$to; s=${s#*"$from"} ;;
            *) out=$out$s; break ;;
          esac
        done
        printf '%s\\n' "$out"
        ;;
      *) usage ;;
    esac
''')


def make_sub(rng):
    ex = scn("example", {}, Run("cut", "abcdefgh", "2", "3"), Run("swap", "a-b-c", "-", "+"))
    return ex, [scn("cut", {}, Run("cut", "abcdefgh", "0", "3"), Run("cut", "abcdefgh", "6", "10"), Run("cut", "abcdefgh", "9", "2"), Run("cut", "two words here", "4", "5"), Run("cut", "x", "0", "0"), Run("cut", "*?[a]", "1", "3"), Run("cut", "", "0", "2")),
                scn("swap", {}, Run("swap", "a.b.c", ".", "-"), Run("swap", "aaa", "aa", "b"), Run("swap", "no match", "zz", "y"), Run("swap", "x*y*z", "*", "/"), Run("swap", "a b  c", " ", ""), Run("swap", "abc", "", "X"), Run("swap", "[x]", "[x]", "&\\1"), Run("swap", "a/b", "/", "//")),
                scn("usage", {}, Run(), Run("frob", "x"), Run("cut", "abc", "1"), Run("cut", "abc", "x", "1"), Run("swap", "a", "b"))]


# ------------------------------------------------------------------------------------------------ 10. top lines with pipefail

BUG_TOP = dd('''
    #!/bin/bash
    set -o pipefail
    # topline.sh FILE : the three most frequent lines of FILE as "<count> <line>" (uniq -c style), most frequent first, ties by line
    [ -r "$1" ] || { echo "error: cannot read $1" >&2; exit 2; }
    sort -- "$1" | uniq -c | sort -k1,1nr -k2 | head -n 3
''')
REF_TOP = dd('''
    #!/bin/sh
    # topline.sh FILE : the three most frequent lines of FILE as "<count> <line>" (uniq -c style), most frequent first, ties by line
    [ $# -eq 1 ] && [ -r "$1" ] || { echo "error: usage: topline.sh FILE (readable)" >&2; exit 2; }
    LC_ALL=C sort -- "$1" | uniq -c | LC_ALL=C sort -k1,1nr -k2 | head -n 3
    exit 0
''')


def make_top(rng):
    ex = scn("example", {"l.txt": F("a\nb\na\nc\na\nb\n")}, Run("l.txt"))
    f = {"many": F("".join(f"line {i % 7}\n" * (i % 5 + 1) for i in range(40))), "ties": F("b\na\nc\nb\na\nc\nd\n"), "short": F("only\n"), "empty": F(""), "my file": F("x y\nx y\nz\n")}
    return ex, [scn("files", f, Run("many"), Run("ties"), Run("short"), Run("empty"), Run("my file")), scn("errors", f, Run("nope", stderr="nonempty"), Run(stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 11. indirect variables

BUG_ENV = dd('''
    #!/bin/bash
    # envshow.sh NAME... : print NAME=value for each environment variable, or "NAME is unset"
    for n in "$@"; do
      if [[ ! $n =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        echo "invalid name: $n" >&2
        exit 2
      fi
      if [[ -v $n ]]; then
        echo "$n=${!n}"
      else
        echo "$n is unset"
      fi
    done
''')
REF_ENV = dd('''
    #!/bin/sh
    # envshow.sh NAME... : print NAME=value for each environment variable, or "NAME is unset"
    for n in "$@"; do
      case $n in
        ''|[0-9]*|*[!A-Za-z0-9_]*) echo "invalid name: $n" >&2; exit 2 ;;
      esac
    done
    for n in "$@"; do
      eval "isset=\\${$n+yes}"
      if [ -n "$isset" ]; then
        eval "val=\\${$n}"
        printf '%s=%s\\n' "$n" "$val"
      else
        printf '%s is unset\\n' "$n"
      fi
    done
''')


def make_env(rng):
    env = {"ALPHA": "one", "EMPTY": "", "SPACY": "a  b *", "QUOTE": "it's \"x\" $HOME `id`", "_under": "u2"}
    ex = scn("example", {}, Run("ALPHA", "MISSING", env={"ALPHA": "one"}))
    return ex, [scn("values", {}, Run("ALPHA", "NOPE", "EMPTY", "SPACY", "QUOTE", "_under", env=env), Run(env=env), Run("SPACY", "SPACY", env=env)),
                scn("invalid names", {}, Run("1ST", env=env), Run("A-B", env=env), Run("ALPHA", "x y", env=env), Run("", env=env), Run("A;touch pwned", env=env))]


# ------------------------------------------------------------------------------------------------ 12. join with a separator

BUG_JOIN = dd('''
    #!/bin/bash
    # joinargs.sh SEP ITEM... : print the items joined with the single character SEP
    sep=$1
    shift
    items=("$@")
    IFS=$sep
    echo "${items[*]}"
''')
REF_JOIN = dd('''
    #!/bin/sh
    # joinargs.sh SEP ITEM... : print the items joined with the single character SEP
    [ $# -ge 1 ] || { echo "usage: joinargs.sh SEP ITEM..." >&2; exit 2; }
    sep=$1
    shift
    [ "${#sep}" -le 1 ] || { echo "error: SEP must be one character" >&2; exit 2; }
    IFS=$sep
    printf '%s\\n' "$*"
''')


def make_join(rng):
    ex = scn("example", {}, Run(",", "a", "b", "c"))
    return ex, [scn("joins", {}, Run(",", "one"), Run("-", "two words", "x*", "y"), Run(":"), Run("|", "", "", "z"), Run("/", "a", "", "b"), Run(" ", "p", "q", "r")),
                scn("errors", {}, Run(stderr="nonempty"), Run("ab", "x", "y"))]


SPECS = [
    S("posix-upper-case", 1,
      "`upper.sh` uses `${w^^}`, which dash doesn't know. Make it run under plain `sh` and keep the behaviour.",
      "`sh upper.sh WORD...` prints every argument converted to upper case (ASCII letters only), one per line. No arguments: usage message on stderr and exit status 2. The script must run with `sh` (dash): no bashisms, no re-executing bash.",
      REF_UP, make_up, script="upper.sh", shell=SH, buggy=BUG_UP, forbid=FORBID, title="Upper-casing in POSIX sh", wrong=(BUG_UP,)),
    S("posix-media-kind", 1,
      "`media.sh` classifies file names with extglob patterns and `nocasematch`. Rewrite it so it works under `sh`.",
      "`sh media.sh NAME...` prints for each name `image` (extensions jpg, jpeg, png, gif), `audio` (mp3, ogg, flac), `video` (mp4, mkv, webm) or `other`, matching the extension case-insensitively. "
      "The extension is the part after the last dot; a name that only consists of an extension (`.png`) counts as having that extension, a name without dot is `other`. Runs with `sh`; no bash.",
      REF_MEDIA, make_media, script="media.sh", shell=SH, buggy=BUG_MEDIA, forbid=FORBID, title="Classify files in POSIX sh", wrong=(BUG_MEDIA,)),
    S("posix-repeat", 1,
      "`repeat.sh` uses a C-style `for ((...))` loop that dash rejects. Port it to POSIX `sh` and add argument validation.",
      "`sh repeat.sh N TEXT` prints `TEXT` `N` times (one per line, via `printf '%s\\n'`-like exactness: backslashes are not interpreted) and then `done`. `N` must be a non-negative integer (digits only) and there must be exactly two arguments, otherwise "
      "a usage message goes to stderr and the exit status is 2 with nothing on stdout. Runs under `sh`.",
      REF_REP, make_rep, script="repeat.sh", shell=SH, buggy=BUG_REP, forbid=FORBID, title="Repeat text in POSIX sh", wrong=(BUG_REP,)),
    S("posix-sorted-args", 2,
      "`sortargs.sh` stores its arguments in a bash array. Make it work under dash, where arrays don't exist.",
      "`sh sortargs.sh ARG...` prints `count: N` (the number of arguments) and then the arguments in byte-wise sorted order (`LC_ALL=C` sorting), one per line. With no arguments only `count: 0` is printed. Arguments contain no line breaks. Runs under `sh`.",
      REF_SORT, make_sort, script="sortargs.sh", shell=SH, buggy=BUG_SORT, forbid=FORBID, title="Sorted arguments in POSIX sh", wrong=(BUG_SORT,)),
    S("posix-echo-table", 2,
      "`table.sh` prints a tab separated table with `echo -e` and `echo -n`, which behave differently (or print `-e`) under dash. Make the output identical everywhere.",
      "`sh table.sh NAME QTY [NAME QTY...]` prints the header `ITEM`, a TAB, `QTY`, then one line per pair `NAME<TAB>QTY` (the texts are printed literally: a backslash in a name stays a backslash), and finally `rows: N` with the number of pairs. "
      "An odd number of arguments or no argument at all prints a usage message on stderr and exits with status 2. Runs under `sh`.",
      REF_TABLE, make_table, script="table.sh", shell=SH, buggy=BUG_TABLE, forbid=FORBID, title="Tables without echo -e", wrong=(BUG_TABLE,)),
    S("posix-source-library", 2,
      "`report.sh` pulls helper functions from `lib.sh` with `source` and `BASH_SOURCE`, and `lib.sh` uses the `function` keyword and `local`. Make both work under `sh`.",
      "`sh report.sh TITLE ITEM...` prints `== TITLE ==` and then one line ` * ITEM` per item, using the functions `banner` and `bullet` from `lib.sh` (found next to the script, whatever the current directory is). "
      "Both files must be valid POSIX `sh`: no `function` keyword, no `source`, no `BASH_SOURCE`, no bash-only `local` (POSIX does not define it). Missing TITLE: usage message on stderr, exit status 2.",
      REF_USELIB, make_lib, script="report.sh", shell=SH, buggy=BUG_USELIB, extra={"lib.sh": BUG_LIB}, ref_extra={"lib.sh": REF_LIB}, forbid=FORBID, title="A sourced library in POSIX sh", wrong=(BUG_USELIB,)),
    S("posix-reverse-lines", 3,
      "`revlines.sh` prints a file backwards with original line numbers using `mapfile` and a C-style loop. Port it to POSIX `sh` without changing the output, edge cases included.",
      "`sh revlines.sh FILE` prints the lines of `FILE` from last to first as `N: text` where `N` is the line's original 1-based number and `text` is the line unchanged (blanks, backslashes, `*` and `$` untouched). A last line without trailing newline counts. "
      "An empty file prints nothing. A missing/unreadable file or the wrong number of arguments: usage message on stderr, exit status 2. Runs under `sh`.",
      REF_REV, make_rev, script="revlines.sh", shell=SH, buggy=BUG_REV, forbid=FORBID, title="Reverse lines in POSIX sh", wrong=(BUG_REV,)),
    S("posix-top-lines", 2,
      "`topline.sh` shows the three most frequent lines of a file but starts with `set -o pipefail`, which dash rejects. Make it run under `sh` and keep its checks.",
      "`sh topline.sh FILE` prints the three most frequent lines of `FILE` formatted as `uniq -c` does (count right-aligned in 7 columns, a space, the line), most frequent first, ties in byte-wise order of the line text; fewer lines if the file has fewer distinct lines; nothing for an empty file. "
      "A missing or unreadable file or a wrong number of arguments: message on stderr and exit status 2. Exit status 0 otherwise. Runs under `sh`.",
      REF_TOP, make_top, script="topline.sh", shell=SH, buggy=BUG_TOP, forbid=FORBID, title="Frequent lines in POSIX sh", wrong=(BUG_TOP,)),
    S("posix-substring-tools", 3,
      "`sub.sh` has two modes (substring and literal replace-all) built on bash-only parameter expansions. Reimplement it in POSIX `sh`; the README spells out the edge cases.",
      "`sh sub.sh cut STRING START LEN` prints at most `LEN` characters of `STRING` starting at the 0-based offset `START` (fewer at the end of the string, empty if `START` is beyond it). "
      "`sh sub.sh swap STRING FROM TO` prints `STRING` with **every non-overlapping occurrence, scanning left to right**, of the literal text `FROM` replaced by the literal text `TO` (no patterns, no `&` or backreferences; an empty `FROM` changes nothing). "
      "`START` and `LEN` must be digits only. Anything else (unknown mode, wrong argument count, non-numeric numbers) prints a usage message on stderr and exits 2. The tests use ASCII strings. Runs under `sh`.",
      REF_SUB, make_sub, script="sub.sh", shell=SH, buggy=BUG_SUB, forbid=FORBID, title="Substring tools in POSIX sh", wrong=(BUG_SUB,)),
    S("posix-join-with-separator", 2,
      "`joinargs.sh` joins its arguments with a separator using an array and `IFS`. Rewrite it for POSIX `sh` (dash has no arrays).",
      "`sh joinargs.sh SEP ITEM...` prints the items joined by `SEP`, which is a single character or empty (then the items are glued together). Items may be empty strings or contain spaces and glob characters. No items: an empty line. "
      "A `SEP` longer than one character, or no arguments at all: message on stderr and exit status 2. Runs under `sh`.",
      REF_JOIN, make_join, script="joinargs.sh", shell=SH, buggy=BUG_JOIN, forbid=FORBID, title="Join arguments in POSIX sh", wrong=(BUG_JOIN,)),
    S("posix-hashtag-counts", 4,
      "`tags.sh` counts hashtags in text from stdin using an associative array and `${t,,}`. Reimplement the same behaviour in POSIX `sh` with standard tools.",
      "`sh tags.sh` reads text on standard input. A *hashtag* is a whitespace-separated word consisting of `#` followed by one or more of `A-Za-z0-9_` and nothing else (`#ok-dash`, `a#b`, `#`, `##x` are not hashtags). "
      "Case is ignored: tags are lower-cased (ASCII). For each distinct tag print `<count> <tag>` (count without padding), most frequent first, ties ordered by tag byte-wise. No tags: no output. Runs under `sh`.",
      REF_TAGS, make_tags, script="tags.sh", shell=SH, buggy=BUG_TAGS, forbid=FORBID, title="Hashtag counts in POSIX sh", wrong=(BUG_TAGS,)),
    S("posix-env-lookup", 4,
      "`envshow.sh` prints environment variables by name using `[[ -v ]]` and `${!n}`. Port it to POSIX `sh` safely: no arbitrary code execution through a crafted name.",
      "`sh envshow.sh NAME...` first validates all names (a valid name matches `[A-Za-z_][A-Za-z0-9_]*`): if any is invalid it prints `invalid name: <name>` on stderr, exits with status 2 and prints nothing on stdout. "
      "Otherwise for each name in order it prints `NAME=value` (the value printed literally) if the variable is set - an empty value counts as set - or `NAME is unset`. Runs under `sh`.",
      REF_ENV, make_env, script="envshow.sh", shell=SH, buggy=BUG_ENV, forbid=FORBID, title="Variable lookup in POSIX sh", wrong=(BUG_ENV,)),
]


@family("shell-posix-portability", category="shell", lang="bash", kind="fix", n=len(SPECS),
        summary="port bash-only scripts to POSIX sh (dash): arrays, [[ ]], echo -e, process substitution, indirect expansion, pipefail")
def posix(rng, n):
    return K.shell_tasks("posix-portability", SPECS, rng, n)
