// Command-line front end: reads a script from standard input and prints what each command reports.
package main

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

var uintArg = regexp.MustCompile(`^[0-9]+$`)

func unescape(text string) string {
	var sb strings.Builder
	for i := 0; i < len(text); i++ {
		c := text[i]
		if c == '\\' && i+1 < len(text) && (text[i+1] == 'n' || text[i+1] == 't' || text[i+1] == '\\') {
			switch text[i+1] {
			case 'n':
				sb.WriteByte('\n')
			case 't':
				sb.WriteByte('\t')
			default:
				sb.WriteByte('\\')
			}
			i++
		} else {
			sb.WriteByte(c)
		}
	}
	return sb.String()
}

func escape(text string) string {
	text = strings.ReplaceAll(text, "\\", "\\\\")
	text = strings.ReplaceAll(text, "\n", "\\n")
	return strings.ReplaceAll(text, "\t", "\\t")
}

// Script runs commands and collects the output lines.
type Script struct {
	lines  []string
	errors int
	engine *Engine
}

func newScript() *Script {
	s := &Script{}
	s.engine = newEngine(s.emit)
	return s
}

func (s *Script) emit(line string) {
	s.lines = append(s.lines, line)
	if strings.HasPrefix(line, "fail ") || strings.HasPrefix(line, "error:") {
		s.errors++
	}
}

func (s *Script) err(msg string) { s.emit("error: " + msg) }

func (s *Script) cmdPut(rest string) {
	rest = strings.TrimLeft(rest, " ")
	path, text := rest, ""
	if i := strings.Index(rest, " "); i >= 0 {
		path, text = rest[:i], rest[i+1:]
	}
	if path == "" {
		s.err("usage: " + CMD_PUT + " PATH [TEXT]")
		return
	}
	if !goodPath(path, false) {
		s.err("bad path '" + path + "'")
		return
	}
	if s.engine.derived(path) {
		s.err("'" + path + "' is derived, not a source file")
		return
	}
	content := unescape(text)
	s.engine.put(path, content)
	s.emit(fmt.Sprintf("wrote %s (%d bytes)", path, len(content)))
}

func (s *Script) cmdRule(tokens []string) {
	r, msg := parseRule(tokens)
	if r == nil {
		s.err(msg)
		return
	}
	if s.engine.book.hasTarget(r.target) {
		s.err("duplicate rule for '" + r.target + "'")
		return
	}
	if hits := s.engine.book.claimed(r.target, s.engine.files); len(hits) > 0 {
		s.err("'" + hits[0] + "' already exists as a source file")
		return
	}
	s.engine.book.add(r)
	s.emit("rule " + r.target)
}

func (s *Script) cmdBuild(tokens []string) {
	keep, budget, i := false, -1, 0
	for i < len(tokens) && strings.HasPrefix(tokens[i], "-") {
		t := tokens[i]
		if (t == "--keep-going" || t == "-k") && KEEP_GOING {
			keep = true
		} else if t == "--max" && BUDGET {
			if i+1 >= len(tokens) || !uintArg.MatchString(tokens[i+1]) {
				bad := ""
				if i+1 < len(tokens) {
					bad = tokens[i+1]
				}
				s.err("bad --max value '" + bad + "'")
				return
			}
			n, err := strconv.Atoi(tokens[i+1])
			if err != nil {
				n = 1 << 30
			}
			budget = n
			i++
		} else {
			s.err("unknown option '" + t + "'")
			return
		}
		i++
	}
	targets := tokens[i:]
	if len(targets) == 0 {
		s.err(CMD_BUILD + " needs at least one target")
		return
	}
	for _, t := range targets {
		if !goodPath(t, false) {
			s.err("bad path '" + t + "'")
			return
		}
	}
	s.engine.build(targets, keep, budget, SUMMARY)
}

