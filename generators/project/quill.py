"""project-quill: a scripted text-editor core: a character buffer with gravity marks, an undo tree (undo, redo, goto) and a wildcard search
language with substitution.  Reference: Python (oracle) and Java."""
from __future__ import annotations

from fx import family

from generators.project import _kit as K

THEME = "quill"
TOOLS = ["quill", "scribe", "inkwell", "stylus", "palimpsest", "redline", "marginal", "scrivener"]
LINES = [
    "item 12: red lantern", "item 7: blue door", "sum=40 total=2", "the quick brown fox", "  indented line here", "ref [3] and [14]", "tab\\there",
    "a-b-c-d", "path/to/file.txt", "end of text.", "x=1;y=22;z=333", "Alpha beta Gamma", "id#0042 ok", "last line", "", "quoted \\\"words\\\" here",
]

PLAN = [
    dict(lang="java", gravity="right", redo="visited", group=True, classes=True, digit=True, anchors=True, register=True),
    dict(lang="python", gravity="left", redo="newest", group=False, classes=True, digit=False, anchors=True, register=False),
    dict(lang="java", gravity="left", redo="visited", group=False, classes=False, digit=True, anchors=False, register=True),
    dict(lang="python", gravity="right", redo="newest", group=True, classes=False, digit=True, anchors=True, register=True),
    dict(lang="java", gravity="right", redo="newest", group=False, classes=True, digit=False, anchors=False, register=False),
    dict(lang="python", gravity="left", redo="visited", group=True, classes=True, digit=True, anchors=False, register=False),
    dict(lang="java", gravity="left", redo="newest", group=True, classes=True, digit=False, anchors=True, register=True),
    dict(lang="python", gravity="right", redo="visited", group=False, classes=False, digit=False, anchors=True, register=True),
]

VOICES = [
    "We need the core of a small scripted text editor: a buffer, marks that follow the text, an undo *tree* (not a stack) and a wildcard search-and-replace. `README.md` defines every command, every output line and every error text. The program is `{tool}`, in {Lang}; it is {run}. Run the visible examples with `python3 tests/run_examples.py`. The hidden checks run long editing sessions, so the exact rules for marks and for moving around the undo tree matter.",
    "implement {tool} per README.md ({Lang}). {run}. it's an editor core driven from stdin: ins/del/rep, marks with gravity, undo tree with goto, wildcard find/sub. the mark rules when text is inserted exactly at a mark, and redo's choice of branch, are where people go wrong. examples: `python3 tests/run_examples.py`",
    "Ticket EDT-{num}: build the `{tool}` editor engine (spec: README.md).\n\nLanguage: {Lang}; the program is {run}. Output is compared exactly, so use the node ids, labels and error messages from the README. Please keep the buffer, the history and the pattern matcher in separate classes or modules.",
    "Could you write the editor core described in README.md? It reads a script on standard input (`ins`, `del`, `rep`, `mark`, `undo`, `redo`, `goto`, `find`, `sub`, ...) and prints what each command reports. {Lang} please; the program is {run}. `python3 tests/run_examples.py` runs a few examples; the hidden checks are much longer sessions, grouped by feature.",
    "Greenfield in {Lang}: `{tool}`, the engine of a modal-less line editor with branching undo. Everything is specified in README.md: position and length checks, mark gravity, the undo tree and its `tree` printout, the wildcard pattern syntax and substitution. {run}. Score is per group of hidden checks, so partial implementations still count.",
    "README.md describes {tool}. Please implement it in {Lang}: {run}. Careful with: undo applying the *inverse* edit (so marks move as they would for a real edit), `goto` crossing branches, and `suball` matching on the original text from left to right but applying right to left. `python3 tests/run_examples.py` for the visible ones.",
    "short version: scripted editor with undo tree, marks and wildcard search, spec in README.md, write it in {Lang} and call it {tool}. {run}",
    "Please build the editor engine from README.md. Name: `{tool}`. Language: {Lang}; how it is run: {run}. The tricky part is that history is a tree: after undo and a new edit there are two branches, and `redo` and `goto` must follow the README's rules exactly. Visible examples: `python3 tests/run_examples.py`.",
]


