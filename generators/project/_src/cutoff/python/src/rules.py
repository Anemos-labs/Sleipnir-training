"""Rules: parsing, validation and lookup (exact rules first, then the best matching pattern)."""
import re

import actions
import config as C

PATH_CHARS = re.compile(r"^[A-Za-z0-9_./%-]+$")


class Rule:
    def __init__(self, target, deps, action, args, always, order):
        self.target = target
        self.deps = deps
        self.action = action
        self.args = args
        self.always = always
        self.order = order
        self.pattern = "%" in target
        if self.pattern:
            self.pre, _, self.suf = target.partition("%")

    def action_text(self):
        return " ".join([self.action] + self.args)

    def match(self, path):
        """The stem if `path` matches this pattern rule, else None."""
        if not self.pattern:
            return None
        if len(path) > len(self.pre) + len(self.suf) and path.startswith(self.pre) and path.endswith(self.suf):
            return path[len(self.pre): len(path) - len(self.suf)]
        return None


def good_path(p, allow_stem=False):
    if not PATH_CHARS.match(p):
        return False
    if "%" in p and (not allow_stem or p.count("%") != 1):
        return False
    for seg in p.split("/"):
        if seg in ("", ".", ".."):
            return False
    return True


def parse_rule(tokens):
    """tokens (after the word `rule`) -> (Rule fields, None) or (None, error message)."""
    syntax = "rule syntax: rule TARGET <- DEP... : ACTION [ARG...]"
    if len(tokens) < 3 or tokens[1] != "<-":
        return None, syntax
    seps = [":"] + ([":!"] if C.ALWAYS_RULES else [])
    sep = next((i for i in range(2, len(tokens)) if tokens[i] in seps), None)
    if sep is None or sep + 1 >= len(tokens):
        return None, syntax
    target, deps = tokens[0], tokens[2:sep]
    always = tokens[sep] == ":!"
    action, args = tokens[sep + 1], tokens[sep + 2:]
    for p in [target] + deps:
        if not good_path(p, C.PATTERNS):
            return None, "bad path '%s'" % p
    if "%" not in target and any("%" in d for d in deps):
        return None, "stem in dependency without stem in target"
    ok, msg = actions.valid(action, args)
    if not ok:
        return None, msg
    return (target, deps, action, args, always), None


class RuleBook:
    def __init__(self):
        self.rules = []

    def add(self, target, deps, action, args, always):
        self.rules.append(Rule(target, deps, action, args, always, len(self.rules)))

    def has_target(self, target):
        return any(r.target == target for r in self.rules)

    def lookup(self, path):
        """(rule, instantiated deps) for a path, or (None, [])."""
        for r in self.rules:
            if not r.pattern and r.target == path:
                return r, list(r.deps)
        best, stem = None, None
        for r in self.rules:
            s = r.match(path)
            if s is None:
                continue
            if best is None or len(r.pre) + len(r.suf) > len(best.pre) + len(best.suf):
                best, stem = r, s
        if best is None:
            return None, []
        return best, [d.replace("%", stem) for d in best.deps]

    def pattern_hits(self, target, files):
        """Sorted existing files that a new rule target (exact or pattern) would claim."""
        if "%" not in target:
            return [target] if target in files else []
        pre, _, suf = target.partition("%")
        return sorted(f for f in files if len(f) > len(pre) + len(suf) and f.startswith(pre) and f.endswith(suf))
