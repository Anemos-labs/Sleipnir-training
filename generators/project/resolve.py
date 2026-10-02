"""project-resolve: a dependency resolver for an invented package ecosystem (versions with tags, constraint clauses, features,
yanked releases, breaks, sticky locks, lock validation, tree view).  Reference: Python (oracle) and Rust."""
from __future__ import annotations

from fx import family

from generators.project import _kit as K

THEME = "resolve"
TOOLS = ["keel", "moor", "davit", "jetty", "cleat", "ballast", "hawser", "fathom"]
POOL = ["anchor", "buoy", "cable", "davit", "eddy", "fender", "gaff", "halyard", "jib", "keel", "lanyard", "mast", "net", "oar", "pulley",
        "quay", "rudder", "shackle", "tiller", "upright"]
FEATS = ["tls", "zip", "log", "net", "fast"]
ALL_OPS = [">=", ">", "<=", "<", "=", "!=", "^", "~", "*"]

PLAN = [
    dict(lang="rust", features=True, breaks=True, tags=True, ops=ALL_OPS, caret_zero=True, oldest=True, sticky=True, unused=True, limit=3000),
    dict(lang="python", features=False, breaks=True, tags=False, ops=[">=", "<", "=", "^", "~", "*"], caret_zero=False, oldest=False, sticky=True, unused=False, limit=2000),
    dict(lang="rust", features=True, breaks=False, tags=True, ops=[">=", ">", "<=", "<", "=", "^", "~"], caret_zero=True, oldest=True, sticky=False, unused=True, limit=1500),
    dict(lang="python", features=True, breaks=True, tags=False, ops=[">=", "<=", "<", "!=", "^", "*"], caret_zero=True, oldest=True, sticky=True, unused=True, limit=4000),
    dict(lang="rust", features=False, breaks=False, tags=True, ops=ALL_OPS, caret_zero=False, oldest=False, sticky=True, unused=True, limit=2500),
    dict(lang="python", features=True, breaks=False, tags=True, ops=[">=", ">", "<", "=", "!=", "^", "~", "*"], caret_zero=True, oldest=False, sticky=False, unused=False, limit=3500),
    dict(lang="rust", features=True, breaks=True, tags=False, ops=[">=", "<", "=", "!=", "^", "~", "*"], caret_zero=False, oldest=True, sticky=True, unused=True, limit=1200),
    dict(lang="python", features=False, breaks=True, tags=True, ops=ALL_OPS, caret_zero=True, oldest=True, sticky=False, unused=True, limit=5000),
]

VOICES = [
    "Our little package ecosystem needs its own resolver, and the rules (invented, so please don't assume semver or cargo behaviour) are written up in `README.md`. The tool is `{tool}`; build it in {Lang} as {run}. Examples can be run with `python3 tests/run_examples.py`. The hidden checks cover all four commands, every error text and a lot of resolution scenarios where the order of attempts decides the answer.",
    "build `{tool}` from README.md in {Lang}. it's a dependency resolver; the search order described there is part of the contract (we compare whole lock files), so follow it literally. visible examples: `python3 tests/run_examples.py`. {run}.",
    "Ticket PKG-{num}: implement the `{tool}` resolver as specified in README.md.\n\n* Language: {Lang}; the program is {run}\n* Output is compared byte for byte, including `error:` and `problem:` lines\n* The index, project and lock formats and the backtracking order are all defined in the README\n\nPlease run the examples under tests/ before you finish.",
    "I need a resolver for our own manifest format. `README.md` has the grammar of the index, the constraint syntax and the exact backtracking procedure, plus the output of the four commands (lock, tree, check{upg}). Please write it in {Lang} and structure it sensibly (parsing, versions, search, reporting in separate modules). The program is {run}. Check yourself with `python3 tests/run_examples.py`.",
    "Greenfield: `{tool}`, a version resolver and lock validator, written in {Lang}. Everything is specified in README.md: the file formats, the candidate order, what counts as a dead end and how it is reported. Hidden tests are grouped (parsing, constraints, search, check, tree...) and each group is scored separately. Run {run} the way the README says.",
    "Can you implement `{tool}`? README.md is the spec. The part that people get wrong is the search: first-in-first-out queue of package names, candidates tried in a fixed order, chronological backtracking, and the *first* dead end is the one reported. {Lang} please; program: {run}. `python3 tests/run_examples.py` runs the visible examples.",
    "quick one: write the `{tool}` dependency resolver (see README.md) in {Lang}. no dependencies besides the standard library. the program is {run}. there are many more hidden cases than visible examples, so read the constraint and feature rules carefully.",
    "Please take README.md and turn it into a working `{tool}` in {Lang}. It has four commands, strict file formats with line-numbered errors, and a deterministic resolution procedure. {run} is how it will be run. Look at the examples in the README and under tests/ first; the hidden suite is much larger and checks the odd corners (yanked releases, tags, ordering of requirement lists).",
]


# ---------------------------------------------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------------------------------------------

