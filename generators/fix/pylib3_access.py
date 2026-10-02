"""Rules, permissions and workflows in domain clothes (python, fix-py-3): folder ACLs, approvals, a rule engine, discount stacking."""
from fx import Lib, dd

from generators.fix._pylib3 import chain, register_libs3

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# aclwalk: folder permissions with inheritance, groups and deny rules (multi-module)
# ======================================================================================================================

ACLWALK_README = dd('''
    # aclwalk

    Permission checks for a document store whose resources are slash-separated paths such as `/projects/apollo/plan.md`.

    ## `aclwalk.paths`

    * `normalize(path) -> str`: the canonical absolute form. The path must start with `/` (else `ValueError`).
      Empty segments and `.` are dropped, `..` removes the previous segment (`ValueError` if there is none: the path
      would leave the root). No trailing slash; the root is `"/"`.
    * `ancestors(path) -> list[str]`: the normalized path's ancestors and itself, root first:
      `ancestors("/a/b") == ["/", "/a", "/a/b"]`; `ancestors("/") == ["/"]`.
    * `depth(path) -> int`: number of segments of the normalized path (`depth("/") == 0`).
    * `matches(pattern, path) -> bool`: does the pattern match the (normalized) path exactly? A pattern is split into
      segments the same way; a segment `**` matches zero or more whole segments; any other segment matches exactly
      one path segment, where `*` inside a segment stands for any run of characters (possibly empty) within that
      segment (`"report-*"` matches `"report-2024"`, `"*"` matches any single segment).

    ## `aclwalk.rules`

    `Rule(effect, who, action, pattern, inherit=True)` is a frozen dataclass. `effect` is `"allow"` or `"deny"`;
    `who` is a user name, `"group:<name>"` or `"*"`; `action` is `"read"`, `"write"`, `"admin"` or `"*"`.
    `parse_rules(text) -> list[Rule]` reads one rule per line: `effect who action pattern` optionally followed by the
    word `noinherit`. `#` starts a comment and blank lines are skipped. A bad line is a `ValueError` starting with
    `line N:` (N counts physical lines from 1): wrong number of fields, unknown effect, unknown action, a pattern that
    does not start with `/`, a fifth word other than `noinherit`.

    ## `aclwalk.evaluator`

    `ACTIONS = ("read", "write", "admin")`. `Policy(rules, groups=None)`: `groups` maps a group name to a collection of
    user names.

    A rule *applies* to a user, an action and a (normalized) path when

    * **who**: `who == "*"`, or `who == "group:g"` and the user is in `groups["g"]`, or `who` equals the user name;
    * **action**: the rule's action equals the requested one or is `"*"`;
    * **scope**: with `inherit=True`, the pattern matches the path or one of its ancestors; with `inherit=False`, the
      pattern matches the path itself. The rule's *scope depth* is the depth of the **shallowest** path among the
      path's ancestors-and-itself that satisfies this (so the rule `/a/**` has scope depth 1 for `/a/b/c`, because it
      already matches `/a`).

    Among the applicable rules the winner has the largest `(scope depth, who rank, is deny)` where who rank is `2`
    for a rule naming the user, `1` for a group rule and `0` for `*`: a deeper rule beats a shallower one, a more
    personal rule beats a more general one at equal depth, and at an otherwise equal key `deny` beats `allow`. When
    several rules share the winning key the earliest in the list is the winner. No applicable rule means denied.

    * `explain(user, action, path) -> Rule | None`: the winning rule.
    * `allowed(user, action, path) -> bool`: the winner exists and is an allow rule.
    * `effective(user, path) -> dict`: `{action: allowed}` for every action in `ACTIONS`.
    * `visible(user, paths) -> list[str]`: the normalized forms of the paths the user may `read`, sorted and without
      duplicates.
''')

ACLWALK_PATHS = dd('''
    """Path helpers: normalising, ancestors and glob-lite matching."""
    import re


    def _segments(path: str) -> list:
        parts = []
        for seg in path.split("/"):
            if seg in ("", "."):
                continue
            if seg == "..":
                if not parts:
                    raise ValueError("path escapes the root")
                parts.pop()
            else:
                parts.append(seg)
        return parts


    def normalize(path: str) -> str:
        if not path.startswith("/"):
            raise ValueError("path must be absolute")
        return "/" + "/".join(_segments(path))


    def ancestors(path: str) -> list:
        parts = _segments(normalize(path))
        return ["/"] + ["/" + "/".join(parts[:i]) for i in range(1, len(parts) + 1)]


    def depth(path: str) -> int:
        return len(_segments(normalize(path)))


    def _seg_match(pat: str, seg: str) -> bool:
        if "*" not in pat:
            return pat == seg
        rx = ".*".join(re.escape(piece) for piece in pat.split("*"))
        return re.fullmatch(rx, seg) is not None


    def _match(pats: list, segs: list) -> bool:
        if not pats:
            return not segs
        head = pats[0]
        if head == "**":
            return any(_match(pats[1:], segs[i:]) for i in range(len(segs) + 1))
        if not segs:
            return False
        return _seg_match(head, segs[0]) and _match(pats[1:], segs[1:])


    def matches(pattern: str, path: str) -> bool:
        if not pattern.startswith("/"):
            raise ValueError("pattern must be absolute")
        pats = [p for p in pattern.split("/") if p not in ("", ".")]
        return _match(pats, _segments(normalize(path)))
''')

ACLWALK_RULES = dd('''
    """Rules and their text format."""
    from dataclasses import dataclass

    EFFECTS = ("allow", "deny")
    RULE_ACTIONS = ("read", "write", "admin", "*")


    @dataclass(frozen=True)
    class Rule:
        effect: str
        who: str
        action: str
        pattern: str
        inherit: bool = True


    def parse_rules(text: str) -> list:
        rules = []
        for lineno, raw in enumerate(text.splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            f = line.split()
            if len(f) not in (4, 5):
                raise ValueError(f"line {lineno}: expected 4 or 5 words, got {len(f)}")
            effect, who, action, pattern = f[:4]
            if effect not in EFFECTS:
                raise ValueError(f"line {lineno}: unknown effect {effect!r}")
            if action not in RULE_ACTIONS:
                raise ValueError(f"line {lineno}: unknown action {action!r}")
            if not pattern.startswith("/"):
                raise ValueError(f"line {lineno}: pattern must start with /")
            if len(f) == 5 and f[4] != "noinherit":
                raise ValueError(f"line {lineno}: unexpected word {f[4]!r}")
            rules.append(Rule(effect, who, action, pattern, len(f) == 4))
        return rules
''')

ACLWALK_EVALUATOR = dd('''
    """Deciding access: the most specific applicable rule wins."""
    from .paths import ancestors, depth, matches, normalize

    ACTIONS = ("read", "write", "admin")


    class Policy:
        def __init__(self, rules, groups=None):
            self.rules = list(rules)
            self.groups = {name: set(users) for name, users in (groups or {}).items()}

        def _who_rank(self, rule, user):
            if rule.who == "*":
                return 0
            if rule.who.startswith("group:"):
                return 1 if user in self.groups.get(rule.who[len("group:"):], ()) else None
            return 2 if rule.who == user else None

        @staticmethod
        def _scope_depth(rule, path):
            if rule.inherit:
                for node in ancestors(path):
                    if matches(rule.pattern, node):
                        return depth(node)
                return None
            return depth(path) if matches(rule.pattern, path) else None

        def explain(self, user, action, path):
            path = normalize(path)
            best_key, best = None, None
            for rule in self.rules:
                if rule.action not in (action, "*"):
                    continue
                rank = self._who_rank(rule, user)
                if rank is None:
                    continue
                scope = self._scope_depth(rule, path)
                if scope is None:
                    continue
                key = (scope, rank, rule.effect == "deny")
                if best_key is None or key > best_key:
                    best_key, best = key, rule
            return best

        def allowed(self, user, action, path):
            rule = self.explain(user, action, path)
            return rule is not None and rule.effect == "allow"

        def effective(self, user, path):
            return {action: self.allowed(user, action, path) for action in ACTIONS}

        def visible(self, user, paths):
            return sorted({normalize(p) for p in paths if self.allowed(user, "read", p)})
''')

ACLWALK_VISIBLE = dd('''
    import unittest

    from aclwalk.evaluator import Policy
    from aclwalk.paths import normalize
    from aclwalk.rules import parse_rules


    class BasicTests(unittest.TestCase):
        def test_normalize(self):
            self.assertEqual(normalize("/a//b/./c/"), "/a/b/c")

        def test_allow_inherited(self):
            p = Policy(parse_rules("allow * read /docs"))
            self.assertTrue(p.allowed("ann", "read", "/docs/readme.md"))
            self.assertFalse(p.allowed("ann", "write", "/docs/readme.md"))


    if __name__ == "__main__":
        unittest.main()
''')

ACLWALK_HIDDEN_PATHS = dd('''
    import unittest

    from aclwalk.paths import ancestors, depth, matches, normalize


    class Normalize(unittest.TestCase):
        def test_forms(self):
            cases = {
                "/": "/", "//": "/", "/a": "/a", "/a/": "/a", "/a//b": "/a/b", "/a/./b": "/a/b", "/a/b/..": "/a",
                "/a/../b": "/b", "/a/b/../../c": "/c", "/./": "/", "/a/b/../..": "/", "/a/../..": None,
            }
            for raw, want in cases.items():
                if want is None:
                    with self.assertRaises(ValueError, msg=raw):
                        normalize(raw)
                else:
                    self.assertEqual(normalize(raw), want, raw)

        def test_must_be_absolute(self):
            for bad in ("", "a/b", "./a", "../a"):
                with self.assertRaises(ValueError):
                    normalize(bad)

        def test_dotdot_cannot_escape(self):
            with self.assertRaises(ValueError):
                normalize("/..")
            with self.assertRaises(ValueError):
                normalize("/a/../../b")
            self.assertEqual(normalize("/a/b/../.."), "/")

        def test_dotdot_dotdot_names(self):
            self.assertEqual(normalize("/a/..b/c"), "/a/..b/c")
            self.assertEqual(normalize("/a/.hidden"), "/a/.hidden")


    class Ancestors(unittest.TestCase):
        def test_ancestors(self):
            self.assertEqual(ancestors("/a/b"), ["/", "/a", "/a/b"])
            self.assertEqual(ancestors("/"), ["/"])
            self.assertEqual(ancestors("/x"), ["/", "/x"])
            self.assertEqual(ancestors("/a//b/../c/"), ["/", "/a", "/a/c"])

        def test_depth(self):
            self.assertEqual(depth("/"), 0)
            self.assertEqual(depth("/a"), 1)
            self.assertEqual(depth("/a/b/c"), 3)
            self.assertEqual(depth("/a//b/"), 2)
            self.assertEqual(depth("/a/b/.."), 1)


    class Matches(unittest.TestCase):
        def test_literal(self):
            self.assertTrue(matches("/a/b", "/a/b"))
            self.assertTrue(matches("/a/b/", "/a/b"))
            self.assertTrue(matches("/a//b", "/a/b/"))
            self.assertFalse(matches("/a/b", "/a"))
            self.assertFalse(matches("/a/b", "/a/b/c"))
            self.assertFalse(matches("/a/b", "/a/c"))
            self.assertTrue(matches("/", "/"))
            self.assertFalse(matches("/", "/a"))

        def test_single_star(self):
            self.assertTrue(matches("/a/*", "/a/b"))
            self.assertFalse(matches("/a/*", "/a"))
            self.assertFalse(matches("/a/*", "/a/b/c"))
            self.assertTrue(matches("/*/b", "/x/b"))
            self.assertFalse(matches("/*/b", "/b"))
            self.assertTrue(matches("/*", "/anything"))
            self.assertFalse(matches("/*", "/"))

        def test_star_inside_segment(self):
            self.assertTrue(matches("/r/report-*", "/r/report-2024"))
            self.assertTrue(matches("/r/report-*", "/r/report-"))
            self.assertFalse(matches("/r/report-*", "/r/report"))
            self.assertTrue(matches("/r/*.md", "/r/readme.md"))
            self.assertFalse(matches("/r/*.md", "/r/readme.mdx"))
            self.assertTrue(matches("/r/a*c", "/r/abbbc"))
            self.assertTrue(matches("/r/a*c", "/r/ac"))
            self.assertFalse(matches("/r/a*c", "/r/ab"))
            self.assertTrue(matches("/r/*x*", "/r/axb"))
            self.assertFalse(matches("/r/*.md", "/r/dir/readme.md"))

        def test_regex_characters_are_literal(self):
            self.assertTrue(matches("/a.b", "/a.b"))
            self.assertFalse(matches("/a.b", "/aXb"))
            self.assertTrue(matches("/a+(b)", "/a+(b)"))
            self.assertFalse(matches("/f.*", "/fXY"))
            self.assertTrue(matches("/f.*", "/f.txt"))

        def test_double_star(self):
            self.assertTrue(matches("/a/**", "/a"))
            self.assertTrue(matches("/a/**", "/a/b"))
            self.assertTrue(matches("/a/**", "/a/b/c/d"))
            self.assertFalse(matches("/a/**", "/b"))
            self.assertTrue(matches("/**", "/"))
            self.assertTrue(matches("/**", "/x/y"))
            self.assertTrue(matches("/**/c", "/c"))
            self.assertTrue(matches("/**/c", "/a/b/c"))
            self.assertFalse(matches("/**/c", "/a/b/d"))
            self.assertTrue(matches("/a/**/c/*", "/a/c/z"))
            self.assertTrue(matches("/a/**/c/*", "/a/x/y/c/z"))
            self.assertFalse(matches("/a/**/c/*", "/a/x/y/c"))
            self.assertTrue(matches("/**/**", "/q"))

        def test_path_is_normalized(self):
            self.assertTrue(matches("/a/b", "/a/x/../b"))
            self.assertTrue(matches("/a/*", "/a/./b"))
            with self.assertRaises(ValueError):
                matches("/a", "/../a")

        def test_pattern_must_be_absolute(self):
            with self.assertRaises(ValueError):
                matches("a/b", "/a/b")


    if __name__ == "__main__":
        unittest.main()
''')

