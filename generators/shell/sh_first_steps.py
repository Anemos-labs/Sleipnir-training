"""Shell tasks, warm-up level: small single-purpose bash scripts (greeting with a default, line counts, column sums, whole-word search, column swaps, head and tail, file kinds, maximum of numbers)."""
import random

from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn, awkward_names

S = K.ShellSpec


def lines(rows):
    return "".join(r + "\n" for r in rows)


# ------------------------------------------------------------------------------------------------ 1. greeting with a default

REF_GREET = dd('''
    #!/usr/bin/env bash
    # greet.sh [NAME...] : say hello
    name="$*"
    [ -n "$name" ] || name=world
    printf 'Hello, %s!\\n' "$name"
''')

DOC_GREET = dd('''
    `greet.sh [NAME...]` prints `Hello, NAME!` on one line. Several arguments are joined with single spaces (`greet.sh Ada Lovelace` prints `Hello, Ada Lovelace!`).
    Without arguments, or when the arguments together are empty (`greet.sh ""`), the name is `world`. The exit status is always 0.
''')


def make_greet(rng):
    ex = scn("example", {}, Run("Ada", "Lovelace"))
    return ex, [scn("names", {}, Run("Grace"), Run("Linus", "Torvalds"), Run("Anne-Marie", "van der", "Berg"), Run("*"), Run("-n"), Run("$HOME", "it's")),
                scn("default name", {}, Run(), Run(""), Run("", ""), Run("x", ""))]


# ------------------------------------------------------------------------------------------------ 2. count lines

REF_COUNT = dd('''
    #!/usr/bin/env bash
    # count-lines.sh FILE... : "<lines> <name>" for every file
    [ $# -gt 0 ] || { echo "usage: count-lines.sh FILE..." >&2; exit 2; }
    rc=0
    for f in "$@"; do
      if [ -f "$f" ]; then
        printf '%s %s\\n' "$(awk 'END { print NR }' < "$f")" "$f"
      else
        echo "count-lines: $f: no such file" >&2
        rc=1
      fi
    done
    exit "$rc"
''')

DOC_COUNT = dd('''
    `count-lines.sh FILE...` prints one line `LINES NAME` for every argument, in argument order: the number of lines of the file, a space, and the name exactly as given.
    A last line without a trailing newline counts as a line too. A name that is not a regular file prints `count-lines: NAME: no such file` on standard error, the other files are still processed, and the exit status is 1 at the end.
    Without arguments it prints a usage line to standard error and exits with status 2.
''')


