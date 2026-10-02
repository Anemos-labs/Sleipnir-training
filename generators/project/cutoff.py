"""project-cutoff: an incremental build engine for text artifacts with invented rule syntax, content digests or logical clocks,
pattern rules, always-rules, action budgets and failure policies.  Reference: Python (oracle) and Go."""
from __future__ import annotations

from fx import dd, family

from generators.project import _kit as K

THEME = "cutoff"
TOOLS = ["stoke", "kiln", "anvil", "weft", "smelt", "rivet", "mortar", "quarry"]
ALL_ACTIONS = ["cat", "upper", "lower", "rev", "count", "lines", "head", "sort", "uniq", "grep", "tag", "sum", "cap", "const", "failif", "fail"]
WORDS = ["red", "blue", "green", "ink", "salt", "ash", "oak", "tin", "rye", "elm"]
NUMS = ["3", "7", "12", "40", "-5", "0", "9", "100"]

# one entry per instance: (lang, mode, patterns, always, budget, keep_going, status, clean, touch)
PLAN = [
    dict(lang="go", mode="digest", patterns=True, always=False, budget=False, keep=True, status=True, clean=True, touch=False, build="build", put="put", summary="summary"),
    dict(lang="python", mode="clock", patterns=False, always=False, budget=True, keep=False, status=True, clean=True, touch=True, build="make", put="write", summary="result"),
    dict(lang="go", mode="clock", patterns=True, always=True, budget=True, keep=True, status=True, clean=True, touch=True, build="want", put="set", summary="tally"),
    dict(lang="python", mode="digest", patterns=True, always=True, budget=False, keep=False, status=False, clean=True, touch=True, build="build", put="write", summary="totals"),
    dict(lang="go", mode="digest", patterns=True, always=True, budget=True, keep=True, status=True, clean=True, touch=True, build="make", put="put", summary="summary"),
    dict(lang="go", mode="clock", patterns=False, always=True, budget=False, keep=True, status=False, clean=False, touch=True, build="want", put="write", summary="tally"),
    dict(lang="python", mode="digest", patterns=False, always=False, budget=True, keep=True, status=True, clean=True, touch=False, build="build", put="set", summary="result"),
    dict(lang="go", mode="digest", patterns=True, always=False, budget=True, keep=False, status=True, clean=False, touch=True, build="make", put="write", summary="totals"),
]

VOICES = [
    "We keep regenerating text artifacts by hand and I'd like a proper little build engine for it. The tool is called `{tool}` and the whole behaviour is written down in `README.md` in this repository. Please implement it in {Lang}; the program must be {run}. `{ex}` runs the visible examples; the real checks are far more thorough, so read the README closely, especially the part about {focus}.",
    "implement {tool} from README.md in {Lang}. examples: `{ex}`. there are many more checks than the examples, mostly about {focus}. keep everything in this repo and don't edit anything under tests/",
    "Ticket BLD-{num}: new tool `{tool}`.\n\nThe spec is README.md (please treat it as the contract, wording included: error messages are compared verbatim). Language: {Lang}. The program is {run}. Acceptance: all hidden check groups pass; the examples in tests/ are a smoke test only. Pay attention to {focus}.",
    "Could you build the `{tool}` program described in README.md? I'd like it in {Lang}, split into a few sensible modules rather than one giant file. Run the example checks with `{ex}` while you work. Nothing is left to guess in the README, but the details of {focus} are easy to get slightly wrong.",
    "Hi! Greenfield job: a deterministic build engine that reads a command script on stdin. Everything (grammar, output lines, error texts, tie-breaks) is in README.md. Use {Lang}; no third-party packages are available. Visible examples: `{ex}`. Hidden checks cover all the groups the README talks about, in particular {focus}.",
    "Spec is in README.md, tool name `{tool}`, language {Lang}; the program is {run}. I will run a much bigger check suite than the one in tests/, covering every command and every error message in the README. Don't forget {focus}. Thanks.",
    "The ops team needs `{tool}` yesterday. It is a tiny make-like engine over an in-memory file store, scripted through stdin; README.md has the full description. Please write it in {Lang} and make sure `{ex}` passes before you hand it back. The tricky bits are {focus}; everything else is bookkeeping.",
    "Task: write {tool} in {Lang} exactly as README.md describes. It is graded by a hidden suite grouped by feature (basics, failures, ordering, {focus_short} and so on); partial credit per group. Run `{ex}` for the visible examples. Take your time with the README: error texts and trace lines must match character for character.",
]


def fx_hash(s: str) -> str:
    h = 0x811C9DC5
    for b in s.encode():
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return "%08x" % h


# ---------------------------------------------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------------------------------------------