def readme(p: dict, tool: str, lang: str, by_name: dict) -> str:
    o: list[str] = []
    w = o.append
    F = p["features"]
    ops = p["ops"]
    w(f"# {tool}: a dependency resolver and lock validator\n")
    w(f"`{tool}` reads a package index, a project file and (optionally) a lock file from the **current directory**, decides which version of which package to use, "
      "and writes or checks a lock file. The version scheme, the constraint syntax and the way conflicts are searched are specific to this ecosystem; "
      "follow the rules below, not the conventions of any real package manager.\n")
    w(f"Build and run it as {K.how_to_run(lang, tool)}. Usage: `{tool} COMMAND [ARGS]`. Everything is printed to standard output (nothing on standard error matters). "
      "The exit status is `1` if any printed line starts with `error:` or `FAILED`, otherwise `0`.\n")
    w("## 1. Words, names, versions\n")
    w("Files are read as lines of text. In every file `#` starts a comment that runs to the end of the line; the rest of a line is split into *words* at white space; "
      "lines without words are skipped. Line numbers start at 1 and count every line, comments and empty lines included.\n")
    w("A **name** is a lower-case letter followed by lower-case letters, digits and `-` (package names, " + ("feature names, " if F else "") + "nothing else).\n")
    w("A **version** is `MAJOR.MINOR.PATCH` where each number is `0` or has no leading zero and at most six digits" +
      (", optionally followed by `-TAG`, a **tag** being one or more lower-case letters followed by digits (for example `rc1`, `beta12`). " if p["tags"] else ". Tags are not part of this ecosystem: `1.2.3-rc1` is a bad version. ") +
      "Versions are ordered by the three numbers" +
      ("; for equal numbers a version *with* a tag is lower than the one without, and two tags are compared as plain byte strings (`rc10` < `rc2`). " if p["tags"] else ". ") +
      "Two versions are equal when they are equal in that order.\n")
    w("## 2. Constraints\n")
    w("A **constraint** is one word (no spaces): clauses separated by `,`, and a version must satisfy every clause. A clause is an operator and a *partial version* "
      "(`1`, `1.2` or `1.2.3" + ("`, or `1.2.3-rc1`" if p["tags"] else "`") + "; missing numbers count as 0" + ("; a tag requires all three numbers" if p["tags"] else "") + "), or `*`, or a bare partial version, which means `=` (always allowed). "
      "Clause meanings (`V` is the partial version completed with zeros):\n")
    table = {
        ">=": "`>=V`: at least `V`", ">": "`>V`: greater than `V`", "<=": "`<=V`: at most `V`", "<": "`<V`: less than `V`", "=": "`=V`: equal to `V`",
        "!=": "`!=V`: not equal to `V`",
        "^": "`^V`: at least `V` and below the *next breaking number*: `(MAJOR+1).0.0`" + (" if MAJOR is not 0; `0.(MINOR+1).0` if MAJOR is 0 and MINOR is not 0; `0.0.(PATCH+1)` if both are 0" if p["caret_zero"] else " (the major number is always the breaking one, also when it is 0)"),
        "~": "`~V`: at least `V` and below `MAJOR.(MINOR+1).0`",
        "*": "`*`: every version",
    }
    for op in ALL_OPS:
        if op in ops:
            w(f"* {table[op]}")
    off = [op for op in ALL_OPS if op not in ops]
    if off:
        w("\nThe operators " + ", ".join(f"`{o}`" for o in off) + " do not exist in this ecosystem; a clause using one is a bad constraint.")
    w("\nThe upper bound of `^` and `~` is compared on the three numbers only, whatever the tag: a version is below the bound when its triple is (so `^1.2` allows `1.9.9-rc1` but not `2.0.0-rc1`). "
      "All other clause comparisons (`>=`, `<`, `=` and so on) use the full version order of section 1, so `<2.0.0` *does* allow `2.0.0-rc1` and `>=1.0.0` does not allow `1.0.0-rc1`. "
      "A constraint that is empty, has an empty clause, an unknown operator or a bad partial version is a **bad constraint**.\n")
    w("## 3. The files\n")
    w("**`index.txt`** lists the available packages as blocks. A block starts with `pkg NAME VERSION` and continues with directive lines until the next `pkg` line:\n")
    w("* `needs NAME CONSTRAINT" + (" [+FEATURE...] [if FEATURE]" if F else "") + "`: this package version needs the package `NAME` in a version satisfying `CONSTRAINT`." +
      (" `+FEATURE` words ask for features of `NAME` to be enabled. `if FEATURE` makes the need *conditional*: it is only active when `FEATURE` of this package is enabled (the feature must have been declared earlier in the same block)." if F else ""))
    if F:
        w("* `feature NAME`: this version offers the feature `NAME` (declaring a feature twice in a block is an error).")
    if p["breaks"]:
        w("* `breaks NAME CONSTRAINT`: this version cannot be used together with any version of `NAME` that satisfies `CONSTRAINT`.")
    w("* `yanked`: this version is withdrawn: it is never chosen, unless the lock file already holds exactly this version (see `lock`).")
    w("\nThe same package may appear in several blocks with different versions; the same name and version twice is an error.\n")
    w("**`project.txt`** has one directive per line: `want NAME CONSTRAINT" + (" [+FEATURE...]" if F else "") + "`: the project needs `NAME` in a version satisfying `CONSTRAINT`" + (" with the given features enabled" if F else "") + ". Several lines may mention the same name.\n")
    w("**`lock.txt`** has one line per locked package, sorted by name: `NAME VERSION" + (" [FEATURES]" if F else "") + "`" +
      (", where `FEATURES` is one word: the enabled features sorted by name and joined with `,` (omitted when none is enabled)." if F else ".") + "\n")
    w("**File errors.** A file that cannot be read gives `error: cannot read FILE`. A malformed line gives `error: FILE:LINE: MESSAGE` and nothing else is done; "
      "the first problem in file order wins. `MESSAGE` is one of:\n")
    w("* `unknown directive 'WORD'` (first word not allowed in that file; the allowed ones are `pkg`, `needs`, `yanked`" + (", `breaks`" if p["breaks"] else "") + (", `feature`" if F else "") + " in the index and `want` in the project);")
    w("* `'WORD' outside a package block` (an index directive before the first `pkg` line);")
    w("* `bad line` (wrong number of words for the directive" + ("; in `needs` and `want` the `+FEATURE` words come after the constraint" if F else "") + ");")
    w("* `bad name 'X'` (checked after the shape: the package name of `pkg`/`needs`/`breaks`/`want`" + (", the gate of `if`, each feature of `feature` and `+FEATURE`, `X` printed without the `+`" if F else "") + ");")
    w("* `bad version 'V'`, `bad constraint 'C'` (checked after the names of the same line);")
    w("* `duplicate package NAME VERSION`" + (", `duplicate feature 'F'`, `undeclared feature 'F'` (a gate that is not declared above in the block)" if F else "") + ";")
    w("* in `lock.txt`: `bad line`, `bad name 'X'`, `bad version 'V'`, `duplicate package 'NAME'`" + (" (a features word is checked like `+FEATURE` words)" if F else "") + ".\n")
    w("Files are read and checked in this order: `index.txt`, `project.txt`, then `lock.txt` when the command needs it.\n")
    w("## 4. Commands\n")
    lock_opts = []
    if p["oldest"]:
        lock_opts.append("`--oldest`: try the oldest candidates first instead of the newest")
    if p["sticky"]:
        lock_opts.append("`--fresh`: ignore `lock.txt`")
    w(f"### `{tool} lock" + (" [--oldest]" if p["oldest"] else "") + (" [--fresh]" if p["sticky"] else "") + "`\n")
    w("Resolves the project (section 5). On success it prints one line per chosen package, sorted by name, in the format of `lock.txt`, then `locked N packages`, and writes the same lines to `lock.txt` "
      "(replacing it). On failure it prints one `error:` line (section 5) and leaves `lock.txt` alone." +
      (" Options: " + "; ".join(lock_opts) + ". " if lock_opts else " There are no options. ") +
      "An argument starting with `-` that is not an option gives `error: unknown option 'ARG'`; any other argument gives `error: usage: " + tool + " lock [OPTION...]`.")
    if p["sticky"]:
        w("\nUnless `--fresh` is given, an existing `lock.txt` is read (and must be well formed) and its versions are **preferred**: see the candidate order in section 5. A missing `lock.txt` is fine here.\n")
        w(f"### `{tool} upgrade NAME...`\n")
        w("Like `lock`, but `lock.txt` must exist (`error: cannot read lock.txt`) and every `NAME` must be locked there (`error: NAME is not locked`, for the first one that is not); "
          "the preference is taken from the lock *without* the named packages, so they are free to move to other versions while everything else stays put when possible. "
          f"No arguments: `error: usage: {tool} upgrade NAME...`. Output as for `lock`.\n")
    w(f"### `{tool} tree`\n")
    w("Needs `lock.txt`. Prints the dependency tree of the locked packages. The first line is `root`. Below it, indented by two spaces per level, come the names wanted in `project.txt` (each once, sorted by name), "
      "and below each package the packages it needs, again each once and sorted by name. The *needs* of a locked package are those of its locked version in the index" +
      (" that are active given the features recorded for it in the lock" if F else "") + " (a package locked at a version missing from the index has none). "
      "A package line is `NAME VERSION`" + (" followed by ` [FEATURES]` (features joined with `,`) when features are enabled" if F else "") + "; a name that is not in the lock is printed as `NAME (not locked)` and has no children. "
      "The tree is printed depth first; a locked package that was already printed earlier in the output (anywhere above or before it) gets ` (*)` appended and is not expanded again.\n")
    w(f"### `{tool} check`\n")
    w("Needs `lock.txt`. Validates it without searching and prints one `problem:` line per violation, in this order: first for each `want` line of the project in file order, then for each locked package in name order, " +
      ("then (last) the packages nothing needs. " if p["unused"] else "") + "The messages (`V` is a locked version, `C` a constraint as written, `NAME`/`DEP` package names):\n")
    w("* `problem: root wants NAME C but NAME is not locked` (and nothing more for that line); `problem: root wants NAME C but locked NAME is V` if the locked version does not satisfy `C`" +
      ("; then for each requested feature `F` (sorted) that is not enabled in the lock: `problem: root wants NAME +F but the lock does not enable it`" if F else "") + ".")
    w("* For a locked `NAME V`: if the index has no such version: `problem: NAME V is not in the index` (and no further check for it)." +
      (" For each enabled feature `F` (sorted) that the version does not declare: `problem: NAME V has no feature F`." if F else ""))
    w("* For each active need of `NAME V` in file order (`needs DEP C" + (" +F..." if F else "") + "`)" + (" (a gated need is active when its gate is enabled for `NAME` in the lock)" if F else "") +
      ": `problem: NAME V needs DEP C but DEP is not locked` (and nothing more for the need); `problem: NAME V needs DEP C but locked DEP is W` if `W` does not satisfy `C`" +
      ("; then for each requested feature `F` (sorted) not enabled for `DEP` in the lock: `problem: NAME V needs DEP +F but the lock does not enable it`" if F else "") + ".")
    if p["breaks"]:
        w("* For each `breaks X C` of `NAME V` in file order: `problem: NAME V breaks X C but locked X is W` if `X` is locked at a version `W` satisfying `C`.")
    if p["unused"]:
        w("* A package is *used* if it is wanted by the project or needed (actively, as above) by a used locked package. `problem: NAME is locked but nothing needs it` for every locked package that is not used, in name order.")
    w("\nAt the end: `ok: N packages` (exit status 0) when there was no problem, otherwise `FAILED: P problems` (exit status 1). Extra arguments give `error: usage: " + tool + " check`; for `tree`: `error: usage: " + tool + " tree`.\n")
    w("Any other command gives `error: unknown command 'WORD'`; no command gives `error: usage: " + tool + " COMMAND [ARGS]`.\n")
    w("## 5. Resolution\n")
    w("The search works on a **state**: the packages chosen so far (name -> version), for every name the list of **requirements** received in order (constraint text and who required it: `root`, or `NAME VERSION` of the package that needs it), "
      + ("the set of features requested for every name, " if F else "") + ("the list of `breaks` recorded by chosen packages, " if p["breaks"] else "") + "and a **queue** of names that still need a decision, in the order they were first required.\n")
    w("**Start.** The state is empty. For each `want` line in file order: add the requirement `(constraint, root)` for its name" + (", add its features to the requested ones" if F else "") + "; append the name to the queue unless it was queued before (a name is queued at most once, ever).\n")
    w("**Step.** Take the first name `N` of the queue (the one that has waited longest).")
    w("1. If the index has no package named `N` at all, this is a **dead end** with the message `unknown package N`.")
    w("2. Otherwise compute the **candidates**: all versions of `N` in the index, newest first, minus these:")
    w("   * yanked versions, unless the version is the one `N` has in the preferred lock (see below);")
    w("   * versions that do not satisfy *every* requirement collected for `N`;")
    if p["breaks"]:
        w("   * versions that satisfy the constraint of a recorded `breaks` entry whose name is `N`;")
    if F:
        w("   * versions that do not declare every feature requested for `N`;")
    w(("   If `lock --oldest` was given, the remaining candidates are reversed (oldest first). " if p["oldest"] else "   The remaining candidates stay in this order. ") +
      ("Finally, if the preferred lock has a version for `N` and it is still a candidate, it moves to the front (the others keep their relative order)." if p["sticky"] else ""))
    w("3. Try the candidates in order. Count every try (across the whole search): when the count would exceed **" + str(p["limit"]) + "**, the search stops at once with `error: search limit reached`. To *try* a candidate `P`: "
      "copy the state, remove `N` from the front of the queue, and **choose** `P`:")
    w("   * record `N -> P` as chosen" + (" (the requested features of `N` stay as they are)" if F else "") + ";")
    if p["breaks"]:
        w("   * for each `breaks X C` of `P` in file order: if `X` is already chosen at a version satisfying `C`, the try fails; otherwise record `(X, C)`;")
    w("   * take the **active needs** of `P`: its `needs` lines in file order" + (", leaving out the gated ones whose feature is not requested for `N`" if F else "") + ". Process them first in, first out, each as follows (a need of a package `Q` on `DEP`):")
    w("     * append `(constraint, Q VERSION)` to the requirements of `DEP`;")
    if F:
        w("     * let `NEW` be the features asked for by the need that were not requested for `DEP` yet; add them to the requested features of `DEP`;")
    w("     * if `DEP` is already chosen at version `D`: the try fails if `D` does not satisfy the constraint" + ("; or if `D` does not declare every feature in `NEW`; otherwise append to the end of the work list the gated needs of `D` (file order) whose gate is in `NEW`" if F else "") + ";")
    w("     * otherwise, if `DEP` was never queued, append it to the queue.")
    w("   If the try did not fail, continue the search from the new state (the next **Step**); if that search succeeds, its result is the answer; otherwise go on with the next candidate.")
    w("4. If all candidates failed or there were none, this is a **dead end** for `N` with the message `cannot resolve N: needs C1 (WHO1), C2 (WHO2), ...` listing *all* requirements of `N` in this state in their order, each as `CONSTRAINT (WHO)`. "
      "(If `N` has no requirements the list is empty and the message ends with `needs `; this cannot happen for queued names.) Then the search backs up to the previous choice.")
    w("When the queue is empty the search succeeds: the answer is the set of chosen packages" + (" with, for each, its requested features (the enabled features)" if F else "") + ". "
      "The **first dead end** that ever occurs during the whole search gives the error line `error: ` + its message, if the search finally fails (later dead ends are ignored). "
      "The step counter does not reset when backing up.\n")
    if p["sticky"]:
        w("**The preferred lock.** For `lock` without `--fresh`, the preference is every `NAME VERSION` of `lock.txt` if that file exists; for `upgrade` it is the same minus the named packages; for `lock --fresh` it is empty. "
          "A preferred version needs not satisfy anything: it only matters as described in the candidate rules (it is exempt from the yanked rule and moves to the front when it is a candidate).\n")
    w("## Examples\n")
    ex = [(c, r) for (c, r) in by_name.values() if c.visible]
    for c, r in ex[:3]:
        w(K.show_case(tool, c, r))
    w("The visible example checks (`tests/examples.json`, run with `python3 tests/run_examples.py`) use the same layout as the hidden ones: every check gives the input files, the command line and the expected output.")
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------------------------------------------

