"""Shell tasks: CSV with quoted fields handled in bash/awk: column picking, sums, sorting, filtering, joins, conversion, validation, grouping, dedupe, JSON."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec

PARSE = '''
function parse(line,   n, i, c, q, cur, len) {
  n = 0; cur = ""; q = 0; len = length(line)
  for (i = 1; i <= len; i++) {
    c = substr(line, i, 1)
    if (q) {
      if (c == "\\"") { if (substr(line, i + 1, 1) == "\\"") { cur = cur "\\""; i++ } else q = 0 }
      else cur = cur c
    } else if (c == "\\"") q = 1
    else if (c == ",") { f[++n] = cur; cur = "" }
    else cur = cur c
  }
  f[++n] = cur
  return n
}
function quote(s) { if (s ~ /[",]/ || s ~ /^ / || s ~ / $/) { gsub(/"/, "\\"\\"", s); return "\\"" s "\\"" } return s }
function cents(s,   neg, p, w, fr) {
  neg = 0
  if (substr(s, 1, 1) == "-") { neg = 1; s = substr(s, 2) } else if (substr(s, 1, 1) == "+") s = substr(s, 2)
  p = index(s, ".")
  if (p) { w = substr(s, 1, p - 1); fr = substr(s, p + 1) } else { w = s; fr = "" }
  fr = substr(fr "00", 1, 2)
  return neg ? -((w + 0) * 100 + (fr + 0)) : (w + 0) * 100 + (fr + 0)
}
function money(c,   sign) { sign = ""; if (c < 0) { sign = "-"; c = -c } return sprintf("%s%d.%02d", sign, int(c / 100), c % 100) }
'''
P = "".join(("    " + l) if l.strip() else l for l in PARSE.splitlines(True))
NUM = r'^[-+]?[0-9]+(\\.[0-9]{1,2})?$'


def csv(rows):
    return "".join(r + "\n" for r in rows)


SAMPLE = csv(["id,name,city,amount,note", '1,"Doe, Jane",Oslo,10.50,"says ""hi"""', "2,Bob,Rome,3,", '3,"  padded  ",Oslo,-2.25,plain', "4,Cy,,0.5,x", '5,"Ünï, ça",Rome,7,"a,b,c"', "6,Dee,Oslo,100.00,end"])


# ------------------------------------------------------------------------------------------------ 1. select columns

REF_COLS = dd('''
    #!/usr/bin/env bash
    # csv-cols.sh FILE COL... : keep the named (or #N, 1-based) columns, in the order given
    [ $# -ge 2 ] && [ -r "$1" ] || { echo "usage: csv-cols.sh FILE COL..." >&2; exit 2; }
    file=$1
    shift
    spec=$(printf '%s\\n' "$@")
    awk -v spec="$spec" '
''' + P + '''
    BEGIN { nc = split(spec, want, "\\n") }
    /^[ \\t]*$/ { next }
    {
      n = parse($0)
      if (++rows == 1) {
        for (i = 1; i <= n; i++) if (!(f[i] in idx)) idx[f[i]] = i
        for (j = 1; j <= nc; j++) {
          if (want[j] ~ /^#[0-9]+$/) col[j] = substr(want[j], 2) + 0
          else if (want[j] in idx) col[j] = idx[want[j]]
          else { print "unknown column: " want[j] > "/dev/stderr"; bad = 1; exit 2 }
        }
      }
      out = ""
      for (j = 1; j <= nc; j++) out = out (j > 1 ? "," : "") quote(col[j] <= n ? f[col[j]] : "")
      print out
    }
    END { if (bad) exit 2 }' "$file"
''')


def make_cols(rng):
    ex = scn("example", {"d.csv": F("a,b,c\n1,2,3\n")}, Run("d.csv", "c", "a"))
    f = {"my data.csv": F(SAMPLE + "\n  \n")}
    return ex, [scn("by name and index", f, Run("my data.csv", "name", "amount"), Run("my data.csv", "#5", "id", "#1"), Run("my data.csv", "note", "note", "city")),
                scn("errors", f, Run("my data.csv", "nope", stderr="nonempty"), Run("my data.csv"), Run("missing.csv", "id"))]


# ------------------------------------------------------------------------------------------------ 2. sum a column