def readme(p: dict, tool: str, lang: str, by_name: dict) -> str:
    B, P = p["build"], p["put"]
    acts = p["actions"]
    mode = p["mode"]
    o: list[str] = []
    w = o.append
    w(f"# {tool}: an incremental build engine for text artifacts\n")
    w(f"`{tool}` keeps a small in-memory store of text files, a set of build rules that derive some files from others, and it rebuilds "
      f"only what is out of date. It is driven by a script on standard input and reports every step on standard output, so that its "
      f"behaviour can be checked exactly. Nothing is read from or written to the real file system.\n")
    w(f"Build and run it as {K.how_to_run(lang, tool)}. The program reads the whole of standard input, runs the script line by line and exits.\n")
    w("## 1. Script and output\n")
    w("* A script is a sequence of lines. Leading and trailing white space of a line is ignored; empty lines and lines starting with `#` do nothing.")
    w("* The first word of a line is the command; words are separated by single or multiple spaces. Command names are lower-case and case-sensitive.")
    w("* Every command prints zero or more lines to standard output (given below). A failing command prints one `error: ...` line and the script continues with the next line.")
    w("* Exit status: `1` if at least one line starting with `error:` or `fail ` was printed during the run, otherwise `0`. Nothing is ever printed to standard error that matters.")
    cmds = [P, "rule", B, "show", "digest", "ls", "stats"] + (["status"] if p["status"] else []) + (["clean"] if p["clean"] else []) + (["touch"] if p["touch"] else [])
    w("* The commands are: " + ", ".join(f"`{c}`" for c in cmds) + ". Any other first word prints `error: unknown command 'WORD'`.\n")
    w("## 2. Paths, files and text\n")
    w("A path is made of letters, digits and the characters `_ . / -`. It is split at `/` into segments and no segment may be empty, `.` or `..` "
      "(so a path does not start or end with `/` and has no `//`). " +
      ("In rule targets and rule dependencies a path may also contain one `%` (see section 4). " if p["patterns"] else "A `%` is not allowed in any path. ") +
      "Anything else is a bad path: `error: bad path 'PATH'`.\n")
    w("The store maps paths to *files*. A file is a text (a string of ASCII characters; it may contain newlines and tabs) plus bookkeeping described below. "
      "A file is either a **source** (created by `" + P + "`) or **derived** (produced by a rule). A path is *derived* if a rule matches it (section 4), "
      "whether or not the file exists yet; every other path is a source path.\n")
    w("The *digest* of a text is the 32-bit FNV-1a hash of its UTF-8 bytes, written as eight lower-case hex digits: start with `h = 0x811c9dc5`; for each byte `b`, "
      "`h = h XOR b`, then `h = (h * 0x01000193) mod 2^32`. The digest of the empty text is `811c9dc5`.\n")
    w(f"The store has a **logical clock**, an integer that starts at 0. It is advanced by one (a *tick*) every time a file is written by `{P}` or by an action, and by `touch`"
      + ("" if p["touch"] else " (there is no `touch` in this build)") + "; each file remembers the clock value of its last write as its *stamp*.\n")
    w("## 3. Commands that change or inspect files\n")
    w(f"* `{P} PATH [TEXT]` creates or replaces a source file. `TEXT` is everything after the single space that follows `PATH` (it may contain further spaces; "
      "white space at the end of the line is not part of it; it may be absent, giving an empty text). In `TEXT`, the escapes `\\n` (newline), `\\t` (tab) and `\\\\` "
      "(one backslash) are decoded; a backslash followed by any other character stays as it is. The file gets a new stamp (one tick). "
      f"Prints `wrote PATH (N bytes)` where `N` is the length of the decoded text in bytes. Errors: no path -> `error: usage: {P} PATH [TEXT]`; a bad path; "
      "a derived path -> `error: 'PATH' is derived, not a source file`.")
    w("* `show PATH` prints `PATH = \"TEXT\"` with the text encoded the opposite way (a backslash becomes `\\\\`, a newline `\\n`, a tab `\\t`). "
      "Unknown file: `error: no such file 'PATH'`. Wrong word count: `error: usage: show PATH`.")
    w("* `digest PATH` prints `PATH DIGEST`. Same errors as `show` (usage text `usage: digest PATH`).")
    w("* `ls` prints one line `PATH DIGEST KIND` for every file in the store, sorted by path (plain byte order), where `KIND` is `derived` if the path is derived, else `source`. "
      "Arguments are ignored.")
    w("* `stats` prints `files=F rules=R actions=A clock=C`: the number of files, the number of rules, the number of action executions so far "
      "(failed attempts included; skipped ones not) and the clock. Arguments are ignored.")
    if p["touch"]:
        w("* `touch PATH` gives an existing file a new stamp (one tick) without changing its text and prints `touched PATH`. Errors: `error: usage: touch PATH`, `error: no such file 'PATH'`.")
    if p["clean"]:
        w("* `clean [PATH...]` deletes derived files. Without arguments it deletes every existing derived file; with arguments it deletes exactly those files. "
          "If an argument is not the path of an existing derived file the command prints `error: 'PATH' is not a derived file` for the first such argument (in the order given) and deletes nothing. "
          "Prints `cleaned N files` (`N` counts distinct deleted files; also for `0` and `1`). Deleting a file also forgets how it was built.")
    w("")
    w("## 4. Rules\n")
    w("`rule TARGET <- DEP... : ACTION [ARG...]` declares how `TARGET` is made. `<-` and `:` are words of their own. There may be no dependencies. "
      + ("A rule written with `:!` instead of `:` is an **always-rule** (see section 6). " if p["always"] else "`:!` is not a separator in this build. ")
      + "Arguments are the words after the action name.\n")
    w("Checks, in this order, each with its error (`error: ` is implied):\n")
    w("1. `rule syntax: rule TARGET <- DEP... : ACTION [ARG...]` if the second word is not `<-`, there is no separator word, or no action name follows it.")
    w("2. `bad path 'P'` for the first of target, dependencies (left to right) that is not a valid path.")
    if p["patterns"]:
        w("3. `stem in dependency without stem in target` if a dependency contains `%` but the target does not.")
    w("4. `unknown action 'NAME'`, or `bad arguments for 'NAME'` (section 5).")
    w("5. `duplicate rule for 'TARGET'` if an earlier rule has exactly the same target text.")
    w("6. `'FILE' already exists as a source file` if a file already in the store would be made by the new rule (for a pattern rule: the first such file in byte order); "
      "rules never take over existing files.")
    w("\nOn success it prints `rule TARGET`.\n")
    if p["patterns"]:
        w("**Pattern rules.** A target with a `%` is a pattern. `%` stands for a non-empty *stem* (it may contain `/`): the pattern `out/%.up` matches `out/a/b.up` with stem `a/b`, but "
          "not `out/.up`. In the dependencies of a pattern rule every `%` is replaced by the stem. Several dependencies may each contain a `%`; dependencies without one are fixed.\n")
    w("**Which rule makes a path.** An exact rule (target without `%`) whose target equals the path wins. " +
      ("Otherwise, among the pattern rules that match the path, the one with the most literal characters (target length minus one) wins; on a tie the earlier declared rule wins. " if p["patterns"] else "") +
      "If no rule matches, the path is a source path.\n")
    w("## 5. Actions\n")
    w("Every action computes the text of the target from the texts of the dependencies, taken in the order written. Let `IN` be those texts joined with a single `\\n` between them "
      "(`IN` is empty when there are no dependencies); *lines of X* means X split at `\\n`, dropping one empty last piece (so the empty text has no lines and `a\\n` has one). "
      "Actions work on ASCII only.\n")
    desc = {
        "cat": ("`cat`", "`IN`."),
        "upper": ("`upper`", "`IN` with `a`-`z` turned into `A`-`Z`."),
        "lower": ("`lower`", "`IN` with `A`-`Z` turned into `a`-`z`."),
        "rev": ("`rev`", "`IN` with its characters in reverse order."),
        "count": ("`count`", "the length of `IN` in characters, in decimal."),
        "lines": ("`lines`", "the number of lines of `IN`, in decimal."),
        "head": ("`head N`", "the first `N` lines of `IN` joined with `\\n` (all of them if there are fewer). `N` is 1 to 9 decimal digits."),
        "sort": ("`sort`", "the lines of `IN` in byte order, joined with `\\n`."),
        "uniq": ("`uniq`", "the lines of `IN` with each run of identical consecutive lines reduced to one, joined with `\\n`."),
        "grep": ("`grep WORD`", "the lines of `IN` that contain `WORD` as a substring, joined with `\\n` (exactly one argument)."),
        "tag": ("`tag NAME`", "`<NAME>` followed by `IN` followed by `</NAME>`; `NAME` is one argument: a letter followed by letters and digits."),
        "sum": ("`sum`", "the sum of all white-space separated words of `IN` that look like an integer (an optional `-` and 1 to 9 digits), in decimal; other words are ignored."),
        "cap": ("`cap N`", "like `sum`, but at most `N` (1 to 9 decimal digits)."),
        "const": ("`const [TEXT...]`", "the arguments joined with single spaces (empty if none); the dependencies are not looked at."),
        "failif": ("`failif WORD`", "`IN`, unless `IN` contains `WORD` as a substring: then the action *fails* with the message `found WORD` (exactly one argument)."),
        "fail": ("`fail`", "nothing: the action always *fails* with the message `always fails`."),
    }
    w("| action | result |")
    w("|---|---|")
    for a in acts:
        d = desc[a]
        w(f"| {d[0]} | {d[1]} |")
    w("\nThese are the only actions of this build; any other name is an unknown action. An action with arguments of the wrong number or shape is `bad arguments`. "
      "Actions without arguments listed above take none.\n")
    w("## 6. Building\n")
    opts = []
    if p["keep"]:
        opts.append("`--keep-going` (or `-k`)")
    if p["budget"]:
        opts.append("`--max N`")
    w(f"`{B} [OPTION...] TARGET...` brings the targets up to date, in the order given. " +
      ("Options come first (words that start with `-` before the first target): " + " and ".join(opts) + ". " if opts else "There are no options: a first word that starts with `-` is `error: unknown option 'WORD'`. ") +
      "Every word after the first word that does not start with `-` is a target, whatever it looks like. Validation happens before any work and stops the command at the first problem, in this order: an unknown option (`error: unknown option 'WORD'`)"
      + ("; a `--max` without a decimal number after it (`error: bad --max value 'X'`, with `X` empty if the word is missing)" if p["budget"] else "")
      + f"; no targets (`error: {B} needs at least one target`); the first target that is not a valid path without `%` (`error: bad path 'P'`).\n")
    w("Bringing a path up to date (*visiting* it) works like this. Each path is visited at most once per command; a second request for it gets the same outcome and prints nothing. "
      "The outcome is one of *source*, *fresh*, *built*, *failed*, *blocked*.\n")
    steps = [
        "Find the rule for the path. If there is none: when the file exists the outcome is *source* (nothing is printed); otherwise print "
        "`error: no rule to make 'PATH'`, followed by ` (needed by 'REQUESTER')` when the path was visited as a dependency of another path, and the outcome is *failed*.",
        "If the path is already being visited further up (a cycle), print `error: cycle A -> B -> ... -> A` where the list starts at the first occurrence of the path on the "
        "chain of paths being visited and ends with the path again. The outcome is *failed*.",
        "Visit the dependencies (stems filled in) from left to right, so everything a path needs is reported before the path itself. "
        "If any dependency is *failed* or *blocked*, print `blocked PATH`; the outcome is *blocked*.",
    ]
    if mode == "digest":
        steps.append("Decide whether the path is **stale**. The *key* of a rule application is the digest of the text `ACTION` + `\\x1f` (the byte 0x1f) + the digests of the dependency texts "
                     "joined with `,`, where `ACTION` is the action name and its arguments joined with single spaces. Every derived file remembers the key of the application that made it. "
                     "The path is stale if its file does not exist, or its remembered key differs from the current key (because a dependency's text changed, so that its digest changed)"
                     + ("; an always-rule is always stale" if p["always"] else "") + ". This gives **early cutoff**: when a dependency is rebuilt to exactly the same text, nothing "
                     "that depends on it is rebuilt. Stamps play no role in this build.")
    else:
        steps.append("Decide whether the path is **stale**. It is stale if its file does not exist, or if any dependency has a stamp greater than the stamp of its file"
                     + ("; an always-rule is always stale" if p["always"] else "") + ". Texts and digests play no role: a dependency that was rebuilt (or touched) "
                     "makes everything above it stale even when its text came out identical, because every write ticks the clock. There is no early cutoff.")
    steps.append("If the path is not stale, print `skip PATH`; the outcome is *fresh*.")
    if p["budget"]:
        steps.append("Otherwise the action has to run. If the command has a budget (`--max N`) and `N` actions have already been executed by this command, print "
                     "`halt: budget of N actions reached` and *stop the whole command* (nothing else is visited). `--max 0` therefore halts at the first action that has to run.")
        steps.append("Run the action (this counts against the budget even if it fails; it also counts in `stats`). If it fails, print `fail PATH: MESSAGE`; the outcome is *failed*, "
                     "and the file (if any) is left as it was.")
    else:
        steps.append("Otherwise run the action (it counts in `stats` even if it fails). If it fails, print `fail PATH: MESSAGE`; the outcome is *failed*, and the file (if any) is left as it was.")
    steps.append("If it succeeds, the file gets the new text and a new stamp (one tick) " + ("and the new key " if mode == "digest" else "") +
                 "and the line is `same PATH` if the file already existed with exactly this text, else `run PATH`. The outcome is *built*.")
    for i, t in enumerate(steps, 1):
        w(f"{i}. {t}")
    w("")
    stopword = "the first failure (any line `fail ...`, `error: no rule ...` or `error: cycle ...` of this command)"
    if p["keep"]:
        w(f"Failure policy. Without `--keep-going` the command stops at {stopword}: after that line nothing more is visited or printed except the final summary line. "
          "With `--keep-going` the command carries on: the other dependencies and the other targets are still visited, and only the paths that depend on a failure are *blocked*.\n")
    else:
        w(f"Failure policy. The command stops at {stopword}: after that line nothing more is visited or printed except the final summary line.\n")
    w(f"At the end of every `{B}` command that got past validation (also when it stopped early) it prints `{p['summary']}: ran=R same=S skipped=K failed=F blocked=B`: the number of paths with the lines `run`, `same`, `skip`, "
      "`fail`/`error: no rule`/`error: cycle` (each such line counts one *failed*, also the one that stopped the command) and `blocked`. Sources and halting add nothing.\n")
    if p["status"]:
        w("## 7. Status\n")
        w("`status TARGET...` (validation as for building; no targets: `error: status needs at least one target`) reports what a build would find, without running anything and without changing any file. "
          "It visits paths like a build does (once each, dependencies first, left to right; sources print nothing; `error: no rule to make ...` and `error: cycle ...` are printed in the same way), "
          "and prints for every derived path one line, in visiting order:\n")
        w("* nothing at all if one of its dependencies had an error (the path itself then counts as erroneous too);")
        w("* otherwise `stale PATH (REASON)` with the first applicable reason: `missing` (no file), `dep D` (`D` is the first dependency, left to right, that was reported stale), "
          + ("`always` (always-rule), " if p["always"] else "") + "`changed` (" + ("the remembered key differs from the key computed from the current texts of the dependencies" if mode == "digest" else "some dependency has a greater stamp") + ");")
        w("* otherwise `fresh PATH`.\n")
        w("Note that `status` is conservative: a path below a stale path is reported stale even though a build might cut off at the stale path.\n" if mode == "digest" else
          "Note that a stale dependency makes every path above it stale in the report.\n")
    w("## Examples\n")
    ex = [(c, r) for (c, r) in by_name.values() if c.visible]
    for i, (c, r) in enumerate(ex[:3]):
        w(K.show_case(tool, c, r))
    w("The example checks in `tests/examples.json` are run with `python3 tests/run_examples.py`; more cases like these (every command, every error text, the orders and counts above) are checked when the work is judged.")
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# script builder and case generators
# ---------------------------------------------------------------------------------------------------------------

