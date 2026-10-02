package main

import (
	"fmt"
	"math"
)

type returnSignal struct{ v Value }

// Env is a scope.
type Env struct {
	vars   map[string]Value
	parent *Env
}

func newEnv(parent *Env) *Env { return &Env{vars: map[string]Value{}, parent: parent} }

func (e *Env) find(name string) *Env {
	for s := e; s != nil; s = s.parent {
		if _, ok := s.vars[name]; ok {
			return s
		}
	}
	return nil
}

type handlerFrame struct {
	tag string
	fn  Value
}

// Interp evaluates a program.
type Interp struct {
	out      []string
	depth    int
	steps    int
	handlers []handlerFrame
	fnDepth  int
	globals  *Env
}

func newInterp() *Interp {
	it := &Interp{globals: newEnv(nil)}
	installBuiltins(it)
	return it
}

func checked(line int, ok bool) {
	if !ok {
		fail(line, "integer overflow")
	}
}

func (it *Interp) call(f Value, args []Value, line int) Value {
	switch fn := f.(type) {
	case *Closure:
		return it.callClosure(fn, args, line)
	case *Builtin:
		okCount := false
		for _, a := range fn.Arity {
			if a == len(args) {
				okCount = true
			}
		}
		if !okCount {
			exp := ""
			for i, a := range fn.Arity {
				if i > 0 {
					exp += " or "
				}
				exp += fmt.Sprint(a)
			}
			fail(line, fmt.Sprintf("wrong number of arguments for %s: expected %s, got %d", fn.Name, exp, len(args)))
		}
		return fn.Fn(it, line, args)
	}
	fail(line, "type error: "+typeName(f)+" is not callable")
	return nil
}

func (it *Interp) callClosure(f *Closure, args []Value, line int) (result Value) {
	if len(args) != len(f.Params) {
		name := f.Name
		if name == "" {
			name = "function"
		}
		fail(line, fmt.Sprintf("wrong number of arguments for %s: expected %d, got %d", name, len(f.Params), len(args)))
	}
	if it.depth >= DEPTH_LIMIT {
		fail(line, "call depth exceeded")
	}
	env := newEnv(f.Env)
	for i, p := range f.Params {
		env.vars[p] = args[i]
	}
	it.depth++
	it.fnDepth++
	defer func() {
		it.depth--
		it.fnDepth--
		if r := recover(); r != nil {
			if rs, ok := r.(returnSignal); ok {
				result = rs.v
				return
			}
			panic(r)
		}
	}()
	return it.eval(f.Body, env)
}

// runBlock runs statements in a new scope; the value is that of the last statement. Deferred statements run at exit.
func (it *Interp) runBlock(stmts []*Node, env *Env, scope bool) Value {
	inner := env
	if scope {
		inner = newEnv(env)
	}
	var deferred []*Node
	var value Value
	func() {
		defer func() {
			if r := recover(); r != nil {
				if _, ok := r.(returnSignal); ok {
					it.runDeferred(&deferred, inner)
				}
				panic(r)
			}
		}()
		for _, st := range stmts {
			value = it.exec(st, inner, &deferred)
		}
	}()
	it.runDeferred(&deferred, inner)
	return value
}

func (it *Interp) runDeferred(deferred *[]*Node, env *Env) {
	for len(*deferred) > 0 {
		last := len(*deferred) - 1
		stmt := (*deferred)[last]
		*deferred = (*deferred)[:last]
		var later []*Node
		it.exec(stmt, env, &later)
		it.runDeferred(&later, env)
	}
}

func (it *Interp) tick(line int) {
	it.steps++
	if it.steps > LOOP_LIMIT {
		fail(line, "step limit exceeded")
	}
}

