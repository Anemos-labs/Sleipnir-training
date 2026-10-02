"""Shell tasks, expert awk: exact arithmetic on digit strings, multi-line quoted CSV records, an RPN calculator, a topological sort with alphabetical ties and a unified-diff patcher (POSIX awk; the tests run mawk)."""
import difflib
import random

from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec
RUN = ("awk", "-f")
NOTE = " Plain POSIX awk only (the tests run `awk -f`, which is mawk here): no gawk extensions."


def doc(text):
    return dd(text).rstrip("\n") + "\n\n" + NOTE.strip() + "\n"


def lines(rows):
    return "".join(r + "\n" for r in rows)


# ------------------------------------------------------------------------------------------------ 1. digit-string arithmetic

REF_BIG = dd(r'''
    # bigcalc.awk : exact "A + B" and "A - B" on arbitrarily long non-negative integers
    function strip(s) { sub(/^0+/, "", s); return s == "" ? "0" : s }
    function cmp(a, b) {
      if (length(a) != length(b)) return length(a) < length(b) ? -1 : 1
      a = a ""; b = b ""
      return a < b ? -1 : (a > b ? 1 : 0)
    }
    function add(a, b,   i, j, c, s, r) {
      i = length(a); j = length(b); c = 0; r = ""
      while (i > 0 || j > 0 || c) {
        s = c + (i > 0 ? substr(a, i, 1) : 0) + (j > 0 ? substr(b, j, 1) : 0)
        r = (s % 10) r
        c = int(s / 10)
        i--; j--
      }
      return strip(r)
    }
    function sub_(a, b,   i, j, d, br, r) {
      i = length(a); j = length(b); br = 0; r = ""
      while (i > 0) {
        d = substr(a, i, 1) - br - (j > 0 ? substr(b, j, 1) : 0)
        if (d < 0) { d += 10; br = 1 } else br = 0
        r = d r
        i--; j--
      }
      return strip(r)
    }
    /^[ \t]*(#|$)/ { next }
    NF == 3 && $1 ~ /^[0-9]+$/ && $3 ~ /^[0-9]+$/ && ($2 == "+" || $2 == "-") {
      a = strip($1); b = strip($3)
      if ($2 == "+") print add(a, b)
      else if (cmp(a, b) >= 0) print sub_(a, b)
      else print "-" sub_(b, a)
      next
    }
    { print "error" }
''')

DOC_BIG = doc('''
    `awk -f bigcalc.awk` reads lines from standard input (or from the files named after the script) and calculates exactly, with **arbitrarily long** non-negative integers (awk's own numbers lose digits after about 15 places):
    a line of three whitespace-separated fields `A + B` or `A - B`, where `A` and `B` are strings of decimal digits (leading zeros allowed) and the operator is a lone `+` or `-`.
    It prints the result as a decimal number without leading zeros on its own line; a negative result has a leading `-` and zero is `0` (never `-0`).
    Blank lines and lines whose first non-blank character is `#` produce no output. Any other line prints `error`.
''')


def _digits(rng, lo, hi):
    return "".join(rng.choice("0123456789") for _ in range(rng.randint(lo, hi)))