class S:
    """Builds a script for one instance."""

    def __init__(self, p, rng):
        self.p, self.rng, self.lines = p, rng, []

    def raw(self, line):
        self.lines.append(line)
        return self

    def put(self, path, text=""):
        return self.raw(f"{self.p['put']} {path}" + (f" {text}" if text != "" else ""))

    def rule(self, target, deps, action, sep=":"):
        return self.raw(f"rule {target} <- " + " ".join(deps + [sep] if deps else [sep]) + f" {action}")

    def build(self, *targets, opts=""):
        return self.raw(f"{self.p['build']} " + (opts + " " if opts else "") + " ".join(targets))

    def text(self):
        return "\n".join(self.lines) + "\n"


def arg_for(rng, a):
    if a in ("head", "cap"):
        return f"{a} {rng.choice([1, 2, 3, 5, 20, 50])}"
    if a == "grep":
        return f"grep {rng.choice(WORDS)}"
    if a == "tag":
        return f"tag {rng.choice(['b', 'item', 'x1', 'Note'])}"
    if a == "const":
        return "const " + rng.choice(["ok", "fixed value", "", "42"]).strip()
    if a == "failif":
        return f"failif {rng.choice(WORDS)}"
    return a


def rand_text(rng, numeric=False):
    n = rng.randint(1, 3)
    if numeric or rng.random() < 0.3:
        return "\\n".join(" ".join(rng.choice(NUMS) for _ in range(rng.randint(1, 3))) for _ in range(n))
    return "\\n".join(" ".join(rng.choice(WORDS) for _ in range(rng.randint(1, 3))) for _ in range(n))