ACLWALK_HIDDEN_RULES = dd('''
    import unittest

    from aclwalk.rules import Rule, parse_rules


    class Parse(unittest.TestCase):
        def test_forms(self):
            text = (
                "allow * read /\\n"
                "deny bob write /projects/secret\\n"
                "allow group:eng * /projects/** noinherit\\n"
            )
            self.assertEqual(parse_rules(text), [
                Rule("allow", "*", "read", "/", True),
                Rule("deny", "bob", "write", "/projects/secret", True),
                Rule("allow", "group:eng", "*", "/projects/**", False),
            ])

        def test_comments_and_blank_lines(self):
            text = "# policy\\n\\n  allow  ann   admin   /x   # trailing\\n   # more\\ndeny * write /y\\n"
            self.assertEqual(parse_rules(text), [Rule("allow", "ann", "admin", "/x"), Rule("deny", "*", "write", "/y")])

        def test_empty(self):
            self.assertEqual(parse_rules(""), [])
            self.assertEqual(parse_rules("# nothing\\n\\n"), [])

        def test_rule_defaults_and_frozen(self):
            r = Rule("allow", "*", "read", "/")
            self.assertTrue(r.inherit)
            with self.assertRaises(Exception):
                r.effect = "deny"

        def test_errors_have_line_numbers(self):
            bad = [
                "allow * read", "allow * read / noinherit extra", "permit * read /", "allow * delete /",
                "allow * read docs", "allow * read / inherit", "ALLOW * read /",
            ]
            for text in bad:
                with self.assertRaises(ValueError, msg=text) as cm:
                    parse_rules("# c\\n\\n" + text)
                self.assertTrue(str(cm.exception).startswith("line 3:"), (text, str(cm.exception)))

        def test_all_actions(self):
            for a in ("read", "write", "admin", "*"):
                self.assertEqual(parse_rules(f"allow x {a} /")[0].action, a)


    if __name__ == "__main__":
        unittest.main()
''')

ACLWALK_HIDDEN_EVAL = dd('''
    import unittest

    from aclwalk.evaluator import ACTIONS, Policy
    from aclwalk.rules import Rule, parse_rules

    RULES = parse_rules("""
    allow * read /
    allow group:eng write /projects/**
    deny  bob write /projects/secret
    allow bob write /projects/secret/notes
    deny  * read /private noinherit
    allow alice * /private/**
    """)
    GROUPS = {"eng": ["alice", "bob", "carol"]}


    def policy():
        return Policy(RULES, GROUPS)


    class Decisions(unittest.TestCase):
        def test_default_deny(self):
            self.assertFalse(Policy([]).allowed("x", "read", "/"))
            self.assertIsNone(Policy([]).explain("x", "read", "/"))
            self.assertEqual(Policy([]).effective("x", "/a"), {"read": False, "write": False, "admin": False})

        def test_inherited_allow(self):
            p = policy()
            self.assertTrue(p.allowed("zed", "read", "/docs/x"))
            self.assertTrue(p.allowed("zed", "read", "/"))
            self.assertFalse(p.allowed("zed", "write", "/docs/x"))

        def test_group_rule(self):
            p = policy()
            self.assertTrue(p.allowed("carol", "write", "/projects/a/b"))
            self.assertTrue(p.allowed("carol", "write", "/projects"))
            self.assertFalse(p.allowed("zed", "write", "/projects/a/b"))
            self.assertFalse(p.allowed("carol", "write", "/other"))
            self.assertFalse(p.allowed("carol", "admin", "/projects/a"))

        def test_deeper_deny_beats_shallower_allow(self):
            p = policy()
            self.assertFalse(p.allowed("bob", "write", "/projects/secret"))
            self.assertFalse(p.allowed("bob", "write", "/projects/secret/x"))
            self.assertTrue(p.allowed("carol", "write", "/projects/secret/x"))

        def test_deeper_allow_beats_deny(self):
            p = policy()
            self.assertTrue(p.allowed("bob", "write", "/projects/secret/notes"))
            self.assertTrue(p.allowed("bob", "write", "/projects/secret/notes/today.txt"))
            self.assertFalse(p.allowed("bob", "write", "/projects/secret/other"))

        def test_noinherit_only_hits_the_exact_path(self):
            p = policy()
            self.assertFalse(p.allowed("bob", "read", "/private"))
            self.assertTrue(p.allowed("bob", "read", "/private/file"))
            self.assertTrue(p.allowed("bob", "read", "/privateer"))

        def test_personal_beats_general_at_equal_depth(self):
            p = policy()
            self.assertTrue(p.allowed("alice", "read", "/private"))
            self.assertTrue(p.allowed("alice", "write", "/private/x"))
            self.assertTrue(p.allowed("alice", "admin", "/private"))
            self.assertFalse(p.allowed("carol", "write", "/private/x"))

        def test_group_beats_star_at_equal_depth(self):
            p = Policy(parse_rules("deny * read /a\\nallow group:g read /a"), {"g": ["u"]})
            self.assertTrue(p.allowed("u", "read", "/a/b"))
            self.assertFalse(p.allowed("v", "read", "/a/b"))
            p = Policy(parse_rules("allow * read /a\\ndeny group:g read /a"), {"g": ["u"]})
            self.assertFalse(p.allowed("u", "read", "/a"))
            self.assertTrue(p.allowed("v", "read", "/a"))

        def test_user_beats_group(self):
            p = Policy(parse_rules("deny group:g read /a\\nallow u read /a"), {"g": ["u"]})
            self.assertTrue(p.allowed("u", "read", "/a"))
            p = Policy(parse_rules("allow group:g read /a\\ndeny u read /a"), {"g": ["u"]})
            self.assertFalse(p.allowed("u", "read", "/a"))

        def test_deny_beats_allow_on_a_tie(self):
            p = Policy(parse_rules("allow u read /a\\ndeny u read /a"))
            self.assertFalse(p.allowed("u", "read", "/a/b"))
            p = Policy(parse_rules("deny u read /a\\nallow u read /a"))
            self.assertFalse(p.allowed("u", "read", "/a/b"))

        def test_depth_beats_rank(self):
            p = Policy(parse_rules("allow u read /a\\ndeny * read /a/b"))
            self.assertFalse(p.allowed("u", "read", "/a/b/c"))
            self.assertTrue(p.allowed("u", "read", "/a/x"))

        def test_wildcard_action(self):
            p = Policy(parse_rules("allow u * /a\\ndeny u write /a/ro"))
            self.assertEqual(p.effective("u", "/a/x"), {"read": True, "write": True, "admin": True})
            self.assertEqual(p.effective("u", "/a/ro/x"), {"read": True, "write": False, "admin": True})
            self.assertEqual(p.effective("u", "/b"), {"read": False, "write": False, "admin": False})

        def test_pattern_scope_depth_uses_shallowest_match(self):
            p = Policy(parse_rules("allow u read /a/**\\ndeny u read /a/b/c"))
            self.assertTrue(p.allowed("u", "read", "/a/q"))
            self.assertTrue(p.allowed("u", "read", "/a"))
            self.assertFalse(p.allowed("u", "read", "/a/b/c"))
            self.assertFalse(p.allowed("u", "read", "/a/b/c/d"))
            p = Policy(parse_rules("deny u read /a/b\\nallow u read /**"))
            self.assertFalse(p.allowed("u", "read", "/a/b/c"))
            self.assertTrue(p.allowed("u", "read", "/a/x"))

        def test_wildcard_patterns_in_rules(self):
            p = Policy(parse_rules("allow * read /users/*/public/**\\ndeny * read /users/*/public/tmp"))
            self.assertTrue(p.allowed("x", "read", "/users/ann/public/a.txt"))
            self.assertFalse(p.allowed("x", "read", "/users/ann/private/a.txt"))
            self.assertFalse(p.allowed("x", "read", "/users/ann/public/tmp/a.txt"))
            self.assertTrue(p.allowed("x", "read", "/users/bob/public"))

        def test_paths_are_normalized_before_checking(self):
            p = policy()
            self.assertFalse(p.allowed("bob", "write", "/projects/x/../secret/y"))
            self.assertTrue(p.allowed("bob", "write", "/projects//x/"))
            with self.assertRaises(ValueError):
                p.allowed("bob", "read", "relative/path")
            with self.assertRaises(ValueError):
                p.allowed("bob", "read", "/../etc")

        def test_unknown_group_has_no_members(self):
            p = Policy(parse_rules("allow group:ghost read /"))
            self.assertFalse(p.allowed("u", "read", "/x"))
            p = Policy(parse_rules("allow group:g read /"), {"g": []})
            self.assertFalse(p.allowed("u", "read", "/x"))

        def test_groups_input_is_copied(self):
            groups = {"g": ["u"]}
            p = Policy(parse_rules("allow group:g read /"), groups)
            groups["g"].append("v")
            groups["h"] = ["w"]
            self.assertFalse(p.allowed("v", "read", "/"))


    class Explain(unittest.TestCase):
        def test_returns_the_winner(self):
            p = policy()
            self.assertEqual(p.explain("bob", "write", "/projects/secret/x"), Rule("deny", "bob", "write", "/projects/secret"))
            self.assertEqual(p.explain("bob", "write", "/projects/secret/notes/a"), Rule("allow", "bob", "write", "/projects/secret/notes"))
            self.assertEqual(p.explain("carol", "write", "/projects/a"), Rule("allow", "group:eng", "write", "/projects/**"))
            self.assertEqual(p.explain("zed", "read", "/q"), Rule("allow", "*", "read", "/"))
            self.assertIsNone(p.explain("zed", "admin", "/q"))

        def test_tie_reports_the_earliest_rule(self):
            first = Rule("allow", "u", "read", "/a")
            second = Rule("allow", "u", "*", "/a")
            p = Policy([first, second])
            self.assertIs(p.explain("u", "read", "/a/b"), first)
            p = Policy([second, first])
            self.assertIs(p.explain("u", "read", "/a/b"), second)


    class Effective(unittest.TestCase):
        def test_actions_constant(self):
            self.assertEqual(ACTIONS, ("read", "write", "admin"))

        def test_effective(self):
            p = policy()
            self.assertEqual(p.effective("alice", "/private"), {"read": True, "write": True, "admin": True})
            self.assertEqual(p.effective("bob", "/projects/x"), {"read": True, "write": True, "admin": False})
            self.assertEqual(list(p.effective("bob", "/projects/x")), ["read", "write", "admin"])

        def test_visible(self):
            p = policy()
            paths = ["/b/../docs", "/private", "/docs", "/private/a", "/z//", "/private/"]
            self.assertEqual(p.visible("bob", paths), ["/docs", "/private/a", "/z"])
            self.assertEqual(p.visible("alice", paths), ["/docs", "/private", "/private/a", "/z"])
            self.assertEqual(p.visible("bob", []), [])
            self.assertEqual(Policy([]).visible("x", ["/a"]), [])


    if __name__ == "__main__":
        unittest.main()
''')

