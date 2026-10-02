"""Shell tasks: finding and removing duplicate files, comparing trees, checksums and manifests (names with spaces, dashes, unicode)."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, HL, L, Run, scn

S = K.ShellSpec


def fs(spec):
    """{name: (tag, mtime)} -> fixture dict; files sharing a tag share their content"""
    out = {}
    for name, v in spec.items():
        tag, m = v if isinstance(v, tuple) else (v, None)
        out[name] = F(f"contents of {tag}\n", m=m)
    return out


# ------------------------------------------------------------------------------------------------ 1. report groups

REF_REPORT = dd('''
    #!/usr/bin/env bash
    # dupes.sh DIR : print groups of files with identical content
    dir=${1:?usage: dupes.sh DIR}
    cd -- "$dir" || exit 1
    tmp=$(mktemp)
    find . -type f -size +0c -print0 | LC_ALL=C sort -z | while IFS= read -r -d '' f; do
      printf '%s\\t%s\\n' "$(sha256sum < "$f" | cut -c1-64)" "${f#./}"
    done > "$tmp"
    awk -F'\\t' '
      { n[$1]++; names[$1] = names[$1] (n[$1] > 1 ? "\\n" : "") $2; if (!($1 in first)) { first[$1] = 1; order[++g] = $1 } }
      END { out = 0; for (i = 1; i <= g; i++) { h = order[i]; if (n[h] > 1) { if (out++) print ""; print names[h] } } }
    ' "$tmp"
    rm -f "$tmp"
''')


def make_report(rng):
    ex = scn("example", {**fs({"a.txt": "alpha", "copy of a.txt": "alpha", "b.txt": "beta", "unique.txt": "gamma"}), "sub/a-again.txt": F("contents of alpha\n"), "sub/other file": F("contents of beta\n")}, Run("."))
    a = fs({"my notes.txt": "n1", "-dash.txt": "n1", "naïve café.txt": "n2", "star*.txt": "n2", "it's.txt": "n2", "q?.txt": "n3", "single": "n4", "same size A": "xxxx", "same size B": "yyyy"})
    a["sub dir/-dash.txt"] = F("contents of n1\n")
    a["empty1"] = F("")
    a["empty2"] = F("")
    a["link"] = L("single")
    b = fs({"a": "one", "b": "two", "c": "three"})
    c = {"data/x/one.bin": F("A" * 100), "data/y/two.bin": F("A" * 99 + "B"), "data/y/three.bin": F("A" * 100), "data/z.bin": F("A" * 100), "outside.bin": F("A" * 100)}
    return ex, [scn("awkward names", a, Run(".")), scn("no duplicates", b, Run(".")), scn("subdirectory argument", c, Run("data"))]


# ------------------------------------------------------------------------------------------------ 2. keep oldest

REF_OLDEST = dd('''
    #!/usr/bin/env bash
    # dedupe.sh DIR : delete duplicate files, keeping the oldest copy of each
    dir=${1:?usage: dedupe.sh DIR}
    cd -- "$dir" || exit 1
    tmp=$(mktemp)
    find . -type f -size +0c -print0 | while IFS= read -r -d '' f; do
      printf '%s\\t%s\\t%s\\n' "$(sha256sum < "$f" | cut -c1-64)" "$(stat -c %Y -- "$f")" "${f#./}"
    done | LC_ALL=C sort -t"$(printf '\\t')" -k1,1 -k2,2n -k3,3 > "$tmp"
    prev=
    removed=$(mktemp)
    while IFS="$(printf '\\t')" read -r h m p; do
      if [ "$h" = "$prev" ]; then
        rm -- "$p"
        printf '%s\\n' "$p" >> "$removed"
      else
        prev=$h
      fi
    done < "$tmp"
    LC_ALL=C sort "$removed" | sed 's/^/removed: /'
    rm -f "$tmp" "$removed"
''')


def make_oldest(rng):
    T = 1700000000
    ex = scn("example", fs({"new copy.txt": ("a", T + 500), "original.txt": ("a", T), "other.txt": ("b", T + 5)}), Run("."))
    a = fs({"report (final).doc": ("r", T + 50), "report.doc": ("r", T), "Report copy.doc": ("r", T + 900), "z-tie-b": ("t", T), "z-tie-a": ("t", T), "z-tie-c": ("t", T),
            "-old": ("d", T - 10), "newer -old": ("d", T + 1), "keep me": ("k", T), "empty": ("", T)})
    a["sub/report.doc"] = F("contents of r\n", m=T - 100)
    a["sub/deep dir/ünï.doc"] = F("contents of r\n", m=T - 100)
    a["empty"] = F("")
    a["empty 2"] = F("")
    b = fs({"u1": ("1", T), "u2": ("2", T), "u3": ("3", T)})
    return ex, [scn("awkward names, ties, empty files", a, Run("."), mtimes=[]), scn("nothing to remove", b, Run(".")), scn("only the given directory", {**fs({"in/x": ("p", T + 1), "in/y": ("p", T + 2)}), "out/x": F("contents of p\n", m=T)}, Run("in"))]


# ------------------------------------------------------------------------------------------------ 3. hardlink duplicates

REF_LINK = dd('''
    #!/usr/bin/env bash
    # link.sh DIR : replace duplicate files by hard links to the oldest copy
    dir=${1:?usage: link.sh DIR}
    cd -- "$dir" || exit 1
    tmp=$(mktemp)
    find . -type f -size +0c -print0 | while IFS= read -r -d '' f; do
      printf '%s\\t%s\\t%s\\n' "$(sha256sum < "$f" | cut -c1-64)" "$(stat -c %Y -- "$f")" "${f#./}"
    done | LC_ALL=C sort -t"$(printf '\\t')" -k1,1 -k2,2n -k3,3 > "$tmp"
    prev=
    done_list=$(mktemp)
    while IFS="$(printf '\\t')" read -r h m p; do
      if [ "$h" = "$prev" ]; then
        if [ ! "$keep" -ef "$p" ]; then
          ln -f -- "$keep" "$p"
          printf '%s\\n' "$p" >> "$done_list"
        fi
      else
        prev=$h
        keep=$p
      fi
    done < "$tmp"
    LC_ALL=C sort "$done_list" | sed 's/^/linked: /'
    rm -f "$tmp" "$done_list"
''')


def make_link(rng):
    T = 1700000000
    ex = scn("example", fs({"old.bin": ("a", T), "new.bin": ("a", T + 9), "x": ("b", T)}), Run("."), nlink=True)
    a = {**fs({"first copy": ("c", T), "second copy": ("c", T + 1), "third copy": ("c", T + 2), "-solo": ("s", T), "sö.txt": ("s", T + 4)}), "sub/c": F("contents of c\n", m=T + 3)}
    b = {"orig": F("contents of h\n", m=T), "link-to-orig": HL("orig"), "indep": F("contents of h\n", m=T + 5), "other": F("contents of o\n", m=T)}
    return ex, [scn("awkward names", a, Run("."), nlink=True), scn("already linked files are left alone", b, Run("."), nlink=True),
                scn("two groups in a subdirectory", {**fs({"d/a1": ("a", T), "d/a2": ("a", T + 1), "d/b1": ("b", T), "d/b2": ("b", T + 1)}), "outside": F("contents of a\n", m=T - 5)}, Run("d"), nlink=True)]


# ------------------------------------------------------------------------------------------------ 4. same name, any case

REF_SAMENAME = dd('''
    #!/usr/bin/env bash
    # samename.sh DIR : files whose names are equal when ASCII case is ignored
    dir=${1:?usage: samename.sh DIR}
    cd -- "$dir" || exit 1
    find . -type f -print0 | LC_ALL=C sort -z | while IFS= read -r -d '' f; do
      p=${f#./}
      b=${p##*/}
      printf '%s\\t%s\\n' "$(printf '%s' "$b" | tr 'A-Z' 'a-z')" "$p"
    done | LC_ALL=C sort -t"$(printf '\\t')" -k1,1 -k2,2 | awk -F'\\t' '
      { cnt[$1]++; paths[$1] = paths[$1] "\\n  " $2; if (!($1 in seen)) { seen[$1] = 1; order[++g] = $1 } }
      END { for (i = 1; i <= g; i++) { k = order[i]; if (cnt[k] > 1) print k ":" paths[k] } }'
''')


def make_samename(rng):
    ex = scn("example", {"a/README.md": F("1"), "b/readme.md": F("2"), "c/notes.txt": F("3")}, Run("."))
    a = {"docs/Read Me.md": F("1"), "src/read me.MD": F("2"), "src/read me.md": F("3"), "x/-Opt.txt": F("4"), "y/-opt.TXT": F("5"), "z/ÉCOLE.txt": F("6"), "w/école.txt": F("7"),
         "only/Unique.c": F("8"), "a b/Makefile": F("9"), "c/makefile": F("10"), "d/MAKEFILE": F("11")}
    return ex, [scn("awkward names", a, Run(".")), scn("nothing shared", {"a/x": F("1"), "b/y": F("2")}, Run("."))]


# ------------------------------------------------------------------------------------------------ 5. size first

REF_SIZEFIRST = dd('''
    #!/usr/bin/env bash
    # sizefirst.sh DIR : duplicates, hashing only files that share their size with another file
    dir=${1:?usage: sizefirst.sh DIR}
    cd -- "$dir" || exit 1
    tab=$(printf '\\t')
    sizes=$(mktemp); cand=$(mktemp); hashed=$(mktemp); order=$(mktemp)
    find . -type f -size +0c -printf '%s\\t%P\\n' | LC_ALL=C sort -t"$tab" -k1,1n -k2,2 > "$sizes"
    awk -F'\\t' 'NR == FNR { c[$1]++; next } c[$1] > 1' "$sizes" "$sizes" > "$cand"
    echo "candidates: $(wc -l < "$cand" | tr -d ' ')"
    while IFS="$tab" read -r s p; do
      printf '%s\\t%s\\n' "$(sha256sum < "$p" | cut -c1-64)" "$p"
    done < "$cand" | LC_ALL=C sort -t"$tab" -k1,1 -k2,2 > "$hashed"
    awk -F'\\t' '{ n[$1]++; if (!($1 in first)) first[$1] = $2 } END { for (h in n) if (n[h] > 1) print first[h] "\\t" h }' "$hashed" |
      LC_ALL=C sort -t"$tab" -k1,1 > "$order"
    while IFS="$tab" read -r fp h; do
      echo "--"
      awk -F'\\t' -v h="$h" '$1 == h { print $2 }' "$hashed"
    done < "$order"
    rm -f "$sizes" "$cand" "$hashed" "$order"
''')


def make_sizefirst(rng):
    ex = scn("example", {"a": F("aaaa"), "b": F("aaaa"), "c": F("bbbb"), "d": F("longer one")}, Run("."))
    a = {"x y": F("12345"), "-z": F("12345"), "w": F("12346"), "p": F("123"), "q": F("12"), "r": F("12"), "t 1": F("hello world"), "t 2": F("hello world"), "t 3": F("hello_world"),
         "sub/ünï": F("12345"), "empty a": F(""), "empty b": F("")}
    b = {"one": F("1"), "two": F("22"), "three": F("333")}
    return ex, [scn("awkward names", a, Run(".")), scn("all sizes unique", b, Run("."))]


# ------------------------------------------------------------------------------------------------ 6. compare trees

REF_TREEDIFF = dd('''
    #!/usr/bin/env bash
    # treediff.sh A B : compare two directory trees by content
    a=${1:?usage: treediff.sh A B}
    b=${2:?usage: treediff.sh A B}
    list() { (cd -- "$1" && find . -type f -print0 | tr '\\0' '\\n' | sed 's|^\\./||'); }
    out=$(mktemp)
    { list "$a"; list "$b"; } | LC_ALL=C sort -u | while IFS= read -r p; do
      if [ -f "$a/$p" ] && [ -f "$b/$p" ]; then
        if cmp -s -- "$a/$p" "$b/$p"; then echo "same $p"; else echo "differs $p"; fi
      elif [ -f "$a/$p" ]; then
        echo "only-in-A $p"
      else
        echo "only-in-B $p"
      fi
    done > "$out"
    cat "$out"
    if grep -q -v '^same ' "$out"; then rc=1; else rc=0; fi
    rm -f "$out"
    exit $rc
''')


def make_treediff(rng):
    ex = scn("example", {"A/x.txt": F("1"), "A/y.txt": F("2"), "B/x.txt": F("1"), "B/y.txt": F("3"), "B/z.txt": F("4")}, Run("A", "B"))
    a = {"left/a b.txt": F("1"), "right/a b.txt": F("1"), "left/-dash": F("2"), "right/-dash": F("2 "), "left/sub dir/n": F("3"), "right/sub dir/n": F("3"), "left/only left": F("l"),
         "right/only right": F("r"), "left/ünï.txt": F("u"), "right/ünï.txt": F("u"), "left/case.TXT": F("c"), "right/case.txt": F("c"), "left/x/y/z": F(""), "right/x/y/z": F("")}
    b = {"one/a": F("1"), "one/b": F("2"), "two/a": F("1"), "two/b": F("2")}
    return ex, [scn("awkward names", a, Run("left", "right")), scn("identical trees exit 0", b, Run("one", "two"))]


# ------------------------------------------------------------------------------------------------ 7. fix checksum compare

BUGGY_SAME = dd('''
    #!/bin/bash
    # same.sh A B : tell whether two files have the same content
    if [ $(md5sum $1 | cut -d' ' -f1) == $(md5sum $2 | cut -d' ' -f1) ]; then
      echo identical
    else
      echo different
      exit 1
    fi
''')

REF_SAME = dd('''
    #!/bin/bash
    # same.sh A B : tell whether two files have the same content
    for f in "$1" "$2"; do
      if [ ! -f "$f" ]; then
        echo "missing: $f"
        exit 2
      fi
    done
    if cmp -s -- "$1" "$2"; then
      echo identical
    else
      echo different
      exit 1
    fi
''')


def make_same(rng):
    ex = scn("example", {"a.txt": F("hello\n"), "b.txt": F("hello\n")}, Run("a.txt", "b.txt"))
    names = {"two words": "x", "-dash": "x", "star*": "y", "q?": "y", "it's": "z", "(p)": "z", "naïve": "z", "tab\tname": "x", "plain": "x"}
    files = {n: F(f"data {t}\n") for n, t in names.items()}
    return ex, [scn("same content, awkward names", files, Run("two words", "-dash"), Run("star*", "q?"), Run("it's", "(p)"), Run("naïve", "naïve"), Run("tab\tname", "plain")),
                scn("different content", files, Run("two words", "star*"), Run("-dash", "it's")),
                scn("missing file", files, Run("two words", "no such file"), Run("no such", "plain"))]


# ------------------------------------------------------------------------------------------------ 8. keep by priority

REF_PRIO = dd('''
    #!/usr/bin/env bash
    # prio.sh DIR : delete duplicates; prefer the copy inside the earliest directory listed in prefer.txt, else the oldest
    dir=${1:?usage: prio.sh DIR}
    prefs=$PWD/prefer.txt
    cd -- "$dir" || exit 1
    rank() {
      local p=$1 i=0 pre
      if [ -f "$prefs" ]; then
        while IFS= read -r pre || [ -n "$pre" ]; do
          [ -n "$pre" ] || continue
          i=$((i + 1))
          case $p in "$pre"/*) echo "$i"; return ;; esac
        done < "$prefs"
      fi
      echo 999999
    }
    tmp=$(mktemp)
    find . -type f -size +0c -print0 | while IFS= read -r -d '' f; do
      p=${f#./}
      printf '%s\\t%s\\t%s\\t%s\\n' "$(sha256sum < "$f" | cut -c1-64)" "$(rank "$p")" "$(stat -c %Y -- "$f")" "$p"
    done | LC_ALL=C sort -t"$(printf '\\t')" -k1,1 -k2,2n -k3,3n -k4,4 > "$tmp"
    prev=
    removed=$(mktemp)
    while IFS="$(printf '\\t')" read -r h r m p; do
      if [ "$h" = "$prev" ]; then
        rm -- "$p"
        printf '%s\\n' "$p" >> "$removed"
      else
        prev=$h
      fi
    done < "$tmp"
    LC_ALL=C sort "$removed" | sed 's/^/removed: /'
    rm -f "$tmp" "$removed"
''')


def make_prio(rng):
    T = 1700000000
    ex = scn("example", {**fs({"photos/a.jpg": ("p", T), "backup/a.jpg": ("p", T - 50), "misc/a copy.jpg": ("p", T - 10)}), "prefer.txt": F("photos\nbackup\n")}, Run("."))
    a = {**fs({"keep here/x y": ("1", T + 30), "old/x y": ("1", T - 30), "other/-x": ("1", T), "keep here/uniq": ("2", T), "late/z": ("3", T), "early/z": ("3", T - 1), "early/zz": ("3", T - 1)}),
         "prefer.txt": F("keep here\nlate\n\nnothing/there\n")}
    b = fs({"p/a": ("1", T), "q/a": ("1", T - 9), "r/b": ("2", T)})
    return ex, [scn("priorities and fallback", a, Run(".")), scn("no preference file", b, Run("."))]


# ------------------------------------------------------------------------------------------------ 9. clean empties

REF_CLEAN = dd('''
    #!/usr/bin/env bash
    # clean.sh DIR : remove empty files, broken symlinks and the directories that end up empty
    dir=${1:?usage: clean.sh DIR}
    cd -- "$dir" || exit 1
    e=0; l=0; d=0
    while IFS= read -r -d '' f; do rm -- "$f"; e=$((e + 1)); done < <(find . -type f -empty -print0)
    while IFS= read -r -d '' f; do rm -- "$f"; l=$((l + 1)); done < <(find . -xtype l -print0)
    while :; do
      n=0
      while IFS= read -r -d '' f; do
        rmdir -- "$f" && { d=$((d + 1)); n=$((n + 1)); }
      done < <(find . -mindepth 1 -type d -empty -print0)
      [ "$n" -gt 0 ] || break
    done
    echo "removed $e empty files, $l broken links, $d empty directories"
''')


def make_clean(rng):
    ex = scn("example", {"keep.txt": F("x"), "empty.txt": F(""), "dir/also empty": F(""), "link": L("keep.txt"), "dead": L("gone")}, Run("."), dirs="all")
    a = {"keep/data": F("1"), "keep/empty one": F(""), "-lead/-empty": F(""), "a/b/c/d/e": F(""), "a/b/keep": F("2"), "links/ok": L("../keep/data"), "links/dead 1": L("../nowhere"),
         "links/to-empty": L("../keep/empty one"), "links/dir": L("../keep"), "links/dead dir": L("../nodir/"), "empty dir": D(), "x/y/z": D(), "ünï/empty": F("")}
    return ex, [scn("nested and broken", a, Run("."), dirs="all"), scn("nothing to clean", {"a": F("1"), "b/c": F("2")}, Run("."), dirs="all"),
                scn("only below DIR", {"in/e": F(""), "in/sub/e": F(""), "out/e": F(""), "out/d": D()}, Run("in"), dirs="all")]


# ------------------------------------------------------------------------------------------------ 10. manifests

REF_MANIFEST = dd('''
    #!/usr/bin/env bash
    # manifest.sh create DIR            : print "<sha256>  <path>" for every file, sorted by path
    # manifest.sh verify DIR MANIFEST   : compare DIR with a manifest
    tab=$(printf '\\t')
    case ${1:-} in
      create)
        cd -- "${2:?usage}" || exit 1
        find . -type f -print0 | LC_ALL=C sort -z | while IFS= read -r -d '' f; do
          printf '%s  %s\\n' "$(sha256sum < "$f" | cut -c1-64)" "${f#./}"
        done
        ;;
      verify)
        dir=${2:?usage}
        man=${3:?usage}
        res=$(mktemp)
        paths=$(mktemp)
        while IFS= read -r line || [ -n "$line" ]; do
          h=${line%%  *}
          p=${line#*  }
          printf '%s\\n' "$p" >> "$paths"
          if [ ! -f "$dir/$p" ]; then
            printf '%s\\t%s\\n' "$p" MISSING
          elif [ "$(sha256sum < "$dir/$p" | cut -c1-64)" = "$h" ]; then
            printf '%s\\t%s\\n' "$p" OK
          else
            printf '%s\\t%s\\n' "$p" FAILED
          fi
        done < "$man" > "$res"
        (cd -- "$dir" && find . -type f -print0 | tr '\\0' '\\n' | sed 's|^\\./||') | while IFS= read -r p; do
          grep -qxF -- "$p" "$paths" || printf '%s\\t%s\\n' "$p" EXTRA
        done >> "$res"
        LC_ALL=C sort -t"$tab" -k1,1 "$res" | while IFS="$tab" read -r p s; do echo "$s $p"; done
        if grep -q -v "${tab}OK\\$" "$res"; then rc=1; else rc=0; fi
        rm -f "$res" "$paths"
        exit $rc
        ;;
      *)
        echo "usage: manifest.sh create DIR | verify DIR MANIFEST" >&2
        exit 2
        ;;
    esac
''')


def make_manifest(rng):
    import hashlib

    def man(files):
        return "".join(f"{hashlib.sha256(v['c'].encode()).hexdigest()}  {k}\n" for k, v in sorted(files.items(), key=lambda kv: kv[0].encode()))
    f1 = {"a.txt": F("alpha\n"), "b c.txt": F("beta\n"), "sub/d": F("delta\n")}
    ex = scn("example", {"data/" + k: v for k, v in f1.items()}, Run("create", "data"))
    base = {"x y.txt": F("1\n"), "-dash": F("2\n"), "sub dir/ünï": F("3\n"), "star*": F("4\n"), "plain": F("5\n")}
    good = man(base)
    tampered = {**base, "x y.txt": F("1!\n")}
    extra = {**base, "new file": F("n\n")}
    missing = {k: v for k, v in base.items() if k != "plain"}
    lines = good.splitlines(True)
    mixed_man = good + man({"ghost one": F("g\n")})
    return ex, [
        scn("create", {"d/" + k: v for k, v in base.items()}, Run("create", "d")),
        scn("verify ok", {**{"d/" + k: v for k, v in base.items()}, "m.txt": F(good)}, Run("verify", "d", "m.txt")),
        scn("verify tampered, extra, missing", {**{"d/" + k: v for k, v in {**tampered, "new file": F("n\n")}.items() if k != "plain"}, "m.txt": F(mixed_man)}, Run("verify", "d", "m.txt")),
        scn("verify extra only", {**{"d/" + k: v for k, v in extra.items()}, "m.txt": F(good)}, Run("verify", "d", "m.txt")),
        scn("bad usage", {}, Run("frobnicate")),
    ]


# ------------------------------------------------------------------------------------------------ 11. biggest files

REF_BIGGEST = dd('''
    #!/usr/bin/env bash
    # biggest.sh N DIR : the N largest files below DIR
    n=${1:-}
    dir=${2:-}
    case $n in
      ''|*[!0-9]*|0) echo "usage: biggest.sh N DIR  (N a positive integer)" >&2; exit 2 ;;
    esac
    [ -d "$dir" ] || { echo "not a directory: $dir" >&2; exit 2; }
    cd -- "$dir" || exit 1
    find . -type f -printf '%s\\t%P\\n' | LC_ALL=C sort -t"$(printf '\\t')" -k1,1nr -k2,2 | head -n "$n"
''')


def make_biggest(rng):
    ex = scn("example", {"d/a": F("x" * 10), "d/b c": F("x" * 300), "d/sub/e": F("x" * 20)}, Run("2", "d"))
    a = {"d/big one": F("x" * 500), "d/-dash": F("x" * 500), "d/sub dir/ünï": F("x" * 100), "d/z": F("x" * 100), "d/a": F("x" * 100), "d/tiny": F("x"), "d/empty": F(""), "d/s*r": F("x" * 7), "d/link": L("big one")}
    return ex, [scn("top three with ties", a, Run("3", "d")), scn("more than there are", a, Run("100", "d")), scn("bad arguments", a, Run("0", "d"), Run("x", "d"), Run("3", "nope"), Run())]


SPECS = [
    S("duplicate-groups", 2,
      "Write `dupes.sh DIR` that prints the groups of files in DIR (recursively) that have identical content. The README has the exact output format and the awkward cases.",
      "`bash dupes.sh DIR` looks at every regular file below `DIR` (symlinks and empty files are ignored) and prints the groups of files whose contents are byte-for-byte identical. "
      "Each group is a list of file paths relative to `DIR` (no `./` prefix), one per line in byte-wise sorted order; groups are separated by one empty line and ordered by their first path. "
      "Files that have no twin are not printed. Nothing is printed when there are no duplicates. File names never contain line breaks or tabs.",
      REF_REPORT, make_report, script="dupes.sh", title="Duplicate groups",
      wrong=("""#!/bin/bash