def readme(p: dict, tool: str, lang: str, by_name: dict) -> str:
    o: list[str] = []
    w = o.append
    w(f"# {tool}: a scripted text editor core\n")
    w(f"`{tool}` holds one text buffer, edits it under script control, keeps every edit in an undo *tree*, tracks named marks through the edits and searches with a small wildcard language. "
      "It reads a script from standard input and prints what each command reports. There is no screen and no cursor: every position is given explicitly.\n")
    w(f"Build and run it as {K.how_to_run(lang, tool)}. The program reads all of standard input, runs the script line by line and exits. "
      "Exit status: `1` if any `error:` line was printed, otherwise `0`.\n")
    w("## 1. Script, text and positions\n")
    w("* A script line is stripped of white space at both ends; empty lines and lines starting with `#` do nothing. The first word is the command; the commands are listed below, anything else is `error: unknown command 'WORD'`.")
    w("* A failing command prints one `error: ...` line, changes nothing and the script goes on.")
    w("* Texts (`TEXT` arguments) are ASCII. In `TEXT` the escapes `\\n` (newline), `\\t` (tab) and `\\\\` (backslash) are decoded; a backslash followed by anything else stays. "
      "`TEXT` is *everything after the single space* that follows the previous argument, so it may contain spaces; it may be empty only where stated. (Because the whole line is stripped, trailing spaces of a `TEXT` are lost; leading ones after the separator are kept.)")
    w("* The **buffer** is a string of characters; newlines (`\\n`) separate lines. A **position** is a number from 0 to the buffer length: it sits *between* characters (0 is before the first). "
      "Numbers are 1 to 9 decimal digits (`error: bad number 'X'` otherwise). A position beyond the end is `error: position P out of range (0..L)` (`L` is the length); "
      "a range (`POS LEN`) needs `LEN >= 1` (`error: bad length 'X'`) and `POS + LEN <= L` (`error: range P+N beyond end (L)`, with the numbers as parsed). "
      "Checks happen in the order: number syntax of the arguments left to right, then position/length rules.\n")
    w("## 2. Editing commands\n")
    w("Every command that changes the buffer creates one **node** of the undo tree (section 4) and prints `node ID`.\n")
    w("* `load TEXT`: replaces the buffer (an empty `TEXT` gives an empty buffer), removes all marks, forgets the history (the tree becomes the single root node 0) and prints `loaded N chars`. It is not undoable.")
    w("* `ins POS TEXT`: inserts `TEXT` at `POS`. Usage: `error: usage: ins POS TEXT` (no arguments); an empty text is `error: nothing to insert` (checked after the position).")
    w("* `del POS LEN`: deletes `LEN` characters starting at `POS`. Wrong word count: `error: usage: del POS LEN`.")
    w("* `rep POS LEN TEXT`: replaces the `LEN` characters at `POS` by `TEXT` (`TEXT` may be empty, then it is a deletion). Fewer than two arguments: `error: usage: rep POS LEN TEXT`.")
    w("* `show`: prints the buffer line by line as `N|LINE` (`N` from 1; a buffer ending in a newline has a last empty line `N|`); an empty buffer prints `(empty)` only.")
    w("* `text`: prints the buffer in quotes on one line with the escapes encoded the other way (`\\\\`, `\\n`, `\\t`), e.g. `\"a\\nb\"`.")
    if p["register"]:
        w("* `yank POS LEN`: copies that range into the single **register** (prints `yanked LEN`; no history entry). `put POS`: inserts the register at `POS` as a new node (`error: register is empty` if nothing was yanked; checked before the position). Usage texts: `error: usage: yank POS LEN`, `error: usage: put POS`. `load` does not clear the register.")
    else:
        w("* There are no registers in this version: `yank` and `put` are unknown commands.")
    w("")
    w("### Primitive edits\n")
    w("Internally every change is a list of **primitive edits**: `insert(pos, text)` and `delete(pos, text)` (the text that is removed). `ins` is one insert; `del` is one delete; `rep` is a delete followed by an insert at the same position (just the delete when `TEXT` is empty); "
      "`put` is one insert. A node stores its primitive edits; applying them in order performs the command, applying the **inverses in reverse order** undoes it (the inverse of an insert is the delete of the same text at the same position and vice versa).\n")
    w("## 3. Marks\n")
    w("A **mark** is a named position that follows the text. Names are a letter followed by up to 15 letters, digits or `_`. Each mark has a **gravity**, `left` or `right`.\n")
    w(f"* `mark NAME POS [left|right]`: creates or moves a mark (gravity default `{p['gravity']}`; a bad gravity word is `error: bad gravity 'X'`; a bad name `error: bad mark name 'X'`). Prints `mark NAME=POS GRAVITY`. Usage: `error: usage: mark NAME POS [left|right]`. Checks: word count, name, position, gravity.")
    w("* `unmark NAME`: prints `unmarked NAME` (`error: no such mark 'NAME'`); usage `error: usage: unmark NAME`.")
    w("* `marks`: one line `NAME=POS GRAVITY` per mark sorted by name (byte order), or `(no marks)`.")
    w("* `at NAME`: prints the position of the mark (errors as `unmark`; usage `error: usage: at NAME`).")
    w("\nEvery primitive edit adjusts the marks (also those made by undo and redo, which apply primitive edits too, and by `load`, which removes the marks):\n")
    w("* **insert at `p` of `n` characters**: a mark at a position greater than `p` moves right by `n`; a mark exactly at `p` moves right by `n` if its gravity is `right` and stays if it is `left`; marks before `p` stay.")
    w("* **delete at `p` of `r` characters**: a mark greater than `p + r` moves left by `r`; a mark greater than `p` and at most `p + r` goes to `p`; marks at or before `p` stay.")
    w("\nSo `rep` first collapses the marks inside the replaced range onto its start and then lets the gravity decide whether they end up before or after the new text. Marks are *not* saved in nodes: only the primitive edits move them.\n")
    w("## 4. The undo tree\n")
    w("The history is a tree of nodes. Node 0 is the **root** (the state after `load`, or the initial empty buffer). Each editing command (`ins`, `del`, `rep`, `put`" + (", and the `sub` commands below" ) + ") adds a new node numbered one higher than the last node ever created, as a child of the **current** node, and makes it current. Children of a node are kept in creation order.\n")
    w("* `undo [N]` (`N` default 1): moves `N` steps towards the root (stopping at the root), undoing the nodes it leaves, and prints `node ID` of the node it ends at. At the root: `error: nothing to undo`. Checks: more than one argument `error: usage: undo [N]`; `N` must be a number of at least 1 (`error: bad number 'X'`, and `error: bad number '0'` for zero); then the root test.")
    if p["redo"] == "visited":
        w("* `redo [N]`: moves down `N` steps, redoing the nodes it enters, and prints `node ID`. Each node remembers its **last visited child**: the child through which the current node was most recently left upwards or entered downwards (a new node also becomes the last visited child of its parent). "
          "`redo` always takes the last visited child. It stops early when there is no child; `error: nothing to redo` if it cannot move at all. Argument checks as for `undo` (`error: usage: redo [N]`).")
    else:
        w("* `redo [N]`: moves down `N` steps, redoing the nodes it enters, and prints `node ID`. At every step it takes the **newest child** (the one created last) of the current node. It stops early when there is no child; `error: nothing to redo` if it cannot move at all. Argument checks as for `undo` (`error: usage: redo [N]`).")
    lv = "the last visited child" if p["redo"] == "visited" else "nothing (visits are not remembered)"
    w("* `goto ID`: moves to the node with that id: undo up to the nearest common ancestor of the current node and the target, then redo down to the target (applying the primitive edits on the way), and prints `node ID`. "
      "`error: no such node ID` for an unknown id; usage `error: usage: goto ID`." + (" Every step up or down updates the last visited children exactly like `undo` and `redo` do." if p["redo"] == "visited" else ""))
    w("* `tree`: prints the whole tree depth first, children in creation order, one line per node: two spaces of indentation per depth, then `ID LABEL`, and ` <` after the label of the current node. The root's label is `(start)`; other labels: "
      "`ins@POS+LEN`, `del@POS-LEN`, `rep@POS-LEN+NEWLEN` (`NEWLEN` is the length of the new text, possibly 0), `put@POS+LEN`, and for substitutions `sub xN` / `suball xN` (N matches)" +
      ("" if p["group"] else ", or `sub@POS-LEN+NEWLEN` for each node of a `suball`") + ".\n")
    w("## 5. Patterns, `find`, `count`, `sub`, `suball`\n")
    feats = []
    w("A **pattern** is one word (no spaces; write `\\s` for a space). Its elements:\n")
    w("* `?` any one character except newline; `*` any run (possibly empty) of characters that are not newlines.")
    if p["digit"]:
        w("* `#` one decimal digit.")
    if p["classes"]:
        w("* `[abc]`, `[a-f0-9]`, `[^x-z]`: one character in (or, with `^`, not in) the set; ranges `lo-hi`; a `-` before `]` is a plain `-`; a character may be escaped with `\\` inside the class. "
          "Errors: `bad pattern: unterminated class`, `bad pattern: empty class` (for `[]` and `[^]`), `bad pattern: bad range` (`hi` below `lo`).")
    if p["anchors"]:
        w("* `^` as the very first element: only matches at the start of the buffer or right after a newline; `$` as the very last element: only at the end of the buffer or right before a newline (anywhere else `^` and `$` are ordinary characters).")
    w("* `\\x`: the character `x` literally (`\\n` newline, `\\t` tab, `\\s` space, any other `x` itself); a lone `\\` at the end is `bad pattern: trailing backslash`.")
    w("* every other character matches itself" + ("" if (p["digit"] and p["classes"] and p["anchors"]) else " (including " + ", ".join(f"`{c}`" for c, k in (("#", "digit"), ("[", "classes"), ("^` and `$", "anchors")) if not p[k]) + ", which have no special meaning in this version)") + ".")
    w("\nA pattern **matches at** a position when its elements match consecutive characters from there; `*` takes as many characters as possible first and gives back one at a time (backtracking) until the rest of the pattern matches. "
      "The **first match** at or after a start position is the one at the smallest start position; its length is what the greedy search finds first. Empty matches are matches.\n")
    w("* `find PATTERN [from POS]`: prints `found START LEN` for the first match at or after `POS` (default 0), or `not found`. Usage `error: usage: find PATTERN [from POS]` (the word `from` is required for the position). Pattern errors are `error: bad pattern: ...` and are detected before the position is checked.")
    w("* `count PATTERN`: prints the number of **non-overlapping matches**: scan from 0; take the first match at or after the scan position; continue after its end, or one character later if it was empty (so an empty match at position `p` is followed by a search from `p + 1`; the end of the buffer counts as a position).")
    w("* `sub PATTERN TEXT` replaces the first non-overlapping match, `suball PATTERN TEXT` all of them (all matches are found on the text as it is before the command, as for `count`, then applied from the last to the first). "
      "`TEXT` may be empty (the matches are deleted). Output: `K replaced, node ID` where `K` is the number of matches replaced and `ID` the id of the current node afterwards; with no match: `0 replaced`; if nothing changes at all (every match empty and `TEXT` empty) it prints `K replaced` and creates no node. "
      "Usage: `error: usage: sub PATTERN TEXT` / `error: usage: suball PATTERN TEXT` (no pattern).")
    if p["group"]:
        w("  All replacements of one command form **one node** (label `sub xK` or `suball xK`, `K` = number of matches): its primitive edits are, from the last match to the first, a delete of the matched text (if not empty) followed by an insert of `TEXT` (if not empty), each at the match's start.")
    else:
        w("  `sub` makes one node (label `sub xK` with `K` = 1). `suball` makes **one node per match that changes the text**, from the last match to the first (labels `sub@POS-LEN+NEWLEN`: start of the match, matched length, length of `TEXT`); a match that is empty with an empty `TEXT` makes no node. `ID` in the output is the id of the last node created (or the current node if none).")
    w("\n## 6. Examples\n")
    ex = [(c, r) for (c, r) in by_name.values() if c.visible]
    for c, r in ex[:3]:
        w(K.show_case(tool, c, r))
    w("The visible examples (`tests/examples.json`, run with `python3 tests/run_examples.py`) use the same format as the hidden checks.")
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------------------------------------------