REF_SUM = dd('''
    #!/usr/bin/env bash
    # csv-sum.sh FILE COL : exact sum (two decimals) of a numeric column; empty cells are skipped
    [ $# -eq 2 ] && [ -r "$1" ] || { echo "usage: csv-sum.sh FILE COL" >&2; exit 2; }
    awk -v want="$2" '
''' + P + '''
    /^[ \\t]*$/ { next }
    {
      n = parse($0)
      if (++rows == 1) {
        for (i = 1; i <= n; i++) if (f[i] == want) { c = i; break }
        if (!c) { print "unknown column: " want > "/dev/stderr"; bad = 2; exit 2 }
        next
      }
      v = (c <= n) ? f[c] : ""
      if (v == "") next
      if (v !~ /''' + NUM + '''/) { print "line " NR ": not a number: " v > "/dev/stderr"; bad = 1; exit 1 }
      total += cents(v)
    }
    END { if (bad) exit bad; print money(total) }' "$1"
''')


def make_sum(rng):
    ex = scn("example", {"d.csv": F("item,price\na,1.5\nb,2\n")}, Run("d.csv", "price"))
    f = {"s.csv": F(SAMPLE), "t.csv": F("k,v\n,\nx,0.10\ny,0.20\nz,-0.30\n"), "bad.csv": F("a,b\n1,2\n2,abc\n3,4\n"), "big.csv": F("v\n123456.78\n0.01\n+5\n-0.5\n")}
    return ex, [scn("sums", f, Run("s.csv", "amount"), Run("t.csv", "v"), Run("big.csv", "v"), Run("s.csv", "id")), scn("errors", f, Run("bad.csv", "b", stderr="nonempty"), Run("s.csv", "nope"), Run("s.csv"), Run("none.csv", "x"))]


# ------------------------------------------------------------------------------------------------ 3. sort by a column

REF_SORT = dd('''
    #!/usr/bin/env bash
    # csv-sort.sh FILE COL [-n] [-r] : header first, then the rows ordered (stably) by column COL
    file=${1:-}
    col=${2:-}
    [ -r "$file" ] && [ -n "$col" ] || { echo "usage: csv-sort.sh FILE COL [-n] [-r]" >&2; exit 2; }
    shift 2
    num=0 rev=0
    for o in "$@"; do
      case $o in -n) num=1 ;; -r) rev=1 ;; *) echo "usage: csv-sort.sh FILE COL [-n] [-r]" >&2; exit 2 ;; esac
    done
    keys='1,1'
    [ "$num" = 1 ] && keys=${keys}g
    [ "$rev" = 1 ] && keys=${keys}r
    tab=$(printf '\\t')
    tmp=$(mktemp)
    trap 'rm -f "$tmp"' EXIT
    awk -v want="$col" -v num="$num" '
''' + P + '''
    /^[ \\t]*$/ { next }
    {
      n = parse($0)
      if (++rows == 1) {
        for (i = 1; i <= n; i++) if (f[i] == want) { c = i; break }
        if (!c) { print "unknown column: " want > "/dev/stderr"; exit 2 }
        print > "/dev/stderr"
        next
      }
      v = (c <= n) ? f[c] : ""
      if (num && v !~ /^[-+]?[0-9]+(\\.[0-9]+)?$/) v = 0
      printf "%s\\t%d\\t%s\\n", v, rows, $0
    }' "$file" 2> "$tmp.head" > "$tmp" || { cat "$tmp.head" >&2; rm -f "$tmp.head"; exit 2; }
    cat "$tmp.head"
    rm -f "$tmp.head"
    LC_ALL=C sort -t"$tab" -k"$keys" -k2,2n "$tmp" | cut -f3-
''')


def make_sort(rng):
    ex = scn("example", {"d.csv": F("n,v\nb,2\na,10\nc,1\n")}, Run("d.csv", "v", "-n"))
    f = {"p.csv": F(csv(["id,name,score", '1,"Smith, Ann",9.5', '2,bob,10', '3,Cy,-1', '4,"x",9.5', '5,dee,', '6,Eve,abc', '7,Fay,10.0', '8,"Zed, Z",2']) + "\n")}
    return ex, [scn("sorting", f, Run("p.csv", "score", "-n"), Run("p.csv", "score", "-n", "-r"), Run("p.csv", "name"), Run("p.csv", "name", "-r"), Run("p.csv", "id", "-r", "-n")),
                scn("errors", f, Run("p.csv", "nope", stderr="nonempty"), Run("p.csv", "id", "-x"), Run("missing.csv", "id"))]


# ------------------------------------------------------------------------------------------------ 4. filter rows

