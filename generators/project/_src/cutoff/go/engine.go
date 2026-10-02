package main

import (
	"fmt"
	"sort"
	"strings"
)

// File is one entry of the store.
type File struct {
	content string
	stamp   int    // logical clock value of the last write
	key     string // digest mode: key of the action run that produced it ("" for sources)
}

// buildState is the state of one build command.
type buildState struct {
	keepGoing                                bool
	budget                                   int // -1: unlimited
	memo                                     map[string]string
	stack                                    []string
	ran, same, skipped, failed, blocked, run int
	aborted                                  bool
}

// Engine is the file store plus the rules.
type Engine struct {
	emit       func(line string)
	files      map[string]*File
	book       *RuleBook
	clock      int
	actionsRun int
}

func newEngine(emit func(string)) *Engine {
	return &Engine{emit: emit, files: map[string]*File{}, book: &RuleBook{}}
}

func (e *Engine) derived(path string) bool {
	r, _ := e.book.lookup(path)
	return r != nil
}

func (e *Engine) tick() int {
	e.clock++
	return e.clock
}

func (e *Engine) keyOf(r *Rule, deps []string) string {
	parts := make([]string, len(deps))
	for i, d := range deps {
		parts[i] = digest(e.files[d].content)
	}
	return digest(r.actionText() + "\x1f" + strings.Join(parts, ","))
}

func (e *Engine) put(path, content string) {
	e.files[path] = &File{content: content, stamp: e.tick()}
}

func (e *Engine) touch(path string) { e.files[path].stamp = e.tick() }

// clean removes the given derived files, or every derived file when paths is nil.
func (e *Engine) clean(paths []string) int {
	if paths == nil {
		for p := range e.files {
			if e.derived(p) {
				paths = append(paths, p)
			}
		}
	}
	for _, p := range paths {
		delete(e.files, p)
	}
	return len(paths)
}

func (e *Engine) build(targets []string, keepGoing bool, budget int, summary string) {
	st := &buildState{keepGoing: keepGoing, budget: budget, memo: map[string]string{}}
	for _, t := range targets {
		if st.aborted {
			break
		}
		e.visit(t, "", st)
	}
	e.emit(fmt.Sprintf("%s: ran=%d same=%d skipped=%d failed=%d blocked=%d", summary, st.ran, st.same, st.skipped, st.failed, st.blocked))
}

func (e *Engine) fail(st *buildState, line string) {
	e.emit(line)
	st.failed++
	if !st.keepGoing {
		st.aborted = true
	}
}

func indexOf(list []string, s string) int {
	for i, x := range list {
		if x == s {
			return i
		}
	}
	return -1
}

func needed(requester string) string {
	if requester == "" {
		return ""
	}
	return " (needed by '" + requester + "')"
}

// visit brings one path up to date (once per build command) and returns its status:
// source, fresh, built, failed or blocked.
func (e *Engine) visit(path, requester string, st *buildState) string {
	if s, ok := st.memo[path]; ok {
		return s
	}
	rule, deps := e.book.lookup(path)
	if rule == nil {
		if _, ok := e.files[path]; ok {
			st.memo[path] = "source"
			return "source"
		}
		e.fail(st, "error: no rule to make '"+path+"'"+needed(requester))
		st.memo[path] = "failed"
		return "failed"
	}
	if i := indexOf(st.stack, path); i >= 0 {
		cyc := append(append([]string(nil), st.stack[i:]...), path)
		e.fail(st, "error: cycle "+strings.Join(cyc, " -> "))
		return "failed"
	}
	st.stack = append(st.stack, path)
	bad := false
	for _, d := range deps {
		if st.aborted {
			break
		}
		if s := e.visit(d, path, st); s == "failed" || s == "blocked" {
			bad = true
		}
	}
	st.stack = st.stack[:len(st.stack)-1]
	if st.aborted {
		return "failed"
	}
	if bad {
		e.emit("blocked " + path)
		st.blocked++
		st.memo[path] = "blocked"
		return "blocked"
	}
	f := e.files[path]
	key := e.keyOf(rule, deps)
	stale := false
	if MODE == "digest" {
		stale = f == nil || f.key != key
	} else {
		stale = f == nil
		for _, d := range deps {
			if f != nil && e.files[d].stamp > f.stamp {
				stale = true
			}
		}
	}
	if rule.always {
		stale = true
	}
	if !stale {
		e.emit("skip " + path)
		st.skipped++
		st.memo[path] = "fresh"
		return "fresh"
	}
	if st.budget >= 0 && st.run >= st.budget {
		e.emit(fmt.Sprintf("halt: budget of %d actions reached", st.budget))
		st.aborted = true
		return "failed"
	}
	st.run++
	e.actionsRun++
	inputs := make([]string, len(deps))
	for i, d := range deps {
		inputs[i] = e.files[d].content
	}
	out, err := runAction(rule.action, rule.args, inputs)
	if err != nil {
		e.fail(st, fmt.Sprintf("fail %s: %s", path, err.Error()))
		st.memo[path] = "failed"
		return "failed"
	}
	same := f != nil && f.content == out
	e.files[path] = &File{content: out, stamp: e.tick(), key: key}
	if same {
		e.emit("same " + path)
		st.same++
	} else {
		e.emit("run " + path)
		st.ran++
	}
	st.memo[path] = "built"
	return "built"
}

// status reports fresh / stale for every rule-made path below the targets without running any action.
func (e *Engine) status(targets []string) {
	memo := map[string]string{}
	var stack []string
	var walk func(path, requester string) string
	walk = func(path, requester string) string {
		if s, ok := memo[path]; ok {
			return s
		}
		rule, deps := e.book.lookup(path)
		if rule == nil {
			if _, ok := e.files[path]; ok {
				memo[path] = "source"
			} else {
				e.emit("error: no rule to make '" + path + "'" + needed(requester))
				memo[path] = "error"
			}
			return memo[path]
		}
		if i := indexOf(stack, path); i >= 0 {
			cyc := append(append([]string(nil), stack[i:]...), path)
			e.emit("error: cycle " + strings.Join(cyc, " -> "))
			return "error"
		}
		stack = append(stack, path)
		states := make([]string, len(deps))
		for i, d := range deps {
			states[i] = walk(d, path)
		}
		stack = stack[:len(stack)-1]
		for _, s := range states {
			if s == "error" {
				memo[path] = "error"
				return "error"
			}
		}
		f := e.files[path]
		firstStale := ""
		for i, d := range deps {
			if states[i] == "stale" {
				firstStale = d
				break
			}
		}
		reason := ""
		switch {
		case f == nil:
			reason = "missing"
		case firstStale != "":
			reason = "dep " + firstStale
		case rule.always:
			reason = "always"
		default:
			changed := false
			if MODE == "digest" {
				changed = f.key != e.keyOf(rule, deps)
			} else {
				for _, d := range deps {
					if e.files[d].stamp > f.stamp {
						changed = true
					}
				}
			}
			if changed {
				reason = "changed"
			}
		}
		if reason == "" {
			e.emit("fresh " + path)
			memo[path] = "fresh"
		} else {
			e.emit("stale " + path + " (" + reason + ")")
			memo[path] = "stale"
		}
		return memo[path]
	}
	for _, t := range targets {
		walk(t, "")
	}
}

func (e *Engine) sortedPaths() []string {
	var ps []string
	for p := range e.files {
		ps = append(ps, p)
	}
	sort.Strings(ps)
	return ps
}
