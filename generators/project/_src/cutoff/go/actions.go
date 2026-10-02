package main

import (
	"errors"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

var (
	intRe  = regexp.MustCompile(`^-?[0-9]{1,9}$`)
	uintRe = regexp.MustCompile(`^[0-9]{1,9}$`)
	nameRe = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9]*$`)
)

// splitLines splits on newlines and drops one empty last segment ("" has no lines, "a\n" has one).
func splitLines(text string) []string {
	parts := strings.Split(text, "\n")
	if parts[len(parts)-1] == "" {
		parts = parts[:len(parts)-1]
	}
	return parts
}

func asciiUpper(text string) string {
	b := []byte(text)
	for i, c := range b {
		if c >= 'a' && c <= 'z' {
			b[i] = c - 32
		}
	}
	return string(b)
}

func asciiLower(text string) string {
	b := []byte(text)
	for i, c := range b {
		if c >= 'A' && c <= 'Z' {
			b[i] = c + 32
		}
	}
	return string(b)
}

func total(text string) int {
	sum := 0
	for _, tok := range strings.Fields(text) {
		if intRe.MatchString(tok) {
			n, _ := strconv.Atoi(tok)
			sum += n
		}
	}
	return sum
}

func actionEnabled(name string) bool {
	for _, a := range ACTIONS {
		if a == name {
			return true
		}
	}
	return false
}

// validAction reports whether name is an enabled action that accepts args; otherwise the error text.
func validAction(name string, args []string) (bool, string) {
	if !actionEnabled(name) {
		return false, "unknown action '" + name + "'"
	}
	ok := true
	switch name {
	case "head", "cap":
		ok = len(args) == 1 && uintRe.MatchString(args[0])
	case "grep", "failif":
		ok = len(args) == 1
	case "tag":
		ok = len(args) == 1 && nameRe.MatchString(args[0])
	case "const":
		ok = true
	default:
		ok = len(args) == 0
	}
	if !ok {
		return false, "bad arguments for '" + name + "'"
	}
	return true, ""
}

// runAction computes the output of an action from the contents of its inputs.
func runAction(name string, args []string, inputs []string) (string, error) {
	text := strings.Join(inputs, "\n")
	switch name {
	case "cat":
		return text, nil
	case "upper":
		return asciiUpper(text), nil
	case "lower":
		return asciiLower(text), nil
	case "rev":
		b := []byte(text)
		for i, j := 0, len(b)-1; i < j; i, j = i+1, j-1 {
			b[i], b[j] = b[j], b[i]
		}
		return string(b), nil
	case "count":
		return strconv.Itoa(len(text)), nil
	case "lines":
		return strconv.Itoa(len(splitLines(text))), nil
	case "head":
		n, _ := strconv.Atoi(args[0])
		ls := splitLines(text)
		if n < len(ls) {
			ls = ls[:n]
		}
		return strings.Join(ls, "\n"), nil
	case "sort":
		ls := splitLines(text)
		sort.Strings(ls)
		return strings.Join(ls, "\n"), nil
	case "uniq":
		var out []string
		for _, ln := range splitLines(text) {
			if len(out) == 0 || out[len(out)-1] != ln {
				out = append(out, ln)
			}
		}
		return strings.Join(out, "\n"), nil
	case "grep":
		var out []string
		for _, ln := range splitLines(text) {
			if strings.Contains(ln, args[0]) {
				out = append(out, ln)
			}
		}
		return strings.Join(out, "\n"), nil
	case "tag":
		return "<" + args[0] + ">" + text + "</" + args[0] + ">", nil
	case "sum":
		return strconv.Itoa(total(text)), nil
	case "cap":
		n, _ := strconv.Atoi(args[0])
		t := total(text)
		if n < t {
			t = n
		}
		return strconv.Itoa(t), nil
	case "const":
		return strings.Join(args, " "), nil
	case "failif":
		if strings.Contains(text, args[0]) {
			return "", errors.New("found " + args[0])
		}
		return text, nil
	case "fail":
		return "", errors.New("always fails")
	}
	return "", errors.New("unknown action")
}