def usable(p):
    """Actions that can appear in generated rules (the failing ones are used on purpose elsewhere)."""
    return [a for a in p["actions"] if a not in ("fail", "failif")]


def make_cases(p: dict, rng) -> list[K.Case]:
    cases: list[K.Case] = []
    cnt: dict[str, int] = {}

    def add(group, s: S, visible=False, name=None):
        cnt[group] = cnt.get(group, 0) + 1
        cases.append(K.Case(name=name or f"{group}-{cnt[group]:02d}", group=group, stdin=s.text(), visible=visible))

    A = usable(p)
    has = lambda a: a in p["actions"]  # noqa: E731
    B = p["build"]

    # --- basics -------------------------------------------------------------------------------------------------
    for k in range(3):
        s = S(p, rng)
        n = 3 + k
        srcs = [f"src/{w}.txt" for w in rng.sample(WORDS, 2)]
        for sp in srcs:
            s.put(sp, rand_text(rng))
        up = rng.choice([a for a in ("upper", "lower", "rev", "cat") if has(a)] or ["cat"])
        mid = "out/mid.txt"
        s.rule(mid, srcs, "cat")
        s.rule("out/final.txt", [mid], rng.choice([x for x in A if x not in ("const",)]) if k else up)
        s.build("out/final.txt")
        s.build("out/final.txt")
        s.put(srcs[0], rand_text(rng))
        s.build("out/final.txt")
        s.raw("show out/final.txt").raw("digest out/mid.txt").raw("ls").raw("stats")
        add("basics", s, visible=(k == 0))

    # --- the two stale rules: edits that leave an intermediate text unchanged ---------------------------------
    cut_table = {  # action -> (first text, edits that keep the action's output, edits that change it)
        "sum": ("sum", "4 5\\n6", ["5 4\\n6", "15", "4 5 6 x"], ["4 5\\n7", "-1"]),
        "count": ("count", "4 5\\n6", ["abcde", "a\\nb c"], ["4 5\\n66", ""]),
        "lines": ("lines", "4 5\\n6", ["x\\ny", "1 2 3\\nz"], ["x\\ny\\nz", "one"]),
        "cap": ("cap 10", "4 5\\n6", ["99", "10"], ["3", "4 5"]),
        "head": ("head 1", "4 5\\n6", ["4 5\\nzzz\\nyyy", "4 5"], ["4 6\\n6", ""]),
        "grep": ("grep 4", "4 5\\n6", ["4 5\\nq", "x\\n4 5"], ["14", ""]),
    }
    opts = [a for a in ("sum", "count", "lines", "cap", "head", "grep") if has(a)]
    for k in range(3):
        s = S(p, rng)
        act, first, same_edits, diff_edits = cut_table[opts[(k + rng.randrange(len(opts))) % len(opts)]][0:4]
        s.put("in/a.txt", first).put("in/b.txt", "7")
        s.rule("mid/a", ["in/a.txt"], act)
        s.rule("mid/b", ["in/b.txt"], "cat")
        s.rule("top/all", ["mid/a", "mid/b"], "cat")
        s.rule("top/tag", ["top/all"], "tag t" if has("tag") else "cat")
        s.build("top/tag")
        s.put("in/a.txt", rng.choice(same_edits))
        s.build("top/tag")
        s.put("in/a.txt", rng.choice(diff_edits))
        s.build("top/tag")
        s.put("in/b.txt", "7")
        s.build("top/tag")
        if p["touch"]:
            s.raw("touch in/b.txt")
            s.build("top/tag")
        s.raw("ls")
        add("cutoff", s, visible=(k == 0))

    # --- shared dependencies, ordering, repeated targets ------------------------------------------------------------
    for k in range(3):
        s = S(p, rng)
        for i in range(3):
            s.put(f"s/{i}.txt", rand_text(rng))
        s.rule("lib/x", ["s/0.txt", "s/1.txt"], "cat")
        s.rule("lib/y", ["s/1.txt", "s/2.txt", "lib/x"], "cat")
        s.rule("app/one", ["lib/y", "lib/x"], rng.choice(A))
        s.rule("app/two", ["lib/x", "s/2.txt"], rng.choice(A))
        order = rng.sample(["app/one", "app/two", "lib/y"], 3) + ["app/one"]
        s.build(*order)
        s.put("s/1.txt", rand_text(rng))
        s.build(*reversed(order))
        s.raw("ls")
        add("order", s)

    # --- failures ------------------------------------------------------------------------------------------------
    if has("failif") or has("fail"):
        for k in range(3):
            s = S(p, rng)
            bad = rng.choice(WORDS)
            s.put("a.txt", f"{bad} one").put("b.txt", "fine two").put("c.txt", "three")
            fa = f"failif {bad}" if has("failif") else "fail"
            s.rule("o/a", ["a.txt"], fa)
            s.rule("o/b", ["b.txt"], "cat")
            s.rule("o/c", ["c.txt"], "cat")
            s.rule("o/ab", ["o/a", "o/b"], "cat")
            s.rule("o/all", ["o/ab", "o/c"], "cat")
            s.build("o/all")
            if p["keep"]:
                s.build("-k" if k % 2 else "--keep-going", "o/all", "o/c")
            s.build("o/b", "o/all")
            s.put("a.txt", "repaired")
            s.build("o/all")
            s.raw("stats")
            add("failures", s, visible=(k == 0))

    # --- keep going ----------------------------------------------------------------------------------------------
    if p["keep"] and (has("failif") or has("fail")):
        for k in range(2):
            s = S(p, rng)
            s.put("p.txt", "x1").put("q.txt", "y2")
            s.rule("a", ["p.txt"], "fail" if has("fail") else "failif x")
            s.rule("b", ["q.txt"], "cat")
            s.rule("c", ["a", "b"], "cat")
            s.rule("d", ["c"], "cat")
            s.rule("e", ["b"], "cat")
            opt = ["--keep-going", "-k"][k]
            s.build(opt, "d", "e")
            s.build("d", "e")
            s.build(opt, "missing.txt", "e")
            s.build(opt, "e", "d")
            add("keepgoing", s)

    # --- budget ---------------------------------------------------------------------------------------------------
    if p["budget"]:
        for k in range(3):
            s = S(p, rng)
            s.put("w/a", rand_text(rng)).put("w/b", rand_text(rng))
            s.rule("m/1", ["w/a"], rng.choice(A)).rule("m/2", ["w/b"], rng.choice(A)).rule("m/3", ["m/1", "m/2"], "cat").rule("m/4", ["m/3"], rng.choice(A))
            n = [1, 2, 0][k]
            s.build("--max", str(n), "m/4")
            s.build("--max", "2", "m/4")
            s.build("m/4")
            s.build("--max", str(n), "m/4")
            s.raw("stats")
            if k == 2:
                s.build("--max", "x", "m/4").build("--max").build("--max", "-1", "m/4")
            add("budget", s, visible=(k == 0 and False))

    # --- patterns -------------------------------------------------------------------------------------------------
    if p["patterns"]:
        for k in range(3):
            s = S(p, rng)
            s.put("src/a.txt", rand_text(rng)).put("src/b.txt", rand_text(rng)).put("src/deep/c.txt", rand_text(rng))
            u = "upper" if has("upper") else "cat"
            s.rule("out/%.up", ["src/%.txt"], u)
            s.rule("out/deep/%.up", ["src/deep/%.txt"], "tag deep" if has("tag") else "cat")
            s.rule("out/%.dup", ["out/%.up", "out/%.up"], "cat")
            s.rule("out/b.up", ["src/a.txt"], "cat")
            s.rule("out/%", ["src/%.txt"], "rev" if has("rev") else "cat")
            s.rule("all", ["out/a.up", "out/b.up", "out/deep/c.up", "out/a.dup"], "cat")
            if k == 0:
                s.build("all")
                s.put("src/a.txt", rand_text(rng))
                s.build("all", "out/c")
            elif k == 1:
                s.build("out/deep/c.up", "out/b.dup", "out/x")
                s.raw("ls")
            else:
                s.build("out/a")
                s.build("out/deep/c")
                s.raw("rule out/%.up <- : cat")
                s.raw("rule src/%.txt <- : cat")
                s.raw("rule a%b%c <- : cat")
                s.raw("rule %.zz <- %.yy : cat")
                s.raw("rule fixed <- other/%.txt : cat")
                s.raw("rule % <- : cat")
                s.raw("rule o/% <- : cat")
                s.raw("rule o/%x <- : cat")
                s.build("o/", "o/zx")
                s.build("o/zx")
            add("patterns", s, visible=(k == 0 and False))
    else:
        s = S(p, rng)
        s.raw("rule out/%.up <- src/%.txt : cat").raw("rule a <- b/%.txt : cat").raw("rule 100% <- : cat").raw(f"{B} out/%.up")
        add("patterns-off", s)

    # --- always-rules ---------------------------------------------------------------------------------------------
    if p["always"]:
        for k in range(2):
            s = S(p, rng)
            s.put("cfg.txt", "mode a")
            s.rule("stamp.txt", ["cfg.txt"], "cat", sep=":!")
            s.rule("const.txt", [], "const fixed" if has("const") else "cat", sep=":!")
            s.rule("report", ["stamp.txt", "const.txt"], "cat")
            s.rule("final", ["report"], "tag r" if has("tag") else "cat")
            s.build("final")
            s.build("final")
            s.put("cfg.txt", "mode b")
            s.build("final")
            if p["status"]:
                s.raw("status final")
            if p["touch"]:
                s.raw("touch const.txt")
                s.build("final")
            s.raw("stats")
            add("always", s)
    else:
        s = S(p, rng)
        s.raw("rule x <- a.txt :! cat").raw("rule y <- : cat").raw("rule y <- :! const z")
        add("always-off", s)

    # --- cycles and missing inputs -------------------------------------------------------------------------------
    for k in range(3):
        s = S(p, rng)
        s.put("real.txt", "r")
        if k == 0:
            s.rule("a", ["b"], "cat").rule("b", ["c"], "cat").rule("c", ["a", "real.txt"], "cat")
            s.build("a")
            s.build("c")
            s.build("real.txt")
        elif k == 1:
            s.rule("self", ["self"], "cat").rule("m", ["nothing.txt", "real.txt"], "cat").rule("n", ["m"], "cat")
            s.build("self")
            s.build("n")
            s.build("real.txt", "n")
            if p["keep"]:
                s.build("--keep-going", "self", "n", "a2")
        else:
            s.rule("x", ["y", "real.txt"], "cat").rule("y", ["x"], "cat")
            if p["keep"]:
                s.build("-k", "x", "y")
            s.build("y", "x")
            if p["status"]:
                s.raw("status x").raw("status nowhere")
        add("cycles", s)

    # --- status ---------------------------------------------------------------------------------------------------
    if p["status"]:
        for k in range(3):
            s = S(p, rng)
            sc = [a for a in ("sum", "count", "lines", "cap") if has(a)]
            s.put("g/a", "1 2").put("g/b", "3")
            s.rule("h/a", ["g/a"], arg_for(rng, sc[0]) if sc else "cat").rule("h/b", ["g/b"], "cat").rule("h/c", ["h/a", "h/b"], "cat").rule("h/d", ["h/c", "g/a"], "cat")
            s.raw("status h/d")
            s.build("h/c")
            s.raw("status h/d h/c")
            s.put("g/a", rng.choice(["2 1", "9 9", "1  2"]))
            s.raw("status h/d")
            s.build("h/d")
            s.raw("status h/d g/a ghost")
            s.raw("status")
            s.raw("status ../x")
            add("status", s, visible=(k == 0 and False))
    else:
        s = S(p, rng)
        s.put("a", "1").rule("b", ["a"], "cat").raw("status b")
        add("status-off", s)

    # --- clean / touch ----------------------------------------------------------------------------------------------
    if p["clean"] or p["touch"]:
        for k in range(2):
            s = S(p, rng)
            s.put("a", "alpha").put("b", "beta")
            s.rule("c", ["a", "b"], "cat").rule("d", ["c"], "upper" if has("upper") else "cat").rule("e", ["b"], "cat")
            s.build("d", "e")
            if p["clean"]:
                s.raw("clean c").build("d")
                s.raw("clean a").raw("clean zzz").raw("clean d e e").build("d", "e")
                s.raw("clean").raw("ls").build("d")
                s.raw("clean").raw("clean")
            if p["touch"]:
                s.raw("touch a").build("d", "e").raw("touch d").build("d", "e").raw("touch nope").raw("touch")
            s.raw("stats")
            add("clean-touch", s)
    for cmd in [x for x in ("clean", "touch", "status") if not p[x if x != "status" else "status"]]:
        s = S(p, rng)
        s.put("a", "1").raw(f"{cmd} a")
        add("disabled", s)

    # --- errors ---------------------------------------------------------------------------------------------------------
    for k in range(3):
        s = S(p, rng)
        P = p["put"]
        s.raw("# comments and blank lines are fine").raw("").raw("   ").raw("  show   ")
        s.raw("frobnicate a b").raw(f"{P}").raw(f"{P} bad//path x").raw(f"{P} ../up x").raw(f"{P} a/./b x").raw(f"{P} trailing/ x").raw(f"{P} UP.txt  two  spaces here  ")
        s.raw("show UP.txt").raw("show").raw("show a b").raw("digest").raw("digest nope").raw("ls extra")
        s.raw("rule").raw("rule a").raw("rule a <-").raw("rule a <- b").raw("rule a <- b :").raw("rule a b : cat").raw("rule a -> b : cat")
        s.raw("rule a <- b : nothing").raw("rule a <- b : head").raw("rule a <- b : head x").raw("rule a <- b : head 1234567890")
        s.raw("rule a <- b : cat extra").raw("rule a <- b : tag 9x").raw("rule 'q' <- : cat")
        s.raw("rule a <- : cat").raw("rule a <- : upper").raw("rule UP.txt <- : cat").raw(f"{P} a x")
        s.raw("rule dup <- a : cat").raw("rule dup <- : const")
        s.raw(f"{B}").raw(f"{B} -x a").raw(f"{B} a ../b").raw(f"{B} --").raw(f"{B} ghost")
        s.raw("stats")
        if k == 1:
            s.lines = [ln for ln in s.lines if not ln.startswith("rule 'q'")]
            s.raw("rule 'q'<- : cat")
        if k == 2:
            s.lines = [ln.replace("a ", "z ", 1) if ln.startswith("rule a <- : sum") else ln for ln in s.lines]
        add("errors", s, visible=(k == 0 and False))

    # --- text escapes -----------------------------------------------------------------------------------------------------
    s = S(p, rng)
    P = p["put"]
    s.raw(f"{P} t/1 line one\\nline\\ttwo\\\\n").raw(f"{P} t/2 a\\qb\\\\\\n").raw(f"{P} t/3").raw(f"{P} t/4    leading spaces\\n\\n")
    s.raw("show t/1").raw("show t/2").raw("show t/3").raw("show t/4").raw("digest t/3").raw("digest t/1")
    s.rule("t/out", ["t/1", "t/2", "t/3", "t/4"], "cat").build("t/out").raw("show t/out").raw("ls")
    add("text", s)

    # --- fuzz: random graphs and random operation sequences -------------------------------------------------------
    for k in range(10):
        s = S(p, rng)
        ns, nd = rng.randint(2, 4), rng.randint(3, 7)
        srcs = [f"s{i}" for i in range(ns)]
        for sp in srcs:
            s.put(sp, rand_text(rng, numeric=rng.random() < 0.5))
        nodes = list(srcs)
        derived = []
        for i in range(nd):
            deps = rng.sample(nodes, min(len(nodes), rng.randint(0, 3)))
            act = rng.choice(A)
            if has("failif") and rng.random() < 0.12:
                act = f"failif {rng.choice(WORDS)}"
            else:
                act = arg_for(rng, act)
            sep = ":!" if (p["always"] and rng.random() < 0.15) else ":"
            s.rule(f"d{i}", deps, act, sep=sep)
            nodes.append(f"d{i}")
            derived.append(f"d{i}")
        for _ in range(rng.randint(8, 16)):
            r = rng.random()
            if r < 0.45:
                tg = rng.sample(derived, rng.randint(1, 2))
                opts = ""
                if p["keep"] and rng.random() < 0.3:
                    opts = "--keep-going"
                if p["budget"] and rng.random() < 0.3:
                    opts = (opts + " " if opts else "") + f"--max {rng.randint(0, 4)}"
                s.build(*tg, opts=opts)
            elif r < 0.65:
                s.put(rng.choice(srcs), rand_text(rng, numeric=rng.random() < 0.5))
            elif r < 0.72 and p["touch"]:
                s.raw("touch " + rng.choice(nodes[:ns] + [d for d in derived if rng.random() < 0.3] or srcs))
            elif r < 0.78 and p["clean"]:
                s.raw("clean " + rng.choice(["", rng.choice(derived)]))
            elif r < 0.86 and p["status"]:
                s.raw("status " + rng.choice(derived))
            elif r < 0.92:
                s.raw("show " + rng.choice(nodes))
            else:
                s.raw(rng.choice(["stats", "ls"]))
        add("fuzz", s)
    return cases