cd "$1" && md5sum $(find . -type f) | sort | uniq -w32 -D
""",)),
    S("dedupe-keep-oldest", 3,
      "I need `dedupe.sh DIR`: delete duplicate files below DIR, keeping the oldest copy of each. The README settles ties and what to print.",
      "`bash dedupe.sh DIR` finds files below `DIR` with identical content (empty files are never treated as duplicates). In each group it keeps the file with the oldest modification time; "
      "on a tie it keeps the one whose relative path is first in byte-wise order. All others are deleted. For every deleted file it prints `removed: <path relative to DIR>`, "
      "sorted byte-wise by path. Nothing else is printed. Names contain no line breaks or tabs.",
      REF_OLDEST, make_oldest, script="dedupe.sh", title="Deduplicate, keep the oldest",
      wrong=("""#!/bin/bash
cd "$1" && for f in $(find . -type f); do for g in $(find . -type f); do [ "$f" != "$g" ] && cmp -s "$f" "$g" && rm -f "$g"; done; done
""",)),
    S("hardlink-duplicates", 4,
      "Disk space is tight, so instead of deleting duplicates I want them hard-linked together. Write `link.sh DIR`; the README explains the keep rule and which files to skip.",
      "`bash link.sh DIR` finds files below `DIR` with identical content (empty files are ignored), keeps the one with the oldest modification time in each group "
      "(tie: first relative path in byte-wise order) and replaces every other copy with a **hard link** to it (same inode). Copies that already are hard links of the kept file are left alone and not reported. "
      "For every file it replaced it prints `linked: <path relative to DIR>` in byte-wise order. File contents never change. Names contain no line breaks or tabs.",
      REF_LINK, make_link, script="link.sh", title="Hard-link duplicates",
      wrong=("""#!/bin/bash
