"""Shell tasks, expert level: a spreadsheet evaluator in awk, a carry-propagating number incrementer in sed, a JSON patch generator in jq, and a worker pool with atomic job claiming in bash."""
import json

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
    m = re.search("".join(parts), text)
    assert m, a
    return text[:m.start()] + b + text[m.end():]


# ------------------------------------------------------------------------------------------------ 1. spreadsheet

REF_SHEET = dd(r'''
    # sheet.awk : evaluate a comma-separated grid whose cells may hold formulas
    function trim(s) { sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); return s }
    function colnum(c) { return index("ABCDEFGHIJKLMNOPQRSTUVWXYZ", c) }
    function isnumtext(s) { return s ~ /^-?[0-9]+(\.[0-9]+)?$/ }
    function fmt(x) { if (x == 0) x = 0; return sprintf("%.10g", x) }
    function iserr(v) { return substr(v, 1, 1) == "#" }
    # value of cell (r, c): a number, "" for empty, "T:text" for text, or an error string
    function cell(r, c,   k, raw, v) {
      k = r SUBSEP c
      if (!(k in raw_)) return ""
      if (k in memo) return memo[k]
      raw = raw_[k]
      if (substr(raw, 1, 1) != "=") {
        if (raw == "") v = ""
        else if (isnumtext(raw)) v = raw + 0
        else v = "T:" raw
        memo[k] = v
        return v
      }
      if (k in busy) return "#CYCLE"
      busy[k] = 1
      v = evalformula(substr(raw, 2))
      delete busy[k]
      memo[k] = v
      return v
    }
    # ---- tokenizer + recursive descent over the global string S, position P
    function ws() { while (substr(S, P, 1) == " ") P++ }
    function parse_expr(   v, w, op) {
      v = parse_term()
      while (1) {
        ws(); op = substr(S, P, 1)
        if (op != "+" && op != "-") break
        P++
        w = parse_term()
        if (!iserr(v)) { if (iserr(w)) v = w; else v = (op == "+") ? v + w : v - w }
      }
      return v
    }
    function parse_term(   v, w, op) {
      v = parse_factor()
      while (1) {
        ws(); op = substr(S, P, 1)
        if (op != "*" && op != "/") break
        P++
        w = parse_factor()
        if (!iserr(v)) {
          if (iserr(w)) v = w
          else if (op == "*") v = v * w
          else if (w == 0) v = "#DIV/0"
          else v = v / w
        }
      }
      return v
    }
    function num(v) {            # operand of arithmetic
      if (iserr(v)) return v
      if (v == "") return 0
      if (substr(v, 1, 2) == "T:") return "#VALUE"
      return v
    }
    function parse_factor(   v, c, m, name, st, i, a, args) {
      ws(); c = substr(S, P, 1)
      if (c == "-") { P++; v = parse_factor(); v = num(v); return iserr(v) ? v : -v }
      if (c == "(") {
        P++; v = parse_expr(); ws()
        if (substr(S, P, 1) != ")") { PERR = 1; return 0 }
        P++
        return num(v)
      }
      if (match(substr(S, P), /^[0-9]+(\.[0-9]+)?/)) { v = substr(S, P, RLENGTH) + 0; P += RLENGTH; return v }
      if (match(substr(S, P), /^[A-Za-z_][A-Za-z_0-9]*/)) {
        name = substr(S, P, RLENGTH); P += RLENGTH
        ws()
        if (substr(S, P, 1) == "(") {
          P++
          return parse_call(name)
        }
        if (name ~ /^[A-Z][0-9]+$/) { return num(DRY ? 0 : cell(substr(name, 2) + 0, colnum(substr(name, 1, 1)))) }
        return DRY ? 0 : "#NAME"
      }
      PERR = 1
      return 0
    }
    # function call: arguments are expressions or ranges; accumulates values into list
    function parse_call(name,   n, v, first, a1, b1, r, c, r1, c1, r2, c2, i, j, x, err, cnt, sum, mn, mx, seen) {
      n = 0; err = ""; cnt = 0; sum = 0; seen = 0
      ws()
      if (substr(S, P, 1) == ")") { P++; return fin(name, 0, 0, 0, 0, "", DRY) }
      while (1) {
        ws()
        if (match(substr(S, P), /^[A-Z][0-9]+:[A-Z][0-9]+/)) {
          x = substr(S, P, RLENGTH); P += RLENGTH
          split(x, rg, ":")
          r1 = substr(rg[1], 2) + 0; c1 = colnum(substr(rg[1], 1, 1)); r2 = substr(rg[2], 2) + 0; c2 = colnum(substr(rg[2], 1, 1))
          if (r1 > r2) { t = r1; r1 = r2; r2 = t }
          if (c1 > c2) { t = c1; c1 = c2; c2 = t }
          if (!DRY) for (i = r1; i <= r2; i++) for (j = c1; j <= c2; j++) {
            v = cell(i, j)
            if (iserr(v)) { if (err == "") err = v }
            else if (v != "" && substr(v, 1, 2) != "T:") { cnt++; sum += v; if (!seen || v < mn) mn = v; if (!seen || v > mx) mx = v; seen = 1 }
          }
        } else {
          v = parse_expr()
          if (!DRY) {
            if (iserr(v)) { if (err == "") err = v }
            else { v = num(v); if (iserr(v)) { if (err == "") err = v } else { cnt++; sum += v; if (!seen || v < mn) mn = v; if (!seen || v > mx) mx = v; seen = 1 } }
          }
        }
        ws()
        if (substr(S, P, 1) == ";") { P++; continue }
        if (substr(S, P, 1) == ")") { P++; break }
        PERR = 1; return 0
      }
      return fin(name, cnt, sum, mn, mx, err, DRY)
    }
    function fin(name, cnt, sum, mn, mx, err, dry) {
      if (dry) return 0
      if (name != "SUM" && name != "MIN" && name != "MAX" && name != "AVG") return "#NAME"
      if (err != "") return err
      if (name == "SUM") return sum
      if (cnt == 0) return (name == "AVG") ? "#DIV/0" : 0
      if (name == "MIN") return mn
      if (name == "MAX") return mx
      return sum / cnt
    }
    function evalformula(f,   v) {
      S = f; P = 1; PERR = 0; DRY = 1
      parse_expr(); ws()
      if (PERR || P <= length(S)) return "#PARSE"
      S = f; P = 1; DRY = 0
      v = parse_expr()
      v = num(v)
      return v
    }
    {
      nr = NR
      n = split($0, parts, ",")
      if (n > nc) nc = n
      width[NR] = n
      for (i = 1; i <= n; i++) raw_[NR, i] = trim(parts[i])
    }
    END {
      for (r = 1; r <= nr; r++) {
        line = ""
        for (c = 1; c <= width[r]; c++) {
          raw = raw_[r, c]
          v = cell(r, c)
          if (substr(raw, 1, 1) == "=") out = iserr(v) ? v : fmt(v)
          else out = raw
          line = line (c > 1 ? "," : "") out
        }
        print line
      }
    }
''')

