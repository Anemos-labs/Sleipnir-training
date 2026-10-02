"""project-fable: an interpreter for Fable, an invented small language with lexical closures and dynamically scoped effect handlers
(`handle` / `emit`), optional pipes and defers, exact error messages with line numbers and resource limits.  Reference: Python
(oracle) and Go."""
from __future__ import annotations

from fx import family

from generators.project import _kit as K

THEME = "fable"
TOOLS = ["fable", "parable", "fabula", "allegro", "saga", "lorekeeper", "storyboard", "tellit"]
CORE = ["len", "str", "push", "range", "map", "filter", "fold"]
OPTIONAL = ["int", "join", "split", "upper", "slice"]

PLAN = [
    dict(lang="go", defer=True, pipe=True, depth=60, loops=3000, extra=["join", "int", "upper"]),
    dict(lang="python", defer=False, pipe=True, depth=40, loops=2000, extra=["join", "split"]),
    dict(lang="go", defer=True, pipe=False, depth=100, loops=5000, extra=["int", "slice", "split", "join"]),
    dict(lang="python", defer=True, pipe=True, depth=30, loops=1500, extra=["upper", "slice"]),
    dict(lang="go", defer=False, pipe=False, depth=80, loops=2500, extra=["join", "int", "split", "upper", "slice"]),
    dict(lang="python", defer=True, pipe=False, depth=50, loops=4000, extra=["int", "join"]),
    dict(lang="go", defer=True, pipe=True, depth=45, loops=1000, extra=["split", "upper"]),
    dict(lang="python", defer=False, pipe=True, depth=120, loops=3500, extra=["join", "int", "slice", "upper"]),
]

VOICES = [
    "Please implement an interpreter for Fable, a small language we are inventing: expression-oriented, lexical closures, and *effect handlers* (`handle ... with ... in` and `emit`) that are dynamically scoped. `README.md` has the lexical rules, the grammar, the semantics, the builtins, every error message with the rule for its line number, and the resource limits. The program is `{tool}`; write it in {Lang}: {run}. It reads the program from standard input. Visible examples: `python3 tests/run_examples.py`.",
    "build {tool}, an interpreter for the Fable language (README.md), in {Lang}. {run}. program on stdin, output on stdout. the handler-stack rule (a handler runs with only the handlers *outside* its own `handle` active), closure capture, newline suppression and the error line rules are the parts that need care. examples: `python3 tests/run_examples.py`",
    "Ticket LANG-{num}: Fable interpreter `{tool}` (spec: README.md).\n\nLanguage: {Lang}; the program is {run}. Parse and runtime errors are printed as `error: line N: MESSAGE` after whatever the program printed before; the exit status is 1 then. Please separate lexer, parser, evaluator and builtins.",
    "Could you write the Fable interpreter described in README.md? It is a tree-walking interpreter: closures, `if`/`while`/`for`, lists, strings, higher-order builtins, and the `handle`/`emit` effect mechanism. {Lang} please; the program is {run}. `python3 tests/run_examples.py` runs a few programs; the hidden checks run many more, grouped by feature, plus a lot of error cases.",
    "Greenfield in {Lang}: `{tool}`, an interpreter for a toy language with closures and dynamically scoped handlers. Everything (grammar, newline rules, truthiness, integer overflow, printing of values, builtins, errors, limits) is specified in README.md. {run}. The hidden suite is graded per group (closures, effects, data, control, arithmetic, errors, layout, limits), so partial implementations earn partial credit.",
    "README.md specifies Fable; please implement `{tool}` for it in {Lang} ({run}). Things that are easy to get wrong: `emit` calls the handler with the handler stack cut down to the frames below the matching `handle`; a closure created inside a `handle` body does *not* carry the handler out with it; syntax errors name the first token that cannot continue the program; division truncates toward zero. Visible examples: `python3 tests/run_examples.py`.",
    "short version: interpreter for the Fable language, spec in README.md, {Lang}, name it {tool}. reads the program on stdin. {run}",
    "Please implement the Fable interpreter from README.md in {Lang}. Name: `{tool}`. How it is run: {run}. The checks compare complete output, including error lines with line numbers and the output printed before an error, so be exact about evaluation order and about which token an error is attributed to.",
]


