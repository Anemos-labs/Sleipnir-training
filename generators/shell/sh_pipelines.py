"""Shell tasks: small text pipelines (sort/uniq/comm/join/paste/awk/tr): set operations, merges, joins, ranges, columns."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec


def lines(rows):
    return "".join(r + "\n" for r in rows)


# ------------------------------------------------------------------------------------------------ 1. common lines

REF_COMMON = dd('''
    #!/usr/bin/env bash
    # common.sh A B : lines present in both files, each once, byte-wise sorted
    [ $# -eq 2 ] && [ -r "$1" ] && [ -r "$2" ] || { echo "usage: common.sh A B" >&2; exit 2; }
    comm -12 <(LC_ALL=C sort -u -- "$1") <(LC_ALL=C sort -u -- "$2")
''')


def make_common(rng):
    ex = scn("example", {"a": F("red\nblue\ngreen\n"), "b": F("green\nyellow\nred\n")}, Run("a", "b"))
    a = lines(["kale", "two words", "Kale", "kale", " lead", "tail ", "ünï", "zebra", "", "-dash"])
    b = lines(["ünï", "kale", "Two Words", "two words", "", "tail", " lead", "-dash", "kale"])
    return ex, [scn("shared tags", {"a b": F(a), "-b": F(b)}, Run("a b", "./-b")), scn("nothing shared", {"a": F("x\ny\n"), "b": F("z\n")}, Run("a", "b")), scn("one empty", {"a": F(""), "b": F("x\n")}, Run("a", "b")),
                scn("usage", {"a": F("x\n")}, Run("a", stderr="nonempty"), Run("a", "missing"))]


# ------------------------------------------------------------------------------------------------ 2. only in the first file

REF_ONLY = dd('''
    #!/usr/bin/env bash
    # onlyfirst.sh A B : lines of A that do not occur in B, in the order of their first appearance in A
    [ $# -eq 2 ] && [ -r "$1" ] && [ -r "$2" ] || { echo "usage: onlyfirst.sh A B" >&2; exit 2; }
    awk 'NR == FNR { b[$0] = 1; next } !($0 in b) && !seen[$0]++' "$2" "$1"
''')


def make_only(rng):
    ex = scn("example", {"a": F("c\nb\na\nb\n"), "b": F("a\n")}, Run("a", "b"))
    a = lines(["zeta", "alpha", "two words", "alpha", "Gamma", "gamma", "", "tail ", "delta", "zeta", "-x"])
    b = lines(["alpha", "tail", "delta", "-x ", "two  words"])
    return ex, [scn("order is kept", {"a.txt": F(a), "b.txt": F(b)}, Run("a.txt", "b.txt"), Run("b.txt", "a.txt")), scn("empty second file", {"a": F("x\nx\ny\n"), "b": F("")}, Run("a", "b")), scn("usage", {"a": F("x\n")}, Run("a", stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 3. most common error codes

REF_CODES = dd('''
    #!/usr/bin/env bash
    # topcodes.sh N : the N most frequent error codes (E followed by 3 or 4 digits) in the log on stdin
    case ${1:-} in ''|*[!0-9]*|0) echo "usage: topcodes.sh N" >&2; exit 2 ;; esac
    grep -oE '\\bE[0-9]{3,4}\\b' | LC_ALL=C sort | uniq -c | awk '{ print $1, $2 }' | LC_ALL=C sort -k1,1nr -k2,2 | head -n "$1"
    exit 0
''')


def make_codes(rng):
    ex = scn("example", {}, Run("2", stdin="E404 not found\nE500 boom E404\nok\nE404\n"))
    log = lines(["2031-01-01 E1001 disk; also E1001 again and E2002", "retry XE1001 E12345 e1001 E99 E100", "E2002 E2002 E3003 E3003", "noise E3003", "E500 E500 E500", "(E500)", "E404,E404", "x E0042 y E0042 z E0041"])
    return ex, [scn("top codes", {}, Run("3", stdin=log), Run("1", stdin=log), Run("20", stdin=log), Run("2", stdin="no codes here\n")), scn("usage", {}, Run(stdin=log), Run("0", stdin=log), Run("x", stdin=log))]


# ------------------------------------------------------------------------------------------------ 4. merge sorted logs

REF_MERGE = dd('''
    #!/usr/bin/env bash
    # merge.sh FILE... : merge files whose lines start with a sortable timestamp; equal timestamps keep the order of the files
    [ $# -ge 1 ] || { echo "usage: merge.sh FILE..." >&2; exit 2; }
    for f in "$@"; do [ -r "$f" ] || { echo "merge.sh: cannot read $f" >&2; exit 2; }; done
    LC_ALL=C sort -m -s -k1,1 -- "$@"
''')


def make_merge(rng):
    ex = scn("example", {"a.log": F("2031-01-01T10:00:00 a1\n2031-01-01T12:00:00 a2\n"), "b.log": F("2031-01-01T11:00:00 b1\n")}, Run("a.log", "b.log"))
    a = lines(["2031-03-01T00:00:00 a-first", "2031-03-01T00:00:05 a tie", "2031-03-01T09:00:00 a-late"])
    b = lines(["2031-03-01T00:00:05 b tie", "2031-03-01T00:00:05 b tie again", "2031-03-02T00:00:00 b-next day"])
    c = lines(["2030-12-31T23:59:59 c-before", "2031-03-01T00:00:05 c tie"])
    return ex, [scn("three files with ties", {"a log": F(a), "b.log": F(b), "-c.log": F(c)}, Run("a log", "b.log", "./-c.log"), Run("./-c.log", "b.log", "a log")), scn("single and empty", {"a": F(a), "e": F("")}, Run("a"), Run("e", "a", "e")),
                scn("errors", {"a": F(a)}, Run(stderr="nonempty"), Run("a", "nope"))]


# ------------------------------------------------------------------------------------------------ 5. join people and scores

REF_JOINP = dd('''
    #!/usr/bin/env bash
    # scores.sh PEOPLE SCORES : "name<TAB>score" for every score line whose id is in PEOPLE, in SCORES order
    [ $# -eq 2 ] && [ -r "$1" ] && [ -r "$2" ] || { echo "usage: scores.sh PEOPLE SCORES" >&2; exit 2; }
    awk -F'\\t' -v OFS='\\t' 'NR == FNR { name[$1] = $2; next } $1 in name { print name[$1], $2 }' "$1" "$2"
''')


def make_joinp(rng):
    t = "\t"
    ex = scn("example", {"p": F(f"1{t}Ann\n2{t}Bob\n"), "s": F(f"2{t}10\n1{t}7\n3{t}5\n2{t}1\n")}, Run("p", "s"))
    people = lines([f"7{t}Ana María", f"12{t}Zoë Quinn", f"3{t}O'Neil, Pat", f"x-1{t}Key With Dash", f"07{t}Leading Zero"])
    scores = lines([f"12{t}88", f"7{t}91.5", f"7{t}60", f"99{t}1", f"x-1{t}0", f"07{t}33", f"3{t}", f"3{t}100"])
    return ex, [scn("repeated ids and odd names", {"people.tsv": F(people), "scores.tsv": F(scores)}, Run("people.tsv", "scores.tsv")), scn("no matches", {"p": F(f"1{t}A\n"), "s": F(f"2{t}5\n")}, Run("p", "s")),
                scn("usage", {"p": F("")}, Run("p", stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 6. transpose key-value lines

REF_TRANS = dd('''
    #!/usr/bin/env bash
    # transpose.sh : "key value..." lines on stdin -> a line of keys and a line of values, TAB separated
    awk 'NF { k = $1; v = $0; sub(/^[ \\t]*[^ \\t]+[ \\t]*/, "", v); sub(/[ \\t]+$/, "", v); keys = keys (n ? "\\t" : "") k; vals = vals (n ? "\\t" : "") v; n++ } END { if (n) { print keys; print vals } }'
''')


def make_trans(rng):
    ex = scn("example", {}, Run(stdin="name Ann\nage 31\ncity New York\n"))
    return ex, [scn("records", {}, Run(stdin="host db-1\nuptime 3 days 4 hours\n\n  port    5432  \nmode\nnote with  spaces inside\n"), Run(stdin="only one\n"), Run(stdin=""), Run(stdin="\n  \n"))]


# ------------------------------------------------------------------------------------------------ 7. dedupe by first field, case-insensitive

REF_DEDUP = dd('''
    #!/usr/bin/env bash
    # firstseen.sh : keep a line only if no earlier line has the same first field (ASCII case-insensitive)
    awk 'NF { k = tolower($1); if (!(k in seen)) { seen[k] = 1; print } }'
''')


def make_dedup(rng):
    ex = scn("example", {}, Run(stdin="Ann 1\nann 2\nBob 3\n"))
    return ex, [scn("mixed case", {}, Run(stdin="Kale 1\nkale 2\nKALE 3\n  Leek   4\nleek 5\nPea\npea x\n\n-dash 1\n-DASH 2\nünï 1\nÜNÏ 2\n"), Run(stdin=""), Run(stdin="a\na\na\n"))]


# ------------------------------------------------------------------------------------------------ 8. initials histogram

REF_INIT = dd('''
    #!/usr/bin/env bash
    # initials.sh : count lines by the first non-blank character, upper-cased; letters A-Z alphabetically, everything else under "#"
    awk '
      { s = $0; sub(/^[ \\t]+/, "", s); if (s == "") next
        c = toupper(substr(s, 1, 1))
        if (c ~ /^[A-Z]$/) n[c]++; else other++ }
      END {
        for (i = 65; i <= 90; i++) { c = sprintf("%c", i); if (n[c]) print c ": " n[c] }
        if (other) print "#: " other
      }'
''')


def make_init(rng):
    ex = scn("example", {}, Run(stdin="apple\nAvocado\nbanana\n42 things\n"))
    return ex, [scn("initials", {}, Run(stdin=lines(["alpha", "Beta", "  gamma", "Gamma 2", "delta", "9lives", "-dash", "zeta", "Zulu", "ünï", "", "   ", "a", "\ttab", "_x", "bravo"])), Run(stdin=""), Run(stdin="123\n456\n"))]


# ------------------------------------------------------------------------------------------------ 9. expand ranges

REF_EXPAND = dd('''
    #!/usr/bin/env bash
    # expand.sh SPEC : "1-3,7,10-12" -> the numbers, one per line; a range may descend (5-3)
    spec=${1-}
    [ $# -eq 1 ] && [[ $spec =~ ^[0-9]+(-[0-9]+)?(,[0-9]+(-[0-9]+)?)*$ ]] || { echo "usage: expand.sh SPEC (like 1-3,7,10-12)" >&2; exit 2; }
    IFS=, read -r -a items <<< "$spec"
    for it in "${items[@]}"; do
      if [[ $it == *-* ]]; then
        a=$((10#${it%-*})); b=$((10#${it#*-}))
        if [ "$a" -le "$b" ]; then seq "$a" "$b"; else seq "$a" -1 "$b"; fi
      else
        echo $((10#$it))
      fi
    done
''')


def make_expand(rng):
    ex = scn("example", {}, Run("1-3,7"))
    return ex, [scn("specs", {}, Run("5"), Run("1-3,7,10-12"), Run("5-3"), Run("007-009,3,3"), Run("0-2,2-0"), Run("100-102"), Run("1-1"), Run("9,8,7-5,4")),
                scn("invalid", {}, Run(), Run(""), Run("1-"), Run("-3"), Run("1,,2"), Run("a-b"), Run("1-2-3"), Run("1 2"), Run("1,2,"), Run("1", "2"))]


# ------------------------------------------------------------------------------------------------ 10. collapse numbers into ranges

REF_COLLAPSE = dd('''
    #!/usr/bin/env bash
    # collapse.sh : integers on stdin (any order, repeats allowed) -> "1-3,5,7-9": runs of 3 or more consecutive numbers become a-b, shorter runs stay as numbers
    grep -E '^[[:space:]]*[0-9]+[[:space:]]*$' | tr -d ' \\t' | LC_ALL=C sort -n -u | awk '
      function flush(   i) {
        if (n == 0) return
        if (n >= 3) out = out (out == "" ? "" : ",") first "-" last
        else for (i = 0; i < n; i++) out = out (out == "" ? "" : ",") (first + i)
      }
      { v = $1 + 0
        if (n > 0 && v == last + 1) { last = v; n++ } else { flush(); first = v; last = v; n = 1 } }
      END { flush(); if (out != "") print out }'
    exit 0
''')


def make_collapse(rng):
    ex = scn("example", {}, Run(stdin="3\n1\n2\n7\n9\n8\n10\n20\n"))
    return ex, [scn("runs", {}, Run(stdin="5\n1\n2\n3\n3\n10\n11\n20\n21\n22\n23\n30\n"), Run(stdin="  7  \n8\nx\n\n9\n-4\n1.5\n100\n"), Run(stdin="0\n1\n2\n"), Run(stdin="42\n"), Run(stdin=""), Run(stdin="abc\n")),
                scn("many numbers", {}, Run(stdin=lines(str(n) for n in [9, 3, 4, 5, 6, 12, 14, 15, 13, 1, 99, 100, 101, 102, 7, 7, 200])))]


# ------------------------------------------------------------------------------------------------ 11. columns

REF_COLUMNS = dd('''
    #!/usr/bin/env bash
    # columns.sh N : arrange the lines of stdin into rows of N items separated by TABs
    case ${1:-} in ''|*[!0-9]*|0) echo "usage: columns.sh N" >&2; exit 2 ;; esac
    paste -d '\\t' $(printf -- '- %.0s' $(seq 1 "$1")) | sed 's/\\t*$//'
    exit 0
''')


def make_columns(rng):
    ex = scn("example", {}, Run("3", stdin="a\nb\nc\nd\ne\n"))
    return ex, [scn("rows", {}, Run("2", stdin="one\ntwo words\nthree\nfour\nfive\n"), Run("4", stdin="1\n2\n3\n4\n5\n6\n7\n8\n"), Run("1", stdin="x\ny\n"), Run("5", stdin="a\nb\n"), Run("3", stdin=""), Run("3", stdin="a\n\nc\nd\n")),
                scn("usage", {}, Run(stdin="a\n"), Run("0", stdin="a\n"), Run("x", stdin="a\n"))]


# ------------------------------------------------------------------------------------------------ 12. fix: top items

BUG_FREQ = dd('''
    #!/bin/bash
    # topitems.sh N : the N most frequent lines of stdin as "COUNT ITEM", most frequent first, ties in alphabetical order
    sort | uniq -c | sort -n | tail -$1
''')
REF_FREQ = dd('''
    #!/bin/bash
    # topitems.sh N : the N most frequent lines of stdin as "COUNT ITEM", most frequent first, ties in alphabetical order
    case ${1:-} in ''|*[!0-9]*|0) echo "usage: topitems.sh N" >&2; exit 2 ;; esac
    LC_ALL=C sort | uniq -c | awk '{ c = $1; sub(/^ *[0-9]+ /, ""); print c "\\t" $0 }' | LC_ALL=C sort -t"$(printf '\\t')" -k1,1nr -k2 | sed 's/\\t/ /' | head -n "$1"
    exit 0
''')


def make_freq(rng):
    ex = scn("example", {}, Run("2", stdin="a\nb\na\nc\nb\na\n"))
    items = ["pear", "apple", "pear", "fig", "two words", "apple", "pear", "fig", "two words", "kiwi", "two words", "date"]
    return ex, [scn("ties and spaces", {}, Run("3", stdin=lines(items)), Run("1", stdin=lines(items)), Run("10", stdin=lines(items)), Run("2", stdin="")), scn("usage", {}, Run(stdin="a\n"), Run("0", stdin="a\n"), Run("z", stdin="a\n"))]


SPECS = [
    S("tags-in-both-files", 2,
      "Write `common.sh A B`: print the lines two files have in common, each once, sorted. README has the exact rules.",
      "`bash common.sh A B` prints every line (compared as exact strings: case, blanks and empty lines all count) that occurs in both files, once, in byte-wise sorted order. Both files must be readable and exactly two arguments given, otherwise usage message on stderr and exit status 2.",
      REF_COMMON, make_common, script="common.sh", title="Lines in both files", wrong=("#!/bin/bash\ngrep -Fxf \"$1\" \"$2\"\n",)),
    S("lines-only-in-first-file", 3,
      "Write `onlyfirst.sh A B`: the lines of A that B does not contain, keeping A's order (no sorting) and listing each once.",
      "`bash onlyfirst.sh A B` prints the lines of file `A` that do not occur (as exact strings) in file `B`, in the order of their first appearance in `A`, each distinct line once. Both files must be readable, with two arguments; otherwise usage message on stderr and exit status 2.",
      REF_ONLY, make_only, script="onlyfirst.sh", title="Lines only in the first file", wrong=("#!/bin/bash\ncomm -23 <(sort -u \"$1\") <(sort -u \"$2\")\n",)),
    S("most-frequent-error-codes", 3,
      "Write `topcodes.sh N`: read a log on stdin and print the N most frequent error codes (`E` and 3-4 digits) with their counts.",
      "`bash topcodes.sh N` finds every error code in the standard input: the letter `E` followed by 3 or 4 digits as a whole word (`E404`, `E1001`; not `XE1001`, `E12345`, `E99` or lower-case `e404`). It prints `COUNT CODE` (one space between) for the `N` most frequent codes, "
      "most frequent first, ties in byte-wise order of the code. `N` must be a positive integer, otherwise usage message on stderr and exit status 2. Fewer lines if fewer distinct codes exist; exit status 0 even when none are found.",
      REF_CODES, make_codes, script="topcodes.sh", title="Most frequent error codes", wrong=("#!/bin/bash\ngrep -o 'E[0-9]*' | sort | uniq -c | sort -rn | head -n $1\n",)),
    S("merge-sorted-logs", 3,
      "Write `merge.sh FILE...`: merge several already-sorted log files into one chronological stream, keeping file order on equal timestamps.",
      "`bash merge.sh FILE...` merges files whose lines begin with a fixed-width timestamp followed by a space and a message; every file is already in timestamp order. The output is all lines in timestamp order (byte-wise comparison of the first field); lines with equal timestamps keep the order of the files on the command line, "
      "and within a file their original order. An unreadable file or no arguments: message on stderr, exit status 2, no output.",
      REF_MERGE, make_merge, script="merge.sh", title="Merge sorted logs", wrong=("#!/bin/bash\ncat \"$@\" | sort\n",)),
    S("scores-for-known-people", 3,
      "Write `scores.sh PEOPLE SCORES`: attach names to score lines through the id column, keeping the order of the scores file.",
      "`bash scores.sh PEOPLE SCORES`: `PEOPLE` has lines `ID<TAB>NAME`, `SCORES` has lines `ID<TAB>SCORE` (ids may repeat in `SCORES`; ids are compared as exact strings, so `07` and `7` differ; names may contain spaces and commas; scores may be empty). "
      "Print `NAME<TAB>SCORE` for every line of `SCORES` whose id appears in `PEOPLE`, in the order of `SCORES`; other score lines are dropped. Two readable files are required, otherwise usage message on stderr and exit status 2.",
      REF_JOINP, make_joinp, script="scores.sh", title="Names for scores", wrong=("#!/bin/bash\njoin \"$1\" \"$2\"\n",)),
    S("transpose-key-value-lines", 2,
      "Write `transpose.sh`: turn `key value` lines on stdin into two TAB-separated lines, the keys and then the values.",
      "`bash transpose.sh` reads lines `KEY VALUE...` from standard input (the key is the first whitespace-separated word, the value is the rest of the line with surrounding blanks removed, possibly empty). Blank lines are skipped. "
      "It prints one line with all keys separated by TABs and a second line with all values separated by TABs, in input order. No usable lines: no output.",
      REF_TRANS, make_trans, script="transpose.sh", title="Transpose key-value lines", wrong=("#!/bin/bash\ncat\n",)),
    S("first-seen-key-ignoring-case", 2,
      "Write `firstseen.sh`: keep each line only if no earlier line had the same first word, ignoring (ASCII) case.",
      "`bash firstseen.sh` filters standard input: a line is printed (unchanged) only if its first whitespace-separated word, lower-cased (ASCII letters only), has not been seen on an earlier line; blank lines are dropped.",
      REF_DEDUP, make_dedup, script="firstseen.sh", title="First line per key", wrong=("#!/bin/bash\nawk '!s[$1]++'\n",)),
    S("lines-by-initial", 3,
      "Write `initials.sh`: count the lines of stdin by their first character (upper-cased letters A-Z, everything else together under `#`).",
      "`bash initials.sh` reads lines on standard input, ignores blank (or blank-only) lines and looks at the first non-blank character of each. ASCII letters (either case) are counted under their upper-case letter, anything else (digits, punctuation, non-ASCII letters) under `#`. "
      "Output `X: N` per letter that occurs, alphabetically, then `#: N` if any line fell in that class. No lines: no output.",
      REF_INIT, make_init, script="initials.sh", title="Lines by initial", wrong=("#!/bin/bash\ncut -c1 | sort | uniq -c\n",)),
    S("expand-number-ranges", 3,
      "Write `expand.sh SPEC` that expands a range list like `1-3,7,10-12` into one number per line.",
      "`bash expand.sh SPEC`: `SPEC` is a comma-separated list of non-negative integers and ranges `A-B` (decimal digits only, leading zeros allowed and ignored). A range is inclusive and may descend (`5-3` is 5, 4, 3). Print the numbers in the order given, without leading zeros, one per line; repeats are kept. "
      "Anything else (empty spec, empty items, `1-`, `-3`, `1-2-3`, spaces, a missing or extra argument) prints a usage message on stderr and exits with status 2 without output.",
      REF_EXPAND, make_expand, script="expand.sh", title="Expand number ranges", wrong=("#!/bin/bash\nseq $(echo $1 | tr - ' ')\n",)),
    S("collapse-numbers-to-ranges", 4,
      "Write `collapse.sh`: read integers from stdin in any order and print them as a compact list with ranges (`1-3,5,7-9`).",
      "`bash collapse.sh` reads lines from standard input; lines that consist only of an optionally blank-padded non-negative integer count (others are ignored). The numbers are de-duplicated and sorted numerically, then printed on one line separated by commas: "
      "every maximal run of **three or more** consecutive integers is written `FIRST-LAST`, shorter runs are written as the individual numbers. No numbers: no output, exit status 0.",
      REF_COLLAPSE, make_collapse, script="collapse.sh", title="Collapse numbers to ranges", wrong=("#!/bin/bash\nsort -n | paste -sd,\n",)),
    S("items-into-columns", 2,
      "Write `columns.sh N` that lays the lines of stdin out in rows of N TAB-separated items, row by row.",
      "`bash columns.sh N` reads lines from standard input and prints them `N` per row, separated by TABs, filling row by row; the last row may be shorter (no padding, no trailing TAB). Empty input prints nothing. `N` must be a positive integer, otherwise usage message on stderr and exit status 2.",
      REF_COLUMNS, make_columns, script="columns.sh", title="Items into columns", wrong=("#!/bin/bash\ncat\n",)),
    S("fix-most-frequent-lines", 2,
      "`topitems.sh N` prints the N most frequent lines with counts, but the order is ascending, ties come out arbitrary and an argument is missing a check. Fix it.",
      "`bash topitems.sh N` reads lines from standard input and prints the `N` most frequent distinct lines as `COUNT ITEM` (one space between; items may contain spaces), most frequent first, equal counts ordered by the item text byte-wise. "
      "`N` must be a positive integer, otherwise usage message on stderr and exit status 2. Fewer lines if there are fewer distinct items.",
      REF_FREQ, make_freq, script="topitems.sh", buggy=BUG_FREQ, title="Most frequent lines", wrong=(BUG_FREQ,)),
]


@family("shell-text-pipelines", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="sort/uniq/comm/join/paste/awk pipelines: set operations, merges, joins, ranges and columns with exact output")
def text_pipelines(rng, n):
    return K.shell_tasks("text-pipelines", SPECS, rng, n)