PROBE = """
import contextlib, io, json, os, sys, tempfile
sys.path.insert(0, os.path.abspath("src"))
import solver, __TOOL__ as app
cases = json.load(sys.stdin)
orig = solver.Solver.run
seen = {}
def run(self):
    try:
        return orig(self)
    finally:
        seen["attempts"] = self.attempts
solver.Solver.run = run
res = []
for c in cases:
    d = tempfile.mkdtemp()
    for p, t in c["files"].items():
        open(os.path.join(d, p), "w").write(t)
    os.chdir(d)
    seen.clear()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = app.main(c["args"])
    lines = buf.getvalue().strip().splitlines()
    res.append({"attempts": seen.get("attempts", 0), "ok": bool(lines) and lines[-1].endswith(" packages"), "n": len(lines) - 1})
print(json.dumps(res))
"""

def vtxt(t, tag=None):
    return "%d.%d.%d" % t + (f"-{tag}" if tag else "")


def allows(op, t, v):
    """Does clause (op, v) allow t?  t and v are (nums, tag) with numbers as tuples; mirrors the README."""
    (tn, ttag), (vn, vtag) = t, v

    def key(n, tag):
        return (n, 1 if tag is None else 0, tag or "")

    kt, kv = key(tn, ttag), key(vn, vtag)
    if op == ">=":
        return kt >= kv
    if op == ">":
        return kt > kv
    if op == "<=":
        return kt <= kv
    if op == "<":
        return kt < kv
    if op == "=":
        return kt == kv
    if op == "!=":
        return kt != kv
    return True


