"""Shell tasks, expert bash tooling: atomic release switching with pruning and rollback, dotenv layering with references and cycle detection, semantic-version sorting, a symlink farm with conflict pre-checks, a resumable batch runner."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec


def lines(rows):
    return "".join(r + "\n" for r in rows)


def rep(text, a, b):
    """replace `a` by `b`; the lines of `a` match whatever indentation the text has"""
    import re
    parts = [re.escape(x.strip()) if i == 0 else r"\n[ ]*" + re.escape(x.strip()) for i, x in enumerate(a.split("\n"))]
    rx = "".join(parts) if len(parts) == 1 else "".join(parts)
    m = re.search(rx, text)
    assert m, a
    return text[:m.start()] + b + text[m.end():]


# ------------------------------------------------------------------------------------------------ 1. release switcher

REF_DEPLOY = dd(r'''
    #!/usr/bin/env bash
    # deploy.sh release SRC | rollback | status : release directories with an atomically switched `current` link
    keep=3
    usage() { echo "usage: deploy.sh release SRC | rollback | status" >&2; exit 2; }
    cur() { if [ -L current ]; then basename -- "$(readlink current)"; fi; }
    releases() {
      local d
      for d in releases/*/; do
        [ -d "$d" ] && basename -- "$d"
      done | LC_ALL=C sort
    }
    switch() {
      rm -f .current.tmp
      ln -s "releases/$1" .current.tmp && mv -T .current.tmp current
    }
    [ $# -ge 1 ] || usage
    case $1 in
      release)
        [ $# -eq 2 ] || usage
        src=$2
        [ -d "$src" ] || { echo "error: no such directory: $src" >&2; exit 1; }
        id=${RELEASE_ID:-}
        [[ $id =~ ^[0-9A-Za-z._-]+$ ]] || { echo "error: RELEASE_ID missing or bad" >&2; exit 2; }
        if [ -e "releases/$id" ]; then echo "error: release $id exists" >&2; exit 1; fi
        mkdir -p "releases/$id" || exit 1
        cp -R -- "$src"/. "releases/$id"/ || exit 1
        switch "$id" || exit 1
        mapfile -t all < <(releases)
        c=$(cur)
        for ((i = 0; i < ${#all[@]} - keep; i++)); do
          [ "${all[i]}" = "$c" ] || rm -rf -- "releases/${all[i]}"
        done
        echo "released $id"
        ;;
      rollback)
        [ $# -eq 1 ] || usage
        mapfile -t all < <(releases)
        c=$(cur)
        prev=""
        for r in "${all[@]}"; do
          [ "$r" = "$c" ] && break
          prev=$r
        done
        if [ -z "$c" ] || [ -z "$prev" ]; then echo "error: nothing to roll back to" >&2; exit 1; fi
        switch "$prev" || exit 1
        echo "rolled back to $prev"
        ;;
      status)
        [ $# -eq 1 ] || usage
        c=$(cur)
        echo "current: ${c:-none}"
        releases | while IFS= read -r r; do
          if [ "$r" = "$c" ]; then echo "* $r"; else echo "  $r"; fi
        done
        ;;
      *) usage ;;
    esac
''')

DOC_DEPLOY = dd(r'''
    `deploy.sh` manages release directories in the current directory (the application directory): `releases/ID/` holds one release, and the symbolic link `current` points to the live one with the **relative** target `releases/ID`.

    * `deploy.sh release SRC` copies the contents of the directory SRC (including hidden files) to `releases/ID/`, where `ID` is the environment variable `RELEASE_ID` (letters, digits, `.`, `_`, `-`), then switches `current` to `releases/ID` **atomically**
      (build the new link under a temporary name and rename it over `current`, so `current` never disappears; the checker rejects scripts that use `ln -f`/`ln --force` or `rm` the old link first, because that is not a rename), and finally prunes: only the newest 3 releases (byte-wise order of the `ID`s) are kept, but the release `current` points to is never deleted.
      It prints `released ID`. Errors (message on standard error, nothing changed): SRC is not a directory (exit 1); `RELEASE_ID` missing or not of that form (exit 2); `releases/ID` already exists (exit 1).
    * `deploy.sh rollback` points `current` at the release that comes just before the current one in the byte-wise order of the `ID`s, prints `rolled back to ID`, and deletes nothing. If `current` is missing or there is no earlier release it prints a message to standard error and exits with status 1.
    * `deploy.sh status` prints `current: ID` (`current: none` when there is no link) and then one line per release in order: `* ID` for the live one and `  ID` (two spaces) for the others.
    * Anything else (unknown subcommand, wrong number of arguments): a usage line on standard error, exit status 2. No temporary files may be left behind.
''')


def make_deploy(rng):
    ex = scn("example", {"build/app.txt": F("v1\n")}, Run("release", "build", env={"RELEASE_ID": "20350101"}))
    files = {"my build/app.txt": F("version two\n"), "my build/.hidden": F("secret\n"), "my build/bin/run.sh": F("#!/bin/sh\necho run\n", x=True), "my build/empty": D(), "other/x": F("x\n")}

    def rel(i):
        return {"RELEASE_ID": i}
    return ex, [scn("first release and a second", files, Run("release", "my build", env=rel("20350101")), Run("status"), Run("release", "other", env=rel("20350102")), Run("status")),
                scn("pruning keeps three", files, *[Run("release", "my build", env=rel(f"2035020{i}")) for i in range(1, 6)], Run("status")),
                scn("rollback", files, Run("release", "my build", env=rel("r1")), Run("release", "other", env=rel("r2")), Run("release", "my build", env=rel("r3")), Run("rollback"), Run("status"), Run("rollback"), Run("rollback", stderr="nonempty"), Run("status")),
                scn("release after a rollback never deletes the live release", files, Run("release", "my build", env=rel("a")), Run("release", "other", env=rel("b")), Run("release", "my build", env=rel("c")), Run("release", "other", env=rel("d")),
                    Run("rollback"), Run("rollback"), Run("release", "my build", env=rel("e")), Run("status")),
                scn("a release with an old id is still live", files, Run("release", "my build", env=rel("m1")), Run("release", "other", env=rel("m2")), Run("release", "my build", env=rel("m3")), Run("release", "other", env=rel("a0")), Run("status"), Run("rollback", stderr="nonempty"), Run("release", "my build", env=rel("m4")), Run("status")),
                scn("errors", files, Run("release", "nodir", env=rel("x"), stderr="nonempty"), Run("release", "my build", stderr="nonempty"), Run("release", "my build", env=rel("bad id"), stderr="nonempty"),
                    Run("release", "my build", env=rel("v1")), Run("release", "other", env=rel("v1"), stderr="nonempty"), Run("rollback", stderr="nonempty"), Run("frobnicate", stderr="nonempty"), Run(stderr="nonempty"), Run("status", "extra", stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 2. env file layers

REF_ENV = dd(r'''
    #!/usr/bin/env bash
    # envmerge.sh FILE... : layer dotenv files (later wins), expand ${NAME} and ${NAME:-default}, print KEY=value lines sorted
    declare -A val mode
    bad=0
    for f in "$@"; do
      n=0
      while IFS= read -r line || [ -n "$line" ]; do
        n=$((n + 1))
        line=${line#"${line%%[![:space:]]*}"}
        line=${line%"${line##*[![:space:]]}"}
        [ -z "$line" ] && continue
        [[ $line == \#* ]] && continue
        line=${line#export }
        if [[ $line =~ ^([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*(.*)$ ]]; then
          k=${BASH_REMATCH[1]}
          raw=${BASH_REMATCH[2]}
          if [[ $raw =~ ^\"(.*)\"$ ]]; then v=${BASH_REMATCH[1]}; m=expand
          elif [[ $raw =~ ^\'(.*)\'$ ]]; then v=${BASH_REMATCH[1]}; m=literal
          elif [[ $raw == \"* || $raw == \'* ]]; then echo "$f:$n: unbalanced quote" >&2; bad=1; continue
          else v=$raw; m=expand
          fi
          val[$k]=$v
          mode[$k]=$m
        else
          echo "$f:$n: not a KEY=VALUE line" >&2
          bad=1
        fi
      done < "$f"
    done
    [ "$bad" -eq 0 ] || exit 2
    RX='\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}'
    refs() { # names referenced by key $1
      local s=${val[$1]} out=""
      [ "${mode[$1]}" = expand ] || return 0
      while [[ $s =~ $RX ]]; do
        out+=" ${BASH_REMATCH[1]}"
        s=${s#*"${BASH_REMATCH[0]}"}
      done
      echo "$out"
    }
    declare -A reach
    keys=("${!val[@]}")
    for k in "${keys[@]}"; do
      for r in $(refs "$k"); do
        [ -n "${val[$r]+x}" ] && reach[$k,$r]=1
      done
    done
    changed=1
    while [ "$changed" -eq 1 ]; do
      changed=0
      for a in "${keys[@]}"; do
        for b in "${keys[@]}"; do
          [ -n "${reach[$a,$b]+x}" ] || continue
          for c in "${keys[@]}"; do
            if [ -n "${reach[$b,$c]+x}" ] && [ -z "${reach[$a,$c]+x}" ]; then reach[$a,$c]=1; changed=1; fi
          done
        done
      done
    done
    circ=()
    for a in "${keys[@]}"; do
      for b in "${keys[@]}"; do
        if [ -n "${reach[$a,$b]+x}" ] && [ -n "${reach[$b,$b]+x}" ]; then circ+=("$a"); break; fi
      done
    done
    if [ ${#circ[@]} -gt 0 ]; then
      echo "circular: $(printf '%s\n' "${circ[@]}" | LC_ALL=C sort | paste -sd' ' -)"
      exit 1
    fi
    resolve() {
      local k=$1 s out="" name def whole
      if [ "${mode[$k]}" = literal ]; then printf '%s' "${val[$k]}"; return; fi
      s=${val[$k]}
      while [[ $s =~ $RX ]]; do
        whole=${BASH_REMATCH[0]}; name=${BASH_REMATCH[1]}; def=${BASH_REMATCH[3]}
        out+=${s%%"$whole"*}
        if [ -n "${val[$name]+x}" ]; then r=$(resolve "$name"); else r=""; fi
        if [[ $whole == *:-* && -z $r ]]; then r=$def; fi
        out+=$r
        s=${s#*"$whole"}
      done
      printf '%s' "$out$s"
    }
    for k in $(printf '%s\n' "${keys[@]}" | LC_ALL=C sort); do
      printf '%s=%s\n' "$k" "$(resolve "$k")"
    done
''')

DOC_ENV = dd(r'''
    `envmerge.sh FILE...` layers dotenv-style files and prints the resulting settings. Later files override earlier ones key by key.

    * Lines are `KEY=VALUE` (KEY starts with a letter or `_`, then letters, digits, `_`), optionally preceded by `export `, with blanks allowed around the key and the `=`. Leading and trailing blanks of the line are ignored. Blank lines and lines starting with `#` are skipped.
      There are no trailing comments: everything after the `=` belongs to the value. A value that starts and ends with double quotes loses the quotes; one in single quotes loses them and is **literal** (no expansion); an unquoted value is taken as is.
      A value that begins with a quote and does not end with the same quote is an error.
    * After layering, references inside values are expanded (except in single-quoted values): `${NAME}` becomes the final value of NAME (empty when NAME is not defined at all), and `${NAME:-default}` becomes the default text (up to the first `}`) when NAME is undefined **or empty**.
      References refer to the final, layered values and are expanded recursively; a bare `$NAME` without braces is not a reference.
    * Output: one line `KEY=VALUE` per key with the fully expanded value, sorted by key in byte order. Nothing is quoted.
    * Errors: lines that are not settings, or have an unbalanced quote, give `FILE:LINE: ...` messages for each such line and exit status 2;
      circular references (a key that, through `${...}` references in non-literal values, reaches itself, and every key that reaches such a key) print the single line `circular: K1 K2 ...` (those keys in byte order, separated by single spaces) on **standard output**, nothing else, and exit with status 1.
''')


def make_env(rng):
    ex = scn("example", {"a.env": F("HOST=db\nURL=http://${HOST}:5432\n"), "b.env": F("HOST=cache\n")}, Run("a.env", "b.env"))
    base = lines(["# base settings", "NAME = demo", "export HOME_DIR=/srv/${NAME}", "LOG_DIR=${HOME_DIR}/log", 'GREETING="hello ${NAME}"', "LITERAL='${NAME} stays'", "EMPTY=", "EMPTY_DEFAULT=${EMPTY:-fallback}", "UNSET_DEFAULT=${NOPE:-none set}",
                  "UNSET_PLAIN=[${NOPE}]", "BARE=$NAME", "EQ=a=b=c", "TWO=${NAME}-${NAME}", "  SPACED   =   value with spaces   ", "QUOTED_HASH=\"# not a comment\"", "DEEP=${LOG_DIR}/${TWO}"])
    over = lines(["NAME=prod", "export EXTRA=1", "GREETING='single ${NAME}'", "EMPTY=now set", "NEWKEY=${EXTRA:-0}${UNSET_DEFAULT}"])
    return ex, [scn("layers and expansion", {"base.env": F(base), "over.env": F(over), "empty.env": F("")}, Run("base.env", "over.env"), Run("over.env", "base.env"), Run("base.env"), Run("empty.env")),
                scn("circular references", {"c.env": F("A=${B}\nB=${C:-x}\nC=${A}\nD=${A}!\nE=ok\nF='${F}'\nG=${G}\n"), "d.env": F("X=${Y}\nY=${X:-z}\nW=${V}\nV=1\n")}, Run("c.env"), Run("d.env")),
                scn("a literal self reference is no cycle", {"l.env": F("F='${F}'\nG='${F}'\nH=${NOPE:-x}\nI=${F}\n")}, Run("l.env")),
                scn("a cycle broken by a later layer", {"c.env": F("A=${B}\nB=${A}\n"), "fix.env": F("B=fixed\n")}, Run("c.env"), Run("c.env", "fix.env")),
                scn("bad lines", {"bad.env": F("OK=1\nthis is not a setting\n9X=1\nQ=\"open\nR='open\nS=\"closed\"\n"), "good.env": F("OK=2\n")}, Run("bad.env", stderr="nonempty"), Run("good.env", "bad.env", stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 3. semantic version order

REF_VSORT = dd(r'''
    #!/usr/bin/env bash
    # vsort.sh : sort semantic versions (SemVer 2.0 precedence), stable; invalid lines go to stderr
    awk '
    function isnum(s) { return s ~ /^(0|[1-9][0-9]*)$/ }
    function valid(v,   m, core, pre, parts, n, i) {
      if (v !~ /^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$/) return 0
      sub(/\+.*/, "", v)
      pre = ""
      if (index(v, "-")) { pre = substr(v, index(v, "-") + 1); v = substr(v, 1, index(v, "-") - 1) }
      n = split(v, parts, ".")
      for (i = 1; i <= 3; i++) if (!isnum(parts[i])) return 0
      if (pre != "") {
        n = split(pre, parts, ".")
        for (i = 1; i <= n; i++) {
          if (parts[i] == "") return 0
          if (parts[i] ~ /^[0-9]+$/ && !isnum(parts[i])) return 0
        }
      }
      return 1
    }
    function cmpnum(a, b) { if (length(a) != length(b)) return length(a) < length(b) ? -1 : 1; a = a ""; b = b ""; return a < b ? -1 : (a > b ? 1 : 0) }
    function cmp(x, y,   a, b, i, n, c, pa, pb, na, nb) {
      split(core[x], a, "."); split(core[y], b, ".")
      for (i = 1; i <= 3; i++) { c = cmpnum(a[i], b[i]); if (c) return c }
      if (pre[x] == "" && pre[y] == "") return 0
      if (pre[x] == "") return 1
      if (pre[y] == "") return -1
      na = split(pre[x], pa, "."); nb = split(pre[y], pb, ".")
      n = na < nb ? na : nb
      for (i = 1; i <= n; i++) {
        if (pa[i] ~ /^[0-9]+$/ && pb[i] ~ /^[0-9]+$/) { c = cmpnum(pa[i], pb[i]); if (c) return c }
        else if (pa[i] ~ /^[0-9]+$/) return -1
        else if (pb[i] ~ /^[0-9]+$/) return 1
        else { x1 = pa[i] ""; y1 = pb[i] ""; if (x1 != y1) return x1 < y1 ? -1 : 1 }
      }
      return na < nb ? -1 : (na > nb ? 1 : 0)
    }
    /^$/ { next }
    {
      if (!valid($0)) { print "invalid: " $0 > "/dev/stderr"; bad = 1; next }
      n++
      txt[n] = $0
      v = $0; sub(/\+.*/, "", v)
      if (index(v, "-")) { pre[n] = substr(v, index(v, "-") + 1); core[n] = substr(v, 1, index(v, "-") - 1) } else { pre[n] = ""; core[n] = v }
    }
    END {
      for (i = 1; i <= n; i++) ord[i] = i
      for (i = 2; i <= n; i++) {
        k = ord[i]
        for (j = i - 1; j >= 1 && cmp(ord[j], k) > 0; j--) ord[j + 1] = ord[j]
        ord[j + 1] = k
      }
      for (i = 1; i <= n; i++) print txt[ord[i]]
      exit bad
    }'
''')

DOC_VSORT = dd(r'''
    `vsort.sh` reads version strings, one per line, from standard input and prints the valid ones sorted from the lowest to the highest version by **Semantic Versioning 2.0** precedence (`sort -V` does not follow these rules).
    A valid version is `MAJOR.MINOR.PATCH` with optional `-PRERELEASE` and optional `+BUILD`: the three numbers are decimal without leading zeros (except `0` itself); PRERELEASE is dot-separated identifiers of `[0-9A-Za-z-]` that are not empty, and numeric ones have no leading zeros; BUILD is dot-separated non-empty identifiers of `[0-9A-Za-z-]`.

    Precedence: compare MAJOR, MINOR, PATCH as numbers (they may be longer than 18 digits). A version with a PRERELEASE is **lower** than the same version without one. Two PRERELEASEs are compared identifier by identifier from the left:
    two numeric identifiers as numbers; a numeric identifier is lower than an alphanumeric one; two alphanumeric ones in byte order; when all shared identifiers are equal, the one with fewer identifiers is lower. BUILD metadata is ignored in comparisons.
    Versions of equal precedence keep their input order, and every line is printed exactly as it was read (build metadata included). Duplicates are all printed. Blank lines are skipped silently.

    A line that is not a valid version is not printed on standard output; instead `invalid: LINE` goes to standard error. The valid lines are still sorted and printed, and the exit status is 1 if any line was invalid, otherwise 0.
''')


def make_vsort(rng):
    ex = scn("example", {}, Run(stdin="1.10.0\n1.2.0\n1.2.0-rc.1\n"))
    pool = ["1.0.0", "1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "2.0.0", "2.1.0", "2.1.1", "0.9.9", "10.0.0", "1.10.0", "1.2.0", "1.0.0+build.5", "1.0.0+build.1",
            "1.0.0-alpha+001", "1.0.0-0", "1.0.0-0.3.7", "1.0.0-x.7.z.92", "1.0.0-x-y-z.--", "1.0.0-1", "1.0.0-a", "1.0.0-Z", "3.0.0-11", "3.0.0-2", "99999999999999999999.0.0", "99999999999999999998.9.9", "1.0.0-alpha.1.1", "1.0.0-alpha.1.a"]
    bad = ["1.0", "v1.2.3", "01.2.3", "1.2.3-", "1.2.3-01", "1.2.3-a..b", "1.2.3+", "1.2.3 ", "1.2.3-rc.01", "a.b.c", "1.2.3.4", "-1.2.3", "1.2.3-a_b"]
    a = rng.sample(pool, 22)
    b = rng.sample(pool, 14) + rng.sample(bad, 5) + ["1.0.0+build.5", "1.0.0+build.1", "1.0.0+build.5"]
    rng.shuffle(b)
    return ex, [scn("valid versions", {}, Run(stdin=lines(a)), Run(stdin=lines(pool))),
                scn("invalid lines", {}, Run(stdin=lines(b), stderr="nonempty"), Run(stdin=lines(bad), stderr="nonempty")),
                scn("stability and blanks", {}, Run(stdin="1.0.0+b\n\n1.0.0+a\n1.0.0\n\n0.1.0\n1.0.0+c\n"), Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 4. symlink farm

REF_FARM = dd(r'''
    #!/usr/bin/env bash
    # farm.sh install|remove TARGET PKG... : link the files of pkgs/PKG into TARGET (like GNU stow, without directory folding)
    usage() { echo "usage: farm.sh install|remove TARGET PKG..." >&2; exit 2; }
    [ $# -ge 3 ] || usage
    cmd=$1 target=${2%/}
    shift 2
    case $cmd in install | remove) ;; *) usage ;; esac
    for p in "$@"; do
      [ -d "pkgs/$p" ] || { echo "error: unknown package $p" >&2; exit 2; }
    done
    declare -A want src
    order=()
    for p in "$@"; do
      while IFS= read -r -d '' f; do
        rel=${f#"pkgs/$p/"}
        dest=$target/$rel
        if [ -n "${want[$dest]+x}" ] && [ "${src[$dest]}" != "$p" ]; then
          dup+=("$dest")
          continue
        fi
        want[$dest]=$(realpath -m --relative-to="$(dirname -- "$dest")" "$f")
        src[$dest]=$p
        order+=("$dest")
      done < <(find "pkgs/$p" -type f -print0 | LC_ALL=C sort -z)
    done
    sorted() { [ $# -gt 0 ] && printf '%s\0' "$@" | LC_ALL=C sort -zu | tr '\0' '\n'; }
    if [ "$cmd" = install ]; then
      conflicts=("${dup[@]}")
      for dest in "${order[@]}"; do
        if [ -L "$dest" ]; then
          [ "$(readlink -- "$dest")" = "${want[$dest]}" ] || conflicts+=("$dest")
          continue
        fi
        if [ -e "$dest" ]; then conflicts+=("$dest"); continue; fi
        d=$(dirname -- "$dest")
        while [ "$d" != "$target" ] && [ "$d" != "." ] && [ "$d" != "/" ]; do
          if [ -L "$d" ] || { [ -e "$d" ] && [ ! -d "$d" ]; }; then conflicts+=("$dest"); break; fi
          d=$(dirname -- "$d")
        done
      done
      if [ ${#conflicts[@]} -gt 0 ]; then
        sorted "${conflicts[@]}" | sed 's/^/conflict: /'
        exit 1
      fi
      made=()
      for dest in "${order[@]}"; do
        [ -L "$dest" ] && continue
        mkdir -p -- "$(dirname -- "$dest")"
        ln -s -- "${want[$dest]}" "$dest"
        made+=("$dest")
      done
      [ ${#made[@]} -gt 0 ] && sorted "${made[@]}" | sed 's/^/linked: /'
    else
      gone=()
      for dest in "${order[@]}"; do
        if [ -L "$dest" ] && [ "$(readlink -- "$dest")" = "${want[$dest]}" ]; then
          rm -- "$dest"
          gone+=("$dest")
        fi
      done
      [ ${#gone[@]} -gt 0 ] && sorted "${gone[@]}" | sed 's/^/unlinked: /'
      if [ -d "$target" ]; then
        find "$target" -mindepth 1 -depth -type d -empty -delete
      fi
    fi
    exit 0
''')

DOC_FARM = dd(r'''
    `farm.sh` installs configuration packages as symbolic links, like GNU `stow` without directory folding. Packages live in `pkgs/NAME/` (relative to the current directory); `farm.sh install TARGET PKG...` and `farm.sh remove TARGET PKG...`
    link or unlink **every regular file** of the named packages: the file `pkgs/PKG/a/b.conf` belongs at `TARGET/a/b.conf` (so a package mirrors the layout of its target). Empty directories inside packages are ignored.

    * **install**: for each file create the missing parent directories under TARGET and a symbolic link `TARGET/REL` whose target is the **relative** path from the link's directory to `pkgs/PKG/REL` (what `realpath -m --relative-to=LINKDIR pkgs/PKG/REL` prints).
      A link that already exists with exactly that target is fine and is left alone. **Before anything is changed**, all files of all packages are checked, and these are *conflicts*: the destination exists as anything else (a regular file, a directory, a link with another target, a link to some other place);
      a parent component of the destination exists but is not a real directory (a file, or a symbolic link); two **different** packages of this call provide the same `REL`. If there is any conflict, the script prints `conflict: DEST` for each conflicting destination (once each, sorted in byte order) on **standard output**,
      changes nothing at all (not even creating directories) and exits with status 1.
      Otherwise it creates what is missing and prints `linked: DEST` for every link it created (sorted in byte order) on standard output; exit status 0.
    * **remove**: remove those of the links that exist with exactly the target an install would have given them (nothing else is touched), printing `unlinked: DEST` for each (sorted); then delete the directories under TARGET that are now empty (but never TARGET itself, and also those that were already empty). Exit status 0.
    * An unknown package (no directory `pkgs/PKG`), a wrong command, or fewer than three arguments: message on standard error, exit status 2, nothing changed. TARGET may not exist yet for `install`. Names in the tests contain spaces and dashes but no line breaks.
''')


def make_farm(rng):
    pk = {"pkgs/shell/.bashrc": F("# bashrc\n"), "pkgs/shell/.config/prompt/theme.sh": F("theme\n"), "pkgs/git/.gitconfig": F("[user]\n"), "pkgs/git/.config/git/ignore": F("*.o\n"),
          "pkgs/my editor/.config/editor/init file.lua": F("-- init\n"), "pkgs/my editor/.config/prompt/extra.sh": F("extra\n"), "pkgs/empty-pkg/.keep-dir": D(), "pkgs/vim/.vimrc": F("set nu\n"), "pkgs/dup/.bashrc": F("# another bashrc\n"), "pkgs/dup/.config/dup/x": F("d\n")}
    ex = scn("example", {k: v for k, v in pk.items() if k.startswith("pkgs/git") or k.startswith("pkgs/shell")}, Run("install", "home", "shell", "git"))
    return ex, [scn("install twice, nothing new the second time", pk, Run("install", "home", "shell", "git"), Run("install", "home", "shell", "git", "my editor"), Run("install", "home/", "vim")),
                scn("conflicts block everything", {**pk, "home/.bashrc": F("mine\n"), "home/.config/git": F("a file where a directory is needed\n"), "home/.vimrc": L("elsewhere")},
                    Run("install", "home", "shell", "git", "vim")),
                scn("same file from two packages", pk, Run("install", "home", "shell", "dup"), Run("install", "home", "shell", "dup", "dup"), Run("install", "home", "shell")),
                scn("a linked directory is not a real directory", {**pk, "real/elsewhere/placeholder": F("x\n"), "home/.config": L("../real/elsewhere")}, Run("install", "home", "git")),
                scn("remove cleans up", pk, Run("install", "home", "shell", "git", "my editor", "vim"), Run("remove", "home", "git", "vim"), Run("remove", "home", "shell"), Run("remove", "home", "shell", "git")),
                scn("remove only touches its own links", {**pk, "home/.bashrc": F("not mine\n"), "home/.gitconfig": L("pkgs/other/.gitconfig"), "home/.config/git/ignore": L("../../../pkgs/git/.config/git/ignore"), "home/empty/leftover": D()},
                    Run("remove", "home", "shell", "git"), Run("remove", "nowhere", "git")),
                scn("errors", pk, Run("install", "home", "nosuch", stderr="nonempty"), Run("install", "home", "git", "nosuch", stderr="nonempty"), Run("upgrade", "home", "git", stderr="nonempty"), Run("install", "home", stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 5. resumable batch runner

REF_RESUME = dd(r'''
    #!/usr/bin/env bash
    # resume.sh LIST CMD [ARG...] : run CMD ARG... ITEM for every item of LIST, remembering what is done in LIST.done
    [ $# -ge 2 ] || { echo "usage: resume.sh LIST CMD [ARG...]" >&2; exit 2; }
    list=$1
    shift
    [ -f "$list" ] || { echo "error: no such list: $list" >&2; exit 2; }
    done_file=$list.done
    touch "$done_file"
    skipped=0 ran=0
    declare -A seen
    while IFS= read -r item || [ -n "$item" ]; do
      [ -z "$item" ] && continue
      [[ $item == \#* ]] && continue
      [ -n "${seen[$item]+x}" ] && continue
      seen[$item]=1
      if grep -qxF -- "$item" "$done_file"; then
        skipped=$((skipped + 1))
        continue
      fi
      "$@" "$item" < /dev/null
      rc=$?
      if [ "$rc" -ne 0 ]; then
        echo "failed: $item (status $rc)" >&2
        echo "stopped after $ran items, $skipped skipped" 
        exit 1
      fi
      printf '%s\n' "$item" >> "$done_file"
      ran=$((ran + 1))
    done < "$list"
    echo "finished: $ran run, $skipped skipped"
''')

DOC_RESUME = dd(r'''
    `resume.sh LIST CMD [ARG...]` works through the items of a list file, one command per item, and can be started again after a failure without repeating finished work.

    * Every line of LIST is an item, except blank lines and lines starting with `#`. The same item text appearing again is ignored (an item is run at most once). Items may contain spaces and other odd characters.
    * For each item in list order, unless it is already recorded as done, run `CMD ARG... ITEM` (the item as one extra last argument) with **standard input from `/dev/null`** (the command must not be able to eat the list). Whatever the command prints goes through.
      After the command succeeds, append the item as a line to the file `LIST.done` (LIST followed by `.done`; created empty at the start if missing), so that progress survives a crash. A recorded item is skipped.
    * When a command fails (non-zero status `N`) the script stops at once: `failed: ITEM (status N)` on standard error, then the line `stopped after R items, S skipped` on standard output (R = items that succeeded in this run, S = items skipped as done), and exit status 1.
    * When all items are done it prints `finished: R run, S skipped` and exits with status 0 (also for an empty list).
    * LIST missing, or fewer than two arguments: message on standard error, exit status 2.
''')


def make_resume(rng):
    cmd = "#!/bin/sh\nif [ \"$1\" = bad ] && [ ! -e allow ]; then echo \"cannot do $1\"; exit 7; fi\ncat >/dev/null\necho \"did $1\" >> work.log\necho \"ok $1\"\n"
    fx = {"cmd.sh": F(cmd, x=True), "list.txt": F("one\ntwo words\n# skipped comment\n\nbad\nthree\ntwo words\nfour")}
    ex = scn("example", {"cmd.sh": F(cmd, x=True), "list.txt": F("a\nb\n")}, Run("list.txt", "sh", "cmd.sh"))
    return ex, [scn("fail, fix, resume", fx, Run("list.txt", "sh", "cmd.sh", stderr="nonempty"), Run("list.txt", "sh", "cmd.sh", stderr="nonempty"), Run("list.txt", "sh", "cmd.sh", ops=[{"op": "write", "path": "allow", "c": "yes\n"}]), Run("list.txt", "sh", "cmd.sh")),
                scn("the command may read stdin", {"cmd.sh": F(cmd, x=True), "l": F("x\ny\nz\n")}, Run("l", "sh", "cmd.sh")),
                scn("extra arguments and odd items", {"cmd.sh": F("#!/bin/sh\necho \"$#: $*\" >> args.log\n", x=True), "my list": F("-n\n*\n$HOME\nit's\n  padded  \n")}, Run("my list", "sh", "cmd.sh", "--flag", "two words")),
                scn("done file is honoured", {"cmd.sh": F(cmd, x=True), "l": F("a\nb\nc\n"), "l.done": F("a\nc\n")}, Run("l", "sh", "cmd.sh")),
                scn("items that look like each other", {"cmd.sh": F(cmd, x=True), "l": F("app\napple\nap\na.c\nabc\n"), "l.done": F("apple\nabc\n")}, Run("l", "sh", "cmd.sh")),
                scn("empty list and errors", {"cmd.sh": F(cmd, x=True), "empty": F(""), "only comments": F("# nothing\n\n")}, Run("empty", "sh", "cmd.sh"), Run("only comments", "sh", "cmd.sh"), Run("nolist", "sh", "cmd.sh", stderr="nonempty"), Run("empty", stderr="nonempty"), Run(stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ family

SPECS = [
    S("atomic-release-switch", 4, "Write `deploy.sh`: keep numbered release directories, switch the `current` link atomically, prune old releases and support `rollback` and `status`. Read README.md.", DOC_DEPLOY, REF_DEPLOY, make_deploy, script="deploy.sh", forbid=(r"\bln\s+(-[A-Za-z]*f|--force)", r"\brm\s+(-[A-Za-z]+\s+)*(--\s+)?current\b"),
      wrong=(rep(REF_DEPLOY, "rm -f .current.tmp\n      ln -s \"releases/$1\" .current.tmp && mv -T .current.tmp current", "rm -f current\n      ln -s \"releases/$1\" current"),
             rep(REF_DEPLOY, "[ \"${all[i]}\" = \"$c\" ] || rm -rf", "rm -rf"), rep(REF_DEPLOY, "keep=3", "keep=2"),
             rep(REF_DEPLOY, 'cp -R -- "$src"/. "releases/$id"/', 'cp -R -- "$src"/* "releases/$id"/'))),
    S("dotenv-layers-with-references", 5, "Write `envmerge.sh`: layer dotenv files, expand `${NAME}` and `${NAME:-default}` references on the final values, and report circular references. Read README.md carefully.", DOC_ENV, REF_ENV, make_env, script="envmerge.sh",
      wrong=(rep(REF_ENV, '[ "${mode[$k]}" = literal ]', '[ "${mode[$k]}" = nothing ]'), rep(REF_ENV, "if [[ $whole == *:-* && -z $r ]]; then r=$def; fi", "if [[ $whole == *:-* && ! -n ${val[$name]+x} ]]; then r=$def; fi"),
             rep(REF_ENV, '[ "${mode[$1]}" = expand ] || return 0', ':'),
             rep(REF_ENV, 'if [ ${#circ[@]} -gt 0 ]; then', 'if false; then'))),
    S("semantic-version-sort", 4, "Write `vsort.sh`: sort version strings by Semantic Versioning 2.0 precedence (pre-releases, build metadata), keeping equal versions in input order and reporting invalid lines. Read README.md.", DOC_VSORT, REF_VSORT, make_vsort, script="vsort.sh",
      wrong=("#!/usr/bin/env bash\nsort -V\n", rep(REF_VSORT, "if (pre[x] == \"\") return 1\n      if (pre[y] == \"\") return -1", "if (pre[x] == \"\") return -1\n      if (pre[y] == \"\") return 1"),
             rep(REF_VSORT, "else if (pa[i] ~ /^[0-9]+$/) return -1\n        else if (pb[i] ~ /^[0-9]+$/) return 1", "else if (pa[i] ~ /^[0-9]+$/) return 1\n        else if (pb[i] ~ /^[0-9]+$/) return -1"),
             rep(REF_VSORT, "cmp(ord[j], k) > 0", "cmp(ord[j], k) >= 0"))),
    S("symlink-farm", 5, "Write `farm.sh`: install and remove packages of configuration files as relative symbolic links, checking all conflicts before touching anything. Read README.md carefully.", DOC_FARM, REF_FARM, make_farm, script="farm.sh",
      wrong=(rep(REF_FARM, "      if [ ${#conflicts[@]} -gt 0 ]; then", "      conflicts=()\n      if [ ${#conflicts[@]} -gt 0 ]; then"),
             rep(REF_FARM, 'want[$dest]=$(realpath -m --relative-to="$(dirname -- "$dest")" "$f")', 'want[$dest]=$(realpath -m "$f")'),
             rep(REF_FARM, "find \"$target\" -mindepth 1 -depth -type d -empty -delete", ":"),
             rep(REF_FARM, "if [ -L \"$dest\" ] && [ \"$(readlink -- \"$dest\")\" = \"${want[$dest]}\" ]; then", "if [ -L \"$dest\" ]; then"))),
    S("resumable-batch-runner", 4, "Write `resume.sh LIST CMD...`: run a command for every item of a list, remember finished items in a `.done` file, stop at the first failure and continue where it stopped next time. Read README.md.", DOC_RESUME, REF_RESUME, make_resume, script="resume.sh",
      wrong=(rep(REF_RESUME, '"$@" "$item" < /dev/null', '"$@" "$item"'), rep(REF_RESUME, '[ -n "${seen[$item]+x}" ] && continue\n      seen[$item]=1', ':'), rep(REF_RESUME, "exit 1\n      fi\n      printf", "continue\n      fi\n      printf"),
             rep(REF_RESUME, "grep -qxF -- \"$item\" \"$done_file\"", "grep -q -- \"$item\" \"$done_file\""))),
]


for _s in SPECS:
    for _w in _s.wrong:
        assert _w != _s.ref, _s.slug


@family("shell-ops-scripts", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="expert bash tooling: atomic release switching with pruning and rollback, dotenv layers with references and cycles, SemVer sorting, a symlink farm with conflict pre-checks, a resumable batch runner")
def ops_scripts(rng, n):
    return K.shell_tasks("shell-ops-scripts", SPECS, rng, n)
