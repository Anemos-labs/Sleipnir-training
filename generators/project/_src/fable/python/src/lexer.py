"""Tokens of the Fable language."""
import config as C

KEYWORDS = {"let", "fn", "if", "then", "else", "end", "while", "do", "for", "in", "return", "and", "or", "not", "true", "false", "nil", "emit", "handle", "with", "print"}
if C.DEFER:
    KEYWORDS.add("defer")
TWO = ("==", "!=", "<=", ">=", "=>") + (("|>",) if C.PIPE else ())
ONE = "+-*/%<>=()[],;"
# a newline directly after one of these tokens does not end a statement
SUPPRESS = {"(", "[", ",", "=", "=>", "then", "else", "do", "with", "in", "and", "or", "not", "+", "-", "*", "/", "%", "==", "!=", "<", "<=", ">", ">=", "|>"}
MAX_INT = 2 ** 63 - 1


class FableError(Exception):
    def __init__(self, line, msg):
        Exception.__init__(self, msg)
        self.line = line
        self.msg = msg


class Tok:
    def __init__(self, kind, text, line, value=None):
        self.kind = kind  # int str id kw op nl eof
        self.text = text
        self.line = line
        self.value = value

    def shown(self):
        if self.kind == "nl":
            return "end of line"
        if self.kind == "eof":
            return "end of input"
        if self.kind == "str":
            return "a string"
        return "'%s'" % self.text


def lex(src):
    toks = []
    i, n, line, depth = 0, len(src), 1, 0

    def add(kind, text, value=None):
        toks.append(Tok(kind, text, line, value))

    while i < n:
        c = src[i]
        if c == "\n":
            if depth == 0 and toks and toks[-1].kind != "nl" and not (toks[-1].kind in ("op", "kw") and toks[-1].text in SUPPRESS):
                add("nl", "\n")
            line += 1
            i += 1
        elif c in " \t\r":
            i += 1
        elif c == "#":
            while i < n and src[i] != "\n":
                i += 1
        elif c.isdigit() and c.isascii():
            j = i
            while j < n and src[j].isdigit() and src[j].isascii():
                j += 1
            if int(src[i:j]) > MAX_INT:
                raise FableError(line, "integer too large")
            add("int", src[i:j], int(src[i:j]))
            i = j
        elif c == '"':
            j, buf = i + 1, []
            while True:
                if j >= n or src[j] == "\n":
                    raise FableError(line, "unterminated string")
                ch = src[j]
                if ch == '"':
                    break
                if ch == "\\":
                    if j + 1 >= n or src[j + 1] not in 'ntr"\\':
                        raise FableError(line, "bad escape")
                    buf.append({"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}[src[j + 1]])
                    j += 2
                else:
                    buf.append(ch)
                    j += 1
            add("str", src[i:j + 1], "".join(buf))
            i = j + 1
        elif (c.isalpha() or c == "_") and c.isascii():
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_") and src[j].isascii():
                j += 1
            w = src[i:j]
            add("kw" if w in KEYWORDS else "id", w)
            i = j
        elif src[i:i + 2] in TWO:
            add("op", src[i:i + 2])
            i += 2
        elif c in ONE:
            if c in "([":
                depth += 1
            elif c in ")]":
                depth = max(0, depth - 1)
            add("op", c)
            i += 1
        else:
            raise FableError(line, "bad character '%s'" % c)
    toks.append(Tok("eof", "", line))
    return toks