REF_FILTER = dd('''
    #!/usr/bin/env bash
    # csv-filter.sh FILE COL OP VALUE : header plus the rows where COL OP VALUE holds (eq ne contains: text; lt gt le ge: numbers)
    [ $# -eq 4 ] && [ -r "$1" ] || { echo "usage: csv-filter.sh FILE COL eq|ne|lt|gt|le|ge|contains VALUE" >&2; exit 2; }
    case $3 in eq|ne|lt|gt|le|ge|contains) ;; *) echo "bad operator: $3" >&2; exit 2 ;; esac
    awk -v want="$2" -v op="$3" -v val="$4" '
''' + P + '''
    function isnum(s) { return s ~ /^[-+]?[0-9]+(\\.[0-9]+)?$/ }
    /^[ \\t]*$/ { next }
    {
      n = parse($0)
      if (++rows == 1) {
        for (i = 1; i <= n; i++) if (f[i] == want) { c = i; break }
        if (!c) { print "unknown column: " want > "/dev/stderr"; exit 2 }
        if (op ~ /^(lt|gt|le|ge)$/ && !isnum(val)) { print "not a number: " val > "/dev/stderr"; exit 2 }
        print; next
      }
      v = (c <= n) ? f[c] : ""
      ok = 0
      if (op == "eq") ok = (v == val)
      else if (op == "ne") ok = (v != val)
      else if (op == "contains") ok = (index(v, val) > 0)
      else if (isnum(v)) {
        if (op == "lt") ok = (v + 0 < val + 0)
        else if (op == "gt") ok = (v + 0 > val + 0)
        else if (op == "le") ok = (v + 0 <= val + 0)
        else ok = (v + 0 >= val + 0)
      }
      if (ok) print
    }' "$1"
''')


def make_filter(rng):
    ex = scn("example", {"d.csv": F("n,v\na,1\nb,5\n")}, Run("d.csv", "v", "gt", "2"))
    f = {"s.csv": F(SAMPLE)}
    return ex, [scn("operators", f, Run("s.csv", "city", "eq", "Oslo"), Run("s.csv", "city", "ne", "Oslo"), Run("s.csv", "amount", "ge", "7"), Run("s.csv", "amount", "lt", "0.5"), Run("s.csv", "name", "contains", ","), Run("s.csv", "note", "eq", "a,b,c"),
                                  Run("s.csv", "amount", "gt", "-3"), Run("s.csv", "name", "eq", "  padded  "), Run("s.csv", "note", "contains", "")),
                scn("errors", f, Run("s.csv", "nope", "eq", "x", stderr="nonempty"), Run("s.csv", "id", "approx", "1"), Run("s.csv", "id", "gt", "abc"), Run("s.csv", "id", "eq"))]


# ------------------------------------------------------------------------------------------------ 5. join

REF_JOIN = dd('''
    #!/usr/bin/env bash
    # csv-join.sh A B KEY : inner join on the column named KEY (unique in B)
    [ $# -eq 3 ] && [ -r "$1" ] && [ -r "$2" ] || { echo "usage: csv-join.sh A B KEY" >&2; exit 2; }
    awk -v key="$3" '
''' + P + '''
    /^[ \\t]*$/ { next }
    FNR == 1 { fileno++; hdr = 1 } FNR > 1 { hdr = 0 }
    fileno == 1 {
      n = parse($0)
      if (hdr) {
        for (i = 1; i <= n; i++) { ah[i] = f[i]; if (f[i] == key) ak = i; used[f[i]] = 1 }
        an = n
        if (!ak) { print "unknown column: " key " in first file" > "/dev/stderr"; bad = 2; exit 2 }
      } else { rows++; for (i = 1; i <= an; i++) ar[rows, i] = (i <= n) ? f[i] : "" }
      next
    }
    {
      n = parse($0)
      if (hdr) {
        for (i = 1; i <= n; i++) if (f[i] == key) bk = i
        if (!bk) { print "unknown column: " key " in second file" > "/dev/stderr"; bad = 2; exit 2 }
        bn = n
        for (i = 1; i <= n; i++) if (i != bk) { nm = f[i]; while (nm in used) nm = nm "_2"; used[nm] = 1; bcols[++nb] = i; bh[nb] = nm }
        next
      }
      id = (bk <= n) ? f[bk] : ""
      if (!(id in bseen)) { bseen[id] = 1; for (j = 1; j <= nb; j++) br[id, j] = (bcols[j] <= n) ? f[bcols[j]] : "" }
    }
    END {
      if (bad) exit bad
      out = ""
      for (i = 1; i <= an; i++) out = out (i > 1 ? "," : "") quote(ah[i])
      for (j = 1; j <= nb; j++) out = out "," quote(bh[j])
      print out
      for (r = 1; r <= rows; r++) {
        id = ar[r, ak]
        if (!(id in bseen)) continue
        out = ""
        for (i = 1; i <= an; i++) out = out (i > 1 ? "," : "") quote(ar[r, i])
        for (j = 1; j <= nb; j++) out = out "," quote(br[id, j])
        print out
      }
    }' "$1" "$2"
''')