cd "$1" && for f in $(find . -type f); do for g in $(find . -type f); do [ "$f" != "$g" ] && cmp -s "$f" "$g" && ln -sf "$f" "$g"; done; done
""",)),
    S("same-name-any-case", 2,
      "Write `samename.sh DIR` that lists files that share a file name once case is ignored (`README.md` vs `readme.md`), grouped, with their paths. See the README for the layout.",
      "`bash samename.sh DIR` considers every regular file below `DIR`. The *name* of a file is its last path component; two names are equal when they are equal after lowercasing ASCII letters only. "
      "For every name that occurs 2 or more times it prints a line `<lowercased name>:` followed by one line per file, each indented with exactly two spaces, showing the path relative to `DIR`, "
      "in byte-wise sorted order. Groups are ordered by the lowercased name (byte-wise). Names that occur once are not printed.",
      REF_SAMENAME, make_samename, script="samename.sh", title="Same name, any case",
      wrong=("""#!/bin/bash
cd "$1" && find . -type f | sed 's|.*/||' | sort -f | uniq -di
""",)),
    S("size-first-dedupe", 3,
      "Hashing every file of a big tree is slow. Write `sizefirst.sh DIR` that finds duplicates but only reads files that share their size with another file, and reports how many that was.",
      "`bash sizefirst.sh DIR` ignores empty files and symlinks. A file is a **candidate** when at least one other regular file below `DIR` has the same size in bytes. "
      "The first line printed is `candidates: N` (N = number of candidate files). Then, for every group of candidates with identical content (2 or more files) it prints a line `--` followed by the group's relative paths, "
      "one per line in byte-wise order; groups are ordered by their first path. Files with a unique size must not be hashed or read. Names contain no line breaks or tabs.",
      REF_SIZEFIRST, make_sizefirst, script="sizefirst.sh", title="Duplicates, size first",
      wrong=("""#!/bin/bash
