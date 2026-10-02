"""Shell tasks: backup scripts: tar snapshots, selective restore, rsync-like mirroring, hard-linked snapshots, verification, rotation."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, HL, L, Run, TAR, scn

S = K.ShellSpec
T = 1700000000


def fz(spec, m=None):
    return {k: F(v, m=m) for k, v in spec.items()}


# ------------------------------------------------------------------------------------------------ 1. snapshot

REF_SNAP = dd('''
    #!/usr/bin/env bash
    # snapshot.sh SRC DEST STAMP : DEST/backup-STAMP.tar with every file of SRC as BASENAME/relative/path
    usage() { echo "usage: snapshot.sh SRC DEST STAMP" >&2; exit 2; }
    [ $# -eq 3 ] || usage
    src=$1 dest=$2 stamp=$3
    [ -d "$src" ] || usage
    [[ $stamp =~ ^[A-Za-z0-9._-]+$ ]] || usage
    while [ "${#src}" -gt 1 ] && [ "${src%/}" != "$src" ]; do src=${src%/}; done
    base=$(basename -- "$src")
    parent=$(dirname -- "$src")
    out=$dest/backup-$stamp.tar
    if [ -e "$out" ]; then echo "error: $out already exists" >&2; exit 1; fi
    mkdir -p -- "$dest"
    tar -cf "$out" -C "$parent" -- "$base"
    echo "created: backup-$stamp.tar"
''')


def make_snap(rng):
    ex = scn("example", {"proj/a.txt": F("alpha\n"), "proj/sub/b.txt": F("beta\n")}, Run("proj", "out", "20310101"))
    f = {"my data/readme": F("hello\n"), "my data/.hidden": F("h\n"), "my data/-dash file": F("d\n"), "my data/sub dir/deep.txt": F("deep\n"), "my data/link": L("readme"), "my data/empty": F("")}
    return ex, [scn("awkward names", f, Run("my data", "backups dir", "2031-06-01"), Run("my data/", "backups dir", "2031-06-02")), scn("refuses to overwrite", f, Run("my data", "b", "x"), Run("my data", "b", "x", stderr="nonempty")),
                scn("usage", f, Run("nope", "b", "x"), Run("my data", "b"), Run("my data", "b", "bad stamp"))]


# ------------------------------------------------------------------------------------------------ 2. selective restore

REF_RESTORE = dd('''
    #!/usr/bin/env bash
    # restore.sh [-f] ARCHIVE DEST [PATH...] : extract files (all, or those at/below PATH) without overwriting unless -f
    usage() { echo "usage: restore.sh [-f] ARCHIVE DEST [PATH...]" >&2; exit 2; }
    force=0
    if [ "${1:-}" = -f ]; then force=1; shift; fi
    [ $# -ge 2 ] && [ -f "$1" ] || usage
    archive=$1 dest=$2
    shift 2
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    tar -xf "$archive" -C "$tmp" || exit 1
    mkdir -p -- "$dest"
    (cd "$tmp" && find . -type f -print0 | LC_ALL=C sort -z) | while IFS= read -r -d '' f; do
      f=${f#./}
      if [ $# -gt 0 ]; then
        ok=0
        for p in "$@"; do
          p=${p%/}
          case $f in "$p"|"$p"/*) ok=1 ;; esac
        done
        [ "$ok" = 1 ] || continue
      fi
      if [ -e "$dest/$f" ] && [ "$force" = 0 ]; then
        echo "skipped: $f"
      else
        mkdir -p -- "$dest/$(dirname -- "$f")"
        cp -p -- "$tmp/$f" "$dest/$f"
        echo "restored: $f"
      fi
    done
''')


def make_restore(rng):
    arc = TAR({"proj/a.txt": "A\n", "proj/my docs/b c.txt": "B\n", "proj/-dash": "D\n", "proj/sub/deep/x": "X\n", "proj/sub/y": "Y\n", "other/z": "Z\n"})
    ex = scn("example", {"b.tar": TAR({"p/a": "1\n", "p/b": "2\n"})}, Run("b.tar", "out", "p/a"))
    return ex, [scn("whole archive", {"b.tar": arc}, Run("b.tar", "out")), scn("selected paths", {"b.tar": arc}, Run("b.tar", "out", "proj/sub", "proj/my docs/b c.txt", "other/")),
                scn("no overwrite unless forced", {"b.tar": arc, "out/proj/a.txt": F("LOCAL\n"), "out/other/z": F("LOCAL Z\n")}, Run("b.tar", "out"), Run("-f", "b.tar", "out", "other")),
                scn("usage", {"b.tar": arc}, Run(stderr="nonempty"), Run("b.tar"), Run("missing.tar", "out"))]


# ------------------------------------------------------------------------------------------------ 3. mirror

REF_MIRROR = dd('''
    #!/usr/bin/env bash
    # mirror.sh SRC DEST : make DEST's files equal SRC's (rsync-like); report "copied: path" and "removed: path"
    usage() { echo "usage: mirror.sh SRC DEST" >&2; exit 2; }
    [ $# -eq 2 ] && [ -d "$1" ] || usage
    src=$1 dest=$2
    mkdir -p -- "$dest"
    tab=$(printf '\\t')
    log=$(mktemp)
    while IFS= read -r -d '' rel; do
      if [ -f "$dest/$rel" ] && [ "$(stat -c '%s %Y' -- "$src/$rel")" = "$(stat -c '%s %Y' -- "$dest/$rel")" ]; then continue; fi
      mkdir -p -- "$dest/$(dirname -- "$rel")"
      cp -p -- "$src/$rel" "$dest/$rel"
      printf '%s\\tcopied: %s\\n' "$rel" "$rel" >> "$log"
    done < <(cd "$src" && find . -type f -printf '%P\\0')
    while IFS= read -r -d '' rel; do
      if [ ! -f "$src/$rel" ]; then
        rm -f -- "$dest/$rel"
        printf '%s\\tremoved: %s\\n' "$rel" "$rel" >> "$log"
      fi
    done < <(cd "$dest" && find . -type f -printf '%P\\0')
    find "$dest" -mindepth 1 -type d -empty -delete
    LC_ALL=C sort -t"$tab" -k1,1 "$log" | cut -f2-
    rm -f "$log"
''')


def make_mirror(rng):
    ex = scn("example", {"s/a": F("1", m=T), "s/b": F("22", m=T), "d/b": F("22", m=T), "d/old": F("x", m=T)}, Run("s", "d"))
    f = {"src/new file": F("new\n", m=T), "src/same": F("same\n", m=T), "src/changed size": F("longer now\n", m=T), "src/changed time": F("abc", m=T + 50), "src/sub dir/deep": F("d\n", m=T), "src/-dash": F("dash\n", m=T),
         "dst/same": F("same\n", m=T), "dst/changed size": F("short", m=T), "dst/changed time": F("abc", m=T), "dst/gone": F("bye\n", m=T), "dst/old dir/inner": F("i\n", m=T), "dst/sub dir/deep": F("d\n", m=T)}
    return ex, [scn("sync", f, Run("src", "dst"), Run("src", "dst"), mtimes=["dst/changed time", "dst/new file", "dst/same"]), scn("empty destination", {"src/a": F("1", m=T), "src/b/c": F("2", m=T)}, Run("src", "fresh")),
                scn("usage", {"src/a": F("1")}, Run("src"), Run("nope", "d"))]


# ------------------------------------------------------------------------------------------------ 4. rotate snapshot directories

REF_ROTS = dd('''
    #!/usr/bin/env bash
    # rotate-snaps.sh DEST KEEP : keep the KEEP newest snap-YYYYMMDD directories of DEST, delete the older ones
    dest=${1:-}
    keep=${2:-}
    case $keep in ''|*[!0-9]*|0) echo "usage: rotate-snaps.sh DEST KEEP" >&2; exit 2 ;; esac
    [ -d "$dest" ] || { echo "usage: rotate-snaps.sh DEST KEEP" >&2; exit 2; }
    snaps=$(cd "$dest" && find . -mindepth 1 -maxdepth 1 -type d -name 'snap-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' -printf '%f\\n' | LC_ALL=C sort)
    total=$(printf '%s' "$snaps" | grep -c . || true)
    [ "$total" -gt "$keep" ] || exit 0
    printf '%s\\n' "$snaps" | head -n $((total - keep)) | while IFS= read -r s; do
      rm -rf -- "$dest/$s"
      echo "removed: $s"
    done
''')


def make_rots(rng):
    ex = scn("example", {"b/snap-20310101/f": F("1"), "b/snap-20310102/f": F("2"), "b/snap-20310103/f": F("3")}, Run("b", "2"))
    f = {f"b/snap-2031{m:02d}01/data": F(f"m{m}") for m in range(1, 8)}
    f.update({"b/snap-latest/x": F("l"), "b/snap-2031010/x": F("short"), "b/notes.txt": F("n"), "b/snap-20310101.tar": F("tar"), "b/other-20300101/x": F("o")})
    return ex, [scn("keeps the newest", f, Run("b", "3"), Run("b", "3")), scn("fewer than keep", f, Run("b", "50")), scn("usage", f, Run("b", "0"), Run("b", "x"), Run("nope", "2"), Run())]


# ------------------------------------------------------------------------------------------------ 5. hard-linked snapshots

REF_HLS = dd('''
    #!/usr/bin/env bash
    # hardlink-snap.sh SRC DEST STAMP : DEST/STAMP is a copy of SRC; files identical to the same path in the previous snapshot become hard links to it
    usage() { echo "usage: hardlink-snap.sh SRC DEST STAMP" >&2; exit 2; }
    [ $# -eq 3 ] && [ -d "$1" ] || usage
    src=$1 dest=$2 stamp=$3
    [[ $stamp =~ ^[A-Za-z0-9._-]+$ ]] || usage
    [ ! -e "$dest/$stamp" ] || { echo "error: $dest/$stamp exists" >&2; exit 1; }
    mkdir -p -- "$dest"
    prev=$(cd "$dest" && find . -mindepth 1 -maxdepth 1 -type d -printf '%f\\n' | LC_ALL=C sort | tail -n 1)
    tab=$(printf '\\t')
    log=$(mktemp)
    mkdir -p -- "$dest/$stamp"
    while IFS= read -r -d '' rel; do
      mkdir -p -- "$dest/$stamp/$(dirname -- "$rel")"
      if [ -n "$prev" ] && [ -f "$dest/$prev/$rel" ] && cmp -s -- "$src/$rel" "$dest/$prev/$rel"; then
        ln -- "$dest/$prev/$rel" "$dest/$stamp/$rel"
        printf '%s\\tlinked: %s\\n' "$rel" "$rel" >> "$log"
      else
        cp -p -- "$src/$rel" "$dest/$stamp/$rel"
        printf '%s\\tcopied: %s\\n' "$rel" "$rel" >> "$log"
      fi
    done < <(cd "$src" && find . -type f -printf '%P\\0')
    LC_ALL=C sort -t"$tab" -k1,1 "$log" | cut -f2-
    rm -f "$log"
''')


def make_hls(rng):
    ex = scn("example", {"live/a": F("same\n"), "live/b": F("new\n"), "bk/20310101/a": F("same\n"), "bk/20310101/b": F("old\n")}, Run("live", "bk", "20310102"), nlink=True)
    f = {"live/keep me": F("k\n"), "live/changed": F("v2\n"), "live/sub dir/deep": F("d\n"), "live/-new": F("n\n"), "bk/20310101/keep me": F("k\n"), "bk/20310101/changed": F("v1\n"), "bk/20310101/sub dir/deep": F("d\n"), "bk/20310101/vanished": F("v\n"),
         "bk/20300101/keep me": F("ancient\n")}
    return ex, [scn("second snapshot", f, Run("live", "bk", "20310102"), nlink=True), scn("third snapshot links to the second", f, Run("live", "bk", "20310102"), Run("live", "bk", "20310103", ops=[{"op": "write", "path": "live/changed", "c": "v3\n"}]), nlink=True),
                scn("first snapshot", {"live/a": F("1\n"), "live/b/c": F("2\n")}, Run("live", "bk", "first"), nlink=True), scn("refuses to reuse a stamp", f, Run("live", "bk", "20310101", stderr="nonempty"), Run("live", "bk"), nlink=True)]


# ------------------------------------------------------------------------------------------------ 6. verify

REF_VERIFY = dd('''
    #!/usr/bin/env bash
    # verify.sh ARCHIVE SRC : compare a snapshot tar (members BASENAME/path) with the directory SRC
    usage() { echo "usage: verify.sh ARCHIVE SRC" >&2; exit 2; }
    [ $# -eq 2 ] && [ -f "$1" ] && [ -d "$2" ] || usage
    src=$2
    while [ "${#src}" -gt 1 ] && [ "${src%/}" != "$src" ]; do src=${src%/}; done
    base=$(basename -- "$src")
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    tar -xf "$1" -C "$tmp" || exit 2
    [ -d "$tmp/$base" ] || { echo "error: archive has no $base/" >&2; exit 2; }
    tab=$(printf '\\t')
    res=$(mktemp)
    (cd "$tmp/$base" && find . -type f -printf '%P\\0') | while IFS= read -r -d '' rel; do
      if [ ! -f "$src/$rel" ]; then printf '%s\\tmissing: %s\\n' "$rel" "$rel"
      elif ! cmp -s -- "$tmp/$base/$rel" "$src/$rel"; then printf '%s\\tchanged: %s\\n' "$rel" "$rel"; fi
    done > "$res"
    (cd "$src" && find . -type f -printf '%P\\0') | while IFS= read -r -d '' rel; do
      [ -f "$tmp/$base/$rel" ] || printf '%s\\textra: %s\\n' "$rel" "$rel"
    done >> "$res"
    if [ -s "$res" ]; then
      LC_ALL=C sort -t"$tab" -k1,1 "$res" | cut -f2-
      rm -f "$res"
      exit 1
    fi
    rm -f "$res"
    echo "all ok"
''')


def make_verify(rng):
    arc = TAR({"data/a.txt": "A\n", "data/my docs/b c.txt": "B\n", "data/-dash": "D\n", "data/gone": "G\n", "data/same": "S\n"})
    ex = scn("example", {"b.tar": TAR({"d/a": "1\n"}), "d/a": F("1\n")}, Run("b.tar", "d"))
    live = {"data/a.txt": F("A\n"), "data/my docs/b c.txt": F("B changed\n"), "data/-dash": F("D\n"), "data/same": F("S\n"), "data/new file": F("n\n"), "data/sub/deeper": F("x\n")}
    return ex, [scn("differences", {"b.tar": arc, **live}, Run("b.tar", "data")), scn("identical", {"b.tar": arc, "data/a.txt": F("A\n"), "data/my docs/b c.txt": F("B\n"), "data/-dash": F("D\n"), "data/gone": F("G\n"), "data/same": F("S\n")}, Run("b.tar", "data/")),
                scn("usage", {"b.tar": arc, **live}, Run("b.tar"), Run("b.tar", "nope"), Run("missing.tar", "data"), Run("b.tar", "data/sub"))]


# ------------------------------------------------------------------------------------------------ 7. snapshot with exclusions

REF_EXCL = dd('''
    #!/usr/bin/env bash
    # snapshot-x.sh SRC DEST STAMP EXCLUDES : like snapshot.sh but skipping files that match a pattern of EXCLUDES
    usage() { echo "usage: snapshot-x.sh SRC DEST STAMP EXCLUDES" >&2; exit 2; }
    [ $# -eq 4 ] && [ -d "$1" ] && [ -r "$4" ] || usage
    src=$1 dest=$2 stamp=$3 ex=$4
    [[ $stamp =~ ^[A-Za-z0-9._-]+$ ]] || usage
    while [ "${#src}" -gt 1 ] && [ "${src%/}" != "$src" ]; do src=${src%/}; done
    base=$(basename -- "$src")
    parent=$(dirname -- "$src")
    out=$dest/backup-$stamp.tar
    [ ! -e "$out" ] || { echo "error: $out exists" >&2; exit 1; }
    mkdir -p -- "$dest"
    list=$(mktemp)
    skipped=0
    while IFS= read -r -d '' rel; do
      hit=0
      while IFS= read -r pat || [ -n "$pat" ]; do
        case $pat in ''|'#'*) continue ;; esac
        # shellcheck disable=SC2254
        case $rel in $pat) hit=1; break ;; esac
      done < "$ex"
      if [ "$hit" = 1 ]; then skipped=$((skipped + 1)); else printf '%s/%s\\0' "$base" "$rel" >> "$list"; fi
    done < <(cd "$src" && find . -type f -printf '%P\\0' | LC_ALL=C sort -z)
    tar -cf "$out" -C "$parent" --null -T "$list"
    rm -f "$list"
    echo "created: backup-$stamp.tar"
    echo "excluded: $skipped"
''')


def make_excl(rng):
    ex = scn("example", {"p/a.txt": F("1"), "p/b.log": F("2"), "ex": F("*.log\n")}, Run("p", "o", "s1", "ex"))
    f = {"proj/main.c": F("int main;\n"), "proj/notes.log": F("log\n"), "proj/build/out.o": F("obj\n"), "proj/build/keep.txt": F("k\n"), "proj/my docs/draft.tmp": F("t\n"), "proj/my docs/final.txt": F("f\n"), "proj/.cache/x": F("c\n"),
         "proj/-odd.log": F("o\n"), "proj/sub/deep.log": F("d\n"), "rules.txt": F("# patterns\n*.log\n\nbuild/*\n*.tmp\n.cache/*\n")}
    return ex, [scn("excludes", f, Run("proj", "bk", "run1", "rules.txt")), scn("empty pattern file", {**f, "none.txt": F("")}, Run("proj", "bk", "all", "none.txt")), scn("usage", f, Run("proj", "bk", "x"), Run("proj", "bk", "x", "missing.txt"), Run("nope", "bk", "x", "rules.txt"))]


# ------------------------------------------------------------------------------------------------ 8. latest archive

REF_LATEST = dd('''
    #!/usr/bin/env bash
    # latest.sh [--list] DEST : newest backup archive name (or all, newest first). Names: backup-YYYYMMDD.tar or backup-YYYYMMDD-N.tar (N = run of the day, missing means 0)
    list=0
    if [ "${1:-}" = --list ]; then list=1; shift; fi
    [ $# -eq 1 ] && [ -d "$1" ] || { echo "usage: latest.sh [--list] DEST" >&2; exit 2; }
    tab=$(printf '\\t')
    out=$(cd "$1" && find . -mindepth 1 -maxdepth 1 -type f -printf '%f\\n' | awk '
      match($0, /^backup-[0-9]{8}(-[0-9]+)?\\.tar$/) {
        s = $0; sub(/^backup-/, "", s); sub(/\\.tar$/, "", s)
        d = substr(s, 1, 8); n = (length(s) > 8) ? substr(s, 10) + 0 : 0
        printf "%s\\t%d\\t%s\\n", d, n, $0 }' | LC_ALL=C sort -t"$tab" -k1,1r -k2,2nr -k3,3r | cut -f3)
    [ -n "$out" ] || exit 1
    if [ "$list" = 1 ]; then printf '%s\\n' "$out"; else printf '%s\\n' "$out" | head -n 1; fi
''')


def make_latest(rng):
    f = {"b/backup-20310101.tar": F("a"), "b/backup-20310101-2.tar": F("b"), "b/backup-20310101-10.tar": F("c"), "b/backup-20310101-3.tar": F("d"), "b/backup-20301231.tar": F("e"), "b/backup-2031010.tar": F("f"), "b/backup-20310101-x.tar": F("g"),
         "b/notes.tar": F("h"), "b/backup-20310102.tar.gz": F("i"), "b/backup-20310099.tar": F("j"), "b/sub/backup-20320101.tar": F("k")}
    ex = scn("example", {"b/backup-20310101.tar": F("1"), "b/backup-20310102.tar": F("2")}, Run("b"), Run("--list", "b"))
    return ex, [scn("ordering", f, Run("b"), Run("--list", "b")), scn("nothing there", {"b/x": F("1")}, Run("b"), Run("--list", "b")), scn("usage", f, Run(), Run("nope"), Run("--list"))]


# ------------------------------------------------------------------------------------------------ 9. fix backup.sh

BUG_BACKUP = dd('''
    #!/bin/bash
    # backup.sh SRC DEST : write DEST/backup.tar holding everything in SRC
    tar -cf $2/backup.tar $1/*
    echo "backup done"
''')
REF_BACKUP = dd('''
    #!/bin/bash
    # backup.sh SRC DEST : write DEST/backup.tar holding everything in SRC
    [ $# -eq 2 ] && [ -d "$1" ] || { echo "usage: backup.sh SRC DEST" >&2; exit 2; }
    mkdir -p -- "$2" || exit 1
    tar -cf "$2/backup.tar" -C "$1" . || exit 1
    echo "backup done"
''')


def make_backup(rng):
    ex = scn("example", {"src/a": F("1"), "src/b c": F("2")}, Run("src", "out"))
    f = {"my files/a b.txt": F("1\n"), "my files/.hidden": F("h\n"), "my files/-dash": F("d\n"), "my files/sub dir/deep": F("x\n"), "my files/*star": F("s\n")}
    return ex, [scn("awkward names and hidden files", f, Run("my files", "dest dir")), scn("existing destination", {**f, "dest/old.txt": F("keep me\n")}, Run("my files", "dest")), scn("usage", f, Run("nope", "d", stderr="nonempty"), Run("my files"))]


# ------------------------------------------------------------------------------------------------ 10. prune old archives

REF_PRUNE = dd('''
    #!/usr/bin/env bash
    # prune-old.sh DEST DAYS TODAY : delete backup-YYYYMMDD.tar older than DAYS days before TODAY (YYYY-MM-DD), but never the newest archive
    dest=${1:-} days=${2:-} today=${3:-}
    case $days in ''|*[!0-9]*) days= ;; esac
    if [ -z "$days" ] || [ ! -d "$dest" ] || ! [[ $today =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || ! now=$(date -u -d "$today" +%s 2>/dev/null); then
      echo "usage: prune-old.sh DEST DAYS YYYY-MM-DD" >&2
      exit 2
    fi
    names=$(cd "$dest" && find . -mindepth 1 -maxdepth 1 -type f -name 'backup-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].tar' -printf '%f\\n' | LC_ALL=C sort)
    [ -n "$names" ] || exit 0
    newest=$(printf '%s\\n' "$names" | tail -n 1)
    printf '%s\\n' "$names" | while IFS= read -r n; do
      [ "$n" != "$newest" ] || continue
      d=${n#backup-}; d=${d%.tar}
      iso=${d:0:4}-${d:4:2}-${d:6:2}
      e=$(date -u -d "$iso" +%s 2>/dev/null) || continue
      if [ $(( (now - e) / 86400 )) -gt "$days" ]; then
        rm -f -- "$dest/$n"
        echo "removed: $n"
      fi
    done
''')


def make_prune(rng):
    ex = scn("example", {"b/backup-20310101.tar": F("1"), "b/backup-20310301.tar": F("2")}, Run("b", "30", "2031-03-10"))
    f = {f"b/backup-{d}.tar": F(d) for d in ["20300101", "20310101", "20310201", "20310215", "20310220", "20310301", "20310302", "20310399", "20310228"]}
    f.update({"b/notes.txt": F("n"), "b/backup-20200101.tar.gz": F("g"), "b/sub/backup-20100101.tar": F("s")})
    return ex, [scn("old ones go, newest stays", f, Run("b", "14", "2031-03-02"), Run("b", "14", "2031-03-02")), scn("everything old but the newest", f, Run("b", "0", "2040-01-01")), scn("usage", f, Run("b", "x", "2031-03-02"), Run("b", "5", "2031-13-02"), Run("nope", "5", "2031-03-02"), Run("b", "5"))]


SPECS = [
    S("tar-snapshot", 2,
      "Write `snapshot.sh SRC DEST STAMP`: archive a directory as `DEST/backup-STAMP.tar` with a predictable layout.",
      "`bash snapshot.sh SRC DEST STAMP` creates the tar archive `DEST/backup-STAMP.tar` (creating `DEST` if needed) holding every file and symlink below the directory `SRC` - hidden files included - with member names `BASENAME/relative/path`, where `BASENAME` is the last component of `SRC` (trailing slashes ignored). "
      "It prints `created: backup-STAMP.tar`. If that archive already exists it prints an error on stderr and exits with status 1 without touching it. `STAMP` may only contain letters, digits, `.`, `_` and `-`; a missing `SRC`, a bad `STAMP` or the wrong number of arguments: usage message on stderr, exit status 2. "
      "The tests compare the archive's members and their contents.",
      REF_SNAP, make_snap, script="snapshot.sh", title="Tar snapshot", wrong=("#!/bin/bash\ntar -cf \"$2/backup-$3.tar\" $1/*\n",)),
    S("selective-restore", 3,
      "Write `restore.sh [-f] ARCHIVE DEST [PATH...]`: extract a snapshot, optionally only some paths, without clobbering existing files unless forced.",
      "`bash restore.sh [-f] ARCHIVE DEST [PATH...]` extracts the regular files of the tar `ARCHIVE` into `DEST` (created if needed), keeping their relative paths. With `PATH` arguments only members equal to a `PATH` or below it (`PATH/...`, a trailing slash on `PATH` is ignored) are extracted. "
      "A file that already exists in `DEST` is **not** overwritten and `skipped: <member>` is printed, unless `-f` is given; extracted files print `restored: <member>`. Lines appear in byte-wise order of the member names. Missing arguments or archive: usage message on stderr, exit status 2.",
      REF_RESTORE, make_restore, script="restore.sh", title="Selective restore", wrong=("#!/bin/bash\ntar -xf \"$1\" -C \"$2\"\n",)),
    S("rsync-like-mirror", 4,
      "Write `mirror.sh SRC DEST`: bring DEST in line with SRC the way a minimal rsync would, reporting what it copied and removed.",
      "`bash mirror.sh SRC DEST` makes the regular files below `DEST` equal to those below `SRC` (`DEST` is created if missing). A file is copied (with `cp -p`, preserving the modification time, creating directories as needed) when it is missing in `DEST` or its size or its modification time (whole seconds) differs; "
      "files in `DEST` that do not exist in `SRC` are deleted, and directories left empty in `DEST` are removed. Print `copied: <path>` and `removed: <path>` lines, relative to the roots, sorted byte-wise by path. A second run therefore prints nothing. A missing `SRC` or wrong argument count: usage message on stderr, exit status 2.",
      REF_MIRROR, make_mirror, script="mirror.sh", title="A minimal mirror", wrong=("#!/bin/bash\ncp -r \"$1\"/. \"$2\"/\n",)),
    S("rotate-snapshot-dirs", 2,
      "Write `rotate-snaps.sh DEST KEEP`: keep the newest KEEP snapshot directories and delete the older ones.",
      "`bash rotate-snaps.sh DEST KEEP` looks at the directories directly inside `DEST` whose names are `snap-` followed by exactly eight digits (`snap-20310101`); other entries (files, `snap-latest`, shorter or longer numbers) are never touched. "
      "The `KEEP` highest names (byte-wise) are kept; every other snapshot directory is removed recursively and `removed: <name>` is printed, oldest first. `KEEP` must be a positive integer and `DEST` an existing directory, otherwise usage message on stderr and exit 2.",
      REF_ROTS, make_rots, script="rotate-snaps.sh", title="Rotate snapshot directories", wrong=("#!/bin/bash\nls -d \"$1\"/snap-* | head -n -$2 | xargs rm -rf\n",)),
    S("hardlinked-snapshots", 4,
      "Write `hardlink-snap.sh SRC DEST STAMP`: make a new full snapshot directory in which unchanged files are hard links to the previous snapshot's files.",
      "`bash hardlink-snap.sh SRC DEST STAMP` creates the directory `DEST/STAMP` (and `DEST` if needed) holding a complete copy of the files below `SRC`. The *previous snapshot* is the directory of `DEST` with the byte-wise greatest name before this run (none on the first run). "
      "For each file whose path exists in the previous snapshot with identical content create a **hard link** to that file; every other file is copied with `cp -p`. Print `linked: <path>` or `copied: <path>` per file, byte-wise sorted by path. "
      "If `DEST/STAMP` already exists: error on stderr, exit 1, nothing changed. Missing `SRC`, a `STAMP` with characters other than letters, digits, `.`, `_`, `-`, or wrong arguments: usage message, exit status 2. The tests check link counts.",
      REF_HLS, make_hls, script="hardlink-snap.sh", title="Hard-linked snapshots", wrong=("#!/bin/bash\nmkdir -p \"$2/$3\" && cp -a \"$1\"/. \"$2/$3\"/\n",)),
    S("verify-archive-against-directory", 3,
      "Write `verify.sh ARCHIVE SRC`: check a snapshot tar (as made by `snapshot.sh`) against the live directory and report the differences.",
      "`bash verify.sh ARCHIVE SRC`: `ARCHIVE` is a tar whose members live under `BASENAME/` (the last component of `SRC`). Compare the regular files of the archive with those below `SRC` and print, byte-wise sorted by relative path: "
      "`missing: <path>` (in the archive, not in `SRC`), `changed: <path>` (both, different content) and `extra: <path>` (in `SRC`, not in the archive), then exit with status 1. If nothing differs print `all ok` and exit 0. "
      "A missing archive or directory, an archive without `BASENAME/` or the wrong argument count: usage message on stderr, exit status 2.",
      REF_VERIFY, make_verify, script="verify.sh", title="Verify a snapshot", wrong=("#!/bin/bash\necho all ok\n",)),
    S("snapshot-with-exclusions", 3,
      "Write `snapshot-x.sh SRC DEST STAMP EXCLUDES`: like the tar snapshot, but skipping files that match patterns from a file.",
      "`bash snapshot-x.sh SRC DEST STAMP EXCLUDES` creates `DEST/backup-STAMP.tar` as `snapshot.sh` does (members `BASENAME/relative/path`, regular files only, `DEST` created if needed, error exit 1 if the archive exists), leaving out every file whose path relative to `SRC` matches a pattern from the `EXCLUDES` file. "
      "Patterns are one per line (blank lines and `#` lines ignored) and use shell `case` glob rules on the whole relative path, so `*` also matches `/` (`*.log` skips logs at any depth, `build/*` everything below `build`). "
      "It prints `created: backup-STAMP.tar` and `excluded: N` with the number of skipped files. Missing `SRC` or pattern file, bad `STAMP` or wrong argument count: usage message on stderr, exit 2.",
      REF_EXCL, make_excl, script="snapshot-x.sh", title="Snapshot with exclusions", wrong=("#!/bin/bash\ntar -cf \"$2/backup-$3.tar\" -C \"$(dirname $1)\" \"$(basename $1)\"\nmkdir -p $2\n",)),
    S("newest-backup-archive", 3,
      "Write `latest.sh [--list] DEST`: name the newest backup archive in a directory, or list all, with a same-day run counter in the names.",
      "`bash latest.sh [--list] DEST` considers the regular files directly in `DEST` named `backup-YYYYMMDD.tar` or `backup-YYYYMMDD-N.tar` (`N` digits: the n-th run of that day; a name without it counts as run 0). Newest means latest date, then highest run number (numerically). "
      "Print the newest name, or with `--list` all matching names, newest first. If there is no matching file print nothing and exit with status 1. Missing directory or wrong arguments: usage message on stderr, exit status 2.",
      REF_LATEST, make_latest, script="latest.sh", title="Newest backup archive", wrong=("#!/bin/bash\nls \"$1\" | sort | tail -1\n",)),
    S("fix-backup-script", 2,
      "`backup.sh` makes a tar of a directory, but it loses hidden files, falls apart on names with spaces and happily continues when something fails. Fix it.",
      "`bash backup.sh SRC DEST` writes `DEST/backup.tar` (creating `DEST`, overwriting an old archive of that name, leaving other files of `DEST` alone) containing **everything** below `SRC` - hidden files too - with member names relative to `SRC` (`a b.txt`, `sub dir/deep`), then prints `backup done`. "
      "File names may contain spaces, glob characters or a leading dash. A missing `SRC` or a wrong argument count: usage message on stderr, exit status 2, no output on stdout. A failing `tar` must make the script fail (non-zero) without printing `backup done`.",
      REF_BACKUP, make_backup, script="backup.sh", buggy=BUG_BACKUP, title="Fix the backup script", wrong=(BUG_BACKUP,)),
    S("prune-old-archives", 3,
      "Write `prune-old.sh DEST DAYS TODAY`: delete backup archives older than DAYS days relative to a given date, but always keep the newest one.",
      "`bash prune-old.sh DEST DAYS TODAY` considers the regular files directly in `DEST` named `backup-YYYYMMDD.tar` whose date is a real calendar date. The newest archive (greatest name) is never deleted. Every other one whose date lies **more than `DAYS` days** before `TODAY` (`YYYY-MM-DD`) is deleted and reported as `removed: <name>`, in byte-wise order. "
      "Archives with an impossible date and all other files are left alone. `DAYS` must be a non-negative integer, `TODAY` a real date and `DEST` a directory, otherwise usage message on stderr and exit status 2.",
      REF_PRUNE, make_prune, script="prune-old.sh", title="Prune old archives", wrong=("#!/bin/bash\nfind \"$1\" -name 'backup-*.tar' -mtime +$2 -delete\n",)),
]


@family("shell-backup-tools", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="backup scripts: tar snapshots, selective restore, rsync-like mirror, hard-linked snapshots, verification, rotation and pruning")
def backup_tools(rng, n):
    return K.shell_tasks("backup-tools", SPECS, rng, n)