def readme(p: dict, tool: str, lang: str, by_name: dict) -> str:
    o: list[str] = []
    w = o.append
    builtins = CORE + p["extra"]
    w(f"# {tool}: an interpreter for the Fable language\n")
    w(f"`{tool}` runs a program written in **Fable**, a small expression-oriented language with first-class functions, lexical closures and *effect handlers*. "
      "The program is read from **standard input**; what it prints goes to standard output, one line per `print`. If the program fails (a syntax error or a runtime error), the interpreter prints, after everything the program already printed, "
      "one line `error: line N: MESSAGE` and exits with status 1; otherwise the status is 0.\n")
    w(f"Build and run it as {K.how_to_run(lang, tool)}.\n")
    w("## 1. Lexical structure\n")
    w("* The source is ASCII text. Lines are numbered from 1; the line of a token is the line where it starts. Spaces, tabs and `\\r` separate tokens. `#` starts a comment that runs to the end of the line.")
    w("* **Integers**: decimal digits (leading zeros allowed). Values are 64-bit signed; a literal above 9223372036854775807 is the error `integer too large`.")
    w("* **Strings**: `\"...\"` on one line with the escapes `\\n \\t \\r \\\" \\\\`; any other backslash sequence is `bad escape`; a string that is not closed before the end of the line is `unterminated string`.")
    w("* **Identifiers**: a letter or `_` followed by letters, digits and `_`. **Keywords** (not usable as identifiers): `let fn if then else end while do for in return and or not true false nil emit handle with print`" + (" `defer`" if p["defer"] else "") + ".")
    w("* **Operators and punctuation**: `+ - * / % == != < <= > >= = => ( ) [ ] , ;`" + (" and `|>`" if p["pipe"] else "") + ". Any other character is `bad character 'c'`.")
    w("* Lexical errors are reported with the line where they occur (for an unterminated string: the line where the string starts) and stop everything before the program runs.")
    w("\n**Statement separators.** A newline ends a statement, but the lexer drops a newline in these cases: when it is inside `( )` or `[ ]` (at any nesting), when the token before it is one of `( [ , = => then else do with in and or not + - * / % == != < <= > >=" + (" |>" if p["pipe"] else "") + "`, and when no token precedes it or the previous token already was a newline. "
      "`;` is also a separator. So a statement may continue on the next line after a binary operator, a comma, `=`, `=>` and the keywords listed, but not after `)`, `]`, a value or `end`.\n")
    w("## 2. Grammar\n")
    w("`sep` is a newline or `;`; any number of them may separate statements, before the first and after the last. `{ x }` is repetition, `[ x ]` optional.\n")
    w("```\nprogram   = block                                 (the block may end only at the end of the input)\nblock     = { sep } { statement ( sep { sep } | <block end> ) }\nstatement = \"let\" ID \"=\" expr\n          | \"fn\" ID \"(\" [params] \")\" \"=>\" expr     (named function; the name is visible inside it)\n          | \"print\" expr\n          | \"return\" [ expr ]                     (no expr when a sep, end or else follows)\n          | \"while\" expr \"do\" block \"end\"\n          | \"for\" ID \"in\" expr \"do\" block \"end\"\n" +
      ("          | \"defer\" statement\n" if p["defer"] else "") +
      "          | ID \"=\" expr                           (assignment: an ID directly followed by =)\n          | expr\nparams    = ID { \",\" ID }\nexpr      = or" + (" { \"|>\" postfix }" if p["pipe"] else "") + "\nor        = and { \"or\" and }\nand       = not { \"and\" not }\nnot       = \"not\" not | cmp\ncmp       = add [ (\"==\"|\"!=\"|\"<\"|\"<=\"|\">\"|\">=\") add ]       (not chainable)\nadd       = mul { (\"+\"|\"-\") mul }\nmul       = unary { (\"*\"|\"/\"|\"%\") unary }\nunary     = \"-\" unary | postfix\npostfix   = primary { \"(\" [ expr { \",\" expr } ] \")\" | \"[\" expr \"]\" }\nprimary   = INT | STRING | \"true\" | \"false\" | \"nil\" | ID | \"(\" expr \")\" | \"[\" [ expr { \",\" expr } ] \"]\"\n          | \"fn\" \"(\" [params] \")\" \"=>\" expr\n          | \"if\" expr \"then\" block [ \"else\" block ] \"end\"\n          | \"do\" block \"end\"\n          | \"handle\" ID \"with\" expr \"in\" block \"end\"\n          | \"emit\" ID expr\n```")
    w("A block ends at `end` (or at `else` for the `then` part of an `if`) or, for the program, at the end of the input. The body of `fn ... =>` and the operand of `emit` are full `expr`s that extend as far as possible. "
      "`else` belongs to the nearest `if`. " + ("In `a |> b`, the right side is a `postfix` expression; the operator is left associative and binds weaker than `or`. " if p["pipe"] else "") + "\n")
    w("**Syntax errors.** The parser reads left to right and reports `error: line N: unexpected TOKEN` for the first token that cannot continue a valid program, where `N` is that token's line and `TOKEN` is `'text'` (the token as written), `a string` for any string literal, `end of line` for a newline token, `end of input` for the end (its line is 1 plus the number of newlines in the source). "
      "After a complete statement the next token must be a separator or the end of the enclosing block, else it is the unexpected one. Nothing is run when there is a syntax error.\n")
    w("## 3. Values and operators\n")
    w("Types: `int`, `string`, `bool`, `nil`, `list`, `function` (the names used in messages). Lists are immutable (operations make new lists). Truthiness: only `false` and `nil` are false; `0`, `\"\"` and `[]` are true.\n")
    w("* `+`: two ints (overflow beyond 64 bits is `integer overflow`), two strings or two lists (concatenation). `-`, `*`: ints. `/` and `%`: ints; `/` truncates toward zero and `%` has the sign of the dividend (`-7 / 2` is `-3`, `-7 % 3` is `-1`); a zero divisor is `division by zero`; `-9223372036854775808 / -1` is `integer overflow`.")
    w("* `<`, `<=`, `>`, `>=`: two ints or two strings (byte order). `==`, `!=` work on any two values and never fail: values of different types are unequal, lists compare element by element, functions are equal only to themselves, builtins equal when they are the same builtin.")
    w("* `and`, `or` evaluate the right side only when needed and give the *operand* value (`nil or 3` is `3`); `not` gives a bool. Unary `-`: ints only (`integer overflow` for the smallest int).")
    w("* Any other operand types: `type error: cannot apply 'OP' to TYPE and TYPE` (`type error: cannot apply '-' to TYPE` for the unary operator).")
    w("* `xs[i]`: `xs` a list or string, `i` an int; a negative `i` counts from the end (`-1` is the last); out of range is `index out of range: I (length N)`; a string gives a one-character string; other types: `type error: cannot index TYPE with TYPE`.")
    w("* Printing (`print`, `str`, `join`): ints in decimal, `true`, `false`, `nil`, strings as they are; **inside a list** strings are quoted with `\"` and the escapes `\\\\ \\\" \\n \\t \\r`, and a list is `[a, b, c]` (elements separated by `, `). A function prints as `<fn NAME>` (a function defined with `fn NAME`), `<fn>` (an anonymous one) or `<builtin NAME>`.\n")
    w("## 4. Scopes, functions, closures\n")
    w("* A **scope** maps names to values and has a parent. The program runs in the global scope together with the builtins. Every `if` branch, `do` block, `while`/`for` body (a fresh scope per iteration), `handle` body and every function call creates a new scope, with `let` binding in the innermost. `let x = ...` again in the same scope replaces the binding.")
    w("* A variable reference looks the name up through the scopes outwards (`unbound variable 'x'`). `x = expr` assigns to the nearest scope that has `x` (`cannot assign to unbound variable 'x'`; the right side is evaluated first). Statements `let`, `fn`, `print`, assignment, loops give no value (`nil`).")
    w("* `fn name(a, b) => expr` binds `name` in the current scope and creates a **closure** that remembers the current scope *by reference* (later changes to the scope are visible). `fn(a, b) => expr` is an anonymous function; `let f = fn(...) => ...` is therefore also able to call itself through `f`. "
      "Calls evaluate the callee, then the arguments left to right. A call needs exactly the declared number of arguments: `wrong number of arguments for NAME: expected N, got M` (`NAME` is `function` for an anonymous function). A non-function: `type error: TYPE is not callable`. The body is evaluated in a new scope below the closure's scope.")
    w("* `return expr` (or `return` for `nil`) leaves the innermost *function* call with that value. Outside any function it is `return outside function`. The value of a block (`if`, `do`, `handle`, a function body that is a `do` block) is the value of its last statement: an expression statement gives its value, any other statement `nil`; an empty block gives `nil`; an `if` without `else` whose condition is false gives `nil`.")
    w("* `while c do ... end` re-evaluates `c` before every iteration. `for x in e do ... end` evaluates `e` once (a list, or a string whose characters are one-character strings; else `type error: cannot iterate over TYPE`) and runs the body once per element with `x` bound in a fresh scope.\n")
    w("## 5. Effects: `handle` and `emit`\n")
    w("The interpreter keeps a **handler stack**: a list of frames `(tag, function)`, innermost last.\n")
    w("* `handle TAG with H in BODY end`: evaluates `H` once (it must be a function, else `type error: TYPE is not callable` at the `handle` keyword), pushes the frame `(TAG, H)`, evaluates the body block, and pops the frame again however the body ends (normally, by `return`, or by an error). The value is the body's value.")
    w("* `emit TAG EXPR`: evaluates `EXPR`, finds the **innermost** frame whose tag is `TAG` (`unhandled emit 'TAG'` if none), and calls its function with the value as the only argument. "
      "**While that call runs, the handler stack consists only of the frames below the matching frame** (so the handler itself and everything pushed after it are not active; an `emit` of the same tag inside the handler goes to an outer frame, if any). "
      "The stack is restored afterwards. The value of the `emit` expression is what the handler returned. Errors in the call (arity, depth) are reported at the `emit` keyword's line.")
    w("* The stack is *dynamic*: calling a function does not change it, whichever scope the function was defined in. A function created inside a `handle` body and called after the `handle` has ended sees no frame of it; a function defined outside and called inside sees the frame.\n")
    if p["defer"]:
        w("## 6. `defer`\n")
        w("`defer STATEMENT` does not run the statement now: it is added to the list of deferred statements of the innermost enclosing *block* (the program's, a function body's, an `if` branch's, a loop iteration's, ...). When that block ends normally or through `return`, its deferred statements run in **reverse order** of deferral, in the block's scope, "
          "after the block's last statement (the block's value is not affected). They do not run when the program stops with an error. A deferred statement may itself contain `defer`s: those run right after it, before the next deferred statement.\n")
    if p["pipe"]:
        w("## 7. Pipes\n")
        w("`a |> f` means `f(a)`; `a |> f(b, c)` means `f(a, b, c)`: if the right side is a call expression, the left value becomes its first argument, otherwise the right side is evaluated and called with the left value. "
          "The left value is evaluated first, then the callee, then the remaining arguments. Errors of the call (not callable, arity, depth, builtin) are reported at the `|>` token's line.\n")
    w("## 8. Builtins\n")
    w("These names are bound in the global scope (they are values: they can be passed around, and `print` shows them as `<builtin NAME>`). A wrong number of arguments is `wrong number of arguments for NAME: expected N, got M` (`expected 1 or 2` for `range`); an argument of the wrong type is `type error: bad argument to NAME`. "
      "Errors of builtins (and of functions they call) are reported at the line of the call's `(` " + ("(or the `|>` token when called by a pipe)" if p["pipe"] else "") + ".\n")
    rows = {
        "len": "`len(x)`: number of elements of a list or characters of a string.",
        "str": "`str(x)`: the printed form of any value (section 3).",
        "push": "`push(xs, v)`: a new list with `v` appended.",
        "range": "`range(n)` is `[0, 1, ..., n-1]`, `range(a, b)` is `[a, ..., b-1]` (empty when `b <= a`); `range too large` if more than 10000 elements.",
        "map": "`map(xs, f)`: the list of `f(x)` for each element, in order.",
        "filter": "`filter(xs, f)`: the elements for which `f(x)` is truthy.",
        "fold": "`fold(xs, init, f)`: `acc = init`, then `acc = f(acc, x)` for each element; returns `acc`.",
        "int": "`int(x)`: an int stays; a string of the form `-?[0-9]{1,18}` is converted; any other string is `cannot convert 'S' to int`.",
        "join": "`join(xs, sep)`: the printed forms of the elements (strings unquoted) joined with the string `sep`.",
        "split": "`split(s, sep)`: the list of pieces of `s` between occurrences of the non-empty string `sep` (an empty `sep` is a bad argument); like cutting at every occurrence, so `split(\"a,,b\", \",\")` is `[\"a\", \"\", \"b\"]`.",
        "upper": "`upper(s)`: `a`-`z` turned into `A`-`Z`.",
        "slice": "`slice(x, a, b)`: the sub-list or substring from index `a` up to but excluding `b`; both are clamped into `0..length`; empty when `a >= b`.",
    }
    for b in builtins:
        w("* " + rows[b])
    w("\nNo other builtin exists (`unbound variable` for any other name).\n")
    w("## 9. Runtime errors and their lines\n")
    w("Output already produced stays; the error line follows. Messages (types are `int string bool nil list function`) and the token whose line is reported:\n")
    w("| message | line of |")
    w("|---|---|")
    for msg, where in [
        ("`unbound variable 'x'`, `cannot assign to unbound variable 'x'`", "the identifier"),
        ("`type error: cannot apply ...`, `division by zero`, `integer overflow` (binary operators)", "the operator token"),
        ("`type error: cannot apply '-' to TYPE`, `integer overflow` (unary minus)", "the `-` token"),
        ("`type error: cannot index ...`, `index out of range: ...`", "the `[` token"),
        ("`type error: TYPE is not callable`, `wrong number of arguments ...`, `call depth exceeded`, builtin errors", "the `(` of the call" + (" (the `|>` token for a pipe)" if p["pipe"] else "")),
        ("`type error: cannot iterate over TYPE`", "the `for` keyword"),
        ("`unhandled emit 'TAG'`, errors of the handler call", "the `emit` keyword"),
        ("`type error: TYPE is not callable` for a handler", "the `handle` keyword"),
        ("`return outside function`", "the `return` keyword"),
        ("`step limit exceeded`", "the `while` or `for` keyword of the loop that ran too long"),
    ]:
        w(f"| {msg} | {where} |")
    w("\nEvaluation order is left to right everywhere (operands of a binary operator, call arguments, list items). For a call, the argument count is checked before the depth limit.\n")
    w("## 10. Limits\n")
    w(f"* **Call depth**: at most **{p['depth']}** user-function calls (closures, including handlers and functions called by builtins) may be active at the same time; calling one more is `call depth exceeded`. Builtins do not count.")
    w(f"* **Loop steps**: the total number of loop iterations over the whole run (every iteration of every `while` and `for`) may not exceed **{p['loops']}**; the iteration that would be number {p['loops'] + 1} is `step limit exceeded`.\n")
    w("## 11. Examples\n")
    ex = [(c, r) for (c, r) in by_name.values() if c.visible]
    for c, r in ex[:3]:
        w(K.show_case(tool, c, r))
    w("The visible examples (`tests/examples.json`, run with `python3 tests/run_examples.py`) use the same format as the hidden checks: a program on standard input, the expected output and exit status.")
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# programs
# ---------------------------------------------------------------------------------------------------------------