cd "$1" && echo "candidates: $(find . -type f -size +0c | wc -l)"
""",)),
    S("compare-trees", 3,
      "Write `treediff.sh A B` that compares two directory trees by content and lists every path with its status. README has the statuses and the exit code rule.",
      "`bash treediff.sh A B` compares the regular files below directories `A` and `B` by content. For every relative path that exists in either tree (byte-wise sorted, each path once) it prints "
      "`same <path>`, `differs <path>` (exists in both with different bytes), `only-in-A <path>` or `only-in-B <path>`. The exit status is 0 when every line is `same` (or both trees have no files), otherwise 1. Names contain no line breaks.",
      REF_TREEDIFF, make_treediff, script="treediff.sh", title="Compare two trees",
      wrong=("""#!/bin/bash
diff -rq "$1" "$2"
""",)),
    S("fix-same-file-check", 2,
      "`same.sh` tells whether two files have the same content, but it breaks as soon as a file name has a space (or looks like an option). Fix it and make it report missing files sensibly.",
      "`bash same.sh A B` prints `identical` (exit 0) when the files `A` and `B` have the same bytes and `different` (exit 1) when they do not. If either path is not a regular file it prints `missing: <path>` "
      "(for the first missing one, `A` before `B`) and exits with status 2. It must work for any file names: spaces, leading dashes, glob characters, quotes.",
      REF_SAME, make_same, script="same.sh", buggy=BUGGY_SAME, title="Compare two files", wrong=(BUGGY_SAME,)),
    S("dedupe-with-priorities", 4,
      "Write `prio.sh DIR`: remove duplicate files below DIR, but let a `prefer.txt` list decide which directory's copy survives. The README gives the full rule.",
      "`bash prio.sh DIR` is run from a directory that may contain `prefer.txt` (next to the script's working directory, not inside `DIR`): one directory prefix per line (relative to `DIR`), highest priority first; blank lines are ignored. "
      "Among files with identical content (empty files ignored) keep the copy whose path lies inside the earliest-listed prefix (the path starts with `<prefix>/`); copies in no listed directory rank last. Remaining ties are broken by the oldest modification time, then the first relative path in byte-wise order. "
      "Delete all others and print `removed: <path>` for each, byte-wise sorted. A missing `prefer.txt` means no preferences. Names contain no line breaks or tabs.",
      REF_PRIO, make_prio, script="prio.sh", title="Deduplicate by directory priority",
      wrong=("""#!/bin/bash
