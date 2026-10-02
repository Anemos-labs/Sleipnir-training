"""Small helpers shared by the interpreter modules."""
from lexer import FableError


def fail(line, msg):
    raise FableError(line, msg)


def bad(line, name):
    raise FableError(line, "type error: bad argument to %s" % name)


def expect(cond, line, name):
    if not cond:
        bad(line, name)
