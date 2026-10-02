"""Shell tasks: find/xargs-style tree work with awkward names: size and age filters, extension counts, pruning, exec bits, empty dirs, symlink audits."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec
T = 1700000000
DAY = 86400


def fz(spec):
    return {k: (F(v[0], m=v[1]) if isinstance(v, tuple) else F(v)) for k, v in spec.items()}


# ------------------------------------------------------------------------------------------------ 1. bigger than

REF_BIG = dd('''
    #!/usr/bin/env bash
    # bigger.sh DIR BYTES : regular files below DIR larger than BYTES bytes, relative paths, byte-wise sorted
    dir=${1:-}
    n=${2:-}
    case $n in ''|*[!0-9]*) echo "usage: bigger.sh DIR BYTES" >&2; exit 2 ;; esac
    [ -d "$dir" ] || { echo "usage: bigger.sh DIR BYTES" >&2; exit 2; }
    find "$dir" -type f -size +"${n}c" -printf '%P\\n' | LC_ALL=C sort
''')


def make_big(rng):
    ex = scn("example", {"d/a": F("x" * 10), "d/b": F("x" * 100)}, Run("d", "50"))
    f = {"d/small": F("x" * 10), "d/exactly 100": F("x" * 100), "d/one over": F("x" * 101), "d/-dash big": F("x" * 500), "d/sub dir/deep file": F("x" * 1000), "d/sub dir/tiny": F("x"), "d/empty": F(""), "d/link": L("one over"), "outside": F("x" * 5000)}
    return ex, [scn("sizes", f, Run("d", "100"), Run("d", "0"), Run("d", "5000"), Run("d/sub dir", "10")), scn("usage", f, Run("d"), Run("nope", "1"), Run("d", "-5"), Run("d", "ten"))]


# ------------------------------------------------------------------------------------------------ 2. older than N days

REF_OLD = dd('''
    #!/usr/bin/env bash
    # older.sh DIR DAYS NOW : regular files below DIR whose mtime is at least DAYS days before the epoch NOW
    dir=${1:-} days=${2:-} now=${3:-}
    case $days$now in *[!0-9]*) echo "usage: older.sh DIR DAYS NOW" >&2; exit 2 ;; esac
    [ -n "$days" ] && [ -n "$now" ] && [ -d "$dir" ] || { echo "usage: older.sh DIR DAYS NOW" >&2; exit 2; }
    limit=$((now - days * 86400))
    find "$dir" -type f ! -newermt "@$limit" -printf '%P\\n' | LC_ALL=C sort
''')


def make_old(rng):
    now = T + 100 * DAY
    ex = scn("example", {"d/new": F("n", m=now - DAY), "d/old": F("o", m=now - 40 * DAY)}, Run("d", "30", str(now)))
    f = {"d/at the limit": F("a", m=now - 30 * DAY), "d/one second newer": F("b", m=now - 30 * DAY + 1), "d/one second older": F("c", m=now - 30 * DAY - 1), "d/-ancient": F("d", m=T), "d/sub/fresh file": F("e", m=now),
         "d/sub/old one": F("f", m=now - 365 * DAY), "d/future": F("g", m=now + 5 * DAY), "d/link": L("-ancient")}
    return ex, [scn("boundary", f, Run("d", "30", str(now)), Run("d", "0", str(now)), Run("d", "365", str(now))), scn("usage", f, Run("d", "30", stderr="nonempty"), Run("d", "x", "5"), Run("nope", "1", "5"))]


# ------------------------------------------------------------------------------------------------ 3. extension counts

REF_EXT = dd('''
    #!/usr/bin/env bash
    # extcount.sh DIR : number of regular files per extension (lower-cased ASCII), "(none)" for files without one
    dir=${1:-}
    [ -d "$dir" ] || { echo "usage: extcount.sh DIR" >&2; exit 2; }
    find "$dir" -type f -printf '%f\\n' | awk '
      { name = $0
        if (name ~ /^\\.[^.]*$/ || name !~ /\\./ || name ~ /\\.$/) ext = "(none)"
        else { ext = name; sub(/^.*\\./, "", ext); ext = tolower(ext) }
        n[ext]++ }
      END { for (e in n) print n[e], e }' | LC_ALL=C sort -k1,1nr -k2,2
''')


def make_ext(rng):
    ex = scn("example", {"d/a.TXT": F("1"), "d/b.txt": F("2"), "d/c.md": F("3"), "d/Makefile": F("4")}, Run("d"))
    f = {"d/one.JPG": F("1"), "d/two.jpg": F("2"), "d/sub dir/three.Jpg": F("3"), "d/.bashrc": F("4"), "d/.hidden.TXT": F("5"), "d/archive.tar.gz": F("6"), "d/other.GZ": F("7"), "d/trailing.": F("8"), "d/README": F("9"), "d/no dot/Makefile": F("a"),
         "d/-dash.md": F("b"), "d/x.md": F("c"), "d/y.md": F("d"), "d/e.é": F("e"), "d/link.txt": L("README")}
    return ex, [scn("counts", f, Run("d")), scn("empty tree and usage", {"e/": D(), "f": F("x")}, Run("e"), Run("nope", stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 4. grep with pruning

REF_GREP = dd('''
    #!/usr/bin/env bash
    # grepfiles.sh TEXT DIR : *.txt and *.md files below DIR containing TEXT (a fixed string), skipping .git and node_modules directories
    [ $# -eq 2 ] && [ -d "$2" ] || { echo "usage: grepfiles.sh TEXT DIR" >&2; exit 2; }
    find "$2" \\( -name .git -o -name node_modules \\) -prune -o -type f \\( -name '*.txt' -o -name '*.md' \\) -print0 |
      xargs -0 -r grep -lZF -e "$1" -- 2>/dev/null | while IFS= read -r -d '' f; do printf '%s\\n' "${f#"$2"/}"; done | LC_ALL=C sort
    exit 0
''')


def make_grep(rng):
    ex = scn("example", {"d/a.txt": F("needle here\n"), "d/b.md": F("nothing\n"), "d/node_modules/x.txt": F("needle\n")}, Run("needle", "d"))
    f = {"d/notes.txt": F("TODO: fix a.b*c\nsecond\n"), "d/my docs/readme.md": F("see a.b*c and -x\n"), "d/-weird.txt": F("-x here\n"), "d/src/code.c": F("a.b*c in code\n"), "d/.git/config.txt": F("a.b*c\n"),
         "d/node_modules/pkg/info.md": F("a.b*c\n"), "d/sub/node_modules.txt": F("a.b*c\n"), "d/UPPER.TXT": F("a.b*c\n"), "d/empty.md": F(""), "d/axbxc.txt": F("axbxc\n"), "d/deep/er/still.md": F("-x\nmore\n")}
    return ex, [scn("fixed strings", f, Run("a.b*c", "d"), Run("-x", "d"), Run("nothing at all", "d")), scn("usage", f, Run("x", stderr="nonempty"), Run("x", "nope"))]


# ------------------------------------------------------------------------------------------------ 5. exec bits for scripts

REF_EXEC = dd('''
    #!/usr/bin/env bash
    # execbits.sh DIR : scripts (first two bytes "#!") become executable, all other regular files not executable; reports changes
    dir=${1:-}
    [ -d "$dir" ] || { echo "usage: execbits.sh DIR" >&2; exit 2; }
    cd -- "$dir" || exit 2
    tmp=$(mktemp)
    while IFS= read -r -d '' f; do
      want=0
      [ "$(head -c 2 -- "$f")" = '#!' ] && want=1
      if [ -x "$f" ]; then have=1; else have=0; fi
      if [ "$want" != "$have" ]; then
        if [ "$want" = 1 ]; then chmod a+x -- "$f"; else chmod a-x -- "$f"; fi
        printf '%s\\n' "${f#./}" >> "$tmp"
      fi
    done < <(find . -type f -print0)
    LC_ALL=C sort "$tmp" | sed 's/^/fixed: /'
    rm -f "$tmp"
''')


def make_exec(rng):
    ex = scn("example", {"d/run.sh": F("#!/bin/sh\necho hi\n"), "d/data.txt": F("plain\n", x=True)}, Run("d"))
    f = {"d/tool": F("#!/usr/bin/env python3\nprint(1)\n"), "d/already run": F("#!/bin/sh\n", x=True), "d/notes.txt": F("hello\n"), "d/old.sh": F("echo no shebang\n", x=True), "d/-odd": F("#!x\n"), "d/hash only": F("# comment\n#!late\n"),
         "d/empty": F(""), "d/one": F("#"), "d/sub dir/s.sh": F("#!/bin/bash\n"), "d/sub dir/d.bin": F("\x7fELF-ish\n", x=True), "d/link": L("tool")}
    return ex, [scn("scripts and data", f, Run("d"), Run("d")), scn("usage", f, Run(stderr="nonempty"), Run("nope"))]


# ------------------------------------------------------------------------------------------------ 6. empty directories

REF_EMPTYD = dd('''
    #!/usr/bin/env bash
    # emptydirs.sh DIR : directories below DIR that contain nothing at all, relative paths, byte-wise sorted
    dir=${1:-}
    [ -d "$dir" ] || { echo "usage: emptydirs.sh DIR" >&2; exit 2; }
    find "$dir" -mindepth 1 -type d -empty -printf '%P\\n' | LC_ALL=C sort
''')


def make_emptyd(rng):
    ex = scn("example", {"d/a/": D(), "d/b/file": F("x")}, Run("d"))
    f = {"d/empty one": D(), "d/-dash": D(), "d/has file/x": F("1"), "d/only dirs/inner": D(), "d/only dirs/inner2/deeper": D(), "d/hidden/.dot": F("h"), "d/.hidden empty": D(), "d/link dir": L("has file"), "d/ünï": D(), "d/files/a/b/c/d.txt": F("x")}
    return ex, [scn("empty dirs", f, Run("d")), scn("none", {"d/x": F("1")}, Run("d")), scn("usage", f, Run(stderr="nonempty"), Run("nope"))]


# ------------------------------------------------------------------------------------------------ 7. sizes per top-level directory

REF_DIRSZ = dd('''
    #!/usr/bin/env bash
    # dirsizes.sh DIR : "BYTES<TAB>NAME" per immediate subdirectory (total size of its regular files, recursively) and "." for files directly in DIR; largest first
    dir=${1:-}
    [ -d "$dir" ] || { echo "usage: dirsizes.sh DIR" >&2; exit 2; }
    cd -- "$dir" || exit 2
    tab=$(printf '\\t')
    {
      find . -mindepth 1 -maxdepth 1 -type f -printf '%s\\t.\\n'
      find . -mindepth 2 -type f -printf '%s\\t%P\\n' | awk -F'\\t' '{ n = $2; sub(/\\/.*/, "", n); print $1 "\\t" n }'
      find . -mindepth 1 -maxdepth 1 -type d -printf '0\\t%P\\n'
    } | awk -F'\\t' '{ s[$2] += $1 } END { for (k in s) print s[k] "\\t" k }' | LC_ALL=C sort -t"$tab" -k1,1nr -k2,2
''')


def make_dirsz(rng):
    ex = scn("example", {"d/a/x": F("1" * 10), "d/b/y": F("1" * 5), "d/top": F("1" * 3)}, Run("d"))
    f = {"d/big dir/one": F("x" * 400), "d/big dir/sub/two": F("x" * 100), "d/-dash/f": F("x" * 500), "d/empty dir/": D(), "d/loose.txt": F("x" * 7), "d/.hidden/h": F("x" * 50), "d/zebra/z": F("x" * 5), "d/alpha/a": F("x" * 5), "d/link": L("big dir")}
    return ex, [scn("sizes", f, Run("d")), scn("only files", {"d/a": F("12"), "d/b": F("1")}, Run("d")), scn("usage", f, Run(stderr="nonempty"), Run("nope"))]


# ------------------------------------------------------------------------------------------------ 8. delete listed files

REF_DELL = dd('''
    #!/usr/bin/env bash
    # deletelisted.sh LIST : delete the regular files named in LIST (one name per line, exact); report missing ones, then the count
    list=${1:-}
    [ -r "$list" ] || { echo "usage: deletelisted.sh LIST" >&2; exit 2; }
    n=0
    while IFS= read -r name || [ -n "$name" ]; do
      [ -n "$name" ] || continue
      if [ -f "$name" ] && [ ! -L "$name" ]; then
        rm -f -- "$name"
        n=$((n + 1))
      else
        echo "missing: $name"
      fi
    done < "$list"
    echo "deleted $n"
''')


def make_dell(rng):
    ex = scn("example", {"a.txt": F("1"), "b.txt": F("2"), "list": F("a.txt\nnope.txt\n")}, Run("list"))
    f = {"my file.txt": F("1"), "-rf": F("2"), "star*.txt": F("3"), "keep.txt": F("4"), "dir/inner file": F("5"), "link": L("keep.txt"), "a dir": D(), "tail ": F("6"),
         "list.txt": F("my file.txt\n-rf\n\nstar*.txt\nstar-nothing.txt\ndir/inner file\nlink\na dir\ntail \nnot here\n")}
    return ex, [scn("awkward names", f, Run("list.txt"), Run("list.txt")), scn("empty list and usage", {"e": F(""), "x": F("1")}, Run("e"), Run("missing", stderr="nonempty"), Run())]


# ------------------------------------------------------------------------------------------------ 9. newest file per subdirectory

REF_NEWEST = dd('''
    #!/usr/bin/env bash
    # newestper.sh DIR : for each immediate subdirectory, its newest regular file (directly inside it): "SUBDIR<TAB>FILE"
    dir=${1:-}
    [ -d "$dir" ] || { echo "usage: newestper.sh DIR" >&2; exit 2; }
    cd -- "$dir" || exit 2
    tab=$(printf '\\t')
    find . -mindepth 2 -maxdepth 2 -type f -printf '%T@\\t%h\\t%f\\n' | sed 's|\\t\\./|\\t|' |
      LC_ALL=C sort -t"$tab" -k2,2 -k1,1nr -k3,3r | awk -F'\\t' '!($2 in s) { s[$2] = 1; print $2 "\\t" $3 }' | LC_ALL=C sort
''')


def make_newest(rng):
    ex = scn("example", {"d/a/old": F("1", m=T), "d/a/new": F("2", m=T + 100), "d/b/only": F("3", m=T)}, Run("d"))
    f = {"d/photos/one.jpg": F("1", m=T + 10), "d/photos/two.jpg": F("2", m=T + 20), "d/photos/zz tie": F("3", m=T + 20), "d/-dash/older": F("4", m=T), "d/-dash/newer file": F("5", m=T + 5), "d/-dash/sub/newest but nested": F("6", m=T + 999),
         "d/empty/": D(), "d/dirs only/inner/x": F("7", m=T + 7), "d/.hidden/h": F("8", m=T + 1), "d/loose": F("9", m=T + 50), "d/tie/b": F("a", m=T + 1), "d/tie/a": F("b", m=T + 1)}
    return ex, [scn("newest per directory", f, Run("d")), scn("usage", f, Run(stderr="nonempty"), Run("nope"))]


# ------------------------------------------------------------------------------------------------ 10. symlink audit

REF_LINKS = dd('''
    #!/usr/bin/env bash
    # linkaudit.sh DIR : every symlink below DIR as "PATH -> TARGET [ok]" or "[broken]", sorted by path
    dir=${1:-}
    [ -d "$dir" ] || { echo "usage: linkaudit.sh DIR" >&2; exit 2; }
    cd -- "$dir" || exit 2
    find . -type l -print0 | LC_ALL=C sort -z | while IFS= read -r -d '' l; do
      t=$(readlink -- "$l")
      if [ -e "$l" ]; then st=ok; else st=broken; fi
      printf '%s -> %s [%s]\\n' "${l#./}" "$t" "$st"
    done
''')


def make_links(rng):
    ex = scn("example", {"d/real": F("1"), "d/good": L("real"), "d/dead": L("gone")}, Run("d"))
    f = {"d/file one": F("1"), "d/sub/target": F("2"), "d/ok rel": L("file one"), "d/ok abs-ish": L("sub/target"), "d/sub/up": L("../file one"), "d/broken": L("nowhere"), "d/-dash link": L("sub"), "d/loop a": L("loop b"), "d/loop b": L("loop a"),
         "d/to dir": L("sub"), "d/dangling dir": L("nodir/"), "d/chain1": L("chain2"), "d/chain2": L("file one")}
    return ex, [scn("audit", f, Run("d")), scn("no links and usage", {"d/x": F("1")}, Run("d"), Run("nope", stderr="nonempty"), Run())]


# ------------------------------------------------------------------------------------------------ 11. fix: delete .tmp files

BUG_RMTMP = dd('''
    #!/bin/bash
    # rmtmp.sh DIR : delete every regular *.tmp file below DIR and say how many
    n=$(find $1 -name *.tmp | wc -l)
    find $1 -name *.tmp | xargs rm
    echo "removed $n"
''')
REF_RMTMP = dd('''
    #!/bin/bash
    # rmtmp.sh DIR : delete every regular *.tmp file below DIR and say how many
    dir=${1:-}
    [ -d "$dir" ] || { echo "usage: rmtmp.sh DIR" >&2; exit 2; }
    n=$(find "$dir" -type f -name '*.tmp' -print0 | tr -cd '\\0' | wc -c)
    find "$dir" -type f -name '*.tmp' -print0 | xargs -0 -r rm -f --
    echo "removed $n"
''')


def make_rmtmp(rng):
    ex = scn("example", {"d/a.tmp": F("1"), "d/b.txt": F("2")}, Run("d"))
    f = {"d/one.tmp": F("1"), "d/two words.tmp": F("2"), "d/-dash.tmp": F("3"), "d/sub dir/deep file.tmp": F("4"), "d/keep.txt": F("5"), "d/tmpdir.tmp/inner.tmp": F("6"), "d/new\nline.tmp": F("7"), "d/.hidden.tmp": F("8"), "d/not.tmp.txt": F("9"), "d/star*.tmp": F("a"), "d/link.tmp": L("keep.txt")}
    return ex, [scn("awkward names", f, Run("d")), scn("nothing to remove", {"d/a": F("1")}, Run("d")), scn("usage", f, Run(stderr="nonempty"), Run("nope"))]


SPECS = [
    S("files-bigger-than", 2,
      "Write `bigger.sh DIR BYTES`, listing the regular files below DIR that are larger than BYTES bytes.",
      "`bash bigger.sh DIR BYTES` prints the paths, relative to `DIR`, of all regular files below it (symlinks are not regular files) whose size is **strictly greater** than `BYTES`, one per line in byte-wise order. File names contain no line breaks. "
      "`BYTES` must be a non-negative integer (digits only) and `DIR` an existing directory, otherwise usage message on stderr and exit status 2.",
      REF_BIG, make_big, script="bigger.sh", title="Files bigger than N bytes", wrong=("#!/bin/bash\nfind $1 -size +$2 -type f\n",)),
    S("files-older-than-days", 3,
      "Write `older.sh DIR DAYS NOW`: list files at least DAYS days older than a reference time given as an epoch, so the result is reproducible.",
      "`bash older.sh DIR DAYS NOW` prints, relative to `DIR` and byte-wise sorted, the regular files below it whose modification time is **at most** `NOW - DAYS*86400` (seconds since the epoch, `DAYS` and `NOW` non-negative integers); i.e. files at least `DAYS` days old at time `NOW`. "
      "Files modified later than that, in the future, and symlinks are not listed. Bad or missing arguments, or a missing directory: usage message on stderr, exit status 2.",
      REF_OLD, make_old, script="older.sh", title="Files older than N days", wrong=("#!/bin/bash\nfind $1 -type f -mtime +$2\n",)),
    S("count-files-per-extension", 3,
      "Write `extcount.sh DIR` that counts files per extension below DIR and prints the busiest extensions first.",
      "`bash extcount.sh DIR` looks at every regular file below `DIR` (any depth, hidden files included, symlinks not counted). The extension is what follows the **last** dot in the file's base name, lower-cased (ASCII); a name without a dot, with a dot only as its first character (`.bashrc`) "
      "or a dot as its last character has no extension and is counted as `(none)`. Print `COUNT EXT` per extension (one space), largest count first, equal counts in byte-wise order of the extension. A directory without files prints nothing. Missing directory: usage message on stderr, exit 2.",
      REF_EXT, make_ext, script="extcount.sh", title="Files per extension", wrong=("#!/bin/bash\nfind \"$1\" -type f | sed 's/.*\\.//' | sort | uniq -c | sort -rn\n",)),
    S("grep-text-files-pruned", 3,
      "Write `grepfiles.sh TEXT DIR`: list the `.txt` and `.md` files below DIR that contain a literal string, never looking inside `.git` or `node_modules`.",
      "`bash grepfiles.sh TEXT DIR` prints, relative to `DIR` and byte-wise sorted, the files whose name ends in `.txt` or `.md` (case-sensitive) and whose content contains `TEXT` as a **fixed string** (no regular expressions; `TEXT` may start with a dash or contain `*` and `.`). "
      "Directories named `.git` or `node_modules` are skipped entirely (a *file* called `node_modules.txt` is fine). Exit status 0 even when nothing matches. Wrong arguments or a missing directory: usage message on stderr, exit 2. File names may contain spaces and a leading dash.",
      REF_GREP, make_grep, script="grepfiles.sh", title="Grep in text files", wrong=("#!/bin/bash\ngrep -rl \"$1\" \"$2\"\n",)),
    S("make-scripts-executable", 3,
      "Write `execbits.sh DIR`: files that start with `#!` must be executable and everything else must not be; report what it changed.",
      "`bash execbits.sh DIR` looks at every regular file below `DIR` (symlinks are left alone). A file whose first two bytes are `#!` must be executable (`chmod a+x`), every other file must not be (`chmod a-x`). "
      "For each file whose executable state it changed print `fixed: <path relative to DIR>`, byte-wise sorted; files already in the right state are not reported. A second run therefore prints nothing. Missing directory or argument: usage message on stderr, exit 2.",
      REF_EXEC, make_exec, script="execbits.sh", title="Executable scripts", wrong=("#!/bin/bash\nfind \"$1\" -type f -exec chmod +x {} +\n",)),
    S("list-empty-directories", 2,
      "Write `emptydirs.sh DIR`: list the directories below DIR that have nothing inside them.",
      "`bash emptydirs.sh DIR` prints the paths (relative to `DIR`, byte-wise sorted) of the directories below it that contain no entries at all - not even hidden files, symlinks or other empty directories (a directory that only holds an empty directory is **not** empty). "
      "`DIR` itself is never listed. A missing directory or argument prints a usage message on stderr and exits with status 2.",
      REF_EMPTYD, make_emptyd, script="emptydirs.sh", title="Empty directories", wrong=("#!/bin/bash\nfind \"$1\" -type d\n",)),
    S("size-per-top-level-directory", 3,
      "Write `dirsizes.sh DIR`, a poor man's `du`: the total size of the files in each immediate subdirectory, largest first.",
      "`bash dirsizes.sh DIR` prints `BYTES<TAB>NAME` for every immediate subdirectory of `DIR` (hidden ones included, symlinks excluded): `BYTES` is the total size of the regular files anywhere below it (0 for an empty one). Regular files lying directly in `DIR` are summed under the name `.`, which is printed too when there is at least one. "
      "Sorted by size descending, equal sizes by name byte-wise. Missing directory or argument: usage message on stderr, exit status 2.",
      REF_DIRSZ, make_dirsz, script="dirsizes.sh", title="Size per top-level directory", wrong=("#!/bin/bash\ndu -sb \"$1\"/*\n",)),
    S("delete-files-from-list", 2,
      "Write `deletelisted.sh LIST`: delete the files named in a list file (any characters allowed in names), reporting the ones that do not exist.",
      "`bash deletelisted.sh LIST` reads `LIST` line by line; every non-empty line is the exact name of a file, relative to the current directory. If it names an existing **regular file** (not a symlink, not a directory) it is deleted; otherwise `missing: <name>` is printed (in list order). "
      "At the end print `deleted N`. Names may contain spaces, glob characters or start with a dash; a last line without trailing newline counts. An unreadable list or a missing argument: usage message on stderr, exit status 2.",
      REF_DELL, make_dell, script="deletelisted.sh", title="Delete files from a list", wrong=("#!/bin/bash\nxargs rm < \"$1\"\n",)),
    S("newest-file-per-subdirectory", 3,
      "Write `newestper.sh DIR`: for each immediate subdirectory print its newest file (looking only at files directly inside it).",
      "`bash newestper.sh DIR` prints `SUBDIR<TAB>FILE` for each immediate subdirectory of `DIR` (hidden ones included) that holds at least one regular file directly inside it: `FILE` is the file name with the newest modification time; on equal times the byte-wise **last** name. "
      "Files in deeper levels and files lying directly in `DIR` are ignored. Output sorted byte-wise by subdirectory name. Missing directory or argument: usage message on stderr, exit 2.",
      REF_NEWEST, make_newest, script="newestper.sh", title="Newest file per subdirectory", wrong=("#!/bin/bash\nls -t \"$1\"\n",)),
    S("symlink-audit", 3,
      "Write `linkaudit.sh DIR`: report every symlink below DIR with its target and whether the target exists.",
      "`bash linkaudit.sh DIR` prints one line `PATH -> TARGET [ok]` or `PATH -> TARGET [broken]` for every symbolic link below `DIR` (any depth, hidden included), byte-wise sorted by path (relative to `DIR`); `TARGET` is the link's text as stored (not resolved). "
      "A link is `ok` when following it ends at an existing file or directory, `broken` when it dangles or loops. Missing directory or argument: usage message on stderr and exit status 2.",
      REF_LINKS, make_links, script="linkaudit.sh", title="Symlink audit", wrong=("#!/bin/bash\nfind \"$1\" -type l -xtype l\n",)),
    S("fix-delete-tmp-files", 2,
      "`rmtmp.sh` deletes the `.tmp` files below a directory with `find | xargs rm`, which misbehaves on names with spaces and when the shell expands `*.tmp`. Fix it.",
      "`bash rmtmp.sh DIR` deletes every regular file whose name ends in `.tmp` anywhere below `DIR` (hidden files too; directories named `x.tmp` and symlinks are left alone) and prints `removed N`. "
      "File names may contain spaces, leading dashes, glob characters or even line breaks. Missing directory or argument: usage message on stderr, exit 2.",
      REF_RMTMP, make_rmtmp, script="rmtmp.sh", buggy=BUG_RMTMP, title="Delete temp files", wrong=(BUG_RMTMP,)),
]


@family("shell-find-xargs", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="find/xargs-style tree tools with awkward names: size and age filters, extension counts, pruning, exec bits, empty dirs, symlink audits")
def find_xargs(rng, n):
    return K.shell_tasks("find-xargs", SPECS, rng, n)
