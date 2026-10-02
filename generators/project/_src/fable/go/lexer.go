package main

import (
	"fmt"
	"strconv"
)

// FableError is a parse or runtime error at a line.
type FableError struct {
	Line int
	Msg  string
}

func fail(line int, msg string) {
	panic(&FableError{Line: line, Msg: msg})
}

// Tok is a token: kind is int, str, id, kw, op, nl or eof.
type Tok struct {
	Kind string
	Text string
	Line int
	Val  Value
}

func (t Tok) shown() string {
	switch t.Kind {
	case "nl":
		return "end of line"
	case "eof":
		return "end of input"
	case "str":
		return "a string"
	}
	return "'" + t.Text + "'"
}

var keywords = map[string]bool{"let": true, "fn": true, "if": true, "then": true, "else": true, "end": true, "while": true, "do": true, "for": true, "in": true,
	"return": true, "and": true, "or": true, "not": true, "true": true, "false": true, "nil": true, "emit": true, "handle": true, "with": true, "print": true}

// a newline directly after one of these tokens does not end a statement
var suppress = map[string]bool{"(": true, "[": true, ",": true, "=": true, "=>": true, "then": true, "else": true, "do": true, "with": true, "in": true, "and": true, "or": true,
	"not": true, "+": true, "-": true, "*": true, "/": true, "%": true, "==": true, "!=": true, "<": true, "<=": true, ">": true, ">=": true, "|>": true}

const maxInt = int64(9223372036854775807)

func isDigit(c byte) bool { return c >= '0' && c <= '9' }
func isAlpha(c byte) bool { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_' }

func twoOp(s string) bool {
	switch s {
	case "==", "!=", "<=", ">=", "=>":
		return true
	case "|>":
		return PIPE
	}
	return false
}

func lex(src string) []Tok {
	if DEFER {
		keywords["defer"] = true
	}
	var toks []Tok
	i, n, line, depth := 0, len(src), 1, 0
	add := func(kind, text string, val Value) {
		toks = append(toks, Tok{Kind: kind, Text: text, Line: line, Val: val})
	}
	for i < n {
		c := src[i]
		switch {
		case c == '\n':
			if depth == 0 && len(toks) > 0 && toks[len(toks)-1].Kind != "nl" {
				last := toks[len(toks)-1]
				if !((last.Kind == "op" || last.Kind == "kw") && suppress[last.Text]) {
					add("nl", "\n", nil)
				}
			}
			line++
			i++
		case c == ' ' || c == '\t' || c == '\r':
			i++
		case c == '#':
			for i < n && src[i] != '\n' {
				i++
			}
		case isDigit(c):
			j := i
			for j < n && isDigit(src[j]) {
				j++
			}
			v, err := strconv.ParseInt(src[i:j], 10, 64)
			if err != nil {
				fail(line, "integer too large")
			}
			add("int", src[i:j], v)
			i = j
		case c == '"':
			j := i + 1
			var buf []byte
			for {
				if j >= n || src[j] == '\n' {
					fail(line, "unterminated string")
				}
				ch := src[j]
				if ch == '"' {
					break
				}
				if ch == '\\' {
					if j+1 >= n {
						fail(line, "bad escape")
					}
					switch src[j+1] {
					case 'n':
						buf = append(buf, '\n')
					case 't':
						buf = append(buf, '\t')
					case 'r':
						buf = append(buf, '\r')
					case '"':
						buf = append(buf, '"')
					case '\\':
						buf = append(buf, '\\')
					default:
						fail(line, "bad escape")
					}
					j += 2
				} else {
					buf = append(buf, ch)
					j++
				}
			}
			add("str", src[i:j+1], string(buf))
			i = j + 1
		case isAlpha(c):
			j := i
			for j < n && (isAlpha(src[j]) || isDigit(src[j])) {
				j++
			}
			w := src[i:j]
			if keywords[w] {
				add("kw", w, nil)
			} else {
				add("id", w, nil)
			}
			i = j
		case i+1 < n && twoOp(src[i:i+2]):
			add("op", src[i:i+2], nil)
			i += 2
		case c == '+' || c == '-' || c == '*' || c == '/' || c == '%' || c == '<' || c == '>' || c == '=' || c == '(' || c == ')' || c == '[' || c == ']' || c == ',' || c == ';':
			if c == '(' || c == '[' {
				depth++
			} else if (c == ')' || c == ']') && depth > 0 {
				depth--
			}
			add("op", string(c), nil)
			i++
		default:
			fail(line, fmt.Sprintf("bad character '%c'", c))
		}
	}
	add("eof", "", nil)
	return toks
}
