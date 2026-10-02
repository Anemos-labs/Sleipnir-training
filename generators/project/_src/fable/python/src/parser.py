"""Recursive-descent parser: tokens -> AST (tuples whose second item is the line of the deciding token)."""
import config as C
from lexer import FableError

CMP = ("==", "!=", "<", "<=", ">", ">=")


class Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    def peek(self, k=0):
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def next(self):
        t = self.toks[self.i]
        if t.kind != "eof":
            self.i += 1
        return t

    def bad(self, t):
        raise FableError(t.line, "unexpected " + t.shown())

    def is_op(self, text, k=0):
        t = self.peek(k)
        return t.kind == "op" and t.text == text

    def is_kw(self, text, k=0):
        t = self.peek(k)
        return t.kind == "kw" and t.text == text

    def expect_op(self, text):
        t = self.next()
        if not (t.kind == "op" and t.text == text):
            self.bad(t)
        return t

    def expect_kw(self, text):
        t = self.next()
        if not (t.kind == "kw" and t.text == text):
            self.bad(t)
        return t

    def expect_id(self):
        t = self.next()
        if t.kind != "id":
            self.bad(t)
        return t

    # -- blocks and statements ------------------------------------------------------------------------------------
    def at_sep(self):
        t = self.peek()
        return t.kind == "nl" or (t.kind == "op" and t.text == ";")

    def at_end(self, stops):
        t = self.peek()
        return t.kind == "eof" or (t.kind == "kw" and t.text in stops)

    def block(self, stops):
        stmts = []
        while True:
            while self.at_sep():
                self.next()
            if self.at_end(stops):
                return stmts
            stmts.append(self.statement())
            if not (self.at_sep() or self.at_end(stops)):
                self.bad(self.peek())

    def program(self):
        stmts = self.block(())
        t = self.peek()
        if t.kind != "eof":
            self.bad(t)
        return stmts

    def statement(self):
        t = self.peek()
        if t.kind == "kw":
            w = t.text
            if w == "let":
                self.next()
                name = self.expect_id()
                self.expect_op("=")
                return ("let", t.line, name.text, self.expr())
            if w == "fn" and self.peek(1).kind == "id":
                self.next()
                name = self.next()
                params, body = self.fn_rest()
                return ("fndef", t.line, name.text, params, body)
            if w == "print":
                self.next()
                return ("print", t.line, self.expr())
            if w == "return":
                self.next()
                if self.at_sep() or self.at_end(("end", "else")):
                    return ("return", t.line, None)
                return ("return", t.line, self.expr())
            if w == "while":
                self.next()
                cond = self.expr()
                self.expect_kw("do")
                body = self.block(("end",))
                self.expect_kw("end")
                return ("while", t.line, cond, body)
            if w == "for":
                self.next()
                var = self.expect_id()
                self.expect_kw("in")
                seq = self.expr()
                self.expect_kw("do")
                body = self.block(("end",))
                self.expect_kw("end")
                return ("for", t.line, var.text, seq, body)
            if w == "defer":
                self.next()
                return ("defer", t.line, self.statement())
        if t.kind == "id" and self.is_op("=", 1):
            self.next()
            self.next()
            return ("assign", t.line, t.text, self.expr())
        return ("expr", t.line, self.expr())

    def fn_rest(self):
        self.expect_op("(")
        params = []
        if not self.is_op(")"):
            params.append(self.expect_id().text)
            while self.is_op(","):
                self.next()
                params.append(self.expect_id().text)
        self.expect_op(")")
        self.expect_op("=>")
        return params, self.expr()

    # -- expressions ------------------------------------------------------------------------------------------------
    def expr(self):
        left = self.or_()
        while C.PIPE and self.is_op("|>"):
            op = self.next()
            right = self.postfix()
            left = ("pipe", op.line, left, right)
        return left

    def or_(self):
        left = self.and_()
        while self.is_kw("or"):
            t = self.next()
            left = ("or", t.line, left, self.and_())
        return left

    def and_(self):
        left = self.not_()
        while self.is_kw("and"):
            t = self.next()
            left = ("and", t.line, left, self.not_())
        return left

    def not_(self):
        if self.is_kw("not"):
            t = self.next()
            return ("not", t.line, self.not_())
        return self.cmp()

    def cmp(self):
        left = self.add()
        t = self.peek()
        if t.kind == "op" and t.text in CMP:
            self.next()
            return ("bin", t.line, t.text, left, self.add())
        return left

    def add(self):
        left = self.mul()
        while self.peek().kind == "op" and self.peek().text in ("+", "-"):
            t = self.next()
            left = ("bin", t.line, t.text, left, self.mul())
        return left

    def mul(self):
        left = self.unary()
        while self.peek().kind == "op" and self.peek().text in ("*", "/", "%"):
            t = self.next()
            left = ("bin", t.line, t.text, left, self.unary())
        return left

    def unary(self):
        if self.is_op("-"):
            t = self.next()
            return ("neg", t.line, self.unary())
        return self.postfix()

    def postfix(self):
        e = self.primary()
        while True:
            if self.is_op("("):
                t = self.next()
                args = []
                if not self.is_op(")"):
                    args.append(self.expr())
                    while self.is_op(","):
                        self.next()
                        args.append(self.expr())
                self.expect_op(")")
                e = ("call", t.line, e, args)
            elif self.is_op("["):
                t = self.next()
                idx = self.expr()
                self.expect_op("]")
                e = ("index", t.line, e, idx)
            else:
                return e

    def primary(self):
        t = self.next()
        k = t.kind
        if k == "int" or k == "str":
            return ("lit", t.line, t.value)
        if k == "id":
            return ("var", t.line, t.text)
        if k == "kw":
            w = t.text
            if w == "true":
                return ("lit", t.line, True)
            if w == "false":
                return ("lit", t.line, False)
            if w == "nil":
                return ("lit", t.line, None)
            if w == "fn":
                params, body = self.fn_rest()
                return ("lambda", t.line, params, body)
            if w == "if":
                cond = self.expr()
                self.expect_kw("then")
                a = self.block(("else", "end"))
                b = None
                if self.is_kw("else"):
                    self.next()
                    b = self.block(("end",))
                self.expect_kw("end")
                return ("if", t.line, cond, a, b)
            if w == "do":
                body = self.block(("end",))
                self.expect_kw("end")
                return ("do", t.line, body)
            if w == "handle":
                tag = self.expect_id()
                self.expect_kw("with")
                h = self.expr()
                self.expect_kw("in")
                body = self.block(("end",))
                self.expect_kw("end")
                return ("handle", t.line, tag.text, h, body)
            if w == "emit":
                tag = self.expect_id()
                return ("emit", t.line, tag.text, self.expr())
        if k == "op":
            if t.text == "(":
                e = self.expr()
                self.expect_op(")")
                return e
            if t.text == "[":
                items = []
                if not self.is_op("]"):
                    items.append(self.expr())
                    while self.is_op(","):
                        self.next()
                        items.append(self.expr())
                self.expect_op("]")
                return ("list", t.line, items)
        self.bad(t)
