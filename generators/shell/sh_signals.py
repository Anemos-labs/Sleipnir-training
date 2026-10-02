"""Shell tasks: traps, signals, cleanup and process control: temp dirs, atomic writes, locks, timeouts, deferred cleanups, parallel jobs."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec
ENV = {"TMPDIR": "./scratch"}
SCR = {"scratch": D()}


# ------------------------------------------------------------------------------------------------ 1. temporary work directory

REF_TEMPDIR = dd('''
    #!/usr/bin/env bash
    # with-tempdir.sh CMD [ARG...] : run CMD with $WORKDIR pointing to a fresh scratch directory that is always removed afterwards
    [ $# -gt 0 ] || { echo "usage: with-tempdir.sh CMD [ARG...]" >&2; exit 2; }
    WORKDIR=$(mktemp -d) || exit 1
    export WORKDIR
    trap 'rm -rf -- "$WORKDIR"' EXIT
    trap 'exit 143' TERM
    trap 'exit 130' INT
    trap 'exit 129' HUP
    "$@"
    exit $?
''')


def make_tempdir(rng):
    ex = scn("example", SCR, Run("sh", "-c", 'touch "$WORKDIR/x"; echo made a file', env=ENV))
    return ex, [scn("normal and failing commands", SCR, Run("sh", "-c", 'touch "$WORKDIR/x"; echo ok', env=ENV), Run("sh", "-c", 'touch "$WORKDIR/y"; exit 3', env=ENV), Run("sh", "-c", 'test -d "$WORKDIR" && ls -A "$WORKDIR" | wc -l', env=ENV)),
                scn("signals", SCR, Run("sh", "-c", 'touch "$WORKDIR/z"; kill -TERM $PPID; sleep 0.3; echo child done', env=ENV), Run("sh", "-c", 'kill -INT $PPID; sleep 0.3', env=ENV), Run("sh", "-c", 'kill -HUP $PPID; sleep 0.3', env=ENV)),
                scn("usage", SCR, Run(env=ENV, stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 2. atomic write

REF_ATOMIC = dd('''
    #!/usr/bin/env bash
    # atomic-write.sh FILE : replace FILE with standard input, all or nothing (a line FAIL in the input aborts the write)
    [ $# -eq 1 ] || { echo "usage: atomic-write.sh FILE" >&2; exit 2; }
    dir=$(dirname -- "$1")
    [ -d "$dir" ] || { echo "error: no directory $dir" >&2; exit 2; }
    tmp=$(mktemp "$dir/.atomic.XXXXXX") || exit 1
    trap 'rm -f -- "$tmp"' EXIT
    cat > "$tmp" || exit 1
    if grep -qx FAIL "$tmp"; then
      echo "error: input contained FAIL, nothing written" >&2
      exit 1
    fi
    mv -f -- "$tmp" "$1"
''')


def make_atomic(rng):
    ex = scn("example", {"out.txt": F("old\n")}, Run("out.txt", stdin="new content\n"))
    f = {"data/report txt": F("previous\n"), "data/other": F("untouched\n")}
    return ex, [scn("replace and create", f, Run("data/report txt", stdin="line 1\nline 2\n"), Run("data/-new file", stdin="fresh\n"), Run("data/empty", stdin="")),
                scn("a FAIL line aborts the write", f, Run("data/report txt", stdin="ok line\nFAIL\nmore\n", stderr="nonempty"), Run("data/never created", stdin="FAIL\n")),
                scn("lines that merely contain FAIL are fine", f, Run("data/report txt", stdin="FAILED attempt\nnot FAIL here\n")),
                scn("usage", f, Run(stderr="nonempty", stdin=""), Run("nodir/file", stdin="x\n"), Run("a", "b", stdin="x\n"))]


# ------------------------------------------------------------------------------------------------ 3. lock then run

REF_LOCK = dd('''
    #!/usr/bin/env bash
    # lockrun.sh LOCKDIR CMD [ARG...] : run CMD while holding the lock directory LOCKDIR (mkdir is atomic); stale locks are taken over
    lock=${1:-}
    [ -n "$lock" ] && [ $# -ge 2 ] || { echo "usage: lockrun.sh LOCKDIR CMD [ARG...]" >&2; exit 2; }
    shift
    if ! mkdir "$lock" 2>/dev/null; then
      pid=$(cat "$lock/pid" 2>/dev/null || true)
      if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "locked by $pid" >&2
        exit 75
      fi
      rm -rf -- "$lock"
      mkdir "$lock" 2>/dev/null || { echo "cannot take the lock" >&2; exit 75; }
    fi
    echo $$ > "$lock/pid"
    trap 'rm -rf -- "$lock"' EXIT
    trap 'exit 143' TERM
    trap 'exit 130' INT
    "$@"
    exit $?
''')


def make_lock(rng):
    ex = scn("example", {}, Run("lock.d", "echo", "hello"))
    return ex, [scn("free lock, status passes through", {}, Run("lock.d", "sh", "-c", 'test -f lock.d/pid && echo holding; exit 7')),
                scn("stale and empty locks are taken over", {"stale.d/pid": F("999999\n"), "empty.d": D(), "file-lock": F("junk\n")}, Run("stale.d", "echo", "took stale"), Run("empty.d", "echo", "took empty"), Run("file-lock", "echo", "took file")),
                scn("a held lock blocks a second run", {}, Run("lock.d", "sh", "-c", 'bash "$SHX_SCRIPT" lock.d echo inner; echo "inner status $?"; test -d lock.d && echo still held')),
                scn("lock released after a kill", {}, Run("lock.d", "sh", "-c", "kill -TERM $PPID; sleep 0.3"), Run("lock.d", "echo", "free again")),
                scn("usage", {}, Run("lock.d", stderr="nonempty"), Run(stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 4. timeout

REF_TIMEOUT = dd('''
    #!/usr/bin/env bash
    # deadline.sh SECONDS CMD [ARG...] : run CMD, killing it and everything it started when SECONDS pass (exit 124)
    [ $# -ge 2 ] && [[ $1 =~ ^[0-9]+(\\.[0-9]+)?$ ]] || { echo "usage: deadline.sh SECONDS CMD [ARG...]" >&2; exit 2; }
    secs=$1
    shift
    timeout -k 1 "$secs" "$@"
    rc=$?
    [ "$rc" -eq 124 ] && echo "timed out after ${secs}s" >&2
    exit "$rc"
''')


def make_timeout(rng):
    ex = scn("example", {}, Run("1", "sh", "-c", "sleep 5; echo never"))
    return ex, [scn("finishes in time, status passes", {}, Run("3", "sh", "-c", "echo quick; exit 9"), Run("3", "true"), Run("0.5", "false")),
                scn("timeouts", {}, Run("1", "sh", "-c", "echo start; sleep 5; echo never", stderr="nonempty"), Run("1", "sleep", "10")),
                scn("descendants are killed too", {}, Run("1", "sh", "-c", "(sleep 2; touch late) & wait"), Run("3", "true", ops=[{"op": "sleep", "s": 2.5}])),
                scn("usage", {}, Run(stderr="nonempty"), Run("1"), Run("soon", "true"))]


# ------------------------------------------------------------------------------------------------ 5. capture output

REF_CAPTURE = dd('''
    #!/usr/bin/env bash
    # capture.sh CMD [ARG...] : run CMD with stdout, stderr and the exit code stored in stdout.txt, stderr.txt and status.txt
    [ $# -gt 0 ] || { echo "usage: capture.sh CMD [ARG...]" >&2; exit 2; }
    "$@" > stdout.txt 2> stderr.txt
    echo $? > status.txt
    exit 0
''')


def make_capture(rng):
    ex = scn("example", {}, Run("sh", "-c", "echo out; echo err >&2; exit 4"))
    return ex, [scn("streams and status", {}, Run("sh", "-c", "echo to-out; echo to-err >&2; exit 3"), Run("echo", "second run overwrites"), Run("sh", "-c", "printf 'no newline'; printf 'e' >&2"), Run("false")),
                scn("arguments with spaces", {}, Run("printf", "[%s]\\n", "a b", "*", "-n")), scn("usage", {}, Run(stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 6. deferred cleanups

REF_DEFER = dd('''
    #!/usr/bin/env bash
    # steps.sh STEP... : STEP is ok:NAME or fail:NAME. Run the steps in order, stop at the first failure, then clean up in reverse order
    [ $# -gt 0 ] || { echo "usage: steps.sh (ok|fail):NAME..." >&2; exit 2; }
    for s in "$@"; do
      [[ $s =~ ^(ok|fail):.+$ ]] || { echo "bad step: $s" >&2; exit 2; }
    done
    done_steps=()
    status=0
    cleanup() {
      local i
      for ((i = ${#done_steps[@]} - 1; i >= 0; i--)); do echo "cleanup ${done_steps[i]}"; done
    }
    trap cleanup EXIT
    for s in "$@"; do
      name=${s#*:}
      echo "run $name"
      done_steps+=("$name")
      if [ "${s%%:*}" = fail ]; then status=1; break; fi
    done
    exit "$status"
''')


def make_defer(rng):
    ex = scn("example", {}, Run("ok:db", "ok:cache", "fail:web", "ok:never"))
    return ex, [scn("all fine", {}, Run("ok:a", "ok:b b", "ok:c")), scn("failure in the middle", {}, Run("ok:mount", "fail:copy files", "ok:later"), Run("fail:only")), scn("usage", {}, Run(stderr="nonempty"), Run("ok:a", "maybe:b"), Run("ok:", "ok:b"), Run("ok"))]


# ------------------------------------------------------------------------------------------------ 7. parallel jobs

REF_PAR = dd('''
    #!/usr/bin/env bash
    # parallel.sh N CMD [ARG...] : run N copies of CMD at the same time (JOB=1..N), then report "job I: STATUS" in order
    n=${1:-}
    case $n in ''|*[!0-9]*|0) echo "usage: parallel.sh N CMD [ARG...]" >&2; exit 2 ;; esac
    [ "$n" -le 16 ] && [ $# -ge 2 ] || { echo "usage: parallel.sh N CMD [ARG...]  (N from 1 to 16)" >&2; exit 2; }
    shift
    pids=()
    for ((i = 1; i <= n; i++)); do
      JOB=$i "$@" &
      pids+=($!)
    done
    fail=0
    for ((i = 1; i <= n; i++)); do
      wait "${pids[i - 1]}"
      st=$?
      echo "job $i: $st"
      [ "$st" -eq 0 ] || fail=1
    done
    exit "$fail"
''')


def make_par(rng):
    ex = scn("example", {}, Run("3", "sh", "-c", 'echo "$JOB" > "out.$JOB"'))
    return ex, [scn("statuses", {}, Run("4", "sh", "-c", 'echo "job $JOB ran" > "out.$JOB"; exit $((JOB % 2 * 5))')), scn("really concurrent", {}, Run("3", "sh", "-c", 'sleep "0.$((9 - 3 * JOB))"; echo "$JOB" >> order')),
                scn("single job and all ok", {}, Run("1", "echo", "solo"), Run("2", "true")), scn("usage", {}, Run(stderr="nonempty"), Run("0", "true"), Run("17", "true"), Run("x", "true"), Run("2"))]


# ------------------------------------------------------------------------------------------------ 8. count signals

REF_SIG = dd('''
    #!/usr/bin/env bash
    # sigcount.sh CMD [ARG...] : run CMD; count the SIGUSR1 signals this script receives meanwhile; print "signals: N"; exit with CMD's status
    [ $# -gt 0 ] || { echo "usage: sigcount.sh CMD [ARG...]" >&2; exit 2; }
    n=0
    trap 'n=$((n + 1))' USR1
    "$@" &
    pid=$!
    wait "$pid"
    rc=$?
    while [ "$rc" -gt 128 ] && kill -0 "$pid" 2>/dev/null; do
      wait "$pid"
      rc=$?
    done
    echo "signals: $n"
    exit "$rc"
''')


def make_sig(rng):
    ex = scn("example", {}, Run("sh", "-c", "for i in 1 2; do kill -USR1 $PPID; sleep 0.2; done"))
    return ex, [scn("signals during the command", {}, Run("sh", "-c", "for i in 1 2 3 4; do kill -USR1 $PPID; sleep 0.2; done; echo sent 4; exit 6"), Run("sh", "-c", "kill -USR1 $PPID; sleep 0.3"), Run("true")),
                scn("output passes through and stdin is not stolen", {}, Run("cat", stdin="through\n"), Run("sh", "-c", "echo $((1+1))")), scn("usage", {}, Run(stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 9. fix leaky temp files

BUG_LEAK = dd('''
    #!/bin/bash
    # top3.sh FILE : the three largest numbers in FILE (one per line); a line "BAD" aborts with status 3
    tmp=$(mktemp)
    sort -rn "$1" > $tmp
    if grep -q BAD $tmp; then
      echo "bad input" >&2
      exit 3
    fi
    head -3 $tmp
    rm $tmp
''')
REF_LEAK = dd('''
    #!/bin/bash
    # top3.sh FILE : the three largest numbers in FILE (one per line); a line "BAD" aborts with status 3
    [ $# -eq 1 ] && [ -r "$1" ] || { echo "usage: top3.sh FILE" >&2; exit 2; }
    tmp=$(mktemp) || exit 1
    trap 'rm -f -- "$tmp"' EXIT
    sort -rn -- "$1" > "$tmp"
    if grep -q BAD "$tmp"; then
      echo "bad input" >&2
      exit 3
    fi
    head -n 3 "$tmp"
''')


def make_leak(rng):
    ex = scn("example", {**SCR, "n.txt": F("5\n40\n7\n12\n")}, Run("n.txt", env=ENV))
    f = {**SCR, "nums": F("3\n10\n2\n99\n7\n"), "my nums.txt": F("1\n2\n"), "bad.txt": F("5\nBAD\n6\n"), "empty": F("")}
    return ex, [scn("scratch stays empty", f, Run("nums", env=ENV), Run("my nums.txt", env=ENV), Run("empty", env=ENV)), scn("bad input leaves nothing behind", f, Run("bad.txt", env=ENV, stderr="nonempty"), Run("nums", env=ENV)),
                scn("usage", f, Run(env=ENV, stderr="nonempty"), Run("missing", env=ENV))]


SPECS = [
    S("tempdir-always-removed", 3,
      "Write `with-tempdir.sh CMD...`: run a command with `$WORKDIR` set to a fresh scratch directory, removing the directory however the command ends - normally, with an error or when the script is signalled.",
      "`bash with-tempdir.sh CMD [ARG...]` creates a scratch directory with `mktemp -d` (the tests point `TMPDIR` at a directory inside the working directory), exports its path as `WORKDIR`, runs the command (arguments passed exactly) and removes the directory afterwards in every case. "
      "The script's exit status is the command's status. If the script receives `SIGTERM`, `SIGINT` or `SIGHUP` (the tests send them from inside the command to its parent) it must still clean up and exit with 143, 130 or 129 respectively once the command has returned. No command: usage message on stderr, exit status 2.",
      REF_TEMPDIR, make_tempdir, script="with-tempdir.sh", title="Scratch directory that always goes away", wrong=("#!/bin/bash\nWORKDIR=$(mktemp -d); export WORKDIR\n\"$@\"\nrc=$?\nrm -rf \"$WORKDIR\"\nexit $rc\n",)),
    S("atomic-file-replace", 3,
      "Write `atomic-write.sh FILE`: replace a file with standard input in an all-or-nothing way, leaving no temporary files behind even on failure.",
      "`bash atomic-write.sh FILE` writes standard input to a temporary file **in the same directory as `FILE`** and only then moves it over `FILE`, so a reader sees the old or the new content, never a mix. If a line of the input is exactly `FAIL` nothing is written: print an error on stderr and exit 1, leaving `FILE` (and the directory) as they were; "
      "no temporary file may remain on any path. The directory of `FILE` must exist (else exit 2 with a message); the wrong number of arguments: usage message on stderr, exit status 2.",
      REF_ATOMIC, make_atomic, script="atomic-write.sh", title="Atomic file replacement", wrong=("#!/bin/bash\ncat > \"$1\"\n",)),
    S("lock-directory-runner", 4,
      "Write `lockrun.sh LOCKDIR CMD...`: run a command under a lock taken with `mkdir`, refuse to run when someone else holds it, and take over stale locks.",
      "`bash lockrun.sh LOCKDIR CMD [ARG...]` takes the lock by creating the directory `LOCKDIR` with `mkdir` and writing its own PID into `LOCKDIR/pid`, runs the command and removes `LOCKDIR` when it ends, whatever the reason (also on `SIGTERM` or `SIGINT`, then exit 143 or 130). Its exit status is the command's. "
      "If `LOCKDIR` already exists: when `LOCKDIR/pid` names a process that is alive (`kill -0` succeeds) print `locked by PID` on stderr and exit with status 75 without running anything and without touching the lock; otherwise the lock is stale (dead PID, missing or empty pid file, or `LOCKDIR` not even a directory) and the script removes it and proceeds. "
      "The environment variable `SHX_SCRIPT` holds the path of the script in the tests so that a command can try the lock itself. Missing arguments: usage message on stderr, exit status 2.",
      REF_LOCK, make_lock, script="lockrun.sh", title="Lock-directory runner", wrong=("#!/bin/bash\nshift\n\"$@\"\n",)),
    S("deadline-runner", 2,
      "Write `deadline.sh SECONDS CMD...`: run a command and kill it - and anything it started - when the time is up.",
      "`bash deadline.sh SECONDS CMD [ARG...]` (`SECONDS` an integer or decimal number) runs the command; if it is still running after `SECONDS` seconds the command **and all processes it started** are killed, `timed out after SECONDSs` is printed on stderr and the exit status is 124. "
      "Otherwise the exit status is the command's. Missing arguments or a non-numeric `SECONDS`: usage message on stderr, exit status 2. (The tests check that a background process started by the command does not survive.)",
      REF_TIMEOUT, make_timeout, script="deadline.sh", title="Deadline runner", wrong=("#!/bin/bash\nsecs=$1; shift\n\"$@\" &\nsleep $secs; kill $! 2>/dev/null\n",)),
    S("capture-streams", 1,
      "Write `capture.sh CMD...`: run a command and store its stdout, stderr and exit code in three files in the current directory.",
      "`bash capture.sh CMD [ARG...]` runs the command (arguments exactly as given) with its standard output written to `stdout.txt`, its standard error to `stderr.txt` (both overwritten each time) and its exit status as a decimal number plus newline to `status.txt`. "
      "The script itself prints nothing and exits 0 whatever the command's status. No command: usage message on stderr, exit status 2.",
      REF_CAPTURE, make_capture, script="capture.sh", title="Capture command output", wrong=("#!/bin/bash\n\"$@\" > stdout.txt\n",)),
    S("deferred-cleanups", 3,
      "Write `steps.sh STEP...`: run named steps in order, stop at the first failure, and undo the steps that started in reverse order, like deferred cleanups.",
      "`bash steps.sh STEP...` where each `STEP` is `ok:NAME` or `fail:NAME` (`NAME` non-empty, may contain spaces). For each step in order print `run NAME`; a `fail:` step makes the run stop (later steps are not run, not even announced). "
      "When the script ends, print `cleanup NAME` for every step that was started - including the failing one - in the reverse order of starting. Exit status 1 if a step failed, otherwise 0. Invalid steps or no steps at all: usage message on stderr, exit status 2 and nothing on stdout (validate before running anything).",
      REF_DEFER, make_defer, script="steps.sh", title="Deferred cleanups", wrong=("#!/bin/bash\nfor s; do echo \"run ${s#*:}\"; done\n",)),
    S("parallel-job-runner", 3,
      "Write `parallel.sh N CMD...`: start N copies of a command at the same time, wait for all of them and report each one's exit status.",
      "`bash parallel.sh N CMD [ARG...]` (`N` from 1 to 16) starts `N` copies of the command **concurrently**, copy number `i` with the environment variable `JOB=i` (1-based), waits for all of them and then prints `job I: STATUS` for `I = 1..N` in order. "
      "Exit status 0 if every copy exited 0, else 1. A bad `N` or a missing command: usage message on stderr, exit status 2, nothing started. (The tests check that the copies overlap in time.)",
      REF_PAR, make_par, script="parallel.sh", title="Parallel job runner", wrong=("#!/bin/bash\nn=$1; shift\nfor ((i=1;i<=n;i++)); do JOB=$i \"$@\"; echo \"job $i: $?\"; done\n",)),
    S("count-usr1-signals", 4,
      "Write `sigcount.sh CMD...`: run a command and count how many SIGUSR1 signals the script itself receives while it runs.",
      "`bash sigcount.sh CMD [ARG...]` runs the command with its arguments, stdin and stdout passed through, counts every `SIGUSR1` delivered to the script while the command runs (the tests send several, a fraction of a second apart, from inside the command with `kill -USR1 $PPID`), "
      "and after the command ended prints `signals: N` on stdout and exits with the command's status. The script must not stop waiting just because a trapped signal interrupts `wait`. No command: usage message on stderr, exit status 2.",
      REF_SIG, make_sig, script="sigcount.sh", title="Count signals while a command runs", wrong=("#!/bin/bash\nn=0; trap 'n=$((n+1))' USR1\n\"$@\"\nrc=$?\necho \"signals: $n\"\nexit $rc\n",)),
    S("fix-leaked-temp-file", 2,
      "`top3.sh` leaves a temporary file behind when it aborts. Fix it so nothing is left in `TMPDIR`, whichever way it ends, and add the argument check.",
      "`bash top3.sh FILE` sorts the numbers of `FILE` (one per line) in descending order using a temporary file made with `mktemp` and prints the three largest lines (fewer if the file is shorter). "
      "If the file contains a line `BAD` it prints `bad input` on stderr and exits with status 3 without printing numbers. The temporary file must be removed on every exit path (the tests point `TMPDIR` at a directory and check it is empty afterwards). "
      "A missing or unreadable file, or a wrong number of arguments: usage message on stderr, exit status 2.",
      REF_LEAK, make_leak, script="top3.sh", buggy=BUG_LEAK, title="Leaked temp file", wrong=(BUG_LEAK,)),
]


@family("shell-signals-and-cleanup", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="traps, signals and process control in bash: scratch dirs, atomic writes, lock directories, deadlines, deferred cleanups, parallel jobs, signal counting")
def signals_cleanup(rng, n):
    return K.shell_tasks("signals-and-cleanup", SPECS, rng, n)