cd "$1" && find . -type f -size +0c | head -0
""",)),
    S("clean-empties", 3,
      "Write `clean.sh DIR` to sweep a tree: delete empty files and broken symlinks, then prune the directories that are empty after that, and print a one-line summary.",
      "`bash clean.sh DIR` does three things below `DIR`, in this order: (1) delete every empty regular file; (2) delete every symlink whose target does not exist (a link to a file removed in step 1 is now broken; links to directories that exist are fine); "
      "(3) repeatedly delete directories that are empty, including ones that only become empty because of the earlier steps, but never `DIR` itself. "
      "Finally print exactly `removed E empty files, L broken links, D empty directories` with the counts (directories that were already empty are counted too).",
      REF_CLEAN, make_clean, script="clean.sh", title="Sweep empty files, dead links and empty directories",
      wrong=("""#!/bin/bash
cd "$1" && find . -empty -delete
""",)),
    S("checksum-manifest", 4,
      "Write `manifest.sh`: `create DIR` prints a SHA-256 manifest of a tree and `verify DIR MANIFEST` checks a tree against one, reporting problems per file. The README has the formats and exit codes.",
      "`bash manifest.sh create DIR` prints one line per regular file below `DIR`: the lowercase hex SHA-256 of its content, two spaces, and its path relative to `DIR` (no `./`), sorted byte-wise by path. "
      "`bash manifest.sh verify DIR MANIFEST` reads such a manifest and prints one line per path involved, byte-wise sorted by path: `OK <path>` (content matches), `FAILED <path>` (file present, different hash), "
      "`MISSING <path>` (listed but not in `DIR`) or `EXTRA <path>` (in `DIR` but not listed). The exit status is 0 only when every line is `OK`. Any other first argument prints a usage line on stderr and exits with status 2. Names contain no line breaks or tabs.",
      REF_MANIFEST, make_manifest, script="manifest.sh", title="Checksum manifests",
      wrong=("""#!/bin/bash
case $1 in create) cd "$2" && sha256sum $(find . -type f | sort);; verify) cd "$2" && sha256sum -c "../$3";; esac
""",)),
    S("largest-files", 2,
      "Write `biggest.sh N DIR` printing the N largest files below DIR with their sizes. Details (format, ties, error handling) are in the README.",
      "`bash biggest.sh N DIR` prints the `N` largest regular files below `DIR` (symlinks are not files here), one per line as `<size in bytes>`, a TAB, `<path relative to DIR>`; "
      "largest first, equal sizes ordered by path (byte-wise). Fewer lines if fewer files exist. `N` must be a positive integer and `DIR` an existing directory; otherwise print a usage message on stderr and exit with status 2 without printing anything on stdout.",
      REF_BIGGEST, make_biggest, script="biggest.sh", title="N largest files",
      wrong=("""#!/bin/bash
cd "$2" && ls -S | head -n "$1"
""",)),
]


@family("shell-dedupe-audit", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="duplicate files and tree audits in shell: hashing, keep rules, hard links, manifests, size-first scanning")
def dedupe(rng, n):
    return K.shell_tasks("dedupe-audit", SPECS, rng, n)
