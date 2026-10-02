"""Shell scripting pitfalls: word splitting, globbing, subshell counters, octal arithmetic, printf formats (bash)."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A: organising a download folder by file extension.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd(r'''
    # organize

    A bash function library that tidies a download folder. Source it and call `organize_by_ext SRC DEST`; the tests are `bash tests/run.sh`.

    * `ext_of NAME` prints the folder name for a file name: the text after the last dot in lower case (`photo.JPG` is `jpg`, `a.tar.gz` is `gz`), or `noext` when
      the name has no dot.
    * `organize_by_ext SRC DEST` moves every regular file that is directly inside `SRC` into `DEST/<ext_of name>/`. Hidden files (names starting with a dot) and
      sub-directories are left alone. Names may contain anything but a slash: spaces, `*`, `[`, quotes, a leading dash.
    * A file whose target name already exists is **never overwritten**: it is stored as `name-1.ext`, `name-2.ext` ... (the counter goes before the last extension; for
      `noext` files the counter is appended: `README-1`).
    * It prints `moved N files` (N is the number of files actually moved, `moved 0 files` for an empty folder, always the word `files`) and returns 0.
    * If `SRC` is not a directory it prints an error to stderr and returns 1. If a file cannot be moved (for instance `DEST/txt` exists and is a regular file) it
      stops at once, returns 1 and prints nothing to stdout; files not yet moved stay where they were.
''')

A_LIB = dd(r'''
    # Sort the files of a directory into sub-directories by extension.

    ext_of() {
      local name=$1
      case $name in
        *.*) ;;
        *) printf 'noext\n'; return 0 ;;
      esac
      local ext=${name##*.}
      printf '%s\n' "${ext,,}"
    }

    organize_by_ext() {
      local src=$1 dest=$2
      if [ ! -d "$src" ]; then
        echo "organize: not a directory: $src" >&2
        return 1
      fi
      local moved=0 f name ext target n stem suffix
      for f in "$src"/*; do
        [ -f "$f" ] || continue
        name=${f##*/}
        ext=$(ext_of "$name")
        mkdir -p -- "$dest/$ext" || return 1
        target="$dest/$ext/$name"
        if [ -e "$target" ]; then
          case $name in
            *.*) stem=${name%.*}; suffix=.${name##*.} ;;
            *) stem=$name; suffix= ;;
          esac
          n=1
          while [ -e "$dest/$ext/$stem-$n$suffix" ]; do
            n=$((n + 1))
          done
          target="$dest/$ext/$stem-$n$suffix"
        fi
        mv -- "$f" "$target" || return 1
        moved=$((moved + 1))
      done
      echo "moved $moved files"
    }
''')

HARNESS = dd(r'''
    #!/usr/bin/env bash
    cd "$(dirname "$0")/.." || exit 2
    fail=0
    check() {
      if [ "$2" != "$3" ]; then
        printf 'FAIL: %s\n  expected: %s\n  actual:   %s\n' "$1" "$2" "$3"
        fail=1
      fi
    }
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
''')

A_VISIBLE = {
    "tests/run.sh": HARNESS + dd(r'''
        . lib/organize.sh

        mkdir "$tmp/v1"
        touch "$tmp/v1/a.txt" "$tmp/v1/b.jpg"
        out=$(organize_by_ext "$tmp/v1" "$tmp/o1")
        check "summary" "moved 2 files" "$out"
        check "layout" "$(printf './jpg/b.jpg\n./txt/a.txt')" "$(cd "$tmp/o1" && find . -type f | LC_ALL=C sort)"
        check "ext_of" "tgz" "$(ext_of 'x.TGZ')"
        exit $fail
    '''),
}

A_HIDDEN = {
    "tests/run.sh": HARNESS + dd(r'''
        . lib/organize.sh

        layout() { (cd "$1" && find . -type f | LC_ALL=C sort); }
        mk() { local d=$1; shift; mkdir -p "$d"; local f; for f in "$@"; do : > "$d/$f"; done; }

        # extensions
        check "ext_of lower-cases" "jpg" "$(ext_of 'photo.JPG')"
        check "ext_of uses the last dot" "gz" "$(ext_of 'a.tar.gz')"
        check "ext_of without a dot" "noext" "$(ext_of 'README')"
        check "ext_of with spaces" "txt" "$(ext_of 'my notes.final.TXT')"

        # plain run
        mk "$tmp/t1" a.TXT b.txt c.jpg README
        out=$(organize_by_ext "$tmp/t1" "$tmp/o1"); rc=$?
        check "t1 summary" "moved 4 files" "$out"
        check "t1 rc" "0" "$rc"
        check "t1 layout" "$(printf './jpg/c.jpg\n./noext/README\n./txt/a.TXT\n./txt/b.txt')" "$(layout "$tmp/o1")"
        check "t1 source is empty" "" "$(ls -A "$tmp/t1")"

        # awkward names
        mk "$tmp/t2" "my photo.png" "a b c.txt" "star*.md" "[x].md" "it's.txt" '"q".txt' "-dash.txt" "-n"
        out=$(organize_by_ext "$tmp/t2" "$tmp/o2"); rc=$?
        check "t2 summary" "moved 8 files" "$out"
        check "t2 rc" "0" "$rc"
        check "t2 layout" "$(printf './md/[x].md\n./md/star*.md\n./noext/-n\n./png/my photo.png\n./txt/"q".txt\n./txt/-dash.txt\n./txt/a b c.txt\n./txt/it'"'"'s.txt')" "$(layout "$tmp/o2")"
        check "t2 source is empty" "" "$(ls -A "$tmp/t2")"

        # what is left alone
        mk "$tmp/t3" visible.txt .hidden.txt
        mkdir "$tmp/t3/subdir"; : > "$tmp/t3/subdir/inner.txt"
        out=$(organize_by_ext "$tmp/t3" "$tmp/o3")
        check "t3 summary" "moved 1 files" "$out"
        check "t3 destination" "./txt/visible.txt" "$(layout "$tmp/o3")"
        check "t3 left behind" "$(printf './.hidden.txt\n./subdir/inner.txt')" "$(layout "$tmp/t3")"

        # empty and missing sources
        mkdir "$tmp/t4"
        out=$(organize_by_ext "$tmp/t4" "$tmp/o4"); rc=$?
        check "empty summary" "moved 0 files" "$out"
        check "empty rc" "0" "$rc"
        check "empty creates nothing" "" "$(ls -A "$tmp/o4" 2>/dev/null)"
        out=$(organize_by_ext "$tmp/nope" "$tmp/o5" 2>"$tmp/err"); rc=$?
        check "missing source rc" "1" "$rc"
        check "missing source stdout" "" "$out"
        check "missing source message" "organize: not a directory: $tmp/nope" "$(cat "$tmp/err")"

        # nothing is overwritten
        mk "$tmp/o6/txt" a.txt
        printf 'old' > "$tmp/o6/txt/a.txt"
        mk "$tmp/t6" a.txt b.txt README
        printf 'new' > "$tmp/t6/a.txt"
        mk "$tmp/o6/noext" README
        out=$(organize_by_ext "$tmp/t6" "$tmp/o6")
        check "t6 summary" "moved 3 files" "$out"
        check "t6 layout" "$(printf './noext/README\n./noext/README-1\n./txt/a-1.txt\n./txt/a.txt\n./txt/b.txt')" "$(layout "$tmp/o6")"
        check "t6 old content kept" "old" "$(cat "$tmp/o6/txt/a.txt")"
        check "t6 new content kept" "new" "$(cat "$tmp/o6/txt/a-1.txt")"
        mk "$tmp/t7" a.txt
        organize_by_ext "$tmp/t7" "$tmp/o6" >/dev/null
        mk "$tmp/t8" a.txt
        organize_by_ext "$tmp/t8" "$tmp/o6" >/dev/null
        check "counters keep counting" "$(printf './txt/a-1.txt\n./txt/a-2.txt\n./txt/a-3.txt\n./txt/a.txt\n./txt/b.txt')" "$(cd "$tmp/o6" && find txt -type f | LC_ALL=C sort | sed 's|^|./|')"

        # failure to move
        mk "$tmp/t9" a.txt b.jpg
        mkdir "$tmp/o9"; : > "$tmp/o9/txt"
        out=$(organize_by_ext "$tmp/t9" "$tmp/o9" 2>/dev/null); rc=$?
        check "blocked destination rc" "1" "$rc"
        check "blocked destination stdout" "" "$out"
        check "blocked destination keeps the source" "./a.txt" "$(layout "$tmp/t9" | grep a.txt)"

        # the same file name in two extension folders, and big batches
        mkdir "$tmp/t10"
        for i in 1 2 3 4 5 6 7 8 9 10 11 12; do : > "$tmp/t10/file $i.dat"; done
        out=$(organize_by_ext "$tmp/t10" "$tmp/o10")
        check "t10 summary" "moved 12 files" "$out"
        check "t10 count" "12" "$(layout "$tmp/o10" | wc -l | tr -d ' ')"
        exit $fail
    '''),
}


def _a_prompts():
    p = {}
    p["unquoted"] = (
        "The tidy-up script chokes on file names with spaces: `my photo.png` produces `mv: cannot stat 'my'` and `mv: cannot stat 'photo.png'`. "
        "Files with simple names are fine. I expect it is a quoting problem in the move."
    )
    p["ls-loop"] = (
        "Files whose names contain spaces are silently skipped (or split into pieces and reported as missing) when the downloads folder is organised, and "
        "folders in the downloads folder get listed as if they were files. It started when somebody replaced the glob loop by something that reads `ls`."
    )
    p["noext"] = (
        "Files without an extension (`README`, `Makefile`) end up in a folder named after the file itself (`README/README`) instead of `noext/`. "
        "Files with an extension are fine."
    )
    p["overwrite"] = (
        "We lost a document: two downloads called `report.pdf` were organised in different runs and the second silently replaced the first in `pdf/`. The "
        "script is supposed to keep both (`report-1.pdf`). Nothing may ever be overwritten."
    )
    p["counter"] = (
        "The summary line always says `moved 0 files` even though files are moved. People started to think the tool does not work. The files do end up in the "
        "right folders."
    )
    p["mkdir"] = (
        "When a destination folder cannot be created (there is a regular file called `txt` where the `txt` folder should be) the tool prints a pile of `mv` errors, "
        "reports `moved N files` as if all went well, and returns 0, so our cron job never alerts. It must stop at once with a non-zero status "
        "and no summary."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "lib/organize.sh": A_LIB}
    lib = "lib/organize.sh"
    bugs = [
        Bug("mv-with-unquoted-variables", 1, {lib: [('    mv -- "$f" "$target" || return 1\n', '    mv -- $f $target || return 1\n')]}, P["unquoted"]),
        Bug("extension-less-files-get-their-own-folder", 2, {lib: [("  case $name in\n    *.*) ;;\n    *) printf 'noext\\n'; return 0 ;;\n  esac\n", "")]}, P["noext"]),
        Bug("loop-over-ls-output", 3, {lib: [('  for f in "$src"/*; do\n    [ -f "$f" ] || continue\n    name=${f##*/}\n', '  for name in $(ls "$src"); do\n    f="$src/$name"\n    [ -f "$f" ] || continue\n')]}, P["ls-loop"]),
        Bug("existing-files-are-overwritten", 3, {lib: [('    if [ -e "$target" ]; then\n      case $name in\n        *.*) stem=${name%.*}; suffix=.${name##*.} ;;\n        *) stem=$name; suffix= ;;\n      esac\n      n=1\n      while [ -e "$dest/$ext/$stem-$n$suffix" ]; do\n        n=$((n + 1))\n      done\n      target="$dest/$ext/$stem-$n$suffix"\n    fi\n', "")]}, P["overwrite"]),
        Bug("counter-lost-in-a-pipeline", 3, {lib: [('  for f in "$src"/*; do\n', '  printf \'%s\\n\' "$src"/* | while IFS= read -r f; do\n')]}, P["counter"]),
        Bug("mkdir-failure-ignored", 3, {lib: [('    mkdir -p -- "$dest/$ext" || return 1\n', '    mkdir -p -- "$dest/$ext"\n'), ('    mv -- "$f" "$target" || return 1\n    moved=$((moved + 1))\n', '    mv -- "$f" "$target"\n    moved=$((moved + 1))\n')]}, P["mkdir"]),
    ]
    return Base("organize", "bash", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B: release-notes helpers.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd(r'''
    # relnotes

    Helpers of a release script (bash; source `lib/notes.sh`; tests: `bash tests/run.sh`).

    * `version_gt A B`: exit status 0 when version A is newer than B. Versions are dot-separated numbers of any length compared number by number (`1.10.0` is newer
      than `1.9.3`); a missing part counts as 0 (`1.0` and `1.0.0` are equal, neither is newer); leading zeros are ignored (`1.09` equals `1.9`).
    * `bump_patch V`: prints V with its last number increased by one (`1.2.9` gives `1.2.10`; `1.2.09` gives `1.2.10`; `3` gives `4`). Numbers are decimal even with leading zeros.
    * `log_line WORDS...`: prints the words joined with single spaces and a newline, **exactly** as given: `%`, backslashes and a leading `-` are just text.
    * `read_lines FILE`: prints `N: LINE` for every line (N from 1), with each line exactly as in the file (leading spaces, backslashes, trailing spaces kept), including a
      last line that has no newline.
    * `count_lines FILE`: the number of lines; a last line without newline counts.
    * `run_logged CMD...`: runs the command, appends `ok` or `failed (STATUS)` to the file named by `$RUN_LOG`, and returns the command's own exit status.
''')

B_LIB = dd(r'''
    # Helpers for the release script.

    version_gt() {
      local IFS=. i x y
      local -a a=($1) b=($2)
      local n=${#a[@]}
      [ "${#b[@]}" -gt "$n" ] && n=${#b[@]}
      for ((i = 0; i < n; i++)); do
        x=$((10#${a[i]:-0}))
        y=$((10#${b[i]:-0}))
        if [ "$x" -gt "$y" ]; then
          return 0
        fi
        if [ "$x" -lt "$y" ]; then
          return 1
        fi
      done
      return 1
    }

    bump_patch() {
      local v=$1 head last
      case $v in
        *.*) head=${v%.*}.; last=${v##*.} ;;
        *) head=; last=$v ;;
      esac
      printf '%s%d\n' "$head" $((10#$last + 1))
    }

    log_line() {
      printf '%s\n' "$*"
    }

    read_lines() {
      local n=0 line
      while IFS= read -r line || [ -n "$line" ]; do
        n=$((n + 1))
        printf '%d: %s\n' "$n" "$line"
      done < "$1"
    }

    count_lines() {
      grep -c '' "$1"
    }

    run_logged() {
      local status
      "$@"
      status=$?
      if [ "$status" -eq 0 ]; then
        echo ok >> "$RUN_LOG"
      else
        echo "failed ($status)" >> "$RUN_LOG"
      fi
      return "$status"
    }
''')

B_VISIBLE = {
    "tests/run.sh": HARNESS + dd(r'''
        . lib/notes.sh

        version_gt 1.2.0 1.1.9; check "newer" "0" "$?"
        version_gt 1.1.9 1.2.0; check "older" "1" "$?"
        check "bump" "1.2.4" "$(bump_patch 1.2.3)"
        check "log" "hello world" "$(log_line hello world)"
        printf 'a\nb\n' > "$tmp/f"
        check "count" "2" "$(count_lines "$tmp/f")"
        exit $fail
    '''),
}

B_HIDDEN = {
    "tests/run.sh": HARNESS + dd(r'''
        . lib/notes.sh

        gt() { version_gt "$1" "$2"; echo $?; }
        check "1.10.0 > 1.9.3" "0" "$(gt 1.10.0 1.9.3)"
        check "1.9.3 > 1.10.0" "1" "$(gt 1.9.3 1.10.0)"
        check "equal" "1" "$(gt 1.2.3 1.2.3)"
        check "2.0 > 1.99.99" "0" "$(gt 2.0 1.99.99)"
        check "1.0.1 > 1.0" "0" "$(gt 1.0.1 1.0)"
        check "1.0 > 1.0.1" "1" "$(gt 1.0 1.0.1)"
        check "1.0 vs 1.0.0" "1" "$(gt 1.0 1.0.0)"
        check "1.0.0 vs 1.0" "1" "$(gt 1.0.0 1.0)"
        check "1.09 vs 1.9" "1" "$(gt 1.09 1.9)"
        check "1.10 > 1.9" "0" "$(gt 1.10 1.9)"
        check "10.0.0 > 9.99.99" "0" "$(gt 10.0.0 9.99.99)"
        check "0.0.0.1 > 0.0.0" "0" "$(gt 0.0.0.1 0.0.0)"
        check "08 vs 7" "0" "$(gt 1.08 1.7)"
        check "100 > 99" "0" "$(gt 100 99)"

        check "bump simple" "1.2.4" "$(bump_patch 1.2.3)"
        check "bump carry" "1.2.10" "$(bump_patch 1.2.9)"
        check "bump leading zero" "1.2.10" "$(bump_patch 1.2.09)"
        check "bump 08" "1.2.9" "$(bump_patch 1.2.08)"
        check "bump 007" "1.2.8" "$(bump_patch 1.2.007)"
        check "bump single" "4" "$(bump_patch 3)"
        check "bump big" "0.0.100" "$(bump_patch 0.0.99)"
        check "bump zero" "1.0.1" "$(bump_patch 1.0.0)"

        check "log words" "a b c" "$(log_line a b c)"
        check "log percent" "100% done" "$(log_line '100% done')"
        check "log format directives" '%s %d %x' "$(log_line '%s %d %x')"
        check "log backslash" 'a\nb\tc' "$(log_line 'a\nb\tc')"
        check "log dash" "-n" "$(log_line -n)"
        check "log nothing" "" "$(log_line)"
        check "log percent in a word" "50%" "$(log_line 50%)"

        printf '  indented\nback\\slash\ntrailing space \nlast' > "$tmp/l1"
        expected=$(printf '1:   indented\n2: back\\slash\n3: trailing space \n4: last')
        check "read_lines keeps lines exactly" "$expected" "$(read_lines "$tmp/l1")"
        printf 'one\ntwo\n' > "$tmp/l2"
        check "read_lines with final newline" "$(printf '1: one\n2: two')" "$(read_lines "$tmp/l2")"
        printf 'only' > "$tmp/l3"
        check "read_lines single unterminated line" "1: only" "$(read_lines "$tmp/l3")"
        : > "$tmp/l4"
        check "read_lines empty file" "" "$(read_lines "$tmp/l4")"
        printf '\n\nx\n' > "$tmp/l5"
        check "read_lines blank lines" "$(printf '1: \n2: \n3: x')" "$(read_lines "$tmp/l5")"

        check "count unterminated" "4" "$(count_lines "$tmp/l1" | tr -d ' ')"
        printf 'a\nb\nc' > "$tmp/c1"
        check "count without final newline" "3" "$(count_lines "$tmp/c1")"
        printf 'a\nb\n' > "$tmp/c2"
        check "count with final newline" "2" "$(count_lines "$tmp/c2")"
        check "count empty" "0" "$(count_lines "$tmp/l4")"
        printf '\n' > "$tmp/c3"
        check "count a single newline" "1" "$(count_lines "$tmp/c3")"

        RUN_LOG="$tmp/run.log"; : > "$RUN_LOG"
        run_logged true; rc1=$?
        run_logged false; rc2=$?
        run_logged sh -c 'exit 7'; rc3=$?
        check "run_logged statuses" "0 1 7" "$rc1 $rc2 $rc3"
        check "run_logged log" "$(printf 'ok\nfailed (1)\nfailed (7)')" "$(cat "$RUN_LOG")"
        exit $fail
    '''),
}


def _b_prompts():
    p = {}
    p["gt"] = (
        "The release script thinks 1.9.3 is newer than 1.10.0 and refuses to publish 1.10.0 (it also says 100 is older than 99). Versions must be compared "
        "number by number, not as text."
    )
    p["octal"] = (
        "`bump_patch 1.2.09` prints `value too great for base (error token is \"09\")` and our release job fails on every patch number that starts with a 0 "
        "and contains an 8 or a 9; `bump_patch 1.2.07` works. Numbers are decimal."
    )
    p["printf"] = lambda c: (
        "Log lines containing a percent sign are mangled: `log_line '100% done'` prints `"
        + c.probe(". lib/notes.sh\nlog_line '100% done'\n")[1]
        + "` instead of `100% done`, messages with `%s` or `%d` print blanks or zeros, and a literal `\\n` in a message turns into a real newline. "
        "The message must be printed exactly as given."
    )
    p["read-r"] = (
        "The changelog preview eats backslashes and leading spaces: a line like `  indented\\path` is printed as `indentedpath`. `read_lines` must print the lines "
        "exactly as they are in the file."
    )
    p["last-line"] = (
        "The last line of a notes file is missing from the preview when the file does not end with a newline (editors on some systems do not add one). "
        "`read_lines` must include it."
    )
    p["wc"] = (
        "`count_lines` says 2 for a three-line file that has no trailing newline, so our \"3 changes\" banner is off by one for those files."
    )
    p["status"] = (
        "`run_logged` writes \"failed (1)\" to the log for a failing command, but returns 0 to its caller, so `set -e` scripts and `||` handlers never "
        "notice the failure. It must return the command's own exit status."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "lib/notes.sh": B_LIB}
    lib = "lib/notes.sh"
    gt_bug = ('''version_gt() {
  local IFS=. i x y
  local -a a=($1) b=($2)
  local n=${#a[@]}
  [ "${#b[@]}" -gt "$n" ] && n=${#b[@]}
  for ((i = 0; i < n; i++)); do
    x=$((10#${a[i]:-0}))
    y=$((10#${b[i]:-0}))
    if [ "$x" -gt "$y" ]; then
      return 0
    fi
    if [ "$x" -lt "$y" ]; then
      return 1
    fi
  done
  return 1
}
''', '''version_gt() {
  [[ "$1" > "$2" ]]
}
''')
    bugs = [
        Bug("count-lines-by-newlines", 2, {lib: [("  grep -c '' \"$1\"\n", "  wc -l < \"$1\"\n")]}, P["wc"]),
        Bug("patch-number-read-as-octal", 1, {lib: [("  printf '%s%d\\n' \"$head\" $((10#$last + 1))\n", "  printf '%s%d\\n' \"$head\" $((last + 1))\n")]}, P["octal"]),
        Bug("versions-compared-as-text", 3, {lib: [gt_bug]}, P["gt"]),
        Bug("message-used-as-a-printf-format", 3, {lib: [("  printf '%s\\n' \"$*\"\n", "  printf \"$*\\n\"\n")]}, P["printf"]),
        Bug("read-without-ifs-and-r", 3, {lib: [("  while IFS= read -r line || [ -n \"$line\" ]; do\n", "  while read line || [ -n \"$line\" ]; do\n")]}, P["read-r"]),
        Bug("unterminated-last-line-dropped", 2, {lib: [("  while IFS= read -r line || [ -n \"$line\" ]; do\n", "  while IFS= read -r line; do\n")]}, P["last-line"]),
        Bug("exit-status-taken-after-the-if", 3, {lib: [("  local status\n  \"$@\"\n  status=$?\n  if [ \"$status\" -eq 0 ]; then\n    echo ok >> \"$RUN_LOG\"\n  else\n    echo \"failed ($status)\" >> \"$RUN_LOG\"\n  fi\n  return \"$status\"\n",
                                                        "  \"$@\"\n  if [ $? -eq 0 ]; then\n    echo ok >> \"$RUN_LOG\"\n  else\n    echo \"failed ($?)\" >> \"$RUN_LOG\"\n  fi\n  return $?\n")]}, P["status"]),
    ]
    return Base("relnotes", "bash", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-bash-quoting", category="fix", lang="bash", kind="fix", n=13,
        summary="shell pitfalls: word splitting, globs, pipeline subshells, octal arithmetic, printf formats, exit statuses (bash)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