def make_big(rng):
    ex = scn("example", {}, Run(stdin="12 + 30\n100 - 1\n5 - 9\n"))
    rows = []
    for _ in range(14):
        a, b = _digits(rng, 1, 45), _digits(rng, 1, 45)
        rows.append(f"{a} {rng.choice(['+', '-'])} {b}")
    n = rng.randint(30, 50)
    rows += ["9" * n + " + 1", "1" + "0" * n + " - 1", "0" * 5 + "7 + 003", "000 - 0", "0 - 0001", "5 - 5", "1" + "0" * n + " - " + "1" + "0" * n,
             "123456789012345678901234567890 + 987654321098765432109876543210", "# comment", "", "   ", "12 +", "12 * 3", "1a + 2", "-5 + 3", "1.5 + 2", "7   +   8", "\t42\t-\t7", "9007199254740993 + 2"]
    return ex, [scn("many sums", {}, Run(stdin=lines(rows))), scn("edge lines", {}, Run(stdin=lines(rows[::-1]))),
                scn("empty input", {}, Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 2. quoted CSV with line breaks

REF_QCSV = dd(r'''
    # qcsv2tsv.awk : CSV records (quoted fields may hold commas, quotes and line breaks) -> one TSV line per record
    function esc(s,   i, c, r) {
      r = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        if (c == "\\") r = r "\\\\"
        else if (c == "\t") r = r "\\t"
        else if (c == "\n") r = r "\\n"
        else r = r c
      }
      return r
    }
    # parse rec; returns the TSV line in OUT and 1 when the record ended inside quotes
    function parse(rec,   i, n, c, inq, start, f, first) {
      n = length(rec); inq = 0; start = 1; f = ""; first = 1; OUT = ""
      for (i = 1; i <= n; i++) {
        c = substr(rec, i, 1)
        if (inq) {
          if (c == "\"") {
            if (substr(rec, i + 1, 1) == "\"") { f = f "\""; i++ } else inq = 0
          } else f = f c
        } else if (c == "\"" && start) { inq = 1; start = 0 }
        else if (c == ",") { OUT = OUT (first ? "" : "\t") esc(f); first = 0; f = ""; start = 1 }
        else { f = f c; start = 0 }
      }
      OUT = OUT (first ? "" : "\t") esc(f)
      return inq
    }
    {
      rec = pending ? rec "\n" $0 : $0
      if (!pending && $0 == "") next
      if (parse(rec)) { pending = 1; next }
      print OUT
      pending = 0; rec = ""
    }
    END { if (pending) { parse(rec); print OUT } }
''')

DOC_QCSV = doc(r'''
    `awk -f qcsv2tsv.awk` converts CSV on standard input to TSV: one output line per CSV **record**, the decoded fields joined by single TAB characters.

    * Fields are separated by commas. A field that **starts** with a double quote is quoted: it runs to the closing quote, a doubled quote `""` inside stands for one quote character, and commas and **line breaks** inside are part of the value
      (so one record can span several input lines). After the closing quote any characters up to the next comma are kept as they are. A quote anywhere else in a field is an ordinary character.
    * A record ends at a line break outside quotes. A completely empty line between records is skipped; a record whose only field is empty but written as `""` produces an empty output line.
      If the input ends while a quoted field is still open, the field ends there and the record is written anyway.
    * In the output, a backslash in a value is written as two backslashes, a TAB as `\t` and a line break as `\n` (backslash and a letter), so each record stays on one line. Nothing else is changed (spaces stay, empty fields stay empty).
''')


def _field(rng):
    kind = rng.random()
    words = ["alpha", "b c", "x,y", "say \"hi\"", "tab\there", "back\\slash", "two\nlines", "", "  pad  ", "semi;colon", "q\"", "last\nline\nthree", "a,b,c", "\"", "plain"]
    w = rng.choice(words)
    if kind < 0.3 and "," not in w and '"' not in w and "\n" not in w:
        return w
    return '"' + w.replace('"', '""') + '"'


def make_qcsv(rng):
    ex = scn("example", {}, Run(stdin='id,note\n1,"hello, world"\n2,"line one\nline two"\n'))
    rows = []
    for _ in range(14):
        rows.append(",".join(_field(rng) for _ in range(rng.randint(1, 5))))
    tricky = ['a,"",c', '""', '"",""', 'x"y,mid"quote', '"ab"cd,e', ',,', '"a""b""",z', '"ends with newline\n",k', '"x\n\ny",1', '  "not quoted",2', 'tail,']
    body = rows[:6] + tricky + rows[6:] + [""]
    text = "\n".join(body[:7]) + "\n\n" + "\n".join(body[7:]) + "\n"
    return ex, [scn("records", {}, Run(stdin=text)),
                scn("open quote at the end", {}, Run(stdin='a,b\n1,"never closed\nsecond line\n')),
                scn("empty", {}, Run(stdin="")), scn("only blank lines", {}, Run(stdin="\n\n\n"))]


# ------------------------------------------------------------------------------------------------ 3. RPN calculator

REF_RPN = dd(r'''
    # rpn.awk : one reverse-Polish expression per line
    function fmt(x) { if (x == 0) x = 0; return sprintf("%.10g", x) }
    /^[ \t]*$/ { next }
    {
      sp = 0; err = ""
      for (i = 1; i <= NF && err == ""; i++) {
        t = $i
        if (t ~ /^-?[0-9]+(\.[0-9]+)?$/) st[++sp] = t + 0
        else if (t == "dup") { if (sp < 1) err = "stack underflow"; else { st[sp + 1] = st[sp]; sp++ } }
        else if (t == "drop") { if (sp < 1) err = "stack underflow"; else sp-- }
        else if (t == "swap") { if (sp < 2) err = "stack underflow"; else { x = st[sp]; st[sp] = st[sp - 1]; st[sp - 1] = x } }
        else if (t ~ /^[-+*\/%^]$/) {
          if (sp < 2) { err = "stack underflow"; break }
          b = st[sp--]; a = st[sp--]
          if (t == "+") r = a + b
          else if (t == "-") r = a - b
          else if (t == "*") r = a * b
          else if (t == "/") { if (b == 0) { err = "division by zero"; break } r = a / b }
          else if (t == "%") { if (b == 0) { err = "division by zero"; break } r = a % b }
          else { if (b < 0 || b != int(b)) { err = "bad exponent"; break } r = a ^ b }
          st[++sp] = r
        } else err = "unknown token " t
      }
      if (err == "" && sp != 1) err = "expected one result, found " sp
      if (err != "") print "error: " err
      else print fmt(st[1])
    }
''')

DOC_RPN = doc(r'''
    `awk -f rpn.awk` evaluates one reverse-Polish (postfix) expression per line of standard input and prints one result line for it. Tokens are separated by blanks.

    * A number is an optional minus sign, digits, and optionally a dot with digits (`-3`, `2.5`). Operators `+ - * / % ^` take the two top values `a` (deeper) and `b` (top) and push `a OP b`: `3 4 -` is -1, `7 2 /` is 3.5, `7 2 %` is 1 (awk's `%`), `2 10 ^` is 1024.
      Words: `dup` copies the top value, `drop` removes it, `swap` exchanges the top two.
    * The result is the single value left on the stack, printed with `printf "%.10g"` (and `0` instead of `-0`). Blank lines produce no output.
    * Anything else produces one line `error: ...` instead of a result, and evaluation of that line stops at the first problem, in this order of checking per token: `error: stack underflow` (not enough values), `error: division by zero` (`/` or `%` by 0),
      `error: bad exponent` (the exponent of `^` is negative or not a whole number), `error: unknown token TOKEN`. When all tokens went fine but the stack does not hold exactly one value: `error: expected one result, found N` (N may be 0).
''')


def make_rpn(rng):
    ex = scn("example", {}, Run(stdin="3 4 +\n7 2 /\n1 +\n"))
    exprs = ["3 4 + 2 *", "5 1 2 + 4 * + 3 -", "2 10 ^", "2 0.5 ^", "2 -1 ^", "7 0 /", "7 0 %", "1 2 3", "", "   ", "dup", "4 dup *", "1 2 swap -", "5 drop", "5 drop drop", "x", "3 4 foo +", "0 0 -", "0 -1 *", "-7 2 %", "7 -2 %",
             "1 3 /", "100 3 /", "2 40 ^", "1.5 1.5 +", "10 4 - 3 - ", "1 2 +  3 4 + *", "-2 3 ^", "9 0.0 /", "1e3", "5 +", "2 3 4 + ^", "0.1 0.2 +", "12345678901 1 +", "3 3 3 3 + +"]
    rng.shuffle(exprs)
    return ex, [scn("expressions", {}, Run(stdin=lines(exprs))), scn("every operator", {}, Run(stdin=lines(["8 3 -", "8 3 +", "8 3 *", "8 3 /", "8 3 %", "8 3 ^", "-8 3 %", "8 -3 %", "0.5 4 *", "2 3 swap /"]))),
                scn("empty input", {}, Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 4. topological order

REF_TOPO = dd(r'''
    # order.awk : "A B" means A must come before B; print an order, alphabetical among the possible choices
    /^[ \t]*(#|$)/ { next }
    NF == 1 { node[$1] = 1; next }
    NF == 2 {
      node[$1] = 1; node[$2] = 1
      if (!(($1 SUBSEP $2) in edge)) { edge[$1, $2] = 1; indeg[$2]++; out[$1] = out[$1] " " $2 }
      next
    }
    { bad = 1 }
    END {
      if (bad) { print "bad input" > "/dev/stderr"; exit 2 }
      total = 0
      for (n in node) total++
      for (k = 1; k <= total; k++) {
        pick = ""
        for (n in node) if (!(n in done) && indeg[n] == 0 && (pick == "" || n < pick)) pick = n
        if (pick == "") break
        print pick
        done[pick] = 1
        m = split(out[pick], to, " ")
        for (j = 1; j <= m; j++) indeg[to[j]]--
        placed++
      }
      if (placed < total) {
        rest = ""
        for (n in node) if (!(n in done)) rest = rest " " n
        m = split(substr(rest, 2), r, " ")
        for (i = 2; i <= m; i++) { v = r[i]; for (j = i - 1; j >= 1 && r[j] > v; j--) r[j + 1] = r[j]; r[j + 1] = v }
        line = "cycle:"
        for (i = 1; i <= m; i++) line = line " " r[i]
        print line
        exit 1
      }
    }
''')

DOC_TOPO = doc(r'''
    `awk -f order.awk` reads dependency lines from standard input. A line with two names `A B` says that `A` must come **before** `B`; a line with one name `X` just declares that `X` exists. Names are non-blank strings without spaces; blank lines and `#` comment lines are skipped; the same pair may be repeated.
    It prints every name once, one per line, in an order that respects all pairs; among the names that could come next, the **smallest in byte order** (plain `<` string comparison) always goes first.
    If the pairs contain a cycle (a name before itself counts), it prints the names that could be ordered first, as above, and then one final line `cycle:` followed by all names that could **not** be ordered (the ones on or after a cycle), in byte order, separated by single spaces,
    and exits with status 1. A line with more than two fields prints `bad input` on standard error and exits with status 2 without any output.
''')


def make_topo(rng):
    ex = scn("example", {}, Run(stdin="app lib\nlib core\nutil core\n"))
    names = ["core", "app", "lib", "util", "net", "db", "ui", "cli", "log", "Zed", "alpha-1", "beta_2", "x.y"]

    def dag(n, extra):
        pick = rng.sample(names, n)
        rows = []
        for i in range(n):
            for j in range(i + 1, n):
                if rng.random() < 0.28:
                    rows.append(f"{pick[i]} {pick[j]}")
        rows += [f"{pick[0]} {pick[1]}", f"# a comment", "", f"{rng.choice(names)}"] + extra
        rng.shuffle(rows)
        return rows
    cyc = ["a b", "b c", "c a", "c d", "e a", "f"]
    return ex, [scn("acyclic graphs", {}, Run(stdin=lines(dag(9, []))), Run(stdin=lines(dag(6, [])))),
                scn("ties are alphabetical", {}, Run(stdin=lines(["m z", "m y", "m x", "b a", "Z a", "m m2", "isolated"]))),
                scn("cycles", {}, Run(stdin=lines(cyc)), Run(stdin=lines(["x x", "y"])), Run(stdin=lines(["p q", "q p", "o p", "r s"]))),
                scn("bad lines and empty input", {}, Run(stdin="a b c\nd e\n", stderr="nonempty"), Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 5. apply a unified diff

REF_PATCH = dd(r'''
    # applydiff.awk PATCH ORIGINAL : apply the hunks of a unified diff to ORIGINAL and print the result
    function fail(msg) { print msg > "/dev/stderr"; failed = 1; exit 1 }
    FNR == NR {
      if ($0 ~ /^@@ /) {
        nh++
        match($0, /-[0-9]+(,[0-9]+)?/)
        split(substr($0, RSTART + 1, RLENGTH - 1), a, ",")
        os[nh] = a[1] + 0
        ol[nh] = (a[2] == "" ? 1 : a[2] + 0)
        inh = 1
        next
      }
      if (inh && $0 ~ /^[ +-]/) { k = ++cnt[nh]; typ[nh, k] = substr($0, 1, 1); txt[nh, k] = substr($0, 2) }
      next
    }
    { orig[FNR] = $0; n = FNR }
    END {
      if (failed) exit 1
      m = 0; pos = 1
      for (h = 1; h <= nh; h++) {
        start = (ol[h] == 0) ? os[h] + 1 : os[h]
        if (start < pos || start > n + 1) fail("hunk " h " failed: bad position")
        while (pos < start) res[++m] = orig[pos++]
        for (k = 1; k <= cnt[h]; k++) {
          if (typ[h, k] == "+") res[++m] = txt[h, k]
          else {
            if (pos > n || orig[pos] != txt[h, k]) fail("hunk " h " failed: line " pos " does not match")
            if (typ[h, k] == " ") res[++m] = orig[pos]
            pos++
          }
        }
      }
      while (pos <= n) res[++m] = orig[pos++]
      for (i = 1; i <= m; i++) print res[i]
    }
''')

DOC_PATCH = doc(r'''
    `awk -f applydiff.awk PATCH ORIGINAL` applies a unified diff to a text file and prints the patched text on standard output (the files themselves are not modified).

    * Everything in `PATCH` before the first line that starts with `@@ ` (the `---`/`+++` headers and so on) is ignored. A hunk starts with `@@ -S[,L] +S2[,L2] @@`; `S` is the line of ORIGINAL (counting from 1) where the hunk begins and `L` the number of ORIGINAL lines it covers (1 when `,L` is missing).
      When `L` is 0 the hunk only inserts: the new lines go **after** line `S` (`-0,0` means at the very beginning). The `+` side numbers are not needed.
    * Every following line of the hunk starts with a space (context: the line must be present and is kept), `-` (the line must be present and is removed) or `+` (a new line, inserted at that point), and the rest of the line is the text.
      The hunk lasts until the next `@@ ` line or the end of the patch. Hunks are in ascending order and do not overlap. There is no fuzz: context and removed lines have to match the original exactly at the stated place.
    * If a hunk does not apply (text differs, or the position is outside the file), print `hunk N failed: ...` (N counts from 1) on standard error, print **nothing** on standard output and exit with status 1.
      The files in the tests end with a newline and patches contain no `\ No newline` markers.
''')


def _words(rng, n):
    base = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet", "kilo", "lima", "mike", "november", "oscar", "papa", "quebec", "romeo", "sierra", "tango", "--- dashes ---", "+plus", "@@ at @@", " spaced", "same", "same"]
    return [f"{rng.choice(base)} {i}" if rng.random() < 0.7 else rng.choice(base) for i in range(n)]


def make_diff(rng):
    orig0 = ["one", "two", "three", "four", "five", "six", "seven", "eight"]
    new0 = ["one", "TWO", "three", "four", "five", "5.5", "six", "eight", "nine"]
    p0 = "".join(l + "\n" for l in difflib.unified_diff(orig0, new0, "a/list.txt", "b/list.txt", lineterm="", n=1))
    files0 = {"list.txt": F(lines(orig0)), "list.patch": F(p0)}
    ex = scn("example", files0, Run("list.patch", "list.txt"))
    scns = []
    for k in range(3):
        a = _words(rng, rng.randint(14, 30))
        b = list(a)
        for _ in range(rng.randint(2, 5)):
            kind = rng.choice(["del", "ins", "rep", "ins0", "tail"])
            i = rng.randrange(len(b)) if b else 0
            if kind == "del" and len(b) > 3:
                del b[i:i + rng.randint(1, 3)]
            elif kind == "ins":
                b[i:i] = [f"new {rng.randint(1, 99)}", "+added", "--- fake header"][: rng.randint(1, 3)]
            elif kind == "rep":
                b[i] = f"changed {rng.randint(1, 99)}"
            elif kind == "ins0":
                b.insert(0, "first line added")
            else:
                b.append("appended at the end")
        if k == 1:
            b = b[: len(b) // 2]
        if k == 2:
            b = ["completely", "different"]
        n = rng.choice([0, 1, 2, 3])
        patch = "".join(l + "\n" for l in difflib.unified_diff(a, b, "a/f.txt", "b/f.txt", lineterm="", n=n))
        if not patch:
            b.append("forced change")
            patch = "".join(l + "\n" for l in difflib.unified_diff(a, b, "a/f.txt", "b/f.txt", lineterm="", n=n))
        scns.append(scn(f"patch {k + 1} (context {n})", {"f.txt": F(lines(a)), "the patch.diff": F(patch)}, Run("the patch.diff", "f.txt")))
    a = _words(rng, 16)
    b = ["inserted at the very beginning"] + a[:4] + ["after four", "after four, too"] + a[4:10] + a[12:] + ["and at the end"]
    patch = "".join(l + "\n" for l in difflib.unified_diff(a, b, "a/f.txt", "b/f.txt", lineterm="", n=0))
    scns.append(scn("insertions and a deletion without context", {"f.txt": F(lines(a)), "bare.diff": F(patch)}, Run("bare.diff", "f.txt")))
    a = _words(rng, 14)
    b = list(a)
    b[3], b[9] = "replaced four", "replaced ten"
    patch = "".join(l + "\n" for l in difflib.unified_diff(a, b, "a/f.txt", "b/f.txt", lineterm="", n=0))
    scns.append(scn("one-line replacements", {"f.txt": F(lines(a)), "one.diff": F(patch)}, Run("one.diff", "f.txt")))
    a = _words(rng, 20)
    b = list(a)
    b[5] = "edited five"
    b[14] = "edited fourteen"
    patch = "".join(l + "\n" for l in difflib.unified_diff(a, b, "a/f.txt", "b/f.txt", lineterm="", n=2))
    drift = list(a)
    drift[14] = "someone else changed this"
    scns.append(scn("second hunk does not match", {"f.txt": F(lines(drift)), "p.diff": F(patch)}, Run("p.diff", "f.txt", stderr="nonempty")))
    shifted = ["extra line at the top"] + a
    scns.append(scn("line numbers do not line up", {"f.txt": F(lines(shifted)), "p.diff": F(patch)}, Run("p.diff", "f.txt", stderr="nonempty")))
    scns.append(scn("empty patch changes nothing", {"f.txt": F(lines(a)), "p.diff": F("--- a/f.txt\n+++ b/f.txt\n")}, Run("p.diff", "f.txt")))
    return ex, scns


# ------------------------------------------------------------------------------------------------ 6. shortest routes

REF_ROUTE = dd(r'''
    # route.awk : shortest routes in an undirected weighted graph, lexicographically smallest among the shortest
    function str(x) { return x "" }
    function dijkstra(src,   n, u, best, v, m, i, nbs) {
      delete dist; delete seen
      for (n in node) dist[n] = -1
      dist[src] = 0
      while (1) {
        u = ""; best = -1
        for (n in node) if (!(n in seen) && dist[n] >= 0 && (best < 0 || dist[n] < best)) { best = dist[n]; u = n }
        if (best < 0) break
        seen[u] = 1
        m = split(nb[u], nbs, " ")
        for (i = 1; i <= m; i++) {
          v = nbs[i]
          if (dist[v] < 0 || dist[u] + W[u, v] < dist[v]) dist[v] = dist[u] + W[u, v]
        }
      }
    }
    /^[ \t]*(#|$)/ { next }
    $1 == "?" && NF == 3 { nq++; qa[nq] = $2; qb[nq] = $3; next }
    NF == 3 && $3 ~ /^[0-9]+$/ && $3 + 0 > 0 {
      a = $1; b = $2; w = $3 + 0
      node[a] = 1; node[b] = 1
      if (a == b) next
      if (!((a, b) in W)) { nb[a] = nb[a] " " b; nb[b] = nb[b] " " a; W[a, b] = w; W[b, a] = w }
      else if (w < W[a, b]) { W[a, b] = w; W[b, a] = w }
      next
    }
    { bad = 1 }
    END {
      if (bad) { print "bad input" > "/dev/stderr"; exit 2 }
      for (q = 1; q <= nq; q++) {
        a = qa[q]; b = qb[q]
        if (!(a in node)) { print a " to " b ": unknown node " a; continue }
        if (!(b in node)) { print a " to " b ": unknown node " b; continue }
        dijkstra(b)
        if (dist[a] < 0) { print a " to " b ": unreachable"; continue }
        path = a; u = a
        while (u != b) {
          m = split(nb[u], nbs, " "); pick = ""
          for (i = 1; i <= m; i++) {
            v = nbs[i]
            if (dist[v] >= 0 && W[u, v] + dist[v] == dist[u] && (pick == "" || str(v) < str(pick))) pick = v
          }
          path = path ">" pick; u = pick
        }
        print a " to " b ": " dist[a] " via " path
      }
    }
''')

DOC_ROUTE = doc(r'''
    `awk -f route.awk` reads an undirected weighted graph and route questions from standard input and answers every question.

    * `A B W` is a road between the places `A` and `B` of length `W` (a positive integer; roads can be used in both directions). Place names are words without blanks. If the same pair appears again, the **shortest** length wins. A road from a place to itself is ignored (but the place exists).
    * `? A B` is a question: the shortest route from `A` to `B`. Questions are answered after the whole input has been read, in the order they were asked, so roads that come later in the input count too.
    * Blank lines and lines starting with `#` are ignored. Any other line (zero or non-numeric length, wrong number of fields) prints `bad input` on standard error and the script exits with status 2 without any output.
    * Every question prints one line: `A to B: D via P` where `D` is the total length and `P` the places of the route joined with `>` (`a>c>b`), or `A to B: unreachable`, or `A to B: unknown node X` for the first of `A`, `B` that is not a place of any road (`A to A: 0 via A` for a known place).
      When several routes have the shortest length, take the one whose place sequence is smallest: at every step go to the **smallest place name in byte order** from which the shortest length can still be reached (names are compared as text, so `10` comes before `9`).
''')


def make_route(rng):
    ex = scn("example", {}, Run(stdin="a b 4\na c 2\nc b 2\n? a b\n"))

    def graph(n):
        names = rng.sample(["harbour", "mill", "ridge", "quarry", "ford", "abbey", "kiln", "weir", "moor", "tarn", "glen", "fen"], n)
        rows = []
        for i in range(n):
            for j in range(i + 1, n):
                if rng.random() < 0.3:
                    rows.append(f"{names[i]} {names[j]} {rng.randint(1, 6)}")
        # a connected spine so that most questions have an answer
        rows += [f"{names[i]} {names[i + 1]} {rng.randint(2, 7)}" for i in range(n - 1) if rng.random() < 0.8]
        # ties: two equally long routes through places named 10 and 9, and one through z-places listed in a non-alphabetical order
        rows += [f"{names[0]} 9 1", f"9 {names[-1]} 1", f"{names[0]} 10 1", f"10 {names[-1]} 1", f"{names[0]} zeta 1", f"zeta {names[-1]} 1", f"{names[0]} alpha 1", f"alpha {names[-1]} 1"]
        rows += ["# comment", "", f"{names[1]} {names[1]} 3", "isle1 isle2 5", f"{names[2]} {names[3]} 9", f"{names[2]} {names[3]} 1"]
        rng.shuffle(rows)
        qs = [f"? {names[0]} {names[-1]}", f"? {names[-1]} {names[0]}", f"? {names[1]} {names[3]}", f"? {names[2]} {names[3]}", f"? {names[0]} isle1", f"? isle1 isle2", f"? {names[0]} nowhere", f"? nowhere {names[0]}", f"? {names[4]} {names[4]}", "? 10 9", f"? 9 {names[1]}"]
        out = rows[: len(rows) // 2] + qs[:5] + rows[len(rows) // 2:] + qs[5:]
        return lines(out)
    return ex, [scn("graph one", {}, Run(stdin=graph(9))), scn("graph two", {}, Run(stdin=graph(7))), scn("small", {}, Run(stdin="x y 1\n? x y\n? y x\n? x q\n")),
                scn("bad lines", {}, Run(stdin="a b 1\na b 0\n? a b\n", stderr="nonempty"), Run(stdin="a b\n", stderr="nonempty"), Run(stdin="a b 1 2\n", stderr="nonempty")), scn("empty", {}, Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ family

def rep(text, a, b):
    assert a in text, a
    return text.replace(a, b)


SPECS = [
    S("exact-big-integer-sums", 4, "Write `bigcalc.awk`: add and subtract arbitrarily long non-negative integers given as digit strings, one calculation per line, exactly. Read README.md." + NOTE, DOC_BIG, REF_BIG, make_big,
      script="bigcalc.awk", runner=RUN, title="Exact arithmetic on digit strings", tags=("awk",),
      wrong=("{ print $1 + 0 == 0 ? \"error\" : ($2 == \"+\" ? $1 + $3 : $1 - $3) }\n",
             rep(REF_BIG, 'else print "-" sub_(b, a)', 'else print sub_(b, a)'))),
    S("quoted-csv-records-to-tsv", 5, "Write `qcsv2tsv.awk`: turn CSV records, including quoted fields with commas, doubled quotes and line breaks inside, into one TSV line per record. Read README.md." + NOTE, DOC_QCSV, REF_QCSV, make_qcsv,
      script="qcsv2tsv.awk", runner=RUN, title="Quoted CSV to TSV", tags=("awk", "csv"),
      wrong=(rep(REF_QCSV, 'else if (c == "\\n") r = r "\\\\n"', 'else if (c == "\\n") r = r " "'), rep(REF_QCSV, "} else if (c == \"\\\"\" && start) { inq = 1; start = 0 }", "} else if (c == \"\\\"\") { inq = 1; start = 0 }"),
             "BEGIN { FS = \",\"; OFS = \"\\t\" } { gsub(/\"/, \"\"); $1 = $1; print }\n")),
    S("rpn-line-calculator", 4, "Write `rpn.awk`: evaluate one reverse-Polish expression per input line, with the stack words `dup`, `drop`, `swap` and precise error lines. Read README.md." + NOTE, DOC_RPN, REF_RPN, make_rpn,
      script="rpn.awk", runner=RUN, title="RPN calculator", tags=("awk",),
      wrong=(rep(REF_RPN, 'r = a / b }', 'r = int(a / b) }'), rep(REF_RPN, 'if (err == "" && sp != 1) err = "expected one result, found " sp', 'if (err == "" && sp < 1) err = "expected one result, found " sp'),
             rep(REF_RPN, 'function fmt(x) { if (x == 0) x = 0; return sprintf("%.10g", x) }', 'function fmt(x) { return x }'))),
    S("alphabetical-topological-order", 4, "Write `order.awk`: print a dependency order for `A B` lines (A before B), always taking the alphabetically smallest available name, and report cycles. Read README.md." + NOTE, DOC_TOPO, REF_TOPO, make_topo,
      script="order.awk", runner=RUN, title="Topological order", tags=("awk",),
      wrong=(rep(REF_TOPO, "(pick == \"\" || n < pick)", "(pick == \"\" || n > pick)"), rep(REF_TOPO, 'print line\n    exit 1', 'exit 1'),
             rep(REF_TOPO, "NF == 2 {", "NF == 2 && $1 != $2 {"))),
    S("apply-unified-diff", 5, "Write `applydiff.awk PATCH ORIGINAL`: apply the hunks of a unified diff to a text file and print the result, or fail without output when a hunk does not match. Read README.md carefully." + NOTE, DOC_PATCH, REF_PATCH, make_diff,
      script="applydiff.awk", runner=RUN, title="Unified diff patcher", tags=("awk", "diff"),
      wrong=(rep(REF_PATCH, "start = (ol[h] == 0) ? os[h] + 1 : os[h]", "start = os[h]"), rep(REF_PATCH, 'if (pos > n || orig[pos] != txt[h, k]) fail("hunk " h " failed: line " pos " does not match")', 'if (pos > n) fail("hunk " h " failed")'),
             rep(REF_PATCH, 'ol[nh] = (a[2] == "" ? 1 : a[2] + 0)', 'ol[nh] = (a[2] == "" ? 0 : a[2] + 0)'))),
    S("shortest-routes-smallest-names", 5, "Write `route.awk`: answer shortest-route questions on an undirected weighted graph, choosing the route with the smallest place names when several are equally short. Read README.md carefully." + NOTE, DOC_ROUTE, REF_ROUTE, make_route,
      script="route.awk", runner=RUN, title="Shortest routes", tags=("awk", "graph"),
      wrong=(rep(REF_ROUTE, "function str(x) { return x \"\" }", "function str(x) { return x + 0 }"), rep(REF_ROUTE, "else if (w < W[a, b]) { W[a, b] = w; W[b, a] = w }", ""),
             rep(REF_ROUTE, '(pick == "" || str(v) < str(pick))', 'pick == ""'))),
]


for _s in SPECS:
    for _w in _s.wrong:
        assert _w != _s.ref, _s.slug


@family("shell-awk-algorithms", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="expert awk programs: exact digit-string arithmetic, multi-line quoted CSV records, an RPN calculator, alphabetical topological order with cycle reports, a unified-diff patcher")
def awk_algorithms(rng, n):
    return K.shell_tasks("shell-awk-algorithms", SPECS, rng, n)
