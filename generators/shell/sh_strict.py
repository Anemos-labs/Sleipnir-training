"""Shell tasks: repairing scripts that break under `set -euo pipefail` (grep -c, ((n++)), unset variables, SIGPIPE, local masking, traps, subshell counters)."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec

# ------------------------------------------------------------------------------------------------ 1. changed.sh

BUG_CHANGED = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # changed.sh A B : say whether two files differ
    diff -q "$1" "$2" >/dev/null
    echo same
''')
REF_CHANGED = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # changed.sh A B : say whether two files differ
    [ $# -eq 2 ] || { echo "usage: changed.sh A B" >&2; exit 2; }
    for f in "$1" "$2"; do
      [ -r "$f" ] || { echo "error: cannot read $f" >&2; exit 2; }
    done
    if diff -q -- "$1" "$2" >/dev/null; then
      echo same
    else
      echo changed
      exit 1
    fi
''')


def make_changed(rng):
    ex = scn("example", {"a.txt": F("1\n"), "b.txt": F("2\n")}, Run("a.txt", "b.txt"))
    f = {"one file": F("x\n"), "-two": F("x\n"), "three": F("y\n"), "empty": F("")}
    return ex, [scn("same and different", f, Run("one file", "-two"), Run("one file", "three"), Run("empty", "empty"), Run("empty", "three")),
                scn("errors", f, Run("one file", "nope", stderr="nonempty"), Run("nope", "one file"), Run("one file"), Run())]


# ------------------------------------------------------------------------------------------------ 2. count-errors

BUG_COUNT = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # count-errors.sh FILE : how many lines mention ERROR
    file=${1:?usage: count-errors.sh FILE}
    n=$(grep -c ERROR "$file")
    echo "errors: $n"
''')
REF_COUNT = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # count-errors.sh FILE : how many lines mention ERROR
    [ $# -eq 1 ] || { echo "usage: count-errors.sh FILE" >&2; exit 2; }
    file=$1
    [ -r "$file" ] || { echo "error: cannot read $file" >&2; exit 2; }
    n=$(grep -c ERROR -- "$file" || true)
    echo "errors: $n"
''')


def make_count(rng):
    ex = scn("example", {"app.log": F("ok\nERROR disk\nok\nERROR net\n")}, Run("app.log"))
    f = {"my log.txt": F("ERROR a\nERROR b\nERRORS c\nerror d\nfine\n"), "-clean": F("all good\nstill good\n"), "empty": F(""), "no newline": F("x\nERROR")}
    return ex, [scn("counts", f, Run("my log.txt"), Run("-clean"), Run("empty"), Run("no newline")), scn("errors", f, Run("missing", stderr="nonempty"), Run(), Run("my log.txt", "extra", stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 3. sum-sizes

BUG_SUM = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # sum-sizes.sh [DIR] : number of regular files directly in DIR and their total size
    dir=${1:-.}
    n=0
    bytes=0
    for f in "$dir"/*; do
      [ -f "$f" ] || continue
      ((n++))
      bytes=$((bytes + $(stat -c %s -- "$f")))
    done
    echo "files: $n, bytes: $bytes"
''')
REF_SUM = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # sum-sizes.sh [DIR] : number of regular files directly in DIR and their total size
    dir=${1:-.}
    n=0
    bytes=0
    for f in "$dir"/*; do
      [ -f "$f" ] || continue
      n=$((n + 1))
      bytes=$((bytes + $(stat -c %s -- "$f")))
    done
    echo "files: $n, bytes: $bytes"
''')


def make_sum(rng):
    ex = scn("example", {"a": F("12345"), "b c": F("xy")}, Run("."))
    f = {"d/one": F("x" * 10), "d/two words": F("y" * 25), "d/-dash": F(""), "d/sub/inner": F("zzz"), "d/.hidden": F("h" * 5), "e/only dir/x": F("1")}
    return ex, [scn("counts", f, Run("d"), Run("e"), Run("d/sub"), Run()), scn("empty directory", {"d": D()}, Run("d"))]


# ------------------------------------------------------------------------------------------------ 4. backup-name

BUG_NAME = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # backup-name.sh [PREFIX] : name of today's backup archive, PREFIX-STAMP.tar
    prefix=$1
    echo "$prefix-$STAMP.tar"
''')
REF_NAME = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # backup-name.sh [PREFIX] : name of today's backup archive, PREFIX-STAMP.tar
    prefix=${1:-backup}
    [ -n "$prefix" ] || prefix=backup
    if [ -z "${STAMP:-}" ]; then
      echo "STAMP is not set" >&2
      exit 3
    fi
    echo "$prefix-$STAMP.tar"
''')


def make_name(rng):
    ex = scn("example", {}, Run("home", env={"STAMP": "2031-05-04"}))
    return ex, [scn("names", {}, Run(env={"STAMP": "2031-05-04"}), Run("my docs", env={"STAMP": "20310504T1200"}), Run("", env={"STAMP": "x"}), Run("-weird", env={"STAMP": "1"}), Run("a/b", env={"STAMP": "s s"})),
                scn("no stamp", {}, Run("x", stderr="nonempty"), Run(env={"STAMP": ""}), Run("x", "y", env={"STAMP": "ok"}))]


# ------------------------------------------------------------------------------------------------ 5. numbered lines

BUG_NUM = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # numbered.sh FILE : print the lines of FILE as "N: text", exactly as they are
    n=0
    while read line; do
      n=$((n+1))
      echo "$n: $line"
    done < "$1"
''')
REF_NUM = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # numbered.sh FILE : print the lines of FILE as "N: text", exactly as they are
    [ $# -eq 1 ] && [ -r "$1" ] || { echo "usage: numbered.sh FILE" >&2; exit 2; }
    n=0
    while IFS= read -r line || [ -n "$line" ]; do
      n=$((n + 1))
      printf '%d: %s\\n' "$n" "$line"
    done < "$1"
''')


def make_num(rng):
    ex = scn("example", {"t.txt": F("alpha\n  indented\nlast")}, Run("t.txt"))
    f = {"plain": F("a\nb\nc\n"), "indent and slash": F("  two spaces\n\ttab\nback\\slash \\n literal\n*star*\n"), "no newline": F("x\ny"), "empty": F(""), "blank lines": F("\n\nx\n\n"),
         "-dash": F("-n\n-e x\n")}
    return ex, [scn("files", f, Run("plain"), Run("indent and slash"), Run("no newline"), Run("empty"), Run("blank lines"), Run("-dash")),
                scn("errors", f, Run("nope", stderr="nonempty"), Run(), Run("plain", "empty"))]


# ------------------------------------------------------------------------------------------------ 6. first word (SIGPIPE)

BUG_FIRST = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # firstword.sh : first word of the first non-empty line of standard input
    cat | grep -v '^[[:space:]]*$' | head -n 1 | awk '{print $1}'
''')
REF_FIRST = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # firstword.sh : first word of the first non-empty line of standard input
    out=$(awk 'NF { print $1; exit }')
    [ -n "$out" ] || exit 1
    printf '%s\\n' "$out"
''')


def make_first(rng):
    ex = scn("example", {}, Run(stdin="\n  hello world\nsecond\n"))
    big = "".join(f"line number {i} with some padding text to fill the pipe\n" for i in range(2800))
    return ex, [scn("small input", {}, Run(stdin="\n\n  alpha beta\ngamma\n"), Run(stdin="single"), Run(stdin="\t tabbed word\n"), Run(stdin="  \n\n")),
                scn("big input", {}, Run(stdin="\n" * 2000 + "after blanks here\n" + big))]


# ------------------------------------------------------------------------------------------------ 7. report (local masking)

BUG_REPORT = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # report.sh FILE... : "FILE: N bytes" for each file; stop at the first one that cannot be read
    report() {
      local size=$(stat -c %s "$1")
      echo "$1: $size bytes"
    }
    for f in "$@"; do
      report "$f"
    done
''')
REF_REPORT = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # report.sh FILE... : "FILE: N bytes" for each file; stop at the first one that cannot be read
    [ $# -gt 0 ] || { echo "usage: report.sh FILE..." >&2; exit 2; }
    report() {
      local size
      size=$(stat -c %s -- "$1")
      echo "$1: $size bytes"
    }
    for f in "$@"; do
      report "$f"
    done
''')


def make_report(rng):
    ex = scn("example", {"a.bin": F("x" * 12), "b c.bin": F("")}, Run("a.bin", "b c.bin"))
    f = {"one": F("x" * 7), "two words": F("y" * 20), "-dash": F("z"), "d": D()}
    return ex, [scn("readable files", f, Run("one", "two words", "./-dash"), Run("one")),
                scn("stops at the first unreadable file", f, Run("one", "missing", "two words", stderr="nonempty"), Run("missing", "one"), Run("nope")),
                scn("usage", f, Run(stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 8. cleanup trap

BUG_CLEAN = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # listing.sh DIR : print the sorted names of the entries of DIR, using a scratch directory
    trap 'rm -rf "$tmp"' EXIT
    usage() { echo "usage: listing.sh DIR" >&2; exit 2; }
    [ $# -eq 1 ] || usage
    [ -d "$1" ] || { echo "error: not a directory: $1" >&2; exit 2; }
    tmp=$(mktemp -d)
    ls -A -- "$1" > "$tmp/names"
    LC_ALL=C sort "$tmp/names"
''')
REF_CLEAN = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # listing.sh DIR : print the sorted names of the entries of DIR, using a scratch directory
    tmp=
    trap '[ -z "$tmp" ] || rm -rf -- "$tmp"' EXIT
    usage() { echo "usage: listing.sh DIR" >&2; exit 2; }
    [ $# -eq 1 ] || usage
    [ -d "$1" ] || { echo "error: not a directory: $1" >&2; exit 2; }
    tmp=$(mktemp -d)
    ls -A -- "$1" > "$tmp/names"
    LC_ALL=C sort "$tmp/names"
''')


def make_clean(rng):
    env = {"TMPDIR": "./scratch"}
    ex = scn("example", {"scratch": D(), "d/b": F("1"), "d/a": F("2"), "d/.c": F("3")}, Run("d", env=env))
    return ex, [scn("listing leaves no scratch files", {"scratch": D(), "d/b file": F("1"), "d/A": F("2"), "d/-x": F("3"), "d/.hidden": F("4"), "d/sub/in": F("5")}, Run("d", env=env), Run("d/sub", env=env)),
                scn("usage errors still exit 2", {"scratch": D(), "f": F("x")}, Run(env=env, stderr="nonempty"), Run("f", env=env, stderr="nonempty"), Run("nope", env=env), Run("a", "b", env=env))]


# ------------------------------------------------------------------------------------------------ 9. subshell counter

BUG_TREE = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # treelines.sh DIR : total number of newline characters in all *.txt files below DIR
    total=0
    find "$1" -name '*.txt' | while read -r f; do
      total=$((total + $(wc -l < "$f")))
    done
    echo "total: $total"
''')
REF_TREE = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # treelines.sh DIR : total number of newline characters in all *.txt files below DIR
    [ $# -eq 1 ] && [ -d "$1" ] || { echo "usage: treelines.sh DIR" >&2; exit 2; }
    total=0
    while IFS= read -r -d '' f; do
      total=$((total + $(wc -l < "$f")))
    done < <(find "$1" -type f -name '*.txt' -print0)
    echo "total: $total"
''')


def make_tree(rng):
    ex = scn("example", {"d/a.txt": F("1\n2\n"), "d/sub/b.txt": F("x\n")}, Run("d"))
    f = {"d/one.txt": F("a\nb\nc\n"), "d/two words.txt": F("x\n"), "d/sub dir/-dash.txt": F("1\n2\n3\n4\n"), "d/sub dir/deep/new\nline.txt": F("p\nq\n"), "d/.hidden.txt": F("h\n"),
         "d/skip.TXT": F("no\nno\n"), "d/skip.txt.bak": F("no\n"), "d/nonl.txt": F("last line without newline"), "d/ünï.txt": F("1\n2\n"), "e/none.dat": F("x\n")}
    return ex, [scn("totals", f, Run("d"), Run("e"), Run("d/sub dir")), scn("errors", f, Run(stderr="nonempty"), Run("nope", stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 10. lookup with unset keys

BUG_LOOKUP = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # total.sh ITEM... : sum of the prices of the items
    declare -A price=([apple]=3 [pear]=4 [fig]=9 ["dragon fruit"]=12)
    total=0
    for k in "$@"; do
      total=$((total + ${price[$k]}))
    done
    echo "total: $total"
''')
REF_LOOKUP = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # total.sh ITEM... : sum of the prices of the items
    declare -A price=([apple]=3 [pear]=4 [fig]=9 ["dragon fruit"]=12)
    total=0
    unknown=0
    for k in "$@"; do
      if [[ -v "price[$k]" ]]; then
        total=$((total + price[$k]))
      else
        echo "unknown: $k" >&2
        unknown=1
      fi
    done
    echo "total: $total"
    exit "$unknown"
''')


def make_lookup(rng):
    ex = scn("example", {}, Run("apple", "fig", "apple"))
    return ex, [scn("known items", {}, Run(), Run("pear"), Run("dragon fruit", "fig", "pear", "pear")),
                scn("unknown items", {}, Run("kiwi", stderr="nonempty"), Run("apple", "banana split", "fig", stderr="nonempty"), Run("", "pear"), Run("Apple", "Fig"))]


# ------------------------------------------------------------------------------------------------ 11. digest (several traps in one script)

BUG_DIGEST = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # digest.sh FILE [TOP] : summary of an application log. Lines look like "DATE TIME LEVEL message".
    file=$1
    top=$2
    lines=$(wc -l < "$file")
    errors=$(grep -c ' ERROR ' "$file")
    warns=$(grep -c ' WARN ' "$file")
    i=0
    while read -r date time level msg; do
      ((i++))
    done < "$file"
    echo "lines: $lines"
    echo "errors: $errors"
    echo "warnings: $warns"
    echo "top errors:"
    grep ' ERROR ' "$file" | cut -d' ' -f4- | sort | uniq -c | sort -k1,1nr -k2 | head -n "$top"
''')
REF_DIGEST = dd('''
    #!/usr/bin/env bash
    set -euo pipefail
    # digest.sh FILE [TOP] : summary of an application log. Lines look like "DATE TIME LEVEL message".
    [ $# -ge 1 ] && [ $# -le 2 ] || { echo "usage: digest.sh FILE [TOP]" >&2; exit 2; }
    file=$1
    top=${2:-3}
    [ -r "$file" ] || { echo "error: cannot read $file" >&2; exit 2; }
    case $top in ''|*[!0-9]*|0) echo "error: TOP must be a positive integer" >&2; exit 2 ;; esac
    lines=$(wc -l < "$file")
    errors=$(grep -c ' ERROR ' "$file" || true)
    warns=$(grep -c ' WARN ' "$file" || true)
    echo "lines: $lines"
    echo "errors: $errors"
    echo "warnings: $warns"
    echo "top errors:"
    if [ "$errors" -eq 0 ]; then
      echo "(none)"
    else
      grep ' ERROR ' "$file" | cut -d' ' -f4- | LC_ALL=C sort | uniq -c | LC_ALL=C sort -k1,1nr -k2 > "${TMPDIR:-/tmp}/digest.$$"
      head -n "$top" "${TMPDIR:-/tmp}/digest.$$"
      rm -f "${TMPDIR:-/tmp}/digest.$$"
    fi
''')


def make_digest(rng):
    import random
    r = random.Random(5)
    ex = scn("example", {"app.log": F("2031-01-01 10:00:00 INFO start\n2031-01-01 10:00:01 ERROR db down\n2031-01-01 10:00:02 WARN slow\n2031-01-01 10:00:03 ERROR db down\n2031-01-01 10:00:04 ERROR disk full\n")}, Run("app.log"))
    small = "".join(f"2031-01-02 09:00:{i:02d} {lvl} {msg}\n" for i, (lvl, msg) in enumerate([("INFO", "up"), ("ERROR", "timeout talking to db"), ("ERROR", "timeout talking to db"), ("WARN", "retrying"), ("ERROR", "bad request"), ("ERROR", "cache miss storm"),
                                                                                                        ("ERROR", "bad request"), ("ERROR", "zebra"), ("ERROR", "alpha")]))
    noerr = "2031-01-03 00:00:00 INFO a\n2031-01-03 00:00:01 WARN b\n"
    nonl = "2031-01-04 00:00:00 ERROR x\n2031-01-04 00:00:01 ERROR x"
    big = "".join(f"2031-01-05 00:00:00 ERROR failure code {r.randint(10 ** 5, 10 ** 6)} on node {i} with a rather long explanation text\n" for i in range(900))
    return ex, [scn("small logs", {"a.log": F(small), "b.log": F(noerr), "c log.log": F(nonl), "empty": F("")}, Run("a.log"), Run("a.log", "2"), Run("a.log", "10"), Run("b.log"), Run("c log.log", "1"), Run("empty")),
                scn("large log", {"big.log": F(big)}, Run("big.log", "2")),
                scn("errors", {"a.log": F(small)}, Run(stderr="nonempty"), Run("nope.log"), Run("a.log", "0"), Run("a.log", "x"), Run("a.log", "1", "2"))]


SPECS = [
    S("fix-silent-diff", 1,
      "`changed.sh` is supposed to tell me whether two files differ, but when they do it just dies without a word. Fix it.",
      "`bash changed.sh A B` prints `same` and exits 0 when the two files have identical content, and prints `changed` and exits with status 1 when they differ. If either file cannot be read, or the number of arguments is not two, "
      "it prints a message on stderr and exits with status 2 (nothing on stdout). The script runs in strict mode (`set -euo pipefail`) and must keep doing so.",
      REF_CHANGED, make_changed, script="changed.sh", buggy=BUG_CHANGED, title="Compare two files", wrong=(BUG_CHANGED,)),
    S("fix-grep-count", 1,
      "`count-errors.sh` works on logs that have errors but exits silently on a clean log. Fix it without dropping strict mode.",
      "`bash count-errors.sh FILE` prints `errors: N`, where `N` is the number of lines of `FILE` containing the text `ERROR` (case-sensitive), including `errors: 0` for a clean or empty file. "
      "A missing or unreadable file, or a wrong number of arguments, prints a message on stderr and exits with status 2. The script keeps `set -euo pipefail`.",
      REF_COUNT, make_count, script="count-errors.sh", buggy=BUG_COUNT, title="Count error lines", wrong=(BUG_COUNT,)),
    S("fix-post-increment", 2,
      "`sum-sizes.sh` counts the files in a directory and adds up their sizes, but it exits right after the first file with nothing printed. Please repair it.",
      "`bash sum-sizes.sh [DIR]` (default `.`) prints `files: N, bytes: B` for the regular files directly inside `DIR` (hidden files are not counted and subdirectories are not entered). "
      "The output is also printed for an empty directory (`files: 0, bytes: 0`). The script runs under `set -euo pipefail`.",
      REF_SUM, make_sum, script="sum-sizes.sh", buggy=BUG_SUM, title="Directory size summary", wrong=(BUG_SUM,)),
    S("fix-unset-argument", 2,
      "`backup-name.sh` dies with an 'unbound variable' error when you run it without a prefix, and gives an ugly error when STAMP is missing. Make it behave as the README says.",
      "`bash backup-name.sh [PREFIX]` prints `PREFIX-STAMP.tar` where `STAMP` comes from the environment variable of that name. `PREFIX` defaults to `backup` when it is absent **or empty**. "
      "If `STAMP` is unset or empty, print `STAMP is not set` on stderr and exit with status 3 (nothing on stdout). More than one argument: exit status 2 with a usage message on stderr. The script keeps `set -euo pipefail`.",
      dd('''
          #!/usr/bin/env bash
          set -euo pipefail
          # backup-name.sh [PREFIX] : name of today's backup archive, PREFIX-STAMP.tar
          [ $# -le 1 ] || { echo "usage: backup-name.sh [PREFIX]" >&2; exit 2; }
          prefix=${1:-backup}
          [ -n "$prefix" ] || prefix=backup
          if [ -z "${STAMP:-}" ]; then
            echo "STAMP is not set" >&2
            exit 3
          fi
          echo "$prefix-$STAMP.tar"
      '''), make_name, script="backup-name.sh", buggy=BUG_NAME, title="Backup archive name", wrong=(BUG_NAME,)),
    S("fix-line-reader", 2,
      "`numbered.sh` prints a file with line numbers but mangles indentation and backslashes and drops the last line when the file has no trailing newline. Fix it.",
      "`bash numbered.sh FILE` prints every line of `FILE` as `N: text` with `N` counting from 1 and `text` exactly as in the file (leading blanks, backslashes, tabs and `*` untouched). "
      "A final line without a trailing newline is still a line and gets printed (with a newline added). An empty file prints nothing. A missing file, or a wrong number of arguments, prints a message on stderr and exits with status 2. The script runs under `set -euo pipefail`.",
      REF_NUM, make_num, script="numbered.sh", buggy=BUG_NUM, title="Numbered lines", wrong=(BUG_NUM,)),
    S("fix-sigpipe", 3,
      "`firstword.sh` prints the first word of the first non-empty line of its input. On long inputs it fails with status 141 even though the answer is printed. Find out why and fix it.",
      "`bash firstword.sh` reads standard input and prints the first whitespace-separated word of the first line that has at least one non-blank character, then exits 0. If there is no such line it prints nothing and exits with status 1. "
      "It must work for arbitrarily large inputs. The script runs under `set -euo pipefail`.",
      REF_FIRST, make_first, script="firstword.sh", buggy=BUG_FIRST, title="First word of the input", wrong=(BUG_FIRST,)),
    S("fix-masked-status", 3,
      "`report.sh` prints sizes of the files it is given, but for a file that does not exist it happily prints an empty size and carries on. It should stop. Fix the script.",
      "`bash report.sh FILE...` prints `FILE: N bytes` for each argument in order, where `N` is the size in bytes. At the first file whose size cannot be determined the script stops with a non-zero exit status (the failing command's), "
      "after having printed the lines of the earlier files and **nothing** for the failing one. No arguments: usage message on stderr, exit status 2. The script runs under `set -euo pipefail`.",
      REF_REPORT, make_report, script="report.sh", buggy=BUG_REPORT, title="File size report", wrong=(BUG_REPORT,)),
    S("fix-trap-unbound", 3,
      "`listing.sh` lists a directory using a scratch directory. When called with wrong arguments it exits with status 1 and a strange 'unbound variable' message instead of status 2. Fix it, and make sure the scratch directory is always removed.",
      "`bash listing.sh DIR` prints the entries of `DIR` (hidden ones included, one per line) in byte-wise sorted order, working through a scratch directory created with `mktemp -d` (the tests point `TMPDIR` at a directory inside the working directory) that must be removed on every exit path. "
      "A wrong number of arguments or a `DIR` that is not a directory prints a message on stderr and exits with status 2, with no stdout. The script runs under `set -euo pipefail` and keeps using an `EXIT` trap.",
      REF_CLEAN, make_clean, script="listing.sh", buggy=BUG_CLEAN, title="Directory listing with a scratch dir", wrong=(BUG_CLEAN,)),
    S("fix-pipeline-subshell", 3,
      "`treelines.sh` should print the total number of lines in all `.txt` files below a directory, but it always says 0 (and chokes on odd file names). Fix it.",
      "`bash treelines.sh DIR` prints `total: N` where `N` is the sum over all regular files below `DIR` whose name ends in `.txt` (case-sensitive, hidden files included) of the number of newline characters in the file (what `wc -l` counts). "
      "File names may contain spaces, leading dashes and even line breaks. A wrong number of arguments or a `DIR` that does not exist prints a message on stderr and exits with status 2. The script runs under `set -euo pipefail`.",
      REF_TREE, make_tree, script="treelines.sh", buggy=BUG_TREE, title="Lines in text files", wrong=(BUG_TREE,)),
    S("fix-unknown-key", 2,
      "`total.sh` adds up prices of items from a built-in table, but one unknown item name makes it crash with an 'unbound variable' error. It should report the unknown item and keep going.",
      "`bash total.sh ITEM...` sums the prices of the items (`apple` 3, `pear` 4, `fig` 9, `dragon fruit` 12; names are case-sensitive and may contain a space) and prints `total: N`. "
      "For an item that is not in the table print `unknown: <item>` on stderr, skip it and continue; the total is still printed at the end, and the exit status is 1 if any item was unknown, otherwise 0. No items: `total: 0`. The script runs under `set -euo pipefail`.",
      REF_LOOKUP, make_lookup, script="total.sh", buggy=BUG_LOOKUP, title="Price total", wrong=(BUG_LOOKUP,)),
    S("fix-log-digest", 4,
      "`digest.sh` summarises an application log, but it falls over on clean logs, without the optional TOP argument, on files without trailing newline and on big logs. Several things are wrong at once; make it robust.",
      "`bash digest.sh FILE [TOP]` prints `lines: L` (newline count, like `wc -l`), `errors: E` (lines containing ` ERROR `), `warnings: W` (lines containing ` WARN `), then the line `top errors:` followed by at most `TOP` lines `<count> <message>` "
      "(as `uniq -c` formats them: count right-aligned in 7 columns, a space, the message) listing the most frequent error messages, most frequent first, equal counts ordered by message text byte-wise; the message is everything after the third space-separated field. "
      "With no error at all print `(none)` instead. `TOP` defaults to 3 and must be a positive integer. A missing file, a bad `TOP` or the wrong number of arguments prints a message on stderr and exits with status 2. "
      "Logs may be large and may lack a final newline. The script runs under `set -euo pipefail`.",
      REF_DIGEST, make_digest, script="digest.sh", buggy=BUG_DIGEST, title="Log digest", wrong=(BUG_DIGEST,)),
]


@family("shell-strict-mode-fixes", category="shell", lang="bash", kind="fix", n=len(SPECS),
        summary="repair bash scripts that misbehave under set -euo pipefail: grep -c, ((i++)), unset vars, SIGPIPE, local masking, traps, subshell counters")
def strict_mode(rng, n):
    return K.shell_tasks("strict-mode-fixes", SPECS, rng, n)