def make_join(rng):
    ex = scn("example", {"a.csv": F("id,x\n1,a\n2,b\n"), "b.csv": F("id,y\n2,B\n3,C\n")}, Run("a.csv", "b.csv", "id"))
    a = csv(["id,name,city", '1,"Doe, Jane",Oslo', "2,Bob,Rome", "3,Cy,Oslo", "2,Bob again,Rome", "9,Nobody,Nowhere"]) + "\n"
    b = csv(["city,id,population,name", "Oslo,1,700000,\"Capital, N\"", "Rome,2,2800000,Roma", "Lima,3,9000000,x"]) + "\n"
    return ex, [scn("join on id", {"a.csv": F(a), "b.csv": F(b)}, Run("a.csv", "b.csv", "id"), Run("a.csv", "b.csv", "city")), scn("no matches", {"a.csv": F("k,v\n1,a\n"), "b.csv": F("k,w\n2,b\n")}, Run("a.csv", "b.csv", "k")),
                scn("errors", {"a.csv": F(a), "b.csv": F(b)}, Run("a.csv", "b.csv", "nope", stderr="nonempty"), Run("a.csv"), Run("a.csv", "missing.csv", "id"))]


# ------------------------------------------------------------------------------------------------ 6. csv to tsv

REF_TSV = dd('''
    #!/usr/bin/env bash
    # csv2tsv.sh : CSV on stdin -> TSV; a TAB inside a field becomes \\t and a backslash becomes \\\\
    awk '
''' + P + '''
    /^[ \\t]*$/ { next }
    {
      n = parse($0)
      out = ""
      for (i = 1; i <= n; i++) { v = f[i]; gsub(/\\\\/, "\\\\\\\\", v); gsub(/\\t/, "\\\\t", v); out = out (i > 1 ? "\\t" : "") v }
      print out
    }'
''')


def make_tsv(rng):
    ex = scn("example", {}, Run(stdin='a,"b,c",d\n'))
    txt = 'id,text,note\n1,"tab\there","back\\slash"\n2,"quote ""q""",\n\n3,,"x,y,z"\n4,"  edge  ",end\n'
    return ex, [scn("conversion", {}, Run(stdin=txt), Run(stdin=""), Run(stdin="solo\n"))]


# ------------------------------------------------------------------------------------------------ 7. validation

REF_VALID = dd('''
    #!/usr/bin/env bash
    # csv-validate.sh FILE : report structural problems as "LINE: message"; exit 1 if any
    [ $# -eq 1 ] && [ -r "$1" ] || { echo "usage: csv-validate.sh FILE" >&2; exit 2; }
    awk '
    function quotes_ok(line,   i, q, len, c) {
      q = 0; len = length(line)
      for (i = 1; i <= len; i++) { c = substr(line, i, 1); if (c == "\\"") q = !q }
      return !q
    }
''' + P + '''
    /^[ \\t]*$/ { next }
    {
      if (!quotes_ok($0)) { print NR ": unbalanced quotes"; bad = 1; next }
      n = parse($0)
      if (!hdr) {
        hdr = 1; cols = n
        for (i = 1; i <= n; i++) { if (f[i] == "") { print NR ": empty column name"; bad = 1 } else if (f[i] in seen) { print NR ": duplicate column name \\047" f[i] "\\047"; bad = 1 } seen[f[i]] = 1 }
        next
      }
      if (n != cols) { print NR ": expected " cols " fields, found " n; bad = 1 }
    }
    END { exit bad ? 1 : 0 }' "$1"
''')


def make_valid(rng):
    ex = scn("example", {"d.csv": F("a,b\n1,2,3\n")}, Run("d.csv"))
    bad = 'id,name,id,\n1,Ann,x,y\n2,"Bob,x,y\n3,"ok, fine",z,w\n4,short\n\n5,too,many,fields,here\n6,"say ""hi""",a,b\n'
    return ex, [scn("problems", {"bad.csv": F(bad)}, Run("bad.csv")), scn("clean file", {"good.csv": F(SAMPLE)}, Run("good.csv")), scn("empty and usage", {"e.csv": F("")}, Run("e.csv"), Run(stderr="nonempty"), Run("nope.csv"))]


# ------------------------------------------------------------------------------------------------ 8. group totals