# ---------------------------------------------------------------------------------------------------------------
# the family
# ---------------------------------------------------------------------------------------------------------------

@family("project-cutoff", category="project", lang="go", kind="greenfield", n=8,
        summary="a make-like build engine over an in-memory store: digests or logical clocks, early cutoff, pattern rules, always-rules, budgets, failure policies")
def gen(rng, n):
    for i in range(n):
        plan = dict(PLAN[i])
        tool = TOOLS[i]
        lang = plan.pop("lang")
        acts = sorted(rng.sample([a for a in ALL_ACTIONS if a not in ("cat", "fail", "failif", "sum", "count", "const")], 6), key=ALL_ACTIONS.index)
        acts = [a for a in ALL_ACTIONS if a in acts or a in ("cat", "fail", "failif", "sum", "count", "const")]
        if i % 3 == 2:
            acts = [a for a in acts if a not in ("failif",)] or acts
        p = dict(plan, actions=acts)
        p["keep"] = plan["keep"]
        cfg = dict(MODE=p["mode"], CMD_BUILD=p["build"], CMD_PUT=p["put"], ACTIONS=acts, PATTERNS=p["patterns"], ALWAYS_RULES=p["always"],
                   BUDGET=p["budget"], KEEP_GOING=p["keep"], HAS_STATUS=p["status"], HAS_CLEAN=p["clean"], HAS_TOUCH=p["touch"], SUMMARY=p["summary"])
        cases = make_cases(p, rng)
        nfeat = sum([p["patterns"], p["always"], p["budget"], p["keep"], p["mode"] == "clock", p["status"]])
        focus_pool = [
            "how staleness is decided (" + ("content digests and early cutoff" if p["mode"] == "digest" else "stamps and the logical clock") + ")",
            "the order of the trace lines",
            "failures and what gets blocked",
        ]
        focus_short = "staleness"
        focus = ", ".join(focus_pool[:2]) + " and " + focus_pool[2]
        voice = VOICES[i % len(VOICES)]
        py_sol = K.merged(K.load_src(THEME, "python", tool), K.render_config("python", cfg))
        sol = py_sol if lang == "python" else K.merged(K.load_src(THEME, lang, tool), K.render_config(lang, cfg))
        prompt = voice.format(tool=tool, Lang=K.LANG_NAME[lang], run=K.how_to_run(lang, tool), ex="python3 tests/run_examples.py",
                              focus=focus, focus_short=focus_short, num=4100 + i * 37)
        yield K.project_task(
            theme=THEME, tool=tool, lang=lang, cases=cases, solution=sol, py_solution=py_sol,
            readme=lambda by_name, p=p, tool=tool, lang=lang: readme(p, tool, lang, by_name),
            prompt=prompt, difficulty=4 if nfeat <= 4 else 5, slug=f"{i + 1:02d}-{tool}-{p['mode']}-{lang}",
            notes={"mode": p["mode"], "features": {k: p[k] for k in ("patterns", "always", "budget", "keep", "status", "clean", "touch")}, "actions": acts},
            tags=["build-system", p["mode"]],
        )