class Gen:
    def __init__(self, p, rng):
        self.p, self.rng = p, rng

    def cons_for(self, versions, target):
        """A constraint word that allows the target version; versions: list of (nums, tag)."""
        p, rng = self.p, self.rng
        ops = p["ops"]
        tn, ttag = target
        op = rng.choice(ops)
        lows = [v for v in versions if allows("<=", v, target)]
        highs = [v for v in versions if allows(">=", v, target)]
        lo, hi = rng.choice(lows), rng.choice(highs)
        T, LO, HI = vtxt(tn, ttag), vtxt(*lo), vtxt(*hi)
        if op == "*":
            return "*"
        if op in (">=", ">"):
            if op == ">" and lo == target:
                op = ">=" if ">=" in ops else None
                if op is None:
                    return T
            c = op + LO
            if "<" in ops and rng.random() < 0.4 and hi != target:
                c += ",<" + HI
            elif "<=" in ops and rng.random() < 0.3:
                c += ",<=" + HI
            return c
        if op in ("<=", "<"):
            if op == "<" and hi == target:
                if "<=" not in ops:
                    return T
                op = "<="
            return op + HI
        if op == "=":
            return T if rng.random() < 0.5 else "=" + T
        if op == "!=":
            base = (">=" + LO) if ">=" in ops else ("*" if "*" in ops else None)
            others = [v for v in versions if v != target]
            if base and others:
                return base + ",!=" + vtxt(*rng.choice(others))
            return base or T
        if ttag:
            return (">=" + T) if ">=" in ops else T
        M, m, pt = tn
        if op == "^":
            if p["caret_zero"] and M == 0:
                style = "Mm" if m > 0 else "Mmp"
            else:
                style = rng.choice(["M", "Mm", "Mmp"])
            return "^" + {"M": str(M), "Mm": f"{M}.{m}", "Mmp": f"{M}.{m}.{pt}"}[style]
        return "~" + (f"{M}.{m}" if rng.random() < 0.5 else f"{M}.{m}.{pt}")

    def index(self, n_pkgs, planted=True):
        p, rng = self.p, self.rng
        names = sorted(rng.sample(POOL, n_pkgs))
        vers: dict[str, list] = {}
        for name in names:
            cur = [rng.randint(0, 2), rng.randint(0, 4), rng.randint(0, 6)]
            lst = []
            for _ in range(rng.randint(1, 4)):
                lst.append((tuple(cur), None))
                r = rng.random()
                if r < 0.25:
                    cur = [cur[0] + 1, 0, rng.randint(0, 2)]
                elif r < 0.6:
                    cur = [cur[0], cur[1] + 1, rng.randint(0, 2)]
                else:
                    cur = [cur[0], cur[1], cur[2] + rng.randint(1, 3)]
            if p["tags"] and rng.random() < 0.35:
                lst.append((tuple(cur), rng.choice(["rc1", "beta2", "alpha", "rc10", "rc2"])))
            vers[name] = lst
        plant = {name: (vers[name][-1] if rng.random() < 0.3 else rng.choice(vers[name])) for name in names}
        blocks = []
        feats_of: dict[tuple, list] = {}
        for name in names:
            for v in vers[name]:
                fl = []
                if p["features"] and rng.random() < 0.4:
                    fl = rng.sample(FEATS, rng.randint(1, 2))
                feats_of[(name, v)] = fl
        for name in names:
            for v in sorted(vers[name], key=lambda x: (x[0], 1 if x[1] is None else 0, x[1] or "")):
                lines = [f"pkg {name} {vtxt(*v)}"]
                if v[1] is None and plant[name] != v and rng.random() < 0.12:
                    lines.append("yanked")
                fl = feats_of[(name, v)]
                for f in fl:
                    lines.append(f"feature {f}")
                others = [n for n in names if n != name]
                for dep in rng.sample(others, min(len(others), rng.choice([0, 1, 1, 2, 2, 3]))):
                    is_plant = plant[name] == v
                    tgt = plant[dep] if (is_plant or rng.random() < 0.25) else rng.choice(vers[dep])
                    c = self.cons_for(vers[dep], tgt)
                    line = f"needs {dep} {c}"
                    if p["features"]:
                        asks = [f for f in feats_of[(dep, tgt)] if rng.random() < 0.4]
                        line += "".join(f" +{f}" for f in asks)
                        if fl and rng.random() < 0.4:
                            line += f" if {rng.choice(fl)}"
                    lines.append(line)
                if p["breaks"] and rng.random() < 0.15:
                    dep = rng.choice(others)
                    cand = [x for x in vers[dep] if x != plant[dep]]
                    if cand:
                        t = rng.choice(cand)
                        lines.append(f"breaks {dep} {vtxt(*t)}")
                if rng.random() < 0.15 and len(lines) > 1:
                    lines.insert(1, f"# {name} {vtxt(*v)} notes")
                blocks.append("\n".join(lines))
        self.declared = feats_of
        return names, vers, plant, "\n".join(blocks) + "\n"

    def project(self, names, vers, plant, n=None):
        p, rng = self.p, self.rng
        roots = sorted(rng.sample(names, n or rng.randint(1, 3)))
        rng.shuffle(roots)
        lines = []
        for r in roots:
            c = self.cons_for(vers[r], plant[r]) if rng.random() < 0.4 else ("*" if "*" in p["ops"] else ">=" + vtxt(*min(vers[r], key=lambda v: (v[0], 1 if v[1] is None else 0, v[1] or ""))))
            line = f"want {r} {c}"
            have = self.declared.get((r, plant[r]), [])
            if p["features"] and have and rng.random() < 0.4:
                line += " +" + rng.choice(have)
            lines.append(line)
        return "\n".join(lines) + "\n"

    def lock_from(self, names, vers, plant, drop=0, mutate=0):
        rng = self.rng
        lines = []
        for n in names:
            if rng.random() < drop:
                continue
            v = plant[n]
            if rng.random() < mutate:
                v = rng.choice(vers[n])
            line = f"{n} {vtxt(*v)}"
            if self.p["features"] and rng.random() < 0.3:
                line += " " + ",".join(sorted(rng.sample(FEATS, rng.randint(1, 2))))
            lines.append(line)
        return "\n".join(lines) + "\n"