def make_count(rng):
    ex = scn("example", {"notes.txt": F("a\nb\nc\n")}, Run("notes.txt"))
    names = awkward_names(rng)
    files = {names[0]: F("one\ntwo\nthree\n"), names[1]: F("no newline at the end"), names[2]: F(""), names[3]: F("\n\n\n"), "dir/x.txt": F("x\ny\n"), "emptydir": D()}
    return ex, [scn("several files", files, Run(*names, "dir/x.txt")),
                scn("repeated and missing", files, Run(names[0], "nothere", names[0], "emptydir", names[1], stderr="nonempty")),
                scn("odd names", {"a=b": F("1\n2\n"), "-n": F("x\n"), "0": F("y\nz\nw\n")}, Run("a=b", "-n", "0")),
                scn("usage", {}, Run(stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 3. sum a column

REF_SUM = dd('''
    #!/usr/bin/env bash
    # sum-column.sh N : total of the integers in column N of the lines on standard input
    case ${1:-} in
      ''|*[!0-9]*|0) echo "usage: sum-column.sh N   (N >= 1)" >&2; exit 2 ;;
    esac
    awk -v n="$1" '$n ~ /^-?[0-9]+$/ { total += $n } END { printf "%d\\n", total }'
''')

DOC_SUM = dd('''
    `sum-column.sh N` reads standard input, splits every line into whitespace-separated fields and adds up field number N (counting from 1) over all the lines where that field is a whole integer (an optional minus sign and digits).
    Lines with fewer than N fields, and fields that are not whole integers (`3.5`, `1e3`, `n/a`, `+4`), are skipped. It prints the total as an integer on one line (`0` when nothing was added). The exit status is 0.
    When N is missing, `0`, or not a positive integer it prints a usage line to standard error and exits with status 2.
''')


def make_sum(rng):
    ex = scn("example", {}, Run("2", stdin="apples 3\npears 4\n"))

    def rows(n):
        out = []
        for _ in range(n):
            k = rng.choice([0, 0, 0, 1, 2, 3])
            v = rng.choice(["5", "12", "-7", "100", "0", "3.5", "1e3", "n/a", "+4", "-0", "007", "2147483648"])
            out.append(" ".join(["x" + str(rng.randint(1, 9)) for _ in range(k)] + [v]))
        return out
    inp = lines(["name  qty  price", "pen\t4\t1.50", "ink   10  7", "  pad   3   2  ", "", "short", "box -2 9"] + rows(15))
    return ex, [scn("three columns", {}, Run("2", stdin=inp), Run("3", stdin=inp), Run("1", stdin=inp), Run("9", stdin=inp)),
                scn("nothing to add", {}, Run("1", stdin=""), Run("1", stdin="a b\nc\n")),
                scn("large and negative", {}, Run("2", stdin="a 2147483647\nb 2147483647\nc -5000000000\nd 9007199254\n")),
                scn("usage", {}, Run(stderr="nonempty"), Run("0", stderr="nonempty"), Run("x", stderr="nonempty"), Run("-1", stderr="nonempty"), Run("2x", stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 4. whole-word search

REF_WORD = dd('''
    #!/usr/bin/env bash
    # find-word.sh WORD FILE : numbered lines of FILE that contain WORD as a whole word, ignoring case
    [ $# -eq 2 ] || { echo "usage: find-word.sh WORD FILE" >&2; exit 2; }
    [ -f "$2" ] && [ -r "$2" ] || { echo "find-word: $2: cannot read" >&2; exit 2; }
    grep -Fwin -- "$1" "$2"
''')

DOC_WORD = dd('''
    `find-word.sh WORD FILE` prints every line of FILE that contains WORD **as a whole word**, ignoring upper/lower case, as `LINENUMBER:LINE` (the line number counts from 1 over all lines).
    WORD is literal text, not a pattern (`c++` or `a.b` mean exactly those characters), and a whole word means that the characters around the match are not letters, digits or underscores (or the line edge).
    The exit status is 0 when at least one line matched and 1 when none did. A wrong number of arguments or a FILE that is not a readable regular file prints a message to standard error and exits with status 2.
''')


def make_word(rng):
    ex = scn("example", {"t.txt": F("the cat sat\nconcatenate\nCat food\n")}, Run("cat", "t.txt"))
    text = lines(["The Cat sat on the mat.", "concatenate and scatter", "cat_food is not the word cat", "CAT, cat; Cat!", "a.b and axb and A.B", "c++ rocks; C++, c+++ no", "-dash -dash-", "", "last line without cat news", "catalog", "tomcat"])
    f = {"book.txt": F(text), "empty.txt": F(""), "dir": D()}
    return ex, [scn("words", f, Run("cat", "book.txt"), Run("CAT", "book.txt"), Run("the", "book.txt"), Run("mat", "book.txt")),
                scn("literal text", f, Run("a.b", "book.txt"), Run("c++", "book.txt"), Run("-dash", "book.txt"), Run(".", "book.txt")),
                scn("nothing found", f, Run("dog", "book.txt"), Run("cat", "empty.txt")),
                scn("errors", f, Run("cat", "dir", stderr="nonempty"), Run("cat", "nofile", stderr="nonempty"), Run("cat", stderr="nonempty"), Run(stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 5. swap columns

REF_SWAP = dd('''
    #!/usr/bin/env bash
    # swap-columns.sh : swap the first two fields of every line
    awk 'NF < 2 { print; next } { t = $1; $1 = $2; $2 = t; print }'
''')

DOC_SWAP = dd('''
    `swap-columns.sh` copies standard input to standard output and swaps the first two whitespace-separated fields (spaces and tabs) of every line that has at least two fields.
    Such a line is written with its fields separated by single spaces (`a   b\\tc` becomes `b a c`). Lines with fewer than two fields (blank lines, single words) are copied unchanged, including their spaces. The exit status is 0.
''')


def make_swap(rng):
    ex = scn("example", {}, Run(stdin="Doe John\nsolo\nx y z\n"))
    inp = lines(["Smith Anna 1990", "  lead  trail  ", "single", "", "tab\tseparated\tfields here", "   ", "a b", "x    y     z  w", "end"])
    return ex, [scn("mixed lines", {}, Run(stdin=inp)), scn("empty input", {}, Run(stdin="")),
                scn("spaces survive in short lines", {}, Run(stdin="  just one  \n\t\n  two words  \n"))]


# ------------------------------------------------------------------------------------------------ 6. head and tail

REF_PEEK = dd('''
    #!/usr/bin/env bash
    # peek.sh N FILE : the first N and the last N lines of FILE
    case ${1:-} in ''|*[!0-9]*|0) echo "usage: peek.sh N FILE   (N >= 1)" >&2; exit 2 ;; esac
    [ $# -eq 2 ] && [ -f "$2" ] || { echo "usage: peek.sh N FILE   (N >= 1)" >&2; exit 2; }
    total=$(awk 'END { print NR }' < "$2")
    if [ "$total" -le $(( $1 * 2 )) ]; then
      cat -- "$2"
    else
      head -n "$1" -- "$2"
      echo "..."
      tail -n "$1" -- "$2"
    fi
''')

DOC_PEEK = dd('''
    `peek.sh N FILE` shows the beginning and the end of a file. With `N` a positive integer: if FILE has at most `2 * N` lines it prints the whole file unchanged;
    otherwise it prints the first N lines, a line containing only `...`, and the last N lines. (Files in the tests end with a newline.)
    A missing, zero or non-numeric N, a missing FILE argument, or a FILE that is not a regular file: usage line on standard error, exit status 2.
''')


def make_peek(rng):
    ex = scn("example", {"log.txt": F(lines([f"line {i}" for i in range(1, 11)]))}, Run("2", "log.txt"))
    big = lines([f"row {i}" for i in range(1, 31)])
    return ex, [scn("long file", {"big file.txt": F(big)}, Run("3", "big file.txt"), Run("1", "big file.txt"), Run("14", "big file.txt"), Run("15", "big file.txt"), Run("29", "big file.txt")),
                scn("short file", {"short": F(lines(["a", "b", "c", "d"])), "one": F("only\n"), "empty": F("")}, Run("2", "short"), Run("3", "short"), Run("1", "one"), Run("5", "empty")),
                scn("usage", {"f": F("x\n"), "d": D()}, Run(stderr="nonempty"), Run("0", "f", stderr="nonempty"), Run("two", "f", stderr="nonempty"), Run("2", stderr="nonempty"), Run("2", "d", stderr="nonempty"), Run("2", "nofile", stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 7. file kinds

REF_KIND = dd('''
    #!/usr/bin/env bash
    # kind.sh PATH... : what is each path?
    for p in "$@"; do
      if [ -L "$p" ]; then k=symlink
      elif [ -d "$p" ]; then k=directory
      elif [ -f "$p" ]; then k=file
      else k=missing
      fi
      printf '%s: %s\\n' "$p" "$k"
    done
''')

DOC_KIND = dd('''
    `kind.sh PATH...` prints `PATH: KIND` for each argument in order, where KIND is `symlink` for any symbolic link (even a broken one, or one pointing to a directory), otherwise `directory`, otherwise `file` (a regular file),
    otherwise `missing` (nothing exists under that name). The path is printed exactly as given. The exit status is always 0, also without arguments (which prints nothing).
''')


def make_kind(rng):
    ex = scn("example", {"a.txt": F("x\n"), "d": D(), "ln": L("a.txt")}, Run("a.txt", "d", "ln", "nope"))
    names = awkward_names(rng)
    files = {names[0]: F("x"), names[1]: D(), "link to dir": L(names[1]), "broken": L("does-not-exist"), "link to file": L(names[0]), "empty": F(""), "-dash": F("d\n")}
    return ex, [scn("every kind", files, Run(names[0], names[1], "link to dir", "broken", "link to file", "empty", "-dash", "ghost", "empty/x")),
                scn("repeat and relative", files, Run("./empty", "empty", "./" + names[1], "./link to dir", "..", ".", "./ghost")),
                scn("no arguments", {}, Run())]


# ------------------------------------------------------------------------------------------------ 8. biggest number

REF_MAX = dd('''
    #!/usr/bin/env bash
    # biggest.sh N... : the largest of the integers given as arguments
    [ $# -gt 0 ] || { echo "usage: biggest.sh INTEGER..." >&2; exit 2; }
    for v in "$@"; do
      [[ $v =~ ^-?[0-9]+$ ]] || { echo "biggest: not an integer: $v" >&2; exit 2; }
    done
    max=$1
    for v in "$@"; do
      (( v > max )) && max=$v
    done
    echo "$((max))"
''')

DOC_MAX = dd('''
    `biggest.sh N...` prints the largest of its arguments, which are integers with an optional leading minus sign (they fit in 64 bits). `-0` counts as 0 and is printed as `0`; there are no other leading zeros.
    Without arguments, or when some argument is not an integer, it prints a message to standard error and exits with status 2 without printing anything on standard output.
''')


def make_max(rng):
    ex = scn("example", {}, Run("3", "17", "-4"))
    return ex, [scn("positive and negative", {}, Run("5"), Run("-5"), Run("-5", "-12", "-9"), Run("3", "17", "-4", "17", "9"), Run("10", "9", "100", "99", "1000")),
                scn("zero and big numbers", {}, Run("0", "-0"), Run("-0", "-1"), Run("-0"), Run("9223372036854775807", "9223372036854775806"), Run("-9223372036854775807", "-9223372036854775806")),
                scn("errors", {}, Run(stderr="nonempty"), Run("3", "x", "5", stderr="nonempty"), Run("2.5", stderr="nonempty"), Run("+3", "4", stderr="nonempty"), Run("", "4", stderr="nonempty"), Run("-", stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ wrong scripts and the family

SPECS = [
    S("greeting-with-default", 1, "Write `greet.sh`: it greets the names given as arguments and says hello to `world` when there is none. Read README.md.", DOC_GREET, REF_GREET, make_greet, script="greet.sh",
      wrong=(REF_GREET.replace('name="$*"', 'name="$1"'), REF_GREET.replace('[ -n "$name" ] || name=world', ':'))),
    S("count-lines-per-file", 1, "Write `count-lines.sh`: print the number of lines of every file given as argument, keep going past missing files. Read README.md.", DOC_COUNT, REF_COUNT, make_count, script="count-lines.sh",
      wrong=(REF_COUNT.replace("awk 'END { print NR }' < \"$f\"", "wc -l < \"$f\""),)),
    S("sum-a-column", 1, "Write `sum-column.sh N`: add up the integers in column N of the lines on standard input and print the total. Read README.md for what counts as an integer.", DOC_SUM, REF_SUM, make_sum, script="sum-column.sh",
      wrong=(REF_SUM.replace("$n ~ /^-?[0-9]+$/ ", "$n ~ /^[-+]?[0-9.]+$/ "),)),
    S("whole-word-search", 1, "Write `find-word.sh WORD FILE`: print the numbered lines of FILE that contain WORD as a whole word, ignoring case. Read README.md.", DOC_WORD, REF_WORD, make_word, script="find-word.sh",
      wrong=(REF_WORD.replace("grep -Fwin", "grep -Fin"), REF_WORD.replace("grep -Fwin", "grep -wn"))),
    S("swap-first-two-columns", 1, "Write `swap-columns.sh`: swap the first two fields of every line read from standard input. Read README.md for the spacing rules.", DOC_SWAP, REF_SWAP, make_swap, script="swap-columns.sh",
      wrong=(REF_SWAP.replace("NF < 2 { print; next }", "NF < 2 { $1 = $1; print; next }"), REF_SWAP.replace("t = $1; $1 = $2; $2 = t; print", "$0 = $2 \" \" $1; print"))),
    S("head-and-tail-preview", 1, "Write `peek.sh N FILE`: show the first and last N lines of a file with a `...` line between them when lines are left out. Read README.md.", DOC_PEEK, REF_PEEK, make_peek, script="peek.sh",
      wrong=(REF_PEEK.replace("-le $(( $1 * 2 ))", "-lt $(( $1 * 2 ))"),)),
    S("what-kind-of-path", 1, "Write `kind.sh PATH...`: say for every path whether it is a symlink, a directory, a file or missing. Read README.md.", DOC_KIND, REF_KIND, make_kind, script="kind.sh",
      wrong=(REF_KIND.replace('if [ -L "$p" ]; then k=symlink\n  elif [ -d "$p" ]; then k=directory', 'if [ -d "$p" ]; then k=directory\n  elif [ -L "$p" ]; then k=symlink'), REF_KIND.replace('[ -L "$p" ]', '[ -h "$p" ] && [ -e "$p" ]'))),
    S("biggest-of-integers", 1, "Write `biggest.sh N...`: print the largest of the integer arguments (negative ones too). Read README.md.", DOC_MAX, REF_MAX, make_max, script="biggest.sh",
      wrong=(REF_MAX.replace("(( v > max )) && max=$v", '[ "$v" \\> "$max" ] && max=$v'), REF_MAX.replace('echo "$((max))"', 'echo "$max"'))),
]


for _s in SPECS:  # a wrong script must differ from the reference, otherwise the replacement silently did nothing
    for _w in _s.wrong:
        assert _w != _s.ref, _s.slug


@family("shell-first-steps", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="warm-up bash scripts: default arguments, line counts, column sums, whole-word search, column swaps, head and tail previews, path kinds, maximum of integers")
def first_steps(rng, n):
    return K.shell_tasks("shell-first-steps", SPECS, rng, n)
