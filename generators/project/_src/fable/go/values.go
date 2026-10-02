package main

import (
	"strconv"
	"strings"
)

// Value is a Fable value: nil, bool, int64, string, []Value (a list), *Closure or *Builtin.
type Value interface{}

// Closure is a user function with its defining scope.
type Closure struct {
	Name   string
	Params []string
	Body   *Node
	Env    *Env
}

// Builtin is a function provided by the interpreter.
type Builtin struct {
	Name  string
	Arity []int
	Fn    func(it *Interp, line int, a []Value) Value
}

func typeName(v Value) string {
	switch v.(type) {
	case nil:
		return "nil"
	case bool:
		return "bool"
	case int64:
		return "int"
	case string:
		return "string"
	case []Value:
		return "list"
	}
	return "function"
}

func equal(a, b Value) bool {
	ta, tb := typeName(a), typeName(b)
	if ta != tb {
		return false
	}
	switch ta {
	case "list":
		x, y := a.([]Value), b.([]Value)
		if len(x) != len(y) {
			return false
		}
		for i := range x {
			if !equal(x[i], y[i]) {
				return false
			}
		}
		return true
	case "function":
		return a == b
	case "nil":
		return true
	}
	return a == b
}

func quote(s string) string {
	s = strings.ReplaceAll(s, "\\", "\\\\")
	s = strings.ReplaceAll(s, "\"", "\\\"")
	s = strings.ReplaceAll(s, "\n", "\\n")
	s = strings.ReplaceAll(s, "\t", "\\t")
	s = strings.ReplaceAll(s, "\r", "\\r")
	return "\"" + s + "\""
}

func show(v Value, nested bool) string {
	switch x := v.(type) {
	case nil:
		return "nil"
	case bool:
		if x {
			return "true"
		}
		return "false"
	case int64:
		return strconv.FormatInt(x, 10)
	case string:
		if nested {
			return quote(x)
		}
		return x
	case []Value:
		parts := make([]string, len(x))
		for i, e := range x {
			parts[i] = show(e, true)
		}
		return "[" + strings.Join(parts, ", ") + "]"
	case *Builtin:
		return "<builtin " + x.Name + ">"
	case *Closure:
		if x.Name != "" {
			return "<fn " + x.Name + ">"
		}
		return "<fn>"
	}
	return "?"
}

func truthy(v Value) bool {
	if v == nil {
		return false
	}
	if b, ok := v.(bool); ok {
		return b
	}
	return true
}
