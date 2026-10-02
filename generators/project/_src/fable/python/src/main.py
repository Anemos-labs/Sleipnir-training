"""fable: runs a program of the Fable language read from standard input."""
import sys

import config as C
from interp import Interp
from lexer import FableError, lex
from parser import Parser


def main():
    src = sys.stdin.read()
    out = []
    status = 0
    try:
        ast = Parser(lex(src)).program()
        it = Interp(out)
        it.run_block(ast, it.globals, scope=False)
    except FableError as e:
        out.append("error: line %d: %s" % (e.line, e.msg))
        status = 1
    sys.stdout.write("".join(l + "\n" for l in out))
    return status


if __name__ == "__main__":
    sys.setrecursionlimit(200000)
    import threading

    threading.stack_size(512 * 1024 * 1024)
    result = []
    t = threading.Thread(target=lambda: result.append(main()))
    t.start()
    t.join()
    sys.exit(result[0] if result else 1)
