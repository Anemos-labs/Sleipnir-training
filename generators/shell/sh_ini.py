"""Shell tasks: INI file tools in bash/awk: get, set, delete, list, lint, diff, merge, expand, typed values (comments, odd spacing, duplicates)."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec

SAMPLE = dd('''
    ; global settings
    editor = vim
    [core]
    name = tidewatch
    # a comment
      path=/srv/app
    name = tidewatch-2

    [Net work]
    host = example.org
    port= 8080
    ; port = 9999
    url = http://x/?a=b&c=d
    [empty]
    [core]
    extra = 1
''')

COMMON_AWK = '''function trim(s) { sub(/^[ \\t]+/, "", s); sub(/[ \\t]+$/, "", s); return s }'''


# ------------------------------------------------------------------------------------------------ 1. get

REF_GET = dd('''
    #!/usr/bin/env bash
    # ini-get.sh FILE SECTION KEY : value of KEY in [SECTION] (last assignment wins), exit 1 when absent
    [ $# -eq 3 ] && [ -r "$1" ] || { echo "usage: ini-get.sh FILE SECTION KEY" >&2; exit 2; }
    awk -v S="$2" -v K="$3" '
      function trim(s) { sub(/^[ \\t]+/, "", s); sub(/[ \\t]+$/, "", s); return s }
      /^[ \\t]*[;#]/ { next }
      /^[ \\t]*\\[/ { s = $0; sub(/^[ \\t]*\\[/, "", s); sub(/\\][ \\t]*$/, "", s); cur = s; next }
      { i = index($0, "="); if (!i) next
        if (cur == S && trim(substr($0, 1, i - 1)) == K) { found = 1; val = trim(substr($0, i + 1)) } }
      END { if (found) { print val; exit 0 } exit 1 }' "$1"
''')


def make_get2(rng):
    ini = "[user]\nname = Ann\nusername = ann42\nnamespace=x\n[admin]\nname = Root\nkey = a=b=c\n[user]\nname = Ann Lee\n"
    ex = scn("example", {"c.ini": F("[a]\nname = x\nusername = y\n")}, Run("c.ini", "a", "name"))
    return ex, [scn("prefix collisions and repeated sections", {"my.ini": F(ini)}, Run("my.ini", "user", "name"), Run("my.ini", "user", "username"), Run("my.ini", "admin", "name"), Run("my.ini", "admin", "key"), Run("my.ini", "user", "user"), Run("my.ini", "admin", "username"), Run("my.ini", "nobody", "name")),
                scn("usage", {"my.ini": F(ini)}, Run("my.ini", "user", stderr="nonempty"), Run("nope.ini", "a", "b"))]


def make_get(rng):
    ex = scn("example", {"c.ini": F("[a]\nx = 1\n")}, Run("c.ini", "a", "x"))
    f = {"my.ini": F(SAMPLE)}
    return ex, [scn("lookups", f, Run("my.ini", "core", "name"), Run("my.ini", "core", "path"), Run("my.ini", "Net work", "port"), Run("my.ini", "Net work", "url"), Run("my.ini", "core", "extra"), Run("my.ini", "", "editor"), Run("my.ini", "empty", "x"),
                                  Run("my.ini", "core", "Name"), Run("my.ini", "net work", "host"), Run("my.ini", "Net work", "port ")),
                scn("usage", f, Run("my.ini", "core", stderr="nonempty"), Run("nope.ini", "a", "b"))]


BUG_GET = dd('''
    #!/bin/bash
    # ini-get.sh FILE SECTION KEY : value of KEY in [SECTION] (last assignment wins), exit 1 when absent
    grep "$3" $1 | cut -d= -f2
''')


# ------------------------------------------------------------------------------------------------ 2. set

REF_SET = dd('''
    #!/usr/bin/env bash
    # ini-set.sh FILE SECTION KEY VALUE : set KEY in [SECTION] (section names are unique), editing FILE in place
    [ $# -eq 4 ] && [ -f "$1" ] || { echo "usage: ini-set.sh FILE SECTION KEY VALUE" >&2; exit 2; }
    tmp=$(mktemp)
    awk -v S="$2" -v K="$3" -v V="$4" '
      function trim(s) { sub(/^[ \\t]+/, "", s); sub(/[ \\t]+$/, "", s); return s }
      { L[NR] = $0 }
      END {
        cur = ""; insec = 0; secl = 0; lastnb = 0; keyl = 0
        for (i = 1; i <= NR; i++) {
          line = L[i]
          if (line ~ /^[ \\t]*[;#]/) { if (insec) lastnb = i; continue }
          if (line ~ /^[ \\t]*\\[/) {
            s = line; sub(/^[ \\t]*\\[/, "", s); sub(/\\][ \\t]*$/, "", s)
            insec = (s == S); if (insec) { secl = i; lastnb = i }
            continue
          }
          if (!insec) continue
          if (line ~ /^[ \\t]*$/) continue
          lastnb = i
          j = index(line, "=")
          if (j && trim(substr(line, 1, j - 1)) == K) keyl = i
        }
        newline = K " = " V
        if (keyl) { for (i = 1; i <= NR; i++) print (i == keyl ? newline : L[i]) }
        else if (secl) { for (i = 1; i <= NR; i++) { print L[i]; if (i == lastnb) print newline } }
        else {
          for (i = 1; i <= NR; i++) print L[i]
          if (NR > 0 && L[NR] !~ /^[ \\t]*$/) print ""
          print "[" S "]"; print newline
        }
      }' "$1" > "$tmp" && cat "$tmp" > "$1"
    rm -f "$tmp"
''')


def make_set(rng):
    base = "; top\n[core]\nname = a\n  path = /x\n\n[net]\nhost=h\n# note\n\n[last]\nz = 1"
    ex = scn("example", {"c.ini": F("[a]\nx = 1\n")}, Run("c.ini", "a", "x", "2"), Run("c.ini", "a", "y", "3"))
    return ex, [scn("replace an existing key", {"c.ini": F(base + "\n")}, Run("c.ini", "core", "path", "/new path")), scn("add to the middle section after its last line", {"c.ini": F(base + "\n")}, Run("c.ini", "net", "port", "80")),
                scn("add to the last section without trailing newline", {"c.ini": F(base)}, Run("c.ini", "last", "y", "2")), scn("new section", {"c.ini": F(base + "\n")}, Run("c.ini", "fresh", "k", "v=1")),
                scn("new section in an empty file and repeated runs", {"e.ini": F("")}, Run("e.ini", "s", "a", "1"), Run("e.ini", "s", "a", "2"), Run("e.ini", "s", "b", "3")),
                scn("usage", {"c.ini": F("[a]\n")}, Run("c.ini", "a", "k", stderr="nonempty"), Run("nope.ini", "a", "k", "v"))]


# ------------------------------------------------------------------------------------------------ 3. delete

REF_DEL = dd('''
    #!/usr/bin/env bash
    # ini-del.sh FILE SECTION KEY : remove every assignment of KEY inside [SECTION] (every block of that name), editing FILE in place
    [ $# -eq 3 ] && [ -f "$1" ] || { echo "usage: ini-del.sh FILE SECTION KEY" >&2; exit 2; }
    tmp=$(mktemp)
    awk -v S="$2" -v K="$3" '
      function trim(s) { sub(/^[ \\t]+/, "", s); sub(/[ \\t]+$/, "", s); return s }
      /^[ \\t]*[;#]/ { print; next }
      /^[ \\t]*\\[/ { s = $0; sub(/^[ \\t]*\\[/, "", s); sub(/\\][ \\t]*$/, "", s); cur = s; print; next }
      { i = index($0, "="); if (i && cur == S && trim(substr($0, 1, i - 1)) == K) next; print }' "$1" > "$tmp" && cat "$tmp" > "$1"
    rm -f "$tmp"
''')


def make_del(rng):
    ex = scn("example", {"c.ini": F("[a]\nx = 1\ny = 2\n")}, Run("c.ini", "a", "x"))
    return ex, [scn("sample file", {"c.ini": F(SAMPLE)}, Run("c.ini", "core", "name"), Run("c.ini", "Net work", "port")), scn("global key and absent key", {"c.ini": F(SAMPLE)}, Run("c.ini", "", "editor"), Run("c.ini", "core", "nothing"), Run("c.ini", "nosuch", "name")),
                scn("usage", {"c.ini": F("[a]\n")}, Run("c.ini", "a", stderr="nonempty"), Run("nope", "a", "b"))]


# ------------------------------------------------------------------------------------------------ 4. sections

REF_SECS = dd('''
    #!/usr/bin/env bash
    # ini-sections.sh FILE : section names in order of first appearance
    [ $# -eq 1 ] && [ -r "$1" ] || { echo "usage: ini-sections.sh FILE" >&2; exit 2; }
    awk '/^[ \\t]*\\[/ { s = $0; sub(/^[ \\t]*\\[/, "", s); sub(/\\][ \\t]*$/, "", s); if (!(s in seen)) { seen[s] = 1; print s } }' "$1"
''')


def make_secs(rng):
    ex = scn("example", {"c.ini": F("[b]\n[a]\n[b]\n")}, Run("c.ini"))
    return ex, [scn("sample", {"my.ini": F(SAMPLE)}, Run("my.ini")), scn("no sections and empty", {"n.ini": F("a=1\n"), "e.ini": F("")}, Run("n.ini"), Run("e.ini")), scn("usage", {}, Run(stderr="nonempty"), Run("nope"))]


# ------------------------------------------------------------------------------------------------ 5. environment export

REF_ENV = dd('''
    #!/usr/bin/env bash
    # ini-env.sh FILE SECTION : "export SECTION_KEY=value" lines for the keys of [SECTION] (last assignment wins, first-appearance order)
    [ $# -eq 2 ] && [ -r "$1" ] || { echo "usage: ini-env.sh FILE SECTION" >&2; exit 2; }
    awk -v S="$2" '
      function trim(s) { sub(/^[ \\t]+/, "", s); sub(/[ \\t]+$/, "", s); return s }
      /^[ \\t]*[;#]/ { next }
      /^[ \\t]*\\[/ { s = $0; sub(/^[ \\t]*\\[/, "", s); sub(/\\][ \\t]*$/, "", s); cur = s; next }
      { i = index($0, "="); if (!i || cur != S) next
        k = trim(substr($0, 1, i - 1)); if (!(k in val)) order[++n] = k
        val[k] = trim(substr($0, i + 1)) }
      END { for (j = 1; j <= n; j++) printf "%s\\t%s\\n", order[j], val[order[j]] }' "$1" |
      while IFS=$'\\t' read -r k v; do
        name=$(printf '%s_%s' "$2" "$k" | tr 'a-z' 'A-Z' | sed 's/[^A-Z0-9]/_/g')
        printf 'export %s=%q\\n' "$name" "$v"
      done
''')


def make_env(rng):
    ex = scn("example", {"c.ini": F("[db]\nhost = h\nport = 5432\n")}, Run("c.ini", "db"))
    ini = "[Net work]\nhost = a b\nport=80\nurl = http://x/?a=b&c='d'\nmy-key.x = $HOME `id`\nport = 8080\n\n[core]\nname = x\n"
    return ex, [scn("section to env", {"my.ini": F(ini)}, Run("my.ini", "Net work"), Run("my.ini", "core"), Run("my.ini", "none")), scn("usage", {}, Run("x", stderr="nonempty"), Run("nope", "a"))]


# ------------------------------------------------------------------------------------------------ 6. merge

REF_MERGE = dd('''
    #!/usr/bin/env bash
    # ini-merge.sh BASE OVERRIDE : merged INI on stdout
    [ $# -eq 2 ] && [ -r "$1" ] && [ -r "$2" ] || { echo "usage: ini-merge.sh BASE OVERRIDE" >&2; exit 2; }
    awk '
      function trim(s) { sub(/^[ \\t]+/, "", s); sub(/[ \\t]+$/, "", s); return s }
      function sect(name) { if (!(name in sseen)) { sseen[name] = 1; snames[++ns] = name } }
      BEGIN { cur = ""; sect("") }
      FNR == 1 { cur = ""; sect("") }
      /^[ \\t]*[;#]/ { next }
      /^[ \\t]*\\[/ { s = $0; sub(/^[ \\t]*\\[/, "", s); sub(/\\][ \\t]*$/, "", s); cur = s; sect(cur); next }
      { i = index($0, "="); if (!i) next
        k = trim(substr($0, 1, i - 1)); id = cur SUBSEP k
        if (!(id in val)) { nk[cur]++; keys[cur, nk[cur]] = k }
        val[id] = trim(substr($0, i + 1)) }
      END {
        first = 1
        for (a = 1; a <= ns; a++) {
          s = snames[a]
          if (s == "" && nk[s] == 0) continue
          if (!first) print ""
          first = 0
          if (s != "") print "[" s "]"
          for (b = 1; b <= nk[s]; b++) print keys[s, b] "=" val[s SUBSEP keys[s, b]]
        }
      }' "$1" "$2"
''')


def make_merge(rng):
    ex = scn("example", {"a.ini": F("[x]\na=1\nb=2\n"), "b.ini": F("[x]\nb=3\n[y]\nc=4\n")}, Run("a.ini", "b.ini"))
    base = "; base\nglobal = 1\n[core]\nname = old\npath = /a\n[net]\nhost = h\n"
    over = "global=2\nnew-global = x\n[net]\nport = 80\nhost = other  \n[extra]\nk = v\n[core]\nname = new\n"
    return ex, [scn("override wins", {"base.ini": F(base), "over.ini": F(over)}, Run("base.ini", "over.ini"), Run("over.ini", "base.ini")), scn("empty override and empty base", {"b": F(base), "e": F("")}, Run("b", "e"), Run("e", "b"), Run("e", "e")),
                scn("usage", {"a": F("")}, Run("a", stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 7. lint

REF_LINT = dd('''
    #!/usr/bin/env bash
    # ini-lint.sh FILE : report problems as "LINE: message"; exit 1 if there are any
    [ $# -eq 1 ] && [ -r "$1" ] || { echo "usage: ini-lint.sh FILE" >&2; exit 2; }
    awk '
      function trim(s) { sub(/^[ \\t]+/, "", s); sub(/[ \\t]+$/, "", s); return s }
      /^[ \\t]*$/ || /^[ \\t]*[;#]/ { next }
      /^[ \\t]*\\[/ {
        s = trim($0)
        if (s !~ /^\\[[^]]+\\]$/) { print NR ": bad section header"; bad = 1; next }
        name = substr(s, 2, length(s) - 2); cur = name; hasSec = 1
        if (name in secs) { print NR ": duplicate section [" name "]"; bad = 1 } else secs[name] = 1
        next
      }
      {
        i = index($0, "=")
        if (!i) { print NR ": malformed line"; bad = 1; next }
        k = trim(substr($0, 1, i - 1))
        if (!hasSec) { print NR ": key outside any section"; bad = 1; next }
        if ((cur SUBSEP k) in kk) { print NR ": duplicate key \\047" k "\\047 in [" cur "]"; bad = 1 } else kk[cur SUBSEP k] = 1
      }
      END { exit bad ? 1 : 0 }' "$1"
''')


def make_lint(rng):
    ex = scn("example", {"c.ini": F("a = 1\n[s]\nx = 1\nx = 2\n")}, Run("c.ini"))
    bad = "a = 1\n; comment\n[core]\nname = x\nname = y\njust words\n[]\n[core]\n  [net\nhost = h\n[net]\nhost = 1\n   port = 2\nport=3\n= empty key\n"
    return ex, [scn("all problem kinds", {"bad.ini": F(bad)}, Run("bad.ini")), scn("clean file", {"good.ini": F("[a]\nx = 1\n\n[b]\nx = 2\n# c\n")}, Run("good.ini")), scn("empty and usage", {"e": F("")}, Run("e"), Run(stderr="nonempty"), Run("nope"))]


# ------------------------------------------------------------------------------------------------ 8. semantic diff

REF_DIFF = dd('''
    #!/usr/bin/env bash
    # ini-diff.sh A B : semantic difference of two INI files, sorted by "section.key"
    [ $# -eq 2 ] && [ -r "$1" ] && [ -r "$2" ] || { echo "usage: ini-diff.sh A B" >&2; exit 2; }
    parse() {
      awk '
        function trim(s) { sub(/^[ \\t]+/, "", s); sub(/[ \\t]+$/, "", s); return s }
        /^[ \\t]*[;#]/ { next }
        /^[ \\t]*\\[/ { s = $0; sub(/^[ \\t]*\\[/, "", s); sub(/\\][ \\t]*$/, "", s); cur = s; next }
        { i = index($0, "="); if (!i) next
          k = trim(substr($0, 1, i - 1)); name = (cur == "" ? k : cur "." k); val[name] = trim(substr($0, i + 1)) }
        END { for (n in val) print n "\\t" val[n] }' "$1"
    }
    a=$(mktemp)
    b=$(mktemp)
    parse "$1" > "$a"
    parse "$2" > "$b"
    awk -F'\\t' 'NR == FNR { x[$1] = $2; seen[$1] = 1; next } { y[$1] = $2; seen[$1] = 1 }
      END { for (n in seen) {
              if ((n in x) && !(n in y)) print n "\\t- " n "=" x[n]
              else if ((n in y) && !(n in x)) print n "\\t+ " n "=" y[n]
              else if (x[n] != y[n]) print n "\\t~ " n ": " x[n] " -> " y[n] } }' "$a" "$b" | LC_ALL=C sort -t"$(printf '\\t')" -k1,1 | cut -f2-
    rm -f "$a" "$b"
''')


def make_diff(rng):
    ex = scn("example", {"a.ini": F("[s]\nx=1\ny=2\n"), "b.ini": F("[s]\nx=1\ny=3\nz=4\n")}, Run("a.ini", "b.ini"))
    a = "top = 1\n[core]\nname = a\npath = /x\nold = gone\n[net]\nhost = h\n"
    b = "top = 2\n[core]\nname = a\npath = /y\nnew = here\n[net]\nhost = h\n[extra]\nk = v\n"
    return ex, [scn("changes", {"a.ini": F(a), "b.ini": F(b)}, Run("a.ini", "b.ini"), Run("b.ini", "a.ini")), scn("identical", {"a.ini": F(a), "same.ini": F("; reordered\n" + a)}, Run("a.ini", "same.ini")),
                scn("usage", {"a": F("")}, Run("a", stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 9. reference expansion

REF_EXPAND = dd('''
    #!/usr/bin/env bash
    # ini-expand.sh FILE : normalised INI with ${section.key} references in values replaced (single pass)
    [ $# -eq 1 ] && [ -r "$1" ] || { echo "usage: ini-expand.sh FILE" >&2; exit 2; }
    awk '
      function trim(s) { sub(/^[ \\t]+/, "", s); sub(/[ \\t]+$/, "", s); return s }
      function sect(name) { if (!(name in sseen)) { sseen[name] = 1; snames[++ns] = name } }
      function expand(v,   out, a, b, ref) {
        out = ""
        while (match(v, /\\$\\{[^}]*\\}/)) {
          ref = substr(v, RSTART + 2, RLENGTH - 3)
          out = out substr(v, 1, RSTART - 1) ((ref in val) ? val[ref] : substr(v, RSTART, RLENGTH))
          v = substr(v, RSTART + RLENGTH)
        }
        return out v
      }
      BEGIN { cur = ""; sect("") }
      /^[ \\t]*[;#]/ { next }
      /^[ \\t]*\\[/ { s = $0; sub(/^[ \\t]*\\[/, "", s); sub(/\\][ \\t]*$/, "", s); cur = s; sect(cur); next }
      { i = index($0, "="); if (!i) next
        k = trim(substr($0, 1, i - 1)); name = (cur == "" ? k : cur "." k)
        if (!(name in val)) { nk[cur]++; keys[cur, nk[cur]] = k }
        val[name] = trim(substr($0, i + 1)) }
      END {
        first = 1
        for (a = 1; a <= ns; a++) {
          s = snames[a]
          if (s == "" && nk[s] == 0) continue
          if (!first) print ""
          first = 0
          if (s != "") print "[" s "]"
          for (b = 1; b <= nk[s]; b++) { k = keys[s, b]; print k "=" expand(val[(s == "" ? k : s "." k)]) }
        }
      }' "$1"
''')


def make_expand(rng):
    ex = scn("example", {"c.ini": F("[paths]\nroot = /srv\nlogs = ${paths.root}/log\n")}, Run("c.ini"))
    ini = "base = /opt\n[app]\nname = tide\nhome = ${base}/${app.name}\nlog = ${app.home}/log\nmissing = ${nope.x}/y ${also}\nplain = no refs\nbroken = ${unclosed\ntwice = ${app.name}-${app.name}\n[other]\nlink = ${app.name}\n"
    return ex, [scn("references", {"my.ini": F(ini)}, Run("my.ini")), scn("empty and usage", {"e": F("")}, Run("e"), Run(stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ 10. typed values

REF_TYPED = dd('''
    #!/usr/bin/env bash
    # ini-typed.sh FILE SECTION KEY TYPE : value of KEY normalised as bool, int or size
    [ $# -eq 4 ] && [ -r "$1" ] || { echo "usage: ini-typed.sh FILE SECTION KEY int|bool|size" >&2; exit 2; }
    case $4 in int|bool|size) ;; *) echo "usage: ini-typed.sh FILE SECTION KEY int|bool|size" >&2; exit 2 ;; esac
    v=$(awk -v S="$2" -v K="$3" '
      function trim(s) { sub(/^[ \\t]+/, "", s); sub(/[ \\t]+$/, "", s); return s }
      /^[ \\t]*[;#]/ { next }
      /^[ \\t]*\\[/ { s = $0; sub(/^[ \\t]*\\[/, "", s); sub(/\\][ \\t]*$/, "", s); cur = s; next }
      { i = index($0, "="); if (i && cur == S && trim(substr($0, 1, i - 1)) == K) { found = 1; val = trim(substr($0, i + 1)) } }
      END { if (!found) exit 1; print val }' "$1") || exit 1
    case $4 in
      int)
        [[ $v =~ ^-?[0-9]+$ ]] || { echo "not an integer: $v" >&2; exit 3; }
        n=${v#-}; n=$((10#$n)); [ "${v:0:1}" = - ] && [ "$n" -ne 0 ] && n=-$n
        echo "$n" ;;
      bool)
        case $(printf '%s' "$v" | tr 'A-Z' 'a-z') in
          yes|true|on|1) echo true ;;
          no|false|off|0) echo false ;;
          *) echo "not a boolean: $v" >&2; exit 3 ;;
        esac ;;
      size)
        [[ $v =~ ^([0-9]+)([kKmMgG]?)$ ]] || { echo "not a size: $v" >&2; exit 3; }
        n=$((10#${BASH_REMATCH[1]}))
        case ${BASH_REMATCH[2]} in k|K) n=$((n * 1024)) ;; m|M) n=$((n * 1048576)) ;; g|G) n=$((n * 1073741824)) ;; esac
        echo "$n" ;;
    esac
''')


def make_typed(rng):
    ex = scn("example", {"c.ini": F("[a]\nn = 007\nflag = Yes\nbuf = 4k\n")}, Run("c.ini", "a", "n", "int"), Run("c.ini", "a", "flag", "bool"), Run("c.ini", "a", "buf", "size"))
    ini = "[v]\ni1 = 42\ni2 = -007\ni3 = -0\ni4 = 4.5\ni5 = 12ab\nb1 = TRUE\nb2 = off\nb3 = maybe\nb4 = 1\nb5 =\ns1 = 10\ns2 = 3K\ns3 = 2m\ns4 = 1G\ns5 = 5 k\ns6 = 0\ns7 = k\n"
    runs = [Run("c.ini", "v", k, t) for k, t in [("i1", "int"), ("i2", "int"), ("i3", "int"), ("i4", "int"), ("i5", "int"), ("b1", "bool"), ("b2", "bool"), ("b3", "bool"), ("b4", "bool"), ("b5", "bool"), ("s1", "size"), ("s2", "size"), ("s3", "size"), ("s4", "size"),
                                                  ("s5", "size"), ("s6", "size"), ("s7", "size"), ("missing", "int")]]
    return ex, [scn("conversions", {"c.ini": F(ini)}, *runs), scn("usage", {"c.ini": F(ini)}, Run("c.ini", "v", "i1", "float", stderr="nonempty"), Run("c.ini", "v", "i1"), Run("nope", "v", "i1", "int"))]


SPECS = [
    S("ini-get-value", 2,
      "Write `ini-get.sh FILE SECTION KEY` that prints a value from an INI file, following the README's parsing rules.",
      "`bash ini-get.sh FILE SECTION KEY` prints the value of `KEY` in section `[SECTION]` of an INI file. Rules: a line `[name]` starts a section (the name is the text between the first `[` and the closing `]`, spaces allowed, compared exactly; keys before the first header belong to the section with the empty name `\"\"`); "
      "lines whose first non-blank character is `;` or `#` are comments; other lines containing `=` are assignments `key = value` split at the **first** `=`, with blanks around key and value trimmed (the value may contain `=`, `;` and `#`); lines without `=` are ignored. "
      "When a key is assigned several times in the same section, in one or several blocks of it, the last assignment wins. Keys and sections are case-sensitive. Print the value and exit 0; if the key is absent print nothing and exit 1. Wrong arguments or unreadable file: usage message on stderr, exit status 2.",
      REF_GET, make_get, script="ini-get.sh", title="Read a value from an INI file", wrong=(BUG_GET,)),
    S("ini-set-value", 4,
      "Write `ini-set.sh FILE SECTION KEY VALUE`: set a key in an INI file in place without disturbing the rest of the file.",
      "`bash ini-set.sh FILE SECTION KEY VALUE` edits `FILE` in place (section names are unique in the test files; INI syntax as in the README of the other INI tools: `[name]` headers, `;`/`#` comment lines, `key = value` assignments split at the first `=` with blanks trimmed). "
      "If `KEY` is assigned in `[SECTION]`, the **last** such assignment line is replaced by `KEY = VALUE` (single spaces around `=`); if not, the line `KEY = VALUE` is inserted right after the last non-blank line of the section (comments count as lines of the section); "
      "if the section does not exist, it is appended at the end of the file as an empty line (unless the file is empty or already ends with a blank line), `[SECTION]` and `KEY = VALUE`. All other lines stay byte-for-byte; the file ends with a newline afterwards. "
      "Wrong arguments or a missing file: usage message on stderr, exit 2.",
      REF_SET, make_set, script="ini-set.sh", title="Set a value in an INI file", wrong=("#!/bin/bash\necho \"$3 = $4\" >> \"$1\"\n",)),
    S("ini-delete-key", 3,
      "Write `ini-del.sh FILE SECTION KEY`: remove every assignment of a key from a section of an INI file, in place.",
      "`bash ini-del.sh FILE SECTION KEY` deletes, in place, every assignment line of `KEY` that lies inside a block of section `[SECTION]` (the section may occur several times; use `\"\"` for keys before the first header). Everything else, comments and blank lines included, stays untouched; the section header stays even if it becomes empty. "
      "Assignments are lines with `=`, key = text before the first `=` with blanks trimmed. Wrong arguments or a missing file: usage message on stderr, exit 2.",
      REF_DEL, make_del, script="ini-del.sh", title="Delete a key from an INI file", wrong=("#!/bin/bash\ngrep -v \"^$3\" \"$1\" > \"$1.new\" && mv \"$1.new\" \"$1\"\n",)),
    S("ini-section-names", 1,
      "Write `ini-sections.sh FILE` printing the section names of an INI file in order, each once.",
      "`bash ini-sections.sh FILE` prints the names of the sections of an INI file (the text between `[` and the closing `]` of a header line, which may be indented), one per line, in order of first appearance, each name once. Comment lines (`;`, `#`) are not headers. "
      "A file without headers prints nothing. Wrong arguments or unreadable file: usage message on stderr, exit 2.",
      REF_SECS, make_secs, script="ini-sections.sh", title="List INI sections", wrong=("#!/bin/bash\ngrep '^\\[' \"$1\"\n",)),
    S("ini-section-to-env", 3,
      "Write `ini-env.sh FILE SECTION`: print shell `export` lines for the keys of one INI section.",
      "`bash ini-env.sh FILE SECTION` prints `export NAME=VALUE` for each key of `[SECTION]` (INI syntax: `[name]` headers, `;`/`#` comments, assignments split at the first `=` with blanks trimmed; the last assignment of a key wins, keys in order of first appearance). "
      "`NAME` is the section name, an underscore and the key, all upper-cased (ASCII) with every character that is not `A-Z`/`0-9` replaced by `_`; `VALUE` is quoted exactly as `printf %q` would. An unknown section prints nothing. Wrong arguments or unreadable file: usage message on stderr, exit 2.",
      REF_ENV, make_env, script="ini-env.sh", title="INI section to environment", wrong=("#!/bin/bash\ngrep = \"$1\" | sed 's/^/export /'\n",)),
    S("ini-merge-two-files", 4,
      "Write `ini-merge.sh BASE OVERRIDE`: merge two INI files into one normalised INI on stdout, the override winning.",
      "`bash ini-merge.sh BASE OVERRIDE` prints the merged configuration: sections appear in order of first appearance (all of `BASE` first, then new ones from `OVERRIDE`); within a section keys appear in order of first appearance and a key set in both files takes the value from `OVERRIDE`. "
      "Keys before the first header form an unnamed section printed first without a header (omitted when empty). Output format: `[name]` header, then `key=value` lines (no spaces around `=`, values trimmed), one empty line between sections, none at the end. Comments are dropped. Wrong arguments or unreadable file: usage message on stderr, exit 2.",
      REF_MERGE, make_merge, script="ini-merge.sh", title="Merge INI files", wrong=("#!/bin/bash\ncat \"$1\" \"$2\"\n",)),
    S("ini-lint", 3,
      "Write `ini-lint.sh FILE`: report problems in an INI file as `LINE: message`, exiting 1 when there are any.",
      "`bash ini-lint.sh FILE` checks an INI file line by line and prints `LINE: MESSAGE` (1-based line numbers, in file order) for each problem, at most one per line, using the first matching rule: blank lines and comment lines (`;`, `#` after optional blanks) are fine; "
      "a line starting (after blanks) with `[` must be `[name]` with a non-empty name and nothing after the `]`, otherwise `bad section header`; a repeated section name is `duplicate section [name]` (the second and later headers); a line without `=` is `malformed line`; "
      "an assignment before any header is `key outside any section`; an assignment whose key (text before the first `=`, trimmed) already occurred in the same section is `duplicate key 'KEY' in [SECTION]`. Exit status 1 if anything was printed, else 0. Wrong arguments or unreadable file: usage message on stderr and exit status 2.",
      REF_LINT, make_lint, script="ini-lint.sh", title="Lint an INI file", wrong=("#!/bin/bash\ngrep -n -v '=' \"$1\"\n",)),
    S("ini-semantic-diff", 4,
      "Write `ini-diff.sh A B`: compare two INI files by meaning (ignoring comments, order and spacing) and list the differences.",
      "`bash ini-diff.sh A B` parses both files (headers `[name]`, `;`/`#` comments, assignments split at the first `=` with blanks trimmed, last assignment wins; keys before the first header have no section). Each setting is named `section.key` (just `key` outside sections). "
      "Print, sorted byte-wise by that name: `- name=value` for settings only in `A`, `+ name=value` for settings only in `B`, `~ name: old -> new` for settings in both with different values. Identical settings print nothing. Wrong arguments or unreadable files: usage message on stderr, exit 2.",
      REF_DIFF, make_diff, script="ini-diff.sh", title="Semantic diff of INI files", wrong=("#!/bin/bash\ndiff \"$1\" \"$2\"\n",)),
    S("ini-expand-references", 4,
      "Write `ini-expand.sh FILE`: print the INI normalised, with `${section.key}` references inside values replaced by the referenced values.",
      "`bash ini-expand.sh FILE` prints the file in normalised form: sections in order of first appearance, keys in order of first appearance, `[name]` headers, `key=value` lines (trimmed, last assignment wins, comments dropped), one empty line between sections; keys before the first header come first without header (omitted if there are none). "
      "In values, every `${NAME}` where `NAME` is `section.key` (or just `key` for an unnamed-section key) is replaced by the **raw** (unexpanded) value of that setting from the file; references to unknown settings and unterminated `${` stay as they are. Replacement is a single pass over the value (text inserted by a reference is not scanned again). Wrong arguments: usage message on stderr, exit 2.",
      REF_EXPAND, make_expand, script="ini-expand.sh", title="Expand references in INI values", wrong=("#!/bin/bash\ncat \"$1\"\n",)),
    S("ini-typed-values", 4,
      "Write `ini-typed.sh FILE SECTION KEY TYPE` that reads an INI value and normalises it as an integer, a boolean or a byte size.",
      "`bash ini-typed.sh FILE SECTION KEY TYPE` finds the value as `ini-get` would (last assignment wins; `[name]` sections; `;`/`#` comments; split at the first `=`, trimmed) and prints it normalised according to `TYPE`: "
      "`int` (an optional `-` and digits only; leading zeros are decimal and dropped, `-0` is `0`), `bool` (`yes true on 1` print `true`, `no false off 0` print `false`, any case) or `size` (digits with an optional suffix `k`, `m` or `g` in either case meaning 1024, 1024^2, 1024^3; prints the number of bytes). "
      "Absent key: nothing printed, exit 1. A value that does not fit the type: message on stderr, exit 3. Wrong arguments or an unknown TYPE: usage message on stderr, exit 2.",
      REF_TYPED, make_typed, script="ini-typed.sh", title="Typed INI values", wrong=("#!/bin/bash\nawk -F= -v k=\"$3\" '$1 ~ k { print $2 }' \"$1\"\n",)),
    S("fix-ini-lookup", 2,
      "`ini-get.sh` is a one-line `grep | cut`. It returns the wrong thing whenever a key name is a prefix of another, a value contains `=`, or the same key exists in two sections. Rewrite it properly.",
      "`bash ini-get.sh FILE SECTION KEY` prints the value of `KEY` in section `[SECTION]` of an INI file: `[name]` headers; lines starting (after blanks) with `;` or `#` are comments; assignments `key = value` are split at the first `=` and trimmed on both sides; "
      "the last assignment of the key in that section wins; keys and sections are case-sensitive; keys before the first header belong to the section named `\"\"`. Print the value (exit 0) or print nothing and exit 1 if absent. Wrong arguments or unreadable file: usage message on stderr, exit 2.",
      REF_GET, make_get2, script="ini-get.sh", buggy=BUG_GET, title="Fix the INI lookup", wrong=(BUG_GET,)),
]


@family("shell-ini-tools", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="INI file tools in bash/awk: get, set, delete, sections, env export, merge, lint, semantic diff, expansion, typed values")
def ini_tools(rng, n):
    return K.shell_tasks("ini-tools", SPECS, rng, n)