def make_cases(p: dict, tool: str, rng) -> list[K.Case]:
    cases: list[K.Case] = []
    cnt: dict[str, int] = {}
    has = lambda b: b in CORE or b in p["extra"]  # noqa: E731
    R = rng

    def add(group, src, visible=False):
        cnt[group] = cnt.get(group, 0) + 1
        cases.append(K.Case(name=f"{group}-{cnt[group]:02d}", group=group, stdin=src.strip("\n") + "\n", visible=visible))

    def names(k):
        return R.sample(["alpha", "beta", "gamma", "delta", "total", "acc", "cur", "left", "right", "item", "step", "count", "base"], k)

    # ---- closures ---------------------------------------------------------------------------------------------------
    for k in range(5):
        a, b, c = R.randint(1, 20), R.randint(1, 20), R.randint(2, 9)
        progs = [
            f"""
# counters share nothing
fn make_counter(start, step) => do
  let n = start
  fn() => do
    n = n + step
    n
  end
end
let c1 = make_counter({a}, {c})
let c2 = make_counter({b}, 1)
print c1()
print c1()
print c2()
print c1() + c2()
print c1
print make_counter
""",
            f"""
fn adder(x) => fn(y) => x + y
let add{a} = adder({a})
let twice = fn(f, v) => f(f(v))
print add{a}({b})
print twice(add{a}, {b})
print twice(twice, add{a})
print adder({c})({a})({b})
""",
            f"""
let fns = []
for i in range({c}) do
  fns = push(fns, fn() => i * {a})
end
let out = []
for f in fns do
  out = push(out, f())
end
print out
let shared = 0
let incs = map(range(3), fn(i) => fn() => do
  shared = shared + {b}
  shared
end)
print [incs[0](), incs[1](), incs[2](), shared]
""",
            f"""
fn fact(n) => if n <= 1 then 1 else n * fact(n - 1) end
fn fib(n) => if n < 2 then n else fib(n - 1) + fib(n - 2) end
let even = fn(n) => if n == 0 then true else odd(n - 1) end
let odd = fn(n) => if n == 0 then false else even(n - 1) end
print fact({c + 3})
print fib({c + 2})
print [even({a}), odd({a}), even({b}), odd({b})]
print fact
""",
            f"""
let x = {a}
fn show_x() => x
let x = {b}
print show_x()
do
  let x = {c}
  print show_x()
  x = x + 1
  print x
end
print x
x = 99
print show_x()
""",
        ]
        add("closures", progs[k], visible=(k == 0))
    # ---- effects --------------------------------------------------------------------------------------------------------
    eff = [
        """
let log = []
handle note with fn(m) => do
  log = push(log, m)
  nil
end in
  emit note "one"
  emit note "two"
  let r = emit note "three"
  print r
end
print log
""",
        """
handle ask with fn(q) => q + 1 in
  print emit ask 10
  print (emit ask 1) * 100
  fn helper(n) => emit ask n * 2
  print helper(5)
end
""",
        """
handle log with fn(m) => print "outer: " + m in
  handle log with fn(m) => do
    print "inner: " + m
    emit log "from inner: " + m
  end in
    emit log "a"
  end
  emit log "b"
end
""",
        """
fn work(n) => do
  emit tick n
  emit tick n * 2
  n
end
let total = 0
handle tick with fn(v) => do
  total = total + v
  0
end in
  print work(5)
  print work(7)
end
print total
""",
        """
let make = fn() => do
  let h = fn(x) => x * 3
  handle scale with h in
    fn(v) => emit scale v
  end
end
let probe = make()
print "made"
handle scale with fn(x) => x + 1000 in
  print probe(2)
end
""",
        """
fn inside() => emit mood "calm"
handle mood with fn(m) => "mood is " + m in
  print inside()
end
print inside()
""",
        """
fn find_first(xs, pred) => do
  handle found with fn(v) => return v in
    for x in xs do
      if pred(x) then
        emit found x
      end
    end
  end
  nil
end
print find_first([3, 8, 11, 20], fn(x) => x > 9)
print find_first([1, 2], fn(x) => x > 9)
""",
        """
handle a with fn(x) => do
  print "a got " + str(x)
  x + 1
end in
  handle b with fn(y) => emit a y * 2 in
    print emit b 5
    handle a with fn(z) => "shadow " + str(z) in
      print emit b 7
      print emit a 1
    end
  end
end
""",
        """
handle e with 5 in
  print 1
end
""",
        """
handle e with fn(x, y) => x in
  print emit e 1
end
""",
        """
handle e with fn(x) => x in
  let f = fn() => emit e 1
  print f()
  return 3
end
print "done"
""",
        """
fn risky(n) => if n > 2 then emit stop n else n end
handle stop with fn(v) => "stopped at " + str(v) in
  print map(range(5), risky)
end
""",
    ]
    ek = R.sample(range(len(eff)), 9)
    for j, i in enumerate(ek):
        add("effects", eff[i], visible=(j == 0))
    # ---- data -------------------------------------------------------------------------------------------------------------
    for k in range(4):
        a, b = R.randint(2, 9), R.randint(10, 30)
        parts = [f'let xs = range({a}, {b})', "print xs", "print len(xs)", "print xs[0] + xs[-1]", "print xs[len(xs) - 1]",
                 "print [1, [2, [3]], \"s\", nil, true, false, [], \"q\\\"uote\\n\"]", "print [1, 2] + [3] == [1, 2, 3]", "print [1, 2] == [1, 3]", "print \"a\" + \"b\" == \"ab\"",
                 'print "abc" < "abd"', "print nil == false", "print 0 == false", "print [] == []", "print len"]
        extra = []
        if has("join"):
            extra += ['print join(map(xs, str), "-")', 'print join(["a", 1, nil, [2, "x"]], ", ")']
        if has("split"):
            extra += ['print split("a,b,,c", ",")', 'print len(split("", ","))', 'print split("abc", "b")']
        if has("upper"):
            extra += ['print upper("Hello, World 42")']
        if has("slice"):
            extra += ["print slice(xs, 1, 3)", "print slice(xs, -5, 2)", "print slice(\"hello\", 1, 99)", "print slice(xs, 4, 2)"]
        if has("int"):
            extra += ['print int("42") + 1', 'print int("-7")', "print int(5)"]
        body = "\n".join(parts) + "\n" + "\n".join(extra) + f"""
print map(xs, fn(x) => x * x)
print filter(xs, fn(x) => x % {a} == 0)
print fold(xs, 0, fn(acc, x) => acc + x)
print fold(map(xs, str), "", fn(s, x) => s + x)
print push(push([], 1), "two")
print "hello"[1] + "hello"[-1]
print [10, 20, 30][1]
print len("")
print str(12) + str(nil) + str(true) + str([1, "a"])
print str("raw")
"""
        add("data", body, visible=False)
    # ---- control ----------------------------------------------------------------------------------------------------------
    for k in range(4):
        a, b = R.randint(3, 8), R.randint(2, 5)
        progs = [
            f"""
let i = 0
let acc = []
while i < {a} do
  if i % 2 == 0 then
    acc = push(acc, i * {b})
  else
    acc = push(acc, -i)
  end
  i = i + 1
end
print acc
for ch in "abc" do
  print ch + ch
end
let v = if {a} > {b} then "big" else "small" end
print v
print if false then 1 end
print do 1
2 end
""",
            f"""
fn first_big(xs) => do
  for x in xs do
    if x > {a} then
      return x
    end
  end
  return nil
end
print first_big([1, {a + 2}, {a + 5}])
print first_big([1, 2])
fn nothing() => return
print nothing()
print (nil or 0) + 1
print false or nil
print 1 and 2
print nil and 2
print not nil
print not 0
""",
            f"""
let log = []
fn t(name, v) => do
  log = push(log, name)
  v
end
print t("a", false) and t("b", true)
print t("c", true) or t("d", false)
print t("e", nil) or t("f", 7)
print log
print [t("x", 1), t("y", 2), t("z", 3)]
print t("p", 1) + t("q", 2) * t("r", 3)
print log
""",
            f"""
let n = {a * 3}
let steps = 0
while n != 1 do
  n = if n % 2 == 0 then n / 2 else 3 * n + 1 end
  steps = steps + 1
  if steps > 500 then
    n = 1
  end
end
print steps
let grid = map(range(3), fn(r) => map(range(3), fn(c) => r * 3 + c))
for row in grid do
  print join_row(row)
end
""".replace("print join_row(row)", "print row"),
        ]
        add("control", progs[k], visible=False)
    # ---- arithmetic -----------------------------------------------------------------------------------------------------------
    for k in range(3):
        big = "9223372036854775807"
        lines = ["print 7 / 2", "print -7 / 2", "print 7 / -2", "print -7 / -2", "print 7 % 3", "print -7 % 3", "print 7 % -3", "print -7 % -3", "print 0 / 5", "print 5 % 5",
                 f"print {big}", f"print {big} - 1", f"print -{big}", f"print -{big} - 1", f"print (-{big} - 1) / 1", "print 3 - 5 - 2", "print 2 + 3 * 4 - 6 / 2", "print -2 * 3", "print - - 4", "print 10 - -3",
                 "print 1 < 2", "print 2 <= 2", "print \"b\" >= \"a\"", "print 1 == 1.0 or 2" if False else "print 1 == 1", "print 1 != 2"]
        errs = [f"print {big} + 1", f"print -{big} - 2", f"print {big} * 2", f"print (-{big} - 1) / -1", "print 1 / 0", "print 1 % 0", "print -(-{big} - 1)".replace("{big}", big),
                "print 1 + \"a\"", "print [1] + 1", "print nil < 1", "print \"a\" < 1", "print true + true", "print -\"x\"", "print -nil", "print 1 < [2]"]
        R.shuffle(lines)
        add("arith", "\n".join(lines[:16]) + "\n", visible=False)
        for e in R.sample(errs, 3):
            add("arith", "print 1\n" + e + "\nprint 2\n")
    # ---- runtime errors with line attribution ----------------------------------------------------------------------------------------------
    rt = [
        "let a = 1\nprint a\nprint b\n", "x = 5\n", "let f = fn(a, b) => a\nprint f(1)\n", "fn named(a) => a\nprint 1\nprint named(1, 2)\n", "let xs = [1, 2]\nprint xs[5]\n", "let xs = [1, 2]\nprint xs[-3]\n",
        "print \"abc\"[3]\n", "print 5[0]\n", "print [1][\"a\"]\n", "let f = 3\nprint 1\nf(1)\n", "print nil()\n", "for x in 5 do\nprint x\nend\n", "return 5\n", "print 1\nlet z = (1 +\n  2) * (3 -\n  nil)\n",
        "print (1 +\n  2 *\n  [1])\n", "let xs = [\n  1,\n  2 / 0,\n  3\n]\n", "fn f(x) =>\n  x +\n  undefined_name\nprint f(1)\n", "print len(5)\n", "print len(1, 2)\n", "print map([1], 5)\n",
        "print range(\"a\")\n", "print range(0, 20000)\n", "print push(1, 2)\n", "handle e with 5 in\n  print 1\nend\n", "print emit nothing 1\n", "print [1,\n  emit gone 2]\n",
        "let f = fn() => f2()\nprint f()\n", "print 1\nprint [1, 2, 3][1 + \n 5]\n", "print fold([1, 2], 0, fn(a) => a)\n", "print map([1, 2], fn(x) =>\n  x / (x - 1))\n",
    ]
    if has("int"):
        rt += ['print int("abc")\n', 'print int("12x")\n', "print int(nil)\n", 'print int("99999999999999999999")\n']
    if has("split"):
        rt += ['print split("a", "")\n', "print split(1, \"a\")\n"]
    if has("slice"):
        rt += ['print slice(5, 1, 2)\n', 'print slice([1], "a", 2)\n']
    if has("join"):
        rt += ['print join(1, ",")\n', 'print join([1], 2)\n']
    if has("upper"):
        rt += ["print upper(5)\n"]
    R.shuffle(rt)
    for i in range(0, 18, 1):
        add("runtime", "print \"start\"\n" + rt[i] + "print \"never\"\n", visible=(i == 0))
    # ---- syntax errors -------------------------------------------------------------------------------------------------------------------
    se = ["print (1 + 2\n", "print 1 +\n", "let = 5\n", "let x 5\n", "if true then print 1\n", "if true print 1 end\n", "while true print 1 end\n", "for x xs do end\n", "fn (a) a\n", "fn f(a, ) => a\n", "print [1, 2\n",
          "print [1 2]\n", "print 1 2\n", "print )\n", "end\n", "else\n", "print 1 end\n", "do\nprint 1\n", "handle x with fn(a) => a\nprint 1\n", "handle x with fn(a) => a in 1\n", "emit\n", "emit 5 1\n", "print \"abc\n",
          "print \"a\\qb\"\n", "print 1 $ 2\n", "print 99999999999999999999\n", "let x = 1;; let y = 2\nprint x + y\n", "print 1 == 2 == 3\n", "print not\n", "print -\n", "x = \n", "1 = 2\n", "f(1,\n", "return 1 2\n",
          "let fn = 1\n", "let print = 1\n", "print 1 +\n\n\n", "if 1 then\nelse\nelse\nend\n", "print true\nprint (\n", "fn f() =>\n", "print a[\n", "print [\n1,\n", "print 1\n\n\n  @\n"]
    if p["defer"]:
        se += ["defer\n", "defer 1 +\n"]
    else:
        se += ["defer print 1\n", "let defer = 1\nprint defer\n"]
    if p["pipe"]:
        se += ["print 1 |>\n", "print 1 |> 2 |> \n", "print |> 1\n"]
    else:
        se += ["print 1 |> str\n"]
    R.shuffle(se)
    for s in se[:18]:
        add("syntax", "print \"before\"\n" + s)
    # ---- layout ------------------------------------------------------------------------------------------------------------------------------
    lay = [
        "let a = 1 +\n  2 +\n  3\nprint a\nprint (a\n  + 1)\nprint [1,\n  2,\n  3]\n",
        "print 1; print 2;; print 3\n;\n\n\nprint 4\n",
        "# only comments\n\n   # indented comment\nprint 1 # trailing\n",
        "let f = fn(a,\n  b) =>\n  a + b\nprint f(1,\n  2)\nprint f(\n  3, 4)\n",
        "let x = if true then\n  1\nelse\n  2\nend\nprint x\nprint do\n  let y = 5\n  y * 2\nend\n",
        "print 1 and\n  2\nprint not\n  false\nprint 1 ==\n  1\n",
        "let xs = [1, 2, 3]\nprint xs\n[7, 8][0]\nprint xs [1]\n",
        "fn f(x) => x\nprint f\n(1)\nprint f(\n1)\n",
        "let s = \"line one\\nline two\\ttabbed \\\"q\\\" back\\\\slash\"\nprint s\nprint [s]\nprint len(s)\n",
        "print 1\nreturn_value = 2\nprint return_value\nlet lettuce = 3\nprint lettuce\nlet _x1 = 4\nprint _x1\n",
        "print 007 + 1\nprint 12345678901234567\nprint -0\n",
        "while false do end\nfor x in [] do end\nprint do end\nprint if true then end\nprint 1\n",
    ]
    for s in lay:
        add("layout", s)
    # ---- limits --------------------------------------------------------------------------------------------------------------------------------
    d, lim = p["depth"], p["loops"]
    add("limits", f"fn down(n) => if n == 0 then 0 else 1 + down(n - 1) end\nprint down({d - 1})\nprint down({d})\nprint \"unreachable\"\n")
    add("limits", f"fn down(n) => if n == 0 then 0 else 1 + down(n - 1) end\nprint down({d - 2})\nprint map(range(3), fn(x) => down({d - 3}))\nprint down({d + 20})\n")
    add("limits", f"let i = 0\nwhile i < {lim} do\n  i = i + 1\nend\nprint i\nwhile true do\n  i = i + 1\nend\n")
    add("limits", f"let n = 0\nfor x in range({lim // 2}) do\n  n = n + 1\nend\nfor y in range({lim // 2}) do\n  n = n + 1\nend\nprint n\nfor z in [1] do\n  n = n + 1\nend\nprint \"no\"\n")
    add("limits", "fn loop(n) => loop(n + 1)\nprint \"go\"\nprint loop(0)\n")
    add("limits", f"fn f(n) => emit deep n\nhandle deep with fn(v) => if v > {d} then v else f(v + 1) end in\n  print f(0)\nend\n")
    add("limits", f"let f = fn(g, n) => if n == 0 then 0 else g(g, n - 1) + 1 end\nprint f(f, {d - 1})\nprint f(f, {d + 1})\n")
    # ---- optional features -----------------------------------------------------------------------------------------------------------------------
    if p["pipe"]:
        add("pipe", f"fn inc(x) => x + 1\nfn add(a, b) => a + b\nprint 5 |> inc\nprint 5 |> add({R.randint(1, 9)})\nprint 1 |> inc |> inc |> add(10) |> str\nprint [1, 2, 3] |> map(inc) |> filter(fn(x) => x % 2 == 0)\n"
                    f"print {R.randint(1, 9)} + 1 |> inc\nprint 2 * 3 |> inc\nprint (1 |> inc) * 5\nlet f = add\nprint 4 |> f(1)\n")
        add("pipe", "print 5 |> 6\n", visible=False)
        add("pipe", "fn two(a, b) => a\nprint 1 |> two\n")
        add("pipe", "print 1 |>\n  str |>\n  len\nprint \"abc\" |> len\nprint [3] |> len |> str |> len\n")
        add("pipe", "print 1 |> nothing_here\n")
        add("pipe", "let g = fn(x) => x[5]\nprint [1] |> g\n")
    else:
        add("pipe", "print 5 |> str\n")
    if p["defer"]:
        add("defer", 'fn f() => do\n  defer print "first deferred"\n  defer print "second deferred"\n  print "body"\n  return 1\nend\nprint f()\ndo\n  defer print "d1"\n  print "b1"\nend\nfor i in range(3) do\n  defer print "end of " + str(i)\n  print "iter " + str(i)\nend\n')
        add("defer", 'let n = 0\nfn g() => do\n  defer n = n + 10\n  n = n + 1\n  n\nend\nprint g()\nprint n\nif true then\n  defer print "after if body"\n  defer defer print "nested"\n  print "in if"\nend\nprint 1\n')
        add("defer", 'fn h() => do\n  defer print "cleanup"\n  print 1 / 0\nend\nprint "start"\nh()\nprint "not reached"\n')
        add("defer", 'defer print "program end"\nprint "main"\nhandle e with fn(v) => do\n  defer print "handler done"\n  v\nend in\n  defer print "handle body done"\n  print emit e 5\nend\n')
    else:
        add("defer", 'defer print "x"\n')
        add("defer", "let defer = 5\nprint defer\n")
    # ---- longer programs -----------------------------------------------------------------------------------------------------------------------------
    add("programs", """
# a tiny stack machine written with handlers
fn run(prog) => do
  let stack = []
  handle push_v with fn(v) => do
    stack = push(stack, v)
    len(stack)
  end in
    handle pop_v with fn(_) => do
      let top = stack[-1]
      stack = slice(stack, 0, len(stack) - 1)
      top
    end in
      for op in prog do
        if op[0] == "push" then
          emit push_v op[1]
        else
          let b = emit pop_v nil
          let a = emit pop_v nil
          if op[0] == "add" then emit push_v a + b end
          if op[0] == "mul" then emit push_v a * b end
          if op[0] == "sub" then emit push_v a - b end
        end
      end
    end
  end
  stack
end
print run([["push", 2], ["push", 3], ["add"], ["push", 4], ["mul"]])
print run([["push", 10], ["push", 4], ["sub"]])
print run([["add"]])
""".replace("slice(stack, 0, len(stack) - 1)", "filter(stack, fn(x) => true)") if not has("slice") else """
# a tiny stack machine written with handlers
fn run(prog) => do
  let stack = []
  handle push_v with fn(v) => do
    stack = push(stack, v)
    len(stack)
  end in
    handle pop_v with fn(_) => do
      let top = stack[-1]
      stack = slice(stack, 0, len(stack) - 1)
      top
    end in
      for op in prog do
        if op[0] == "push" then
          emit push_v op[1]
        else
          let b = emit pop_v nil
          let a = emit pop_v nil
          if op[0] == "add" then emit push_v a + b end
          if op[0] == "mul" then emit push_v a * b end
          if op[0] == "sub" then emit push_v a - b end
        end
      end
    end
  end
  stack
end
print run([["push", 2], ["push", 3], ["add"], ["push", 4], ["mul"]])
print run([["push", 10], ["push", 4], ["sub"]])
print run([["add"]])
""", visible=False)
    add("programs", f"""
# queue simulation with closures
fn make_queue() => do
  let items = []
  let api = [
    fn(x) => do
      items = push(items, x)
      len(items)
    end,
    fn() => len(items),
    fn() => items
  ]
  api
end
let q = make_queue()
let enqueue = q[0]
let size = q[1]
let all = q[2]
for i in range({R.randint(3, 6)}) do
  enqueue(i * i)
end
print size()
print all()
let q2 = make_queue()
q2[0]("only")
print [size(), q2[1]()]
print q2[2]()
""")
    add("programs", f"""
fn compose(f, g) => fn(x) => f(g(x))
fn curry(f) => fn(a) => fn(b) => f(a, b)
let add = curry(fn(a, b) => a + b)
let mul = curry(fn(a, b) => a * b)
let inc = add(1)
let dbl = mul(2)
let pipeline = compose(dbl, inc)
print map(range({R.randint(4, 8)}), pipeline)
print fold([inc, dbl, inc], 5, fn(acc, f) => f(acc))
fn memo(f) => do
  let seen = []
  let hits = 0
  fn(n) => do
    for pair in seen do
      if pair[0] == n then
        hits = hits + 1
        return pair[1]
      end
    end
    let v = f(n)
    seen = push(seen, [n, v])
    v
  end
end
let sq = memo(fn(n) => n * n)
print [sq(4), sq(4), sq(5), sq(4)]
""")
    return cases