_R_BASIC = "parse_rules('allow * read /\\ndeny * read /private noinherit\\nallow alice * /private/**')"
_R_PROJ = "parse_rules('allow group:eng write /projects/**\\ndeny bob write /projects/secret\\nallow bob write /projects/secret/notes')"
_G = "{'eng': ['alice', 'bob', 'carol']}"

ACLWALK = Lib(
    name="aclwalk", lang="python", title="the aclwalk permission checker",
    blurb="The document store calls aclwalk before every read or write to decide whether a user may touch a folder or file.",
    files={
        "aclwalk/__init__.py": "", "aclwalk/paths.py": ACLWALK_PATHS, "aclwalk/rules.py": ACLWALK_RULES,
        "aclwalk/evaluator.py": ACLWALK_EVALUATOR, "README.md": ACLWALK_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": ACLWALK_VISIBLE},
    hidden_tests={
        "tests/test_paths.py": ACLWALK_HIDDEN_PATHS, "tests/test_rules.py": ACLWALK_HIDDEN_RULES,
        "tests/test_eval.py": ACLWALK_HIDDEN_EVAL,
    },
    mutate=["aclwalk/paths.py", "aclwalk/rules.py", "aclwalk/evaluator.py"],
    difficulty=4, tags=["permissions", "acl", "multi-module"],
    probes=[
        "normalize('/a/b/../../c/')", "ancestors('/a//b/../c/')", "depth('/a//b/')",
        "matches('/a/**/c/*', '/a/x/y/c/z')", "matches('/**/c', '/c')", "matches('/r/report-*', '/r/report')",
        "matches('/r/*.md', '/r/dir/readme.md')", "matches('/f.*', '/fXY')",
        "parse_rules('deny bob write /p noinherit')",
        f"[Policy({_R_PROJ}, {_G}).allowed('bob', 'write', x) for x in ('/projects/secret/x', '/projects/secret/notes/a', '/projects/a')]",
        f"[Policy({_R_BASIC}).allowed('bob', 'read', x) for x in ('/private', '/private/file', '/docs')]",
        f"[Policy({_R_BASIC}).allowed(u, 'read', '/private') for u in ('alice', 'bob')]",
        f"Policy({_R_PROJ}, {_G}).explain('carol', 'write', '/projects/a')",
        f"Policy({_R_PROJ}, {_G}).effective('bob', '/projects/x')",
        f"Policy({_R_BASIC}).visible('bob', ['/b/../docs', '/private', '/docs', '/private/a', '/z//'])",
    ],
    probe_import=(
        "from aclwalk.paths import normalize, ancestors, depth, matches\n"
        "from aclwalk.rules import parse_rules\nfrom aclwalk.evaluator import Policy\n"
    ),
)

# ======================================================================================================================
# approvalflow: purchase-request approvals (multi-module state machine)
# ======================================================================================================================

APPROVALFLOW_README = dd('''
    # approvalflow

    Approval workflow for purchase requests. A request moves through states; how many approvals it needs depends on
    its amount (in whole currency units). Times are plain integers (hours).

    ## `approvalflow.states`

    States: `draft`, `submitted`, `approved`, `rejected`, `withdrawn`, `expired`; the last four are *final*.

    * `next_state(state, action) -> str`: the legal transitions are
      `draft --submit--> submitted`, `draft --withdraw--> withdrawn`, `submitted --approve--> approved`,
      `submitted --reject--> rejected`, `submitted --send_back--> draft`, `submitted --withdraw--> withdrawn`,
      `submitted --expire--> expired`. Anything else raises `IllegalTransition`, a subclass of `ValueError`.
    * `is_final(state) -> bool`.

    ## `approvalflow.rules`

    * `stages_for(amount) -> list[(role, needed)]`: the approval stages, in order. `ValueError` if `amount < 1`.
      Up to 500: `manager` (1). Up to 5000: `manager` (1), `finance` (1). Up to 20000: `manager` (1), `finance` (1),
      `director` (1). Above 20000: `manager` (1), `finance` (2), `director` (1).
    * `Directory(roles)`: `roles` maps a role name to a collection of user names. `has_role(user, role)` (unknown
      roles have nobody) and `holders(role)` (sorted list of users).

    ## `approvalflow.engine`

    `Request(id, requester, amount, created)` starts in state `draft`. Attributes: `stages` (from `stages_for`, so a
    bad amount raises `ValueError`), `approvals` (list of `(user, role, at)`), `submitted_at` (`None` until
    submitted), `reason` (`None`), `history` (list of `(action, user, at)` for every successful action; `at` is
    `None` for `withdraw`). `pending() -> (role, needed, got) | None`: the first stage that is not yet satisfied
    (`got` is the number of recorded approvals with that role), or `None` when every stage is satisfied.

    `Engine(directory, ttl=72)`. Every method raises `IllegalTransition` first if the action is not legal in the
    request's current state (that includes every action on a final request). Checks then run in the order given:

    * `submit(request, user, now)`: only the requester (`PermissionError` otherwise). Sets `submitted_at = now`.
    * `approve(request, user, now) -> str`: `PermissionError` if `user` is the requester; `ValueError` if the user
      already approved this request; `PermissionError` if the user does not hold the role of the pending stage.
      Records `(user, role, now)`. When no stage is pending any more the state becomes `approved`. Returns the new
      state.
    * `reject(request, user, now, reason)`: `PermissionError` unless the user holds the pending stage's role;
      `ValueError` if `reason` is empty or only whitespace. State `rejected`, `request.reason = reason`.
    * `send_back(request, user, now)`: the pending stage's role holder returns the request to `draft`; approvals are
      cleared and `submitted_at` reset to `None` (`PermissionError` for anyone else).
    * `withdraw(request, user)`: only the requester (`PermissionError`); allowed in `draft` and `submitted`.
    * `expire_overdue(requests, now) -> list[str]`: every request in state `submitted` with
      `now - submitted_at >= ttl` becomes `expired`; returns their ids in input order. Other requests are untouched.
''')

APPROVALFLOW_STATES = dd('''
    """Request states and legal transitions."""

    FINAL = frozenset({"approved", "rejected", "withdrawn", "expired"})

    TRANSITIONS = {
        "draft": {"submit": "submitted", "withdraw": "withdrawn"},
        "submitted": {
            "approve": "approved",
            "reject": "rejected",
            "send_back": "draft",
            "withdraw": "withdrawn",
            "expire": "expired",
        },
    }


    class IllegalTransition(ValueError):
        pass


    def next_state(state, action):
        try:
            return TRANSITIONS[state][action]
        except KeyError:
            raise IllegalTransition(f"cannot {action} a request that is {state}") from None


    def is_final(state):
        return state in FINAL
''')

APPROVALFLOW_RULES = dd('''
    """Which approvals a request needs, and who may give them."""


    def stages_for(amount):
        if amount < 1:
            raise ValueError("amount must be at least 1")
        if amount <= 500:
            return [("manager", 1)]
        if amount <= 5000:
            return [("manager", 1), ("finance", 1)]
        if amount <= 20000:
            return [("manager", 1), ("finance", 1), ("director", 1)]
        return [("manager", 1), ("finance", 2), ("director", 1)]


    class Directory:
        def __init__(self, roles):
            self._roles = {role: set(users) for role, users in roles.items()}

        def has_role(self, user, role):
            return user in self._roles.get(role, ())

        def holders(self, role):
            return sorted(self._roles.get(role, ()))
''')

APPROVALFLOW_ENGINE = dd('''
    """The approval engine."""
    from .rules import stages_for
    from .states import next_state


    class Request:
        def __init__(self, request_id, requester, amount, created):
            self.id = request_id
            self.requester = requester
            self.amount = amount
            self.created = created
            self.stages = stages_for(amount)
            self.state = "draft"
            self.approvals = []
            self.submitted_at = None
            self.reason = None
            self.history = []

        def pending(self):
            for role, needed in self.stages:
                got = sum(1 for _, r, _ in self.approvals if r == role)
                if got < needed:
                    return (role, needed, got)
            return None


    class Engine:
        def __init__(self, directory, ttl=72):
            self.directory = directory
            self.ttl = ttl

        def _require_pending_role(self, request, user):
            role = request.pending()[0]
            if not self.directory.has_role(user, role):
                raise PermissionError(f"{user} does not hold the {role} role")

        def submit(self, request, user, now):
            state = next_state(request.state, "submit")
            if user != request.requester:
                raise PermissionError("only the requester can submit")
            request.state = state
            request.submitted_at = now
            request.history.append(("submit", user, now))

        def approve(self, request, user, now):
            state = next_state(request.state, "approve")
            if user == request.requester:
                raise PermissionError("requesters cannot approve their own request")
            if any(u == user for u, _, _ in request.approvals):
                raise ValueError(f"{user} already approved this request")
            self._require_pending_role(request, user)
            role = request.pending()[0]
            request.approvals.append((user, role, now))
            request.history.append(("approve", user, now))
            if request.pending() is None:
                request.state = state
            return request.state

        def reject(self, request, user, now, reason):
            state = next_state(request.state, "reject")
            self._require_pending_role(request, user)
            if not reason or not reason.strip():
                raise ValueError("a reason is required")
            request.state = state
            request.reason = reason
            request.history.append(("reject", user, now))

        def send_back(self, request, user, now):
            state = next_state(request.state, "send_back")
            self._require_pending_role(request, user)
            request.state = state
            request.approvals = []
            request.submitted_at = None
            request.history.append(("send_back", user, now))

        def withdraw(self, request, user):
            state = next_state(request.state, "withdraw")
            if user != request.requester:
                raise PermissionError("only the requester can withdraw")
            request.state = state
            request.history.append(("withdraw", user, None))

        def expire_overdue(self, requests, now):
            expired = []
            for request in requests:
                if request.state == "submitted" and now - request.submitted_at >= self.ttl:
                    request.state = next_state(request.state, "expire")
                    request.history.append(("expire", None, now))
                    expired.append(request.id)
            return expired
''')

APPROVALFLOW_VISIBLE = dd('''
    import unittest

    from approvalflow.engine import Engine, Request
    from approvalflow.rules import Directory, stages_for
    from approvalflow.states import next_state


    class BasicTests(unittest.TestCase):
        def test_stages(self):
            self.assertEqual(stages_for(300), [("manager", 1)])

        def test_transition(self):
            self.assertEqual(next_state("draft", "submit"), "submitted")

        def test_small_request_is_approved_by_a_manager(self):
            eng = Engine(Directory({"manager": ["mia"]}))
            r = Request("r1", "rex", 300, 0)
            eng.submit(r, "rex", 1)
            self.assertEqual(eng.approve(r, "mia", 2), "approved")


    if __name__ == "__main__":
        unittest.main()
''')

APPROVALFLOW_HIDDEN_STATES = dd('''
    import unittest

    from approvalflow.rules import Directory, stages_for
    from approvalflow.states import FINAL, IllegalTransition, is_final, next_state


    class States(unittest.TestCase):
        def test_legal_transitions(self):
            table = {
                ("draft", "submit"): "submitted", ("draft", "withdraw"): "withdrawn",
                ("submitted", "approve"): "approved", ("submitted", "reject"): "rejected",
                ("submitted", "send_back"): "draft", ("submitted", "withdraw"): "withdrawn",
                ("submitted", "expire"): "expired",
            }
            for (state, action), want in table.items():
                self.assertEqual(next_state(state, action), want)

        def test_illegal_transitions(self):
            bad = [
                ("draft", "approve"), ("draft", "reject"), ("draft", "send_back"), ("draft", "expire"),
                ("submitted", "submit"), ("approved", "withdraw"), ("rejected", "submit"), ("withdrawn", "submit"),
                ("expired", "approve"), ("approved", "reject"), ("nonsense", "submit"), ("draft", "teleport"),
            ]
            for state, action in bad:
                with self.assertRaises(IllegalTransition, msg=(state, action)):
                    next_state(state, action)

        def test_illegal_transition_is_a_value_error(self):
            self.assertTrue(issubclass(IllegalTransition, ValueError))

        def test_final_states(self):
            self.assertEqual(set(FINAL), {"approved", "rejected", "withdrawn", "expired"})
            for s in ("approved", "rejected", "withdrawn", "expired"):
                self.assertTrue(is_final(s))
            for s in ("draft", "submitted"):
                self.assertFalse(is_final(s))


    class Stages(unittest.TestCase):
        def test_bands(self):
            cases = {
                1: [("manager", 1)], 500: [("manager", 1)],
                501: [("manager", 1), ("finance", 1)], 5000: [("manager", 1), ("finance", 1)],
                5001: [("manager", 1), ("finance", 1), ("director", 1)],
                20000: [("manager", 1), ("finance", 1), ("director", 1)],
                20001: [("manager", 1), ("finance", 2), ("director", 1)],
                10 ** 7: [("manager", 1), ("finance", 2), ("director", 1)],
            }
            for amount, want in cases.items():
                self.assertEqual(stages_for(amount), want, amount)

        def test_bad_amount(self):
            for amount in (0, -5):
                with self.assertRaises(ValueError):
                    stages_for(amount)


    class DirectoryTests(unittest.TestCase):
        def test_roles(self):
            d = Directory({"manager": ["mia", "max"], "finance": ("fay",)})
            self.assertTrue(d.has_role("mia", "manager"))
            self.assertFalse(d.has_role("mia", "finance"))
            self.assertFalse(d.has_role("mia", "ghost"))
            self.assertEqual(d.holders("manager"), ["max", "mia"])
            self.assertEqual(d.holders("ghost"), [])

        def test_input_is_copied(self):
            roles = {"manager": ["mia"]}
            d = Directory(roles)
            roles["manager"].append("max")
            roles["finance"] = ["fay"]
            self.assertFalse(d.has_role("max", "manager"))
            self.assertFalse(d.has_role("fay", "finance"))


    if __name__ == "__main__":
        unittest.main()
''')

APPROVALFLOW_HIDDEN_ENGINE = dd('''
    import unittest

    from approvalflow.engine import Engine, Request
    from approvalflow.rules import Directory
    from approvalflow.states import IllegalTransition

    DIR = Directory({
        "manager": ["mia", "max"], "finance": ["fay", "fin", "max"], "director": ["dina"],
    })


    def engine(ttl=72):
        return Engine(DIR, ttl=ttl)


    def submitted(amount, requester="rex", rid="r"):
        eng = engine()
        r = Request(rid, requester, amount, 0)
        eng.submit(r, requester, 10)
        return eng, r


    class RequestTests(unittest.TestCase):
        def test_initial_state(self):
            r = Request("r1", "rex", 4000, 3)
            self.assertEqual((r.id, r.requester, r.amount, r.created), ("r1", "rex", 4000, 3))
            self.assertEqual((r.state, r.approvals, r.submitted_at, r.reason, r.history), ("draft", [], None, None, []))
            self.assertEqual(r.stages, [("manager", 1), ("finance", 1)])
            self.assertEqual(r.pending(), ("manager", 1, 0))

        def test_bad_amount(self):
            with self.assertRaises(ValueError):
                Request("r1", "rex", 0, 0)


    class Submit(unittest.TestCase):
        def test_submit(self):
            eng = engine()
            r = Request("r", "rex", 100, 0)
            eng.submit(r, "rex", 10)
            self.assertEqual((r.state, r.submitted_at), ("submitted", 10))
            self.assertEqual(r.history, [("submit", "rex", 10)])

        def test_only_requester_submits(self):
            eng = engine()
            r = Request("r", "rex", 100, 0)
            with self.assertRaises(PermissionError):
                eng.submit(r, "mia", 10)
            self.assertEqual((r.state, r.submitted_at, r.history), ("draft", None, []))

        def test_twice_is_illegal(self):
            eng, r = submitted(100)
            with self.assertRaises(IllegalTransition):
                eng.submit(r, "rex", 11)

        def test_illegal_transition_is_reported_before_permissions(self):
            eng, r = submitted(100)
            with self.assertRaises(IllegalTransition):
                eng.submit(r, "someone-else", 11)


    class Approve(unittest.TestCase):
        def test_small_request(self):
            eng, r = submitted(300)
            self.assertEqual(eng.approve(r, "mia", 12), "approved")
            self.assertEqual(r.state, "approved")
            self.assertEqual(r.approvals, [("mia", "manager", 12)])
            self.assertIsNone(r.pending())
            self.assertEqual(r.history[-1], ("approve", "mia", 12))

        def test_two_stages_in_order(self):
            eng, r = submitted(4000)
            with self.assertRaises(PermissionError):
                eng.approve(r, "fay", 11)
            self.assertEqual(r.approvals, [])
            self.assertEqual(eng.approve(r, "mia", 12), "submitted")
            self.assertEqual(r.pending(), ("finance", 1, 0))
            with self.assertRaises(PermissionError):
                eng.approve(r, "dina", 13)
            self.assertEqual(eng.approve(r, "fay", 14), "approved")
            self.assertEqual(r.approvals, [("mia", "manager", 12), ("fay", "finance", 14)])

        def test_quorum_of_two(self):
            eng, r = submitted(30000)
            eng.approve(r, "mia", 11)
            self.assertEqual(eng.approve(r, "fay", 12), "submitted")
            self.assertEqual(r.pending(), ("finance", 2, 1))
            with self.assertRaises(ValueError):
                eng.approve(r, "fay", 13)
            self.assertEqual(eng.approve(r, "fin", 14), "submitted")
            self.assertEqual(r.pending(), ("director", 1, 0))
            with self.assertRaises(PermissionError):
                eng.approve(r, "max", 15)     # a manager and a finance person, but not a director
            self.assertEqual(eng.approve(r, "dina", 16), "approved")
            self.assertEqual(len(r.approvals), 4)

        def test_requester_cannot_approve_own_request(self):
            eng, r = submitted(100, requester="mia")
            with self.assertRaises(PermissionError):
                eng.approve(r, "mia", 11)
            self.assertEqual(r.state, "submitted")

        def test_self_approval_is_checked_before_role(self):
            eng, r = submitted(100, requester="zed")
            with self.assertRaises(PermissionError):
                eng.approve(r, "zed", 11)

        def test_duplicate_approval_is_a_value_error(self):
            eng, r = submitted(4000)
            eng.approve(r, "max", 11)     # max is a manager and also in finance
            self.assertEqual(r.pending(), ("finance", 1, 0))
            with self.assertRaises(ValueError) as cm:
                eng.approve(r, "max", 12)
            self.assertNotIsInstance(cm.exception, PermissionError)
            self.assertEqual(eng.approve(r, "fay", 13), "approved")

        def test_duplicate_is_checked_before_role(self):
            eng, r = submitted(300)
            eng2, r2 = submitted(4000)
            eng2.approve(r2, "mia", 11)
            with self.assertRaises(ValueError):
                eng2.approve(r2, "mia", 12)

        def test_approve_draft_or_final(self):
            eng = engine()
            r = Request("r", "rex", 100, 0)
            with self.assertRaises(IllegalTransition):
                eng.approve(r, "mia", 1)
            eng, r = submitted(100)
            eng.approve(r, "mia", 11)
            with self.assertRaises(IllegalTransition):
                eng.approve(r, "max", 12)


    class Reject(unittest.TestCase):
        def test_reject(self):
            eng, r = submitted(4000)
            eng.approve(r, "mia", 11)
            eng.reject(r, "fay", 12, "over budget")
            self.assertEqual((r.state, r.reason), ("rejected", "over budget"))
            self.assertEqual(r.history[-1], ("reject", "fay", 12))

        def test_only_pending_role_may_reject(self):
            eng, r = submitted(4000)
            with self.assertRaises(PermissionError):
                eng.reject(r, "fay", 11, "no")
            with self.assertRaises(PermissionError):
                eng.reject(r, "nobody", 11, "no")
            self.assertEqual(r.state, "submitted")

        def test_reason_required(self):
            eng, r = submitted(100)
            for reason in ("", "   ", "\\t\\n", None):
                with self.assertRaises(ValueError):
                    eng.reject(r, "mia", 11, reason)
            self.assertEqual(r.state, "submitted")
            self.assertIsNone(r.reason)

        def test_permission_checked_before_reason(self):
            eng, r = submitted(100)
            with self.assertRaises(PermissionError):
                eng.reject(r, "fay", 11, "")

        def test_not_in_draft(self):
            eng = engine()
            r = Request("r", "rex", 100, 0)
            with self.assertRaises(IllegalTransition):
                eng.reject(r, "mia", 1, "no")


    class SendBackAndWithdraw(unittest.TestCase):
        def test_send_back_and_resubmit(self):
            eng, r = submitted(4000)
            eng.approve(r, "mia", 11)
            eng.send_back(r, "fay", 12)
            self.assertEqual((r.state, r.approvals, r.submitted_at), ("draft", [], None))
            self.assertEqual(r.history[-1], ("send_back", "fay", 12))
            eng.submit(r, "rex", 20)
            self.assertEqual((r.state, r.submitted_at), ("submitted", 20))
            self.assertEqual(r.pending(), ("manager", 1, 0))
            self.assertEqual(eng.approve(r, "mia", 21), "submitted")

        def test_send_back_permissions(self):
            eng, r = submitted(4000)
            with self.assertRaises(PermissionError):
                eng.send_back(r, "fay", 11)
            self.assertEqual(r.state, "submitted")
            eng2 = engine()
            d = Request("d", "rex", 100, 0)
            with self.assertRaises(IllegalTransition):
                eng2.send_back(d, "mia", 1)

        def test_withdraw(self):
            eng = engine()
            d = Request("d", "rex", 100, 0)
            eng.withdraw(d, "rex")
            self.assertEqual(d.state, "withdrawn")
            self.assertEqual(d.history, [("withdraw", "rex", None)])
            eng, r = submitted(100)
            eng.withdraw(r, "rex")
            self.assertEqual(r.state, "withdrawn")

        def test_withdraw_permissions(self):
            eng, r = submitted(100)
            with self.assertRaises(PermissionError):
                eng.withdraw(r, "mia")
            self.assertEqual(r.state, "submitted")
            eng.approve(r, "mia", 12)
            with self.assertRaises(IllegalTransition):
                eng.withdraw(r, "rex")


    class Expiry(unittest.TestCase):
        def test_boundaries_and_selection(self):
            eng = engine(ttl=72)
            a, b, c, d = (Request(i, "rex", 100, 0) for i in "abcd")
            eng.submit(a, "rex", 10)      # expires at 82
            eng.submit(b, "rex", 12)      # expires at 84
            eng.submit(c, "rex", 10)
            eng.approve(c, "mia", 20)     # approved: never expires
            self.assertEqual(eng.expire_overdue([a, b, c, d], 81), [])
            self.assertEqual(eng.expire_overdue([a, b, c, d], 82), ["a"])
            self.assertEqual((a.state, b.state, c.state, d.state), ("expired", "submitted", "approved", "draft"))
            self.assertEqual(a.history[-1], ("expire", None, 82))
            self.assertEqual(eng.expire_overdue([d, b, a], 1000), ["b"])
            self.assertEqual((b.state, c.state, d.state), ("expired", "approved", "draft"))

        def test_order_follows_input(self):
            eng = engine(ttl=5)
            rs = [Request(i, "rex", 100, 0) for i in ("x", "y", "z")]
            for r in rs:
                eng.submit(r, "rex", 0)
            self.assertEqual(eng.expire_overdue([rs[2], rs[0], rs[1]], 5), ["z", "x", "y"])

        def test_custom_ttl_default(self):
            self.assertEqual(Engine(DIR).ttl, 72)
            self.assertEqual(Engine(DIR, ttl=5).ttl, 5)


    if __name__ == "__main__":
        unittest.main()
''')

_DIR = "Directory({'manager': ['mia', 'max'], 'finance': ['fay', 'fin', 'max'], 'director': ['dina']})"
_SUB = "e.submit(r, r.requester, 10)"


def flow(amount, calls, requester="rex"):
    """A probe expression: an engine and one request go through a list of calls, every result is reported."""
    items = ", ".join(calls)
    return f"(lambda e, r: [{items}])(Engine({_DIR}), Request('r1', {requester!r}, {amount}, 0))"


APPROVALFLOW = Lib(
    name="approvalflow", lang="python", title="the approvalflow purchase-request workflow",
    blurb="The procurement portal uses approvalflow to route purchase requests through the right approvers and to expire stale ones.",
    files={
        "approvalflow/__init__.py": "", "approvalflow/states.py": APPROVALFLOW_STATES, "approvalflow/rules.py": APPROVALFLOW_RULES,
        "approvalflow/engine.py": APPROVALFLOW_ENGINE, "README.md": APPROVALFLOW_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": APPROVALFLOW_VISIBLE},
    hidden_tests={
        "tests/test_states.py": APPROVALFLOW_HIDDEN_STATES, "tests/test_engine.py": APPROVALFLOW_HIDDEN_ENGINE,
    },
    mutate=["approvalflow/states.py", "approvalflow/rules.py", "approvalflow/engine.py"],
    difficulty=3, tags=["workflow", "state-machine", "multi-module"],
    probes=[
        "[stages_for(n) for n in (500, 501, 5000, 5001, 20000, 20001)]",
        "next_state('submitted', 'send_back')", "is_final('expired')",
        flow(4000, [_SUB, "e.approve(r, 'mia', 11)", "r.pending()", "e.approve(r, 'fay', 12)", "r.state"]),
        flow(30000, [_SUB, "e.approve(r, 'mia', 11)", "e.approve(r, 'fay', 12)", "r.pending()", "e.approve(r, 'fin', 13)", "r.pending()", "e.approve(r, 'dina', 14)"]),
        flow(100, [_SUB, "e.reject(r, 'mia', 11, 'too pricey')", "r.state", "r.reason", "r.history"]),
        flow(4000, [_SUB, "e.approve(r, 'mia', 11)", "e.send_back(r, 'fay', 12)", "r.state", "r.approvals", "r.submitted_at"]),
        flow(100, [_SUB, "e.expire_overdue([r], 81)", "e.expire_overdue([r], 82)", "r.state"]),
        flow(4000, [_SUB, "e.approve(r, 'max', 11)", "e.approve(r, 'max', 12)"]),
        flow(100, [_SUB, "e.approve(r, 'mia', 11)"], requester="mia"),
        flow(100, ["e.submit(r, 'zed', 10)"]),
        flow(100, [_SUB, "e.withdraw(r, 'rex')", "r.state", "r.history"]),
    ],
    probe_import=(
        "from approvalflow.engine import Engine, Request\n"
        "from approvalflow.rules import Directory, stages_for\nfrom approvalflow.states import next_state, is_final\n"
    ),
)

# ======================================================================================================================
# rulebook: a small forward-chaining rule engine
# ======================================================================================================================

RULEBOOK_README = dd('''
    # rulebook

    A small forward-chaining rule engine that a shop uses to derive shipping, discounts and notes from an order. The
    order is a dict of *facts*; rules look at the facts and change them.

    ## Rules

    `Rule(name, when, then, salience=0)`:

    * `name`: a non-empty string.
    * `when`: a list of conditions, all of which must hold. A condition is a tuple `(field, op, value)` or, for the
      ops `exists` and `missing`, `(field, op)`. Ops: `==`, `!=`, `<`, `<=`, `>`, `>=` (compare the fact with the
      value), `in` (the fact is a member of the list `value`), `contains` (`value` is a member of the fact, which is
      a list or a string), `exists` (the field is present) and `missing` (it is absent). Every op except `missing`
      is **false** when the field is absent (this includes `!=`), and a comparison that Python cannot evaluate
      (`TypeError`, e.g. `"a" < 3`) is false.
    * `then`: a list of actions, performed in order: `("set", field, value)`, `("unset", field)` (no error when the
      field is absent), `("add", field, number)` (an absent field counts as `0`), `("append", field, value)` (an
      absent field becomes a new list) and `("tag", name)` (append `name` to the list in the field `tags` unless it
      is already there; the list is created when absent).
    * `salience`: an integer; higher fires first.

    `Rule(...)` raises `ValueError` for an empty or non-string name, a condition or action of an unknown kind or the
    wrong length, a non-list `when` or `then`, an empty `when`, or a salience that is not an `int`.
    `rule_from_dict(d) -> Rule` builds a rule from a dict with the keys `name`, `when`, `then` and optionally
    `salience`; lists inside may be lists instead of tuples. Any other key, or a missing required key, is a
    `ValueError`.

    ## `Engine(rules)`

    `ValueError` if two rules share a name.

    * `eligible(facts, fired=()) -> list[str]`: the names of the rules not in `fired` whose conditions all hold,
      ordered by salience (highest first) and, for equal salience, by the order of the rules in the engine.
    * `run(facts) -> (facts, trace)`: works on a deep copy (the argument is never changed). Repeatedly: take the
      first name of `eligible(facts, fired)`, perform that rule's actions, mark it as fired, and stop when nothing
      is eligible. Every rule fires at most once. Returns the resulting facts and the list of fired rule names in
      firing order.
''')

RULEBOOK_SRC = dd('''
    """A small forward-chaining rule engine."""
    import copy

    OPS = ("==", "!=", "<", "<=", ">", ">=", "in", "contains", "exists", "missing")
    ACTION_LENGTHS = {"set": 3, "unset": 2, "add": 3, "append": 3, "tag": 2}


    def _check_condition(cond):
        if not isinstance(cond, (tuple, list)) or len(cond) < 2 or not isinstance(cond[0], str):
            raise ValueError(f"bad condition {cond!r}")
        if cond[1] not in OPS:
            raise ValueError(f"unknown operator {cond[1]!r}")
        want = 2 if cond[1] in ("exists", "missing") else 3
        if len(cond) != want:
            raise ValueError(f"operator {cond[1]!r} takes {want - 1} operands")
        return tuple(cond)


    def _check_action(act):
        if not isinstance(act, (tuple, list)) or not act or act[0] not in ACTION_LENGTHS:
            raise ValueError(f"unknown action {act!r}")
        if len(act) != ACTION_LENGTHS[act[0]]:
            raise ValueError(f"action {act[0]!r} takes {ACTION_LENGTHS[act[0]] - 1} operands")
        return tuple(act)


    class Rule:
        def __init__(self, name, when, then, salience=0):
            if not isinstance(name, str) or not name:
                raise ValueError("a rule needs a name")
            if not isinstance(when, (list, tuple)) or not when or not isinstance(then, (list, tuple)):
                raise ValueError("when must be a non-empty list and then a list")
            if isinstance(salience, bool) or not isinstance(salience, int):
                raise ValueError("salience must be an int")
            self.name = name
            self.when = [_check_condition(c) for c in when]
            self.then = [_check_action(a) for a in then]
            self.salience = salience


    def rule_from_dict(d):
        extra = set(d) - {"name", "when", "then", "salience"}
        if extra:
            raise ValueError(f"unknown keys {sorted(extra)}")
        if not {"name", "when", "then"} <= set(d):
            raise ValueError("name, when and then are required")
        return Rule(d["name"], d["when"], d["then"], d.get("salience", 0))


    def _holds(facts, cond):
        field, op = cond[0], cond[1]
        if op == "exists":
            return field in facts
        if op == "missing":
            return field not in facts
        if field not in facts:
            return False
        left, right = facts[field], cond[2]
        try:
            if op == "==":
                return left == right
            if op == "!=":
                return left != right
            if op == "<":
                return left < right
            if op == "<=":
                return left <= right
            if op == ">":
                return left > right
            if op == ">=":
                return left >= right
            if op == "in":
                return left in right
            return right in left
        except TypeError:
            return False


    def _perform(facts, act):
        kind = act[0]
        if kind == "set":
            facts[act[1]] = copy.deepcopy(act[2])
        elif kind == "unset":
            facts.pop(act[1], None)
        elif kind == "add":
            facts[act[1]] = facts.get(act[1], 0) + act[2]
        elif kind == "append":
            facts.setdefault(act[1], []).append(copy.deepcopy(act[2]))
        else:
            tags = facts.setdefault("tags", [])
            if act[1] not in tags:
                tags.append(act[1])


    class Engine:
        def __init__(self, rules):
            names = [r.name for r in rules]
            if len(set(names)) != len(names):
                raise ValueError("duplicate rule name")
            self.rules = list(rules)

        def eligible(self, facts, fired=()):
            order = sorted(range(len(self.rules)), key=lambda i: (-self.rules[i].salience, i))
            return [
                self.rules[i].name for i in order
                if self.rules[i].name not in fired and all(_holds(facts, c) for c in self.rules[i].when)
            ]

        def run(self, facts):
            facts = copy.deepcopy(facts)
            by_name = {r.name: r for r in self.rules}
            fired, trace = set(), []
            while True:
                names = self.eligible(facts, fired)
                if not names:
                    return facts, trace
                rule = by_name[names[0]]
                for act in rule.then:
                    _perform(facts, act)
                fired.add(rule.name)
                trace.append(rule.name)
''')

RULEBOOK_VISIBLE = dd('''
    import unittest

    from rulebook.engine import Engine, Rule


    class BasicTests(unittest.TestCase):
        def test_fires_matching_rule(self):
            eng = Engine([Rule("big", [("total", ">=", 100)], [("set", "free", True)])])
            facts, trace = eng.run({"total": 150})
            self.assertEqual(facts, {"total": 150, "free": True})
            self.assertEqual(trace, ["big"])


    if __name__ == "__main__":
        unittest.main()
''')

RULEBOOK_HIDDEN = dd('''
    import unittest

    from rulebook.engine import Engine, Rule, rule_from_dict


    def R(name, when, then=(("tag", "x"),), salience=0):
        return Rule(name, list(when), list(then), salience)


    SHOP = [
        Rule("free-ship", [("total", ">=", 5000), ("country", "in", ["DE", "FR"])],
             [("set", "ship", 0), ("tag", "free")], salience=10),
        Rule("base-ship", [("ship", "missing")], [("set", "ship", 700)]),
        Rule("bulk", [("items", "contains", "b")], [("add", "discount", 100)], salience=5),
        Rule("note", [("tags", "contains", "free")], [("append", "notes", "free shipping applied")], salience=1),
    ]


    class Conditions(unittest.TestCase):
        def holds(self, cond, facts):
            return Engine([R("r", [cond])]).eligible(facts) == ["r"]

        def test_comparisons(self):
            f = {"n": 5}
            table = [
                (("n", "==", 5), True), (("n", "==", 6), False), (("n", "!=", 6), True), (("n", "!=", 5), False),
                (("n", "<", 6), True), (("n", "<", 5), False), (("n", "<=", 5), True), (("n", "<=", 4), False),
                (("n", ">", 4), True), (("n", ">", 5), False), (("n", ">=", 5), True), (("n", ">=", 6), False),
            ]
            for cond, want in table:
                self.assertEqual(self.holds(cond, f), want, cond)

        def test_in_and_contains(self):
            self.assertTrue(self.holds(("c", "in", ["DE", "FR"]), {"c": "FR"}))
            self.assertFalse(self.holds(("c", "in", ["DE", "FR"]), {"c": "US"}))
            self.assertTrue(self.holds(("items", "contains", "b"), {"items": ["a", "b"]}))
            self.assertFalse(self.holds(("items", "contains", "c"), {"items": ["a", "b"]}))
            self.assertTrue(self.holds(("name", "contains", "ell"), {"name": "hello"}))
            self.assertFalse(self.holds(("name", "contains", "z"), {"name": "hello"}))

        def test_exists_and_missing(self):
            self.assertTrue(self.holds(("x", "exists"), {"x": None}))
            self.assertFalse(self.holds(("x", "exists"), {}))
            self.assertTrue(self.holds(("x", "missing"), {}))
            self.assertFalse(self.holds(("x", "missing"), {"x": 0}))

        def test_absent_field_is_false_for_everything_but_missing(self):
            for op, val in (("==", 1), ("!=", 1), ("<", 1), ("<=", 1), (">", 1), (">=", 1), ("in", [1]), ("contains", 1)):
                self.assertFalse(self.holds(("zz", op, val), {"other": 1}), op)

        def test_type_errors_are_false(self):
            self.assertFalse(self.holds(("a", "<", 3), {"a": "text"}))
            self.assertFalse(self.holds(("a", ">=", "x"), {"a": 3}))
            self.assertFalse(self.holds(("a", "in", 5), {"a": 3}))
            self.assertFalse(self.holds(("a", "contains", "x"), {"a": 3}))

        def test_all_conditions_needed(self):
            r = R("r", [("a", ">", 1), ("b", "<", 5)])
            self.assertEqual(Engine([r]).eligible({"a": 2, "b": 4}), ["r"])
            self.assertEqual(Engine([r]).eligible({"a": 2, "b": 5}), [])
            self.assertEqual(Engine([r]).eligible({"a": 1, "b": 4}), [])
            self.assertEqual(Engine([r]).eligible({"a": 2}), [])


    class Actions(unittest.TestCase):
        def run_one(self, act, facts):
            return Engine([R("r", [("go", "exists")], [act])]).run(dict(facts, go=1))[0]

        def test_set_unset(self):
            self.assertEqual(self.run_one(("set", "x", [1, 2]), {}), {"go": 1, "x": [1, 2]})
            self.assertEqual(self.run_one(("set", "x", 2), {"x": 1}), {"go": 1, "x": 2})
            self.assertEqual(self.run_one(("unset", "x"), {"x": 1, "y": 2}), {"go": 1, "y": 2})
            self.assertEqual(self.run_one(("unset", "nope"), {"y": 2}), {"go": 1, "y": 2})

        def test_add(self):
            self.assertEqual(self.run_one(("add", "n", 5), {}), {"go": 1, "n": 5})
            self.assertEqual(self.run_one(("add", "n", 5), {"n": 10}), {"go": 1, "n": 15})
            self.assertEqual(self.run_one(("add", "n", -3), {"n": 1}), {"go": 1, "n": -2})
            self.assertEqual(self.run_one(("add", "n", 0), {"n": 4}), {"go": 1, "n": 4})

        def test_append(self):
            self.assertEqual(self.run_one(("append", "l", "a"), {}), {"go": 1, "l": ["a"]})
            self.assertEqual(self.run_one(("append", "l", "b"), {"l": ["a"]}), {"go": 1, "l": ["a", "b"]})
            self.assertEqual(self.run_one(("append", "l", "a"), {"l": ["a"]}), {"go": 1, "l": ["a", "a"]})

        def test_tag(self):
            self.assertEqual(self.run_one(("tag", "t"), {}), {"go": 1, "tags": ["t"]})
            self.assertEqual(self.run_one(("tag", "t"), {"tags": ["a"]}), {"go": 1, "tags": ["a", "t"]})
            self.assertEqual(self.run_one(("tag", "t"), {"tags": ["t", "a"]}), {"go": 1, "tags": ["t", "a"]})

        def test_actions_run_in_order(self):
            eng = Engine([R("r", [("go", "exists")], [("set", "n", 1), ("add", "n", 2), ("unset", "go"), ("set", "go", 9)])])
            self.assertEqual(eng.run({"go": 1})[0], {"n": 3, "go": 9})

        def test_values_are_copied(self):
            payload = [1, 2]
            eng = Engine([R("r", [("go", "exists")], [("set", "a", payload), ("append", "b", payload)])])
            facts, _ = eng.run({"go": 1})
            facts["a"].append(99)
            facts["b"][0].append(98)
            self.assertEqual(payload, [1, 2])


    class Running(unittest.TestCase):
        def test_shop_with_free_shipping(self):
            facts, trace = Engine(SHOP).run({"total": 6000, "country": "DE", "items": ["a", "b"]})
            self.assertEqual(trace, ["free-ship", "bulk", "note"])
            self.assertEqual(facts, {
                "total": 6000, "country": "DE", "items": ["a", "b"], "ship": 0, "tags": ["free"],
                "discount": 100, "notes": ["free shipping applied"],
            })

        def test_shop_without_free_shipping(self):
            facts, trace = Engine(SHOP).run({"total": 100, "country": "US", "items": ["b"]})
            self.assertEqual(trace, ["bulk", "base-ship"])
            self.assertEqual(facts["ship"], 700)
            self.assertEqual(facts["discount"], 100)
            self.assertNotIn("tags", facts)

        def test_input_is_not_modified(self):
            facts = {"total": 6000, "country": "DE", "items": ["b"]}
            Engine(SHOP).run(facts)
            self.assertEqual(facts, {"total": 6000, "country": "DE", "items": ["b"]})

        def test_nothing_fires(self):
            self.assertEqual(Engine([]).run({"a": 1}), ({"a": 1}, []))
            facts, trace = Engine([R("r", [("a", ">", 5)])]).run({"a": 1})
            self.assertEqual((facts, trace), ({"a": 1}, []))

        def test_each_rule_fires_once(self):
            eng = Engine([R("count", [("n", ">=", 0)], [("add", "n", 1)])])
            self.assertEqual(eng.run({"n": 0}), ({"n": 1}, ["count"]))

        def test_chaining(self):
            eng = Engine([
                R("c", [("b", "exists")], [("set", "c", 1)]),
                R("b", [("a", "exists")], [("set", "b", 1)]),
                R("a", [("start", "exists")], [("set", "a", 1)]),
            ])
            facts, trace = eng.run({"start": 0})
            self.assertEqual(trace, ["a", "b", "c"])
            self.assertEqual(facts, {"start": 0, "a": 1, "b": 1, "c": 1})

        def test_a_rule_can_disable_another(self):
            eng = Engine([
                R("first", [("go", "exists")], [("unset", "go")], salience=5),
                R("second", [("go", "exists")], [("set", "second", 1)], salience=1),
            ])
            self.assertEqual(eng.run({"go": 1}), ({}, ["first"]))

        def test_salience_then_definition_order(self):
            eng = Engine([
                R("low", [("go", "exists")], [("append", "log", "low")], salience=1),
                R("high", [("go", "exists")], [("append", "log", "high")], salience=9),
                R("mid1", [("go", "exists")], [("append", "log", "mid1")], salience=5),
                R("mid2", [("go", "exists")], [("append", "log", "mid2")], salience=5),
                R("neg", [("go", "exists")], [("append", "log", "neg")], salience=-3),
            ])
            facts, trace = eng.run({"go": 1})
            self.assertEqual(trace, ["high", "mid1", "mid2", "low", "neg"])
            self.assertEqual(facts["log"], trace)
            self.assertEqual(eng.eligible({"go": 1}), trace)
            self.assertEqual(eng.eligible({"go": 1}, fired={"high", "low"}), ["mid1", "mid2", "neg"])
            self.assertEqual(eng.eligible({}), [])

        def test_default_salience_is_zero(self):
            eng = Engine([R("a", [("go", "exists")]), R("b", [("go", "exists")], salience=1), R("c", [("go", "exists")], salience=-1)])
            self.assertEqual(eng.eligible({"go": 1}), ["b", "a", "c"])


    class Validation(unittest.TestCase):
        def test_duplicate_names(self):
            with self.assertRaises(ValueError):
                Engine([R("a", [("x", "exists")]), R("a", [("y", "exists")])])

        def test_bad_rules(self):
            bad = [
                dict(name="", when=[("a", "exists")], then=[("tag", "t")]),
                dict(name=5, when=[("a", "exists")], then=[("tag", "t")]),
                dict(name="r", when=[], then=[("tag", "t")]),
                dict(name="r", when="a exists", then=[("tag", "t")]),
                dict(name="r", when=[("a", "exists")], then="tag"),
                dict(name="r", when=[("a", "~~", 1)], then=[("tag", "t")]),
                dict(name="r", when=[("a", "==")], then=[("tag", "t")]),
                dict(name="r", when=[("a", "exists", 1)], then=[("tag", "t")]),
                dict(name="r", when=[("a",)], then=[("tag", "t")]),
                dict(name="r", when=[(1, "exists")], then=[("tag", "t")]),
                dict(name="r", when=[("a", "exists")], then=[("explode", "t")]),
                dict(name="r", when=[("a", "exists")], then=[("set", "x")]),
                dict(name="r", when=[("a", "exists")], then=[("tag", "t", "u")]),
                dict(name="r", when=[("a", "exists")], then=[("unset", "x", 1)]),
                dict(name="r", when=[("a", "exists")], then=[()]),
                dict(name="r", when=[("a", "exists")], then=[("tag", "t")], salience="high"),
                dict(name="r", when=[("a", "exists")], then=[("tag", "t")], salience=1.5),
                dict(name="r", when=[("a", "exists")], then=[("tag", "t")], salience=True),
            ]
            for kw in bad:
                with self.assertRaises(ValueError, msg=str(kw)):
                    Rule(**kw)

        def test_empty_then_is_allowed(self):
            r = Rule("r", [("a", "exists")], [])
            self.assertEqual(Engine([r]).run({"a": 1}), ({"a": 1}, ["r"]))

        def test_rule_attributes(self):
            r = Rule("r", [["a", ">", 1]], [["set", "b", 2]], salience=4)
            self.assertEqual((r.name, r.when, r.then, r.salience), ("r", [("a", ">", 1)], [("set", "b", 2)], 4))
            self.assertEqual(Rule("q", [("a", "exists")], []).salience, 0)

        def test_rule_from_dict(self):
            r = rule_from_dict({"name": "n", "when": [["a", "<", 3], ["b", "missing"]], "then": [["add", "a", 1]], "salience": 7})
            self.assertEqual((r.name, r.when, r.then, r.salience), ("n", [("a", "<", 3), ("b", "missing")], [("add", "a", 1)], 7))
            r = rule_from_dict({"name": "n", "when": [["a", "exists"]], "then": []})
            self.assertEqual(r.salience, 0)

        def test_rule_from_dict_errors(self):
            for d in (
                {"name": "n", "when": [["a", "exists"]]}, {"when": [["a", "exists"]], "then": []}, {"name": "n", "then": []},
                {"name": "n", "when": [["a", "exists"]], "then": [], "color": "red"},
                {"name": "n", "when": [["a", "bad"]], "then": []},
            ):
                with self.assertRaises(ValueError, msg=str(d)):
                    rule_from_dict(d)


    if __name__ == "__main__":
        unittest.main()
''')

_RB = "Rule('free-ship', [('total', '>=', 5000), ('country', 'in', ['DE', 'FR'])], [('set', 'ship', 0), ('tag', 'free')], 10), Rule('base-ship', [('ship', 'missing')], [('set', 'ship', 700)]), Rule('bulk', [('items', 'contains', 'b')], [('add', 'discount', 100)], 5), Rule('note', [('tags', 'contains', 'free')], [('append', 'notes', 'free')], 1)"

RULEBOOK = Lib(
    name="rulebook", lang="python", title="the rulebook rule engine (`rulebook/engine.py`)",
    blurb="The shop's checkout service uses rulebook to derive shipping costs, discounts and order notes from the facts of an order.",
    files={"rulebook/__init__.py": "", "rulebook/engine.py": RULEBOOK_SRC, "README.md": RULEBOOK_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": RULEBOOK_VISIBLE},
    hidden_tests={"tests/test_full.py": RULEBOOK_HIDDEN},
    mutate=["rulebook/engine.py"], difficulty=3, tags=["rules", "engine"],
    probes=[
        f"Engine([{_RB}]).run({{'total': 6000, 'country': 'DE', 'items': ['a', 'b']}})",
        f"Engine([{_RB}]).run({{'total': 100, 'country': 'US', 'items': ['b']}})",
        "Engine([Rule('r', [('n', '!=', 1)], [('tag', 't')])]).run({})",
        "Engine([Rule('r', [('n', '<', 1)], [('tag', 't')])]).run({'n': 'x'})",
        "Engine([Rule('c', [('n', '>=', 0)], [('add', 'n', 1)])]).run({'n': 0})",
        "Engine([Rule('r', [('go', 'exists')], [('add', 'n', 5), ('tag', 't'), ('tag', 't')])]).run({'go': 1})",
        "Engine([Rule('r', [('go', 'exists')], [('append', 'l', 'a')])]).run({'go': 1, 'l': ['z']})",
        "Engine([Rule('a', [('go', 'exists')], [('tag', 'a')]), Rule('b', [('go', 'exists')], [('tag', 'b')], 1), Rule('c', [('go', 'exists')], [('tag', 'c')], -1)]).run({'go': 1})[1]",
        "Engine([Rule('first', [('go', 'exists')], [('unset', 'go')], 5), Rule('second', [('go', 'exists')], [('set', 's', 1)], 1)]).run({'go': 1})",
        "Rule('r', [['a', '>', 1]], [['set', 'b', 2]], salience=4).when",
    ],
    probe_import="from rulebook.engine import Engine, Rule, rule_from_dict\n",
)

# ======================================================================================================================
# basketcut: discount stacking at checkout (multi-module)
# ======================================================================================================================

BASKETCUT_README = dd('''
    # basketcut

    Checkout pricing for a small web shop: several promotions can apply to one basket and they must combine in a
    predictable way. All amounts are integer cents.

    ## `basketcut.money`

    * `round_div(n, d)`: `n / d` rounded half up (`ValueError` unless `n >= 0` and `d > 0`).
    * `pct_of(amount, pct)`: `pct` percent of `amount`, rounded half up (`round_div(amount * pct, 100)`).
      `ValueError` if `amount < 0` or `pct` is outside `0..100`.
    * `fmt(cents) -> str`: `"12.34"`; two decimals, a leading `-` for a negative amount, no thousands separators.

    ## `basketcut.promos`

    `Line(sku, unit, qty)` is a frozen dataclass with the property `total = unit * qty`. A promotion has a unique
    `code`, an optional exclusivity `group`, a `stackable` flag (default `True`) and an `amount(lines, running)`
    method: the discount it would give on the basket `lines` when `running` cents are still to be paid. All
    promotions are frozen dataclasses:

    * `Percent(code, pct, skus=None, min_subtotal=0, cap=None, group=None, stackable=True)`: `pct` percent of
      `min(running, eligible)` where `eligible` is the undiscounted total of the lines whose sku is in `skus` (every
      line when `skus is None`); rounded half up with `pct_of`; never more than `cap` when a cap is given.
    * `Fixed(code, off, min_subtotal=0, group=None, stackable=True)`: `min(off, running)`.
    * `BuyGet(code, sku, buy, get, min_subtotal=0, group=None, stackable=True)`: on every line with that sku, each
      complete set of `buy + get` units makes `get` units free: `(qty // (buy + get)) * get * unit` summed over such
      lines; never more than `running`.

    The class attribute `ORDER` is `0` for `BuyGet`, `1` for `Percent` and `2` for `Fixed`.

    ## `basketcut.checkout`

    `price(lines, promos, global_cap_pct=50) -> Quote` where `Quote` has `subtotal`, `applied` (list of
    `(code, amount)`), `discount` and `total`. `ValueError` for a line with `qty < 1` or `unit < 0`, duplicate promo
    codes, or a `global_cap_pct` outside `0..100`. The subtotal is the sum of the line totals. Then:

    1. A promotion is *eligible* when `subtotal >= min_subtotal` (the undiscounted subtotal).
    2. Within each non-`None` `group` only one eligible promotion survives: the one with the largest
       `amount(lines, subtotal)`, ties going to the smaller `code`.
    3. The surviving *stackable* promotions are applied one after another in order of `(ORDER, code)`; each one's
       amount is computed with `amount(lines, running)` where `running` starts at the subtotal and goes down by
       every applied amount; a promotion whose amount is `0` is left out of `applied`.
    4. If there are surviving non-stackable promotions, take the best one (largest `amount(lines, subtotal)`, ties
       to the smaller `code`). If its amount is **strictly greater** than the total discount of the stacked
       promotions, it replaces them: `applied` is just that promotion.
    5. The total discount may not exceed `subtotal * global_cap_pct // 100`. Walking through `applied` in order each
       amount is reduced to what the allowance still permits; entries that end up at `0` are dropped.
    6. `discount` is the sum of the final amounts and `total = subtotal - discount`.
''')

BASKETCUT_MONEY = dd('''
    """Integer money helpers."""


    def round_div(n: int, d: int) -> int:
        if d <= 0 or n < 0:
            raise ValueError("need n >= 0 and d > 0")
        return (2 * n + d) // (2 * d)


    def pct_of(amount: int, pct: int) -> int:
        if amount < 0 or not 0 <= pct <= 100:
            raise ValueError("amount must be >= 0 and pct within 0..100")
        return round_div(amount * pct, 100)


    def fmt(cents: int) -> str:
        sign = "-" if cents < 0 else ""
        whole, frac = divmod(abs(cents), 100)
        return f"{sign}{whole}.{frac:02d}"
''')

BASKETCUT_PROMOS = dd('''
    """Promotion types."""
    from dataclasses import dataclass
    from typing import ClassVar, Optional

    from .money import pct_of


    @dataclass(frozen=True)
    class Line:
        sku: str
        unit: int
        qty: int

        @property
        def total(self) -> int:
            return self.unit * self.qty


    @dataclass(frozen=True)
    class Percent:
        ORDER: ClassVar[int] = 1
        code: str
        pct: int
        skus: Optional[tuple] = None
        min_subtotal: int = 0
        cap: Optional[int] = None
        group: Optional[str] = None
        stackable: bool = True

        def amount(self, lines, running):
            eligible = sum(l.total for l in lines if self.skus is None or l.sku in self.skus)
            discount = pct_of(min(running, eligible), self.pct)
            return discount if self.cap is None else min(discount, self.cap)


    @dataclass(frozen=True)
    class Fixed:
        ORDER: ClassVar[int] = 2
        code: str
        off: int
        min_subtotal: int = 0
        group: Optional[str] = None
        stackable: bool = True

        def amount(self, lines, running):
            return min(self.off, running)


    @dataclass(frozen=True)
    class BuyGet:
        ORDER: ClassVar[int] = 0
        code: str
        sku: str
        buy: int
        get: int
        min_subtotal: int = 0
        group: Optional[str] = None
        stackable: bool = True

        def amount(self, lines, running):
            free = 0
            for l in lines:
                if l.sku == self.sku:
                    free += (l.qty // (self.buy + self.get)) * self.get * l.unit
            return min(free, running)
''')

BASKETCUT_CHECKOUT = dd('''
    """Combining promotions into a price."""
    from dataclasses import dataclass

    @dataclass
    class Quote:
        subtotal: int
        applied: list
        discount: int
        total: int


    def _stack(promos, lines, subtotal):
        running = subtotal
        out = []
        for promo in sorted(promos, key=lambda p: (p.ORDER, p.code)):
            amount = promo.amount(lines, running)
            if amount > 0:
                out.append((promo.code, amount))
                running -= amount
        return out


    def _best(promos, lines, subtotal):
        return min(promos, key=lambda p: (-p.amount(lines, subtotal), p.code))


    def price(lines, promos, global_cap_pct=50):
        lines = list(lines)
        if any(l.qty < 1 or l.unit < 0 for l in lines):
            raise ValueError("bad line")
        codes = [p.code for p in promos]
        if len(set(codes)) != len(codes):
            raise ValueError("duplicate promo code")
        if not 0 <= global_cap_pct <= 100:
            raise ValueError("global_cap_pct must be within 0..100")
        subtotal = sum(l.total for l in lines)
        eligible = [p for p in promos if subtotal >= p.min_subtotal]
        keep, groups = [], {}
        for p in eligible:
            if p.group is None:
                keep.append(p)
            else:
                groups.setdefault(p.group, []).append(p)
        for members in groups.values():
            keep.append(_best(members, lines, subtotal))
        applied = _stack([p for p in keep if p.stackable], lines, subtotal)
        solo = [p for p in keep if not p.stackable]
        if solo:
            best = _best(solo, lines, subtotal)
            amount = best.amount(lines, subtotal)
            if amount > sum(a for _, a in applied):
                applied = [(best.code, amount)]
        allowance = subtotal * global_cap_pct // 100
        final, used = [], 0
        for code, amount in applied:
            amount = min(amount, allowance - used)
            if amount > 0:
                final.append((code, amount))
                used += amount
        return Quote(subtotal, final, used, subtotal - used)
''')

BASKETCUT_VISIBLE = dd('''
    import unittest

    from basketcut.checkout import price
    from basketcut.money import fmt
    from basketcut.promos import Line, Percent


    class BasicTests(unittest.TestCase):
        def test_fmt(self):
            self.assertEqual(fmt(1234), "12.34")

        def test_percent(self):
            q = price([Line("a", 1000, 2)], [Percent("P10", 10)])
            self.assertEqual((q.subtotal, q.discount, q.total), (2000, 200, 1800))


    if __name__ == "__main__":
        unittest.main()
''')

BASKETCUT_HIDDEN_PROMOS = dd('''
    import unittest

    from basketcut.money import fmt, pct_of, round_div
    from basketcut.promos import BuyGet, Fixed, Line, Percent

    CART = [Line("A", 1000, 3), Line("B", 500, 2)]


    class Money(unittest.TestCase):
        def test_round_div(self):
            self.assertEqual(round_div(5, 2), 3)
            self.assertEqual(round_div(4, 3), 1)
            self.assertEqual(round_div(1, 3), 0)
            self.assertEqual(round_div(0, 7), 0)
            self.assertEqual(round_div(5, 1), 5)
            for args in ((1, 0), (1, -2), (-1, 2)):
                with self.assertRaises(ValueError):
                    round_div(*args)

        def test_pct_of(self):
            self.assertEqual(pct_of(70, 15), 11)       # 10.5 rounds up
            self.assertEqual(pct_of(69, 15), 10)       # 10.35
            self.assertEqual(pct_of(4000, 10), 400)
            self.assertEqual(pct_of(1, 50), 1)
            self.assertEqual(pct_of(99, 100), 99)
            self.assertEqual(pct_of(99, 0), 0)
            self.assertEqual(pct_of(0, 40), 0)
            for args in ((-1, 10), (100, -1), (100, 101)):
                with self.assertRaises(ValueError):
                    pct_of(*args)

        def test_fmt(self):
            self.assertEqual(fmt(0), "0.00")
            self.assertEqual(fmt(5), "0.05")
            self.assertEqual(fmt(1234), "12.34")
            self.assertEqual(fmt(100000), "1000.00")
            self.assertEqual(fmt(-5), "-0.05")
            self.assertEqual(fmt(-1234), "-12.34")


    class Lines(unittest.TestCase):
        def test_total_and_frozen(self):
            l = Line("A", 250, 3)
            self.assertEqual(l.total, 750)
            with self.assertRaises(Exception):
                l.qty = 1


    class PromoAmounts(unittest.TestCase):
        def test_percent(self):
            self.assertEqual(Percent("P", 10).amount(CART, 4000), 400)
            self.assertEqual(Percent("P", 10).amount(CART, 3000), 300)     # limited by what is left to pay
            self.assertEqual(Percent("P", 10).amount(CART, 5000), 400)     # never more than the lines are worth
            self.assertEqual(Percent("P", 10, skus=("B",)).amount(CART, 4000), 100)
            self.assertEqual(Percent("P", 10, skus=("B",)).amount(CART, 800), 80)
            self.assertEqual(Percent("P", 10, skus=("A", "B")).amount(CART, 4000), 400)
            self.assertEqual(Percent("P", 10, skus=("Z",)).amount(CART, 4000), 0)
            self.assertEqual(Percent("P", 50, cap=300).amount(CART, 4000), 300)
            self.assertEqual(Percent("P", 5, cap=300).amount(CART, 4000), 200)
            self.assertEqual(Percent("P", 50, cap=2000).amount(CART, 4000), 2000)
            self.assertEqual(Percent("P", 15).amount([Line("x", 70, 1)], 70), 11)

        def test_fixed(self):
            self.assertEqual(Fixed("F", 500).amount(CART, 4000), 500)
            self.assertEqual(Fixed("F", 500).amount(CART, 300), 300)
            self.assertEqual(Fixed("F", 500).amount(CART, 500), 500)
            self.assertEqual(Fixed("F", 500).amount(CART, 0), 0)

        def test_buy_get(self):
            self.assertEqual(BuyGet("B", "A", 2, 1).amount(CART, 4000), 1000)
            self.assertEqual(BuyGet("B", "A", 1, 1).amount(CART, 4000), 1000)
            self.assertEqual(BuyGet("B", "A", 3, 1).amount(CART, 4000), 0)
            self.assertEqual(BuyGet("B", "B", 1, 1).amount(CART, 4000), 500)
            self.assertEqual(BuyGet("B", "A", 1, 2).amount(CART, 4000), 2000)
            self.assertEqual(BuyGet("B", "Z", 1, 1).amount(CART, 4000), 0)
            self.assertEqual(BuyGet("B", "A", 2, 1).amount(CART, 600), 600)
            self.assertEqual(BuyGet("B", "A", 1, 1).amount([Line("A", 100, 5), Line("A", 200, 4)], 9999), 200 + 400)

        def test_defaults_and_order(self):
            p = Percent("P", 10)
            self.assertEqual((p.skus, p.min_subtotal, p.cap, p.group, p.stackable), (None, 0, None, None, True))
            self.assertEqual((BuyGet.ORDER, Percent.ORDER, Fixed.ORDER), (0, 1, 2))
            f = Fixed("F", 5)
            self.assertEqual((f.min_subtotal, f.group, f.stackable), (0, None, True))
            b = BuyGet("B", "A", 1, 1)
            self.assertEqual((b.min_subtotal, b.group, b.stackable), (0, None, True))
            with self.assertRaises(Exception):
                p.pct = 5
            with self.assertRaises(Exception):
                f.off = 1
            with self.assertRaises(Exception):
                b.get = 3


    if __name__ == "__main__":
        unittest.main()
''')

BASKETCUT_HIDDEN_CHECKOUT = dd('''
    import unittest

    from basketcut.checkout import price
    from basketcut.promos import BuyGet, Fixed, Line, Percent

    CART = [Line("A", 1000, 3), Line("B", 500, 2)]     # subtotal 4000


    class Basics(unittest.TestCase):
        def test_no_promos(self):
            q = price(CART, [])
            self.assertEqual((q.subtotal, q.applied, q.discount, q.total), (4000, [], 0, 4000))

        def test_empty_cart(self):
            q = price([], [Percent("P", 10), Fixed("F", 100)])
            self.assertEqual((q.subtotal, q.applied, q.discount, q.total), (0, [], 0, 0))

        def test_single_percent(self):
            q = price(CART, [Percent("P10", 10)])
            self.assertEqual((q.applied, q.discount, q.total), ([("P10", 400)], 400, 3600))

        def test_rounding(self):
            q = price([Line("x", 70, 1)], [Percent("R", 15)])
            self.assertEqual((q.applied, q.total), ([("R", 11)], 59))

        def test_validation(self):
            with self.assertRaises(ValueError):
                price([Line("a", 100, 0)], [])
            with self.assertRaises(ValueError):
                price([Line("a", -1, 1)], [])
            with self.assertRaises(ValueError):
                price(CART, [Percent("P", 5), Fixed("P", 5)])
            for cap in (-1, 101):
                with self.assertRaises(ValueError):
                    price(CART, [], global_cap_pct=cap)
            price([Line("a", 0, 1)], [], global_cap_pct=0)
            price(CART, [], global_cap_pct=100)

        def test_input_lists_are_not_modified(self):
            lines = list(CART)
            promos = [Fixed("F", 100), Percent("P", 10)]
            price(lines, promos)
            self.assertEqual(lines, CART)
            self.assertEqual([p.code for p in promos], ["F", "P"])


    class Stacking(unittest.TestCase):
        def test_application_order(self):
            promos = [Fixed("F5", 500), Percent("P10", 10), BuyGet("BG", "A", 2, 1)]
            q = price(CART, promos)
            # BuyGet first (1000, running 3000), then 10% of 3000 (300), then fixed 500
            self.assertEqual(q.applied, [("BG", 1000), ("P10", 300), ("F5", 500)])
            self.assertEqual((q.subtotal, q.discount, q.total), (4000, 1800, 2200))

        def test_codes_order_within_a_kind(self):
            q = price(CART, [Percent("B20", 20), Percent("A10", 10)])
            # A10 first: 400, running 3600; then 20% of min(3600, 4000) = 720
            self.assertEqual(q.applied, [("A10", 400), ("B20", 720)])

        def test_percent_skus_after_other_discounts(self):
            q = price(CART, [BuyGet("BG", "A", 2, 1), Percent("PB", 50, skus=("B",))])
            self.assertEqual(q.applied, [("BG", 1000), ("PB", 500)])

        def test_zero_amount_promos_are_left_out(self):
            q = price(CART, [Percent("P0", 0), Percent("PZ", 10, skus=("Z",)), BuyGet("BG", "A", 5, 1), Fixed("F", 0), Fixed("G", 50)])
            self.assertEqual(q.applied, [("G", 50)])

        def test_one_cent_counts(self):
            self.assertEqual(price(CART, [Fixed("ONE", 1)]).applied, [("ONE", 1)])
            q = price([Line("x", 3, 1)], [Fixed("F", 5)], global_cap_pct=50)
            self.assertEqual((q.applied, q.total), ([("F", 1)], 2))

        def test_fixed_cannot_go_below_zero(self):
            q = price([Line("x", 300, 1)], [Fixed("F", 500)], global_cap_pct=100)
            self.assertEqual((q.applied, q.total), ([("F", 300)], 0))

        def test_min_subtotal_boundary(self):
            f5 = Fixed("F5", 500, min_subtotal=4000)
            self.assertEqual(price(CART, [f5]).applied, [("F5", 500)])
            self.assertEqual(price([Line("A", 1000, 3), Line("B", 499, 2)], [Fixed("F5", 500, min_subtotal=3999)]).applied, [])
            self.assertEqual(price([Line("A", 1000, 3), Line("B", 500, 2)], [Fixed("F5", 500, min_subtotal=4001)]).applied, [])

        def test_min_subtotal_uses_the_undiscounted_subtotal(self):
            promos = [Percent("P50", 50), Fixed("F", 100, min_subtotal=3000)]
            q = price(CART, promos, global_cap_pct=100)
            self.assertEqual(q.applied, [("P50", 2000), ("F", 100)])


    class Groups(unittest.TestCase):
        def test_largest_in_group_wins(self):
            promos = [Percent("W10", 10, group="welcome"), Fixed("W500", 500, group="welcome")]
            q = price(CART, promos)
            self.assertEqual(q.applied, [("W500", 500)])
            promos = [Percent("W20", 20, group="welcome"), Fixed("W500", 500, group="welcome")]
            self.assertEqual(price(CART, promos).applied, [("W20", 800)])

        def test_tie_goes_to_the_smaller_code(self):
            promos = [Fixed("Z", 400, group="g"), Percent("A", 10, group="g")]
            self.assertEqual(price(CART, promos).applied, [("A", 400)])
            promos = [Fixed("A", 400, group="g"), Percent("Z", 10, group="g")]
            self.assertEqual(price(CART, promos).applied, [("A", 400)])

        def test_groups_are_independent_and_ungrouped_all_apply(self):
            promos = [
                Percent("G1A", 10, group="one"), Percent("G1B", 20, group="one"),
                Fixed("G2A", 100, group="two"), Fixed("G2B", 50, group="two"),
                Fixed("FREE", 25),
            ]
            q = price(CART, promos, global_cap_pct=100)
            self.assertEqual(q.applied, [("G1B", 800), ("FREE", 25), ("G2A", 100)])

        def test_group_choice_uses_the_original_subtotal(self):
            promos = [BuyGet("BG", "A", 2, 1), Percent("P30", 30, group="g"), Fixed("F900", 900, group="g")]
            q = price(CART, promos)
            # standalone on 4000: P30 = 1200, F900 = 900 -> P30 survives
            self.assertEqual([c for c, _ in q.applied], ["BG", "P30"])

        def test_group_members_must_be_eligible(self):
            promos = [Fixed("BIG", 900, min_subtotal=5000, group="g"), Fixed("SMALL", 100, group="g")]
            self.assertEqual(price(CART, promos).applied, [("SMALL", 100)])


    class NonStackable(unittest.TestCase):
        def test_solo_wins_when_strictly_better(self):
            promos = [Percent("P10", 10), Fixed("F5", 500), Percent("MEGA", 30, stackable=False)]
            q = price(CART, promos)
            # stack: 400 + 500 = 900; MEGA alone = 1200
            self.assertEqual((q.applied, q.discount), ([("MEGA", 1200)], 1200))

        def test_stack_wins_when_better_or_equal(self):
            promos = [Percent("P10", 10), Fixed("F5", 500), Percent("MEGA", 20, stackable=False)]
            q = price(CART, promos)
            self.assertEqual([c for c, _ in q.applied], ["P10", "F5"])
            self.assertEqual(q.discount, 900)
            promos = [Percent("P10", 10), Fixed("F5", 500), Fixed("EQ", 900, stackable=False)]
            self.assertEqual([c for c, _ in price(CART, promos).applied], ["P10", "F5"])
            promos = [Percent("P10", 10), Fixed("F5", 500), Fixed("EQ", 901, stackable=False)]
            self.assertEqual(price(CART, promos).applied, [("EQ", 901)])

        def test_best_solo_and_ties(self):
            promos = [Fixed("S2", 700, stackable=False), Fixed("S1", 900, stackable=False), Fixed("S3", 900, stackable=False)]
            self.assertEqual(price(CART, promos).applied, [("S1", 900)])
            promos = [Fixed("Z", 400, stackable=False), Percent("A", 10, stackable=False)]
            self.assertEqual(price(CART, promos).applied, [("A", 400)])

        def test_solo_with_nothing_else(self):
            q = price(CART, [Fixed("ONLY", 300, stackable=False)])
            self.assertEqual((q.applied, q.total), ([("ONLY", 300)], 3700))
            self.assertEqual(price(CART, [Fixed("ZERO", 0, stackable=False)]).applied, [])

        def test_solo_not_eligible(self):
            promos = [Fixed("P", 100), Fixed("BIG", 3000, min_subtotal=5000, stackable=False)]
            self.assertEqual(price(CART, promos).applied, [("P", 100)])

        def test_solo_group_interaction(self):
            promos = [Fixed("G1", 300, group="g", stackable=False), Fixed("G2", 200, group="g"), Percent("P10", 10)]
            q = price(CART, promos)
            # group keeps G1 (300, non-stackable); stack = P10 (400) beats it
            self.assertEqual(q.applied, [("P10", 400)])


    class GlobalCap(unittest.TestCase):
        def test_default_cap_is_half(self):
            q = price(CART, [Percent("A30", 30), Percent("B40", 40)])
            # A30: 1200 (running 2800); B40: 40% of min(2800, 4000) = 1120 -> total 2320, allowance 2000
            self.assertEqual(q.applied, [("A30", 1200), ("B40", 800)])
            self.assertEqual((q.discount, q.total), (2000, 2000))

        def test_later_entries_are_dropped(self):
            q = price(CART, [Percent("A60", 60), Fixed("B", 100)])
            self.assertEqual(q.applied, [("A60", 2000)])
            self.assertEqual(q.total, 2000)

        def test_custom_cap(self):
            q = price(CART, [Percent("P", 50)], global_cap_pct=10)
            self.assertEqual((q.applied, q.total), ([("P", 400)], 3600))
            q = price(CART, [Percent("P", 50)], global_cap_pct=100)
            self.assertEqual((q.applied, q.total), ([("P", 2000)], 2000))
            q = price(CART, [Percent("P", 50)], global_cap_pct=0)
            self.assertEqual((q.applied, q.discount, q.total), ([], 0, 4000))

        def test_allowance_is_floored(self):
            q = price([Line("x", 999, 1)], [Fixed("F", 999)], global_cap_pct=50)
            self.assertEqual(q.applied, [("F", 499)])
            self.assertEqual(q.total, 500)

        def test_exact_cap_keeps_everything(self):
            q = price(CART, [Percent("A", 25), Fixed("B", 1000)], global_cap_pct=50)
            # 25% of 4000 = 1000, then fixed 1000: total 2000 = allowance
            self.assertEqual(q.applied, [("A", 1000), ("B", 1000)])
            self.assertEqual(q.total, 2000)

        def test_cap_applies_to_a_solo_promo_too(self):
            q = price(CART, [Percent("MEGA", 90, stackable=False)])
            self.assertEqual(q.applied, [("MEGA", 2000)])


    if __name__ == "__main__":
        unittest.main()
''')

_BC = "[Line('A', 1000, 3), Line('B', 500, 2)]"

BASKETCUT = Lib(
    name="basketcut", lang="python", title="the basketcut checkout pricing package",
    blurb="The web shop's checkout calls basketcut to combine coupons, sale prices and buy-X-get-Y offers into one predictable price.",
    files={
        "basketcut/__init__.py": "", "basketcut/money.py": BASKETCUT_MONEY, "basketcut/promos.py": BASKETCUT_PROMOS,
        "basketcut/checkout.py": BASKETCUT_CHECKOUT, "README.md": BASKETCUT_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": BASKETCUT_VISIBLE},
    hidden_tests={"tests/test_promos.py": BASKETCUT_HIDDEN_PROMOS, "tests/test_checkout.py": BASKETCUT_HIDDEN_CHECKOUT},
    mutate=["basketcut/money.py", "basketcut/promos.py", "basketcut/checkout.py"],
    difficulty=3, tags=["pricing", "promotions", "multi-module"],
    probes=[
        "pct_of(70, 15)", "pct_of(99, 100)", "fmt(-5)",
        f"price({_BC}, [Fixed('F5', 500), Percent('P10', 10), BuyGet('BG', 'A', 2, 1)]).applied",
        f"price({_BC}, [Percent('B20', 20), Percent('A10', 10)]).applied",
        f"price({_BC}, [Percent('W10', 10, group='welcome'), Fixed('W500', 500, group='welcome')]).applied",
        f"price({_BC}, [Fixed('Z', 400, group='g'), Percent('A', 10, group='g')]).applied",
        f"price({_BC}, [Percent('P10', 10), Fixed('F5', 500), Percent('MEGA', 30, stackable=False)]).applied",
        f"price({_BC}, [Percent('P10', 10), Fixed('F5', 500), Fixed('EQ', 900, stackable=False)]).applied",
        f"price({_BC}, [Percent('A30', 30), Percent('B40', 40)])",
        f"price({_BC}, [Percent('PB', 50, skus=('B',)), BuyGet('BG', 'A', 2, 1)]).applied",
        f"price({_BC}, [Fixed('F', 500, min_subtotal=4001)]).applied",
        "price([Line('x', 999, 1)], [Fixed('F', 999)]).applied",
    ],
    probe_import="from basketcut.money import pct_of, fmt\nfrom basketcut.promos import Line, Percent, Fixed, BuyGet\nfrom basketcut.checkout import price\n",
)

LIBS = [ACLWALK, APPROVALFLOW, RULEBOOK, BASKETCUT]
register_libs3(LIBS, n=10)