REF_GROUP = dd('''
    #!/usr/bin/env bash
    # csv-group.sh FILE KEYCOL VALCOL : "KEYCOL,count,sum" per distinct key, sorted by key (byte-wise); empty values are not counted
    [ $# -eq 3 ] && [ -r "$1" ] || { echo "usage: csv-group.sh FILE KEYCOL VALCOL" >&2; exit 2; }
    awk -v kc="$2" -v vc="$3" '
''' + P + '''
    /^[ \\t]*$/ { next }
    {
      n = parse($0)
      if (++rows == 1) {
        for (i = 1; i <= n; i++) { if (f[i] == kc) ki = i; if (f[i] == vc) vi = i }
        if (!ki || !vi) { print "unknown column" > "/dev/stderr"; bad = 2; exit 2 }
        next
      }
      k = (ki <= n) ? f[ki] : ""
      v = (vi <= n) ? f[vi] : ""
      if (!(k in seen)) { seen[k] = 1; keys[++nk] = k }
      if (v == "") next
      if (v !~ /''' + NUM + '''/) { print "line " NR ": not a number: " v > "/dev/stderr"; bad = 1; exit 1 }
      cnt[k]++; sum[k] += cents(v)
    }
    END {
      if (bad) exit bad
      for (i = 2; i <= nk; i++) { x = keys[i]; for (j = i - 1; j >= 1 && keys[j] > x; j--) keys[j + 1] = keys[j]; keys[j + 1] = x }
      print quote(kc) ",count,sum"
      for (i = 1; i <= nk; i++) print quote(keys[i]) "," cnt[keys[i]] + 0 "," money(sum[keys[i]])
    }' "$1"
''')


def make_group(rng):
    ex = scn("example", {"d.csv": F("k,v\na,1\nb,2\na,3.5\n")}, Run("d.csv", "k", "v"))
    f = {"s.csv": F(SAMPLE), "bad.csv": F("k,v\na,1\nb,oops\n")}
    return ex, [scn("groups", f, Run("s.csv", "city", "amount"), Run("s.csv", "note", "id")), scn("errors", f, Run("bad.csv", "k", "v", stderr="nonempty"), Run("s.csv", "city", "nope"), Run("s.csv", "city"))]


# ------------------------------------------------------------------------------------------------ 9. dedupe by columns

REF_DEDUP = dd('''
    #!/usr/bin/env bash
    # csv-dedupe.sh [-l] FILE COL... : drop rows whose COL values were seen before (-l: keep the last occurrence instead of the first)
    last=0
    if [ "${1:-}" = -l ]; then last=1; shift; fi
    [ $# -ge 2 ] && [ -r "$1" ] || { echo "usage: csv-dedupe.sh [-l] FILE COL..." >&2; exit 2; }
    file=$1
    shift
    spec=$(printf '%s\\n' "$@")
    awk -v spec="$spec" -v last="$last" '
''' + P + '''
    BEGIN { nc = split(spec, want, "\\n") }
    /^[ \\t]*$/ { next }
    {
      n = parse($0)
      if (++rows == 1) {
        for (i = 1; i <= n; i++) if (!(f[i] in idx)) idx[f[i]] = i
        for (j = 1; j <= nc; j++) { if (!(want[j] in idx)) { print "unknown column: " want[j] > "/dev/stderr"; bad = 2; exit 2 } col[j] = idx[want[j]] }
        print; next
      }
      key = ""
      for (j = 1; j <= nc; j++) key = key (col[j] <= n ? f[col[j]] : "") "\\034"
      m++
      line[m] = $0; k[m] = key
      lastidx[key] = m
      if (!(key in firstidx)) firstidx[key] = m
    }
    END {
      if (bad) exit bad
      for (i = 1; i <= m; i++) if ((last ? lastidx[k[i]] : firstidx[k[i]]) == i) print line[i]
    }' "$file"
''')


def make_dedup(rng):
    ex = scn("example", {"d.csv": F("id,v\n1,a\n1,b\n2,c\n")}, Run("d.csv", "id"))
    d = csv(["id,city,note", '1,Oslo,first', '2,"Rome, IT",x', '1,Oslo,second', '3,Oslo,third', '2,"Rome, IT",y', '1,oslo,case differs', '4,,empty city', '5,,empty city too', '4,,dup']) + "\n"
    return ex, [scn("dedupe", {"d.csv": F(d)}, Run("d.csv", "id"), Run("-l", "d.csv", "id"), Run("d.csv", "id", "city"), Run("-l", "d.csv", "city"), Run("d.csv", "note", "note")), scn("errors", {"d.csv": F(d)}, Run("d.csv", "nope", stderr="nonempty"), Run("d.csv"), Run("-l", "d.csv"))]


