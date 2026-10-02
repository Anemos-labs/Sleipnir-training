"""boxtab: a CLI that draws delimited text as a bordered table with an invented option set (exact output)."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

WORDS = ["harbour", "ferry", "kelp", "tide", "lantern", "moor", "quay", "salt", "gull", "net", "oar", "buoy", "pier", "swell", "reef", "brine", "sail", "mast", "dock", "anchor"]
STYLE_NAMES = ["ascii", "dots", "tilde", "plain", "stars", "heavy", "thin"]
LANG_PLAN = ["bash", "python", "c", "go", "bash", "c", "go", "bash", "python", "c", "go", "bash"]
CTX = ["a ferry timetable", "the tide log", "an allotment rota", "a library shelf list", "a harbour fee sheet", "a lamp inventory"]


def params(rng, level, i):
    names = rng.sample(STYLE_NAMES, 3 if level >= 2 else 2)
    styles = {}
    for nm in names:
        styles[nm] = (rng.choice("+*.#o"), rng.choice("-=~._"), rng.choice("|:!I"), rng.choice("=-~#"))
    default = names[0]
    return {
        "level": level, "styles": styles, "default": default, "sep": [",", ";", "|", "\t"][(i + rng.randrange(4)) % 4], "ctx": rng.choice(CTX),
        "has_align": level >= 2, "has_pad": level >= 2, "has_max": level >= 3, "has_rules": level >= 3, "has_n": level >= 3,
    }


PY = r'''
import sys

STYLES = @STYLES_PY@
DEFAULT = "@DEFAULT@"
SEP = "@SEP@"
HAS_ALIGN = @ALIGN@
HAS_PAD = @PAD@
HAS_MAX = @MAX@
HAS_RULES = @RULES@
HAS_N = @N@
DG = "0123456789"


def is_num(s):
    body = s[1:] if s[:1] in "+-" else s
    if "." in body:
        a, b = body.split(".", 1)
        return a != "" and b != "" and all(c in DG for c in a + b)
    return body != "" and all(c in DG for c in body)


def main(argv):
    opts = {"style": DEFAULT, "header": "yes", "pad": "1", "rules": "edges", "align": "", "max": ""}
    seen = set()
    offered = {"style", "header"}
    if HAS_ALIGN:
        offered.add("align")
    if HAS_PAD:
        offered.add("pad")
    if HAS_MAX:
        offered.add("max")
    if HAS_RULES:
        offered.add("rules")
    for a in argv:
        if "=" not in a:
            return 2
        k, v = a.split("=", 1)
        if k not in offered or k in seen:
            return 2
        seen.add(k)
        if k == "style" and v not in STYLES:
            return 2
        if k == "header" and v not in ("yes", "no"):
            return 2
        if k == "rules" and v not in ("edges", "all"):
            return 2
        if k == "pad" and v not in ("0", "1", "2", "3"):
            return 2
        if k == "max" and not (1 <= len(v) <= 2 and all(c in DG for c in v) and int(v) >= 2):
            return 2
        if k == "align" and (v == "" or any(c not in ("lrcn" if HAS_N else "lrc") for c in v)):
            return 2
        opts[k] = v
    data = sys.stdin.read()
    if data.endswith("\n"):
        data = data[:-1]
    if data == "":
        return 1
    rows = [r.split(SEP) for r in data.split("\n")]
    if opts["max"]:
        m = int(opts["max"])
        rows = [[c if len(c) <= m else c[:m - 1] + "~" for c in r] for r in rows]
    nc = max(len(r) for r in rows)
    rows = [r + [""] * (nc - len(r)) for r in rows]
    widths = [max(len(r[j]) for r in rows) for j in range(nc)]
    corner, h, v, hh = STYLES[opts["style"]]
    pad = int(opts["pad"])
    al = opts["align"]

    def place(cell, j):
        a = al[j] if j < len(al) else "l"
        if a == "n":
            a = "r" if is_num(cell) else "l"
        room = widths[j] - len(cell)
        if a == "l":
            return cell + " " * room
        if a == "r":
            return " " * room + cell
        return " " * (room // 2) + cell + " " * (room - room // 2)

    def rule(ch):
        return corner + corner.join(ch * (w + 2 * pad) for w in widths) + corner

    def line(r):
        sp = " " * pad
        return v + v.join(sp + place(c, j) + sp for j, c in enumerate(r)) + v

    out = [rule(h)]
    header = opts["header"] == "yes"
    for i, r in enumerate(rows):
        out.append(line(r))
        if i == 0 and header:
            out.append(rule(hh))
        elif i < len(rows) - 1 and opts["rules"] == "all":
            out.append(rule(h))
    out.append(rule(h))
    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

GO = r'''
package main

import (
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"
)

const (
	defaultStyle = "@DEFAULT@"
	sepCh        = "@SEP@"
	hasAlign     = @ALIGN@
	hasPad       = @PAD@
	hasMax       = @MAX@
	hasRules     = @RULES@
	hasN         = @N@
)

var styles = @STYLES_GO@

func isDigits(s string) bool {
	if s == "" {
		return false
	}
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
	}
	return true
}

func isNum(s string) bool {
	body := s
	if strings.HasPrefix(s, "+") || strings.HasPrefix(s, "-") {
		body = s[1:]
	}
	if i := strings.IndexByte(body, '.'); i >= 0 {
		return isDigits(body[:i]) && isDigits(body[i+1:])
	}
	return isDigits(body)
}

func main() {
	os.Exit(run())
}

func run() int {
	opts := map[string]string{"style": defaultStyle, "header": "yes", "pad": "1", "rules": "edges", "align": "", "max": ""}
	offered := map[string]bool{"style": true, "header": true, "align": hasAlign, "pad": hasPad, "max": hasMax, "rules": hasRules}
	seen := map[string]bool{}
	for _, a := range os.Args[1:] {
		i := strings.IndexByte(a, '=')
		if i < 0 {
			return 2
		}
		k, v := a[:i], a[i+1:]
		if !offered[k] || seen[k] {
			return 2
		}
		seen[k] = true
		switch k {
		case "style":
			if _, ok := styles[v]; !ok {
				return 2
			}
		case "header":
			if v != "yes" && v != "no" {
				return 2
			}
		case "rules":
			if v != "edges" && v != "all" {
				return 2
			}
		case "pad":
			if v != "0" && v != "1" && v != "2" && v != "3" {
				return 2
			}
		case "max":
			n, _ := strconv.Atoi(v)
			if len(v) < 1 || len(v) > 2 || !isDigits(v) || n < 2 {
				return 2
			}
		case "align":
			allowed := "lrc"
			if hasN {
				allowed = "lrcn"
			}
			if v == "" || strings.Trim(v, allowed) != "" {
				return 2
			}
		}
		opts[k] = v
	}
	raw, _ := io.ReadAll(os.Stdin)
	data := strings.TrimSuffix(string(raw), "\n")
	if len(raw) > 0 && raw[len(raw)-1] != '\n' {
		data = string(raw)
	}
	if data == "" {
		return 1
	}
	var rows [][]string
	for _, line := range strings.Split(data, "\n") {
		rows = append(rows, strings.Split(line, sepCh))
	}
	if opts["max"] != "" {
		m, _ := strconv.Atoi(opts["max"])
		for _, r := range rows {
			for j, c := range r {
				if len(c) > m {
					r[j] = c[:m-1] + "~"
				}
			}
		}
	}
	nc := 0
	for _, r := range rows {
		if len(r) > nc {
			nc = len(r)
		}
	}
	for i, r := range rows {
		for len(r) < nc {
			r = append(r, "")
		}
		rows[i] = r
	}
	widths := make([]int, nc)
	for _, r := range rows {
		for j, c := range r {
			if len(c) > widths[j] {
				widths[j] = len(c)
			}
		}
	}
	st := styles[opts["style"]]
	corner, h, v, hh := st[0], st[1], st[2], st[3]
	pad, _ := strconv.Atoi(opts["pad"])
	al := opts["align"]
	place := func(cell string, j int) string {
		a := byte('l')
		if j < len(al) {
			a = al[j]
		}
		if a == 'n' {
			if isNum(cell) {
				a = 'r'
			} else {
				a = 'l'
			}
		}
		room := widths[j] - len(cell)
		switch a {
		case 'l':
			return cell + strings.Repeat(" ", room)
		case 'r':
			return strings.Repeat(" ", room) + cell
		}
		return strings.Repeat(" ", room/2) + cell + strings.Repeat(" ", room-room/2)
	}
	rule := func(ch string) string {
		parts := make([]string, nc)
		for j, w := range widths {
			parts[j] = strings.Repeat(ch, w+2*pad)
		}
		return corner + strings.Join(parts, corner) + corner
	}
	var out []string
	out = append(out, rule(h))
	header := opts["header"] == "yes"
	sp := strings.Repeat(" ", pad)
	for i, r := range rows {
		parts := make([]string, nc)
		for j, c := range r {
			parts[j] = sp + place(c, j) + sp
		}
		out = append(out, v+strings.Join(parts, v)+v)
		if i == 0 && header {
			out = append(out, rule(hh))
		} else if i < len(rows)-1 && opts["rules"] == "all" {
			out = append(out, rule(h))
		}
	}
	out = append(out, rule(h))
	fmt.Print(strings.Join(out, "\n") + "\n")
	return 0
}
'''

CC = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SEP '@SEP_C@'
#define DEFAULT_STYLE "@DEFAULT@"
#define HAS_ALIGN @ALIGN@
#define HAS_PAD @PAD@
#define HAS_MAX @MAX@
#define HAS_RULES @RULES@
#define HAS_N @N@

typedef struct { const char *name; char corner, h, v, hh; } Style;
static const Style STYLES[] = @STYLES_C@;
#define NSTYLES ((int)(sizeof STYLES / sizeof STYLES[0]))

static int all_digits(const char *s, size_t n) {
    if (n == 0) return 0;
    for (size_t i = 0; i < n; i++)
        if (s[i] < '0' || s[i] > '9') return 0;
    return 1;
}

static int is_num(const char *s) {
    if (*s == '+' || *s == '-') s++;
    const char *dot = strchr(s, '.');
    if (dot) return all_digits(s, (size_t)(dot - s)) && all_digits(dot + 1, strlen(dot + 1));
    return all_digits(s, strlen(s));
}

static void rep(char c, int n) {
    for (int i = 0; i < n; i++) putchar(c);
}

int main(int argc, char **argv) {
    const char *style = DEFAULT_STYLE, *header = "yes", *rules = "edges", *align = "";
    int pad = 1, max = 0;
    int seen[6] = {0, 0, 0, 0, 0, 0};
    const char *keys[6] = {"style", "header", "align", "pad", "max", "rules"};
    int offered[6] = {1, 1, HAS_ALIGN, HAS_PAD, HAS_MAX, HAS_RULES};
    for (int a = 1; a < argc; a++) {
        char *eq = strchr(argv[a], '=');
        if (!eq) return 2;
        size_t kl = (size_t)(eq - argv[a]);
        const char *v = eq + 1;
        int ki = -1;
        for (int k = 0; k < 6; k++)
            if (strlen(keys[k]) == kl && strncmp(argv[a], keys[k], kl) == 0) ki = k;
        if (ki < 0 || !offered[ki] || seen[ki]) return 2;
        seen[ki] = 1;
        if (ki == 0) {
            int ok = 0;
            for (int s = 0; s < NSTYLES; s++) if (strcmp(STYLES[s].name, v) == 0) ok = 1;
            if (!ok) return 2;
            style = v;
        } else if (ki == 1) {
            if (strcmp(v, "yes") != 0 && strcmp(v, "no") != 0) return 2;
            header = v;
        } else if (ki == 5) {
            if (strcmp(v, "edges") != 0 && strcmp(v, "all") != 0) return 2;
            rules = v;
        } else if (ki == 3) {
            if (strlen(v) != 1 || v[0] < '0' || v[0] > '3') return 2;
            pad = v[0] - '0';
        } else if (ki == 4) {
            size_t n = strlen(v);
            if (n < 1 || n > 2 || !all_digits(v, n) || atoi(v) < 2) return 2;
            max = atoi(v);
        } else {
            const char *allowed = HAS_N ? "lrcn" : "lrc";
            if (*v == 0) return 2;
            for (const char *p = v; *p; p++) if (!strchr(allowed, *p)) return 2;
            align = v;
        }
    }
    size_t cap = 4096, len = 0;
    char *buf = malloc(cap);
    size_t got;
    while ((got = fread(buf + len, 1, cap - len - 1, stdin)) > 0) {
        len += got;
        if (cap - len < 2) { cap *= 2; buf = realloc(buf, cap); }
    }
    buf[len] = 0;
    if (len > 0 && buf[len - 1] == '\n') buf[--len] = 0;
    if (len == 0) return 1;
    /* rows */
    int nrows = 1;
    for (size_t i = 0; i < len; i++) if (buf[i] == '\n') nrows++;
    char ***cells = malloc(nrows * sizeof(char **));
    int *ncell = malloc(nrows * sizeof(int));
    int nc = 0;
    char *p = buf;
    for (int r = 0; r < nrows; r++) {
        char *e = strchr(p, '\n');
        if (e) *e = 0;
        int n = 1;
        for (char *q = p; *q; q++) if (*q == SEP) n++;
        cells[r] = malloc(n * sizeof(char *));
        ncell[r] = n;
        char *q = p;
        for (int j = 0; j < n; j++) {
            cells[r][j] = q;
            char *s = strchr(q, SEP);
            if (s) { *s = 0; q = s + 1; }
        }
        if (n > nc) nc = n;
        p = e ? e + 1 : p;
    }
    int *widths = calloc(nc, sizeof(int));
    for (int r = 0; r < nrows; r++) {
        for (int j = 0; j < nc; j++) {
            if (j >= ncell[r]) continue;
            char *c = cells[r][j];
            if (max && (int)strlen(c) > max) { c[max - 1] = '~'; c[max] = 0; }
            if ((int)strlen(c) > widths[j]) widths[j] = (int)strlen(c);
        }
    }
    Style st = STYLES[0];
    for (int s = 0; s < NSTYLES; s++) if (strcmp(STYLES[s].name, style) == 0) st = STYLES[s];
    int hdr = strcmp(header, "yes") == 0, all = strcmp(rules, "all") == 0;
#define RULE(CH) do { putchar(st.corner); for (int j = 0; j < nc; j++) { rep(CH, widths[j] + 2 * pad); putchar(st.corner); } putchar('\n'); } while (0)
    RULE(st.h);
    for (int r = 0; r < nrows; r++) {
        putchar(st.v);
        for (int j = 0; j < nc; j++) {
            const char *c = j < ncell[r] ? cells[r][j] : "";
            char a = (int)strlen(align) > j ? align[j] : 'l';
            if (a == 'n') a = is_num(c) ? 'r' : 'l';
            int room = widths[j] - (int)strlen(c);
            rep(' ', pad);
            if (a == 'l') { fputs(c, stdout); rep(' ', room); }
            else if (a == 'r') { rep(' ', room); fputs(c, stdout); }
            else { rep(' ', room / 2); fputs(c, stdout); rep(' ', room - room / 2); }
            rep(' ', pad);
            putchar(st.v);
        }
        putchar('\n');
        if (r == 0 && hdr) RULE(st.hh);
        else if (r < nrows - 1 && all) RULE(st.h);
    }
    RULE(st.h);
    return 0;
}
'''

SH = r'''
#!/usr/bin/env bash
# boxtab: draw delimited text as a table
exec awk -v SEP='@SEP@' -v DEFAULT='@DEFAULT@' -v HAS_ALIGN=@ALIGN@ -v HAS_PAD=@PAD@ -v HAS_MAX=@MAX@ -v HAS_RULES=@RULES@ -v HAS_N=@N@ \
  -v NARGS="$#" -v A1="${1-}" -v A2="${2-}" -v A3="${3-}" -v A4="${4-}" -v A5="${5-}" -v A6="${6-}" -v A7="${7-}" -v A8="${8-}" '
function isdig(s,   i, n) {
  n = length(s)
  if (n == 0) return 0
  for (i = 1; i <= n; i++) if (index("0123456789", substr(s, i, 1)) == 0) return 0
  return 1
}
function isnum(s,   body, d) {
  body = s
  if (substr(s, 1, 1) == "+" || substr(s, 1, 1) == "-") body = substr(s, 2)
  d = index(body, ".")
  if (d > 0) return isdig(substr(body, 1, d - 1)) && isdig(substr(body, d + 1))
  return isdig(body)
}
function spaces(n,   s, i) { s = ""; for (i = 0; i < n; i++) s = s " "; return s }
function rep(ch, n,   s, i) { s = ""; for (i = 0; i < n; i++) s = s ch; return s }
function rule(ch,   s, j) {
  s = CORNER
  for (j = 1; j <= nc; j++) s = s rep(ch, W[j] + 2 * PAD) CORNER
  return s
}
function place(cell, j,   a, room) {
  a = (j <= length(ALIGN)) ? substr(ALIGN, j, 1) : "l"
  if (a == "n") a = isnum(cell) ? "r" : "l"
  room = W[j] - length(cell)
  if (a == "l") return cell spaces(room)
  if (a == "r") return spaces(room) cell
  return spaces(int(room / 2)) cell spaces(room - int(room / 2))
}
function fail(code) { bad = code; exit code }
BEGIN {
STYLEDEFS
  style = DEFAULT; header = "yes"; PAD = 1; rules = "edges"; ALIGN = ""; mx = 0
  for (n = 1; n <= NARGS; n++) {
    if (n > 8) fail(2)
    a = (n == 1) ? A1 : (n == 2) ? A2 : (n == 3) ? A3 : (n == 4) ? A4 : (n == 5) ? A5 : (n == 6) ? A6 : (n == 7) ? A7 : A8
    eq = index(a, "=")
    if (eq == 0) fail(2)
    k = substr(a, 1, eq - 1); v = substr(a, eq + 1)
    if (k == "style") { if (!(v in CORN)) fail(2); style = v }
    else if (k == "header") { if (v != "yes" && v != "no") fail(2); header = v }
    else if (k == "rules" && HAS_RULES) { if (v != "edges" && v != "all") fail(2); rules = v }
    else if (k == "pad" && HAS_PAD) { if (v != "0" && v != "1" && v != "2" && v != "3") fail(2); PAD = v + 0 }
    else if (k == "max" && HAS_MAX) { if (length(v) < 1 || length(v) > 2 || !isdig(v) || v + 0 < 2) fail(2); mx = v + 0 }
    else if (k == "align" && HAS_ALIGN) {
      if (v == "") fail(2)
      for (i = 1; i <= length(v); i++) {
        c = substr(v, i, 1)
        if (c != "l" && c != "r" && c != "c" && !(c == "n" && HAS_N)) fail(2)
      }
      ALIGN = v
    }
    else fail(2)
    if (k in SEEN) fail(2)
    SEEN[k] = 1
  }
}
{ LINES[NR] = $0 }
END {
  if (bad) exit bad
  if (NR == 0 || (NR == 1 && LINES[1] == "")) exit 1
  nc = 0
  for (r = 1; r <= NR; r++) {
    n = split(LINES[r], tmp, "[" SEP "]")
    if (n == 0) { n = 1; tmp[1] = "" }
    NC[r] = n
    for (j = 1; j <= n; j++) {
      c = tmp[j]
      if (mx > 0 && length(c) > mx) c = substr(c, 1, mx - 1) "~"
      CELL[r, j] = c
      if (length(c) > W[j]) W[j] = length(c)
    }
    if (n > nc) nc = n
  }
  for (j = 1; j <= nc; j++) W[j] += 0
  CORNER = CORN[style]; H = HCH[style]; V = VCH[style]; HH = HHCH[style]
  print rule(H)
  for (r = 1; r <= NR; r++) {
    line = V
    for (j = 1; j <= nc; j++) {
      c = (j <= NC[r]) ? CELL[r, j] : ""
      line = line spaces(PAD) place(c, j) spaces(PAD) V
    }
    print line
    if (r == 1 && header == "yes") print rule(HH)
    else if (r < NR && rules == "all") print rule(H)
  }
  print rule(H)
}'
'''

SOURCES = {"python": PY, "go": GO, "c": CC, "bash": SH}


def _b(lang, v):
    if lang == "python":
        return "True" if v else "False"
    if lang in ("c", "bash"):
        return "1" if v else "0"
    return "true" if v else "false"


def sol(lang, p):
    st = p["styles"]
    sep = p["sep"]
    py = "{" + ", ".join(f'"{k}": ("{a}", "{b}", "{c}", "{d}")' for k, (a, b, c, d) in st.items()) + "}"
    go = "map[string][4]string{" + ", ".join(f'"{k}": {{"{a}", "{b}", "{c}", "{d}"}}' for k, (a, b, c, d) in st.items()) + "}"
    cc = "{" + ", ".join(f'{{"{k}", \'{a}\', \'{b}\', \'{c}\', \'{d}\'}}' for k, (a, b, c, d) in st.items()) + "}"
    sd = "\n".join(f'  CORN["{k}"] = "{a}"; HCH["{k}"] = "{b}"; VCH["{k}"] = "{c}"; HHCH["{k}"] = "{d}"' for k, (a, b, c, d) in st.items())
    sep_py = "\\t" if sep == "\t" else sep
    sep_go = "\\t" if sep == "\t" else sep
    sep_c = "\\t" if sep == "\t" else sep
    src = SOURCES[lang]
    if lang == "bash":
        src = src.replace("STYLEDEFS", sd)
    return K.subst(src, STYLES_PY=py, STYLES_GO=go, STYLES_C=cc, DEFAULT=p["default"], SEP=(sep if lang == "bash" else sep_py if lang == "python" else sep_go),
                   SEP_C=sep_c, ALIGN=_b(lang, p["has_align"]), PAD=_b(lang, p["has_pad"]), MAX=_b(lang, p["has_max"]), RULES=_b(lang, p["has_rules"]),
                   N=_b(lang, p["has_n"])).lstrip("\n")


# ---------------------------------------------------------------------------------------------------------------

def sepname(sep):
    return {",": "a comma", ";": "a semicolon", "|": "a vertical bar", "\t": "a tab"}[sep]


def readme(p, spec, lang, examples):
    st = p["styles"]
    sep = p["sep"]
    L = ["# boxtab: tables for plain text", ""]
    L.append(f"`boxtab` reads delimited text on standard input and prints it as a bordered table. The office uses it to print {p['ctx']}. "
             f"Fields are separated by {sepname(sep)} (no quoting: a field can never contain the separator). Options are given as command-line arguments of the form `key=value`.")
    L.append("")
    L.append("## Input")
    L.append("")
    L.append("Lines end with `\\n`; if the input ends with `\\n`, that last newline is not a row separator (it is simply removed first). If nothing is left, there are no rows: print nothing and exit with status 1. "
             "Otherwise each remaining line is a row, empty lines included (an empty line is a row with one empty cell). Each row is split at every separator, so `a,,b` has three cells, the middle one empty and a row ending in a separator ends with an empty cell. "
             "The table has as many columns as the longest row; shorter rows are padded on the right with empty cells. Cells are plain ASCII text (anything except the separator and newline).")
    L.append("")
    L.append("## Options")
    L.append("")
    L.append("Every argument must be exactly one option `key=value`; each key may be used at most once, and only the keys below exist. Any violation (an argument without `=`, an unknown or repeated key, an invalid value, "
             "a key that this version does not have) makes the program print nothing to standard output, write a message to standard error and exit with status 2 -- before standard input is looked at.")
    L.append("")
    L.append("| key | values | default |")
    L.append("|---|---|---|")
    L.append("| `style` | " + ", ".join(f"`{k}`" for k in st) + f" (see below) | `{p['default']}` |")
    L.append("| `header` | `yes` or `no` | `yes` |")
    if p["has_align"]:
        L.append("| `align` | a non-empty string of letters, one per column from the left: `l` left, `r` right, `c` centre" + (", `n` numeric (see below)" if p["has_n"] else "") + "; columns beyond the string are `l`, letters beyond the last column are ignored | all `l` |")
    if p["has_pad"]:
        L.append("| `pad` | `0`, `1`, `2` or `3`: spaces on each side of a cell | `1` |")
    if p["has_max"]:
        L.append("| `max` | an integer from 2 to 99 written with one or two ASCII digits (no sign) | no limit |")
    if p["has_rules"]:
        L.append("| `rules` | `edges` or `all` | `edges` |")
    L.append("")
    if p["has_max"]:
        L.append("**`max=N`**: a cell longer than `N` characters is replaced by its first `N-1` characters followed by `~` (so its length becomes `N`). This is done before the column widths are computed.")
        L.append("")
    L.append("## Drawing")
    L.append("")
    L.append("The *width* of a column is the length of its longest cell (0 if all its cells are empty). Each style has four characters, `corner`, `h` (horizontal), `v` (vertical) and `hh` (the horizontal character of the header rule):")
    L.append("")
    L.append("| style | corner | h | v | hh |")
    L.append("|---|---|---|---|---|")
    for k, (a, b, c, d) in st.items():
        L.append(f"| `{k}` | `{a}` | `{b}` | `{c}` | `{d}` |")
    L.append("")
    L.append("A **rule** is `corner`, then for every column `(width + 2*pad)` copies of the rule's horizontal character followed by `corner`: for two columns of widths 3 and 1 and `pad=1`, with the first style's characters, it is `" +
             list(st.values())[0][0] + list(st.values())[0][1] * 5 + list(st.values())[0][0] + list(st.values())[0][1] * 3 + list(st.values())[0][0] + "`. "
             "A **row line** is `v`, then for every column `pad` spaces, the cell aligned inside `width` characters, `pad` spaces and `v`.")
    L.append("")
    L.append("Alignment inside the column: `l` puts the cell first and fills with spaces, `r` puts the spaces first, `c` puts `floor(room/2)` spaces before and the rest after (`room` = width minus cell length)." +
             (" `n` means: right-aligned when the cell is *numeric* - an optional `+` or `-`, one or more ASCII digits, optionally `.` and one or more digits - and left-aligned otherwise (decided cell by cell)." if p["has_n"] else ""))
    L.append("")
    L.append("The output is: a rule with `h`; then the rows in order, where after the **first** row there is a rule with `hh` if `header=yes`" + (", and after every other row except the last a rule with `h` if `rules=all`" if p["has_rules"] else "") + "; and finally a rule with `h`. "
             "Every line, including the last, ends with `\\n`. A table with a single row and `header=yes` therefore has two rules after the row (the `hh` rule, then the closing rule).")
    L.append("")
    L.append("Exit status: 0 after printing a table, 1 when there are no rows, 2 for an option error.")
    L.append("")
    L.append("## Where")
    L.append("")
    L.append(f"The program lives in {spec.how(lang)}.")
    L.append("")
    L.append("## Examples")
    L.append("")
    for c, out in examples:
        L.append("```")
        L.append(f"$ boxtab {' '.join(c.args)} <<'EOF'".replace("  <<", " <<"))
        L.append(c.stdin.rstrip("\n").replace("\t", "<TAB>"))
        L.append("EOF")
        L.append(out.rstrip("\n"))
        L.append("```")
        L.append("")
    if sep == "\t":
        L.append("(`<TAB>` stands for a tab character in the examples above.)")
        L.append("")
    L.append(K.run_hint("bash"))
    return "\n".join(L) + "\n"


def make_cases(rng, p):
    sep = p["sep"]
    st = list(p["styles"])
    cases = []

    def cell(kind=None):
        k = kind or rng.choice(["w", "w", "n", "n", "d", "e", "s"])
        if k == "w":
            return rng.choice(WORDS)
        if k == "n":
            return str(rng.randrange(-50, 5000))
        if k == "d":
            return f"{rng.randrange(0, 300)}.{rng.randrange(0, 100):02d}"
        if k == "e":
            return ""
        return rng.choice(WORDS) + " " + rng.choice(WORDS)

    def table(nr=None, nc=None, ragged=False):
        nr = nr or rng.randrange(1, 6)
        nc = nc or rng.randrange(1, 5)
        rows = []
        for _ in range(nr):
            n = nc if not ragged else rng.randrange(1, nc + 1)
            rows.append(sep.join(cell() for _ in range(n)))
        return "\n".join(rows) + "\n"

    def add(args, text):
        cases.append(K.CliCase(list(args), text))

    add([], table(3, 3))
    add([f"style={st[-1]}"] + (["align=lrc"] if p["has_align"] else ["header=no"]), table(4, 3))
    add([f"style={st[1]}", "header=no"] + (["pad=2"] if p["has_pad"] else []), table(3, 2))
    nex = len(cases)
    for _ in range(6):
        add([], table())
    for s in st:
        add([f"style={s}"], table())
        add([f"style={s}", "header=no"], table())
    add(["header=no"], table(1, 1))
    add([], table(1, 1))
    add([], table(1, 4))
    add([], table(2, 1))
    add([], "")
    add([], "\n")
    add([], "x")
    add([], "x\n")
    add([], "\n\n")
    add([], "\n\nx\n")
    add([], "a" + sep + "b\n\nc" + sep + "d\n")
    add([], sep + "\n")
    add([], sep + sep + "\n" + sep + "\n")
    add([], "a" + sep + "\n" + sep + "b\n")
    add([], "a" + sep + "b" + sep + "\nc\n")
    add([], "a\nb" + sep + "c" + sep + "d\ne" + sep + "f\n")
    add([], "a\n\n\nb")
    add([], "no trailing newline" + sep + "x")
    add([], "x\n\n")
    add([], "head" + sep + "er\nrow" + sep + "one\n" + sep + "\n")
    add([], table(5, 4, ragged=True))
    add([], table(6, 5, ragged=True))
    add(["style=" + st[0]], table(4, 4, ragged=True))
    if p["has_align"]:
        t = table(4, 4)
        for al in ("l", "r", "c", "rl", "lrc", "crl", "cccc", "rrrrrr", "lrcl", "r", "cr", "ccrr"):
            add([f"align={al}"], t)
        add(["align=c"], "a" + sep + "bb\nccc" + sep + "d\n" + "x" + sep + "yyyy\n")
        add(["align=c", "header=no"], "ab\nabc\na\nabcd\n" + "\n")
        add(["align=rc"], "ab" + sep + "x\n" + "abcdefg" + sep + "yz\n" + sep + "\n")
        add(["align="], t)
        add(["align=x"], t)
        add(["align=lrx"], t)
        add(["align=L"], t)
        add(["align=l,r"], t)
        add(["align=n"] if not p["has_n"] else ["align=q"], t)
        add(["align=lr", "align=rl"], t)
        add(["align=lrc", "style=" + st[-1], "header=no"], t)
    else:
        for bad in (["align=lrc"], ["align=l"]):
            add(bad, table(2, 2))
    if p["has_pad"]:
        t = table(3, 3)
        for pd in ("0", "1", "2", "3"):
            add([f"pad={pd}"], t)
        add(["pad=0", "header=no"], "a" + sep + "b\n")
        add(["pad=3", "align=c"] if p["has_align"] else ["pad=3"], "a" + sep + "bbbb\nccccc" + sep + "d\n")
        for bad in ("pad=4", "pad=-1", "pad=01", "pad=", "pad=x", "pad=1.5", "pad= 1", "pad=10"):
            add([bad], t)
    else:
        add(["pad=1"], table(2, 2))
        add(["pad=0"], table(2, 2))
    if p["has_max"]:
        t = "kelp" + sep + "1234567890\nlongerword" + sep + "x\n" + "ab" + sep + "abc\n"
        for m in ("2", "3", "4", "5", "9", "10", "11", "99", "02", "07"):
            add([f"max={m}"], t)
        add(["max=3", "align=r"] if p["has_align"] else ["max=3"], t)
        add(["max=5", "header=no"], table(4, 3))
        add(["max=6", "rules=all"] if p["has_rules"] else ["max=6"], table(4, 3))
        for bad in ("max=1", "max=0", "max=100", "max=-3", "max=", "max=x", "max=2.5", "max= 5", "max=+5", "max=005"):
            add([bad], t)
    else:
        add(["max=5"], table(2, 2))
    if p["has_rules"]:
        t = table(4, 3)
        add(["rules=all"], t)
        add(["rules=all", "header=no"], t)
        add(["rules=all"], table(1, 2))
        add(["rules=all", "header=no"], table(1, 2))
        add(["rules=all"], table(2, 2))
        add(["rules=edges", "pad=0"] if p["has_pad"] else ["rules=edges"], t)
        add(["rules=all", "pad=0", "header=no"] if p["has_pad"] else ["rules=all", "header=no"], t)
        for bad in ("rules=none", "rules=", "rules=ALL", "rules=edge"):
            add([bad], t)
    else:
        add(["rules=all"], table(2, 2))
    if p["has_n"]:
        t = "item" + sep + "qty" + sep + "price\nrope" + sep + "12" + sep + "3.50\nnet" + sep + "-7" + sep + "+0.25\nbuoy" + sep + "n/a" + sep + "1,5\nanchor" + sep + "5." + sep + ".5\n" + "x" + sep + "007" + sep + "-\n"
        add(["align=lnn"], t)
        add(["align=nnn"], t)
        add(["align=nrn"], t)
        add(["align=ncn", "pad=2"] if p["has_pad"] else ["align=ncn"], t)
        add(["align=n", "header=no"], "12\nabc\n-3.5\n+\n--1\n1.2.3\n1e5\n 12\n")
    else:
        add(["align=n"], table(2, 2))
    # option errors (all levels)
    t = table(2, 2)
    for bad in (["frobnicate"], ["style"], ["style="], ["style=nosuch"], ["style=" + st[0].upper()], ["header=maybe"], ["header=YES"], ["header="], ["=yes"], ["=" ], ["a=b"], ["style=" + st[0], "style=" + st[1]],
                ["header=no", "header=no"], ["--style=" + st[0]], ["-h"], ["style:" + st[0]], ["style = " + st[0]], ["style= " + st[0]], ["style=" + st[0] + " "], ["header=no", "bogus=1"], ["bogus=1", "header=no"],
                ["header=no", "x"], [" header=no"], ["header==no"], ["header=no=yes"]):
        add(bad, t)
    add(["bogus"], "")
    add(["style=nosuch"], "")
    add(["header=no"], "")
    add(["header=no"], "\n")
    out, seen = [], set()
    for c in cases:
        if c.key() not in seen:
            seen.add(c.key())
            out.append(c)
    return out, nex


def prompt(rng, p, spec, lang):
    ln = K.LANG_NAME[lang]
    where = spec.short(lang)
    opts = ["style", "header"] + (["align"] if p["has_align"] else []) + (["pad"] if p["has_pad"] else []) + (["max"] if p["has_max"] else []) + (["rules"] if p["has_rules"] else [])
    ol = ", ".join(f"`{o}`" for o in opts)
    variants = [
        f"We print {p['ctx']} from delimited text, and the stock table tools disagree with our house style. Please write `boxtab` in {ln} (entry point {where}): it reads delimited rows on stdin and draws the table; options ({ol}) are `key=value` arguments. README.md gives the exact characters and layout. {K.closer(rng)}",
        f"Task ({ln}): implement the `boxtab` command line tool from README.md. Entry point {where}. Output must match the spec byte for byte, including the rule lines; exit codes are part of the contract (0, 1 for no rows, 2 for option errors).",
        f"need `boxtab` in {ln}, entry point {where}. spec = README.md. options: {ol}. it's all about exact rendering and the edge cases (ragged rows, empty input, repeated options). {K.closer(rng)}",
        f"Please build the table drawer described in README.md in {ln}. It lives in {where}. The hidden checks compare whole outputs, so alignment details (centering with odd room, padding, header rule) matter.",
    ]
    return rng.choice(variants).strip()


@family("greenfield-boxtab", category="greenfield", lang="mixed", kind="greenfield", n=12,
        summary="delimited text -> bordered table CLI with an invented option set, per-instance separator and border characters, exact rendering and exit codes")
def gen(rng, n):
    levels = [1, 1, 2, 2, 3, 3, 2, 3, 1, 3, 2, 3]
    diffs = [1, 1, 2, 2, 3, 3, 2, 3, 1, 4, 2, 3]
    spec = K.CliSpec("boxtab")
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level, i)
        sols = {lang: sol(lang, p), "python": sol("python", p)}
        cases, nex = make_cases(rng, p)
        pt = K.merged(spec.skeleton("python"), spec.stub("python"), {spec.path("python"): sols["python"]})
        res = K.record_cli(spec, "python", pt, cases[:nex])
        ex = [(c, o[0]) for c, o in zip(cases[:nex], res)]
        rd = readme(p, spec, lang, ex)
        yield K.cli_task(
            spec=spec, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, spec, lang),
            difficulty=diffs[i % len(diffs)], slug=f"{i + 1:02d}-{lang}-{p['default']}-{ {',': 'comma', ';': 'semi', '|': 'pipe', chr(9): 'tab'}[p['sep']] }",
            tags=["cli", "formatting", "exit-codes"], notes={"level": level, "sep": p["sep"], "styles": p["styles"]},
        )
