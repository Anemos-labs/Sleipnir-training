package main

import (
	"regexp"
	"sort"
	"strings"
)

var pathChars = regexp.MustCompile(`^[A-Za-z0-9_./%-]+$`)

// Rule is one build rule; a rule whose target contains '%' is a pattern rule.
type Rule struct {
	target  string
	deps    []string
	action  string
	args    []string
	always  bool
	pattern bool
	pre     string
	suf     string
}

func (r *Rule) actionText() string {
	return strings.Join(append([]string{r.action}, r.args...), " ")
}

// match returns the stem if path matches this pattern rule.
func (r *Rule) match(path string) (string, bool) {
	if !r.pattern {
		return "", false
	}
	if len(path) > len(r.pre)+len(r.suf) && strings.HasPrefix(path, r.pre) && strings.HasSuffix(path, r.suf) {
		return path[len(r.pre) : len(path)-len(r.suf)], true
	}
	return "", false
}

func goodPath(p string, allowStem bool) bool {
	if !pathChars.MatchString(p) {
		return false
	}
	if strings.Contains(p, "%") && (!allowStem || strings.Count(p, "%") != 1) {
		return false
	}
	for _, seg := range strings.Split(p, "/") {
		if seg == "" || seg == "." || seg == ".." {
			return false
		}
	}
	return true
}

// parseRule parses the words after `rule`; on failure the error text is returned.
func parseRule(tokens []string) (*Rule, string) {
	syntax := "rule syntax: rule TARGET <- DEP... : ACTION [ARG...]"
	if len(tokens) < 3 || tokens[1] != "<-" {
		return nil, syntax
	}
	sep := -1
	for i := 2; i < len(tokens); i++ {
		if tokens[i] == ":" || (ALWAYS_RULES && tokens[i] == ":!") {
			sep = i
			break
		}
	}
	if sep < 0 || sep+1 >= len(tokens) {
		return nil, syntax
	}
	r := &Rule{target: tokens[0], deps: tokens[2:sep], always: tokens[sep] == ":!", action: tokens[sep+1], args: tokens[sep+2:]}
	for _, p := range append([]string{r.target}, r.deps...) {
		if !goodPath(p, PATTERNS) {
			return nil, "bad path '" + p + "'"
		}
	}
	if !strings.Contains(r.target, "%") {
		for _, d := range r.deps {
			if strings.Contains(d, "%") {
				return nil, "stem in dependency without stem in target"
			}
		}
	}
	if ok, msg := validAction(r.action, r.args); !ok {
		return nil, msg
	}
	if i := strings.Index(r.target, "%"); i >= 0 {
		r.pattern = true
		r.pre, r.suf = r.target[:i], r.target[i+1:]
	}
	return r, ""
}

// RuleBook holds the rules in declaration order.
type RuleBook struct {
	rules []*Rule
}

func (b *RuleBook) add(r *Rule) { b.rules = append(b.rules, r) }

func (b *RuleBook) hasTarget(target string) bool {
	for _, r := range b.rules {
		if r.target == target {
			return true
		}
	}
	return false
}

// lookup finds the rule for a path: an exact rule first, otherwise the pattern with the longest literal part
// (the earliest declared wins a tie). The dependencies come back with the stem filled in.
func (b *RuleBook) lookup(path string) (*Rule, []string) {
	for _, r := range b.rules {
		if !r.pattern && r.target == path {
			return r, append([]string(nil), r.deps...)
		}
	}
	var best *Rule
	stem := ""
	for _, r := range b.rules {
		s, ok := r.match(path)
		if !ok {
			continue
		}
		if best == nil || len(r.pre)+len(r.suf) > len(best.pre)+len(best.suf) {
			best, stem = r, s
		}
	}
	if best == nil {
		return nil, nil
	}
	deps := make([]string, len(best.deps))
	for i, d := range best.deps {
		deps[i] = strings.ReplaceAll(d, "%", stem)
	}
	return best, deps
}

// claimed returns the sorted existing files that a new rule target (exact or pattern) would claim.
func (b *RuleBook) claimed(target string, files map[string]*File) []string {
	var hits []string
	if !strings.Contains(target, "%") {
		if _, ok := files[target]; ok {
			hits = append(hits, target)
		}
		return hits
	}
	i := strings.Index(target, "%")
	pre, suf := target[:i], target[i+1:]
	for f := range files {
		if len(f) > len(pre)+len(suf) && strings.HasPrefix(f, pre) && strings.HasSuffix(f, suf) {
			hits = append(hits, f)
		}
	}
	sort.Strings(hits)
	return hits
}
