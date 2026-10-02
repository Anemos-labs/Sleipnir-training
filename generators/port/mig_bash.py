"""Port bash tools to python: the command-line contract (options, output, exit codes) must be reproduced exactly.

The bash script is the specification of last resort: the expected stdout/stderr/exit code of every hidden case is produced
by *running the script* here, and the README of each task documents the semantics the cases rely on (byte order of ``sort``,
newline handling, awk field splitting, ``getopts`` rules).
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from fx import Task, dd, family
from fx.run import write_tree

# ----------------------------------------------------------------------------------------------------------------------
# tool definitions
# ----------------------------------------------------------------------------------------------------------------------

TALLY_SH = r'''#!/bin/bash
# tally - count how often each value of one field occurs
usage() { echo "usage: tally [-d DELIM] [-f FIELD] [-n TOP] [-m MIN] [FILE...]" >&2; exit 2; }
delim=''; field=@FIELD@; top=0; min=@MIN@
while getopts ':d:f:n:m:' opt; do
  case "$opt" in
    d) delim=$OPTARG ;;
    f) field=$OPTARG ;;
    n) top=$OPTARG ;;
    m) min=$OPTARG ;;
    *) usage ;;
  esac
done
shift $((OPTIND - 1))
for v in "$field" "$top" "$min"; do
  case "$v" in ''|*[!0-9]*) echo "error: not a number: $v" >&2; exit 2 ;; esac
done
[ "$field" -ge 1 ] || { echo "error: field must be at least 1" >&2; exit 2; }
if [ -n "$delim" ]; then
  if [ "${#delim}" -ne 1 ] || [ "$delim" = ' ' ] || [ "$delim" = '\' ]; then
    echo "error: bad delimiter" >&2
    exit 2
  fi
fi
for f in "$@"; do
  [ -f "$f" ] && [ -r "$f" ] || { echo "error: cannot read: $f" >&2; exit 2; }
done
export LC_ALL=C
tab=$(printf '\t')
awk -v d="$delim" -v f="$field" '
  BEGIN { if (d != "") FS = d }
  NF >= f && $f != "" { count[$f]++ }
  END { for (k in count) printf "%d\t%s\n", count[k], k }
' "$@" | sort -t "$tab" -k1,1nr -k2,2 | awk -F "$tab" -v m="$min" -v t="$top" '
  $1 + 0 >= m + 0 { if (t + 0 == 0 || n < t + 0) { print @OUT@; n++ } }
'
'''

TALLY_PY = r'''#!/usr/bin/env python3
"""tally - count how often each value of one field occurs."""
import getopt
import os
import re
import sys

USAGE = "usage: tally [-d DELIM] [-f FIELD] [-n TOP] [-m MIN] [FILE...]"


def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(2)


def main(argv):
    try:
        opts, files = getopt.getopt(argv, "d:f:n:m:")
    except getopt.GetoptError:
        fail(USAGE)
    delim, field, top, mn = "", "@FIELD@", "0", "@MIN@"
    for o, v in opts:
        if o == "-d":
            delim = v
        elif o == "-f":
            field = v
        elif o == "-n":
            top = v
        elif o == "-m":
            mn = v
    for v in (field, top, mn):
        if not re.fullmatch(r"[0-9]+", v):
            fail("error: not a number: " + v)
    field, top, mn = int(field), int(top), int(mn)
    if field < 1:
        fail("error: field must be at least 1")
    if delim != "" and (len(delim.encode("utf-8")) != 1 or delim in "\\ "):
        fail("error: bad delimiter")
    for f in files:
        if not (os.path.isfile(f) and os.access(f, os.R_OK)):
            fail("error: cannot read: " + f)
    if files:
        chunks = []
        for f in files:
            with open(f, "rb") as fh:
                chunks.append(fh.read())
        data = b"".join(chunks)
    else:
        data = sys.stdin.buffer.read()
    text = data.decode("utf-8")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    counts = {}
    for line in lines:
        if delim:
            fields = line.split(delim) if line != "" else []
        else:
            fields = [x for x in re.split("[ \t]+", line) if x != ""]
        if len(fields) >= field and fields[field - 1] != "":
            counts[fields[field - 1]] = counts.get(fields[field - 1], 0) + 1
    rows = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].encode("utf-8")))
    out = []
    for value, n in rows:
        if n >= mn and (top == 0 or len(out) < top):
            out.append(@OUTPY@)
    sys.stdout.write("".join(line + "\n" for line in out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

TALLY_README = dd('''
    # tally

    `tally.sh` counts how often each value of one field occurs in delimited text and prints the most frequent ones. It is being replaced
    by a Python program, `tally.py`, that must behave identically: same options, same standard output byte for byte, same messages on
    standard error, same exit status. Run as `python3 tally.py [options] [FILE...]`.

    ## Command line

    `tally [-d DELIM] [-f FIELD] [-n TOP] [-m MIN] [FILE...]`

    * Options are parsed like the shell's `getopts`: `-n 3` and `-n3` are the same, `--` ends the options, parsing stops at the first argument that
      is not an option, and a later option overrides an earlier one. An unknown option or a missing option argument prints the usage line
      `usage: tally [-d DELIM] [-f FIELD] [-n TOP] [-m MIN] [FILE...]` to standard error and exits with status 2.
    * `-f FIELD` (default @FIELD@) is the 1-based field to count; `-n TOP` (default 0) limits the output to the first TOP lines (0 means no limit);
      `-m MIN` (default @MIN@) leaves out values seen fewer than MIN times. These three must be non-empty strings of ASCII digits, otherwise the
      error is `error: not a number: <value>`; a field of 0 gives `error: field must be at least 1`. (Checks happen in this order: the three
      numbers in the order field, top, min; then the field value; then the delimiter; then the files.)
    * `-d DELIM`: the field delimiter, exactly one ASCII character that is not a space and not a backslash (otherwise `error: bad delimiter`). It is used
      literally. Without `-d`, fields are separated by runs of spaces and tabs and leading/trailing blanks are ignored (a carriage return is an
      ordinary character).
    * `FILE...`: read in order and treated as one stream; without files standard input is read. A file that is not a readable regular file gives
      `error: cannot read: <file>`; nothing is printed in that case.
    * Every error exits with status 2 after printing one line to standard error; success is status 0.

    ## Input and output

    * The input is UTF-8 text. Lines end at a line feed **only**; a final line without one still counts. A `\\r` is never a line end.
    * A line contributes the value of field FIELD unless it has fewer fields or that field is empty (empty lines never count; with `-d`, a
      line `a,` has the fields `a` and an empty one).
    * Output is one line per value, @ORDER@, sorted by count, highest first, equal counts by value in **byte order** (the order `LC_ALL=C sort` gives
      for UTF-8 text). Values never contain a tab or a line feed.
''')

CSVCUT_SH = r'''#!/bin/bash
# csvcut - pick columns of a simple delimited table by header name
usage() { echo "usage: csvcut -c NAME[,NAME...] [-d CHAR] [-H] [-s]" >&2; exit 2; }
cols=''; delim='@DELIM@'; noheader=0; squeeze=0
while getopts ':c:d:Hs' opt; do
  case "$opt" in
    c) cols=$OPTARG ;;
    d) delim=$OPTARG ;;
    H) noheader=1 ;;
    s) squeeze=1 ;;
    *) usage ;;
  esac
done
shift $((OPTIND - 1))
[ $# -eq 0 ] || usage
[ -n "$cols" ] || usage
if [ "${#delim}" -ne 1 ] || [ "$delim" = ' ' ] || [ "$delim" = '\' ]; then
  echo "error: bad delimiter" >&2
  exit 2
fi
export LC_ALL=C
awk -F "$delim" -v cols="$cols" -v od="$delim" -v noheader="$noheader" -v squeeze="$squeeze" '
  BEGIN { n = split(cols, want, ",") }
  NR == 1 {
    for (i = 1; i <= NF; i++) idx[$i] = i
    for (j = 1; j <= n; j++) {
      if (!(want[j] in idx)) { print "error: no such column: " want[j] > "/dev/stderr"; failed = 1; exit 2 }
    }
    if (!noheader) {
      line = ""
      for (j = 1; j <= n; j++) line = line (j > 1 ? od : "") want[j]
      print line
    }
    next
  }
  NF == 0 { next }
  {
    line = ""; any = 0
    for (j = 1; j <= n; j++) {
      v = $(idx[want[j]])
      if (v != "") any = 1
      line = line (j > 1 ? od : "") v
    }
    if (squeeze && !any) next
    print line
  }
  END { if (!failed && NR == 0) { print "error: empty input" > "/dev/stderr"; exit 2 } }
'
'''

CSVCUT_PY = r'''#!/usr/bin/env python3
"""csvcut - pick columns of a simple delimited table by header name."""
import getopt
import sys

USAGE = "usage: csvcut -c NAME[,NAME...] [-d CHAR] [-H] [-s]"


def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(2)


def main(argv):
    try:
        opts, rest = getopt.getopt(argv, "c:d:Hs")
    except getopt.GetoptError:
        fail(USAGE)
    cols, delim, noheader, squeeze = "", "@DELIM@", False, False
    for o, v in opts:
        if o == "-c":
            cols = v
        elif o == "-d":
            delim = v
        elif o == "-H":
            noheader = True
        elif o == "-s":
            squeeze = True
    if rest or cols == "":
        fail(USAGE)
    if len(delim.encode("utf-8")) != 1 or delim in "\\ ":
        fail("error: bad delimiter")
    want = cols.split(",")
    lines = sys.stdin.buffer.read().decode("utf-8").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        fail("error: empty input")
    header = lines[0].split(delim) if lines[0] != "" else []
    idx = {}
    for i, name in enumerate(header):
        idx[name] = i
    for name in want:
        if name not in idx:
            fail("error: no such column: " + name)
    out = []
    if not noheader:
        out.append(delim.join(want))
    for line in lines[1:]:
        if line == "":
            continue
        fields = line.split(delim)
        vals = [fields[idx[name]] if idx[name] < len(fields) else "" for name in want]
        if squeeze and all(v == "" for v in vals):
            continue
        out.append(delim.join(vals))
    sys.stdout.write("".join(l + "\n" for l in out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

CSVCUT_README = dd('''
    # csvcut

    `csvcut.sh` selects columns of a simple delimited table (no quoting) by their header names. It is being replaced by `csvcut.py`, which must
    behave identically (standard output byte for byte, messages on standard error, exit status). Run as `python3 csvcut.py [options] < table`.

    ## Command line

    `csvcut -c NAME[,NAME...] [-d CHAR] [-H] [-s]`

    * Options are parsed like `getopts` (`-cname` equals `-c name`, `--` ends the options, later options override earlier ones). Positional
      arguments are not accepted. An unknown option, a missing option argument, a missing or empty `-c`, or any positional argument prints
      `usage: csvcut -c NAME[,NAME...] [-d CHAR] [-H] [-s]` to standard error and exits with status 2.
    * `-d CHAR`: the delimiter (default `@DELIM@`): exactly one ASCII character, not a space and not a backslash, otherwise `error: bad delimiter`
      (checked after the usage checks). It is used literally for reading and for writing.
    * `-H` leaves the header line out of the output. `-s` drops data rows in which every selected value is empty.
    * Errors: a requested name that is not in the header prints `error: no such column: <NAME>` (the first missing one, in `-c` order) and
      nothing else to standard output; completely empty input prints `error: empty input`. Both exit with status 2.

    ## Table rules

    * The input is UTF-8; lines end at a line feed only (a `\\r` is an ordinary character of the last field). The first line is the header; an
      empty header line has no columns.
    * Column names are matched exactly (case-sensitive). If a name occurs twice in the header, the **last** occurrence is used. `-c` may repeat a
      name; the column then appears twice in the output.
    * Output columns follow the `-c` order, joined with the delimiter; the header line is the requested names joined the same way.
    * Empty data lines are skipped. A row with fewer fields than needed gets empty values for the missing ones; extra fields are ignored.
''')

RENAME_SH = r'''#!/bin/bash
# tidynames - turn messy file names read from standard input into tidy ones
usage() { echo "usage: tidynames [-a] [-s SEP]" >&2; exit 2; }
all=0; sep='@SEP@'
while getopts ':as:' opt; do
  case "$opt" in
    a) all=1 ;;
    s) sep=$OPTARG ;;
    *) usage ;;
  esac
done
shift $((OPTIND - 1))
[ $# -eq 0 ] || usage
case "$sep" in
  _|-|.) ;;
  *) echo "error: bad separator: $sep" >&2; exit 2 ;;
esac
export LC_ALL=C
declare -A used
while IFS= read -r name || [ -n "$name" ]; do
  [ -n "$name" ] || continue
  stem=$name; ext=''
  case "$name" in
    ?*.*) stem=${name%.*}; ext=${name##*.} ;;
  esac
  stem=$(printf '%s' "$stem" | tr 'A-Z' 'a-z' | sed -e "s/[^a-z0-9][^a-z0-9]*/$sep/g" -e "s/^[$sep]//" -e "s/[$sep]\$//")
  [ -n "$stem" ] || stem=@FALLBACK@
  ext=$(printf '%s' "$ext" | tr 'A-Z' 'a-z' | tr -cd 'a-z0-9')
  new=$stem
  [ -z "$ext" ] || new=$stem.$ext
  n=1
  cand=$new
  while [ -n "${used[$cand]+x}" ]; do
    n=$((n + 1))
    cand=$stem$sep$n
    [ -z "$ext" ] || cand=$cand.$ext
  done
  used[$cand]=1
  if [ "$cand" != "$name" ]; then
    echo "$name -> $cand"
  elif [ "$all" = 1 ]; then
    echo "$name == $cand"
  fi
done
'''

RENAME_PY = r'''#!/usr/bin/env python3
"""tidynames - turn messy file names read from standard input into tidy ones."""
import getopt
import re
import sys

USAGE = "usage: tidynames [-a] [-s SEP]"
LOWER = {ord(c): ord(c) + 32 for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}


def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(2)


def main(argv):
    try:
        opts, rest = getopt.getopt(argv, "as:")
    except getopt.GetoptError:
        fail(USAGE)
    show_all, sep = False, "@SEP@"
    for o, v in opts:
        if o == "-a":
            show_all = True
        elif o == "-s":
            sep = v
    if rest:
        fail(USAGE)
    if sep not in ("_", "-", "."):
        fail("error: bad separator: " + sep)
    lines = sys.stdin.buffer.read().decode("utf-8").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    used = set()
    out = []
    for name in lines:
        if name == "":
            continue
        stem, ext = name, ""
        dot = name.rfind(".")
        if dot >= 1:
            stem, ext = name[:dot], name[dot + 1:]
        stem = re.sub("[^a-z0-9]+", sep, stem.translate(LOWER))
        if stem.startswith(sep):
            stem = stem[1:]
        if stem.endswith(sep):
            stem = stem[:-1]
        if stem == "":
            stem = "@FALLBACK@"
        ext = re.sub("[^a-z0-9]", "", ext.translate(LOWER))
        new = stem + ("." + ext if ext else "")
        n, cand = 1, new
        while cand in used:
            n += 1
            cand = stem + sep + str(n) + ("." + ext if ext else "")
        used.add(cand)
        if cand != name:
            out.append("%s -> %s" % (name, cand))
        elif show_all:
            out.append("%s == %s" % (name, cand))
    sys.stdout.write("".join(l + "\n" for l in out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

RENAME_README = dd('''
    # tidynames

    `tidynames.sh` reads file names from standard input, one per line, and prints a rename plan. It is being replaced by `tidynames.py`, which must
    behave identically (standard output byte for byte, standard error, exit status). Run as `python3 tidynames.py [options] < names`.

    ## Command line

    `tidynames [-a] [-s SEP]`

    * `getopts`-style options. `-a` also lists names that do not change. `-s SEP` sets the separator, one of `_`, `-` or `.` (default `@SEP@`), otherwise
      `error: bad separator: <SEP>` and exit status 2. Positional arguments, unknown options and a missing option argument print
      `usage: tidynames [-a] [-s SEP]` to standard error and exit with status 2 (usage problems are reported before the separator check).

    ## Rules

    The input is UTF-8; lines end at a line feed only (a final line without one counts); empty lines are skipped. For every name, in input order:

    1. **Split.** The extension is the text after the last dot, but only if at least one character precedes that dot (so `.bashrc` has no extension
       and `a.` has an empty one); the rest is the stem.
    2. **Stem.** Upper-case ASCII letters become lower case (no other character changes case). Every maximal run of characters that are not `a-z` or
       `0-9` (spaces, punctuation, every non-ASCII character, ...) becomes a single SEP. One SEP at the start and one at the end are removed. If nothing is left
       the stem is `@FALLBACK@`.
    3. **Extension.** Lower-cased the same way; every character that is not `a-z` or `0-9` is removed; if nothing is left there is no extension.
    4. **Name.** `stem` or `stem.ext`. If that name was already produced for an earlier line (or is an earlier output of this rule), insert `SEP2`, `SEP3`, ... between the stem
       and the extension (`SEP` followed by the number) with the smallest number from 2 that gives an unused name.
    5. **Output.** `<old> -> <new>` when the result differs from the original text; with `-a`, unchanged names are printed as `<old> == <new>`; otherwise they are not
       printed (but they still count as used).
''')

RETAIN_SH = r'''#!/bin/bash
# retain - decide which dated backup files to keep
usage() { echo "usage: retain [-k N] [-m]" >&2; exit 2; }
keep=@KEEP@; monthly=@MONTHLY@
while getopts ':k:m' opt; do
  case "$opt" in
    k) keep=$OPTARG ;;
    m) monthly=1 ;;
    *) usage ;;
  esac
done
shift $((OPTIND - 1))
[ $# -eq 0 ] || usage
case "$keep" in ''|*[!0-9]*) echo "error: not a number: $keep" >&2; exit 2 ;; esac
export LC_ALL=C
tab=$(printf '\t')
awk -v tab="$tab" '
  {
    name = $0
    if (match(name, /-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9](\.[A-Za-z0-9.]+)?$/)) {
      prefix = substr(name, 1, RSTART - 1)
      date = substr(name, RSTART + 1, 10)
      mo = substr(date, 6, 2) + 0
      da = substr(date, 9, 2) + 0
      if (prefix != "" && mo >= 1 && mo <= 12 && da >= 1 && da <= 31) {
        print "V" tab prefix tab date tab name tab NR
        next
      }
    }
    print "S" tab "" tab "" tab name tab NR
  }' | sort -s -t "$tab" -k1,1 -k2,2 -k3,3r -k4,4r | awk -F "$tab" -v keep="$keep" -v monthly="$monthly" -v tab="$tab" '
  $1 == "S" { print $5 tab "skip " $4; next }
  {
    if ($2 != cur || !started) { cur = $2; started = 1; rank = 0; for (m in months) delete months[m] }
    rank++
    month = substr($3, 1, 7)
    kept = (rank <= keep + 0)
    if (monthly && !(month in months)) kept = 1
    months[month] = 1
    print $5 tab (kept ? "keep " : "drop ") $4
  }
' | sort -t "$tab" -k1,1n | cut -f2-
'''

RETAIN_PY = r'''#!/usr/bin/env python3
"""retain - decide which dated backup files to keep."""
import getopt
import re
import sys

USAGE = "usage: retain [-k N] [-m]"
DATED = re.compile(r"-[0-9]{4}-[0-9]{2}-[0-9]{2}(\.[A-Za-z0-9.]+)?$")


def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(2)


def main(argv):
    try:
        opts, rest = getopt.getopt(argv, "k:m")
    except getopt.GetoptError:
        fail(USAGE)
    keep, monthly = "@KEEP@", @MONTHLYPY@
    for o, v in opts:
        if o == "-k":
            keep = v
        elif o == "-m":
            monthly = True
    if rest:
        fail(USAGE)
    if not re.fullmatch(r"[0-9]+", keep):
        fail("error: not a number: " + keep)
    keep = int(keep)
    lines = sys.stdin.buffer.read().decode("utf-8").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    decision = {}
    groups = {}
    for i, name in enumerate(lines):
        m = DATED.search(name)
        if m:
            prefix, date = name[:m.start()], name[m.start() + 1:m.start() + 11]
            mo, da = int(date[5:7]), int(date[8:10])
            if prefix != "" and 1 <= mo <= 12 and 1 <= da <= 31:
                groups.setdefault(prefix, []).append((date, name, i))
                continue
        decision[i] = "skip " + name
    for prefix, items in groups.items():
        items.sort(key=lambda t: (t[0].encode("utf-8"), t[1].encode("utf-8")), reverse=True)
        months = set()
        for rank, (date, name, i) in enumerate(items, 1):
            kept = rank <= keep
            if monthly and date[:7] not in months:
                kept = True
            months.add(date[:7])
            decision[i] = ("keep " if kept else "drop ") + name
    sys.stdout.write("".join(decision[i] + "\n" for i in range(len(lines))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

RETAIN_README = dd('''
    # retain

    `retain.sh` reads backup file names from standard input and says which to keep. It is being replaced by `retain.py`, which must behave
    identically (standard output byte for byte, standard error, exit status). Run as `python3 retain.py [options] < names`.

    ## Command line

    `retain [-k N] [-m]`

    * `getopts`-style options; `-k N` (default @KEEP@) is the number of newest backups to keep per series (digits only, otherwise `error: not a number: <N>`);
      `-m` (@MONTHDEFAULT@) also keeps the newest backup of every calendar month. Positional arguments, unknown options and a missing option argument print
      `usage: retain [-k N] [-m]` to standard error. Every error exits with status 2 and prints nothing to standard output (usage problems are reported
      before the number check).

    ## Rules

    The input is UTF-8; lines end at a line feed only. Every input line produces exactly one output line, in input order: `keep <name>`, `drop <name>` or `skip <name>`.

    * A name is a **dated backup** if it ends with `-YYYY-MM-DD` (ASCII digits) optionally followed by an extension (a dot and letters, digits and dots), using the *first*
      position from the left where such an ending starts; the text before it (the **series**) must not be empty, the month must be 01..12 and the day 01..31. Anything else
      (including empty lines) is `skip`.
    * Series are independent. Within a series order the backups by date, newest first, and equal dates by full name, in descending **byte order**. The first N are kept;
      with `-m` the first backup of each `YYYY-MM` in that order is kept too. All other backups are dropped. Names are never normalised.
''')

BUMP_SH = r'''#!/bin/bash
# bump - increase a version number
usage() { echo "usage: bump (major|minor|patch) [-p PRE] [-n] [FILE]" >&2; exit 2; }
[ $# -ge 1 ] || usage
part=$1
shift
case "$part" in major|minor|patch) ;; *) usage ;; esac
pre=''; show=0
while getopts ':p:n' opt; do
  case "$opt" in
    p) pre=$OPTARG ;;
    n) show=1 ;;
    *) usage ;;
  esac
done
shift $((OPTIND - 1))
[ $# -le 1 ] || usage
if [ $# -eq 1 ]; then
  [ -f "$1" ] && [ -r "$1" ] || { echo "error: cannot read: $1" >&2; exit 2; }
  IFS= read -r line < "$1" || true
else
  IFS= read -r line || true
fi
re='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$'
if [[ ! "$line" =~ $re ]]; then
  echo "error: not a version: $line" >&2
  exit 2
fi
major=${BASH_REMATCH[1]}; minor=${BASH_REMATCH[2]}; patch=${BASH_REMATCH[3]}
case "$part" in
  major) major=$((major + 1)); minor=0; patch=0 ;;
  minor) minor=$((minor + 1)); patch=0 ;;
  patch) patch=$((patch + 1)) ;;
esac
new=$major.$minor.$patch
if [ -n "$pre" ]; then
  [[ "$pre" =~ ^[0-9A-Za-z.-]+$ ]] || { echo "error: bad pre-release: $pre" >&2; exit 2; }
  new=$new-$pre
fi
if [ "$show" = 1 ]; then echo "$line -> $new"; else echo "$new"; fi
'''

BUMP_PY = r'''#!/usr/bin/env python3
"""bump - increase a version number."""
import getopt
import os
import re
import sys

USAGE = "usage: bump (major|minor|patch) [-p PRE] [-n] [FILE]"
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?")


def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(2)


def main(argv):
    if not argv:
        fail(USAGE)
    part, argv = argv[0], argv[1:]
    if part not in ("major", "minor", "patch"):
        fail(USAGE)
    try:
        opts, rest = getopt.getopt(argv, "p:n")
    except getopt.GetoptError:
        fail(USAGE)
    pre, show = "", False
    for o, v in opts:
        if o == "-p":
            pre = v
        elif o == "-n":
            show = True
    if len(rest) > 1:
        fail(USAGE)
    if rest:
        if not (os.path.isfile(rest[0]) and os.access(rest[0], os.R_OK)):
            fail("error: cannot read: " + rest[0])
        with open(rest[0], "rb") as fh:
            data = fh.read()
    else:
        data = sys.stdin.buffer.read()
    line = data.decode("utf-8").split("\n")[0]
    m = VERSION.fullmatch(line)
    if not m:
        fail("error: not a version: " + line)
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    new = "%d.%d.%d" % (major, minor, patch)
    if pre:
        if not re.fullmatch(r"[0-9A-Za-z.-]+", pre):
            fail("error: bad pre-release: " + pre)
        new += "-" + pre
    sys.stdout.write(("%s -> %s" % (line, new) if show else new) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

BUMP_README = dd('''
    # bump

    `bump.sh` increases a version number read from a file or standard input. It is being replaced by `bump.py`, which must behave identically (standard output
    byte for byte, standard error, exit status). Run as `python3 bump.py (major|minor|patch) [options] [FILE]`.

    ## Command line

    `bump (major|minor|patch) [-p PRE] [-n] [FILE]`

    * The first argument must be `major`, `minor` or `patch`, otherwise the usage line `usage: bump (major|minor|patch) [-p PRE] [-n] [FILE]` is printed to
      standard error and the exit status is 2. The remaining arguments are `getopts`-style options (`-p PRE`, `-n`) followed by at most one `FILE` (more than
      one, an unknown option or a missing option argument is a usage error).
    * `FILE` must be a readable regular file (`error: cannot read: <FILE>`); without it standard input is read. Only the **first line** of the input is used; a
      missing line counts as an empty one.
    * The line must be exactly `MAJOR.MINOR.PATCH` with optional `-PRERELEASE` (decimal numbers without leading zeros, pre-release made of `0-9A-Za-z.-`), otherwise
      `error: not a version: <line>` (nothing is trimmed: a trailing `\\r` or space makes it invalid). Numbers stay below 10^15.
    * `major` adds one to MAJOR and resets MINOR and PATCH to 0; `minor` adds one to MINOR and resets PATCH; `patch` adds one to PATCH. Any pre-release of the input is dropped.
      `-p PRE` appends `-PRE` to the new version (PRE must be non-empty and made of `0-9A-Za-z.-`, else `error: bad pre-release: <PRE>`; an empty `-p ""` means no pre-release).
    * Output: the new version and a line feed; with `-n` instead `<old line> -> <new version>`.
    * Every error exits with status 2 and prints nothing to standard output. Checks happen in this order: the part, option parsing, argument count, reading, the version, the pre-release.
''')

# ----------------------------------------------------------------------------------------------------------------------
# running the bash reference
# ----------------------------------------------------------------------------------------------------------------------


def run_sh(script: str, args: list, stdin: str, files: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="fxbash-") as tmp:
        write_tree(Path(tmp), files)
        Path(tmp, "tool.sh").write_text(script, encoding="utf-8")
        env = {"PATH": os.environ.get("PATH", ""), "HOME": tmp}
        p = subprocess.run(["bash", "tool.sh", *args], cwd=tmp, env=env, input=stdin.encode("utf-8"), capture_output=True, timeout=30)
        return {"code": p.returncode, "stdout": p.stdout.decode("utf-8", "replace"), "stderr": p.stderr.decode("utf-8", "replace")}


HIDDEN = dd('''
    import json
    import os
    import subprocess
    import sys
    import tempfile
    import unittest

    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    TOOL = os.path.join(ROOT, "%(tool)s.py")
    CASES = json.loads(%(cases)s)


    def run(args, stdin, files):
        with tempfile.TemporaryDirectory() as tmp:
            for name, text in files.items():
                with open(os.path.join(tmp, name), "wb") as fh:
                    fh.write(text.encode("utf-8"))
            p = subprocess.run([sys.executable, TOOL] + args, cwd=tmp, input=stdin.encode("utf-8"), capture_output=True, timeout=30,
                               env={"PATH": os.environ.get("PATH", ""), "HOME": tmp})
            return {"code": p.returncode, "stdout": p.stdout.decode("utf-8", "replace"), "stderr": p.stderr.decode("utf-8", "replace")}


    class CliTest(unittest.TestCase):
        def test_cases(self):
            bad = []
            for c in CASES:
                got = run(c["args"], c["stdin"], c["files"])
                if got != c["want"]:
                    bad.append("args=%%r stdin=%%r\\n    want %%r\\n    got  %%r" %% (c["args"], c["stdin"][:60], c["want"], got))
            self.assertEqual(bad, [], "\\n" + "\\n".join(bad[:4]))


    if __name__ == "__main__":
        unittest.main()
''')

NAMES = ["Report Final.TXT", "report-final.txt", "IMG_0001.JPG", "img 0001.jpg", "  spaced name .md", "café menu.PDF", "中文.txt", "notes", "Notes", ".bashrc", "..hidden.Cfg", "a.", "A..b", "x.tar.GZ", "X.TAR.gz",
         "!!!.txt", "___", "-lead-.dat", "multi   space   file.log", "UPPER.CASE.NAME.txt", "tilde~backup~", "data (1).csv", "data (2).csv", "data.csv", "ok_already.txt", "weird\\name.bin", "a/b/c.txt"]


def _tally_cases(rng, field_default):
    words = ["alpha", "beta", "gamma", "delta", "eps", "zeta", "éclair", "über", "ok", "Zed", "10", "9", "alpha"]
    logs = []
    for _ in range(14):
        logs.append(" ".join([rng.choice(words) for _ in range(rng.randint(1, 5))]))
    logs += ["", "   leading blanks here", "tab\tseparated\tvalue", "trailing blank   ", "x\r", "x \r"]
    stdin1 = "\n".join(logs) + "\n"
    csv = "\n".join(",".join(rng.choice(words + ["", "c d"]) for _ in range(rng.randint(1, 4))) for _ in range(15)) + "\n"
    cases = [
        ([], stdin1, {}), (["-f", "2"], stdin1, {}), (["-f", "3", "-n", "2"], stdin1, {}), (["-m", "2"], stdin1, {}), (["-f", "1", "-m", "3", "-n", "1"], stdin1, {}), (["-n2"], stdin1, {}), (["-f1", "-n", "0"], stdin1, {}),
        (["-d", ",", "-f", "2"], csv, {}), (["-d", ",", "-f", "1", "-m", "2"], csv, {}), (["-d", ",", "-f", "9"], csv, {}), (["-d", ",", "-f", "3", "-n", "3"], csv, {}), (["-d", ";"], "a;b\nc;d\na;z\n;q\n", {}),
        (["-d", "|", "-f", "2"], "x|a\ny|b\nz|a\nw|\n", {}), (["-d", ".", "-f", "2"], "x.a\ny.b\nz.a\n", {}), (["-d", "\t"], "a\tb\nc\td\na\tz\n", {}),
        ([], "no newline at end", {}), ([], "", {}), ([], "\n\n\n", {}), (["-f", "2"], "a b\r\nc d\r\ne\r\n", {}), ([], "a\r\nb\r\na\r\n", {}), ([], "b\na\nB\né\nz\n中\nA\n", {}),
        (["-f", "1", "a.txt", "b.txt"], "ignored\n", {"a.txt": "one two\none three\n", "b.txt": "two two\none\n"}), (["a.txt"], "ignored\n", {"a.txt": "x\nx\ny"}), (["-f", "2", "a.txt", "empty.txt"], "", {"a.txt": "p q\nr q\n", "empty.txt": ""}),
        (["nope.txt"], "", {}), (["a.txt", "nope.txt"], "", {"a.txt": "x\n"}), (["-d", "ab"], "x\n", {}), (["-d", " "], "x\n", {}), (["-d", "\\"], "x\n", {}), (["-f", "0"], "x\n", {}), (["-f", "x"], "x\n", {}), (["-f", "-2"], "x\n", {}),
        (["-n", ""], "x\n", {}), (["-m", "1.5"], "x\n", {}), (["-z"], "x\n", {}), (["-f"], "x\n", {}), (["--", "a.txt"], "", {"a.txt": "q\nq\n"}), (["a.txt", "-f", "2"], "", {"a.txt": "q w\n"}), (["-f", "2", "-f", "1"], "k l\nk m\n", {}),
        (["-n", "007", "-m", "01"], stdin1, {}), (["-d", "", "-f", "2"], "a b\nc b\n", {}),
    ]
    return [{"args": a, "stdin": s, "files": f} for a, s, f in cases]


def _csv_cases(rng, delim):
    d = delim
    table = d.join(["id", "name", "city", "score"]) + "\n" + "\n".join(d.join([str(i), rng.choice(["ann", "bob", "café", ""]), rng.choice(["Oslo", "Rome", ""]), rng.choice(["", "7", "12"])]) for i in range(1, 9)) + "\n"
    table += "\n" + d.join(["9", "short"]) + "\n" + d.join(["10", "long", "X", "1", "extra", "more"]) + "\n"
    dup = d.join(["a", "b", "a"]) + "\n" + d.join(["1", "2", "3"]) + "\n"
    cases = [
        (["-c", "name"], table), (["-c", "name,id"], table), (["-c", "score,score"], table), (["-c", "city", "-H"], table), (["-c", "name,city", "-s"], table), (["-c", "score", "-s", "-H"], table),
        (["-c", "id,city,name,score"], table), (["-cname"], table), (["-c", "a"], dup), (["-c", "a,b"], dup), (["-c", "nothing"], table), (["-c", "name,nothing,zzz"], table), (["-c", "Name"], table), (["-c", "name"], ""),
        (["-c", "x"], "\n"), (["-c", "x"], "x\n"), (["-c", "x", "-H"], "x\n"), (["-c", "x"], "x\r\n1\r\n"), (["-c", "x"], "y" + d + "x\n1" + d + "2\n3\n"), (["-c", "y"], "x" + d + "y\n" + "1\n" + "\n" + "2" + d + "\n"), (["-c", "y", "-s"], "x" + d + "y\n" + "1\n" + "2" + d + "\n3" + d + "4\n"),
        ([], table), (["-c", ""], table), (["-d", "x"], table), (["-c", "name", "extra"], table), (["-c", "name", "-z"], table), (["-c"], table), (["-c", "name", "-d", ""], table), (["-c", "name", "-d", " "], table), (["-c", "name", "-d", "\\"], table),
        (["-c", "name", "-d", "ab"], table), (["-c", "name", "--", "x"], table), (["--", "-c", "name"], table), (["-c", "a", "-c", "b"], dup),
        (["-c", "b,a", "-d", ";"], "a;b\n1;2\n"), (["-c", "b,a", "-d", "|"], "a|b\n1|2\n3|4\n"), (["-c", "b", "-d", "\t"], "a\tb\n1\t2\n"), (["-c", "b", "-d", "."], "a.b\n1.2\n"),
        (["-c", "name"], d.join(["name", "n"]) + "\n" + "xé" + d + "1\n" + "中文" + d + "2\n"),
    ]
    return [{"args": a, "stdin": s, "files": {}} for a, s in cases]


def _rename_cases(rng):
    base = "\n".join(NAMES) + "\n"
    sub = ["\n".join(rng.sample(NAMES, rng.randint(3, 12))) + "\n" for _ in range(6)]
    cases = [([], base), (["-a"], base), (["-s", "-"], base), (["-s", ".", "-a"], base), (["-s", "_"], base), (["-a", "-s", "-"], base), ([], ""), ([], "\n\n"), ([], "single"), ([], "x.txt\nX.TXT\nx.Txt\nx_2.txt\nx.txt\n"),
             ([], "a b.txt\na_b.txt\na-b.txt\na.b.txt\n"), (["-s", "-"], "a b.txt\na_b.txt\na-b.txt\na.b.txt\n"), ([], "report\nreport\nreport_2\nreport\n"), ([], "..\n.\n...\n-\n"), ([], "name.\nname..\nname.txt.\n"),
             ([], "no newline at end"), (["-a"], "already_tidy.txt\nAlready Tidy.txt\n"), (["-s", ";"], base), (["-s", "--"], base), (["-s", "ab"], base), (["-s", ""], base), (["-s"], base), (["-x"], base), (["extra"], base), (["-a", "extra"], base),
             ([], "CaféÉ.TXT\nnaïve.txt\nüöä.md\n"), ([], "x.éè\nfile.tést\n"), ([], "A.B.C.D\n"), ([], "UPPER\nupper\nUpper\n")]
    cases += [([], s) for s in sub] + [(["-a"], s) for s in sub[:2]]
    return [{"args": a, "stdin": s, "files": {}} for a, s in cases]


def _retain_cases(rng):
    def names(prefix, ext, n, start):
        out = []
        for i in range(n):
            m = 1 + (start + i * 3) % 12
            dday = 1 + (start + i * 7) % 28
            out.append(f"{prefix}-{2023 + (start + i) // 12:04d}-{m:02d}-{dday:02d}{ext}")
        return out
    a = names("db", ".tar.gz", 9, 0)
    b = names("logs", ".zip", 5, 2)
    mixed = a + ["notes.txt", "db-2024-13-01.tar", "db-2024-00-10.tar", "db-2024-05-32.tar", "-2024-05-05.tar", "db-2024-5-5.tar", "", "db-2024-05-05", "db-2024-05-05.tar.gz", "db-2024-05-05.TAR"] + b
    rng.shuffle(mixed)
    cases = [
        ([], "\n".join(a) + "\n"), (["-m"], "\n".join(a) + "\n"), (["-k", "1"], "\n".join(a) + "\n"), (["-k", "1", "-m"], "\n".join(a) + "\n"), (["-k", "0"], "\n".join(a) + "\n"), (["-k", "0", "-m"], "\n".join(a) + "\n"), (["-k", "100"], "\n".join(a) + "\n"),
        (["-k", "2"], "\n".join(mixed) + "\n"), (["-k", "2", "-m"], "\n".join(mixed) + "\n"), ([], "\n".join(mixed) + "\n"), ([], ""), ([], "\n"), ([], "only-2024-01-01.tar\n"), ([], "a-2024-01-01.tar\na-2024-01-01.zip\na-2024-01-01.bz2\n"),
        (["-k", "1"], "a-2024-01-01.tar\na-2024-01-01.zip\na-2024-01-01.bz2\n"), (["-k", "2", "-m"], "x-2024-03-01\nx-2024-03-15\nx-2024-02-20\nx-2023-03-31\nx-2024-03-02\n"), (["-k", "1"], "x-2024-03-01\ny-2024-03-01\nx-2024-03-02\ny-2024-02-01\n"),
        (["-k", "1", "-m"], "x-2024-03-01\ny-2024-03-01\nx-2024-03-02\ny-2024-02-01\n"), (["-k", "2"], "a-b-2024-01-01.tar\na-2024-01-02.tar\na-b-2024-01-03.tar\n"), ([], "x-2024-01-01-2024-02-02.tar\n"), ([], "x-1999-12-31\nx-2000-01-01\nx-2000-01-02\nx-1999-11-30\n"),
        (["-k", "x"], "a\n"), (["-k", ""], "a\n"), (["-k", "-1"], "a\n"), (["-k"], "a\n"), (["-z"], "a\n"), (["extra"], "a\n"), (["-k", "1", "extra"], "a\n"), (["-k", "1.0"], "a\n"), (["-k", "007"], "\n".join(a) + "\n"),
        (["-m", "-k", "1", "-k", "2"], "\n".join(a) + "\n"), ([], "d-2024-02-29.t\nd-2024-02-30.t\nd-2024-04-31.t\n"), ([], "café-2024-01-01.tar\ncafé-2024-01-02.tar\né-2024-01-03\n"),
    ]
    return [{"args": a_, "stdin": s, "files": {}} for a_, s in cases]


def _bump_cases(rng):
    vers = ["1.2.3", "0.0.0", "0.9.9", "10.20.30", "1.2.3-rc1", "1.2.3-beta.2", "2.0.0-0", "1.2.3-", "01.2.3", "1.02.3", "1.2.03", "1.2", "1.2.3.4", "v1.2.3", " 1.2.3", "1.2.3 ", "1.2.3\r", "", "x", "1.2.3-a_b", "999999999999.0.1", "1.2.3-A-b.C", "0.1.0+build"]
    cases = []
    for v in vers:
        for part in ["major", "minor", "patch"]:
            if rng.random() < 0.45:
                cases.append(([part], v + "\n", {}))
    cases += [(["patch"], "1.2.3", {}), (["patch"], "1.2.3\nsecond line\n", {}), (["patch"], "\n1.2.3\n", {}), (["minor", "-p", "rc1"], "1.2.3\n", {}), (["major", "-p", "beta.1", "-n"], "1.9.9-rc\n", {}), (["patch", "-n"], "0.0.1\n", {}),
              (["patch", "-p", ""], "1.0.0\n", {}), (["patch", "-p", "bad pre"], "1.0.0\n", {}), (["patch", "-p", "a_b"], "1.0.0\n", {}), (["patch", "-p"], "1.0.0\n", {}), (["patch", "-z"], "1.0.0\n", {}), (["patch", "-pX", "-n"], "1.0.0-old\n", {}),
              (["huge"], "1.0.0\n", {}), ([], "1.0.0\n", {}), (["MAJOR"], "1.0.0\n", {}), (["patch", "ver.txt"], "", {"ver.txt": "3.4.5\n"}), (["patch", "-n", "ver.txt"], "ignored 1.1.1\n", {"ver.txt": "3.4.5-x\nmore\n"}), (["patch", "missing.txt"], "", {}),
              (["patch", "a.txt", "b.txt"], "", {"a.txt": "1.0.0\n", "b.txt": "1.0.0\n"}), (["patch", "ver.txt"], "", {"ver.txt": ""}), (["patch", "ver.txt"], "", {"ver.txt": "1.0.0"}), (["minor", "--", "ver.txt"], "", {"ver.txt": "1.2.3\n"}),
              (["patch", "-p", "r", "-p", "s"], "1.0.0\n", {}), (["patch", "-n", "-n"], "1.0.0\n", {}), (["patch", "-p", "-"], "1.0.0\n", {}), (["patch", "-p", "."], "1.0.0\n", {})]
    return [{"args": a, "stdin": s, "files": f} for a, s, f in cases]


TOOLS = {
    "tally": dict(sh=TALLY_SH, py=TALLY_PY, readme=TALLY_README, difficulty=3),
    "csvcut": dict(sh=CSVCUT_SH, py=CSVCUT_PY, readme=CSVCUT_README, difficulty=3),
    "tidynames": dict(sh=RENAME_SH, py=RENAME_PY, readme=RENAME_README, difficulty=4),
    "retain": dict(sh=RETAIN_SH, py=RETAIN_PY, readme=RETAIN_README, difficulty=4),
    "bump": dict(sh=BUMP_SH, py=BUMP_PY, readme=BUMP_README, difficulty=2),
}


def _fill(text, subs):
    for k, v in subs.items():
        text = text.replace("@" + k + "@", v)
    return text


@family("port-bash-to-python", category="port", lang="python", kind="greenfield", n=8,
        summary="reimplement a bash/awk/sort tool in python with an identical command-line contract")
def gen_bash(rng, n):
    plan = [
        ("tally", dict(FIELD="1", MIN="1", OUT='$2 "\\t" $1', OUTPY='value + "\\t" + str(n)', ORDER="`<value><TAB><count>`")),
        ("csvcut", dict(DELIM=",")),
        ("bump", dict()),
        ("tidynames", dict(SEP="_", FALLBACK="unnamed")),
        ("tally", dict(FIELD="2", MIN="2", OUT='$1 " " $2', OUTPY='str(n) + " " + value', ORDER="`<count><space><value>`")),
        ("retain", dict(KEEP="3", MONTHLY="0", MONTHLYPY="False", MONTHDEFAULT="off unless given")),
        ("csvcut", dict(DELIM=";")),
        ("tidynames", dict(SEP="-", FALLBACK="item")),
    ]
    prompts = [
        "`{tool}.sh` is a small shell tool we want to retire. Port it to Python as `{tool}.py` in the repository root: same options, same output, same messages and exit codes. README.md documents the contract (including the places where bash, awk and sort behave in ways you might not expect).",
        "rewrite {tool}.sh in python ({tool}.py). It has to be a drop-in replacement: identical stdout, stderr and exit status for every input, options parsed the getopts way. The README spells out the rules. Hidden cases exercise the error paths too.",
        "Ticket: replace the bash implementation of `{tool}` by `{tool}.py`. Acceptance: for any invocation the Python program prints exactly what the script printed (stdout and stderr) and exits with the same status; see README.md for the contract. Standard library only.",
        "We can't ship bash on the new appliance. Please translate `{tool}.sh` to `{tool}.py` (run as `python3 {tool}.py ...`). Keep the behaviour byte-for-byte; README.md lists the details that matter, e.g. how lines are split and how sorting is ordered.",
    ]
    for i in range(n):
        tool, subs = plan[i % len(plan)]
        t = TOOLS[tool]
        sh = _fill(t["sh"], subs)
        py = _fill(t["py"], subs)
        readme = _fill(t["readme"], subs)
        if tool == "tally":
            cases = _tally_cases(rng, subs["FIELD"])
        elif tool == "csvcut":
            cases = _csv_cases(rng, subs["DELIM"])
        elif tool == "tidynames":
            cases = _rename_cases(rng)
        elif tool == "retain":
            cases = _retain_cases(rng)
        else:
            cases = _bump_cases(rng)
        for c in cases:
            c["want"] = run_sh(sh, c["args"], c["stdin"], c["files"])
        # sanity: the cases must exercise success and failure, and the python reference must agree
        codes = {c["want"]["code"] for c in cases}
        if codes != {0, 2}:
            raise RuntimeError(f"{tool}: exit codes seen {codes}")
        py_cases = json.dumps(cases, ensure_ascii=True)
        hidden = HIDDEN % dict(tool=tool, cases=repr(py_cases))
        vis = [c for c in cases if c["want"]["code"] == 0][:3] + [c for c in cases if c["want"]["code"] == 2][:1]
        visible = HIDDEN % dict(tool=tool, cases=repr(json.dumps(vis, ensure_ascii=True)))
        d = t["difficulty"]
        yield Task(
            slug=f"{i + 1:02d}-{tool}",
            prompt=rng.choice(prompts).format(tool=tool),
            difficulty=d,
            lang="python",
            kind="greenfield",
            start={f"{tool}.sh": sh, "README.md": readme, "tests/test_examples.py": visible},
            hidden={"tests/test_cli.py": hidden},
            solution={f"{tool}.py": py},
            verify="python3 -m unittest discover -s tests -v",
            tags=["port", "bash-to-python", "cli", tool],
            notes={"tool": tool, "cases": len(cases)},
        )
