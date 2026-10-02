package main

import (
	"regexp"
	"strconv"
	"strings"
)

var intRe = regexp.MustCompile(`^-?[0-9]{1,18}$`)

func badArg(line int, name string) { fail(line, "type error: bad argument to "+name) }

func installBuiltins(it *Interp) {
	reg := func(name string, arity []int, fn func(it *Interp, line int, a []Value) Value) {
		for _, b := range BUILTINS {
			if b == name {
				it.globals.vars[name] = &Builtin{Name: name, Arity: arity, Fn: fn}
			}
		}
	}
	reg("len", []int{1}, func(it *Interp, line int, a []Value) Value {
		switch x := a[0].(type) {
		case string:
			return int64(len(x))
		case []Value:
			return int64(len(x))
		}
		badArg(line, "len")
		return nil
	})
	reg("str", []int{1}, func(it *Interp, line int, a []Value) Value { return show(a[0], false) })
	reg("int", []int{1}, func(it *Interp, line int, a []Value) Value {
		switch x := a[0].(type) {
		case int64:
			return x
		case string:
			if intRe.MatchString(x) {
				v, _ := strconv.ParseInt(x, 10, 64)
				return v
			}
			fail(line, "cannot convert '"+x+"' to int")
		}
		badArg(line, "int")
		return nil
	})
	reg("push", []int{2}, func(it *Interp, line int, a []Value) Value {
		xs, ok := a[0].([]Value)
		if !ok {
			badArg(line, "push")
		}
		out := make([]Value, 0, len(xs)+1)
		out = append(out, xs...)
		return append(out, a[1])
	})
	reg("range", []int{1, 2}, func(it *Interp, line int, a []Value) Value {
		var nums []int64
		for _, x := range a {
			v, ok := x.(int64)
			if !ok {
				badArg(line, "range")
			}
			nums = append(nums, v)
		}
		lo, hi := int64(0), nums[0]
		if len(nums) == 2 {
			lo, hi = nums[0], nums[1]
		}
		if hi-lo > 10000 {
			fail(line, "range too large")
		}
		out := []Value{}
		for v := lo; v < hi; v++ {
			out = append(out, v)
		}
		return out
	})
	reg("map", []int{2}, func(it *Interp, line int, a []Value) Value {
		xs, ok := a[0].([]Value)
		if !ok {
			badArg(line, "map")
		}
		out := make([]Value, 0, len(xs))
		for _, x := range xs {
			out = append(out, it.call(a[1], []Value{x}, line))
		}
		return out
	})
	reg("filter", []int{2}, func(it *Interp, line int, a []Value) Value {
		xs, ok := a[0].([]Value)
		if !ok {
			badArg(line, "filter")
		}
		out := []Value{}
		for _, x := range xs {
			if truthy(it.call(a[1], []Value{x}, line)) {
				out = append(out, x)
			}
		}
		return out
	})
	reg("fold", []int{3}, func(it *Interp, line int, a []Value) Value {
		xs, ok := a[0].([]Value)
		if !ok {
			badArg(line, "fold")
		}
		acc := a[1]
		for _, x := range xs {
			acc = it.call(a[2], []Value{acc, x}, line)
		}
		return acc
	})
	reg("join", []int{2}, func(it *Interp, line int, a []Value) Value {
		xs, ok := a[0].([]Value)
		sep, ok2 := a[1].(string)
		if !ok || !ok2 {
			badArg(line, "join")
		}
		parts := make([]string, len(xs))
		for i, x := range xs {
			parts[i] = show(x, false)
		}
		return strings.Join(parts, sep)
	})
	reg("split", []int{2}, func(it *Interp, line int, a []Value) Value {
		s, ok := a[0].(string)
		sep, ok2 := a[1].(string)
		if !ok || !ok2 || sep == "" {
			badArg(line, "split")
		}
		out := []Value{}
		for _, p := range strings.Split(s, sep) {
			out = append(out, p)
		}
		return out
	})
	reg("upper", []int{1}, func(it *Interp, line int, a []Value) Value {
		s, ok := a[0].(string)
		if !ok {
			badArg(line, "upper")
		}
		b := []byte(s)
		for i, c := range b {
			if c >= 'a' && c <= 'z' {
				b[i] = c - 32
			}
		}
		return string(b)
	})
	reg("slice", []int{3}, func(it *Interp, line int, a []Value) Value {
		lo, ok1 := a[1].(int64)
		hi, ok2 := a[2].(int64)
		if !ok1 || !ok2 {
			badArg(line, "slice")
		}
		clamp := func(v, n int64) int64 {
			if v < 0 {
				return 0
			}
			if v > n {
				return n
			}
			return v
		}
		switch x := a[0].(type) {
		case string:
			l, h := clamp(lo, int64(len(x))), clamp(hi, int64(len(x)))
			if l >= h {
				return ""
			}
			return x[l:h]
		case []Value:
			l, h := clamp(lo, int64(len(x))), clamp(hi, int64(len(x)))
			if l >= h {
				return []Value{}
			}
			out := make([]Value, h-l)
			copy(out, x[l:h])
			return out
		}
		badArg(line, "slice")
		return nil
	})
}