func (it *Interp) exec(st *Node, env *Env, deferred *[]*Node) Value {
	switch st.Kind {
	case "expr":
		return it.eval(st.A, env)
	case "let":
		env.vars[st.Name] = it.eval(st.A, env)
	case "fndef":
		env.vars[st.Name] = &Closure{Name: st.Name, Params: st.Params, Body: st.A, Env: env}
	case "assign":
		v := it.eval(st.A, env)
		e := env.find(st.Name)
		if e == nil {
			fail(st.Line, "cannot assign to unbound variable '"+st.Name+"'")
		}
		e.vars[st.Name] = v
	case "print":
		it.out = append(it.out, show(it.eval(st.A, env), false))
	case "return":
		if it.fnDepth == 0 {
			fail(st.Line, "return outside function")
		}
		var v Value
		if st.A != nil {
			v = it.eval(st.A, env)
		}
		panic(returnSignal{v})
	case "defer":
		*deferred = append(*deferred, st.A)
	case "while":
		for truthy(it.eval(st.A, env)) {
			it.tick(st.Line)
			it.runBlock(st.Body, env, true)
		}
	case "for":
		seq := it.eval(st.A, env)
		var items []Value
		switch s := seq.(type) {
		case string:
			for i := 0; i < len(s); i++ {
				items = append(items, string(s[i]))
			}
		case []Value:
			items = append(items, s...)
		default:
			fail(st.Line, "type error: cannot iterate over "+typeName(seq))
		}
		for _, item := range items {
			it.tick(st.Line)
			inner := newEnv(env)
			inner.vars[st.Name] = item
			it.runBlock(st.Body, inner, true)
		}
	default:
		panic("unknown statement " + st.Kind)
	}
	return nil
}

func (it *Interp) eval(n *Node, env *Env) Value {
	switch n.Kind {
	case "lit":
		return n.Val
	case "var":
		e := env.find(n.Name)
		if e == nil {
			fail(n.Line, "unbound variable '"+n.Name+"'")
		}
		return e.vars[n.Name]
	case "bin":
		return it.binary(n, env)
	case "call":
		f := it.eval(n.A, env)
		args := make([]Value, len(n.List))
		for i, a := range n.List {
			args[i] = it.eval(a, env)
		}
		return it.call(f, args, n.Line)
	case "pipe":
		left := it.eval(n.A, env)
		right := n.B
		var f Value
		args := []Value{left}
		if right.Kind == "call" {
			f = it.eval(right.A, env)
			for _, a := range right.List {
				args = append(args, it.eval(a, env))
			}
		} else {
			f = it.eval(right, env)
		}
		return it.call(f, args, n.Line)
	case "if":
		if truthy(it.eval(n.A, env)) {
			return it.runBlock(n.Body, env, true)
		}
		if n.HasElse {
			return it.runBlock(n.Else, env, true)
		}
		return nil
	case "do":
		return it.runBlock(n.Body, env, true)
	case "lambda":
		return &Closure{Params: n.Params, Body: n.A, Env: env}
	case "list":
		items := make([]Value, len(n.List))
		for i, x := range n.List {
			items[i] = it.eval(x, env)
		}
		return items
	case "index":
		return it.index(n, env)
	case "and":
		left := it.eval(n.A, env)
		if truthy(left) {
			return it.eval(n.B, env)
		}
		return left
	case "or":
		left := it.eval(n.A, env)
		if truthy(left) {
			return left
		}
		return it.eval(n.B, env)
	case "not":
		return !truthy(it.eval(n.A, env))
	case "neg":
		v := it.eval(n.A, env)
		x, ok := v.(int64)
		if !ok {
			fail(n.Line, "type error: cannot apply '-' to "+typeName(v))
		}
		checked(n.Line, x != math.MinInt64)
		return -x
	case "emit":
		return it.evalEmit(n, env)
	case "handle":
		return it.evalHandle(n, env)
	}
	panic("unknown expression " + n.Kind)
}

func (it *Interp) evalEmit(n *Node, env *Env) Value {
	value := it.eval(n.A, env)
	idx := -1
	for i := len(it.handlers) - 1; i >= 0; i-- {
		if it.handlers[i].tag == n.Name {
			idx = i
			break
		}
	}
	if idx < 0 {
		fail(n.Line, "unhandled emit '"+n.Name+"'")
	}
	handler := it.handlers[idx].fn
	saved := it.handlers
	it.handlers = saved[:idx]
	defer func() { it.handlers = saved }()
	return it.call(handler, []Value{value}, n.Line)
}