DOC_SHEET = dd(r'''
    `awk -f sheet.awk` reads a small spreadsheet from standard input and prints it with every formula replaced by its value. Plain POSIX awk only (the tests run mawk).

    **Grid.** One row per input line, cells separated by commas (there is no quoting, so a formula cannot contain a comma). Leading and trailing blanks of a cell are removed. Row `1` is the first line, column `A` the first cell; rows may have different lengths (the output keeps each row's number of cells; an empty line is an empty row).
    A cell is a **formula** when it starts with `=`; **numeric** when it is an optional minus sign, digits and optionally a dot with digits; otherwise **text**; or empty. Cells that are not formulas are printed unchanged (after trimming): `007` and `1.50` stay as they are.

    **Formulas.** Blanks between tokens are allowed. Grammar: `expr = term {(+|-) term}`, `term = factor {(*|/) factor}`, `factor = -factor | ( expr ) | number | CELL | FUNC( [arg {; arg}] )`, `arg = expr | RANGE`.
    A number is digits with an optional `.digits`. A `CELL` is one capital letter `A`-`Z` followed by digits (`B12`; a cell outside the grid is empty). A `RANGE` is `CELL:CELL`, the rectangle between the two corners in either order, allowed only as a function argument.
    The functions are `SUM`, `MIN`, `MAX` and `AVG`; arguments are separated by `;`. A numeric operand is its value; an empty cell counts as 0 in arithmetic and as a single-cell argument; **inside a range, empty and text cells are skipped**. `SUM` of nothing is 0, `MIN`/`MAX` of nothing are 0, `AVG` of nothing is `#DIV/0`.

    **Errors** are printed instead of the value: `#PARSE` for a syntax error (this wins over everything else in that formula: the whole formula must fit the grammar, any other word such as `a1`, `A` or `AA1` is fine syntactically), `#NAME` for a word that is not a cell reference or a function name, or an unknown function (whatever its arguments are),
    `#VALUE` for a text cell used as an operand (also as a single-cell argument or inside parentheses or after a minus sign), `#DIV/0` for a division by zero, `#CYCLE` for a cell that refers to itself or, directly or through other cells, depends on a cell that does.
    Evaluation goes from left to right (ranges row by row): the first error met is the result; an error in a cell makes every formula that uses the cell show the same error.

    **Output.** The evaluated grid, same layout, cells joined by commas. A numeric result is printed with `printf "%.10g"` (`0` instead of `-0`).
''')