# ------------------------------------------------------------------------------------------------ 10. csv to json

REF_JSON = dd('''
    #!/usr/bin/env bash
    # csv2json.sh FILE : JSON array of objects, one per data row, every value a string
    [ $# -eq 1 ] && [ -r "$1" ] || { echo "usage: csv2json.sh FILE" >&2; exit 2; }
    awk '
''' + P + '''
    function js(s) { gsub(/\\\\/, "\\\\\\\\", s); gsub(/"/, "\\\\\\"", s); gsub(/\\t/, "\\\\t", s); return "\\"" s "\\"" }
    /^[ \\t]*$/ { next }
    {
      n = parse($0)
      if (++rows == 1) { hn = n; for (i = 1; i <= n; i++) h[i] = f[i]; next }
      obj = "{"
      for (i = 1; i <= hn; i++) obj = obj (i > 1 ? ", " : "") js(h[i]) ": " js(i <= n ? f[i] : "")
      objs[++m] = obj "}"
    }
    END {
      if (m == 0) { print "[]"; exit }
      print "["
      for (i = 1; i <= m; i++) print "  " objs[i] (i < m ? "," : "")
      print "]"
    }' "$1"
''')


def make_json(rng):
    ex = scn("example", {"d.csv": F("a,b\n1,x\n")}, Run("d.csv"))
    d = 'id,name,note\n1,"Doe, Jane","says ""hi"""\n2,Bob\n3,"tab\there",back\\slash\n4,,"x,y"\n5,Ünï,extra,fields,ignored\n'
    return ex, [scn("objects", {"d.csv": F(d), "h.csv": F("only,header\n"), "e.csv": F("")}, Run("d.csv"), Run("h.csv"), Run("e.csv")), scn("usage", {"d.csv": F(d)}, Run(stderr="nonempty"), Run("nope.csv"))]


# ------------------------------------------------------------------------------------------------ 11. fix cut-based column

BUG_COL = dd('''
    #!/bin/bash
    # csv-col.sh FILE N : print column N (1-based) of every row, decoded
    cut -d, -f$2 $1
''')
REF_COL = dd('''
    #!/usr/bin/env bash
    # csv-col.sh FILE N : print column N (1-based) of every row, decoded
    [ $# -eq 2 ] && [ -r "$1" ] && [[ $2 =~ ^[1-9][0-9]*$ ]] || { echo "usage: csv-col.sh FILE N" >&2; exit 2; }
    awk -v c="$2" '
''' + P + '''
    /^[ \\t]*$/ { next }
    { n = parse($0); print (c <= n ? f[c] : "") }' "$1"
''')


def make_col(rng):
    ex = scn("example", {"d.csv": F('a,"b,c",d\n')}, Run("d.csv", "2"))
    f = {"s.csv": F(SAMPLE + "\n")}
    return ex, [scn("columns", f, Run("s.csv", "2"), Run("s.csv", "5"), Run("s.csv", "1"), Run("s.csv", "9")), scn("usage", f, Run("s.csv", "0", stderr="nonempty"), Run("s.csv", "x"), Run("s.csv"), Run("nope.csv", "1"))]


