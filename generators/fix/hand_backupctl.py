"""A layered bash project (snapshot tool: create, list, prune, verify, restore) with defects in different libraries than the
symptom, and incident tickets that combine causes."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, combo, tasks_from

README = dd(r'''
    # backupctl

    Snapshots of a directory as tar files with a checksum manifest (bash; `bin/backupctl`, libraries in `lib/`; tests: `bash tests/run.sh`).
    Needs GNU tar, coreutils and find. `BACKUPCTL_NOW` (epoch seconds) replaces the current time; the stamp of a snapshot is
    `YYYYmmdd-HHMMSS` **in UTC**, whatever `TZ` says. Exit status: 0 success, 1 the operation failed, 2 bad usage or a bad argument (the message
    goes to stderr as `backupctl: ...`). Usage errors also print the usage text to stderr.

    ## create SRC DEST [--name NAME] [--exclude PATTERN]...

    * Writes `DEST/NAME-STAMP.tar` and `DEST/NAME-STAMP.manifest` (DEST is created if needed; NAME defaults to the base name of SRC and may contain dashes).
      The tar holds the regular files below SRC with paths relative to SRC (no `./`); the manifest has one line per file, `<sha256>  <path>`, sorted by path
      in the C locale. Hidden files are included. Names may contain spaces and any other character except a newline.
    * `--exclude PATTERN` (repeatable) is a shell pattern matched against the *base name* of files and directories; a matching directory is skipped
      with everything below it.
    * It never overwrites: if the snapshot exists, exit 1, `snapshot exists: <path>` on stderr, nothing changed. If SRC is not a directory: exit 2.
      If anything fails halfway (for instance tar), exit 1 and **nothing** is left in DEST.
    * On success it prints `created NAME-STAMP.tar (N files)`.

    ## list DEST

    One line per snapshot, newest first (by stamp; equal stamps by name): `NAME-STAMP.tar  N files  S bytes` (N from the manifest, S the size of the tar).
    Nothing for an empty directory. DEST not a directory: exit 2.

    ## prune DEST --keep-last N [--keep-daily D] [-n]

    Snapshots are grouped by NAME. In each group the N newest are kept, plus the newest snapshot of each of the D most recent UTC days that have
    snapshots (default D = 0). Every other snapshot (tar and manifest) is deleted. Output: `deleted FILE` per snapshot (by name, oldest first), then
    `kept K, deleted M`. With `-n` nothing is deleted and the words are `would delete FILE` and `kept K, would delete M`. N and D are decimal
    integers (`08` is eight); anything else, or a missing `--keep-last`, is exit 2.

    ## verify ARCHIVE

    Compares the files in the tar with its manifest (`ARCHIVE` with `.manifest` instead of `.tar`). Prints `ok` and exits 0 when they agree. Otherwise
    one line per path, sorted by path (C locale): `MISSING path` (in the manifest, not in the tar), `CHANGED path` (different checksum) or `EXTRA path`
    (in the tar, not in the manifest), and exits 1. Missing archive or manifest: exit 2.

    ## restore ARCHIVE TARGET

    Extracts into TARGET (created if needed) and prints `restored N files`. A TARGET that exists and is not an empty directory is refused (exit 1,
    nothing written). Missing archive: exit 2.
''')

MAIN = dd(r'''
    #!/usr/bin/env bash
    # backupctl: snapshots of a directory as tar files with a checksum manifest.
    set -u
    root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
    . "$root/lib/common.sh"
    . "$root/lib/create.sh"
    . "$root/lib/list.sh"
    . "$root/lib/prune.sh"
    . "$root/lib/verify.sh"
    . "$root/lib/restore.sh"

    main() {
      local cmd=${1:-}
      [ $# -gt 0 ] && shift
      case $cmd in
        create) cmd_create "$@" ;;
        list) cmd_list "$@" ;;
        prune) cmd_prune "$@" ;;
        verify) cmd_verify "$@" ;;
        restore) cmd_restore "$@" ;;
        help | -h | --help) usage; return 0 ;;
        *) usage; return 2 ;;
      esac
    }

    main "$@"
''')

COMMON = dd(r'''
    # Shared helpers.

    usage() {
      cat >&2 <<'EOF'
    usage: backupctl create SRC DEST [--name NAME] [--exclude PATTERN]...
           backupctl list DEST
           backupctl prune DEST --keep-last N [--keep-daily D] [-n]
           backupctl verify ARCHIVE
           backupctl restore ARCHIVE TARGET
    EOF
    }

    die() {
      local status=$1
      shift
      echo "backupctl: $*" >&2
      exit "$status"
    }

    now() {
      echo "${BACKUPCTL_NOW:-$(date +%s)}"
    }

    # The stamp of a point in time: YYYYmmdd-HHMMSS in UTC.
    stamp() {
      date -u -d "@${1:-$(now)}" +%Y%m%d-%H%M%S
    }

    # split_snapshot FILE: sets SNAP_NAME, SNAP_STAMP and SNAP_DAY from "NAME-YYYYmmdd-HHMMSS.tar" (NAME may contain dashes).
    split_snapshot() {
      local b=${1##*/}
      b=${b%.tar}
      SNAP_STAMP=${b: -15}
      SNAP_NAME=${b%-"$SNAP_STAMP"}
      SNAP_DAY=${SNAP_STAMP%-*}
    }

    # to_uint VALUE OPTION: sets REPLY to a non-negative decimal integer, or exits 2.
    to_uint() {
      [[ $1 =~ ^[0-9]+$ ]] || die 2 "$2 needs a non-negative integer, got '$1'"
      REPLY=$((10#$1))
    }
''')

CREATE = dd(r'''
    # backupctl create

    cmd_create() {
      local name= pos=() excludes=()
      while [ $# -gt 0 ]; do
        case $1 in
          --name)
            [ $# -ge 2 ] || die 2 "missing value for --name"
            name=$2
            shift 2
            ;;
          --exclude)
            [ $# -ge 2 ] || die 2 "missing value for --exclude"
            excludes+=("$2")
            shift 2
            ;;
          --) shift; pos+=("$@"); break ;;
          -*) die 2 "unknown option: $1" ;;
          *) pos+=("$1"); shift ;;
        esac
      done
      if [ ${#pos[@]} -ne 2 ]; then
        usage
        exit 2
      fi
      local src=${pos[0]} dest=${pos[1]}
      [ -d "$src" ] || die 2 "not a directory: $src"
      [ -n "$name" ] || name=$(basename -- "$src")
      mkdir -p -- "$dest" || die 1 "cannot create $dest"

      local base="$name-$(stamp)"
      local tarfile="$dest/$base.tar" manifest="$dest/$base.manifest"
      if [ -e "$tarfile" ] || [ -e "$manifest" ]; then
        die 1 "snapshot exists: $tarfile"
      fi

      tmp=$(mktemp -d "$dest/.backupctl.XXXXXX") || die 1 "cannot create a temporary directory in $dest"
      trap 'rm -rf -- "$tmp"' EXIT
      local out_tar="$tmp/archive.tar" out_manifest="$tmp/manifest"

      local expr=() pat first=1
      if [ ${#excludes[@]} -gt 0 ]; then
        expr+=(\()
        for pat in "${excludes[@]}"; do
          [ $first -eq 1 ] || expr+=(-o)
          expr+=(-name "$pat")
          first=0
        done
        expr+=(\) -prune -o)
      fi
      (cd "$src" && find . -mindepth 1 "${expr[@]}" -type f -print0) | sed -z 's|^\./||' | LC_ALL=C sort -z > "$tmp/list"
      [ "${PIPESTATUS[0]}" -eq 0 ] || die 1 "cannot read $src"

      local count=0 rel hash
      : > "$out_manifest"
      while IFS= read -r -d '' rel; do
        hash=$(sha256sum < "$src/$rel") || die 1 "cannot read $src/$rel"
        printf '%s  %s\n' "${hash%% *}" "$rel" >> "$out_manifest"
        count=$((count + 1))
      done < "$tmp/list"

      tar -cf "$out_tar" -C "$src" --null --no-recursion -T "$tmp/list" || die 1 "tar failed"
      mv -- "$out_tar" "$tarfile" && mv -- "$out_manifest" "$manifest" || die 1 "cannot store the snapshot"
      echo "created $base.tar ($count files)"
    }
''')

LIST = dd(r'''
    # backupctl list

    cmd_list() {
      [ $# -eq 1 ] || { usage; exit 2; }
      local dest=$1 f n size
      [ -d "$dest" ] || die 2 "not a directory: $dest"
      local keys=()
      for f in "$dest"/*.tar; do
        [ -e "$f" ] || continue
        split_snapshot "$f"
        keys+=("$SNAP_STAMP"$'\t'"$SNAP_NAME"$'\t'"${f##*/}")
      done
      [ ${#keys[@]} -gt 0 ] || return 0
      local stamp name file
      while IFS=$'\t' read -r stamp name file; do
        n=$(wc -l < "$dest/${file%.tar}.manifest")
        size=$(stat -c %s -- "$dest/$file")
        echo "$file  $((n)) files  $size bytes"
      done < <(printf '%s\n' "${keys[@]}" | LC_ALL=C sort -t $'\t' -k1,1r -k2,2)
    }
''')

PRUNE = dd(r'''
    # backupctl prune

    cmd_prune() {
      local keep_last= keep_daily=0 dry=0 pos=()
      while [ $# -gt 0 ]; do
        case $1 in
          --keep-last)
            [ $# -ge 2 ] || die 2 "missing value for --keep-last"
            keep_last=$2
            shift 2
            ;;
          --keep-daily)
            [ $# -ge 2 ] || die 2 "missing value for --keep-daily"
            keep_daily=$2
            shift 2
            ;;
          -n | --dry-run) dry=1; shift ;;
          -*) die 2 "unknown option: $1" ;;
          *) pos+=("$1"); shift ;;
        esac
      done
      if [ ${#pos[@]} -ne 1 ]; then
        usage
        exit 2
      fi
      local dest=${pos[0]}
      [ -d "$dest" ] || die 2 "not a directory: $dest"
      [ -n "$keep_last" ] || die 2 "--keep-last is required"
      to_uint "$keep_last" --keep-last
      keep_last=$REPLY
      to_uint "$keep_daily" --keep-daily
      keep_daily=$REPLY

      local f keys=()
      for f in "$dest"/*.tar; do
        [ -e "$f" ] || continue
        split_snapshot "$f"
        keys+=("$SNAP_NAME"$'\t'"$SNAP_STAMP"$'\t'"${f##*/}")
      done
      local verb=deleted
      [ "$dry" -eq 1 ] && verb="would delete"
      [ ${#keys[@]} -gt 0 ] || { echo "kept 0, $verb 0"; return 0; }

      # newest first inside each name: decide what to keep
      local -A keep=()
      local name stamp file prev= rank=0 days=0 last_day=
      while IFS=$'\t' read -r name stamp file; do
        if [ "$name" != "$prev" ]; then
          prev=$name
          rank=0
          days=0
          last_day=
        fi
        rank=$((rank + 1))
        [ "$rank" -le "$keep_last" ] && keep[$file]=1
        if [ "${stamp%-*}" != "$last_day" ]; then
          last_day=${stamp%-*}
          days=$((days + 1))
          [ "$days" -le "$keep_daily" ] && keep[$file]=1
        fi
      done < <(printf '%s\n' "${keys[@]}" | LC_ALL=C sort -t $'\t' -k1,1 -k2,2r)

      # delete the rest, oldest first inside each name
      local kept=0 deleted=0
      while IFS=$'\t' read -r name stamp file; do
        if [ -n "${keep[$file]+x}" ]; then
          kept=$((kept + 1))
          continue
        fi
        echo "$verb $file"
        deleted=$((deleted + 1))
        if [ "$dry" -eq 0 ]; then
          rm -f -- "$dest/$file" "$dest/${file%.tar}.manifest"
        fi
      done < <(printf '%s\n' "${keys[@]}" | LC_ALL=C sort -t $'\t' -k1,1 -k2,2)
      echo "kept $kept, $verb $deleted"
    }
''')

VERIFY = dd(r'''
    # backupctl verify

    cmd_verify() {
      [ $# -eq 1 ] || { usage; exit 2; }
      local archive=$1
      [ -f "$archive" ] || die 2 "no such archive: $archive"
      local manifest=${archive%.tar}.manifest
      [ -f "$manifest" ] || die 2 "no manifest for $archive"

      tmp=$(mktemp -d) || die 1 "cannot create a temporary directory"
      trap 'rm -rf -- "$tmp"' EXIT
      mkdir "$tmp/x"
      tar -xf "$archive" -C "$tmp/x" || die 1 "cannot read $archive"

      local report="$tmp/report" line hash path actual
      local -A expected=()
      : > "$report"
      while IFS= read -r line; do
        hash=${line%%  *}
        path=${line#*  }
        expected[$path]=$hash
        if [ ! -f "$tmp/x/$path" ]; then
          echo "MISSING $path" >> "$report"
          continue
        fi
        actual=$(sha256sum < "$tmp/x/$path")
        [ "${actual%% *}" = "$hash" ] || echo "CHANGED $path" >> "$report"
      done < "$manifest"
      while IFS= read -r -d '' path; do
        path=${path#./}
        [ -n "${expected[$path]+x}" ] || echo "EXTRA $path" >> "$report"
      done < <(cd "$tmp/x" && find . -type f -print0)

      if [ -s "$report" ]; then
        LC_ALL=C sort -t ' ' -k2 "$report"
        return 1
      fi
      echo ok
    }
''')

RESTORE = dd(r'''
    # backupctl restore

    cmd_restore() {
      [ $# -eq 2 ] || { usage; exit 2; }
      local archive=$1 target=$2
      [ -f "$archive" ] || die 2 "no such archive: $archive"
      if [ -e "$target" ] && [ ! -d "$target" ]; then
        die 1 "not a directory: $target"
      fi
      if [ -d "$target" ] && [ -n "$(ls -A -- "$target")" ]; then
        die 1 "target is not empty: $target"
      fi
      mkdir -p -- "$target" || die 1 "cannot create $target"
      tar -xf "$archive" -C "$target" || die 1 "cannot extract $archive"
      echo "restored $(tar -tf "$archive" | wc -l) files"
    }
''')

HARNESS = dd(r'''
    #!/usr/bin/env bash
    cd "$(dirname "$0")/.." || exit 2
    ROOT=$(pwd)
    fail=0
    check() {
      if [ "$2" != "$3" ]; then
        printf 'FAIL: %s\n  expected: %s\n  actual:   %s\n' "$1" "$2" "$3"
        fail=1
      fi
    }
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    BIN="$tmp/backupctl"
    printf '#!/bin/sh\nexec bash "%s/bin/backupctl" "$@"\n' "$ROOT" > "$BIN"
    chmod +x "$BIN"
    # run CMD...: sets OUT, ERR, RC
    run() {
      OUT=$("$@" 2> "$tmp/err")
      RC=$?
      ERR=$(cat "$tmp/err")
    }
    mkfile() { mkdir -p "$(dirname "$1")"; printf '%s' "$2" > "$1"; }
    sha() { printf '%s' "$1" | sha256sum | cut -d' ' -f1; }
''')

VISIBLE = {
    "tests/run.sh": HARNESS + dd(r'''
        src="$tmp/docs"
        mkfile "$src/a.txt" alpha
        mkfile "$src/sub/b.txt" beta
        export BACKUPCTL_NOW=1700000000
        run "$BIN" create "$src" "$tmp/dest"
        check "create output" "created docs-20231114-221320.tar (2 files)" "$OUT"
        check "create rc" "0" "$RC"
        check "manifest" "$(printf '%s  a.txt\n%s  sub/b.txt' "$(sha alpha)" "$(sha beta)")" "$(cat "$tmp/dest/docs-20231114-221320.manifest")"
        run "$BIN" verify "$tmp/dest/docs-20231114-221320.tar"
        check "verify" "ok" "$OUT"
        exit $fail
    '''),
}

HIDDEN = {
    "tests/run.sh": HARNESS + dd(r'''
        export BACKUPCTL_NOW=1700000000   # 2023-11-14 22:13:20 UTC
        S0=20231114-221320

        # ---- create -----------------------------------------------------------------------------------------------
        src="$tmp/docs"
        mkfile "$src/a.txt" alpha
        mkfile "$src/sub/b.txt" beta
        mkfile "$src/.hidden" secret
        mkfile "$src/sp ace.txt" spaced
        mkfile "$src/sub/deeper/c.txt" gamma
        run "$BIN" create "$src" "$tmp/dest"
        check "create output" "created docs-$S0.tar (5 files)" "$OUT"
        check "create rc" "0" "$RC"
        want=$(printf '%s  .hidden\n%s  a.txt\n%s  sp ace.txt\n%s  sub/b.txt\n%s  sub/deeper/c.txt' "$(sha secret)" "$(sha alpha)" "$(sha spaced)" "$(sha beta)" "$(sha gamma)")
        check "manifest (hidden files, spaces, C order)" "$want" "$(cat "$tmp/dest/docs-$S0.manifest")"
        check "tar members" "$(printf '.hidden\na.txt\nsp ace.txt\nsub/b.txt\nsub/deeper/c.txt')" "$(tar -tf "$tmp/dest/docs-$S0.tar" | LC_ALL=C sort)"
        check "dest holds exactly two files" "2" "$(find "$tmp/dest" -type f | wc -l)"
        check "dest has no leftovers" "0" "$(find "$tmp/dest" -mindepth 1 ! -name '*.tar' ! -name '*.manifest' | wc -l)"

        # the stamp is UTC whatever TZ says
        TZ=UTC-5:30 run "$BIN" create "$src" "$tmp/dest_tz"
        check "stamp in UTC" "created docs-$S0.tar (5 files)" "$OUT"

        # names
        run "$BIN" create "$src" "$tmp/dest_n" --name my-docs
        check "--name" "created my-docs-$S0.tar (5 files)" "$OUT"

        # it never overwrites
        sum1=$(sha256sum < "$tmp/dest/docs-$S0.tar")
        mkfile "$src/new.txt" later
        run "$BIN" create "$src" "$tmp/dest"
        check "existing snapshot rc" "1" "$RC"
        check "existing snapshot message" "backupctl: snapshot exists: $tmp/dest/docs-$S0.tar" "$ERR"
        check "existing snapshot untouched" "$sum1" "$(sha256sum < "$tmp/dest/docs-$S0.tar")"
        check "existing snapshot manifest untouched" "5" "$(wc -l < "$tmp/dest/docs-$S0.manifest")"
        rm "$src/new.txt"

        # a missing source
        run "$BIN" create "$tmp/nope" "$tmp/dest_x"
        check "missing source rc" "2" "$RC"
        check "missing source message" "backupctl: not a directory: $tmp/nope" "$ERR"

        # argument errors
        run "$BIN" create "$src"
        check "one positional rc" "2" "$RC"
        run "$BIN" create "$src" "$tmp/d" --bogus
        check "unknown option rc" "2" "$RC"
        run "$BIN" create "$src" "$tmp/d" --exclude
        check "missing option value rc" "2" "$RC"
        run "$BIN" create "$src" "$tmp/d" --name
        check "missing name value rc" "2" "$RC"
        check "no dest created by a usage error" "no" "$([ -e "$tmp/d" ] && echo yes || echo no)"

        # excludes match base names, directories are pruned
        ex="$tmp/ex"
        mkfile "$ex/keep.txt" k
        mkfile "$ex/x.tmp" t
        mkfile "$ex/d/y.tmp" t
        mkfile "$ex/cache/z.txt" z
        mkfile "$ex/d/cache/w.txt" w
        mkfile "$ex/cachefile.txt" c
        mkfile "$ex/my file.txt" m
        mkfile "$ex/d/ok.txt" o
        run "$BIN" create "$ex" "$tmp/dest_ex" --exclude '*.tmp' --exclude cache --exclude 'my file.txt'
        check "exclude output" "created ex-$S0.tar (3 files)" "$OUT"
        check "exclude manifest paths" "$(printf 'cachefile.txt\nd/ok.txt\nkeep.txt')" "$(cut -d' ' -f3- "$tmp/dest_ex/ex-$S0.manifest")"
        check "exclude tar members" "$(printf 'cachefile.txt\nd/ok.txt\nkeep.txt')" "$(tar -tf "$tmp/dest_ex/ex-$S0.tar" | LC_ALL=C sort)"

        # a failing tar leaves nothing behind
        mkdir "$tmp/stub"
        printf '#!/bin/sh\nexit 2\n' > "$tmp/stub/tar"
        chmod +x "$tmp/stub/tar"
        PATH="$tmp/stub:$PATH" run "$BIN" create "$src" "$tmp/dest_fail"
        check "failing tar rc" "1" "$RC"
        check "failing tar leaves nothing" "0" "$(find "$tmp/dest_fail" -mindepth 1 | wc -l)"

        # ---- list -------------------------------------------------------------------------------------------------
        lst="$tmp/lst"
        small="$tmp/small"
        mkfile "$small/f" data
        BACKUPCTL_NOW=1700000000 "$BIN" create "$small" "$lst" --name docs > /dev/null
        BACKUPCTL_NOW=1700086400 "$BIN" create "$small" "$lst" --name docs > /dev/null
        BACKUPCTL_NOW=1700003600 "$BIN" create "$small" "$lst" --name my-photos > /dev/null
        BACKUPCTL_NOW=1700003600 "$BIN" create "$small" "$lst" --name a-notes > /dev/null
        run "$BIN" list "$lst"
        size=$(stat -c %s "$lst/docs-$S0.tar")
        want=$(printf 'docs-20231115-221320.tar  1 files  %s bytes\na-notes-20231114-231320.tar  1 files  %s bytes\nmy-photos-20231114-231320.tar  1 files  %s bytes\ndocs-20231114-221320.tar  1 files  %s bytes' "$size" "$size" "$size" "$size")
        check "list: newest first, ties by name, dashes in names" "$want" "$OUT"
        check "list rc" "0" "$RC"
        mkdir "$tmp/empty"
        run "$BIN" list "$tmp/empty"
        check "list of nothing" "" "$OUT"
        check "list of nothing rc" "0" "$RC"
        run "$BIN" list "$tmp/missing"
        check "list of a missing dir rc" "2" "$RC"

        # ---- prune ------------------------------------------------------------------------------------------------
        mk_pr() {
          local d=$1 t name
          rm -rf "$d"
          for spec in "docs|2023-11-10 08:00:00" "docs|2023-11-10 20:00:00" "docs|2023-11-11 09:00:00" "docs|2023-11-12 01:00:00" \
                      "docs|2023-11-12 23:00:00" "docs|2023-11-13 12:00:00" "my-photos|2023-11-12 10:00:00" "my-photos|2023-11-13 10:00:00"; do
            name=${spec%%|*}
            t=$(date -u -d "${spec#*|}" +%s)
            BACKUPCTL_NOW=$t "$BIN" create "$small" "$d" --name "$name" > /dev/null
          done
        }
        names() { (cd "$1" && ls *.tar | LC_ALL=C sort | sed 's/\.tar$//' | tr '\n' ' '); }

        mk_pr "$tmp/p1"
        run "$BIN" prune "$tmp/p1" --keep-last 2
        want=$(printf 'deleted docs-20231110-080000.tar\ndeleted docs-20231110-200000.tar\ndeleted docs-20231111-090000.tar\ndeleted docs-20231112-010000.tar\nkept 4, deleted 4')
        check "prune keep-last output" "$want" "$OUT"
        check "prune keep-last rc" "0" "$RC"
        check "prune keep-last leaves" "docs-20231112-230000 docs-20231113-120000 my-photos-20231112-100000 my-photos-20231113-100000 " "$(names "$tmp/p1")"
        check "prune removes manifests too" "4" "$(ls "$tmp/p1"/*.manifest | wc -l)"

        mk_pr "$tmp/p2"
        run "$BIN" prune "$tmp/p2" --keep-last 1 --keep-daily 3
        want=$(printf 'deleted docs-20231110-080000.tar\ndeleted docs-20231110-200000.tar\ndeleted docs-20231112-010000.tar\nkept 5, deleted 3')
        check "prune keep-daily output" "$want" "$OUT"
        check "prune keep-daily leaves" "docs-20231111-090000 docs-20231112-230000 docs-20231113-120000 my-photos-20231112-100000 my-photos-20231113-100000 " "$(names "$tmp/p2")"

        mk_pr "$tmp/p3"
        run "$BIN" prune "$tmp/p3" --keep-last 1 -n
        want=$(printf 'would delete docs-20231110-080000.tar\nwould delete docs-20231110-200000.tar\nwould delete docs-20231111-090000.tar\nwould delete docs-20231112-010000.tar\nwould delete docs-20231112-230000.tar\nwould delete my-photos-20231112-100000.tar\nkept 2, would delete 6')
        check "prune dry run output" "$want" "$OUT"
        check "prune dry run deletes nothing" "8" "$(ls "$tmp/p3"/*.tar | wc -l)"
        check "prune dry run keeps manifests" "8" "$(ls "$tmp/p3"/*.manifest | wc -l)"

        mk_pr "$tmp/p4"
        run "$BIN" prune "$tmp/p4" --keep-last 08 --keep-daily 09
        check "leading zeros are decimal" "kept 8, deleted 0" "$OUT"
        check "leading zeros rc" "0" "$RC"
        run "$BIN" prune "$tmp/p4" --keep-last 0
        check "keep nothing" "kept 0, deleted 8" "$(printf '%s' "$OUT" | tail -n 1)"
        check "keep nothing leaves nothing" "0" "$(find "$tmp/p4" -type f | wc -l)"

        run "$BIN" prune "$tmp/p4"
        check "keep-last is required" "2" "$RC"
        run "$BIN" prune "$tmp/p4" --keep-last abc
        check "bad number rc" "2" "$RC"
        run "$BIN" prune "$tmp/p4" --keep-last -1
        check "negative number rc" "2" "$RC"
        run "$BIN" prune "$tmp/p4" --keep-last 1 --keep-daily x
        check "bad daily number rc" "2" "$RC"
        run "$BIN" prune "$tmp/missing" --keep-last 1
        check "prune of a missing dir rc" "2" "$RC"
        run "$BIN" prune "$tmp/empty" --keep-last 1
        check "prune of an empty dir" "kept 0, deleted 0" "$OUT"

        # names with dashes are separate groups
        dd_="$tmp/p5"
        for t in 1700000000 1700100000 1700200000; do
          BACKUPCTL_NOW=$t "$BIN" create "$small" "$dd_" --name my-docs > /dev/null
          BACKUPCTL_NOW=$t "$BIN" create "$small" "$dd_" --name my-photos > /dev/null
        done
        run "$BIN" prune "$dd_" --keep-last 1
        check "one per dashed name" "my-docs-20231117-054640 my-photos-20231117-054640 " "$(names "$dd_")"
        check "dashed names summary" "kept 2, deleted 4" "$(printf '%s' "$OUT" | tail -n 1)"

        # ---- verify -----------------------------------------------------------------------------------------------
        ver="$tmp/ver"
        vsrc="$tmp/vsrc"
        mkfile "$vsrc/one.txt" 1
        mkfile "$vsrc/two words.txt" 2
        mkfile "$vsrc/dir/three.txt" 3
        "$BIN" create "$vsrc" "$ver" > /dev/null
        arch="$ver/vsrc-$S0.tar"
        man="$ver/vsrc-$S0.manifest"
        run "$BIN" verify "$arch"
        check "verify ok" "ok" "$OUT"
        check "verify ok rc" "0" "$RC"
        cp "$man" "$tmp/man.orig"
        sed -i "s/^$(sha 1)/$(sha 9)/" "$man"
        run "$BIN" verify "$arch"
        check "verify changed" "CHANGED one.txt" "$OUT"
        check "verify changed rc" "1" "$RC"
        cp "$tmp/man.orig" "$man"
        grep -v 'three.txt' "$tmp/man.orig" > "$man"
        run "$BIN" verify "$arch"
        check "verify extra" "EXTRA dir/three.txt" "$OUT"
        check "verify extra rc" "1" "$RC"
        { cat "$tmp/man.orig"; printf '%s  gone file.txt\n' "$(sha 5)"; } > "$man"
        sed -i "s/^$(sha 2)/$(sha 8)/" "$man"
        run "$BIN" verify "$arch"
        check "verify several, sorted by path" "$(printf 'MISSING gone file.txt\nCHANGED two words.txt')" "$OUT"
        check "verify several rc" "1" "$RC"
        { cat "$tmp/man.orig"; printf '%s  zzz.txt\n' "$(sha 5)"; } > "$man"
        grep -v 'one.txt' "$man" > "$man.2"; mv "$man.2" "$man"
        run "$BIN" verify "$arch"
        check "verify sorted: extra before missing" "$(printf 'EXTRA one.txt\nMISSING zzz.txt')" "$OUT"
        rm "$man"
        run "$BIN" verify "$arch"
        check "verify without a manifest rc" "2" "$RC"
        run "$BIN" verify "$tmp/nothing.tar"
        check "verify without an archive rc" "2" "$RC"

        # ---- restore ----------------------------------------------------------------------------------------------
        run "$BIN" restore "$tmp/dest/docs-$S0.tar" "$tmp/restored"
        check "restore output" "restored 5 files" "$OUT"
        check "restore rc" "0" "$RC"
        check "restored tree equals the source" "" "$(diff -r "$src" "$tmp/restored")"
        run "$BIN" restore "$tmp/dest/docs-$S0.tar" "$tmp/restored"
        check "restore into a used directory rc" "1" "$RC"
        mkdir "$tmp/emptydir"
        run "$BIN" restore "$tmp/dest/docs-$S0.tar" "$tmp/emptydir"
        check "restore into an empty directory" "restored 5 files" "$OUT"
        : > "$tmp/afile"
        run "$BIN" restore "$tmp/dest/docs-$S0.tar" "$tmp/afile"
        check "restore onto a file rc" "1" "$RC"
        run "$BIN" restore "$tmp/nothing.tar" "$tmp/r2"
        check "restore of a missing archive rc" "2" "$RC"
        check "nothing created for it" "no" "$([ -e "$tmp/r2" ] && echo yes || echo no)"

        # ---- the front door ---------------------------------------------------------------------------------------
        run "$BIN" frobnicate
        check "unknown command rc" "2" "$RC"
        check "unknown command prints usage" "usage: backupctl create SRC DEST [--name NAME] [--exclude PATTERN]..." "$(printf '%s' "$ERR" | head -n 1)"
        run "$BIN"
        check "no command rc" "2" "$RC"
        run "$BIN" help
        check "help rc" "0" "$RC"
        exit $fail
    '''),
}


def _prompts() -> dict:
    p = {}
    p["utc"] = (
        "Snapshots made by our nightly job on the Mumbai servers carry the wrong time in their names (5 and a half hours ahead of the other "
        "servers), so `prune --keep-daily` also counts days differently than in the other regions. Stamps are supposed to be UTC."
    )
    p["missing-src-rc"] = (
        "The deploy wrapper treats exit status 1 as 'the backup failed, retry later' and 2 as 'configuration error, page someone'. When the "
        "source directory is wrong, `backupctl create` exits with 1, so the nightly job retries forever instead of paging."
    )
    p["unknown-rc"] = (
        "`backupctl frobnicate` prints the usage text and then exits 0, so typos in our cron lines look like successful runs."
    )
    p["overwrite"] = (
        "Running the backup twice within the same second (our wrapper retries quickly on a flaky mount) replaced the first snapshot with a "
        "second one that had a different content. A snapshot must never be overwritten."
    )
    p["hidden"] = "Restores from our snapshots are missing `.env` and `.gitignore`: dot files are not in the archive."
    p["spaces"] = (
        "Backing up a folder with a file called `Q3 report final.xlsx` fails with `backupctl: cannot read /srv/finance/Q3` (the name is cut "
        "at the first space) and the snapshot is not created. Folders without such names work."
    )
    p["exclude-path"] = (
        "`--exclude '*.tmp'` works but `--exclude cache` does not exclude our `cache` directories (there is one in every project folder), "
        "and the archives are huge. The option takes a pattern for the base name of files and directories."
    )
    p["partial"] = (
        "When the disk filled up during a backup, `create` failed as it should, but the destination was left with a truncated "
        "`.tar` and a half-written `.manifest` with a perfectly valid-looking name, and the next `prune` counted them as good snapshots."
    )
    p["exclude-shift"] = (
        "`backupctl create /srv/app /backup --exclude '*.tmp' --exclude cache` ends with a usage error (`create` seems to see the "
        "patterns as extra directories). Without `--exclude` it works."
    )
    p["list-order"] = "`backupctl list` shows the oldest snapshot first; on a directory with hundreds of snapshots the one you want is at the bottom."
    p["dash-split"] = (
        "Pruning a backup directory that holds `my-docs-...` and `my-photos-...` snapshots keeps one snapshot in total instead of one per "
        "name, and `list` does not show them in time order either. Names without a dash behave."
    )
    p["daily-snapshots"] = (
        "`prune --keep-last 1 --keep-daily 3` keeps three snapshots even when they are all from the same day; the README says three *days*."
    )
    p["octal"] = (
        "Our retention config says `--keep-last 08` (months are zero padded in the config generator) and `backupctl prune` dies with "
        "`value too great for base (error token is \"08\")`. The README says those are decimal numbers."
    )
    p["dry-run"] = "`backupctl prune /backup --keep-last 3 -n` printed 'would delete ...' lines and then really deleted the snapshots. A dry run must change nothing."
    p["mix-names"] = (
        "`prune --keep-last 2` on a directory with `docs` and `photos` snapshots deletes all of the `photos` snapshots as soon as `docs` has "
        "two or more. Each name is supposed to be pruned on its own."
    )
    p["orphan-manifest"] = (
        "After `prune` the backup directory is full of `.manifest` files whose `.tar` is gone."
    )
    p["extra"] = (
        "`verify` says `ok` for an archive in which somebody had slipped an extra file (not in the manifest). The README lists `EXTRA` for that case."
    )
    p["verify-rc"] = (
        "`backupctl verify` prints `CHANGED ...` lines but exits 0, so our post-backup check in the pipeline never fails."
    )
    p["restore-used"] = (
        "A restore into a folder that already holds production files unpacked over them. The README says a target that is not empty is refused."
    )
    p["dashed-incident"] = (
        "Retention incident on the file server. (1) `list` shows `my-docs` and `my-photos` snapshots interleaved in the wrong order. "
        "(2) `prune --keep-last 1` kept only one snapshot for the whole directory, not one per name, and the `photos` history was lost. "
        "(3) Before that, `list` had been showing the oldest snapshot first, which is how nobody noticed. Please fix all of it."
    )
    p["release-night"] = (
        "Release night checklist, three items: (1) snapshots made on the Mumbai servers carry a local time instead of UTC; (2) the exit status of "
        "`verify` is 0 even when it reports problems; (3) a `create` with several `--exclude` options ends with a usage error."
    )
    return p


def _base() -> Base:
    P = _prompts()
    good = {
        "README.md": README, "bin/backupctl": MAIN, "lib/common.sh": COMMON, "lib/create.sh": CREATE, "lib/list.sh": LIST,
        "lib/prune.sh": PRUNE, "lib/verify.sh": VERIFY, "lib/restore.sh": RESTORE,
    }
    bn, co, cr, li, pr, ve, re_ = "bin/backupctl", "lib/common.sh", "lib/create.sh", "lib/list.sh", "lib/prune.sh", "lib/verify.sh", "lib/restore.sh"
    utc = ('  date -u -d "@${1:-$(now)}" +%Y%m%d-%H%M%S\n', '  date -d "@${1:-$(now)}" +%Y%m%d-%H%M%S\n')
    miss_rc = ('  [ -d "$src" ] || die 2 "not a directory: $src"\n', '  [ -d "$src" ] || die 1 "not a directory: $src"\n')
    unknown_rc = ("    *) usage; return 2 ;;\n", "    *) usage; return 0 ;;\n")
    overwrite = ('  if [ -e "$tarfile" ] || [ -e "$manifest" ]; then\n    die 1 "snapshot exists: $tarfile"\n  fi\n', "")
    hidden = ('find . -mindepth 1 "${expr[@]}" -type f -print0)', "find . -mindepth 1 \"${expr[@]}\" -type f ! -name '.*' -print0)")
    spaces = [
        ("  while IFS= read -r -d '' rel; do\n", "  for rel in $(tr '\\0' '\\n' < \"$tmp/list\"); do\n"),
        ("  done < \"$tmp/list\"\n", "  done\n"),
    ]
    exclude_path = ('      expr+=(-name "$pat")\n', '      expr+=(-path "$pat")\n')
    partial = [
        ('  local out_tar="$tmp/archive.tar" out_manifest="$tmp/manifest"\n', '  local out_tar="$tarfile" out_manifest="$manifest"\n'),
        ('  mv -- "$out_tar" "$tarfile" && mv -- "$out_manifest" "$manifest" || die 1 "cannot store the snapshot"\n', ""),
    ]
    exclude_shift = ('        excludes+=("$2")\n        shift 2\n', '        excludes+=("$2")\n        shift\n')
    list_order = ("sort -t $'\\t' -k1,1r -k2,2)", "sort -t $'\\t' -k1,1 -k2,2)")
    dash = ('  SNAP_STAMP=${b: -15}\n  SNAP_NAME=${b%-"$SNAP_STAMP"}\n', '  SNAP_STAMP=${b#*-}\n  SNAP_NAME=${b%%-*}\n')
    daily = ('    if [ "${stamp%-*}" != "$last_day" ]; then\n      last_day=${stamp%-*}\n      days=$((days + 1))\n      [ "$days" -le "$keep_daily" ] && keep[$file]=1\n    fi\n',
             '    days=$((days + 1))\n    [ "$days" -le "$keep_daily" ] && keep[$file]=1\n')
    octal = ("  REPLY=$((10#$1))\n", "  REPLY=$(($1))\n")
    dry = ('    if [ "$dry" -eq 0 ]; then\n      rm -f -- "$dest/$file" "$dest/${file%.tar}.manifest"\n    fi\n', '    rm -f -- "$dest/$file" "$dest/${file%.tar}.manifest"\n')
    mix = ('    if [ "$name" != "$prev" ]; then\n      prev=$name\n      rank=0\n      days=0\n      last_day=\n    fi\n', "")
    orphan = ('      rm -f -- "$dest/$file" "$dest/${file%.tar}.manifest"\n', '      rm -f -- "$dest/$file"\n')
    extra = ('  while IFS= read -r -d \'\' path; do\n    path=${path#./}\n    [ -n "${expected[$path]+x}" ] || echo "EXTRA $path" >> "$report"\n  done < <(cd "$tmp/x" && find . -type f -print0)\n', "")
    verify_rc = ('    LC_ALL=C sort -t \' \' -k2 "$report"\n    return 1\n', '    LC_ALL=C sort -t \' \' -k2 "$report"\n    return $?\n')
    restore_used = ('  if [ -d "$target" ] && [ -n "$(ls -A -- "$target")" ]; then\n    die 1 "target is not empty: $target"\n  fi\n', "")
    bugs = [
        Bug("missing-source-exits-one", 1, {cr: [miss_rc]}, P["missing-src-rc"]),
        Bug("unknown-command-exits-zero", 1, {bn: [unknown_rc]}, P["unknown-rc"]),
        Bug("stamp-in-local-time", 2, {co: [utc]}, P["utc"]),
        Bug("snapshot-overwritten-when-the-stamp-repeats", 2, {cr: [overwrite]}, P["overwrite"]),
        Bug("hidden-files-left-out", 2, {cr: [hidden]}, P["hidden"]),
        Bug("list-shows-oldest-first", 2, {li: [list_order]}, P["list-order"]),
        Bug("dry-run-deletes", 2, {pr: [dry]}, P["dry-run"]),
        Bug("prune-leaves-the-manifest", 2, {pr: [orphan]}, P["orphan-manifest"]),
        Bug("restore-into-a-used-directory", 2, {re_: [restore_used]}, P["restore-used"]),
        Bug("file-names-with-spaces-break-the-manifest", 3, {cr: spaces}, P["spaces"]),
        Bug("exclude-matches-whole-paths", 3, {cr: [exclude_path]}, P["exclude-path"]),
        Bug("failed-create-leaves-partial-files", 3, {cr: partial}, P["partial"]),
        Bug("exclude-value-is-not-shifted", 3, {cr: [exclude_shift]}, P["exclude-shift"]),
        Bug("keep-daily-counts-snapshots", 3, {pr: [daily]}, P["daily-snapshots"]),
        Bug("leading-zeros-are-octal", 3, {co: [octal]}, P["octal"]),
        Bug("prune-mixes-names", 3, {pr: [mix]}, P["mix-names"]),
        Bug("verify-ignores-extra-files", 3, {ve: [extra]}, P["extra"]),
        Bug("verify-exits-zero-on-problems", 3, {ve: [verify_rc]}, P["verify-rc"]),
        Bug("names-split-at-the-first-dash", 4, {co: [dash]}, P["dash-split"]),
    ]
    base = Base("backupctl", "bash", good, VISIBLE, HIDDEN, bugs)
    base.bugs.extend([
        combo(base, ["names-split-at-the-first-dash", "prune-mixes-names", "list-shows-oldest-first"], 5, "dashed-names-incident",
              "Retention incident on the file server, three symptoms that turned out to be related:"),
        combo(base, ["stamp-in-local-time", "verify-exits-zero-on-problems", "exclude-value-is-not-shifted"], 5, "release-night",
              "Release night checklist, three items from three people:"),
        combo(base, ["hidden-files-left-out", "exclude-matches-whole-paths", "failed-create-leaves-partial-files"], 4, "create-review",
              "Review of `create` found three problems:"),
        combo(base, ["keep-daily-counts-snapshots", "leading-zeros-are-octal", "dry-run-deletes"], 4, "prune-policy-review",
              "Review of the retention policy code found three problems:"),
    ])
    return base


@family("fix-hand-backup-ctl", category="fix", lang="bash", kind="fix", n=23,
        summary="a layered bash snapshot tool (create, list, prune, verify, restore) with defects in different libraries than their symptoms")
def gen(rng, n):
    return tasks_from([_base()])