def make_sheet(rng):
    ex = scn("example", {}, Run(stdin="item,qty,price,total\npens,4,1.5,=B2*C2\nsum,=SUM(B2:B2),,=SUM(D2:D2)\n"))
    def rows(k):
        q = [rng.randint(1, 9) for _ in range(3)]
        p = [rng.choice(["1.5", "2", "0.25", "7.75", "10"]) for _ in range(3)]
        r = ["name,qty,price,cost,note",
             f"alpha,{q[0]},{p[0]},=B2*C2,first",
             f"beta,{q[1]},{p[1]},=B3*C3,",
             f"gamma,{q[2]},{p[2]},=B4*C4,=D4-D2",
             "totals,=SUM(B2:B4),=AVG(C2:C4),=SUM(D2:D4),=MAX(D2:D4)-MIN(D2:D4)",
             "calc,=-(B2+B3)*2,= ( 1 + 2 ) * ( 3 - 1 ),=10/4,=SUM(B2:C3;5;-B4)",
             "range,=SUM(C4:B2),=MIN(A2:A4),=MAX(B2:B4;100),=AVG(A2:A4)",
             "text,=A2+1,=-A2,=(A2),=SUM(A2;B2)",
             "div,=1/0,=B2/(C2-C2),=AVG(A2:A3),=D8+1",
             "names,=a1,=FOO(1;2),=SUM(1;x),=Z99+Z98",
             "syntax,=(1+2,=1+,=SUM(1;;2),=2**3",
             "cycle,=C12,=B12,=B12+1,=E12",
             "deps,=B12+1,=D12*2,=D6+D8,=SUM(B12:D12)",
             "  spaced  ,  =  1 + 2  ,007,1.50",
             "empty refs,=Q3,=SUM(Q1:Q3),=MIN(Q3),=MAX(Q3:Q4)",
             ""]
        return r
    tail = ["x,=B1", "=SUM(", "=1 +", "=)", "=", "left over,=1+2),=3 4,=(1)(2),=A1 A2"]
    return ex, [scn("sheet one", {}, Run(stdin=lines(rows(0)))), scn("sheet two", {}, Run(stdin=lines(rows(1) + tail))),
                scn("tiny", {}, Run(stdin="=1\n=A1+1\n=A2*B1,3\n,,=A3\n")), scn("empty", {}, Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 2. sed: increment every number

REF_INC = dd(r'''
    s/^/\x01/
    :next
    /\x01[^0-9]*[0-9]/!bdone
    s/\x01([^0-9]*)([0-9]+)/\1\x02\2\x03\x01/
    :nines
    s/9(\x04*)\x03/\x04\1\x03/
    tnines
    s/\x02(\x04*)\x03/\x021\1\x03/
    tfin
    s/8(\x04*)\x03/9\1\x03/
    tfin
    s/7(\x04*)\x03/8\1\x03/
    tfin
    s/6(\x04*)\x03/7\1\x03/
    tfin
    s/5(\x04*)\x03/6\1\x03/
    tfin
    s/4(\x04*)\x03/5\1\x03/
    tfin
    s/3(\x04*)\x03/4\1\x03/
    tfin
    s/2(\x04*)\x03/3\1\x03/
    tfin
    s/1(\x04*)\x03/2\1\x03/
    tfin
    s/0(\x04*)\x03/1\1\x03/
    :fin
    s/\x02//
    s/\x03//
    s/\x04/0/g
    bnext
    :done
    s/\x01//
''')

DOC_INC = dd(r'''
    `sed -E -f increment.sed` adds one to **every number** in its input. A number is a maximal run of ASCII digits, wherever it stands (inside words, after a minus sign or a dot: `a9b` becomes `a10b`, `3.14` becomes `4.15`, `-5` becomes `-6` because the minus is an ordinary character).
    Leading zeros are kept as long as the number fits: `007` becomes `008`, `099` becomes `100`, `0099` becomes `0100`; only a carry out of the top digit makes it longer (`999` becomes `1000`, `0` becomes `1`). Numbers may have any number of digits (do not count on arithmetic).
    All other characters, including `@`, tabs, and empty lines, pass through unchanged. The input has no control characters. (GNU sed 4.9, extended regular expressions; `\x02`-style escapes are available.)
''')


def make_inc(rng):
    ex = scn("example", {}, Run(stdin="item 9, item 19\n"))
    txt = ["a9b 199 x 0099 007", "mail a@b.c 5 and 9@x", "3.14 -5 999", "no digits at all", "id_00 v2.0.9", "9", "", "tab\t7\t8", "0 1 2 3 4 5 6 7 8 9", "99999999999999999999999 123456789012345678901234567890", "x0y09z009", "12:59:59", "@@ 9 @@ 9@"]
    rng.shuffle(txt)
    return ex, [scn("mixed text", {}, Run(stdin=lines(txt))), scn("one line without newline at the end", {}, Run(stdin="v1.9 and 99")), scn("empty", {}, Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 3. jq: JSON patch

REF_PATCH = dd(r'''
    def esc: gsub("~"; "~0") | gsub("/"; "~1");
    def diff($p; $a; $b):
      if $a == $b then empty
      elif ($a | type) == "object" and ($b | type) == "object" then
        ((($a | keys) + ($b | keys)) | unique[]) as $k
        | ($p + "/" + ($k | esc)) as $q
        | if ($a | has($k) | not) then {op: "add", path: $q, value: $b[$k]}
          elif ($b | has($k) | not) then {op: "remove", path: $q}
          else diff($q; $a[$k]; $b[$k]) end
      elif ($a | type) == "array" and ($b | type) == "array" then
        ([($a | length), ($b | length)] | min) as $m
        | (range(0; $m) as $i | diff($p + "/" + ($i | tostring); $a[$i]; $b[$i])),
          (range($m; $b | length) as $i | {op: "add", path: ($p + "/" + ($i | tostring)), value: $b[$i]}),
          (range(($a | length) - 1; $m - 1; -1) as $i | {op: "remove", path: ($p + "/" + ($i | tostring))})
      else {op: "replace", path: $p, value: $b} end;
    [inputs] as [$a, $b] | [diff(""; $a; $b)]
''')

DOC_PATCH = dd(r'''
    `jq -n -c -f patch.jq OLD.json NEW.json` prints, as one compact JSON array, the list of operations that turns the document in `OLD.json` into the one in `NEW.json`, in the style of JSON Patch (RFC 6902) but with only `add`, `remove` and `replace` (jq 1.7; each file holds one JSON document, read with `inputs`).
    An operation is `{"op":"add","path":P,"value":V}`, `{"op":"remove","path":P}` or `{"op":"replace","path":P,"value":V}` (keys in that order). Paths are JSON Pointers: `""` is the root, a step is `/` followed by the object key or the array index, with `~` written `~0` and `/` written `~1` in keys.

    Compare `old` and `new` recursively; equal values (deep equality, key order does not matter, `1` equals `1.0`) give no operation. Otherwise:
    * both **objects**: go through the union of the keys in byte order of the key (jq's `keys` order); a key only in `new` gives an `add` of its value, a key only in `old` a `remove`, and a key in both is compared recursively;
    * both **arrays**: compare the elements at the indexes `0 .. min(length)-1` recursively, in this order; then one `add` per extra element of `new` (ascending index, at that index); then one `remove` per extra element of `old`, from the **last index down** to the first extra one (so the operations can be applied in the given order);
    * anything else (different types, or different scalars): one `replace` of the whole value at that path (at the root this is a path `""`).
    If the documents are equal the output is `[]`.
''')


def js(o):
    return json.dumps(o, ensure_ascii=False)


def _doc(rng, depth=0):
    kind = rng.random()
    if depth >= 3 or kind < 0.4:
        return rng.choice([1, 2, 3, 10, 1.5, "a", "b", "text here", True, False, None, "", 0])
    if kind < 0.7:
        keys = rng.sample(["name", "tags", "a/b", "~k", "z", "n", "Zed", "k 1", "é", "", "id", "items"], rng.randint(1, 4))
        return {k: _doc(rng, depth + 1) for k in keys}
    return [_doc(rng, depth + 1) for _ in range(rng.randint(0, 4))]


def _mutate(rng, d, depth=0):
    if isinstance(d, dict):
        out = {}
        for k, v in d.items():
            if rng.random() < 0.15:
                continue
            out[k] = _mutate(rng, v, depth + 1) if rng.random() < 0.6 else v
        if rng.random() < 0.4:
            out[rng.choice(["new", "x/y", "~t", "zz", "Added"])] = _doc(rng, 2)
        return out
    if isinstance(d, list):
        out = [_mutate(rng, v, depth + 1) if rng.random() < 0.5 else v for v in d]
        r = rng.random()
        if r < 0.3 and out:
            del out[rng.randrange(len(out))]
        elif r < 0.6:
            out.append(_doc(rng, 2))
        elif r < 0.7 and len(out) > 1:
            out = out[:-2]
        return out
    return d if rng.random() < 0.5 else rng.choice([7, "changed", None, [1], {"o": 1}, False])


def make_patch(rng):
    ex = scn("example", {"a.json": F(js({"n": 1, "tags": ["x", "y"]})), "b.json": F(js({"n": 2, "tags": ["x"], "new": True}))}, Run("-n", "-c", "a.json", "b.json"))
    scns = []
    for k in range(5):
        a = {"id": 1, "tags": ["a", "b", "c"], "a/b": {"~k": 1, "z": [1, 2]}, "n": 1}
        extra = _doc(rng)
        if isinstance(extra, dict):
            a.update(extra)
        else:
            a["extra"] = extra
        b = _mutate(rng, a)
        scns.append(scn(f"documents {k + 1}", {"old.json": F(js(a) + "\n"), "new file.json": F(js(b) + "\n")}, Run("-n", "-c", "old.json", "new file.json")))
    scns.append(scn("tricky keys and arrays", {"o.json": F('{"a/b":{"~k":1,"z":[1,2]},"gone":true,"n":1,"name":"x","tags":["a","b","c"],"deep":[[1,2],[3]]}'), "n.json": F('{"a/b":{"~k":2,"z":[1,2,3]},"n":1.0,"name":"y","new":null,"tags":["a","q"],"deep":[[1],[3,4],[5]]}')}, Run("-n", "-c", "o.json", "n.json")))
    scns.append(scn("equal and root changes", {"a.json": F('{"x":[1,2,{"y":null}]}'), "b.json": F('{"x":[1,2,{"y":null}]}'), "s1.json": F("1"), "s2.json": F('"1"'), "arr.json": F("[1,2,3]"), "arr2.json": F("[3]")},
                    Run("-n", "-c", "a.json", "b.json"), Run("-n", "-c", "s1.json", "s2.json"), Run("-n", "-c", "arr.json", "arr2.json"), Run("-n", "-c", "arr2.json", "arr.json"), Run("-n", "-c", "a.json", "s1.json")))
    return ex, scns


# ------------------------------------------------------------------------------------------------ 4. worker pool

REF_POOL = dd(r'''
    #!/usr/bin/env bash
    # pool.sh N : run the jobs of queue/ with N concurrent workers, each job exactly once
    { [ $# -eq 1 ] && [[ $1 =~ ^[1-9][0-9]*$ ]]; } || { echo "usage: pool.sh N" >&2; exit 2; }
    [ -d queue ] || { echo "error: no queue directory" >&2; exit 2; }
    mkdir -p running done failed out || exit 1
    tmp=$(mktemp -d) || exit 1
    trap 'rm -rf -- "$tmp"' EXIT
    : > "$tmp/ok"
    : > "$tmp/bad"
    worker() {
      local f name base mine
      for f in queue/*.job; do
        [ -e "$f" ] || continue
        name=$(basename -- "$f")
        base=${name%.job}
        mine=running/$name.$BASHPID
        mv -- "$f" "$mine" 2> /dev/null || continue
        if sh "$mine" > "out/$base.out" 2> "out/$base.err" < /dev/null; then
          mv -- "$mine" "done/$name"
          echo x >> "$tmp/ok"
        else
          mv -- "$mine" "failed/$name"
          echo x >> "$tmp/bad"
        fi
      done
    }
    for ((i = 0; i < $1; i++)); do
      worker &
    done
    wait
    nd=$(wc -l < "$tmp/ok")
    nf=$(wc -l < "$tmp/bad")
    echo "done: $nd failed: $nf"
    [ "$nf" -eq 0 ]
''')

DOC_POOL = dd(r'''
    `pool.sh N` runs the jobs waiting in the directory `queue/` with **N workers at the same time** (N a positive integer) and waits until the queue is empty.

    * Every file `queue/NAME.job` is a job: a shell script (run as `sh queue-file`, in the current directory, with standard input from `/dev/null`). Each job must be run **exactly once**, so a worker has to claim a job atomically (rename it; renaming a file that another worker just took fails).
      At every moment up to N jobs run in parallel, and when fewer than N jobs are left only that many run. Other files in `queue/` are ignored.
    * At the start create the directories `running/`, `done/`, `failed/` and `out/` if they are missing. While a worker runs a job its file is in `running/` under a name of your choice; when the job ends the file is moved to `done/NAME.job` (exit status 0) or `failed/NAME.job` (any other status), and `running/` is left empty.
      The standard output of the job goes to `out/NAME.out` and its standard error to `out/NAME.err` (both files exist, possibly empty). Jobs named like a previous run's overwrite the old results.
    * When all workers have finished it prints `done: A failed: B` (the numbers for **this run**) and exits with status 0 if B is 0, otherwise 1.
    * Wrong usage (the argument is missing, not a positive integer, or there is no `queue/` directory): message on standard error, exit status 2, nothing created.
''')


def make_pool(rng):
    ex = scn("example", {"queue/a.job": F("echo hello from a\n"), "queue/b.job": F("echo hello from b; exit 1\n")}, Run("2"))
    jobs = {f"queue/{n}.job": F(f"echo {n} >> log.txt\necho out-{n}\n") for n in ("alpha", "beta", "gamma", "delta", "eps", "zeta", "eta")}
    jobs["queue/has space.job"] = F("echo spaced >> log.txt\necho 'two words'\n")
    jobs["queue/fails.job"] = F("echo failing >> log.txt\necho oops >&2\nexit 3\n")
    jobs["queue/ignored.txt"] = F("not a job\n")
    barrier = "mkdir -p barrier\n: > barrier/b{n}\nwhile [ \"$(ls barrier | wc -l)\" -lt 3 ]; do sleep 0.05; done\necho passed {n}\n"
    bj = {f"queue/b{i}.job": F(barrier.format(n=i)) for i in (1, 2, 3)}
    bj.update({f"queue/c{i}.job": F(f"echo plain {i}\n") for i in (1, 2)})
    slot = "mkdir -p slots\nmkdir \"slots/$$\"\n[ \"$(ls slots | wc -l)\" -le 2 ] || echo violation >> violations.log\nsleep 0.25\nrmdir \"slots/$$\"\necho slot {n}\n"
    sj = {f"queue/s{i}.job": F(slot.format(n=i)) for i in range(1, 9)}
    return ex, [scn("every job exactly once", jobs, Run("3"), sorted_files=["log.txt"]),
                scn("N workers really run together", bj, Run("3")),
                scn("never more than N at once", sj, Run("2")),
                scn("a second run handles only the new jobs", {"queue/one.job": F("echo one >> log.txt\n"), "queue/two.job": F("echo two >> log.txt\nexit 2\n")},
                    Run("1"), Run("4", ops=[{"op": "write", "path": "queue/three.job", "c": "echo three >> log.txt\n"}, {"op": "write", "path": "queue/one.job", "c": "echo one-again >> log.txt\n"}]), sorted_files=["log.txt"]),
                scn("empty queue", {"queue/readme.txt": F("nothing here\n")}, Run("5")),
                scn("usage", {"queue/x.job": F("echo x >> log.txt\n")}, Run(stderr="nonempty"), Run("0", stderr="nonempty"), Run("two", stderr="nonempty"), Run("1", "2", stderr="nonempty")),
                scn("no queue", {}, Run("2", stderr="nonempty"))]


# ------------------------------------------------------------------------------------------------ family

SPECS = [
    S("spreadsheet-evaluator", 5, "Write `sheet.awk`: evaluate the formulas of a comma-separated spreadsheet (arithmetic, cell references, ranges, SUM/MIN/MAX/AVG) and print the grid with values, reporting errors and cycles the way README.md describes. Plain POSIX awk (mawk).", DOC_SHEET, REF_SHEET, make_sheet,
      script="sheet.awk", runner=("awk", "-f"), title="Spreadsheet evaluator", tags=("awk",),
      wrong=(rep(REF_SHEET, 'if (k in busy) return "#CYCLE"', 'if (k in busy) return 0'), rep(REF_SHEET, 'else if (w == 0) v = "#DIV/0"', 'else if (w == 0) v = 0'),
             rep(REF_SHEET, 'if (v != "" && substr(v, 1, 2) != "T:") { cnt++;', 'if (v != "" && substr(v, 1, 2) != "T:" || 1) { cnt++;'),
             rep(REF_SHEET, 'if (PERR || P <= length(S)) return "#PARSE"', 'if (PERR) return "#PARSE"'))),
    S("increment-every-number", 5, "Write `increment.sed`: add one to every number in the text, carrying through the digits with plain sed commands (no arithmetic available), keeping leading zeros. Read README.md.", DOC_INC, REF_INC, make_inc,
      script="increment.sed", runner=("sed", "-E", "-f"), title="Increment numbers with sed", tags=("sed",),
      wrong=("s/[0-9]+/&1/g\n", rep(REF_INC, "s/\\x04/0/g", "s/\\x04//g"), rep(REF_INC, "s/\\x02(\\x04*)\\x03/\\x021\\1\\x03/\ntfin", "s/\\x02(\\x04*)\\x03/\\x020\\1\\x03/\ntfin"))),
    S("json-patch-diff", 5, "Write `patch.jq`: compute the list of add/remove/replace operations that turn one JSON document into another, with the exact ordering rules of README.md.", DOC_PATCH, REF_PATCH, make_patch,
      script="patch.jq", runner=("jq", "-f"), title="JSON patch generator", tags=("jq",),
      wrong=(rep(REF_PATCH, "range(($a | length) - 1; $m - 1; -1)", "range($m; $a | length)"), rep(REF_PATCH, 'def esc: gsub("~"; "~0") | gsub("/"; "~1");', "def esc: .;"),
             rep(REF_PATCH, '{op: "add", path: $q, value: $b[$k]}', '{op: "replace", path: $q, value: $b[$k]}'))),
    S("bounded-worker-pool", 5, "Write `pool.sh N`: run the jobs in `queue/` with N parallel workers that claim jobs atomically, collect their results in `done/`, `failed/` and `out/` and print a summary. Read README.md.", DOC_POOL, REF_POOL, make_pool,
      script="pool.sh",
      wrong=(rep(REF_POOL, "worker &", "worker"), rep(REF_POOL, 'mv -- "$f" "$mine" 2> /dev/null || continue', 'cp -- "$f" "$mine" || continue'), rep(REF_POOL, "for ((i = 0; i < $1; i++)); do", "for ((i = 0; i < $1 * 2 + 1; i++)); do"),
             rep(REF_POOL, 'echo "done: $nd failed: $nf"\n[ "$nf" -eq 0 ]', 'echo "done: $nd failed: $nf"'))),
]


for _s in SPECS:
    for _w in _s.wrong:
        assert _w != _s.ref, _s.slug


@family("shell-expert-tools", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="expert tools: an awk spreadsheet evaluator with cycles and errors, a sed incrementer with carries, a jq JSON patch generator, a bash worker pool with atomic claiming")
def expert_tools(rng, n):
    return K.shell_tasks("shell-expert-tools", SPECS, rng, n)