SPECS = [
    S("csv-select-columns", 3,
      "Write `csv-cols.sh FILE COL...`: keep chosen columns of a CSV file (by header name or position), with proper quoting.",
      "`bash csv-cols.sh FILE COL...` reads a CSV file with a header row. Fields may be double-quoted (`\"\"` is a quote inside; no field contains a line break); blank lines are ignored. Each `COL` is a header name or `#N` (the N-th column, 1-based); the output has those columns in the given order (repeats allowed), header included. "
      "Missing cells (short rows, `#N` beyond the width) are empty. Output fields are re-quoted: a field is written in double quotes (inner quotes doubled) when it contains a comma or a double quote or begins or ends with a space; otherwise it is written bare. "
      "Unknown name: `unknown column: NAME` on stderr, exit 2, no output. Missing columns argument or unreadable file: usage message on stderr, exit 2.",
      REF_COLS, make_cols, script="csv-cols.sh", title="Select CSV columns", wrong=("#!/bin/bash\ncut -d, -f1 \"$1\"\n",)),
    S("csv-column-sum", 3,
      "Write `csv-sum.sh FILE COL`: the exact sum of a numeric column, two decimals.",
      "`bash csv-sum.sh FILE COL` sums the column named `COL` of a CSV file with a header (same CSV conventions as the other tools: double-quoted fields, no line breaks inside, blank lines ignored). Cells are numbers with an optional sign and at most two decimals; empty cells (or missing ones in short rows) are skipped. "
      "Print the sum with exactly two decimals, computed exactly (`0.10 + 0.20 - 0.30` is `0.00`, never `-0.00`). A non-numeric cell prints `line N: not a number: VALUE` on stderr and exits 1 with no output; an unknown column prints `unknown column: NAME` and exits 2; wrong arguments: usage message, exit 2.",
      REF_SUM, make_sum, script="csv-sum.sh", title="Sum a CSV column", wrong=("#!/bin/bash\nawk -F, -v c=\"$2\" 'NR>1{s+=$c} END{print s}' \"$1\"\n",)),
    S("csv-stable-sort", 3,
      "Write `csv-sort.sh FILE COL [-n] [-r]`: sort the rows of a CSV file by one column, keeping the header on top and ties in their original order.",
      "`bash csv-sort.sh FILE COL [-n] [-r]` prints the header row first and then the data rows sorted by the column named `COL` (decoded value; quoted fields with commas count as one field; blank lines are ignored; rows are printed exactly as in the file). "
      "Default comparison is byte-wise on the text; with `-n` it is numeric (`10` > `9`, decimals and signs allowed) and cells that are not numbers, empty or missing count as 0. `-r` reverses the order of the keys but rows with equal keys still keep their original order (the sort is stable in both directions). "
      "Unknown column: message on stderr, exit 2; an unknown option or wrong arguments: usage message on stderr, exit 2.",
      REF_SORT, make_sort, script="csv-sort.sh", title="Stable CSV sort", wrong=("#!/bin/bash\n(head -1 \"$1\"; tail -n +2 \"$1\" | sort -t, -k1,1) \n",)),
    S("csv-filter-rows", 3,
      "Write `csv-filter.sh FILE COL OP VALUE`: print the header and the rows where a column satisfies a simple condition.",
      "`bash csv-filter.sh FILE COL OP VALUE` prints the header and every data row (exactly as in the file) for which the decoded value of column `COL` satisfies `OP VALUE`. Operators: `eq`, `ne` (exact text), `contains` (the cell contains the text, possibly empty), "
      "and `lt gt le ge` (numeric comparison; a cell that is not a number never matches; `VALUE` must be a number). Quoted fields, doubled quotes and commas inside quotes follow the usual CSV rules; blank lines are ignored. "
      "Unknown column, unknown operator or a non-numeric `VALUE` for a numeric operator: message on stderr, exit 2. Wrong number of arguments: usage message, exit 2.",
      REF_FILTER, make_filter, script="csv-filter.sh", title="Filter CSV rows", wrong=("#!/bin/bash\ngrep \"$4\" \"$1\"\n",)),
    S("csv-inner-join", 4,
      "Write `csv-join.sh A B KEY`: inner-join two CSV files on a column name they share.",
      "`bash csv-join.sh A B KEY` joins two CSV files with headers on the column named `KEY` (present in both; unique in `B`; compared as exact text). The output header is the header of `A` followed by the columns of `B` except `KEY`; a `B` column whose name already occurs gets `_2` appended (repeatedly if needed). "
      "Output rows follow the order of `A`; rows of `A` with no match in `B` are dropped; a repeated key in `A` joins each time. Fields are re-quoted when they contain a comma or a double quote or begin or end with a space. Unknown key, unreadable file or wrong arguments: message on stderr, exit 2.",
      REF_JOIN, make_join, script="csv-join.sh", title="Inner join of two CSV files", wrong=("#!/bin/bash\njoin -t, \"$1\" \"$2\"\n",)),
    S("csv-to-tsv", 3,
      "Write `csv2tsv.sh`: convert CSV from stdin to TSV, unquoting fields and escaping TABs and backslashes.",
      "`bash csv2tsv.sh` reads CSV on standard input (double-quoted fields with `\"\"` for a quote, no line breaks inside fields, blank lines skipped) and writes one TSV line per row: the decoded fields joined by TABs, where a TAB inside a field is written `\\t` and a backslash `\\\\` (the two characters). Nothing else is changed (empty fields stay empty, spaces stay).",
      REF_TSV, make_tsv, script="csv2tsv.sh", title="CSV to TSV", wrong=("#!/bin/bash\ntr , '\\t'\n",)),
    S("csv-validator", 3,
      "Write `csv-validate.sh FILE`: report structural problems of a CSV file as `LINE: message` lines.",
      "`bash csv-validate.sh FILE` checks a CSV file and prints `LINE: MESSAGE` (1-based physical line numbers, in order; blank lines are skipped but counted), at most one message per line, exiting 1 if anything was printed and 0 otherwise. Checks, in this order per line: "
      "`unbalanced quotes` (an odd number of `\"` characters on the line); for the first non-blank line (the header): `empty column name` and `duplicate column name 'NAME'` (one message per offending name, the header's width defines the expected field count and these messages can follow each other on the same line number); "
      "for every other line: `expected N fields, found M` when the number of fields (commas outside quotes, plus one) differs from the header's. Wrong arguments or unreadable file: usage message, exit 2.",
      REF_VALID, make_valid, script="csv-validate.sh", title="CSV validator", wrong=("#!/bin/bash\nawk -F, 'NR==1{n=NF} NF!=n{print NR\": bad\"}' \"$1\"\n",)),
    S("csv-group-totals", 3,
      "Write `csv-group.sh FILE KEYCOL VALCOL`: count and total per distinct key, exact to the cent.",
      "`bash csv-group.sh FILE KEYCOL VALCOL` prints the header `KEYCOL,count,sum` (the key column name, quoted if needed) and then one line per distinct value of `KEYCOL` (decoded text, empty included), sorted byte-wise, with the number of non-empty `VALCOL` cells and their exact sum with two decimals. "
      "Cells are numbers with an optional sign and at most two decimals; empty ones are not counted. A group whose cells are all empty shows `0` and `0.00`. A non-numeric cell: `line N: not a number: VALUE` on stderr, exit 1, no output. Unknown column or wrong arguments: message, exit 2. Keys are re-quoted when they contain a comma or quote or begin/end with a space.",
      REF_GROUP, make_group, script="csv-group.sh", title="Group totals", wrong=("#!/bin/bash\ncut -d, -f3 \"$1\" | sort | uniq -c\n",)),
    S("csv-dedupe-rows", 3,
      "Write `csv-dedupe.sh [-l] FILE COL...`: drop rows that repeat the values of the given columns, keeping the first (or with `-l` the last) occurrence.",
      "`bash csv-dedupe.sh [-l] FILE COL...` prints the header and then the data rows (exactly as written in the file) whose combination of values in the named columns has not occurred in an earlier row; with `-l` the **last** row of each combination is kept instead, "
      "and output order is the file order of the rows that remain. Values are compared as decoded exact text. Blank lines are skipped. An unknown column name, no column at all or an unreadable file: message on stderr, exit 2.",
      REF_DEDUP, make_dedup, script="csv-dedupe.sh", title="Deduplicate CSV rows", wrong=("#!/bin/bash\nsort -u \"$1\"\n",)),
    S("csv-to-json-objects", 4,
      "Write `csv2json.sh FILE`: turn a CSV file into a JSON array of objects, with exactly the formatting described.",
      "`bash csv2json.sh FILE` prints the CSV (first row = header; double-quoted fields with `\"\"`; no line breaks in fields; blank lines skipped) as a JSON array: line `[`, then one line per data row `  {\"h1\": \"v1\", \"h2\": \"v2\"}` (two leading spaces, `\", \"` between members, `\": \"` between key and value, all values strings) "
      "with a comma at the end of every row line except the last, then line `]`. In strings `\"` is written `\\\"`, a backslash `\\\\`, a TAB `\\t`. Short rows get empty strings for missing cells, extra cells are ignored. No data rows (or an empty file): the single line `[]`. Wrong arguments or unreadable file: usage message, exit 2.",
      REF_JSON, make_json, script="csv2json.sh", title="CSV to JSON", wrong=("#!/bin/bash\ncat \"$1\"\n",)),
    S("fix-csv-column-cut", 2,
      "`csv-col.sh FILE N` prints one column of a CSV file with `cut -d,`, which splits quoted fields at their commas and keeps the quotes. Fix it.",
      "`bash csv-col.sh FILE N` prints the decoded value of the N-th column (1-based) of every non-blank row, one per line: quotes are removed, `\"\"` becomes `\"`, commas inside quotes belong to the value; a row with fewer fields prints an empty line. "
      "`N` must be a positive integer and `FILE` readable, otherwise usage message on stderr, exit status 2.",
      REF_COL, make_col, script="csv-col.sh", buggy=BUG_COL, title="Fix the CSV column picker", wrong=(BUG_COL,)),
]


@family("shell-csv-tools", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="CSV tools with quoted fields in bash/awk: columns, sums, stable sort, filter, join, TSV, validation, grouping, dedupe, JSON")
def csv_tools(rng, n):
    return K.shell_tasks("csv-tools", SPECS, rng, n)