func (s *Script) cmdStatus(tokens []string) {
	if len(tokens) == 0 {
		s.err("status needs at least one target")
		return
	}
	for _, t := range tokens {
		if !goodPath(t, false) {
			s.err("bad path '" + t + "'")
			return
		}
	}
	s.engine.status(tokens)
}

func (s *Script) one(tokens []string, usage string) (*File, bool) {
	if len(tokens) != 1 {
		s.err("usage: " + usage + " PATH")
		return nil, false
	}
	f, ok := s.engine.files[tokens[0]]
	if !ok {
		s.err("no such file '" + tokens[0] + "'")
		return nil, false
	}
	return f, true
}

func (s *Script) cmdShow(tokens []string) {
	if f, ok := s.one(tokens, "show"); ok {
		s.emit(fmt.Sprintf("%s = \"%s\"", tokens[0], escape(f.content)))
	}
}

func (s *Script) cmdDigest(tokens []string) {
	if f, ok := s.one(tokens, "digest"); ok {
		s.emit(tokens[0] + " " + digest(f.content))
	}
}

func (s *Script) cmdTouch(tokens []string) {
	if _, ok := s.one(tokens, "touch"); ok {
		s.engine.touch(tokens[0])
		s.emit("touched " + tokens[0])
	}
}

func (s *Script) cmdClean(tokens []string) {
	for _, t := range tokens {
		if _, ok := s.engine.files[t]; !ok || !s.engine.derived(t) {
			s.err("'" + t + "' is not a derived file")
			return
		}
	}
	var paths []string
	if len(tokens) > 0 {
		seen := map[string]bool{}
		for _, t := range tokens {
			if !seen[t] {
				seen[t] = true
				paths = append(paths, t)
			}
		}
		sort.Strings(paths)
	}
	s.emit(fmt.Sprintf("cleaned %d files", s.engine.clean(paths)))
}

func (s *Script) cmdLs() {
	for _, p := range s.engine.sortedPaths() {
		kind := "source"
		if s.engine.derived(p) {
			kind = "derived"
		}
		s.emit(p + " " + digest(s.engine.files[p].content) + " " + kind)
	}
}

func (s *Script) cmdStats() {
	e := s.engine
	s.emit(fmt.Sprintf("files=%d rules=%d actions=%d clock=%d", len(e.files), len(e.book.rules), e.actionsRun, e.clock))
}

func (s *Script) runLine(raw string) {
	line := strings.TrimSpace(raw)
	if line == "" || strings.HasPrefix(line, "#") {
		return
	}
	cmd, rest := line, ""
	if i := strings.Index(line, " "); i >= 0 {
		cmd, rest = line[:i], line[i+1:]
	}
	tokens := strings.Fields(rest)
	switch {
	case cmd == CMD_PUT:
		s.cmdPut(rest)
	case cmd == "rule":
		s.cmdRule(tokens)
	case cmd == CMD_BUILD:
		s.cmdBuild(tokens)
	case cmd == "show":
		s.cmdShow(tokens)
	case cmd == "digest":
		s.cmdDigest(tokens)
	case cmd == "ls":
		s.cmdLs()
	case cmd == "stats":
		s.cmdStats()
	case cmd == "status" && HAS_STATUS:
		s.cmdStatus(tokens)
	case cmd == "clean" && HAS_CLEAN:
		s.cmdClean(tokens)
	case cmd == "touch" && HAS_TOUCH:
		s.cmdTouch(tokens)
	default:
		s.err("unknown command '" + cmd + "'")
	}
}

func main() {
	data, _ := io.ReadAll(bufio.NewReader(os.Stdin))
	s := newScript()
	for _, raw := range strings.Split(string(data), "\n") {
		s.runLine(raw)
	}
	w := bufio.NewWriter(os.Stdout)
	for _, ln := range s.lines {
		w.WriteString(ln + "\n")
	}
	w.Flush()
	if s.errors > 0 {
		os.Exit(1)
	}
}