def make_cases(p: dict, tool: str, rng, probe) -> list[K.Case]:
    g = Gen(p, rng)
    cases: list[K.Case] = []
    cnt: dict[str, int] = {}

    def add(group, args, files, visible=False, watch=None):
        cnt[group] = cnt.get(group, 0) + 1
        cases.append(K.Case(name=f"{group}-{cnt[group]:02d}", group=group, args=args, files=files, visible=visible, watch=watch if watch is not None else []))

    # resolution scenarios: draw many candidates; the oracle tells which succeed and how much it had to backtrack
    pool = []
    for k in range(70):
        names, vers, plant, idx = g.index(rng.randint(4, 8))
        proj = g.project(names, vers, plant)
        if k % 3 == 2:
            extra = rng.choice(names)
            proj += f"want {extra} " + g.cons_for(vers[extra], rng.choice(vers[extra])) + "\n"
        args = ["lock"] + (["--oldest"] if p["oldest"] and k % 3 == 1 else [])
        pool.append(K.Case(name=f"pool-{k}", group="lock", args=args, files={"index.txt": idx, "project.txt": proj}, watch=["lock.txt"]))
    stats = probe(pool)
    good = sorted((c for c, s_ in zip(pool, stats) if s_["ok"]), key=lambda c: -(stats[pool.index(c)]["attempts"] - stats[pool.index(c)]["n"]))
    bad = sorted((c for c, s_ in zip(pool, stats) if not s_["ok"]), key=lambda c: -stats[pool.index(c)]["attempts"])
    picked = good[:8] + good[8:][::3][:3] + bad[:5]
    for k, c in enumerate(picked):
        add("lock", c.args, c.files, visible=(k == 0), watch=["lock.txt"])
    # sticky / upgrade
    if p["sticky"]:
        for k in range(5):
            names, vers, plant, idx = g.index(rng.randint(4, 7))
            proj = g.project(names, vers, plant)
            lock = g.lock_from(names, vers, plant, drop=0.1, mutate=0.4)
            files = {"index.txt": idx, "project.txt": proj, "lock.txt": lock}
            if k < 2:
                add("sticky", ["lock"] + (["--fresh"] if k else []), files, watch=["lock.txt"])
            else:
                tgt = sorted(rng.sample(names, rng.randint(1, 2)))
                if k == 4:
                    tgt.append("ghost")
                add("sticky", ["upgrade"] + tgt, files, watch=["lock.txt"])
        for args in (["upgrade"], ["lock", "--fresh", "--fresh"]):
            names, vers, plant, idx = g.index(4)
            add("sticky", args, {"index.txt": idx, "project.txt": g.project(names, vers, plant), "lock.txt": g.lock_from(names, vers, plant)}, watch=["lock.txt"])
    # check
    for k in range(7):
        names, vers, plant, idx = g.index(rng.randint(4, 8))
        proj = g.project(names, vers, plant)
        lock = g.lock_from(names, vers, plant, drop=0.15 * (k % 3), mutate=0.2 * (k % 4))
        add("check", ["check"], {"index.txt": idx, "project.txt": proj, "lock.txt": lock}, visible=False)
    # tree
    for k in range(4):
        names, vers, plant, idx = g.index(rng.randint(4, 8))
        proj = g.project(names, vers, plant)
        lock = g.lock_from(names, vers, plant, drop=0.1 * (k % 2), mutate=0.1)
        add("tree", ["tree"], {"index.txt": idx, "project.txt": proj, "lock.txt": lock}, visible=(k == 0))
    # file errors
    def base(k):
        names, vers, plant, idx = g.index(4)
        return {"index.txt": idx, "project.txt": g.project(names, vers, plant, 2)}, names

    F = p["features"]
    bad_index = [
        "needs a 1.0.0\npkg a 1.0.0\n", "pkg a\n", "pkg A 1.0.0\n", "pkg a 1.0\n", "pkg a 01.0.0\n", "pkg a 1.0.0-rc1\n", "pkg a 1.0.0\npkg a 1.0.0\n",
        "pkg a 1.0.0\nfrobnicate x\n", "pkg a 1.0.0\nneeds b\n", "pkg a 1.0.0\nneeds B 1.0\n", "pkg a 1.0.0\nneeds b >=1..0\n",
        "pkg a 1.0.0\nneeds b ^1,\n", "pkg a 1.0.0\nneeds b *\n", "pkg a 1.0.0\nneeds b ~1\n", "pkg a 1.0.0\nneeds b !=1.0.0\n", "pkg a 1.0.0\nneeds b <1.0.0-beta\n",
        "pkg a 1.0.0\nyanked now\n", "# only comments\n\n  \n", "pkg a 1.0.0\nneeds b 1 extra\n", "pkg a 1.0.0 extra\n",
        "pkg a 1.0.0\nneeds b 1 +x\n", "pkg a 1.0.0\nfeature t\nneeds b 1 if t\nneeds c 1 if u\n", "pkg a 1.0.0\nfeature t\nfeature t\n",
        "pkg a 1.0.0\nfeature T\n", "pkg a 1.0.0\nbreaks b\n", "pkg a 1.0.0\nbreaks b >=1\n", "pkg a 1.0.0\nneeds b 1 +T\n", "pkg a 1.0.0\nneeds 9b 1\n",
    ]
    rng.shuffle(bad_index)
    for text in bad_index[:12]:
        files, _ = base(0)
        files["index.txt"] = text
        add("format", ["lock"], files)
    for text in ["want\n", "want a\n", "want a 1 extra\n", "need a 1\n", "want A 1\n", "want a >>1\n", "want a 1 +T\n", "# x\nwant a 1 +t extra\n"]:
        files, _ = base(0)
        files["project.txt"] = text
        add("format", ["lock"], files)
    for text in ["a\n", "a 1.0\n", "A 1.0.0\n", "a 1.0.0\na 1.1.0\n", "a 1.0.0 x y\n", "a 1.0.0 T\n", "a 1.0.0 t,\n"]:
        files, _ = base(0)
        files["lock.txt"] = text
        add("format", ["check"], files)
    # command line
    names, vers, plant, idx = g.index(4)
    files = {"index.txt": idx, "project.txt": g.project(names, vers, plant, 2)}
    cli = [[], ["frob"], ["lock", "extra"], ["lock", "--bogus"], ["lock", "--oldest"], ["lock", "--fresh"], ["tree"], ["check"], ["tree", "x"], ["check", "x"], ["upgrade"], ["upgrade", "a"], ["Lock"], ["lock", "-x"]]
    for args in cli:
        add("cli", args, dict(files), watch=["lock.txt"])
    add("cli", ["lock"], {"project.txt": files["project.txt"]}, watch=["lock.txt"])
    add("cli", ["lock"], {"index.txt": files["index.txt"]}, watch=["lock.txt"])
    # search stress: independent choices are made first, the contradiction shows up last, chronological backtracking thrashes
    import math
    k_limit = math.ceil(math.log(p["limit"], 3)) + 1
    for k, tail in ((k_limit, "limit"), (3, "exhaust"), (4, "late-need")):
        idx = []
        for i in range(k):
            for v in range(3):
                idx.append(f"pkg p{i:02d}x 1.{v}.0")
        if tail == "late-need":
            for v in range(3):
                idx.append(f"pkg zlast 1.{v}.0\nneeds p00x ^1.{(v + 1) % 3}\nneeds p01x =1.{v}.0")
            proj = "".join(f"want p{i:02d}x *\n" if "*" in p["ops"] else f"want p{i:02d}x >=0\n" for i in range(k)) + "want zlast >=1.5\n"
        else:
            idx.append("pkg zlast 1.0.0")
            proj = "".join(f"want p{i:02d}x *\n" if "*" in p["ops"] else f"want p{i:02d}x >=0\n" for i in range(k)) + "want zlast >=2\n"
        add("search", ["lock"], {"index.txt": "\n".join(idx) + "\n", "project.txt": proj}, watch=["lock.txt"])
    names, vers, plant, idx = g.index(5)
    add("search", ["lock"], {"index.txt": idx, "project.txt": g.project(names, vers, plant, 3) + f"want {names[0]} >=99\n"}, watch=["lock.txt"])
    return cases


