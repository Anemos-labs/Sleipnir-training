"""Shell tasks: repairing quoting, word-splitting, globbing, IFS, eval and heredoc bugs in small bash tools."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec

# ------------------------------------------------------------------------------------------------ 1. echo args

BUG_ARGS = dd('''
    #!/bin/bash
    # showargs.sh ARG... : print every argument on its own line as "arg: <argument>"
    for a in $*; do
      echo "arg: $a"
    done
''')
REF_ARGS = dd('''
    #!/bin/bash
    # showargs.sh ARG... : print every argument on its own line as "arg: <argument>"
    for a in "$@"; do
      printf 'arg: %s\\n' "$a"
    done
''')


def make_args(rng):
    ex = scn("example", {"x.txt": F("1"), "y.txt": F("2")}, Run("hello world", "*"))
    f = {"x.txt": F("1"), "y.txt": F("2"), "-n": F("3")}
    return ex, [scn("awkward arguments", f, Run("a b", "c"), Run("*"), Run("  lead and trail  "), Run(""), Run("-n"), Run("-e", "x\\ny"), Run("$HOME", "`date`", "it's", '"q"'), Run("[xy].txt", "?.txt"), Run()),
                scn("many", f, Run(*[f"item {i}" for i in range(12)]))]


# ------------------------------------------------------------------------------------------------ 2. wrapper with log

BUG_WRAP = dd('''
    #!/bin/bash
    # wrapper.sh CMD [ARG...] : append "+ <command line>" to wrapper.log, then run the command
    cmd="$@"
    echo "+ $cmd" >> wrapper.log
    $cmd
''')
REF_WRAP = dd('''
    #!/bin/bash
    # wrapper.sh CMD [ARG...] : append "+ <command line>" to wrapper.log, then run the command
    [ $# -gt 0 ] || { echo "usage: wrapper.sh CMD [ARG...]" >&2; exit 2; }
    { printf '+'; printf ' %q' "$@"; printf '\\n'; } >> wrapper.log
    "$@"
''')


def make_wrap(rng):
    ex = scn("example", {}, Run("printf", "[%s]\\n", "a b", "c"))
    return ex, [scn("arguments survive", {"x.txt": F("1")}, Run("printf", "[%s]\\n", "a b", "*", "$HOME"), Run("echo", "-n", "no newline"), Run("sh", "-c", 'echo "$1|$2"', "sh", "one two", "it's")),
                scn("exit status and log", {}, Run("sh", "-c", "exit 7"), Run("false"), Run("true")),
                scn("log keeps appending", {"wrapper.log": F("+ old\n")}, Run("echo", "new")),
                scn("usage", {}, Run(stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 3. emptiness

BUG_EMPTY = dd('''
    #!/bin/bash
    # isempty.sh ARG... : for each argument say "empty" (zero length) or "non-empty"
    for a in "$@"; do
      if [ -z $a ]; then
        echo empty
      else
        echo non-empty
      fi
    done
''')
REF_EMPTY = dd('''
    #!/bin/bash
    # isempty.sh ARG... : for each argument say "empty" (zero length) or "non-empty"
    for a in "$@"; do
      if [ -z "$a" ]; then
        echo empty
      else
        echo non-empty
      fi
    done
''')


def make_empty(rng):
    ex = scn("example", {}, Run("", "x", " "))
    return ex, [scn("tricky arguments", {}, Run("", " ", "  ", "-n", "-z", "=", "!", "a b", "(", "-o", "*", "\t"), Run("-z", ""), Run(), Run("x"))]


# ------------------------------------------------------------------------------------------------ 4. string equality

BUG_EQ = dd('''
    #!/bin/bash
    # equal.sh A B : "equal" (exit 0) if the two strings are identical, else "different" (exit 1)
    if [[ $1 == $2 ]]; then
      echo equal
    else
      echo different
      exit 1
    fi
''')
REF_EQ = dd('''
    #!/bin/bash
    # equal.sh A B : "equal" (exit 0) if the two strings are identical, else "different" (exit 1)
    [ $# -eq 2 ] || { echo "usage: equal.sh A B" >&2; exit 2; }
    if [[ $1 == "$2" ]]; then
      echo equal
    else
      echo different
      exit 1
    fi
''')


def make_eq(rng):
    ex = scn("example", {}, Run("abc", "abc"))
    return ex, [scn("patterns are not patterns", {}, Run("abc", "a*"), Run("a*", "a*"), Run("abc", "[a-c]bc"), Run("x", "?"), Run("", ""), Run("", "*"), Run("a b", "a b"), Run("a b", "a  b"), Run("-n", "-n"), Run("A", "a")),
                scn("usage", {}, Run("one"), Run(), Run("a", "b", "c"))]


# ------------------------------------------------------------------------------------------------ 5. colon-separated dirs

BUG_DIRS = dd('''
    #!/bin/bash
    # dirs.sh LIST : LIST is a colon-separated list of directories; print "ok: DIR" or "missing: DIR" for each non-empty entry
    for d in ${1//:/ }; do
      if [ -d $d ]; then
        echo "ok: $d"
      else
        echo "missing: $d"
      fi
    done
''')
REF_DIRS = dd('''
    #!/bin/bash
    # dirs.sh LIST : LIST is a colon-separated list of directories; print "ok: DIR" or "missing: DIR" for each non-empty entry
    [ $# -eq 1 ] || { echo "usage: dirs.sh LIST" >&2; exit 2; }
    IFS=: read -r -a parts <<< "$1:"
    for d in "${parts[@]}"; do
      [ -n "$d" ] || continue
      if [ -d "$d" ]; then
        echo "ok: $d"
      else
        echo "missing: $d"
      fi
    done
''')


def make_dirs(rng):
    ex = scn("example", {"a/x": F("1"), "b b/y": F("2")}, Run("a:b b:nope"))
    f = {"a/x": F("1"), "b b/y": F("2"), "-dash/z": F("3"), "star*/q": F("4"), "d/e/f": F("5")}
    return ex, [scn("awkward entries", f, Run("a:b b:-dash:star*:d/e"), Run(":a::b b:"), Run("nope:*:a"), Run("x y:z"), Run("")), scn("usage", f, Run(), Run("a", "b"))]


# ------------------------------------------------------------------------------------------------ 6. heredoc config

BUG_CONF = dd('''
    #!/bin/bash
    # mkconfig.sh NAME : write config.ini for the application NAME
    cat > config.ini <<EOF
    [app]
    name=$1
    home=$HOME/apps/$1
    started=`date +%s`
    price=costs $5 and 50% off
    shell=$SHELL -l
    EOF
''')
REF_CONF = dd('''
    #!/bin/bash
    # mkconfig.sh NAME : write config.ini for the application NAME
    [ $# -eq 1 ] || { echo "usage: mkconfig.sh NAME" >&2; exit 2; }
    cat > config.ini <<EOF
    [app]
    name=$1
    home=\\$HOME/apps/$1
    started=\\`date +%s\\`
    price=costs \\$5 and 50% off
    shell=\\$SHELL -l
    EOF
''')


def make_conf(rng):
    ex = scn("example", {}, Run("tidewatch"))
    return ex, [scn("names", {}, Run("two words")), scn("name with shell characters", {}, Run("$HOME and `id` and $(whoami) \\n")), scn("rerun overwrites", {"config.ini": F("old\n")}, Run("again")),
                scn("usage", {}, Run(stderr="nonempty"), Run("a", "b"))]


# ------------------------------------------------------------------------------------------------ 7. remove tmp files

BUG_RMTMP = dd('''
    #!/bin/bash
    # cleantmp.sh DIR : delete the *.tmp files directly inside DIR (hidden ones too) and say how many
    count=$(ls $1/*.tmp | wc -l)
    rm -f $1/*.tmp
    echo "removed $count files"
''')
REF_RMTMP = dd('''
    #!/bin/bash
    # cleantmp.sh DIR : delete the *.tmp files directly inside DIR (hidden ones too) and say how many
    dir=${1:?usage: cleantmp.sh DIR}
    [ -d "$dir" ] || { echo "error: not a directory: $dir" >&2; exit 2; }
    shopt -s nullglob dotglob
    count=0
    for f in "$dir"/*.tmp; do
      [ -f "$f" ] || continue
      rm -f -- "$f"
      count=$((count + 1))
    done
    echo "removed $count files"
''')


def make_rmtmp(rng):
    ex = scn("example", {"w/a.tmp": F("1"), "w/b.txt": F("2"), "w/c.tmp": F("3")}, Run("w"))
    f = {"my dir/one.tmp": F("1"), "my dir/two words.tmp": F("2"), "my dir/.hidden.tmp": F("3"), "my dir/keep.txt": F("4"), "my dir/-dash.tmp": F("5"), "my dir/sub.tmp/inner.tmp": F("6"), "my dir/star*.tmp": F("7"),
         "empty/none.txt": F("8")}
    return ex, [scn("awkward names", f, Run("my dir")), scn("nothing to remove", f, Run("empty")), scn("no such dir", f, Run("nope", stderr="nonempty"), Run(stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 8. search with eval

BUG_SEARCH = dd('''
    #!/bin/bash
    # search.sh [-i] [-w] PATTERN FILE... : grep -n with optional flags
    opts=
    while getopts iw o; do
      case $o in
        i) opts="$opts -i" ;;
        w) opts="$opts -w" ;;
      esac
    done
    shift $((OPTIND - 1))
    pattern=$1
    shift
    eval "grep -n $opts $pattern $*"
''')
REF_SEARCH = dd('''
    #!/bin/bash
    # search.sh [-i] [-w] PATTERN FILE... : grep -n with optional flags
    args=(-n)
    while getopts ':iw' o; do
      case $o in
        i) args+=(-i) ;;
        w) args+=(-w) ;;
        *) echo "usage: search.sh [-i] [-w] PATTERN FILE..." >&2; exit 2 ;;
      esac
    done
    shift $((OPTIND - 1))
    [ $# -ge 2 ] || { echo "usage: search.sh [-i] [-w] PATTERN FILE..." >&2; exit 2; }
    pattern=$1
    shift
    grep "${args[@]}" -e "$pattern" -- "$@"
''')


def make_search(rng):
    ex = scn("example", {"log.txt": F("Error one\nok\nerror two\n")}, Run("-i", "error", "log.txt"))
    f = {"a b.txt": F("hello world\nHello there\nworld wide\nsay \"hi\"; touch pwned\n"), "-x": F("hello\nhelloworld\n"), "c.txt": F("it's here\nthe end\n")}
    return ex, [scn("flags and files", f, Run("hello", "a b.txt"), Run("-i", "hello", "a b.txt", "./-x"), Run("-w", "hello", "./-x"), Run("-iw", "HELLO", "a b.txt", "./-x")),
                scn("patterns with spaces and metacharacters", f, Run("hello world", "a b.txt"), Run("it's", "c.txt"), Run('say "hi"; touch pwned', "a b.txt"), Run("world; touch pwned2", "a b.txt"), Run("$(touch pwned3)", "a b.txt"), Run("h.llo", "a b.txt")),
                scn("status and usage", f, Run("absent", "a b.txt"), Run("hello"), Run(), Run("-q", "x", "a b.txt"))]


# ------------------------------------------------------------------------------------------------ 9. forwarding

TARGET = dd('''
    #!/bin/bash
    # target.sh : prints how many arguments it got and each of them in brackets
    echo "args: $#"
    for a in "$@"; do
      echo "[$a]"
    done
''')
BUG_FWD = dd('''
    #!/bin/bash
    # forward.sh ARG... : call ./target.sh --via-forward with the same arguments
    ./target.sh --via-forward $@
''')
REF_FWD = dd('''
    #!/bin/bash
    # forward.sh ARG... : call ./target.sh --via-forward with the same arguments
    exec ./target.sh --via-forward "$@"
''')


def make_fwd(rng):
    ex = scn("example", {"target.sh": F(TARGET, x=True)}, Run("one", "two words"))
    f = {"target.sh": F(TARGET, x=True), "x.txt": F("1")}
    return ex, [scn("arguments", f, Run(), Run("a b", "c"), Run("*"), Run(""), Run("-n", "--help"), Run("tab\tsep", "it's", '"q"', "$HOME"), Run("", "", "last"))]


# ------------------------------------------------------------------------------------------------ 10. leading zeros

BUG_SUMN = dd('''
    #!/bin/bash
    # sumn.sh N... : sum of non-negative decimal integers (leading zeros allowed)
    total=0
    for n in "$@"; do
      total=$((total + n))
    done
    echo "$total"
''')
REF_SUMN = dd('''
    #!/bin/bash
    # sumn.sh N... : sum of non-negative decimal integers (leading zeros allowed)
    total=0
    for n in "$@"; do
      case $n in
        ''|*[!0-9]*) echo "bad number: $n" >&2; exit 2 ;;
      esac
      total=$((total + 10#$n))
    done
    echo "$total"
''')


def make_sumn(rng):
    ex = scn("example", {}, Run("08", "09", "10"))
    return ex, [scn("leading zeros", {}, Run("007", "010", "0"), Run("08"), Run("0000019", "1"), Run("099", "0100"), Run(), Run("123456789012", "000000000001")),
                scn("bad input", {}, Run("1", "x", stderr="nonempty"), Run("-5"), Run("1.5"), Run(""), Run("0x10"))]


# ------------------------------------------------------------------------------------------------ 11. join lines

BUG_JOIN = dd('''
    #!/bin/bash
    # joinlines.sh FILE : print the lines of FILE joined with commas
    echo $(cat $1) | tr ' ' ','
''')
REF_JOIN = dd('''
    #!/bin/bash
    # joinlines.sh FILE : print the lines of FILE joined with commas
    [ $# -eq 1 ] && [ -r "$1" ] || { echo "usage: joinlines.sh FILE" >&2; exit 2; }
    awk 'NR > 1 { printf "," } { printf "%s", $0 } END { if (NR > 0) printf "\\n" }' "$1"
''')


def make_join(rng):
    ex = scn("example", {"l.txt": F("red\ngreen apple\nblue\n")}, Run("l.txt"))
    f = {"plain": F("a\nb\nc\n"), "spaces and globs": F("two  words\n*\n  lead\ntrail  \n[x]\n"), "one": F("solo\n"), "empty": F(""), "blank lines": F("a\n\nb\n"), "no newline": F("p\nq"), "my file": F("x\ny\n"), "star.txt": F("s\n")}
    return ex, [scn("files", f, Run("plain"), Run("spaces and globs"), Run("one"), Run("empty"), Run("blank lines"), Run("no newline"), Run("my file")), scn("usage", f, Run(stderr="nonempty"), Run("nope"))]


# ------------------------------------------------------------------------------------------------ 12. run inside a directory

BUG_INSIDE = dd('''
    #!/bin/bash
    # inside.sh DIR CMD [ARG...] : run CMD inside DIR
    cd $1
    shift
    $@
''')
REF_INSIDE = dd('''
    #!/bin/bash
    # inside.sh DIR CMD [ARG...] : run CMD inside DIR
    [ $# -ge 2 ] || { echo "usage: inside.sh DIR CMD [ARG...]" >&2; exit 2; }
    dir=$1
    shift
    cd -- "$dir" 2>/dev/null || { echo "error: cannot enter $dir" >&2; exit 2; }
    exec "$@"
''')


def make_inside(rng):
    ex = scn("example", {"w/a.txt": F("1"), "w/b.txt": F("2")}, Run("w", "ls"))
    f = {"my dir/one": F("1"), "my dir/two words": F("2"), "-dash/z": F("3"), "other/o": F("4")}
    return ex, [scn("runs in the directory", f, Run("my dir", "ls", "-1"), Run("./-dash", "touch", "made here"), Run("my dir", "sh", "-c", "echo $0-$#; exit 4", "arg x", "y"), Run("my dir", "cat", "two words")),
                scn("errors", f, Run("nope", "touch", "should not exist", stderr="nonempty"), Run("my dir"), Run(), Run("other", "touch", "x y"))]


SPECS = [
    S("fix-argument-loop", 1,
      "`showargs.sh` should print each of its arguments on a line of its own, but it splits arguments with spaces and expands `*`. Fix it.",
      "`bash showargs.sh ARG...` prints one line `arg: <argument>` per argument, in order, exactly as given: arguments may contain spaces, `*`, `?`, quotes, a leading dash, or be empty. No arguments: no output.",
      REF_ARGS, make_args, script="showargs.sh", buggy=BUG_ARGS, title="Print arguments", wrong=(BUG_ARGS,)),
    S("fix-empty-test", 1,
      "`isempty.sh` is meant to say whether each argument is the empty string, but spaces and option-like arguments confuse it. Fix the test.",
      "`bash isempty.sh ARG...` prints, for every argument in order, `empty` if the argument has zero length and `non-empty` otherwise (a single space is non-empty; so is `-z` or `!`). No arguments: no output.",
      REF_EMPTY, make_empty, script="isempty.sh", buggy=BUG_EMPTY, title="Emptiness test", wrong=(BUG_EMPTY,)),
    S("fix-pattern-compare", 2,
      "`equal.sh` compares two strings, yet `equal.sh abc 'a*'` says they are equal. Make it compare literally.",
      "`bash equal.sh A B` prints `equal` and exits 0 when the two arguments are the identical string (case-sensitive, no pattern matching of any kind: `*`, `?` and `[...]` are ordinary characters) and prints `different` and exits 1 otherwise. "
      "Any other number of arguments: usage message on stderr and exit status 2.",
      REF_EQ, make_eq, script="equal.sh", buggy=BUG_EQ, title="Literal string compare", wrong=(BUG_EQ,)),
    S("fix-heredoc-expansion", 2,
      "`mkconfig.sh` writes a `config.ini` but the shell expands `$HOME`, backticks and `$5` while generating it, and the file ends up with the wrong text. The file should contain those pieces literally (only the name is substituted).",
      "`bash mkconfig.sh NAME` (exactly one argument, otherwise usage on stderr and exit 2) overwrites `config.ini` in the current directory with these lines, `NAME` being the argument used verbatim (whatever characters it has): "
      "`[app]`, `name=NAME`, `home=$HOME/apps/NAME`, ``started=`date +%s` ``, `price=costs $5 and 50% off`, `shell=$SHELL -l`. Apart from `NAME`, every `$` and backtick above is literal text in the file; nothing is expanded or executed.",
      REF_CONF, make_conf, script="mkconfig.sh", buggy=BUG_CONF, title="Generate a config file", wrong=(BUG_CONF,)),
    S("fix-leading-zero-sum", 2,
      "`sumn.sh` adds up numbers, but `sumn.sh 08 09` blows up with a base error. Numbers with leading zeros are plain decimals here. Fix it and reject non-numbers.",
      "`bash sumn.sh N...` prints the sum of its arguments, each a non-empty string of decimal digits (leading zeros allowed and meaning nothing: `010` is ten; values stay far below 2^63). No arguments: `0`. "
      "An argument that is not made only of digits (empty, signs, dots, `0x10`...) prints `bad number: <argument>` on stderr and exits with status 2 without printing the sum.",
      REF_SUMN, make_sumn, script="sumn.sh", buggy=BUG_SUMN, title="Sum with leading zeros", wrong=(BUG_SUMN,)),
    S("fix-join-lines", 2,
      "`joinlines.sh` joins the lines of a file with commas but wrecks lines that contain spaces, globs or leading blanks. Rewrite it so the lines come through untouched.",
      "`bash joinlines.sh FILE` prints the lines of `FILE` joined with a single comma between them, each line exactly as it is in the file (inner, leading and trailing blanks, `*` and `[x]` untouched; an empty line is an empty item), followed by a newline. "
      "An empty file prints nothing. A final line without trailing newline counts as a line. A missing file or wrong number of arguments: usage message on stderr, exit status 2.",
      REF_JOIN, make_join, script="joinlines.sh", buggy=BUG_JOIN, title="Join lines with commas", wrong=(BUG_JOIN,)),
    S("fix-forwarded-arguments", 2,
      "`forward.sh` hands its arguments to `./target.sh` after `--via-forward`, but arguments with spaces or stars arrive mangled. `target.sh` is fine; fix `forward.sh`.",
      "`bash forward.sh ARG...` runs `./target.sh --via-forward ARG...` so that `target.sh` sees exactly the same arguments (same count, same text: spaces, `*`, empty strings, leading dashes) after `--via-forward`, and the exit status and output are those of `target.sh`. "
      "`target.sh` (already in the repository) prints `args: N` and then every argument in brackets; do not change it.",
      REF_FWD, make_fwd, script="forward.sh", buggy=BUG_FWD, extra={"target.sh": TARGET}, title="Forward arguments", wrong=(BUG_FWD,)),
    S("fix-dir-list", 3,
      "`dirs.sh` takes a colon-separated list of directories and reports which exist, but directory names with spaces or glob characters break it. Fix the splitting and the tests.",
      "`bash dirs.sh LIST` splits `LIST` at colons and prints for every **non-empty** entry, in order, `ok: <entry>` if it is an existing directory and `missing: <entry>` otherwise. Entries may contain spaces, a leading dash or glob characters like `*`, which must be taken literally. "
      "Empty entries (`a::b`, a leading or trailing colon, or an empty list) are skipped. Wrong number of arguments: usage message on stderr, exit 2.",
      REF_DIRS, make_dirs, script="dirs.sh", buggy=BUG_DIRS, title="Check a list of directories", wrong=(BUG_DIRS,)),
    S("fix-wrapper-log", 3,
      "`wrapper.sh` logs a command line to `wrapper.log` and runs the command, but arguments with spaces are split on the way and the log line is useless for replaying the command. Fix it.",
      "`bash wrapper.sh CMD [ARG...]` appends one line to `wrapper.log` in the current directory: a `+` followed by each of `CMD` and the arguments preceded by a space and quoted as `printf %q` does, so the line can be pasted into a shell to replay the command. "
      "Then it runs the command with the arguments exactly as received and exits with its status (output passes through). No arguments: usage message on stderr and exit status 2, no log line.",
      REF_WRAP, make_wrap, script="wrapper.sh", buggy=BUG_WRAP, title="Logging wrapper", wrong=(BUG_WRAP,)),
    S("fix-cleantmp", 2,
      "`cleantmp.sh` deletes the `.tmp` files of a directory and reports how many, but it breaks on a directory with a space in its name and prints an error when nothing matches. Fix it.",
      "`bash cleantmp.sh DIR` deletes every regular file whose name ends in `.tmp` directly inside `DIR` (hidden ones included; directories whose name ends in `.tmp` stay) and prints `removed N files` (`N` may be 0). "
      "A `DIR` that is not a directory, or a missing argument, prints a message on stderr and exits with status 2. Any file name must work.",
      REF_RMTMP, make_rmtmp, script="cleantmp.sh", buggy=BUG_RMTMP, title="Delete .tmp files", wrong=(BUG_RMTMP,)),
    S("fix-run-inside", 3,
      "`inside.sh` runs a command inside a directory, but it breaks on directory names with spaces, splits the command's arguments, and keeps going in the wrong directory when `cd` fails. Fix it.",
      "`bash inside.sh DIR CMD [ARG...]` changes to `DIR` and runs `CMD ARG...` there with the arguments exactly as given; its exit status is the command's. If `DIR` cannot be entered it prints `error: cannot enter DIR` on stderr and exits with status 2 without running anything. "
      "Fewer than two arguments: usage message on stderr, exit status 2. Directory names may contain spaces or start with a dash (given as `./-dash`).",
      REF_INSIDE, make_inside, script="inside.sh", buggy=BUG_INSIDE, title="Run a command inside a directory", wrong=(BUG_INSIDE,)),
    S("fix-search-eval", 3,
      "`search.sh` builds a grep command string and `eval`s it. Patterns with spaces or quotes break it, and a pattern like `x; touch pwned` runs arbitrary commands. Rewrite it safely.",
      "`bash search.sh [-i] [-w] PATTERN FILE...` runs `grep -n` on the files with `-i` (ignore case) and/or `-w` (whole words) if given and prints grep's output unchanged (`FILE:LINE:text` for several files, `LINE:text` for one); the exit status is grep's (1 when nothing matches). "
      "`PATTERN` is a basic regular expression passed to grep as one argument, whatever characters it contains; nothing in it may be executed by the shell. Too few arguments or an unknown option: usage message on stderr, exit status 2.",
      REF_SEARCH, make_search, script="search.sh", buggy=BUG_SEARCH, title="Safe grep wrapper", wrong=(BUG_SEARCH,)),
]


@family("shell-quoting-fixes", category="shell", lang="bash", kind="fix", n=len(SPECS),
        summary="repair quoting, word-splitting, glob, heredoc, eval and arithmetic-base bugs in small bash tools")
def quoting_fixes(rng, n):
    return K.shell_tasks("quoting-fixes", SPECS, rng, n)