@family("project-fable", category="project", lang="go", kind="greenfield", n=8,
        summary="an interpreter for an invented language with lexical closures and dynamically scoped effect handlers, newline rules, exact error lines and resource limits")
def gen(rng, n):
    for i in range(n):
        plan = dict(PLAN[i])
        tool = TOOLS[i]
        lang = plan.pop("lang")
        p = dict(plan)
        cfg = dict(DEFER=p["defer"], PIPE=p["pipe"], DEPTH_LIMIT=p["depth"], LOOP_LIMIT=p["loops"], BUILTINS=CORE + p["extra"])
        cases = make_cases(p, tool, rng)
        py_sol = K.merged(K.load_src(THEME, "python", tool), K.render_config("python", cfg))
        sol = py_sol if lang == "python" else K.merged(K.load_src(THEME, lang, tool), K.render_config(lang, cfg))
        prompt = VOICES[i % len(VOICES)].format(tool=tool, Lang=K.LANG_NAME[lang], run=K.how_to_run(lang, tool), num=1100 + i * 23)
        nfeat = sum([p["defer"], p["pipe"]])
        yield K.project_task(
            theme=THEME, tool=tool, lang=lang, cases=cases, solution=sol, py_solution=py_sol,
            readme=lambda by_name, p=p, tool=tool, lang=lang: readme(p, tool, lang, by_name),
            prompt=prompt, difficulty=4 if nfeat == 0 else 5, slug=f"{i + 1:02d}-{tool}-{'d' if p['defer'] else ''}{'p' if p['pipe'] else ''}-{lang}",
            notes={"defer": p["defer"], "pipe": p["pipe"], "depth": p["depth"], "loops": p["loops"], "builtins": CORE + p["extra"]}, tags=["interpreter", "closures", "effects"],
        )