@family("project-resolve", category="project", lang="rust", kind="greenfield", n=8,
        summary="a dependency resolver for an invented ecosystem: tagged versions, constraint clauses, features, yanked releases, breaks, sticky locks, lock validation, tree view")
def gen(rng, n):
    for i in range(n):
        plan = dict(PLAN[i])
        tool = TOOLS[i]
        lang = plan.pop("lang")
        p = dict(plan)
        cfg = dict(TOOL=tool, LIMIT=p["limit"], FEATURES=p["features"], BREAKS=p["breaks"], TAGS=p["tags"], OPS=p["ops"], CARET_ZERO=p["caret_zero"],
                   OLDEST_OPT=p["oldest"], STICKY=p["sticky"], CHECK_UNUSED=p["unused"])
        py_sol = K.merged(K.load_src(THEME, "python", tool), K.render_config("python", cfg))
        cases = make_cases(p, tool, rng, lambda pool, py_sol=py_sol, tool=tool: K.probe(py_sol, tool, PROBE.replace("__TOOL__", tool), [{"files": c.files, "args": c.args} for c in pool]))
        sol = py_sol if lang == "python" else K.merged(K.load_src(THEME, lang, tool), K.render_config(lang, cfg))
        nfeat = sum([p["features"], p["breaks"], p["tags"], p["caret_zero"], p["sticky"], p["unused"]])
        voice = VOICES[i % len(VOICES)]
        prompt = voice.format(tool=tool, Lang=K.LANG_NAME[lang], run=K.how_to_run(lang, tool), num=2300 + i * 29, upg=", upgrade" if p["sticky"] else "")
        yield K.project_task(
            theme=THEME, tool=tool, lang=lang, cases=cases, solution=sol, py_solution=py_sol,
            readme=lambda by_name, p=p, tool=tool, lang=lang: readme(p, tool, lang, by_name),
            prompt=prompt, difficulty=4 if nfeat <= 3 else 5, slug=f"{i + 1:02d}-{tool}-{lang}",
            notes={"features": p["features"], "breaks": p["breaks"], "tags": p["tags"], "ops": p["ops"], "limit": p["limit"]},
            tags=["resolver", "backtracking"],
        )
