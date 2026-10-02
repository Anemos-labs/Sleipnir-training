"""Shell tasks: awk programs with exact expected output (POSIX awk; the tests run mawk): ledgers, sessions, joins, tables, wrapping, state machines."""
import random

from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec
RUN = ("awk", "-f")
NOTE = " Plain POSIX awk only (the tests run `awk -f`, which is mawk here): no gawk extensions such as `asort`, `gensub` or `strftime`."


def lines(rows):
    return "".join(r + "\n" for r in rows)


# ------------------------------------------------------------------------------------------------ 1. exact ledger

REF_LEDGER = dd('''
    # balance.awk : balances per account in exact cents
    function cents(s,   neg, p, w, f, n) {
      neg = 0
      if (substr(s, 1, 1) == "-") { neg = 1; s = substr(s, 2) }
      else if (substr(s, 1, 1) == "+") s = substr(s, 2)
      p = index(s, ".")
      if (p) { w = substr(s, 1, p - 1); f = substr(s, p + 1) } else { w = s; f = "" }
      f = substr(f "00", 1, 2)
      n = (w + 0) * 100 + (f + 0)
      return neg ? -n : n
    }
    function money(c,   sign) {
      sign = ""
      if (c < 0) { sign = "-"; c = -c }
      return sprintf("%s%d.%02d", sign, int(c / 100), c % 100)
    }
    /^[ \\t]*(#|$)/ { next }
    {
      if (!($2 in bal)) { names[++n] = $2; bal[$2] = 0 }
      bal[$2] += cents($3)
    }
    END {
      for (i = 2; i <= n; i++) {
        v = names[i]
        for (j = i - 1; j >= 1 && names[j] > v; j--) names[j + 1] = names[j]
        names[j + 1] = v
      }
      for (i = 1; i <= n; i++) print names[i], money(bal[names[i]])
    }
''')


