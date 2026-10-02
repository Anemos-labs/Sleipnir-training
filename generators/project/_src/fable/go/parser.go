package main

// Node is an AST node; which fields are used depends on Kind.
type Node struct {
	Kind    string
	Line    int
	Name    string
	Val     Value
	A, B    *Node
	List    []*Node
	Params  []string
	Body    []*Node
	Else    []*Node
	HasElse bool
}

type Parser struct {
	toks []Tok
	i    int
}

func (p *Parser) peek(k int) Tok {
	j := p.i + k
	if j >= len(p.toks) {
		j = len(p.toks) - 1
	}
	return p.toks[j]
}

func (p *Parser) next() Tok {
	t := p.toks[p.i]
	if t.Kind != "eof" {
		p.i++
	}
	return t
}

func (p *Parser) bad(t Tok) { fail(t.Line, "unexpected "+t.shown()) }

func (p *Parser) isOp(text string, k int) bool {
	t := p.peek(k)
	return t.Kind == "op" && t.Text == text
}

func (p *Parser) isKw(text string, k int) bool {
	t := p.peek(k)
	return t.Kind == "kw" && t.Text == text
}

func (p *Parser) expectOp(text string) Tok {
	t := p.next()
	if !(t.Kind == "op" && t.Text == text) {
		p.bad(t)
	}
	return t
}

func (p *Parser) expectKw(text string) Tok {
	t := p.next()
	if !(t.Kind == "kw" && t.Text == text) {
		p.bad(t)
	}
	return t
}

func (p *Parser) expectID() Tok {
	t := p.next()
	if t.Kind != "id" {
		p.bad(t)
	}
	return t
}

func (p *Parser) atSep() bool {
	t := p.peek(0)
	return t.Kind == "nl" || (t.Kind == "op" && t.Text == ";")
}

func (p *Parser) atEnd(stops ...string) bool {
	t := p.peek(0)
	if t.Kind == "eof" {
		return true
	}
	if t.Kind == "kw" {
		for _, s := range stops {
			if t.Text == s {
				return true
			}
		}
	}
	return false
}

func (p *Parser) block(stops ...string) []*Node {
	var stmts []*Node
	for {
		for p.atSep() {
			p.next()
		}
		if p.atEnd(stops...) {
			return stmts
		}
		stmts = append(stmts, p.statement())
		if !(p.atSep() || p.atEnd(stops...)) {
			p.bad(p.peek(0))
		}
	}
}

func (p *Parser) program() []*Node {
	stmts := p.block()
	if t := p.peek(0); t.Kind != "eof" {
		p.bad(t)
	}
	return stmts
}

func (p *Parser) statement() *Node {
	t := p.peek(0)
	if t.Kind == "kw" {
		switch t.Text {
		case "let":
			p.next()
			name := p.expectID()
			p.expectOp("=")
			return &Node{Kind: "let", Line: t.Line, Name: name.Text, A: p.expr()}
		case "fn":
			if p.peek(1).Kind == "id" {
				p.next()
				name := p.next()
				params, body := p.fnRest()
				return &Node{Kind: "fndef", Line: t.Line, Name: name.Text, Params: params, A: body}
			}
		case "print":
			p.next()
			return &Node{Kind: "print", Line: t.Line, A: p.expr()}
		case "return":
			p.next()
			if p.atSep() || p.atEnd("end", "else") {
				return &Node{Kind: "return", Line: t.Line}
			}
			return &Node{Kind: "return", Line: t.Line, A: p.expr()}
		case "while":
			p.next()
			cond := p.expr()
			p.expectKw("do")
			body := p.block("end")
			p.expectKw("end")
			return &Node{Kind: "while", Line: t.Line, A: cond, Body: body}
		case "for":
			p.next()
			v := p.expectID()
			p.expectKw("in")
			seq := p.expr()
			p.expectKw("do")
			body := p.block("end")
			p.expectKw("end")
			return &Node{Kind: "for", Line: t.Line, Name: v.Text, A: seq, Body: body}
		case "defer":
			p.next()
			return &Node{Kind: "defer", Line: t.Line, A: p.statement()}
		}
	}
	if t.Kind == "id" && p.isOp("=", 1) {
		p.next()
		p.next()
		return &Node{Kind: "assign", Line: t.Line, Name: t.Text, A: p.expr()}
	}
	return &Node{Kind: "expr", Line: t.Line, A: p.expr()}
}

func (p *Parser) fnRest() ([]string, *Node) {
	p.expectOp("(")
	var params []string
	if !p.isOp(")", 0) {
		params = append(params, p.expectID().Text)
		for p.isOp(",", 0) {
			p.next()
			params = append(params, p.expectID().Text)
		}
	}
	p.expectOp(")")
	p.expectOp("=>")
	return params, p.expr()
}