func (it *Interp) evalHandle(n *Node, env *Env) Value {
	h := it.eval(n.A, env)
	switch h.(type) {
	case *Closure, *Builtin:
	default:
		fail(n.Line, "type error: "+typeName(h)+" is not callable")
	}
	nh := make([]handlerFrame, len(it.handlers)+1)
	copy(nh, it.handlers)
	nh[len(it.handlers)] = handlerFrame{tag: n.Name, fn: h}
	it.handlers = nh
	depth := len(nh)
	defer func() { it.handlers = it.handlers[:depth-1] }()
	return it.runBlock(n.Body, env, true)
}

func (it *Interp) binary(n *Node, env *Env) Value {
	op := n.Name
	a := it.eval(n.A, env)
	b := it.eval(n.B, env)
	ta, tb := typeName(a), typeName(b)
	switch op {
	case "==":
		return equal(a, b)
	case "!=":
		return !equal(a, b)
	case "<", "<=", ">", ">=":
		if ta == tb && ta == "int" {
			x, y := a.(int64), b.(int64)
			switch op {
			case "<":
				return x < y
			case "<=":
				return x <= y
			case ">":
				return x > y
			}
			return x >= y
		}
		if ta == tb && ta == "string" {
			x, y := a.(string), b.(string)
			switch op {
			case "<":
				return x < y
			case "<=":
				return x <= y
			case ">":
				return x > y
			}
			return x >= y
		}
	case "+":
		if ta == "int" && tb == "int" {
			x, y := a.(int64), b.(int64)
			c := x + y
			checked(n.Line, !((x > 0 && y > 0 && c < 0) || (x < 0 && y < 0 && c >= 0)))
			return c
		}
		if ta == tb && ta == "string" {
			return a.(string) + b.(string)
		}
		if ta == tb && ta == "list" {
			x, y := a.([]Value), b.([]Value)
			out := make([]Value, 0, len(x)+len(y))
			out = append(out, x...)
			return append(out, y...)
		}
	default:
		if ta == "int" && tb == "int" {
			x, y := a.(int64), b.(int64)
			switch op {
			case "-":
				c := x - y
				checked(n.Line, !((x >= 0 && y < 0 && c < 0) || (x < 0 && y > 0 && c >= 0)))
				return c
			case "*":
				c := x * y
				checked(n.Line, x == 0 || (c/x == y && !(x == -1 && y == math.MinInt64)))
				return c
			}
			if y == 0 {
				fail(n.Line, "division by zero")
			}
			if op == "/" {
				checked(n.Line, !(x == math.MinInt64 && y == -1))
				return x / y
			}
			if y == -1 {
				return int64(0)
			}
			return x % y
		}
	}
	fail(n.Line, fmt.Sprintf("type error: cannot apply '%s' to %s and %s", op, ta, tb))
	return nil
}

func (it *Interp) index(n *Node, env *Env) Value {
	seq := it.eval(n.A, env)
	iv := it.eval(n.B, env)
	ts, ti := typeName(seq), typeName(iv)
	if (ts != "list" && ts != "string") || ti != "int" {
		fail(n.Line, fmt.Sprintf("type error: cannot index %s with %s", ts, ti))
	}
	i := iv.(int64)
	var ln int64
	if s, ok := seq.(string); ok {
		ln = int64(len(s))
	} else {
		ln = int64(len(seq.([]Value)))
	}
	j := i
	if i < 0 {
		j = i + ln
	}
	if j < 0 || j >= ln {
		fail(n.Line, fmt.Sprintf("index out of range: %d (length %d)", i, ln))
	}
	if s, ok := seq.(string); ok {
		return string(s[j])
	}
	return seq.([]Value)[j]
}
