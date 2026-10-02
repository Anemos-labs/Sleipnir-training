"""Podcast chapter files: a command line tool that validates, tabulates and shifts chapter lists (invented syntax per instance)."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

WORDS = ["intro", "recap", "mailbag", "interview", "listener question", "sponsor read", "deep dive", "news roundup", "outro",
         "cold open", "behind the scenes", "bonus round", "tech check", "field notes", "guest bio", "Q&A", "teaser", "credits",
         "headlines", "the long story", "reader letters", "garden update", "weather talk", "ferry delays", "tide tables"]
SHOWS = ["The Lantern Hour", "Slow Harbour", "Notes from the Moor", "Quarry Radio", "Salt & Signal", "Kettle Lane", "The Dovetail Show",
         "Low Tide Club", "Almanac Weekly", "Night Ferry"]
STYLES = [("", ""), ("[", "]"), ("@", ""), ("(", ")")]
CASE = {1: ("python", "bash"), 2: ("python", "bash", "ruby", "go"), 3: ("python", "bash", "ruby", "go")}

LANG_PLAN = ["python", "bash", "go", "ruby", "bash", "python", "go", "ruby", "bash", "go"]


def params(rng, level):
    op, cl = rng.choice(STYLES)
    return {
        "level": level, "show": rng.choice(SHOWS), "open": op, "close": cl, "tsep": rng.choice([":", ":", "."]),
        "maxt": rng.choice([32, 40, 48, 60]), "minlen": rng.choice([10, 15, 20, 30]), "maxn": rng.choice([6, 8, 12, 20]),
        "r_title": level >= 2, "r_short": level >= 2, "r_maxn": level >= 2, "has_table": level >= 2, "has_shift": level >= 3,
    }


def _b(lang, v):
    if lang == "python":
        return "True" if v else "False"
    if lang == "ruby":
        return "true" if v else "false"
    if lang == "bash":
        return "1" if v else "0"
    return "true" if v else "false"


PY = r'''
import sys

OPEN = "@OPEN@"
CLOSE = "@CLOSE@"
TSEP = "@TSEP@"
MAX_TITLE = @MAXT@
MIN_LEN = @MINLEN@
MAX_CH = @MAXN@
R_TITLE = @R_TITLE@
R_SHORT = @R_SHORT@
R_MAXN = @R_MAXN@
HAS_TABLE = @HAS_TABLE@
HAS_SHIFT = @HAS_SHIFT@
CODES = ["syntax", "no-title", "title-long", "no-start", "order", "too-many", "short"]


def digits(s, lo, hi):
    return lo <= len(s) <= hi and all(c in "0123456789" for c in s)


def parse_time(tok):
    parts = tok.split(TSEP)
    if len(parts) == 2:
        a, b = parts
        if digits(a, 1, 2) and digits(b, 2, 2) and int(b) < 60:
            return int(a) * 60 + int(b)
    elif len(parts) == 3:
        a, b, c = parts
        if digits(a, 1, 2) and digits(b, 2, 2) and digits(c, 2, 2) and int(b) < 60 and int(c) < 60:
            return int(a) * 3600 + int(b) * 60 + int(c)
    return None


def fmt(t):
    if t < 3600:
        return "%02d%s%02d" % (t // 60, TSEP, t % 60)
    return "%d%s%02d%s%02d" % (t // 3600, TSEP, t // 60 % 60, TSEP, t % 60)


def parse_line(raw):
    line = raw.strip(" \t")
    if not line or line[0] == "#":
        return "skip"
    if not line.startswith(OPEN):
        return None
    rest = line[len(OPEN):]
    if CLOSE:
        i = rest.find(CLOSE)
        if i < 0:
            return None
        tok, after = rest[:i], rest[i + len(CLOSE):]
    else:
        j = 0
        while j < len(rest) and rest[j] not in " \t":
            j += 1
        tok, after = rest[:j], rest[j:]
    if after and after[0] not in " \t":
        return None
    t = parse_time(tok)
    if t is None:
        return None
    return (t, after.strip(" \t"))


def usage():
    sys.stderr.write("usage: chapters check | table [--total TIME] | shift SECONDS\n")
    sys.exit(2)


def main(argv):
    if not argv:
        usage()
    cmd = argv[0]
    total = None
    shift = 0
    if cmd == "check" and len(argv) == 1:
        pass
    elif HAS_TABLE and cmd == "table" and len(argv) == 1:
        pass
    elif HAS_TABLE and cmd == "table" and len(argv) == 3 and argv[1] == "--total":
        total = parse_time(argv[2])
        if total is None:
            usage()
    elif HAS_SHIFT and cmd == "shift" and len(argv) == 2:
        a = argv[1]
        body = a[1:] if a[:1] in "+-" and a else a
        if not digits(body, 1, 6):
            usage()
        shift = int(body) * (-1 if a[0] == "-" else 1)
    else:
        usage()
    lines = sys.stdin.read().split("\n")
    chapters = []
    problems = []
    for no, raw in enumerate(lines, 1):
        r = parse_line(raw)
        if r == "skip":
            continue
        if r is None:
            problems.append((no, 0, "syntax"))
            continue
        chapters.append((no, r[0], r[1]))
    if not chapters:
        problems.append((0, -1, "empty"))
    for idx, (no, t, title) in enumerate(chapters):
        if R_TITLE:
            if title == "":
                problems.append((no, 1, "no-title"))
            if len(title) > MAX_TITLE:
                problems.append((no, 2, "title-long"))
        if idx == 0:
            if t != 0:
                problems.append((no, 3, "no-start"))
        elif t <= chapters[idx - 1][1]:
            problems.append((no, 4, "order"))
        if R_MAXN and idx >= MAX_CH:
            problems.append((no, 5, "too-many"))
        if R_SHORT and idx + 1 < len(chapters):
            nt = chapters[idx + 1][1]
            if nt > t and nt - t < MIN_LEN:
                problems.append((no, 6, "short"))
    problems.sort()
    if problems:
        for no, _, code in problems:
            print("line %d: %s" % (no, code))
        print("problems: %d" % len(problems))
        return 1
    if cmd == "check":
        print("ok %d chapters" % len(chapters))
    elif cmd == "table":
        for i, (no, t, title) in enumerate(chapters):
            if i + 1 < len(chapters):
                ln = fmt(chapters[i + 1][1] - t)
            elif total is not None and total > t:
                ln = fmt(total - t)
            else:
                ln = "-"
            print("%02d %s %s" % (i + 1, fmt(t), ln) + (" " + title if title else ""))
    else:
        if any(t + shift < 0 for _, t, _ in chapters):
            sys.stderr.write("shift would give a negative time\n")
            return 3
        for no, t, title in chapters:
            print(OPEN + fmt(t + shift) + CLOSE + (" " + title if title else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

RB = r'''
OPEN = '@OPEN@'
CLOSE = '@CLOSE@'
TSEP = '@TSEP@'
MAX_TITLE = @MAXT@
MIN_LEN = @MINLEN@
MAX_CH = @MAXN@
R_TITLE = @R_TITLE@
R_SHORT = @R_SHORT@
R_MAXN = @R_MAXN@
HAS_TABLE = @HAS_TABLE@
HAS_SHIFT = @HAS_SHIFT@

def digits?(s, lo, hi)
  s.length >= lo && s.length <= hi && s.each_char.all? { |c| c >= '0' && c <= '9' }
end

def parse_time(tok)
  parts = tok.split(TSEP, -1)
  if parts.length == 2
    a, b = parts
    return a.to_i * 60 + b.to_i if digits?(a, 1, 2) && digits?(b, 2, 2) && b.to_i < 60
  elsif parts.length == 3
    a, b, c = parts
    return a.to_i * 3600 + b.to_i * 60 + c.to_i if digits?(a, 1, 2) && digits?(b, 2, 2) && digits?(c, 2, 2) && b.to_i < 60 && c.to_i < 60
  end
  nil
end

def fmt(t)
  return format('%02d%s%02d', t / 60, TSEP, t % 60) if t < 3600
  format('%d%s%02d%s%02d', t / 3600, TSEP, t / 60 % 60, TSEP, t % 60)
end

def blank?(c)
  c == ' ' || c == "\t"
end

def strip_blanks(s)
  s.sub(/\A[ \t]+/, '').sub(/[ \t]+\z/, '')
end

def parse_line(raw)
  line = strip_blanks(raw)
  return :skip if line.empty? || line[0] == '#'
  return nil unless line.start_with?(OPEN)
  rest = line[OPEN.length..]
  if CLOSE.empty?
    j = 0
    j += 1 while j < rest.length && !blank?(rest[j])
    tok = rest[0, j]
    after = rest[j..]
  else
    i = rest.index(CLOSE)
    return nil if i.nil?
    tok = rest[0, i]
    after = rest[(i + CLOSE.length)..]
  end
  return nil if !after.empty? && !blank?(after[0])
  t = parse_time(tok)
  return nil if t.nil?
  [t, strip_blanks(after)]
end

def usage
  $stderr.puts 'usage: chapters check | table [--total TIME] | shift SECONDS'
  exit 2
end

def main(argv)
  usage if argv.empty?
  cmd = argv[0]
  total = nil
  shift = 0
  if cmd == 'check' && argv.length == 1
  elsif HAS_TABLE && cmd == 'table' && argv.length == 1
  elsif HAS_TABLE && cmd == 'table' && argv.length == 3 && argv[1] == '--total'
    total = parse_time(argv[2])
    usage if total.nil?
  elsif HAS_SHIFT && cmd == 'shift' && argv.length == 2
    a = argv[1]
    body = (a[0] == '+' || a[0] == '-') ? a[1..] : a
    usage unless digits?(body, 1, 6)
    shift = body.to_i * (a[0] == '-' ? -1 : 1)
  else
    usage
  end
  lines = $stdin.read.split("\n", -1)
  chapters = []
  problems = []
  lines.each_with_index do |raw, i|
    no = i + 1
    r = parse_line(raw)
    next if r == :skip
    if r.nil?
      problems << [no, 0, 'syntax']
      next
    end
    chapters << [no, r[0], r[1]]
  end
  problems << [0, -1, 'empty'] if chapters.empty?
  chapters.each_with_index do |(no, t, title), idx|
    if R_TITLE
      problems << [no, 1, 'no-title'] if title.empty?
      problems << [no, 2, 'title-long'] if title.length > MAX_TITLE
    end
    if idx == 0
      problems << [no, 3, 'no-start'] if t != 0
    elsif t <= chapters[idx - 1][1]
      problems << [no, 4, 'order']
    end
    problems << [no, 5, 'too-many'] if R_MAXN && idx >= MAX_CH
    if R_SHORT && idx + 1 < chapters.length
      nt = chapters[idx + 1][1]
      problems << [no, 6, 'short'] if nt > t && nt - t < MIN_LEN
    end
  end
  problems.sort!
  unless problems.empty?
    problems.each { |no, _, code| puts "line #{no}: #{code}" }
    puts "problems: #{problems.length}"
    return 1
  end
  if cmd == 'check'
    puts "ok #{chapters.length} chapters"
  elsif cmd == 'table'
    chapters.each_with_index do |(_no, t, title), i|
      ln = if i + 1 < chapters.length then fmt(chapters[i + 1][1] - t)
           elsif !total.nil? && total > t then fmt(total - t)
           else '-'
           end
      puts format('%02d %s %s', i + 1, fmt(t), ln) + (title.empty? ? '' : " #{title}")
    end
  else
    if chapters.any? { |_n, t, _ti| t + shift < 0 }
      $stderr.puts 'shift would give a negative time'
      return 3
    end
    chapters.each { |_n, t, title| puts OPEN + fmt(t + shift) + CLOSE + (title.empty? ? '' : " #{title}") }
  end
  0
end

exit main(ARGV)
'''

GO = r'''
package main

import (
	"fmt"
	"io"
	"os"
	"sort"
	"strconv"
	"strings"
)

const (
	open     = "@OPEN@"
	closeS   = "@CLOSE@"
	tsep     = "@TSEP@"
	maxTitle = @MAXT@
	minLen   = @MINLEN@
	maxCh    = @MAXN@
	rTitle   = @R_TITLE@
	rShort   = @R_SHORT@
	rMaxn    = @R_MAXN@
	hasTable = @HAS_TABLE@
	hasShift = @HAS_SHIFT@
)

func digits(s string, lo, hi int) bool {
	if len(s) < lo || len(s) > hi {
		return false
	}
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
	}
	return true
}

func parseTime(tok string) (int, bool) {
	parts := strings.Split(tok, tsep)
	n := func(s string) int { v, _ := strconv.Atoi(s); return v }
	if len(parts) == 2 {
		if digits(parts[0], 1, 2) && digits(parts[1], 2, 2) && n(parts[1]) < 60 {
			return n(parts[0])*60 + n(parts[1]), true
		}
	} else if len(parts) == 3 {
		if digits(parts[0], 1, 2) && digits(parts[1], 2, 2) && digits(parts[2], 2, 2) && n(parts[1]) < 60 && n(parts[2]) < 60 {
			return n(parts[0])*3600 + n(parts[1])*60 + n(parts[2]), true
		}
	}
	return 0, false
}

func fmtTime(t int) string {
	if t < 3600 {
		return fmt.Sprintf("%02d%s%02d", t/60, tsep, t%60)
	}
	return fmt.Sprintf("%d%s%02d%s%02d", t/3600, tsep, t/60%60, tsep, t%60)
}

func isBlank(c byte) bool { return c == ' ' || c == '\t' }

type chapter struct {
	no, t int
	title string
}

type problem struct {
	no, rank int
	code     string
}

// parseLine returns kind: 0 skip, 1 ok, 2 syntax error
func parseLine(raw string) (int, int, string) {
	line := strings.Trim(raw, " \t")
	if line == "" || line[0] == '#' {
		return 0, 0, ""
	}
	if !strings.HasPrefix(line, open) {
		return 2, 0, ""
	}
	rest := line[len(open):]
	var tok, after string
	if closeS != "" {
		i := strings.Index(rest, closeS)
		if i < 0 {
			return 2, 0, ""
		}
		tok, after = rest[:i], rest[i+len(closeS):]
	} else {
		j := 0
		for j < len(rest) && !isBlank(rest[j]) {
			j++
		}
		tok, after = rest[:j], rest[j:]
	}
	if after != "" && !isBlank(after[0]) {
		return 2, 0, ""
	}
	t, ok := parseTime(tok)
	if !ok {
		return 2, 0, ""
	}
	return 1, t, strings.Trim(after, " \t")
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: chapters check | table [--total TIME] | shift SECONDS")
	os.Exit(2)
}

func main() {
	argv := os.Args[1:]
	if len(argv) == 0 {
		usage()
	}
	cmd := argv[0]
	total, hasTotal, shift := 0, false, 0
	switch {
	case cmd == "check" && len(argv) == 1:
	case hasTable && cmd == "table" && len(argv) == 1:
	case hasTable && cmd == "table" && len(argv) == 3 && argv[1] == "--total":
		v, ok := parseTime(argv[2])
		if !ok {
			usage()
		}
		total, hasTotal = v, true
	case hasShift && cmd == "shift" && len(argv) == 2:
		a := argv[1]
		body := a
		if len(a) > 0 && (a[0] == '+' || a[0] == '-') {
			body = a[1:]
		}
		if !digits(body, 1, 6) {
			usage()
		}
		shift, _ = strconv.Atoi(body)
		if a[0] == '-' {
			shift = -shift
		}
	default:
		usage()
	}
	data, _ := io.ReadAll(os.Stdin)
	var chapters []chapter
	var problems []problem
	for i, raw := range strings.Split(string(data), "\n") {
		kind, t, title := parseLine(raw)
		switch kind {
		case 2:
			problems = append(problems, problem{i + 1, 0, "syntax"})
		case 1:
			chapters = append(chapters, chapter{i + 1, t, title})
		}
	}
	if len(chapters) == 0 {
		problems = append(problems, problem{0, -1, "empty"})
	}
	for idx, c := range chapters {
		if rTitle {
			if c.title == "" {
				problems = append(problems, problem{c.no, 1, "no-title"})
			}
			if len(c.title) > maxTitle {
				problems = append(problems, problem{c.no, 2, "title-long"})
			}
		}
		if idx == 0 {
			if c.t != 0 {
				problems = append(problems, problem{c.no, 3, "no-start"})
			}
		} else if c.t <= chapters[idx-1].t {
			problems = append(problems, problem{c.no, 4, "order"})
		}
		if rMaxn && idx >= maxCh {
			problems = append(problems, problem{c.no, 5, "too-many"})
		}
		if rShort && idx+1 < len(chapters) {
			nt := chapters[idx+1].t
			if nt > c.t && nt-c.t < minLen {
				problems = append(problems, problem{c.no, 6, "short"})
			}
		}
	}
	sort.SliceStable(problems, func(i, j int) bool {
		if problems[i].no != problems[j].no {
			return problems[i].no < problems[j].no
		}
		return problems[i].rank < problems[j].rank
	})
	if len(problems) > 0 {
		for _, p := range problems {
			fmt.Printf("line %d: %s\n", p.no, p.code)
		}
		fmt.Printf("problems: %d\n", len(problems))
		os.Exit(1)
	}
	switch cmd {
	case "check":
		fmt.Printf("ok %d chapters\n", len(chapters))
	case "table":
		for i, c := range chapters {
			ln := "-"
			if i+1 < len(chapters) {
				ln = fmtTime(chapters[i+1].t - c.t)
			} else if hasTotal && total > c.t {
				ln = fmtTime(total - c.t)
			}
			row := fmt.Sprintf("%02d %s %s", i+1, fmtTime(c.t), ln)
			if c.title != "" {
				row += " " + c.title
			}
			fmt.Println(row)
		}
	default:
		for _, c := range chapters {
			if c.t+shift < 0 {
				fmt.Fprintln(os.Stderr, "shift would give a negative time")
				os.Exit(3)
			}
		}
		for _, c := range chapters {
			row := open + fmtTime(c.t+shift) + closeS
			if c.title != "" {
				row += " " + c.title
			}
			fmt.Println(row)
		}
	}
}
'''

SH = r'''
#!/usr/bin/env bash
# chapters: check, tabulate and shift podcast chapter lists
usage() {
  echo 'usage: chapters check | table [--total TIME] | shift SECONDS' >&2
  exit 2
}

HAS_TABLE=@HAS_TABLE@
HAS_SHIFT=@HAS_SHIFT@
cmd=${1:-}
total=""
shiftby=0
if [ "$cmd" = check ] && [ $# -eq 1 ]; then
  :
elif [ "$HAS_TABLE" = 1 ] && [ "$cmd" = table ] && [ $# -eq 1 ]; then
  :
elif [ "$HAS_TABLE" = 1 ] && [ "$cmd" = table ] && [ $# -eq 3 ] && [ "$2" = "--total" ]; then
  total=$3
elif [ "$HAS_SHIFT" = 1 ] && [ "$cmd" = shift ] && [ $# -eq 2 ]; then
  [[ $2 =~ ^[+-]?[0-9]{1,6}$ ]] || usage
  shiftby=$2
else
  usage
fi

exec awk -v CMD="$cmd" -v TOTAL="$total" -v SHIFT="$shiftby" \
  -v OPENS='@OPEN@' -v CLOSES='@CLOSE@' -v TSEP='@TSEP@' \
  -v MAXT=@MAXT@ -v MINLEN=@MINLEN@ -v MAXN=@MAXN@ \
  -v R_TITLE=@R_TITLE@ -v R_SHORT=@R_SHORT@ -v R_MAXN=@R_MAXN@ '
function isdig(s,   i, n) {
  n = length(s)
  if (n == 0) return 0
  for (i = 1; i <= n; i++) if (index("0123456789", substr(s, i, 1)) == 0) return 0
  return 1
}
function dig(s, lo, hi) { return (length(s) >= lo && length(s) <= hi && isdig(s)) }
function ptime(tok,   n, p) {
  n = split(tok, p, "[" TSEP "]")
  if (n == 2) {
    if (dig(p[1], 1, 2) && dig(p[2], 2, 2) && p[2] + 0 < 60) return p[1] * 60 + p[2]
  } else if (n == 3) {
    if (dig(p[1], 1, 2) && dig(p[2], 2, 2) && dig(p[3], 2, 2) && p[2] + 0 < 60 && p[3] + 0 < 60) return p[1] * 3600 + p[2] * 60 + p[3]
  }
  return -1
}
function fmt(t) {
  if (t < 3600) return sprintf("%02d%s%02d", int(t / 60), TSEP, t % 60)
  return sprintf("%d%s%02d%s%02d", int(t / 3600), TSEP, int(t / 60) % 60, TSEP, t % 60)
}
function trim(s) { sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); return s }
function pline(raw,   s, rest, i, j, tok, after, ol, t) {
  s = trim(raw)
  if (s == "" || substr(s, 1, 1) == "#") return "skip"
  ol = length(OPENS)
  if (ol > 0 && substr(s, 1, ol) != OPENS) return "bad"
  rest = substr(s, ol + 1)
  if (CLOSES != "") {
    i = index(rest, CLOSES)
    if (i == 0) return "bad"
    tok = substr(rest, 1, i - 1)
    after = substr(rest, i + length(CLOSES))
  } else {
    j = 1
    while (j <= length(rest) && substr(rest, j, 1) != " " && substr(rest, j, 1) != "\t") j++
    tok = substr(rest, 1, j - 1)
    after = substr(rest, j)
  }
  if (after != "" && substr(after, 1, 1) != " " && substr(after, 1, 1) != "\t") return "bad"
  t = ptime(tok)
  if (t < 0) return "bad"
  PT = t
  PTITLE = trim(after)
  return "ok"
}
BEGIN {
  CODE[0] = "syntax"; CODE[1] = "no-title"; CODE[2] = "title-long"; CODE[3] = "no-start"
  CODE[4] = "order"; CODE[5] = "too-many"; CODE[6] = "short"; CODE[-1] = "empty"
  BADARG = 0
  HAVETOTAL = 0
  if (TOTAL != "") {
    TT = ptime(TOTAL)
    if (TT < 0) BADARG = 1
    HAVETOTAL = 1
  }
}
{ LINES[NR] = $0 }
END {
  if (BADARG) exit 2
  nch = 0; np = 0
  for (no = 1; no <= NR; no++) {
    r = pline(LINES[no])
    if (r == "skip") continue
    if (r == "bad") { P[no, 0] = 1; np++; continue }
    nch++
    CNO[nch] = no; CT[nch] = PT; CTITLE[nch] = PTITLE
  }
  if (nch == 0) { P[0, -1] = 1; np++ }
  for (idx = 1; idx <= nch; idx++) {
    no = CNO[idx]; t = CT[idx]; title = CTITLE[idx]
    if (R_TITLE == 1) {
      if (title == "") { P[no, 1] = 1; np++ }
      if (length(title) > MAXT) { P[no, 2] = 1; np++ }
    }
    if (idx == 1) {
      if (t != 0) { P[no, 3] = 1; np++ }
    } else if (t <= CT[idx - 1]) { P[no, 4] = 1; np++ }
    if (R_MAXN == 1 && idx > MAXN) { P[no, 5] = 1; np++ }
    if (R_SHORT == 1 && idx < nch) {
      nt = CT[idx + 1]
      if (nt > t && nt - t < MINLEN) { P[no, 6] = 1; np++ }
    }
  }
  if (np > 0) {
    for (no = 0; no <= NR; no++)
      for (k = -1; k <= 6; k++)
        if ((no, k) in P) printf "line %d: %s\n", no, CODE[k]
    printf "problems: %d\n", np
    exit 1
  }
  if (CMD == "check") {
    printf "ok %d chapters\n", nch
  } else if (CMD == "table") {
    for (i = 1; i <= nch; i++) {
      if (i < nch) ln = fmt(CT[i + 1] - CT[i])
      else if (HAVETOTAL && TT > CT[i]) ln = fmt(TT - CT[i])
      else ln = "-"
      row = sprintf("%02d %s %s", i, fmt(CT[i]), ln)
      if (CTITLE[i] != "") row = row " " CTITLE[i]
      print row
    }
  } else {
    for (i = 1; i <= nch; i++) if (CT[i] + SHIFT < 0) exit 3
    for (i = 1; i <= nch; i++) {
      row = OPENS fmt(CT[i] + SHIFT) CLOSES
      if (CTITLE[i] != "") row = row " " CTITLE[i]
      print row
    }
  }
  exit 0
}
'
'''

SOURCES = {"python": PY, "ruby": RB, "go": GO, "bash": SH}


def sol(lang, p):
    return K.subst(
        SOURCES[lang], OPEN=p["open"], CLOSE=p["close"], TSEP=p["tsep"], MAXT=p["maxt"], MINLEN=p["minlen"], MAXN=p["maxn"],
        R_TITLE=_b(lang, p["r_title"]), R_SHORT=_b(lang, p["r_short"]), R_MAXN=_b(lang, p["r_maxn"]),
        HAS_TABLE=_b(lang, p["has_table"]), HAS_SHIFT=_b(lang, p["has_shift"]),
    ).lstrip("\n")


# ---------------------------------------------------------------------------------------------------------------

def tfmt(p, t, style):
    s = p["tsep"]
    if style == 3 or t >= 3600:
        return f"{t // 3600}{s}{t // 60 % 60:02d}{s}{t % 60:02d}"
    return f"{t // 60:02d}{s}{t % 60:02d}"


def chap_line(p, t, title, rng, noise=False):
    style = rng.choice([2, 2, 3]) if t < 3600 else 3
    core = p["open"] + tfmt(p, t, style) + p["close"]
    sep = " " if not noise else rng.choice([" ", "  ", "\t", " \t "])
    line = core + (sep + title if title else "")
    if noise:
        line = rng.choice(["", "", " ", "\t", "  "]) + line + rng.choice(["", "", " ", "\t"])
    return line


def readme(p, spec, lang, examples):
    op, cl, ts = p["open"], p["close"], p["tsep"]
    L = [f"# chapters: chapter lists for \"{p['show']}\"", ""]
    L.append(f"The producers of *{p['show']}* keep the chapter list of every episode in a plain text file. `chapters` reads such a "
             f"file on **standard input** and checks it" + (", prints it as a table" if p["has_table"] else "") +
             (", or shifts all its timestamps" if p["has_shift"] else "") + ". It writes results to standard output; "
             "messages for usage mistakes go to standard error (their text is not checked).")
    L.append("")
    L.append("## Chapter file")
    L.append("")
    L.append("Lines end with `\\n` (a missing final `\\n` is fine). Leading and trailing blanks (spaces or tabs) of a line are ignored. "
             "A line that is empty after that, or starts with `#`, is skipped; skipped lines still count when numbering lines "
             "(the first line is line 1).")
    L.append("")
    marks = []
    if op:
        marks.append(f"the opening mark `{op}`, written first")
    marks.append("the time")
    if cl:
        marks.append(f"the closing mark `{cl}`, which follows the time directly")
    L.append("Every other line is a *chapter line*. It consists of " + (", then ".join(marks) if len(marks) > 1 else marks[0]) +
             ", and then, optionally, one or more blanks (spaces or tabs) followed by the title. " +
             ("The time text is everything between the opening mark and the first closing mark on the line. " if (op and cl) else
              "The time text is everything before the first closing mark on the line. " if cl else
              "The time text ends at the first blank, or at the end of the line. " if op else
              "The time text ends at the first blank, or at the end of the line. ") +
             "Whatever follows the closing mark (or the time) must be empty or start with a blank, otherwise the line has a syntax problem. "
             "The title is the rest of the line without its trailing blanks; it may contain anything, including blanks inside it, and may be empty.")
    L.append("")
    L.append(f"Here the time is written with `{ts}` as separator, in one of two forms: `M{ts}SS` (minutes of one or two digits, then exactly "
             f"two digits of seconds below 60; minutes may exceed 59, `75{ts}10` is 75 minutes) or `H{ts}MM{ts}SS` (hours of one or two digits, "
             f"exactly two digits of minutes below 60 and exactly two digits of seconds below 60). Only ASCII digits count. "
             f"Example chapter line: `{op}12{ts}05{cl} Mailbag`.")
    L.append("")
    L.append("A line that does not fit this shape (wrong or missing marks, a malformed time, no blank between the closing mark and the title, ...) "
             "is a *syntax* problem and is not a chapter. Times are converted to seconds.")
    L.append("")
    L.append("## Problems")
    L.append("")
    L.append("Every check below is applied independently to the *chapters* (lines without a syntax problem), numbering them 1, 2, 3, ... in file order. "
             "A single line can have several problems.")
    L.append("")
    L.append("| code | when |")
    L.append("|---|---|")
    L.append("| `syntax` | the line is not a chapter line (see above) |")
    if p["r_title"]:
        L.append("| `no-title` | the title is empty |")
        L.append(f"| `title-long` | the title is longer than {p['maxt']} characters |")
    L.append("| `no-start` | the first chapter does not start at time 0 |")
    L.append("| `order` | a chapter other than the first starts at or before the start of the chapter before it |")
    if p["r_maxn"]:
        L.append(f"| `too-many` | the chapter is number {p['maxn'] + 1} or later |")
    if p["r_short"]:
        L.append(f"| `short` | the chapter is not the last, the next chapter starts later than this one, and the gap is shorter than {p['minlen']} seconds |")
    L.append("")
    L.append("If the file has no chapter at all (no line passes the syntax check), there is one more problem, with code `empty`, reported as line 0.")
    L.append("")
    L.append("Problems are reported sorted by line number and, for the same line, in the order of the table above (`empty` first).")
    L.append("")
    L.append("## Commands")
    L.append("")
    L.append("**`chapters check`** prints one line `line N: CODE` per problem, then `problems: K` and exits with status 1. "
             "Without problems it prints `ok K chapters` (K = number of chapters) and exits 0.")
    L.append("")
    cnt = 0
    if p["has_table"]:
        L.append("**`chapters table [--total TIME]`**: if the file has problems it behaves exactly like `check` (same output, status 1). "
                 "Otherwise it prints one row per chapter, `NN START LENGTH TITLE`, separated by single spaces: `NN` is the chapter number "
                 "with at least two digits (`01`), START the start time and LENGTH the distance to the next chapter's start, both in the *canonical time form* below; "
                 "for the last chapter LENGTH is `TOTAL - START` when `--total` is given and TIME is later than the start, and `-` otherwise. "
                 "An empty title is omitted together with the blank before it. `TIME` after `--total` uses the same time forms as the chapter file "
                 "(with the separator `" + ts + "`, without the marks); an invalid `TIME` is a usage error. Exit status 0.")
        L.append("")
    if p["has_shift"]:
        L.append("**`chapters shift SECONDS`**: `SECONDS` is one to six ASCII digits with an optional leading `+` or `-`. "
                 "If the file has problems it behaves exactly like `check`. Otherwise it prints every chapter again, one per line and in file order "
                 f"(comments and blank lines are dropped), as `{op}TIME{cl} TITLE` with every start moved by SECONDS and written in the canonical time form "
                 "(a blank and the title are omitted for an empty title). If any shifted time would be negative, nothing is printed to standard output and the status is 3.")
        L.append("")
    L.append(f"**Canonical time form**: below one hour `MM{ts}SS` (minutes padded to two digits); from one hour on `H{ts}MM{ts}SS` (hours without padding, "
             f"minutes and seconds padded to two digits). So 75 minutes is `1{ts}15{ts}00`.")
    L.append("")
    L.append("**Usage errors** (exit status 2, nothing on standard output, standard input is not read): no command, an unknown command, "
             "a wrong number of arguments or an unknown option" + (", an invalid `SECONDS` or `TIME`" if (p["has_shift"] or p["has_table"]) else "") + ".")
    L.append("")
    L.append("## Where")
    L.append("")
    L.append(f"The program lives in {spec.how(lang)}.")
    L.append("")
    L.append("## Examples")
    L.append("")
    for c, out in examples:
        L.append("```")
        L.append(f"$ chapters {' '.join(c.args)} <<'EOF'")
        L.append(c.stdin.rstrip("\n"))
        L.append("EOF")
        L.append(out.rstrip("\n"))
        L.append(f"[exit {c.code}]")
        L.append("```")
        L.append("")
    L.append(K.run_hint("bash"))
    return "\n".join(L) + "\n"


def make_cases(rng, p, py_run):
    """Returns (cases, number_of_examples)."""
    cases = []

    def titles(n):
        return [rng.choice(WORDS).capitalize() for _ in range(n)]

    def valid_file(n=None, noise=False, start0=True, gap=None):
        n = n or rng.randrange(2, 7)
        t = 0 if start0 else rng.randrange(1, 120)
        rows = []
        for i, ti in enumerate(titles(n)):
            rows.append((t, ti))
            t += rng.randrange(p["minlen"], 900) if gap is None else gap
        return rows

    def render(rows, noise=False, comments=False):
        out = []
        if comments:
            out.append("# chapters of " + p["show"])
        for t, ti in rows:
            if comments and rng.random() < 0.3:
                out.append("")
            out.append(chap_line(p, t, ti, rng, noise))
        txt = "\n".join(out)
        return txt + rng.choice(["\n", "\n", ""])

    def add(args, stdin):
        cases.append(K.CliCase(args=args, stdin=stdin))

    # examples
    rows = valid_file(3)
    add(["check"], render(rows))
    bad = valid_file(4)
    bad[2] = (bad[1][0] - 5 if bad[1][0] > 5 else 1, bad[2][1])
    add(["check"], render(bad))
    if p["has_table"]:
        add(["table", "--total", tfmt(p, rows[-1][0] + 400, 2)], render(valid_file(4, gap=300)))
    elif p["has_shift"]:
        add(["shift", "+30"], render(valid_file(3)))
    else:
        add(["check"], render(valid_file(5), noise=True, comments=True))
    nex = len(cases)

    # check: valid, noisy
    add(["check"], render(valid_file(1)))
    add(["check"], render(valid_file(6), noise=True, comments=True))
    add(["check"], render(valid_file(3), noise=True))
    # no start, order, equal
    add(["check"], render(valid_file(4, start0=False)))
    r2 = valid_file(5)
    r2[3] = (r2[2][0], r2[3][1])
    add(["check"], render(r2))
    r3 = valid_file(5)
    r3[4] = (r3[1][0], r3[4][1])
    add(["check"], render(r3))
    # syntax variety
    ts = p["tsep"]
    op, cl = p["open"], p["close"]
    good = valid_file(3)
    base = render(good).rstrip("\n").split("\n")
    def with_line(i, txt):
        ls = list(base)
        ls[i] = txt
        return "\n".join(ls) + "\n"
    synt = [
        f"{op}1{ts}5{cl} short seconds", f"{op}01{ts}60{cl} sixty", f"{op}001{ts}00{cl} wide", f"{op}1{ts}2{ts}3{cl} bad parts",
        f"{op}00{ts}10{cl}title glued", f"{op}00{ts}10{ts}00{ts}00{cl} four parts", f"just words", f"{op}aa{ts}10{cl} letters",
        f"{op}00{ts}10 no close" if cl else f"{op}00{ts}1x title", f"{op}-1{ts}10{cl} negative", f"{op}{ts}10{cl} empty minutes",
        f"{op}0{ts}00{ts}0{cl} short hms", f"{op} 00{ts}10 {cl} spaced",
        (("x" + op + "00" + ts + "10" + cl + " prefixed") if op else ("00" + ts + "10" + "x" + " junk")),
    ]
    for s in synt:
        add(["check"], with_line(rng.randrange(1, 3), s))
    add(["check"], "\n".join(["nonsense", op + tfmt(p, 0, 2) + cl + " fine", "more nonsense"]) + "\n")
    # empty & comments only
    add(["check"], "")
    add(["check"], "\n\n# nothing here\n   \n")
    add(["check"], "bogus line\n")
    # 3-part forms, big minutes
    add(["check"], "\n".join([op + f"0{ts}00{ts}00" + cl + " zero", op + f"75{ts}10" + cl + " long", op + f"1{ts}30{ts}00" + cl + " later"]) + "\n")
    add(["check"], "\n".join([op + f"00{ts}00" + cl + " a", op + f"99{ts}59{ts}59" + cl + " z"]) + "\n")
    if p["r_title"]:
        t1 = ["", " "]
        add(["check"], render([(0, "Start"), (100, "")]).rstrip("\n") + "\n")
        add(["check"], render([(0, ""), (400, "x")]))
        long_t = "A" * p["maxt"]
        add(["check"], render([(0, long_t), (400, long_t + "B"), (900, "ok " + "y" * (p["maxt"] - 3))]))
        add(["check"], render([(0, "tab\tinside  and  spaces"), (500, "end")]))
        add(["check"], op + tfmt(p, 0, 2) + cl + "\n" + op + tfmt(p, 400, 2) + cl + "   \n")
    if p["r_short"]:
        ml = p["minlen"]
        add(["check"], render([(0, "a"), (ml - 1, "b"), (ml - 1 + ml, "c"), (ml * 3, "d")]))
        add(["check"], render([(0, "a"), (ml, "b"), (ml + ml + 1, "c")]))
        add(["check"], render([(0, "a"), (ml - 1, "b")]))
        add(["check"], render([(0, "a"), (5, "b"), (5, "c"), (3, "d")]))
        add(["check"], "\n".join([chap_line(p, 0, "a", rng), "oops", chap_line(p, 3, "b", rng), chap_line(p, 100, "c", rng)]) + "\n")
    if p["r_maxn"]:
        n = p["maxn"]
        add(["check"], render([(i * 60, f"c{i}") for i in range(n)]))
        add(["check"], render([(i * 60, f"c{i}") for i in range(n + 1)]))
        add(["check"], render([(i * 60, f"c{i}") for i in range(n + 3)]))
        add(["check"], render([(i * 60, f"c{i}") for i in range(n)] + [(5, "back")]))
    add(["check"], render([(0, "x"), (30, "y")]) + "# trailing comment\n")
    # table
    if p["has_table"]:
        r = valid_file(4, gap=rng.randrange(max(p["minlen"], 60), 700))
        add(["table"], render(r))
        add(["table", "--total", tfmt(p, r[-1][0] + 777, 2)], render(r))
        add(["table", "--total", tfmt(p, r[-1][0], 2)], render(r))
        add(["table", "--total", tfmt(p, max(r[-1][0] - 5, 0), 3)], render(r))
        add(["table", "--total", tfmt(p, 3600 * 2 + 61, 3)], render([(0, "Only"), ]))
        add(["table", "--total", f"75{ts}10"], render([(0, "Only"), (4000, "Hour mark")], noise=True))
        add(["table"], render([(0, "One")]))
        if p["r_title"]:
            add(["table"], render(valid_file(3), noise=True, comments=True))
        else:
            add(["table"], op + tfmt(p, 0, 2) + cl + "\n" + op + tfmt(p, 3599, 2) + cl + " end\n")
        add(["table"], render(valid_file(3, start0=False)))
        add(["table", "--total"], render(valid_file(2)))
        add(["table", "--total", "abc"], render(valid_file(2)))
        add(["table", "--total", f"1{ts}2"], render(valid_file(2)))
        add(["table", "--total", tfmt(p, 500, 2), "extra"], render(valid_file(2)))
        add(["table", "--bogus", "5"], render(valid_file(2)))
        add(["table"], render([(0, "a"), (3599, "b"), (3600, "c"), (7199, "d"), (7200, "e"), (36000 + 61, "f")]))
    # shift
    if p["has_shift"]:
        r = valid_file(4)
        for a in ["+30", "-0", "120", "-5", "+0", "3601", "+000007"]:
            add(["shift", a], render(r))
        r0 = valid_file(3, start0=True)
        add(["shift", "-1"], render(r0))
        add(["shift", f"-{r[1][0]}"], render([(r[1][0], "later"), (r[1][0] + 100, "x")]))
        add(["shift", f"-{r[1][0] + 1}"], render([(r[1][0], "later"), (r[1][0] + 100, "x")]))
        add(["shift", "+7"], render(valid_file(3), noise=True, comments=True))
        add(["shift", "+3590"], render([(0, "a"), (9, "b"), (3600, "c")]))
        add(["shift", "999999"], render([(0, "a")]))
        add(["shift", "5"], render(valid_file(3, start0=False)))
        add(["shift", "+5"], "bogus\n")
        for bad in ["", "x", "+", "-", "1.5", "+-3", "1234567", " 5", "5 "]:
            add(["shift", bad], render(valid_file(2)))
        add(["shift"], render(valid_file(2)))
        add(["shift", "5", "6"], render(valid_file(2)))
    # usage
    add([], render(valid_file(2)))
    add(["frobnicate"], render(valid_file(2)))
    add(["check", "extra"], render(valid_file(2)))
    add(["CHECK"], render(valid_file(2)))
    add(["--help"], "")
    if not p["has_table"]:
        add(["table"], render(valid_file(2)))
    if not p["has_shift"]:
        add(["shift", "+5"], render(valid_file(2)))
    out, seen = [], set()
    for c in cases:
        if c.key() not in seen:
            seen.add(c.key())
            out.append(c)
    return out, nex


def prompt(rng, p, spec, lang, level):
    ln = K.LANG_NAME[lang]
    show = p["show"]
    where = spec.short(lang)
    subs = [c for c, f in (("table", p["has_table"]), ("shift", p["has_shift"])) if f]
    extra = (" Besides `check` it has " + " and ".join(f"a `{c}` subcommand" for c in subs) + ".") if subs else " It only has a `check` subcommand."
    opts = [
        f"The editors of {show} want a small command line tool, `chapters`, that validates an episode's chapter list.{extra} The format, rules and exit codes are all in README.md. Please write it in {ln} (entry point {where}).",
        f"Can you build `chapters` for me in {ln}? It reads a chapter file ({show} uses its own line format; see README.md) from stdin and reports problems. Details, outputs and exit statuses are specified in the README.{extra} {K.closer(rng)}",
        f"We keep chapter markers for {show} in plain text and people keep breaking them. Write the checker as a {ln} program, entry point {where}. README.md has the exact grammar and the problem codes.{extra} The checks I'll run follow the README to the letter.",
        f"need a {ln} CLI for chapter files, per README.md. input on stdin, results on stdout, exit codes matter.{extra} {K.closer(rng)}",
        f"Greenfield task: implement the `chapters` tool described in README.md ({ln}, entry point {where}). It is the validator for {show}'s chapter lists.{extra} Stick to the documented syntax and messages; the visible examples only cover a few of the rules.",
    ]
    return rng.choice(opts).strip()


@family("greenfield-chapters", category="greenfield", lang="mixed", kind="greenfield", n=10,
        summary="podcast chapter-list CLI (check / table / shift) with an invented line syntax, rules and exit codes")
def gen(rng, n):
    levels = [1, 2, 2, 3, 3, 3, 2, 3, 1, 3]
    spec = K.CliSpec("chapters")
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level)
        sols = {lang: sol(lang, p), "python": sol("python", p)}
        cases, nex = make_cases(rng, p, None)
        # examples text needs the recorded outputs: record with the python solution
        pt = K.merged(spec.skeleton("python"), spec.stub("python"), {spec.path("python"): sols["python"]})
        res = K.record_cli(spec, "python", pt, cases[:nex])
        ex = [(c, o[0]) for c, o in zip(cases[:nex], res)]
        for c, o in zip(cases[:nex], res):
            c.code = o[1]
        rd = readme(p, spec, lang, ex)
        yield K.cli_task(
            spec=spec, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex,
            prompt=prompt(rng, p, spec, lang, level), difficulty=level + (1 if level == 3 and i % 3 == 0 else 0),
            slug=f"{i + 1:02d}-{lang}-{p['show'].lower().replace(' ', '-').replace('&', 'and')}", tags=["cli", "parser", "exit-codes"],
            notes={"level": level, "open": p["open"], "close": p["close"], "tsep": p["tsep"]},
        )