def make_cases(p: dict, tool: str, rng) -> list[K.Case]:
    cases: list[K.Case] = []
    cnt: dict[str, int] = {}

    def add(group, lines, visible=False):
        cnt[group] = cnt.get(group, 0) + 1
        cases.append(K.Case(name=f"{group}-{cnt[group]:02d}", group=group, stdin="\n".join(lines) + "\n", visible=visible))

    def text(k=3):
        return "\\n".join(rng.sample(LINES, k))

    def word():
        return rng.choice(["foo", "bar", "ab", "x", "12", "-", "Q9", "hello", " ", "\\n", "\\t", "end."])

    def edit(maxpos=30):
        r = rng.random()
        pos = rng.randint(0, maxpos)
        if r < 0.4:
            return f"ins {pos} {word()}"
        if r < 0.7:
            return f"del {pos} {rng.randint(1, 5)}"
        return f"rep {pos} {rng.randint(1, 4)} {rng.choice(['', word(), word() + word()])}".rstrip()

    # --- plain edits --------------------------------------------------------------------------------------------
    for k in range(4):
        lines = [f"load {text(rng.randint(2, 4))}", "show", "text"]
        for _ in range(rng.randint(8, 14)):
            lines.append(edit())
            if rng.random() < 0.3:
                lines.append(rng.choice(["show", "text"]))
        lines += ["show", "text"]
        add("edit", lines, visible=(k == 0))
    # --- marks -----------------------------------------------------------------------------------------------------
    for k in range(4):
        lines = [f"load {text(3)}"]
        for i in range(4):
            lines.append(f"mark m{i} {rng.choice([0, 3, 5, 10, 12])}" + rng.choice(["", " left", " right"]))
        lines.append("marks")
        for _ in range(8):
            r = rng.choice(["at", "ins", "ins", "del", "rep", "ins"])
            # edits exactly at a mark are what gravity is about
            at = rng.choice([0, 3, 5, 10, 12])
            if r == "at":
                lines.append(f"at m{rng.randint(0, 3)}")
            elif r == "ins":
                lines.append(f"ins {at} {word()}")
            elif r == "del":
                lines.append(f"del {at} {rng.randint(1, 4)}")
            else:
                lines.append(f"rep {at} {rng.randint(1, 3)} {word()}")
            if rng.random() < 0.4:
                lines.append("marks")
        lines += ["unmark m0", "marks", "text", "mark m9 99", "mark bad-name 1", "mark m1 2 up", "at nope"]
        add("marks", lines, visible=False)
    # --- undo tree ---------------------------------------------------------------------------------------------------
    for k in range(5):
        lines = [f"load {text(2)}"]
        for _ in range(rng.randint(3, 5)):
            lines.append(edit(15))
        lines.append("tree")
        for _ in range(rng.randint(4, 7)):
            lines.append(rng.choice(["undo", "undo", "undo 2", "redo", "redo 2", edit(15), f"goto {rng.randint(0, 6)}", "tree", "text"]))
        lines += ["tree", "undo 99", "undo", "redo 99", "text", "goto 0", "redo", "tree", "goto 77", "undo 0", "undo 1 2", "redo x", "goto"]
        add("undo", lines, visible=(k == 0))
    # branches: undo, edit, undo, redo to see which branch redo follows
    for k in range(3):
        lines = [f"load {text(2)}", "ins 0 A", "ins 1 B", "undo", "ins 2 C", "undo", "tree", "redo", "text", "undo 2", "redo 2", "tree",
                 "goto 2", "undo", "goto 3", "tree", "undo", "redo", "tree", "text"]
        if k:
            lines = lines[:8] + [f"mark t {rng.randint(0, 6)}"] + lines[8:] + ["marks"]
        add("branches", lines)
    # --- undo and marks ------------------------------------------------------------------------------------------------
    for k in range(4):
        lines = [f"load {text(3)}", "mark a 4 left", "mark b 4 right", "mark c 7", "mark d 0 left", "mark e 20 right"]
        for _ in range(5):
            lines.append(rng.choice([f"ins 4 {word()}", f"del 3 {rng.randint(1, 4)}", f"rep 4 {rng.randint(1, 3)} {word()}", f"del 0 {rng.randint(1, 3)}"]))
        lines.append("marks")
        for _ in range(6):
            lines.append(rng.choice(["undo", "undo 2", "redo", "redo 3", "goto 0", "marks"]))
        lines += ["marks", "text"]
        add("undo-marks", lines)
    # --- find / count -----------------------------------------------------------------------------------------------------
    pats = ["item", "i?em", "*", "t*e", "o*o", "a*b*c", "#", "##", "item\\s#*:", "[a-c]", "[^a-z]", "[0-9][0-9]", "^t", "^item", "e$", "t.$", "\\[#*\\]", "*=*", "\\*", "[a-]", "[\\]]", "^$", "x?=", "\\n", "t\\tt", "[z-a]", "[", "[]", "abc\\", "$e", "a^b"]
    for k in range(4):
        lines = [f"load {text(rng.randint(3, 5))}"]
        for _ in range(10):
            pat = rng.choice(pats)
            if rng.random() < 0.6:
                lines.append(f"find {pat}" + rng.choice(["", "", f" from {rng.randint(0, 25)}"]))
            else:
                lines.append(f"count {pat}")
        lines += ["find", "find a from", "find a to 3", "find a from 999", "count", "count a b"]
        add("find", lines, visible=False)
    # --- sub / suball --------------------------------------------------------------------------------------------------------
    for k in range(5):
        lines = [f"load {text(rng.randint(3, 5))}", "show"]
        for _ in range(7):
            cmd = rng.choice(["sub", "suball", "suball"])
            pat = rng.choice(["e", "i?", "*", "#", "[a-c]", "o*", "^i", "e$", "t", "\\s", "?"])
            rep = rng.choice(["", "XY", "_", "<>", "z z"])
            lines.append((f"{cmd} {pat} {rep}").rstrip() if rep else f"{cmd} {pat}")
            if rng.random() < 0.5:
                lines.append(rng.choice(["text", "tree", "undo", "redo", "marks"]))
        lines += ["tree", "undo", "text", "sub", "sub a", "suball [", "sub zzzz Q"]
        add("sub", lines, visible=(k == 0))
    # marks through substitutions
    for k in range(2):
        lines = [f"load {text(3)}", "mark a 3 left", "mark b 3 right", "mark c 9", "mark z 30 right", "suball e QQ", "marks", "undo", "marks", "redo", "marks", "suball * -", "marks", "text"]
        add("sub-marks", lines)
    # --- registers ------------------------------------------------------------------------------------------------------------
    lines = [f"load {text(3)}", "yank 2 4", "put 0", "put 5", "text", "yank 0 99", "put 99", "put", "undo", "undo", "tree"]
    if not p["register"]:
        pass
    add("register", lines)
    # --- errors ------------------------------------------------------------------------------------------------------------------
    for k in range(3):
        lines = ["frob", "ins", "ins 0", "ins x abc", "del 1", "del 1 2 3", "rep 1", "undo", "redo", "goto 1", "tree", "show", "text", "marks", "at a", "find a", "count a",
                 "load abc", "ins 4 x", "ins 3 ", "ins 3  two", "del 0 0", "del 2 2", "del 3 1", "del 02 1", "del 1234567890 1", "rep 1 5 z", "rep 0 3", "show", "mark a 1", "mark a 9",
                 "yank 0 1", "put 1", "load", "show", "text", "ins 0 \\n\\n", "show", "text", "load a\\tb\\\\n\\q", "text", "show"]
        rng.shuffle(lines)
        lines = ["load " + text(2)] + lines
        add("errors", lines)
    # --- long sessions ---------------------------------------------------------------------------------------------------------------
    for k in range(10):
        lines = [f"load {text(rng.randint(2, 4))}"]
        for _ in range(rng.randint(25, 45)):
            r = rng.random()
            if r < 0.30:
                lines.append(edit())
            elif r < 0.40:
                lines.append(f"mark m{rng.randint(0, 3)} {rng.randint(0, 20)}" + rng.choice(["", " left", " right"]))
            elif r < 0.60:
                lines.append(rng.choice(["undo", "redo", "undo 2", "redo 2", f"goto {rng.randint(0, 10)}"]))
            elif r < 0.68:
                lines.append(rng.choice(["sub", "suball", "suball"]) + " " + rng.choice(["e", "i?", "#", "[a-c]", "o*", "^i", "t", "\\s", "?"]) + " " + rng.choice(["Q", "zz", "-"]))
            elif r < 0.76:
                lines.append(f"find {rng.choice(['e', 't*e', '#', '[ab]', '^l', 'e$'])}" + rng.choice(["", f" from {rng.randint(0, 20)}"]))
            elif r < 0.80 and p["register"]:
                lines.append(rng.choice([f"yank {rng.randint(0, 10)} {rng.randint(1, 5)}", f"put {rng.randint(0, 15)}"]))
            else:
                lines.append(rng.choice(["marks", "tree", "text", "show", f"at m{rng.randint(0, 3)}"]))
        add("session", lines)
    return cases


