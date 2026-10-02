"""A small text-tool CLI whose commands must be implemented AND registered in shared files (registry, docs, changelog)."""
from __future__ import annotations

import json
import random

from fx import Task, dd, family

from ._kit import GRADE_CMD, score_script, team

VOCAB = ["lantern", "ferry", "ledger", "orchard", "tarn", "quill", "bramble", "harbour", "cobble", "mosaic", "ember", "thistle", "pylon",
         "meadow", "gantry", "kiln", "tide", "wicker", "spindle", "fennel", "garret", "sluice", "pennant", "cairn", "dovecote", "brine"]


def words(rng, n):
    return [rng.choice(VOCAB) for _ in range(n)]


def sentence(rng, lo=3, hi=9):
    return " ".join(words(rng, rng.randint(lo, hi)))


def paragraphs(rng, n, blank_ws=True):
    out = []
    for i in range(n):
        for _ in range(rng.randint(1, 4)):
            line = sentence(rng, 2, 8)
            if rng.random() < 0.2:
                line += "   "
            out.append(line)
        for _ in range(rng.choice([1, 1, 2, 3])):
            out.append(rng.choice(["", "", "  ", "\t"]) if blank_ws else "")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------------------------------- command kinds
def K():
    kinds = {}

    def kind(name):
        def deco(fn):
            kinds[name] = fn
            return fn
        return deco

    @kind("squeeze")
    def squeeze(rng):
        keep = rng.choice([1, 1, 2])
        src = f'''"""squeeze command."""


def run(text, opts):
    keep = int(opts.get("keep", {keep}))
    out, blanks = [], 0
    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            blanks += 1
            continue
        if out and blanks:
            out.extend([""] * min(blanks, keep))
        blanks = 0
        out.append(line)
    return "".join(l + "\\n" for l in out)
'''
        doc = (f"Remove trailing whitespace from every line. A run of blank lines (empty or whitespace-only) is cut down to at most `keep` blank lines "
               f"(option `keep`, default {keep}); blank lines at the very start and at the end of the text are dropped. Every output line, including the last, "
               "ends with a newline; empty input gives empty output.")
        cases = lambda r: [(paragraphs(r, r.randint(2, 4)), {}), (paragraphs(r, 3), {"keep": 2}), (paragraphs(r, 3), {"keep": 0}), ("\n\n  \n", {}), ("", {})]
        return dict(src=src, doc=doc, summary=f"Squeeze runs of blank lines (default keep {keep})", cases=cases)

    @kind("indent")
    def indent(rng):
        width = rng.choice([2, 4, 8])
        src = f'''"""indent command."""


def run(text, opts):
    width = int(opts.get("width", {width}))
    pad = ("\\t" if opts.get("tab") else " ") * width
    return "".join((pad + line if line.strip() else "") + "\\n" for line in text.splitlines())
'''
        doc = (f"Indent every non-blank line by `width` characters (option `width`, default {width}): spaces, or tab characters when the flag `tab` is given. "
               "Blank lines (empty or whitespace-only) become empty lines. Output lines all end with a newline.")
        cases = lambda r: [(paragraphs(r, 2), {}), (paragraphs(r, 2), {"width": 3}), (paragraphs(r, 2), {"width": 2, "tab": True}), ("", {}), ("one\n", {"width": 0})]
        return dict(src=src, doc=doc, summary=f"Indent non-blank lines (default width {width})", cases=cases)

    @kind("numberlines")
    def numberlines(rng):
        start, width, sep = rng.choice([1, 0, 10]), rng.choice([3, 4, 6]), rng.choice([": ", " | ", "\\t"])
        sep_doc = {": ": "`: `", " | ": "` | `", "\\t": "a tab"}[sep]
        src = f'''"""numberlines command."""


def run(text, opts):
    n = int(opts.get("start", {start}))
    width = int(opts.get("width", {width}))
    sep = {sep!r}
    skip = bool(opts.get("skipblank"))
    out = []
    for line in text.splitlines():
        if skip and not line.strip():
            out.append(" " * width + sep + line)
            continue
        out.append(str(n).rjust(width) + sep + line)
        n += 1
    return "".join(l + "\\n" for l in out)
'''
        doc = (f"Prefix every line with its number, right-aligned to `width` characters (option `width`, default {width}), then {sep_doc}. "
               f"The first number is `start` (option, default {start}). With the flag `skipblank`, a blank line (empty or whitespace-only) is not "
               "numbered and does not use up a number: its prefix is `width` spaces followed by the same separator. Lines are copied unchanged otherwise.")
        cases = lambda r: [(paragraphs(r, 2), {}), (paragraphs(r, 2), {"skipblank": True}), (paragraphs(r, 1), {"start": 98, "width": 3}), ("", {}), ("a\n\nb\n", {"skipblank": True, "start": 5})]
        return dict(src=src, doc=doc, summary=f"Number lines (width {width}, starting at {start})", cases=cases)

    @kind("fieldpick")
    def fieldpick(rng):
        delim = rng.choice([",", ":", ";"])
        src = f'''"""fieldpick command."""


def run(text, opts):
    delim = str(opts.get("delim", {delim!r}))
    picks = [int(p) for p in str(opts.get("cols", "1")).split(",")]
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split(delim)
        row = []
        for p in picks:
            i = p - 1 if p > 0 else len(fields) + p
            row.append(fields[i] if 0 <= i < len(fields) else "")
        out.append(delim.join(row))
    return "".join(l + "\\n" for l in out)
'''
        doc = (f"Split every non-blank line on `delim` (option, default `{delim}`) and print the chosen columns joined by the same delimiter. `cols` is a comma-separated "
               "list of 1-based column numbers (default `1`); a negative number counts from the end (`-1` is the last column); a column that does not exist "
               "gives an empty field. Blank lines (empty or whitespace-only) are skipped. Number strings given through the CLI arrive as integers or strings: "
               "accept both for `cols`, e.g. `3` or `\"2,-1\"`.")

        def cases(r):
            rows = "\n".join(delim.join(r.choice(VOCAB) for _ in range(r.randint(1, 5))) for _ in range(6)) + "\n\n" + delim.join(words(r, 3)) + "\n"
            return [(rows, {}), (rows, {"cols": "2,1"}), (rows, {"cols": "-1"}), (rows, {"cols": "3,-2,9"}), (rows, {"cols": 2}), ("a;b;c\n", {"delim": ";", "cols": "3,2"})]
        return dict(src=src, doc=doc, summary=f"Pick columns from delimited lines (delimiter {delim!r})", cases=cases)

    @kind("wrapat")
    def wrapat(rng):
        width = rng.choice([30, 40, 60])
        src = f'''"""wrapat command."""


def run(text, opts):
    width = int(opts.get("width", {width}))
    paras, cur = [], []
    for line in text.splitlines():
        if line.strip():
            cur.extend(line.split())
        elif cur:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    blocks = []
    for ws in paras:
        lines, line = [], ""
        for w in ws:
            while len(w) > width:
                if line:
                    lines.append(line)
                    line = ""
                lines.append(w[:width])
                w = w[width:]
            if not line:
                line = w
            elif len(line) + 1 + len(w) <= width:
                line += " " + w
            else:
                lines.append(line)
                line = w
        if line:
            lines.append(line)
        blocks.append("\\n".join(lines))
    return "\\n\\n".join(blocks) + ("\\n" if blocks else "")
'''
        doc = (f"Reflow the text to lines of at most `width` characters (option, default {width}). Paragraphs are separated by one or more blank lines "
               "(empty or whitespace-only); inside a paragraph all whitespace runs collapse to single spaces and words are packed greedily onto lines. "
               "A word longer than `width` is cut into pieces of exactly `width` characters, the last piece continuing the line like a short word. Paragraphs are "
               "output separated by exactly one blank line, and the output ends with one newline; empty input gives empty output.")

        def cases(r):
            long_word = "x" * 23
            text = paragraphs(r, 3) + f"\ncarry {long_word} over   tabs\tand   gaps\n"
            return [(text, {}), (text, {"width": 12}), (paragraphs(r, 2), {"width": 20}), ("", {}), ("\n \n", {}), ("one\n", {"width": 3})]
        return dict(src=src, doc=doc, summary=f"Re-wrap paragraphs (default width {width})", cases=cases)

    @kind("headtail")
    def headtail(rng):
        head, tail = rng.choice([3, 5]), rng.choice([2, 3])
        src = f'''"""headtail command."""


def run(text, opts):
    head = int(opts.get("head", {head}))
    tail = int(opts.get("tail", {tail}))
    lines = text.splitlines()
    if len(lines) <= head + tail:
        return "".join(l + "\\n" for l in lines)
    omitted = len(lines) - head - tail
    kept = lines[:head] + ["... (%d lines omitted)" % omitted] + (lines[len(lines) - tail:] if tail else [])
    return "".join(l + "\\n" for l in kept)
'''
        doc = (f"Keep the first `head` and the last `tail` lines (options, defaults {head} and {tail}). If lines were left out, a single line `... (K lines omitted)` "
               "(K is the number of omitted lines) stands between the two parts. If the text has at most `head + tail` lines it is copied unchanged. Output lines end with a newline.")

        def cases(r):
            many = "\n".join(sentence(r, 1, 4) for _ in range(30)) + "\n"
            few = "\n".join(sentence(r, 1, 4) for _ in range(head + tail)) + "\n"
            return [(many, {}), (many, {"head": 1, "tail": 1}), (many, {"tail": 0}), (few, {}), ("", {}), (many, {"head": 29, "tail": 1})]
        return dict(src=src, doc=doc, summary=f"Show the head and tail of a text (default {head} and {tail} lines)", cases=cases)

    @kind("dedupe")
    def dedupe(rng):
        suffix = rng.choice([" (x%d)", " [%d]", " *%d"])
        shown = suffix.replace("%d", "N")
        src = f'''"""dedupe command."""


def run(text, opts):
    icase = bool(opts.get("icase"))
    count = bool(opts.get("count"))
    groups = []
    for line in text.splitlines():
        key = line.lower() if icase else line
        if groups and groups[-1][0] == key:
            groups[-1][2] += 1
        else:
            groups.append([key, line, 1])
    return "".join((line + ({suffix!r} % n if count and n > 1 else "")) + "\\n" for _, line, n in groups)
'''
        doc = ("Collapse runs of identical adjacent lines into the first line of the run (its text is kept). Lines are compared exactly; with the flag `icase` "
               f"they are compared ignoring case. With the flag `count`, a collapsed run of N > 1 lines gets the suffix `{shown}`. Only adjacent repeats "
               "are collapsed. Output lines end with a newline.")

        def cases(r):
            base = []
            for _ in range(10):
                line = sentence(r, 1, 3)
                base += [line] * r.randint(1, 4)
                if r.random() < 0.4:
                    base.append(line.upper())
            return [("\n".join(base) + "\n", {}), ("\n".join(base) + "\n", {"count": True}), ("\n".join(base) + "\n", {"icase": True, "count": True}), ("", {}), ("a\nA\na\n", {"icase": True, "count": True})]
        return dict(src=src, doc=doc, summary=f"Collapse adjacent duplicate lines (count suffix `{shown}`)", cases=cases)

    @kind("columnize")
    def columnize(rng):
        cols = rng.choice([2, 3, 4])
        src = f'''"""columnize command."""


def run(text, opts):
    cols = int(opts.get("cols", {cols}))
    ws = text.split()
    if not ws:
        return ""
    rows = -(-len(ws) // cols)
    grid = [ws[c * rows:(c + 1) * rows] for c in range(cols)]
    widths = [max((len(w) for w in col), default=0) for col in grid]
    out = []
    for r in range(rows):
        cells = [grid[c][r].ljust(widths[c]) if r < len(grid[c]) else "" for c in range(cols)]
        out.append("  ".join(cells).rstrip())
    return "".join(l + "\\n" for l in out)
'''
        doc = (f"Arrange the whitespace-separated words of the text into `cols` columns (option, default {cols}), filled column by column (down first, then across): "
               "the number of rows is `ceil(words / cols)`; column 1 takes the first that-many words, column 2 the next ones, and so on (later columns may be short or even empty). "
               "Each column is left-justified to its widest word, columns are separated by two spaces and trailing spaces are stripped from every line. "
               "No words give empty output.")

        def cases(r):
            return [(paragraphs(r, 2), {}), (paragraphs(r, 2), {"cols": 5}), (" ".join(words(r, 7)), {"cols": 3}), ("", {}), ("solo", {"cols": 4}), (" ".join(words(r, 13)), {"cols": 4})]
        return dict(src=src, doc=doc, summary=f"Arrange words into columns (default {cols})", cases=cases)

    @kind("grepctx")
    def grepctx(rng):
        ctx = rng.choice([1, 2])
        src = f'''"""grepctx command."""


def run(text, opts):
    pat = opts.get("pat")
    if not pat:
        raise ValueError("option pat is required")
    pat = str(pat)
    ctx = int(opts.get("ctx", {ctx}))
    lines = text.splitlines()
    hits = [i for i, l in enumerate(lines) if pat in l]
    shown = {{}}
    for i in hits:
        for j in range(max(0, i - ctx), min(len(lines), i + ctx + 1)):
            shown[j] = shown.get(j, False) or j == i
    out, prev = [], None
    for j in sorted(shown):
        if prev is not None and j != prev + 1:
            out.append("--")
        out.append(("* " if shown[j] else "  ") + lines[j])
        prev = j
    return "".join(l + "\\n" for l in out)
'''
        doc = (f"Print the lines that contain the option `pat` (a plain case-sensitive substring; missing or empty `pat` raises `ValueError`) together with `ctx` lines of context "
               f"on each side (option, default {ctx}). Matching lines are prefixed with `* `, context lines with two spaces. Overlapping or touching context is shown once; "
               "two shown stretches that are not adjacent in the input are separated by a line `--`. No match gives empty output.")

        def cases(r):
            lines = [sentence(r, 2, 5) for _ in range(24)]
            pat = r.choice(VOCAB)
            text = "\n".join(lines) + "\n"
            return [(text, {"pat": pat}), (text, {"pat": pat, "ctx": 0}), (text, {"pat": pat, "ctx": 3}), (text, {"pat": "zzzz"}), ("a\nb\nc\nb\n", {"pat": "b", "ctx": 1})]
        return dict(src=src, doc=doc, summary=f"Grep with context lines (default {ctx})", cases=cases, raises=[({"pat": ""}, "ValueError"), ({}, "ValueError")])

    @kind("bullets")
    def bullets(rng):
        char = rng.choice(["-", "*", "+"])
        src = f'''"""bullets command."""
import re


def run(text, opts):
    char = str(opts.get("char", {char!r}))
    out = []
    for line in text.splitlines():
        m = re.match(r"^(\\s*)[*+\\u2022-] (.*)$", line)
        out.append(m.group(1) + char + " " + m.group(2) if m else line)
    return "".join(l + "\\n" for l in out)
'''
        doc = (f"Make list bullets uniform. A line is a bullet line when, after optional leading whitespace, it has one of the characters `*`, `+`, `-` or `•` followed by a space; "
               f"that character is replaced by `char` (option, default `{char}`), keeping the indentation and the text. Every other line is copied unchanged. "
               "Output lines end with a newline.")

        def cases(r):
            lines = []
            for _ in range(14):
                b = r.choice(["*", "-", "+", "•", "", "-"])
                ind = " " * r.choice([0, 0, 2, 4])
                lines.append(f"{ind}{b} {sentence(r, 1, 4)}" if b else sentence(r, 1, 4))
            lines += ["-no space", "  * nested  ", "--- rule ---"]
            text = "\n".join(lines) + "\n"
            return [(text, {}), (text, {"char": "*"}), (text, {"char": "•"}), ("", {})]
        return dict(src=src, doc=doc, summary=f"Normalise list bullets (default {char!r})", cases=cases)

    @kind("boxtext")
    def boxtext(rng):
        pad = rng.choice([0, 1, 2])
        src = f'''"""boxtext command."""


def run(text, opts):
    pad = int(opts.get("pad", {pad}))
    lines = text.splitlines()
    inner = max((len(l) for l in lines), default=0) + 2 * pad
    bar = "+" + "-" * inner + "+"
    body = ["|" + " " * pad + l.ljust(inner - 2 * pad) + " " * pad + "|" for l in lines]
    return "".join(l + "\\n" for l in [bar] + body + [bar])
'''
        doc = (f"Draw a box around the text. Let `inner` be the length of the longest line plus `2 * pad` (`pad` is an option, default {pad}). The first and last line are `+`, "
               "`inner` dashes and `+`. Each text line becomes `|`, `pad` spaces, the line left-justified to the longest line's length, `pad` spaces, `|`. "
               "Empty input gives just the two bars with `inner` equal to `2 * pad`. Output lines end with a newline.")

        def cases(r):
            return [("\n".join(sentence(r, 1, 3) for _ in range(3)) + "\n", {}), ("short\nmuch longer line here\nmid\n", {"pad": 2}), ("x\n", {"pad": 0}), ("", {}), ("a\n\nb\n", {"pad": 1})]
        return dict(src=src, doc=doc, summary=f"Draw an ASCII box around text (default padding {pad})", cases=cases)

    @kind("sortblocks")
    def sortblocks(rng):
        by = rng.choice(["first", "last"])
        idx = "0" if by == "first" else "-1"
        src = f'''"""sortblocks command."""


def run(text, opts):
    blocks, cur = [], []
    for line in text.splitlines():
        if line.strip():
            cur.append(line)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    key = (lambda b: b[{idx}].lower()) if opts.get("icase") else (lambda b: b[{idx}])
    ordered = sorted(blocks, key=key, reverse=bool(opts.get("reverse")))
    return "\\n".join("\\n".join(b) + "\\n" for b in ordered)
'''
        doc = (f"Sort the paragraphs of the text. A paragraph is a maximal run of non-blank lines (blank = empty or whitespace-only); paragraphs are ordered by their {by} line, "
               "compared exactly (upper case sorts before lower case), or ignoring case with the flag `icase`. The sort is stable. The flag `reverse` sorts descending "
               "(still stable: equal keys keep their input order). Output paragraphs are separated by exactly one blank line and the output ends with one newline; "
               "no paragraphs give empty output.")

        def cases(r):
            blocks = ["\n".join([r.choice(["Alpha", "alpha", "Beta", "beta", "Gamma", "delta"]) + " " + sentence(r, 1, 2) for _ in range(r.randint(1, 3))]) for _ in range(7)]
            text = "\n\n".join(blocks) + "\n"
            return [(text, {}), (text, {"reverse": True}), (text, {"icase": True}), (text, {"icase": True, "reverse": True}), ("", {}), ("b\n\n\na\nz\n", {})]
        return dict(src=src, doc=doc, summary=f"Sort paragraphs by their {by} line", cases=cases)

    return kinds