func (p *Parser) expr() *Node {
	left := p.or()
	for PIPE && p.isOp("|>", 0) {
		op := p.next()
		right := p.postfix()
		left = &Node{Kind: "pipe", Line: op.Line, A: left, B: right}
	}
	return left
}

func (p *Parser) or() *Node {
	left := p.and()
	for p.isKw("or", 0) {
		t := p.next()
		left = &Node{Kind: "or", Line: t.Line, A: left, B: p.and()}
	}
	return left
}

func (p *Parser) and() *Node {
	left := p.not()
	for p.isKw("and", 0) {
		t := p.next()
		left = &Node{Kind: "and", Line: t.Line, A: left, B: p.not()}
	}
	return left
}

func (p *Parser) not() *Node {
	if p.isKw("not", 0) {
		t := p.next()
		return &Node{Kind: "not", Line: t.Line, A: p.not()}
	}
	return p.cmp()
}

func (p *Parser) cmp() *Node {
	left := p.add()
	t := p.peek(0)
	if t.Kind == "op" {
		switch t.Text {
		case "==", "!=", "<", "<=", ">", ">=":
			p.next()
			return &Node{Kind: "bin", Line: t.Line, Name: t.Text, A: left, B: p.add()}
		}
	}
	return left
}

func (p *Parser) add() *Node {
	left := p.mul()
	for {
		t := p.peek(0)
		if t.Kind == "op" && (t.Text == "+" || t.Text == "-") {
			p.next()
			left = &Node{Kind: "bin", Line: t.Line, Name: t.Text, A: left, B: p.mul()}
		} else {
			return left
		}
	}
}

func (p *Parser) mul() *Node {
	left := p.unary()
	for {
		t := p.peek(0)
		if t.Kind == "op" && (t.Text == "*" || t.Text == "/" || t.Text == "%") {
			p.next()
			left = &Node{Kind: "bin", Line: t.Line, Name: t.Text, A: left, B: p.unary()}
		} else {
			return left
		}
	}
}

func (p *Parser) unary() *Node {
	if p.isOp("-", 0) {
		t := p.next()
		return &Node{Kind: "neg", Line: t.Line, A: p.unary()}
	}
	return p.postfix()
}

func (p *Parser) postfix() *Node {
	e := p.primary()
	for {
		if p.isOp("(", 0) {
			t := p.next()
			var args []*Node
			if !p.isOp(")", 0) {
				args = append(args, p.expr())
				for p.isOp(",", 0) {
					p.next()
					args = append(args, p.expr())
				}
			}
			p.expectOp(")")
			e = &Node{Kind: "call", Line: t.Line, A: e, List: args}
		} else if p.isOp("[", 0) {
			t := p.next()
			idx := p.expr()
			p.expectOp("]")
			e = &Node{Kind: "index", Line: t.Line, A: e, B: idx}
		} else {
			return e
		}
	}
}

func (p *Parser) primary() *Node {
	t := p.next()
	switch t.Kind {
	case "int", "str":
		return &Node{Kind: "lit", Line: t.Line, Val: t.Val}
	case "id":
		return &Node{Kind: "var", Line: t.Line, Name: t.Text}
	case "kw":
		switch t.Text {
		case "true":
			return &Node{Kind: "lit", Line: t.Line, Val: true}
		case "false":
			return &Node{Kind: "lit", Line: t.Line, Val: false}
		case "nil":
			return &Node{Kind: "lit", Line: t.Line, Val: nil}
		case "fn":
			params, body := p.fnRest()
			return &Node{Kind: "lambda", Line: t.Line, Params: params, A: body}
		case "if":
			cond := p.expr()
			p.expectKw("then")
			a := p.block("else", "end")
			n := &Node{Kind: "if", Line: t.Line, A: cond, Body: a}
			if p.isKw("else", 0) {
				p.next()
				n.Else = p.block("end")
				n.HasElse = true
			}
			p.expectKw("end")
			return n
		case "do":
			body := p.block("end")
			p.expectKw("end")
			return &Node{Kind: "do", Line: t.Line, Body: body}
		case "handle":
			tag := p.expectID()
			p.expectKw("with")
			h := p.expr()
			p.expectKw("in")
			body := p.block("end")
			p.expectKw("end")
			return &Node{Kind: "handle", Line: t.Line, Name: tag.Text, A: h, Body: body}
		case "emit":
			tag := p.expectID()
			return &Node{Kind: "emit", Line: t.Line, Name: tag.Text, A: p.expr()}
		}
	case "op":
		if t.Text == "(" {
			e := p.expr()
			p.expectOp(")")
			return e
		}
		if t.Text == "[" {
			var items []*Node
			if !p.isOp("]", 0) {
				items = append(items, p.expr())
				for p.isOp(",", 0) {
					p.next()
					items = append(items, p.expr())
				}
			}
			p.expectOp("]")
			return &Node{Kind: "list", Line: t.Line, List: items}
		}
	}
	p.bad(t)
	return nil
}