@family("project-quill", category="project", lang="java", kind="greenfield", n=8,
        summary="a scripted editor core: buffer with gravity marks, undo tree with goto, wildcard find/sub with backtracking")
def gen(rng, n):
    for i in range(n):
        plan = dict(PLAN[i])
        tool = TOOLS[i]
        lang = plan.pop("lang")
        p = dict(plan)
        cfg = dict(DEFAULT_GRAVITY=p["gravity"], REDO_MODE=p["redo"], SUB_GROUP=p["group"], HAS_CLASSES=p["classes"], HAS_DIGIT=p["digit"],
                   HAS_ANCHORS=p["anchors"], HAS_REGISTER=p["register"])
        cases = make_cases(p, tool, rng)
        py_sol = K.merged(K.load_src(THEME, "python", tool), K.render_config("python", cfg))
        sol = py_sol if lang == "python" else K.merged(K.load_src(THEME, lang, tool), K.render_config(lang, cfg))
        prompt = VOICES[i % len(VOICES)].format(tool=tool, Lang=K.LANG_NAME[lang], run=K.how_to_run(lang, tool), num=6100 + i * 31)
        nfeat = sum([p["redo"] == "visited", p["group"], p["classes"], p["anchors"], p["digit"], p["register"]])
        yield K.project_task(
            theme=THEME, tool=tool, lang=lang, cases=cases, solution=sol, py_solution=py_sol,
            readme=lambda by_name, p=p, tool=tool, lang=lang: readme(p, tool, lang, by_name),
            prompt=prompt, difficulty=5 if nfeat >= 5 else 4, slug=f"{i + 1:02d}-{tool}-{p['redo']}-{lang}",
            notes={k: p[k] for k in ("gravity", "redo", "group", "classes", "digit", "anchors", "register")}, tags=["editor", "undo-tree"],
        )