KINDS = K()
KIND_NAMES = sorted(KINDS)

MAIN_PY = '''"""Command line entry: python3 -m toolbench COMMAND [--option VALUE | --flag] < input"""
import importlib
import re
import sys

from .registry import COMMANDS


def parse_options(argv):
    opts, i = {}, 0
    while i < len(argv):
        a = argv[i]
        if not a.startswith("--"):
            raise SystemExit("unexpected argument: " + a)
        key = a[2:]
        if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            v = argv[i + 1]
            opts[key] = int(v) if re.fullmatch(r"-?[0-9]+", v) else v
            i += 2
        else:
            opts[key] = True
            i += 1
    return opts


def main(argv):
    if not argv or argv[0] not in COMMANDS:
        raise SystemExit("usage: python3 -m toolbench COMMAND [options]; commands: " + ", ".join(sorted(COMMANDS)))
    run = importlib.import_module(COMMANDS[argv[0]]).run
    sys.stdout.write(run(sys.stdin.read(), parse_options(argv[1:])))


if __name__ == "__main__":
    main(sys.argv[1:])
'''

STUB = '''"""{name} command (see SPECS.md)."""


def run(text, opts):
    raise NotImplementedError("{name}: see SPECS.md")
'''

CHECK_SHARED = '''import ast
import json
import os
import re
import subprocess
import sys

DATA = json.loads(%(data)r)


def fail(msg):
    print("FAILED:", msg, file=sys.stderr)
    sys.exit(1)


def check_registry():
    src = open("toolbench/registry.py", encoding="utf-8").read()
    if re.search(r"^(<{7}|={7}|>{7})", src, re.M):
        fail("merge markers in registry.py")
    tree = ast.parse(src)
    keys = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "COMMANDS" for t in node.targets) and isinstance(node.value, ast.Dict):
            keys = [k.value for k in node.value.keys]
            got = dict(zip(keys, [v.value for v in node.value.values]))
    if keys is None:
        fail("COMMANDS dict literal not found")
    want = DATA["registry"]
    if got != want:
        fail("registry entries differ: missing %%s, unexpected %%s" %% (sorted(set(want) - set(got)), sorted(set(got) - set(want))))
    if len(keys) != len(set(keys)):
        fail("duplicate keys in registry")
    if keys != sorted(keys):
        fail("registry entries are not sorted by name")


def check_docs():
    text = open("docs/COMMANDS.md", encoding="utf-8").read()
    if re.search(r"^(<{7}|={7}|>{7})", text, re.M):
        fail("merge markers in docs/COMMANDS.md")
    rows = re.findall(r"^\\| `([a-z]+)` \\| (.*?) \\|$", text, re.M)
    want = DATA["docs"]
    if [r[0] for r in rows] != [w[0] for w in want]:
        fail("docs table rows are %%s, want %%s (sorted by command)" %% ([r[0] for r in rows], [w[0] for w in want]))
    for (name, summary), (wn, ws) in zip(rows, want):
        if summary != ws:
            fail("docs row %%s has summary %%r, want %%r" %% (name, summary, ws))
    if not text.startswith(DATA["docs_head"]):
        fail("docs/COMMANDS.md header changed")


def check_changelog():
    text = open("CHANGELOG.md", encoding="utf-8").read()
    if re.search(r"^(<{7}|={7}|>{7})", text, re.M):
        fail("merge markers in CHANGELOG.md")
    head, sep, rest = text.partition("## Unreleased\\n")
    if not sep or head != DATA["cl_head"]:
        fail("changelog preamble changed")
    unreleased, sep2, older = rest.partition("\\n## ")
    if (sep2 + older) != DATA["cl_older"]:
        fail("older releases in CHANGELOG.md were modified")
    bullets = re.findall(r"^- `([a-z]+)`: (.*)$", unreleased, re.M)
    want = DATA["changelog"]
    if bullets != [tuple(w) for w in want]:
        fail("Unreleased entries are %%r, want %%r" %% (bullets, [tuple(w) for w in want]))
    if "### Added" not in unreleased:
        fail("### Added heading missing")


def check_command(name):
    mod = __import__("toolbench.commands." + name, fromlist=["run"])
    for text, opts, want in DATA["cases"][name]:
        got = mod.run(text, dict(opts))
        if got != want:
            fail("command %%s with options %%r on %%r\\n  got  %%r\\n  want %%r" %% (name, opts, text[:80], got, want))
    for opts, exc in DATA["raises"].get(name, []):
        try:
            mod.run("x\\n", dict(opts))
        except Exception as e:  # noqa: BLE001
            if type(e).__name__ != exc:
                fail("%%s with %%r raised %%s, want %%s" %% (name, opts, type(e).__name__, exc))
        else:
            fail("%%s with %%r should raise %%s" %% (name, opts, exc))


def check_cli():
    for name in DATA["new"]:
        for text, opts, want in DATA["cases"][name][:3]:
            argv = [sys.executable, "-m", "toolbench", name]
            for k, v in opts.items():
                argv.append("--" + k)
                if v is not True:
                    argv.append(str(v))
            p = subprocess.run(argv, input=text, capture_output=True, text=True, timeout=20)
            if p.returncode != 0 or p.stdout != want:
                fail("cli %%s %%r: exit %%s output %%r want %%r %%s" %% (name, opts, p.returncode, p.stdout[:120], want[:120], p.stderr[-200:]))


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    what = sys.argv[1]
    if what == "registry":
        check_registry()
    elif what == "docs":
        check_docs()
    elif what == "changelog":
        check_changelog()
    elif what == "cli":
        check_cli()
    else:
        check_command(what)
'''