def make_ledger(rng):
    ex = scn("example", {"l.txt": F("2031-01-01 cash 10.50\n2031-01-02 rent -7\n# comment\n\n2031-01-03 cash -0.25\n")}, Run("l.txt"))
    accts = ["cash", "rent", "food", "fx-fees", "tips", "Zeta"]

    def rows(n, tricky):
        out = []
        for i in range(n):
            a = rng.choice(accts)
            c = rng.choice([1, 5, 10, 20, 30, 99, 150, 1234, 50000, 700, 2500, 4000])
            sign = rng.choice(["-", "", "+"])
            if c % 100 == 0 and rng.random() < 0.5:
                amt = str(c // 100)
            elif c % 10 == 0 and rng.random() < 0.5:
                amt = f"{c / 100:.1f}"
            else:
                amt = f"{c / 100:.2f}"
            out.append(f"2031-02-{rng.randint(1, 28):02d} {a} {sign}{amt}")
        if tricky:  # float traps: sums that are not exactly representable, and accounts that end at exactly zero
            out += ["2031-03-01 trap 0.10", "2031-03-01 trap 0.20", "2031-03-01 trap -0.30", "2031-03-02 trap2 -0.10", "2031-03-02 trap2 -0.20", "2031-03-02 trap2 0.30",
                    "# a comment line", "", "  ", "2031-03-03 big 123456.78", "2031-03-03 big 0.01", "2031-03-04 neg -0.01"]
        return out
    return ex, [scn("many accounts", {"l.txt": F(lines(rows(30, True)))}, Run("l.txt")), scn("another ledger", {"a.txt": F(lines(rows(20, True)))}, Run("a.txt")),
                scn("empty and comments only", {"e.txt": F("# nothing\n\n")}, Run("e.txt"))]


# ------------------------------------------------------------------------------------------------ 2. sessions

REF_SESS = dd('''
    # sessions.awk : "USER EPOCH PAGE" -> one line per session "USER START END PAGES" (gap of more than 1800 s starts a new one)
    NF >= 3 { n++; u[n] = $1; t[n] = $2 + 0 }
    END {
      for (i = 1; i <= n; i++) idx[i] = i
      for (i = 2; i <= n; i++) {
        v = idx[i]
        for (j = i - 1; j >= 1 && (u[idx[j]] > u[v] || (u[idx[j]] == u[v] && t[idx[j]] > t[v])); j--) idx[j + 1] = idx[j]
        idx[j + 1] = v
      }
      for (k = 1; k <= n; k++) {
        i = idx[k]
        if (k == 1 || u[i] != cu || t[i] - last > 1800) {
          if (k > 1) print cu, start, last, pages
          cu = u[i]; start = t[i]; pages = 0
        }
        last = t[i]; pages++
      }
      if (n > 0) print cu, start, last, pages
    }
''')


def make_sess(rng):
    ex = scn("example", {}, Run(stdin="ann 1000 /a\nann 1100 /b\nann 5000 /a\nbob 1000 /x\n"))

    def ev(users, k):
        out = []
        for u in users:
            t = rng.randint(10 ** 6, 2 * 10 ** 6)
            for _ in range(rng.randint(3, k)):
                out.append(f"{u} {t} /p{rng.randint(1, 5)}")
                t += rng.choice([5, 60, 600, 1799, 1800, 1801, 1802, 3600, 20000])
        rng.shuffle(out)
        return lines(out)
    return ex, [scn("shuffled events", {}, Run(stdin=ev(["ann", "bob", "cy-1"], 9))), scn("gap boundaries", {}, Run(stdin="u 100 /a\nu 1900 /b\nu 3701 /c\nu 3701 /d\nv 5 /x\n")),
                scn("no input and junk", {}, Run(stdin=""), Run(stdin="only two\n\nx 5\nu 10 /a\n"))]


# ------------------------------------------------------------------------------------------------ 3. last record wins

REF_LAST = dd('''
    # latest.awk : print the last line seen for every key (first field), in order of first appearance
    NF == 0 { next }
    !($1 in last) { order[++n] = $1 }
    { last[$1] = $0 }
    END { for (i = 1; i <= n; i++) print last[order[i]] }
''')


def make_last(rng):
    ex = scn("example", {}, Run(stdin="a 1\nb 2\na 3\nc 4\nb 5\n"))
    keys = ["host-a", "host-b", "db1", "db2", "cache"]
    rows = [f"{rng.choice(keys)} {rng.choice(['up', 'down', 'degraded'])} load={rng.randint(0, 99)}  {rng.choice(['', 'extra  spaces', 'tail'])}".rstrip() for _ in range(30)]
    return ex, [scn("status feed", {}, Run(stdin=lines(rows))), scn("blank lines and single key", {}, Run(stdin="\n\nk 1\n\nk 2\n  \n")), scn("empty", {}, Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 4. histogram

REF_HIST = dd('''
    # histogram.awk w=WIDTH : one line per bucket between the lowest and the highest value: "LOW HIGH #####"
    function floor(x) { return (x == int(x) || x > 0) ? int(x) : int(x) - 1 }
    $1 ~ /^-?[0-9]+(\\.[0-9]+)?$/ {
      k = floor($1 / w)
      c[k]++
      if (!seen++ || k < lo) lo = k
      if (k > hi || seen == 1) hi = k
    }
    END {
      for (k = lo; seen && k <= hi; k++) {
        bar = ""
        for (i = 0; i < c[k]; i++) bar = bar "#"
        printf "%6d %6d %s\\n", k * w, (k + 1) * w, bar
      }
    }
''')


def make_hist(rng):
    ex = scn("example", {}, Run("w=10", stdin="3\n7\n12\n25\n29\n-4\n"))
    vals = [str(rng.choice([rng.randint(-35, 80), rng.randint(0, 30)])) + rng.choice(["", "", ".5", ".25"]) for _ in range(60)]
    return ex, [scn("width 10", {}, Run("w=10", stdin=lines(vals))), scn("width 7 and 1", {}, Run("w=7", stdin=lines(vals[:25])), Run("w=1", stdin="3\n3\n5\n3\n")),
                scn("negatives, boundaries, junk", {}, Run("w=5", stdin="-5\n-4.9\n-0.1\n0\n4.9\n5\nabc\n\n-10\n10 extra\n"), Run("w=5", stdin=""), Run("w=5", stdin="x\ny\n"), Run("w=100", stdin="1\n99\n100\n"))]


# ------------------------------------------------------------------------------------------------ 5. join two files

REF_JOIN = dd('''
    # owners.awk pets.txt visits.txt : total fee per owner (exact cents); visits of unknown pets under "(unknown)" last
    function cents(s,   p, w, f) {
      p = index(s, ".")
      if (p) { w = substr(s, 1, p - 1); f = substr(s, p + 1) } else { w = s; f = "" }
      f = substr(f "00", 1, 2)
      return (w + 0) * 100 + (f + 0)
    }
    function money(c) { return sprintf("%d.%02d", int(c / 100), c % 100) }
    FNR == 1 { fileno++ }
    /^[ \\t]*(#|$)/ { next }
    fileno == 1 { owner[$1] = $2; next }
    {
      if ($1 in owner) {
        o = owner[$1]
        if (!(o in tot)) { names[++n] = o; tot[o] = 0 }
        tot[o] += cents($2)
      } else { unk += cents($2); hasunk = 1 }
    }
    END {
      for (i = 2; i <= n; i++) {
        v = names[i]
        for (j = i - 1; j >= 1 && names[j] > v; j--) names[j + 1] = names[j]
        names[j + 1] = v
      }
      for (i = 1; i <= n; i++) print names[i], money(tot[names[i]])
      if (hasunk) print "(unknown)", money(unk)
    }
''')


def make_join(rng):
    ex = scn("example", {"pets.txt": F("p1 Ruth\np2 Omar\n"), "visits.txt": F("p1 20.50\np2 15\np1 4.5\np9 3.25\n")}, Run("pets.txt", "visits.txt"))
    pets = [f"p{i} {n}" for i, n in enumerate(["Ruth", "Omar", "Ruth", "Ines", "Zed"], 1)]
    vis = [f"p{rng.randint(1, 7)} {rng.choice(['20', '20.5', '7.25', '100.99', '0.05', '3'])}" for _ in range(30)]
    return ex, [scn("owners with several pets", {"pets.txt": F("# pets\n" + lines(pets)), "visits.txt": F(lines(vis) + "\n")}, Run("pets.txt", "visits.txt")),
                scn("only unknown pets", {"pets.txt": F("p1 A\n"), "visits.txt": F("p5 1.10\np6 2.20\n")}, Run("pets.txt", "visits.txt")),
                scn("no visits", {"pets.txt": F("p1 A\n"), "visits.txt": F("")}, Run("pets.txt", "visits.txt"))]


# ------------------------------------------------------------------------------------------------ 6. aligned table

REF_TABLE = dd('''
    # table.awk : align a TAB-separated table (first row = header)
    BEGIN { FS = "\\t" }
    {
      rows++
      if (NF > nf) nf = NF
      for (c = 1; c <= NF; c++) {
        cell[rows, c] = $c
        if (length($c) > w[c]) w[c] = length($c)
        if (rows > 1 && $c != "") {
          if ($c ~ /^-?[0-9]+(\\.[0-9]+)?$/) num[c]++; else txt[c]++
        }
      }
    }
    function pad(s, width, right,   n) {
      n = width - length(s)
      while (n-- > 0) s = right ? " " s : s " "
      return s
    }
    function line(r,   c, out, right) {
      out = ""
      for (c = 1; c <= nf; c++) {
        right = (num[c] > 0 && txt[c] == 0)
        out = out (c > 1 ? "  " : "") pad(cell[r, c], w[c], right)
      }
      sub(/ +$/, "", out)
      return out
    }
    END {
      if (!rows) exit
      print line(1)
      u = ""
      for (c = 1; c <= nf; c++) { d = ""; for (i = 0; i < w[c]; i++) d = d "-"; u = u (c > 1 ? "  " : "") d }
      print u
      for (r = 2; r <= rows; r++) print line(r)
    }
''')


def make_table(rng):
    tab = "\t"
    ex = scn("example", {}, Run(stdin=f"item{tab}qty{tab}note\nbolt{tab}12{tab}zinc\nwasher{tab}1500{tab}\n"))
    names = ["bolt", "washer", "nut (M6)", "spring", "o-ring"]
    rows = [f"{rng.choice(names)}{tab}{rng.choice(['3', '12', '1500', '-7', '0.5', '12.25'])}{tab}{rng.choice(['zinc', '', 'steel plate', 'x'])}{tab}{rng.choice(['10', '', '2.5'])}" for _ in range(8)]
    return ex, [scn("mixed columns", {}, Run(stdin=f"item{tab}qty{tab}note{tab}price\n" + lines(rows))), scn("ragged and empty", {}, Run(stdin=f"a{tab}b\n1\n{tab}2{tab}3\n"), Run(stdin=""), Run(stdin=f"only header\n")),
                scn("text column with numbers inside", {}, Run(stdin=f"id{tab}code\n1{tab}10\n2{tab}A10\n3{tab}20\n"))]


# ------------------------------------------------------------------------------------------------ 7. job states

REF_JOBS = dd('''
    # jobs.awk : "HH:MM:SS JOB EVENT [CODE]" -> "JOB STATUS DURATION" sorted by job
    function secs(t,   a) { split(t, a, ":"); return a[1] * 3600 + a[2] * 60 + a[3] }
    NF >= 3 {
      j = $2
      if (!(j in seen)) { seen[j] = 1; names[++n] = j }
      if ($3 == "start") { st[j] = secs($1); has[j] = 1 }
      else if ($3 == "end" || $3 == "fail") {
        en[j] = secs($1); res[j] = ($3 == "end") ? "ok" : "failed(" $4 ")"
      }
    }
    END {
      for (i = 2; i <= n; i++) {
        v = names[i]
        for (k = i - 1; k >= 1 && names[k] > v; k--) names[k + 1] = names[k]
        names[k + 1] = v
      }
      for (i = 1; i <= n; i++) {
        j = names[i]
        if (!(j in has)) print j, "orphan", "-"
        else if (!(j in res)) print j, "running", "-"
        else { d = en[j] - st[j]; if (d < 0) d += 86400; print j, res[j], d }
      }
    }
''')


def make_jobs(rng):
    ex = scn("example", {}, Run(stdin="10:00:00 etl start\n10:05:30 etl end\n10:06:00 mail start\n10:07:00 mail fail 3\n10:08:00 sync start\n"))
    ev = []
    for j in ["backup", "report", "etl-1", "etl-2", "purge", "sync", "mail", "zip"]:
        h = rng.randint(0, 23)
        m = rng.randint(0, 59)
        ev.append((h * 3600 + m * 60, j, "start", ""))
        r = rng.random()
        if r < 0.5:
            ev.append((h * 3600 + m * 60 + rng.randint(1, 5000), j, "end", ""))
        elif r < 0.75:
            ev.append((h * 3600 + m * 60 + rng.randint(1, 5000), j, "fail", str(rng.randint(1, 9))))
    ev.append((12 * 3600, "ghost", "end", ""))
    ev.append((23 * 3600 + 3000, "night", "start", ""))
    ev.append((3 * 60, "night", "end", ""))
    ev.sort()
    txt = lines(f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d} {j} {e}" + (f" {c}" if c else "") for t, j, e, c in ev)
    return ex, [scn("mixed outcomes", {}, Run(stdin=txt)), scn("empty and noise", {}, Run(stdin=""), Run(stdin="# header\n\n09:00:00 a start\n09:00:01 a end\n"))]


# ------------------------------------------------------------------------------------------------ 8. wrap

REF_WRAP = dd('''
    # wrap.awk w=WIDTH : re-flow paragraphs to at most WIDTH columns (a longer word keeps a line to itself)
    function flush(   i, ln) {
      if (n == 0) return
      if (printed) print ""
      ln = ""
      for (i = 1; i <= n; i++) {
        if (ln == "") ln = word[i]
        else if (length(ln) + 1 + length(word[i]) <= w) ln = ln " " word[i]
        else { print ln; ln = word[i] }
      }
      print ln
      printed = 1
      n = 0
    }
    NF == 0 { flush(); next }
    { for (i = 1; i <= NF; i++) word[++n] = $i }
    END { flush() }
''')


def make_wrap(rng):
    ex = scn("example", {}, Run("w=20", stdin="the quick brown fox jumps over the lazy dog again and again\n"))
    text = ("Harbour lights flicker over the water while the last ferry noses into its berth.\n  The crew ties up, passengers shuffle off,\nand somebody counts the cars twice.\n\n\n"
            "supercalifragilisticexpialidocious is a long word\nshort\n\nlast paragraph here\n")
    return ex, [scn("widths", {}, Run("w=30", stdin=text), Run("w=12", stdin=text), Run("w=80", stdin=text), Run("w=1", stdin="a bb ccc\n")), scn("blank edges and empty", {}, Run("w=10", stdin="\n\n  \nhello   world  again\n\n\n"), Run("w=10", stdin=""))]


# ------------------------------------------------------------------------------------------------ 9. top two per group

REF_TOP = dd('''
    # top2.awk : "GROUP SCORE NAME" -> the two best per group: "GROUP RANK NAME SCORE" (score desc, name asc), groups sorted
    NF >= 3 && $2 ~ /^-?[0-9]+(\\.[0-9]+)?$/ {
      g = $1
      if (!(g in cnt)) { groups[++ng] = g; cnt[g] = 0 }
      k = ++cnt[g]
      sc[g, k] = $2 + 0; raw[g, k] = $2; nm[g, k] = $3
    }
    function better(g, a, b) {
      if (sc[g, a] != sc[g, b]) return sc[g, a] > sc[g, b]
      return nm[g, a] < nm[g, b]
    }
    END {
      for (i = 2; i <= ng; i++) {
        v = groups[i]
        for (j = i - 1; j >= 1 && groups[j] > v; j--) groups[j + 1] = groups[j]
        groups[j + 1] = v
      }
      for (i = 1; i <= ng; i++) {
        g = groups[i]
        for (r = 1; r <= 2 && r <= cnt[g]; r++) {
          best = 0
          for (k = 1; k <= cnt[g]; k++) {
            if (used[g, k]) continue
            if (best == 0 || better(g, k, best)) best = k
          }
          used[g, best] = 1
          print g, r, nm[g, best], raw[g, best]
        }
      }
    }
''')


def make_top(rng):
    ex = scn("example", {}, Run(stdin="red 5 ann\nred 9 bob\nblue 7 cy\nred 9 abe\n"))
    rows = [f"{rng.choice(['north', 'south', 'east', 'west-2'])} {rng.choice(['10', '7.5', '7.50', '9', '-1', '10', '0'])} {rng.choice(['ann', 'bob', 'cy', 'dee', 'eli', 'fay', 'gus'])}" for _ in range(30)]
    return ex, [scn("ties and decimals", {}, Run(stdin=lines(rows))), scn("single member groups and junk", {}, Run(stdin="solo 3 x\nname only\nbad abc y\nduo 1 a\nduo 1 b\nduo 1 c\n")), scn("empty", {}, Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 10. hourly buckets

REF_HOURLY = dd('''
    # hourly.awk : "YYYY-MM-DDTHH:MM:SS VALUE" -> one line per hour from the first to the last hour: "HOUR COUNT AVG"
    function hnum(h,   y, m, d, a) {
      split(h, a, /[-T]/)
      return days(a[1], a[2], a[3]) * 24 + a[4]
    }
    function days(y, m, d,   i, n, dim) {
      split("31 28 31 30 31 30 31 31 30 31 30 31", dim, " ")
      n = (y - 1970) * 365 + int((y - 1969) / 4) - int((y - 1901) / 100) + int((y - 1601) / 400)
      for (i = 1; i < m; i++) n += dim[i] + (i == 2 && (y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)))
      return n + d - 1
    }
    function hname(n,   dd, y, m, h, dim, i, leap) {
      h = n % 24; dd = int(n / 24)
      y = 1970
      while (1) {
        leap = (y % 4 == 0 && (y % 100 != 0 || y % 400 == 0))
        if (dd < 365 + leap) break
        dd -= 365 + leap; y++
      }
      split("31 28 31 30 31 30 31 31 30 31 30 31", dim, " ")
      for (m = 1; m <= 12; m++) {
        i = dim[m] + (m == 2 && leap)
        if (dd < i) break
        dd -= i
      }
      return sprintf("%04d-%02d-%02dT%02d", y, m, dd + 1, h)
    }
    $1 ~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:/ && $2 ~ /^-?[0-9]+$/ {
      k = hnum(substr($1, 1, 13))
      cnt[k]++; sum[k] += $2
      if (!seen++ || k < lo) lo = k
      if (k > hi || seen == 1) hi = k
    }
    END {
      for (k = lo; seen && k <= hi; k++) {
        if (cnt[k]) printf "%s %d %.2f\\n", hname(k), cnt[k], sum[k] / cnt[k]
        else printf "%s 0 -\\n", hname(k)
      }
    }
''')


def make_hourly(rng):
    ex = scn("example", {}, Run(stdin="2031-05-01T10:15:00 4\n2031-05-01T10:45:00 6\n2031-05-01T12:00:00 9\n"))
    ev = []
    for h in [0, 1, 4, 5, 22, 23]:
        for _ in range(rng.choice([1, 2, 3, 5, 6, 7])):
            ev.append(f"2031-12-31T{h:02d}:{rng.randint(0, 59):02d}:00 {rng.randint(-20, 100)}")
    for h in [0, 1, 2, 7]:
        for _ in range(rng.choice([1, 3, 5])):
            ev.append(f"2032-01-01T{h:02d}:{rng.randint(0, 59):02d}:30 {rng.randint(0, 50)}")
    rng.shuffle(ev)
    leap = lines(["2032-02-28T23:10:00 5", "2032-02-29T00:20:00 6", "2032-03-01T00:05:00 7"])
    return ex, [scn("across the new year", {}, Run(stdin=lines(ev))), scn("leap day", {}, Run(stdin=leap)), scn("junk and empty", {}, Run(stdin="x y\n2031-01-01T01:00:00 abc\n2031-01-01T01:00:00 3\n"), Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 11. key=value parser

REF_KV = dd('''
    # kv.awk : parse "key=value; key2="quoted; text"" lines -> "LINE<TAB>KEY<TAB>VALUE"
    /^[ \\t]*(#|$)/ { next }
    {
      s = $0; n = length(s); i = 1
      while (i <= n) {
        while (i <= n && substr(s, i, 1) ~ /[ \\t;]/) i++
        if (i > n) break
        key = ""
        while (i <= n && substr(s, i, 1) != "=" && substr(s, i, 1) != ";") { key = key substr(s, i, 1); i++ }
        sub(/[ \\t]+$/, "", key)
        val = ""
        if (substr(s, i, 1) == "=") {
          i++
          while (i <= n && substr(s, i, 1) ~ /[ \\t]/) i++
          if (substr(s, i, 1) == "\\"") {
            i++
            while (i <= n && substr(s, i, 1) != "\\"") {
              if (substr(s, i, 1) == "\\\\" && i < n) i++
              val = val substr(s, i, 1); i++
            }
            i++
            while (i <= n && substr(s, i, 1) != ";") i++
          } else {
            while (i <= n && substr(s, i, 1) != ";") { val = val substr(s, i, 1); i++ }
            sub(/[ \\t]+$/, "", val)
          }
        }
        printf "%d\\t%s\\t%s\\n", NR, key, val
      }
    }
''')


def make_kv(rng):
    ex = scn("example", {}, Run(stdin='host=db1; mode="a;b"; retries=3\n'))
    txt = ('# settings\nname = Harbour Lights ;  greeting="Hello; \\"World\\""; empty=; flag\n\n  a=1;b=2;;c = "x y" ;\n'
           'path=/usr/local/bin; msg="unterminated\n=novalue; k=v=w; semi="end;"; ünï=ça va\n')
    return ex, [scn("quoting rules", {}, Run(stdin=txt)), scn("empty", {}, Run(stdin=""), Run(stdin="# only\n\n"))]


# ------------------------------------------------------------------------------------------------ 12. fix stats

BUG_STATS = dd('''
    # stats.awk : per endpoint: count, min, max, average
    { c[$1]++; s[$1] += $2; if (c[$1] == 1 || $2 < mn[$1]) mn[$1] = $2; if ($2 > mx[$1]) mx[$1] = $2 }
    END { for (k in c) printf "%s %d %d %d %d\\n", k, c[k], mn[k], mx[k], s[k] / c[k] }
''')
REF_STATS = dd('''
    # stats.awk : per endpoint: count, min, max, average
    $2 ~ /^[0-9]+$/ {
      v = $2 + 0
      if (!($1 in c)) { names[++n] = $1; mn[$1] = v; mx[$1] = v }
      c[$1]++; s[$1] += v
      if (v < mn[$1]) mn[$1] = v
      if (v > mx[$1]) mx[$1] = v
    }
    END {
      for (i = 2; i <= n; i++) {
        x = names[i]
        for (j = i - 1; j >= 1 && names[j] > x; j--) names[j + 1] = names[j]
        names[j + 1] = x
      }
      for (i = 1; i <= n; i++) { k = names[i]; printf "%s %d %d %d %.1f\\n", k, c[k], mn[k], mx[k], s[k] / c[k] }
    }
''')


def make_stats(rng):
    ex = scn("example", {}, Run(stdin="/home 120\n/home 80\n/api 9\n"))
    rows = ["endpoint millis"]
    for ep, k in (("/home", 3), ("/api/v1/items", 5), ("/login", 6), ("/health", 9), ("/z", 1)):
        rows += [f"{ep} {rng.choice([5, 9, 10, 95, 100, 250, 1000, 12])}" for _ in range(k)]
    rows += ["bad -5", "alone", "/login abc"]
    rng.shuffle(rows)
    return ex, [scn("several endpoints", {}, Run(stdin=lines(rows))), scn("numbers that look alike", {}, Run(stdin="/a 9\n/a 10\n/a 100\n/b 1000\n/b 99\n")), scn("nothing usable", {}, Run(stdin=""), Run(stdin="header only\n"))]


SPECS = [
    S("exact-ledger-balances", 3,
      "Write `balance.awk`: read a plain-text ledger and print each account's balance exactly (no floating-point surprises like `-0.00`)." + NOTE,
      "`awk -f balance.awk FILE` reads lines `DATE ACCOUNT AMOUNT` (whitespace separated; `AMOUNT` is an optionally signed number with at most two decimals, like `12`, `3.5`, `-0.07`, `+4.00`). Lines that are blank or start with `#` (after optional blanks) are ignored. "
      "For every account print `ACCOUNT BALANCE` with exactly two decimals, sorted by account name in byte order. The arithmetic must be exact to the cent: a balance of zero prints `0.00` (never `-0.00`), however the amounts add up (`0.10 + 0.20 - 0.30` is exactly zero).",
      REF_LEDGER, make_ledger, script="balance.awk", runner=RUN, title="Exact ledger balances", wrong=("{ s[$2] += $3 } END { for (k in s) printf \"%s %.2f\\n\", k, s[k] }",)),
    S("page-view-sessions", 4,
      "Write `sessions.awk`: group page views into sessions per user (a pause of more than half an hour starts a new one) and print one line per session." + NOTE,
      "`awk -f sessions.awk` reads lines `USER EPOCH PAGE` from standard input (in any order; `EPOCH` is a whole number of seconds). Per user, sort the views by time; a view starts a new session when it is **more than 1800 seconds** after the previous view of the same user "
      "(exactly 1800 continues the session). For every session print `USER START END PAGES` (first and last epoch, number of views). Sessions are ordered by user name (byte order) and then by start time. Lines with fewer than three fields are ignored.",
      REF_SESS, make_sess, script="sessions.awk", runner=RUN, title="Sessions from page views", wrong=("{ print $1, $2, $2, 1 }",)),
    S("latest-record-per-key", 2,
      "Write `latest.awk`: for each key (the first field) keep only the last line seen, but in the order the keys first appeared." + NOTE,
      "`awk -f latest.awk` reads lines from standard input. The key of a line is its first whitespace-separated field. For every key print the **last** line carrying that key, unchanged, and order the output by the first appearance of each key. Blank (or blank-only) lines are skipped.",
      REF_LAST, make_last, script="latest.awk", runner=RUN, title="Last record per key", wrong=("!seen[$1]++",)),
    S("text-histogram", 3,
      "Write `histogram.awk`: a text histogram of numbers with a bucket width given on the command line as `w=10`." + NOTE,
      "`awk -f histogram.awk w=WIDTH` (a positive integer given as a command-line assignment *before* the input) reads numbers, one per line (optionally negative, optionally with decimals); lines whose first field is not such a number are ignored. "
      "The bucket of a value `v` is `floor(v / WIDTH)`. Print one line for every bucket from the lowest to the highest occupied one (empty buckets in between included): `printf \"%6d %6d %s\\n\", LOW, HIGH, BAR` where `LOW` is `bucket*WIDTH`, `HIGH` is `LOW+WIDTH` and `BAR` is one `#` per value. No numbers: no output.",
      REF_HIST, make_hist, script="histogram.awk", runner=RUN, title="Text histogram", wrong=("{ c[int($1/w)]++ } END { for (k in c) print k }",)),
    S("join-pets-and-visits", 3,
      "Write `owners.awk`, which takes two files (pets and their owners, then visits with fees) and prints the total fee per owner." + NOTE,
      "`awk -f owners.awk pets.txt visits.txt`: the first file has lines `PETID OWNER`, the second `PETID FEE` (`FEE` with at most two decimals, like `20`, `7.5`, `0.05`). Blank lines and lines starting with `#` are ignored in both. "
      "Print `OWNER TOTAL` for every owner with at least one visit, `TOTAL` exact to the cent with two decimals, owners sorted by name in byte order; visits of pets that are not in the first file are added up under the name `(unknown)`, printed last. Owners without visits are not printed.",
      REF_JOIN, make_join, script="owners.awk", runner=RUN, title="Owners and visit fees", wrong=("{ print }",)),
    S("aligned-table", 3,
      "Write `table.awk` to pretty-print a TAB-separated table from stdin: aligned columns, a dashed line under the header, numbers right-aligned." + NOTE,
      "`awk -f table.awk` reads TAB-separated rows from standard input; the first row is the header. Output: every column padded to the width of its widest cell (header included); columns are separated by two spaces; after the header comes a line of dashes (one run per column, as wide as the column, separated like the columns); then the data rows. "
      "A column is *numeric* when all its non-empty data cells match `-?digits[.digits]` and it has at least one; numeric columns (header too) are right-aligned, all others left-aligned. Trailing spaces are never printed. Short rows are padded with empty cells. Empty input: no output.",
      REF_TABLE, make_table, script="table.awk", runner=RUN, title="Aligned table", wrong=("{ print }",)),
    S("job-log-states", 4,
      "Write `jobs.awk`: summarise a job log into one line per job with its outcome and duration." + NOTE,
      "`awk -f jobs.awk` reads lines `HH:MM:SS JOB EVENT [CODE]` from standard input; `EVENT` is `start`, `end` or `fail` (a `fail` has a numeric `CODE`). Print `JOB STATUS DURATION` for every job, sorted by job name in byte order: "
      "status `ok` (it started and ended), `failed(CODE)` (it started and failed), `running` (started, no outcome yet: duration `-`) or `orphan` (an outcome without a start: duration `-`). `DURATION` is the whole number of seconds between start and outcome; if the outcome's time is earlier than the start's the job ran past midnight, add 24 hours. "
      "Each job appears once. Lines with fewer than three fields are ignored.",
      REF_JOBS, make_jobs, script="jobs.awk", runner=RUN, title="Job log states", wrong=("{ print $2 }",)),
    S("word-wrap-paragraphs", 3,
      "Write `wrap.awk` which re-flows text to a given width (`w=NN`) and keeps paragraph breaks." + NOTE,
      "`awk -f wrap.awk w=WIDTH` reads text from standard input. Paragraphs are separated by one or more blank (or blank-only) lines. Each paragraph is re-flowed greedily: words (separated by any amount of whitespace, line breaks included) are put on a line separated by single spaces "
      "while the line stays at most `WIDTH` characters; a word longer than `WIDTH` gets a line of its own. Paragraphs are separated in the output by exactly one empty line; no leading or trailing empty lines, no trailing spaces. Empty input: no output.",
      REF_WRAP, make_wrap, script="wrap.awk", runner=RUN, title="Re-flow paragraphs", wrong=("{ print }",)),
    S("best-two-per-group", 4,
      "Write `top2.awk`: for each group print its two highest scoring entries with their rank." + NOTE,
      "`awk -f top2.awk` reads lines `GROUP SCORE NAME` (score: optionally negative number, possibly with decimals; lines with fewer than three fields or a non-numeric score are ignored). For every group, in byte order of the group name, print up to two lines `GROUP RANK NAME SCORE` "
      "with `RANK` 1 and 2, ordered by score descending (numeric comparison, so `7.5` equals `7.50`) and names ascending (byte order) on equal scores. `SCORE` is printed exactly as it appears in the input.",
      REF_TOP, make_top, script="top2.awk", runner=RUN, title="Best two per group", wrong=("{ print $1, 1, $3, $2 }",)),
    S("hourly-buckets", 4,
      "Write `hourly.awk`: bucket timestamped readings by hour and print count and average per hour, including the empty hours in between." + NOTE,
      "`awk -f hourly.awk` reads lines `YYYY-MM-DDTHH:MM:SS VALUE` (integer value, possibly negative; other lines are ignored). For every hour from the earliest to the latest hour seen (calendar-correct: month ends, new year and leap days), print `YYYY-MM-DDTHH COUNT AVG` where `AVG` is the mean with two decimals (`%.2f`; the tests avoid exact rounding ties); "
      "hours without readings print `HOUR 0 -`. No readings: no output. You must do the date arithmetic yourself (no `mktime`/`strftime`).",
      REF_HOURLY, make_hourly, script="hourly.awk", runner=RUN, title="Hourly buckets", wrong=("{ print substr($1, 1, 13) }",)),
    S("quoted-key-values", 4,
      "Write `kv.awk`: a small parser for configuration lines such as `host=db1; mode=\"a;b\"; retries=3` that prints one tab-separated line per pair." + NOTE,
      "`awk -f kv.awk` reads lines of `key=value` pairs separated by `;` (blank lines and lines starting with `#` are ignored). Whitespace around keys, `=` and `;` is ignored. A value is either bare (up to the next `;`, trailing blanks removed) or double-quoted: inside quotes `;` and `=` are ordinary characters, `\\\"` is a quote and `\\\\` a backslash; "
      "text after the closing quote up to the next `;` is ignored, and an unterminated quote runs to the end of the line. A pair without `=` has an empty value; empty segments (`;;`) produce nothing. For every pair print `LINENO`, a TAB, `KEY`, a TAB, `VALUE` (the unquoted value), `LINENO` being the input line number (comment lines count).",
      REF_KV, make_kv, script="kv.awk", runner=RUN, title="Quoted key=value parser", wrong=("{ print NR \"\\t\" $0 }",)),
    S("fix-endpoint-stats", 2,
      "`stats.awk` should print count, minimum, maximum and average per endpoint, but its output order is random, the average is truncated and the header line pollutes the numbers. Fix it." + NOTE,
      "`awk -f stats.awk` reads lines `ENDPOINT MILLIS` from standard input. Lines whose second field is not a non-negative integer (a header, junk, missing fields) are ignored. For every endpoint print `ENDPOINT COUNT MIN MAX AVG` where `AVG` has one decimal (`%.1f`; the tests avoid exact ties); "
      "endpoints are sorted by name in byte order. No usable line: no output.",
      REF_STATS, make_stats, script="stats.awk", runner=RUN, buggy=BUG_STATS, title="Endpoint statistics", wrong=(BUG_STATS,)),
]


@family("shell-awk-programs", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="awk programs with exact output: ledgers in cents, sessions, joins, aligned tables, wrapping, job logs, quoted key=value parsing")
def awk_programs(rng, n):
    return K.shell_tasks("awk-programs", SPECS, rng, n)