def load_run(src):
    ns: dict = {}
    exec(compile(src, "<cmd>", "exec"), ns)  # our own generated code
    return ns["run"]


@family("swarm-registry-merge", category="swarm", lang="python", kind="feature", n=12,
        summary="k new CLI commands that must each be implemented and registered in three shared files (registry, docs table, changelog)")
def registry_merge(rng, n):
    counts = [3, 4, 4, 5, 3, 5, 6, 4, 6, 5, 3, 7]
    tools = [("toolbench", "Toolbench", "small text filters for the lab's report pipeline"), ("scrivener", "Scrivener", "plain-text cleanup commands for a print shop"),
             ("quillbox", "Quillbox", "command line helpers for a poetry-journal's editors"), ("inkwell", "Inkwell", "text utilities for a small newsroom")]
    for i in range(n):
        k = counts[i % len(counts)]
        names = list(KIND_NAMES)
        rng.shuffle(names)
        existing_names = sorted(names[:3])
        new_names = sorted(names[3:3 + k])
        spec = {nm: KINDS[nm](rng) for nm in existing_names + new_names}
        pkg, disp, blurb = "toolbench", "Toolbench", tools[i % len(tools)][2]
        cases, raises = {}, {}
        for nm in new_names:
            run_fn = load_run(spec[nm]["src"])
            cs = []
            for text, opts in spec[nm]["cases"](rng):
                cs.append([text, opts, run_fn(text, dict(opts))])
            cases[nm] = cs
            raises[nm] = [[o, e] for o, e in spec[nm].get("raises", [])]
        registry = {nm: f"toolbench.commands.{nm}" for nm in sorted(existing_names + new_names)}
        docs_head = "# Commands\n\nEvery command reads text on stdin and writes text on stdout. Options are `--name value` or a bare `--flag`.\n\n| command | summary |\n|---|---|\n"
        docs_rows = [(nm, spec[nm]["summary"]) for nm in sorted(existing_names + new_names)]
        pre_unrel = existing_names[0]
        cl_head = "# Changelog\n\nAll notable changes to this project are listed here, newest first.\n\n"
        cl_older = ("\n## 0.4.0\n\n### Added\n\n" + "\n".join(f"- `{nm}`: {spec[nm]['summary']}" for nm in existing_names[1:]) +
                    "\n\n## 0.3.0\n\n### Added\n\n- initial release with the command runner\n")
        changelog_want = [(nm, spec[nm]["summary"]) for nm in sorted(existing_names[:1] + new_names)]
        data = {"registry": registry, "docs": docs_rows, "docs_head": docs_head, "cl_head": cl_head, "cl_older": cl_older, "changelog": changelog_want,
                "cases": cases, "raises": raises, "new": new_names}
        start = {
            "README.md": dd(f'''
                # {disp}

                {blurb[0].upper() + blurb[1:]}. `python3 -m toolbench COMMAND [options] < input` runs one command.

                Adding a command means four things: its module in `toolbench/commands/`, a line in `toolbench/registry.py`,
                a row in `docs/COMMANDS.md` and a bullet in the Unreleased section of `CHANGELOG.md`. The last three are
                shared files, kept **sorted by command name**.
            '''),
            "toolbench/__init__.py": "",
            "toolbench/__main__.py": MAIN_PY,
            "toolbench/registry.py": '"""Command registry: every command listed here, one per line, sorted by name."""\n\nCOMMANDS = {\n'
                                     + "".join(f'    "{nm}": "toolbench.commands.{nm}",\n' for nm in existing_names) + "}\n",
            "toolbench/commands/__init__.py": "",
            "docs/COMMANDS.md": docs_head + "".join(f"| `{nm}` | {spec[nm]['summary']} |\n" for nm in existing_names),
            "CHANGELOG.md": cl_head + "## Unreleased\n\n### Added\n\n" + f"- `{pre_unrel}`: {spec[pre_unrel]['summary']}\n" + cl_older,
        }
        # the changelog of the start must satisfy the head/older split used by the checker
        for nm in existing_names:
            start[f"toolbench/commands/{nm}.py"] = spec[nm]["src"]
        for nm in new_names:
            start[f"toolbench/commands/{nm}.py"] = STUB.format(name=nm)
        specs_md = ["# Specs for the new commands", "",
                    "Each command is `run(text, opts) -> str` in `toolbench/commands/<name>.py`. `opts` is a dict; options given as `--name value` arrive as `int` when the "
                    "value looks like an integer and as `str` otherwise, a bare `--flag` arrives as `True`. A missing option means its documented default.",
                    "For the shared files use the exact **summary line** given for each command.", ""]
        for nm in new_names:
            specs_md += [f"## `{nm}`", "", f"Summary line: `{spec[nm]['summary']}`", "", spec[nm]["doc"], ""]
        start["SPECS.md"] = "\n".join(specs_md)
        # existing visible tests: a tiny smoke test of an existing command through the CLI
        ex = existing_names[0]
        ex_case = spec[ex]["cases"](rng)[0]
        ex_run = load_run(spec[ex]["src"])
        start["tests/test_existing.py"] = dd(f'''
            import os
            import sys
            import unittest

            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
            from toolbench.commands import {ex}


            class ExistingCommands(unittest.TestCase):
                def test_{ex}(self):
                    self.assertEqual({ex}.run({ex_case[0]!r}, {ex_case[1]!r}), {ex_run(ex_case[0], dict(ex_case[1]))!r})


            if __name__ == "__main__":
                unittest.main()
        ''')
        hidden = {".grade/check_shared.py": CHECK_SHARED % {"data": json.dumps(data, sort_keys=True)}}
        units = [{"name": f"command {nm}", "cmd": ["python3", ".grade/check_shared.py", nm], "weight": 1} for nm in new_names]
        for what in ("registry", "docs", "changelog", "cli"):
            units.append({"name": f"shared: {what}", "cmd": ["python3", ".grade/check_shared.py", what], "weight": 1})
        hidden[".grade/score.py"] = score_script(units)
        solution = {}
        reg = dict(registry)
        for nm in new_names:
            solution[f"toolbench/commands/{nm}.py"] = spec[nm]["src"]
        solution["toolbench/registry.py"] = '"""Command registry: every command listed here, one per line, sorted by name."""\n\nCOMMANDS = {\n' + "".join(f'    "{nm}": "{mod}",\n' for nm, mod in sorted(reg.items())) + "}\n"
        solution["docs/COMMANDS.md"] = docs_head + "".join(f"| `{nm}` | {sm} |\n" for nm, sm in docs_rows)
        solution["CHANGELOG.md"] = cl_head + "## Unreleased\n\n### Added\n\n" + "".join(f"- `{nm}`: {sm}\n" for nm, sm in changelog_want) + cl_older
        voices = [
            f"We need {k} new commands in {disp} ({blurb}). SPECS.md describes each one. Beyond the module itself every command has to be registered, "
            f"listed in the docs table and noted in the changelog; those three files are shared and sorted, so please coordinate and check that nothing gets lost.",
            f"Add the commands from SPECS.md to {disp}: {', '.join(new_names)}. Each is a stub in toolbench/commands/. Remember the registry, docs/COMMANDS.md "
            f"and CHANGELOG.md; the README explains the conventions.",
            f"{disp} release prep: {k} commands are still missing ({', '.join(new_names)}). Work them in parallel if you can, but the shared files "
            f"(registry, command table, changelog) have to end consistent and sorted. `python3 -m toolbench <command>` must work for each.",
            f"Implement the new commands described in SPECS.md and wire each one up completely (registry line, docs row, changelog bullet). "
            f"Existing entries must stay exactly as they are.",
        ]
        d = 3 if k <= 3 else 4 if k <= 5 else 5
        yield Task(
            slug=f"{i + 1:02d}-k{k}-{new_names[0]}",
            prompt=voices[i % len(voices)], difficulty=d,
            start=start, hidden=hidden, solution=solution,
            verify=GRADE_CMD, pass_mode="json-score",
            team=team(rng, min(k, 6)),
            tags=["shared-registry", "merge-conflicts", "cli"],
            notes={"existing": existing_names, "new": new_names},
        )
