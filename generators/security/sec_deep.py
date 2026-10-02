"""Security family: deeper Python tasks where the flaw is a design problem, not one missing check (HTML sanitizer, authorization policy engine,
link builder / link validator, template sandbox). The agent has to replace a blacklist or a naive algorithm by a sound one and keep the documented behaviour."""
from fx import dd, family

from . import _sec
from ._sec import patched, readme

SC = []

# ---------------------------------------------------------------------------------------------------------------------------------
# HTML sanitizer for comments
SAN_START = dd(r'''
    """Comment sanitizer: turns user supplied HTML into the small subset of markup that comments may contain (see README.md)."""
    import re

    ALLOWED = {"b", "i", "em", "strong", "u", "p", "ul", "ol", "li", "blockquote", "code", "pre", "br", "a"}

    TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*)>")
    HREF = re.compile(r'href\s*=\s*"([^"]*)"', re.I)


    def sanitize(text):
        """Return `text` with every tag that is not in ALLOWED removed and dangerous link targets neutralised."""
        text = re.sub(r"<script.*?</script>", "", text, flags=re.S | re.I)
        text = re.sub(r"<style.*?</style>", "", text, flags=re.S | re.I)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)

        def tag(match):
            closing, name, attrs = match.groups()
            name = name.lower()
            if name not in ALLOWED:
                return ""
            if closing:
                return "</%s>" % name
            if name == "a":
                href = HREF.search(attrs)
                if not href:
                    return "<a>"
                url = href.group(1).replace("javascript:", "")
                return '<a href="%s" rel="nofollow noopener">' % url
            return "<%s>" % name

        return TAG.sub(tag, text)
''')

SAN_SOL = dd(r'''
    """Comment sanitizer: turns user supplied HTML into the small subset of markup that comments may contain (see README.md)."""
    import html
    import re
    from html.parser import HTMLParser

    ALLOWED = {"b", "i", "em", "strong", "u", "p", "ul", "ol", "li", "blockquote", "code", "pre", "a"}
    MAX_OPEN = 20
    SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*):")


    def safe_href(value):
        """http, https, mailto or a relative URL without a scheme (and not scheme-relative)."""
        if any(ord(c) < 32 or ord(c) == 127 or c == "\\" for c in value):
            return False
        value = value.strip()
        if not value:
            return False
        found = SCHEME.match(value)
        if found:
            return found.group(1).lower() in ("http", "https", "mailto")
        if value.startswith("//"):
            return False
        return ":" not in re.split(r"[/?#]", value, maxsplit=1)[0]


    class Sanitizer(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.out = []
            self.stack = []
            self.dropping = None

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self.dropping = tag
                return
            if self.dropping:
                return
            if tag == "br":
                self.out.append("<br>")
                return
            if tag not in ALLOWED or len(self.stack) >= MAX_OPEN:
                return
            if tag == "a":
                href = dict(attrs).get("href")
                if href is None or not safe_href(href):
                    return
                self.out.append('<a href="%s" rel="nofollow noopener">' % html.escape(href.strip(), quote=True))
            else:
                self.out.append("<%s>" % tag)
            self.stack.append(tag)

        def handle_endtag(self, tag):
            if self.dropping:
                if tag == self.dropping:
                    self.dropping = None
                return
            if tag not in self.stack:
                return
            while self.stack:
                top = self.stack.pop()
                self.out.append("</%s>" % top)
                if top == tag:
                    break

        def handle_data(self, data):
            if not self.dropping:
                self.out.append(html.escape(data, quote=False))

        def result(self):
            self.close()
            while self.stack:
                self.out.append("</%s>" % self.stack.pop())
            return "".join(self.out)


    def sanitize(text):
        """Return `text` reduced to the markup that comments may contain (see README.md)."""
        parser = Sanitizer()
        parser.feed(text)
        return parser.result()
''')

SAN_README = readme("comment sanitizer", r"""
`sanitize(text)` takes the HTML a user typed into the comment box and returns markup that is safe to put inside any element of a page; the comment page does
`<div class="comment">` + `sanitize(text)` + `</div>`.

Output format (exact):

- Text is escaped: `&`, `<` and `>` become `&amp;`, `&lt;` and `&gt;`, quotes stay as they are. Character references in the input are decoded first, so `&lt;b&gt;` stays `&lt;b&gt;` and `&#60;` becomes `&lt;`.
- Allowed elements: `b i em strong u p ul ol li blockquote code pre a` and `br`. Their names are written in lower case and they have no attributes (except `a`); `<br>` and `<br/>` both give `<br>`.
- `a` is kept only when it has an `href` that is an `http:`, `https:` or `mailto:` URL or a relative URL (no scheme, not starting with `//`). It is written as `<a href="ESCAPED" rel="nofollow noopener">` with the
  href HTML-escaped (`&` -> `&amp;`, quotes escaped, surrounding blanks removed). A link without href or with any other kind of target loses its tags but its text stays.
- Everything else is dropped: other elements (their text stays), every other attribute, comments, doctypes, CDATA and processing instructions. `script` and `style` are dropped together with their content.
- Nesting: an end tag closes every open element above the matching start tag (`<b><i>x</b></i>` gives `<b><i>x</i></b>`), an end tag without a matching open element is dropped, elements still open at the end of the input are closed.
  At most 20 elements are open at once; start tags beyond that are dropped (their text stays).
- Linear time: a megabyte of hostile input must not keep the server busy.
- `sanitize(sanitize(x)) == sanitize(x)`.
""")

SAN_VISIBLE = {"tests/test_sanitize.py": _sec.PY_PRELUDE + dd(r'''
    import sanitize as m


    class SanitizeTest(unittest.TestCase):
        def test_formatting_is_kept(self):
            self.assertEqual(m.sanitize("Hello <b>world</b>"), "Hello <b>world</b>")
            self.assertEqual(m.sanitize("<ul><li>a</li><li>b</li></ul>"), "<ul><li>a</li><li>b</li></ul>")

        def test_scripts_and_handlers_are_removed(self):
            self.assertEqual(m.sanitize("<script>alert(1)</script>ok"), "ok")
            self.assertEqual(m.sanitize("<p onclick='x'>a</p>"), "<p>a</p>")
            self.assertEqual(m.sanitize("<img src=x onerror=alert(1)>"), "")

        def test_links(self):
            self.assertEqual(m.sanitize('<a href="https://example.com/x">x</a>'), '<a href="https://example.com/x" rel="nofollow noopener">x</a>')


    if __name__ == "__main__":
        unittest.main()
''')}

SAN_TEST = _sec.PY_PRELUDE + dd(r'''
    import re
    import signal
    import contextlib
    from html.parser import HTMLParser
    from urllib.parse import unquote

    import sanitize as m

    ALLOWED_TAGS = {"b", "i", "em", "strong", "u", "p", "ul", "ol", "li", "blockquote", "code", "pre", "a", "br"}


    @contextlib.contextmanager
    def time_limit(seconds=6):
        def boom(signum, frame):
            raise TimeoutError("sanitize took too long")
        old = signal.signal(signal.SIGALRM, boom)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)


    class Collector(HTMLParser):
        """What a browser would build from the comment page: the wrapper div plus whatever the sanitizer let through."""

        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.tags, self.ends, self.hrefs, self.bad = [], [], [], []

        def handle_starttag(self, tag, attrs):
            self.tags.append(tag)
            if len(self.tags) == 1:
                if tag != "div" or attrs != [("class", "comment")]:
                    self.bad.append(("wrapper", tag, attrs))
            elif tag not in ALLOWED_TAGS:
                self.bad.append(("tag", tag, attrs))
            elif tag == "a":
                if sorted(name for name, _ in attrs) != ["href", "rel"] or dict(attrs).get("rel") != "nofollow noopener":
                    self.bad.append(("a-attributes", attrs))
                else:
                    self.hrefs.append(dict(attrs)["href"])
            elif attrs:
                self.bad.append(("attributes", tag, attrs))

        def handle_endtag(self, tag):
            self.ends.append(tag)

        def handle_comment(self, data):
            self.bad.append(("comment", data))

        def handle_decl(self, decl):
            self.bad.append(("decl", decl))

        def handle_pi(self, data):
            self.bad.append(("pi", data))

        def unknown_decl(self, data):
            self.bad.append(("unknown_decl", data))


    def collect(out):
        c = Collector()
        c.feed('<div class="comment">' + out + "</div>")
        c.close()
        return c


    def browser_scheme(href):
        flat = re.sub(r"[\t\r\n]", "", href).lstrip("".join(chr(i) for i in range(33)))
        found = re.match(r"([A-Za-z][A-Za-z0-9+.-]*):", flat)
        return found.group(1).lower() if found else None


    EXACT = [
        ("Hello <b>world</b>", "Hello <b>world</b>"),
        ("<p onclick='x'>a</p>", "<p>a</p>"),
        ("<script>alert(1)</script>ok", "ok"),
        ("<style>p{}</style>x", "x"),
        ("<img src=x onerror=alert(1)>", ""),
        ('<a href="javascript:alert(1)">x</a>', "x"),
        ('<a href="https://e.com/?a=1&b=2">x</a>', '<a href="https://e.com/?a=1&amp;b=2" rel="nofollow noopener">x</a>'),
        ("1 < 2 & 3 > 2", "1 &lt; 2 &amp; 3 &gt; 2"),
        ("<b>bold", "<b>bold</b>"),
        ("x</b>", "x"),
        ("<b><i>x</b></i>", "<b><i>x</i></b>"),
        ("<B>Up</B>", "<b>Up</b>"),
        ("line<br>two<br/>three", "line<br>two<br>three"),
        ("<!-- c -->t", "t"),
        ("&lt;script&gt;alert(1)&lt;/script&gt;", "&lt;script&gt;alert(1)&lt;/script&gt;"),
        ("&#60;b&#62;", "&lt;b&gt;"),
        ('<a href="/docs/x?y=1">rel</a>', '<a href="/docs/x?y=1" rel="nofollow noopener">rel</a>'),
        ('<a href="mailto:a@b.co">mail</a>', '<a href="mailto:a@b.co" rel="nofollow noopener">mail</a>'),
        ('<a href=" http://e.com/a b ">sp</a>', '<a href="http://e.com/a b" rel="nofollow noopener">sp</a>'),
        ('<a href="//evil.io">x</a>', "x"),
        ('<a>no target</a>', "no target"),
        ("<ul><li>a</li><li>b</li></ul>", "<ul><li>a</li><li>b</li></ul>"),
        ("<div><span>kept text</span></div>", "kept text"),
        ('<a href="https://ok.io/" title="t" onclick="x()">k</a>', '<a href="https://ok.io/" rel="nofollow noopener">k</a>'),
        ('<a href="https://ok.io/?q=%22a%22&x=\'1\'">q</a>', '<a href="https://ok.io/?q=%22a%22&amp;x=&#x27;1&#x27;" rel="nofollow noopener">q</a>'),
        ("<p>one<p>two", "<p>one<p>two</p></p>"),
    ]

    ATTACKS = [
        "<script>alert(1)</script>", "<SCRIPT SRC=//evil.io/x.js></SCRIPT>", "<scr<script>ipt>alert(1)</scr</script>ipt>", "<img src=x onerror=alert(1)>", "<svg/onload=alert(1)>",
        "<body onload=alert(1)>", '<a href="javascript:alert(1)">x</a>', '<a href="JaVaScRiPt:alert(1)">x</a>', '<a href="javajavascript:script:alert(1)">x</a>',
        '<a href="java&#115;cript:alert(1)">x</a>', '<a href="java&#x09;script:alert(1)">x</a>', '<a href="&#x6A;avascript:alert(1)">x</a>', '<a href=" javascript:alert(1)">x</a>',
        '<a href="\tjavascript:alert(1)">x</a>', '<a href="java\nscript:alert(1)">x</a>', "<a href='javascript:alert(1)'>x</a>", "<a href=javascript:alert(1)>x</a>",
        '<a href="\x01javascript:alert(1)">x</a>', '<a href="vbscript:msgbox(1)">x</a>', '<a href="data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==">x</a>',
        '<a href="//evil.io/x">x</a>', '<a href="\\\\evil.io">x</a>', '<a href="/\\evil.io">x</a>', '<a href="https://ok.io/" onclick="alert(1)">x</a>',
        '<a href="https://ok.io/"onmouseover="alert(1)">x</a>', '<a href="https://ok.io/" style="position:fixed;top:0">x</a>', '<a href="x" href="javascript:alert(1)">x</a>',
        "<a href='\"onmouseover=\"alert(1)'>x</a>", '<a href="x&quot; onmouseover=&quot;alert(1)">x</a>', '<a href="x" "onmouseover=alert(1) ">x</a>',
        '<iframe src="javascript:alert(1)"></iframe>', '<object data="javascript:alert(1)">', '<embed src="data:text/html,x">',
        '<form action="javascript:alert(1)"><button>x</button></form>', "<style>@import 'javascript:alert(1)';</style>", '<b style="background:url(javascript:alert(1))">x</b>',
        '<meta http-equiv="refresh" content="0;url=javascript:alert(1)">', '<base href="javascript:alert(1)//">', "<img src=x onerror=alert(1)//", "<<img src=x onerror=alert(1)//",
        "<b <img src=x onerror=alert(1)>", "<p<img src=x onerror=alert(1)>>", "<!--><img src=x onerror=alert(1)>-->", "<!-- --!><img src=x onerror=alert(1)>",
        "<![CDATA[><img src=x onerror=alert(1)>]]>", "<?php echo 1 ?><img src=x onerror=alert(1)>", "<math><mtext><img src=x onerror=alert(1)>",
        '<noscript><p title="</noscript><img src=x onerror=alert(1)>">', "<textarea></textarea><img src=x onerror=alert(1)>", "<title><img src=x onerror=alert(1)></title>",
        "<xmp><img src=x onerror=alert(1)></xmp>", "&lt;img src=x onerror=alert(1)&gt;", "&#60;img src=x onerror=alert(1)&#62;", "<b>" * 40 + "x",
        '<a href="https://ok.io">' * 40, "<\x00script>alert(1)</script>", "<scri\x00pt>alert(1)</script>", "<img/src=x/onerror=alert(1)>", '<BR/><a/href="javascript:alert(1)">x</a>',
        "1 <img src=x onerror=alert(1) 2", "a<b", "a < b < c > d", "<a href=\"https://ok.io/\">x</a onmouseover=alert(1)>", "</a><img src=x onerror=alert(1)>",
        "<script>alert(1)", "<script><script>alert(1)</script></script>", "<STYLE>x</STYLE><script>alert(1)</script>",
    ]


    class SanitizeTest(unittest.TestCase):
        def test_documented_output(self):
            for src, want in EXACT:
                self.assertEqual(m.sanitize(src), want, src)

        def test_attacks_leave_only_the_allowed_markup(self):
            for src in ATTACKS:
                with time_limit():
                    out = m.sanitize(src)
                c = collect(out)
                self.assertEqual(c.bad, [], (src, out))
                self.assertEqual(c.tags[0], "div", (src, out))
                self.assertEqual(c.ends.count("div"), 1, (src, out))
                self.assertEqual(c.ends[-1], "div", (src, out))
                for href in c.hrefs:
                    self.assertIn(browser_scheme(href), (None, "http", "https", "mailto"), (src, out))
                    self.assertFalse(href.lstrip().startswith("//") or "\\" in href, (src, out))
                    self.assertFalse(re.search(r"[\x00-\x1f\x7f]", href), (src, out))

        def test_output_is_idempotent(self):
            for src in ATTACKS + [s for s, _ in EXACT]:
                once = m.sanitize(src)
                self.assertEqual(m.sanitize(once), once, src)

        def test_output_is_balanced(self):
            for src in ["<b><i>x</b></i>", "<b>" * 30 + "x", "</i></b>text<u>", "<ul><li>a<li>b</ul>", "<a href='/x'><b>y</a></b>"]:
                out = m.sanitize(src)
                depth = 0
                for closing, name in re.findall(r"<(/?)([a-z]+)", out):
                    if name == "br":
                        continue
                    depth += -1 if closing else 1
                    self.assertGreaterEqual(depth, 0, out)
                    self.assertLessEqual(depth, 20, out)
                self.assertEqual(depth, 0, out)

        def test_nesting_limit(self):
            out = m.sanitize("<b>" * 100 + "deep" + "</b>" * 100)
            self.assertIn("deep", out)
            self.assertEqual(out.count("<b>"), 20)

        def test_hostile_sizes_are_cheap(self):
            for src in ["<script>" * 40000, '<a href="' + "x" * 300000, "<" * 100000, "<!--" * 80000, "&" * 300000, '<a href="http://x.io">' * 30000, "<b " + 'a="1" ' * 40000 + ">x</b>"]:
                with time_limit(5):
                    out = m.sanitize(src)
                self.assertIsInstance(out, str)

        def test_text_survives(self):
            self.assertEqual(m.sanitize("<script>bad()</script>ok <b>1 < 2</b> done"), "ok <b>1 &lt; 2</b> done")
            self.assertEqual(m.sanitize(""), "")
            self.assertEqual(m.sanitize("plain"), "plain")


    if __name__ == "__main__":
        unittest.main()
''')

SC.append(dict(
    slug="html-sanitizer", d=4, product="the comment system", func="sanitize", cwe="CWE-79",
    finding=("`sanitize` removes tags and attributes with regular expressions: link targets are only filtered for the literal text `javascript:`, so `<a href=\"JaVaScRiPt:alert(1)\">`, "
             "`<a href=\"javajavascript:script:alert(1)\">` and `<a href=\"java&#115;cript:alert(1)\">` all keep a working script link, and a stray `<` is passed through unescaped, so "
             "`<img src=x onerror=alert(1)//` becomes a live tag once the comment is placed in the page."),
    extra="The comment page places the result inside a `<div class=\"comment\">` element; README.md specifies the exact output format.",
    start={"sanitize.py": SAN_START, "README.md": SAN_README},
    solution={"sanitize.py": SAN_SOL},
    visible=SAN_VISIBLE,
    hidden={"tests/test_sanitize_security.py": SAN_TEST},
    timeout_s=150,
))

# ---------------------------------------------------------------------------------------------------------------------------------
# authorization policy engine
POL_START = dd(r'''
    """Authorization policy evaluation for the document store (see README.md)."""
    import fnmatch


    def _expand(policy, role):
        """The role and every role it inherits from."""
        found = {role}
        for parent in policy.get("roles", {}).get(role, []):
            found |= _expand(policy, parent)
        return found


    def _roles_of(policy, user):
        found = set()
        for role in user.get("roles", []):
            found |= _expand(policy, role)
        return found


    def _glob(pattern, resource):
        return fnmatch.fnmatchcase(resource, pattern.replace("**", "*"))


    def check(policy, user, action, resource):
        """True when `user` may perform `action` on `resource`."""
        roles = _roles_of(policy, user)
        for rule in policy.get("rules", []):
            if "*" not in rule["roles"] and not roles & set(rule["roles"]):
                continue
            if "*" not in rule["actions"] and action not in rule["actions"]:
                continue
            if not any(_glob(pattern, resource) for pattern in rule["resources"]):
                continue
            return rule["effect"] == "allow"
        return True
''')

POL_SOL = dd(r'''
    """Authorization policy evaluation for the document store (see README.md)."""


    def normalize(resource):
        """The segments of an absolute resource path with `.`, `..` and empty segments resolved, or None when the path is not acceptable."""
        if not isinstance(resource, str) or not resource.startswith("/") or "\x00" in resource or "\\" in resource:
            return None
        parts = []
        for segment in resource.split("/"):
            if segment in ("", "."):
                continue
            if segment == "..":
                if not parts:
                    return None
                parts.pop()
            else:
                parts.append(segment)
        return parts


    def _segment_match(pattern, text):
        """`*` matches any run of characters, `?` one character, everything else is literal (iterative, no backtracking blow-up)."""
        p = s = 0
        star = -1
        mark = 0
        while s < len(text):
            if p < len(pattern) and pattern[p] == "*":
                star, mark = p, s
                p += 1
            elif p < len(pattern) and (pattern[p] == "?" or pattern[p] == text[s]):
                p += 1
                s += 1
            elif star != -1:
                mark += 1
                p, s = star + 1, mark
            else:
                return False
        while p < len(pattern) and pattern[p] == "*":
            p += 1
        return p == len(pattern)


    def _glob(pattern_parts, parts):
        """Segment-wise match: `**` matches any number of segments (also none), `*` and `?` stay inside one segment."""
        reachable = {0}
        for piece in pattern_parts:
            if piece == "**":
                reachable = set(range(min(reachable), len(parts) + 1))
            else:
                reachable = {i + 1 for i in reachable if i < len(parts) and _segment_match(piece, parts[i])}
            if not reachable:
                return False
        return len(parts) in reachable


    def _effective_roles(policy, roles):
        graph = policy.get("roles")
        graph = graph if isinstance(graph, dict) else {}
        seen = set()
        todo = list(roles)
        while todo:
            role = todo.pop()
            if role in seen:
                continue
            seen.add(role)
            parents = graph.get(role, [])
            if isinstance(parents, (list, tuple)):
                todo.extend(p for p in parents if isinstance(p, str))
        return seen


    def _listed(values, have):
        return isinstance(values, (list, tuple)) and ("*" in values or any(v in have for v in values if isinstance(v, str)))


    def _resource_matches(patterns, parts):
        if not isinstance(patterns, (list, tuple)):
            return False
        for pattern in patterns:
            if isinstance(pattern, str) and pattern.startswith("/") and _glob([piece for piece in pattern.split("/") if piece], parts):
                return True
        return False


    def check(policy, user, action, resource):
        """True when `user` may perform `action` on `resource`."""
        parts = normalize(resource)
        if parts is None or not isinstance(action, str) or not isinstance(policy, dict) or not isinstance(user, dict):
            return False
        roles = user.get("roles", [])
        if not isinstance(roles, (list, tuple)) or not all(isinstance(r, str) for r in roles):
            return False
        effective = _effective_roles(policy, roles)
        rules = policy.get("rules", [])
        allowed = False
        for rule in rules if isinstance(rules, (list, tuple)) else []:
            if not isinstance(rule, dict) or rule.get("effect") not in ("allow", "deny"):
                continue
            if not (_listed(rule.get("roles"), effective) and _listed(rule.get("actions"), {action}) and _resource_matches(rule.get("resources"), parts)):
                continue
            if rule["effect"] == "deny":
                return False
            allowed = True
        return allowed
''')

POL_README = readme("document store policy", r"""
`check(policy, user, action, resource)` decides whether `user` (a dict like `{"name": "ann", "roles": ["editor"]}`) may do `action` (a string such as `"read"`) to `resource` (an absolute path such as `/docs/a.txt`).
It returns `True` or `False` and never raises on bad input: anything malformed is a denial.

The policy is a dict:

    {"roles": {"admin": ["editor"], "editor": ["viewer"]},
     "rules": [{"effect": "allow", "roles": ["viewer"], "actions": ["read"], "resources": ["/docs/**"]}, ...]}

Semantics:

- Deny by default: access is granted only when at least one `allow` rule matches. A matching `deny` rule always wins, wherever it is in the list; the order of the rules never matters.
- `roles` maps a role to the roles it inherits from, transitively (`admin` gets everything `editor` and `viewer` get). The table may contain loops and may be thousands of levels deep, the check must still terminate and give the right answer.
  A role is only a name: a user role of `"*"` is not a wildcard, and names are case sensitive.
- A rule applies when one of the user's (inherited) roles is in its `roles` list, `action` is in its `actions` list and the normalised resource matches one of its `resources` patterns. `"*"` in `roles` means every user (also one without roles), `"*"` in `actions` every action.
- The resource is normalised before it is matched: empty and `.` segments are dropped, `..` removes the previous segment, a trailing `/` does not matter (`/docs/a/../b/` is `/docs/b`). It must be an absolute path: relative paths, paths that climb above `/`, paths with a backslash or a NUL character are denied. Segments are literal names: nothing is percent-decoded.
- Patterns are matched segment by segment: `*` matches any run of characters inside one segment (never `/`), `?` one character inside a segment, a segment `**` any number of whole segments including none (`/docs/**` matches `/docs` and `/docs/a/b`, not `/docsx` or `/docs-old/a`). Every other character, brackets included, is literal (`/files/report[1].txt` names exactly that file).
- Rules that are not dicts, have an `effect` other than `allow` or `deny`, or have a `roles`, `actions` or `resources` field that is not a list are ignored. User `roles` must be a list of strings (a bare string is not accepted).
- `check` must not modify the policy or the user.
""")

POL_VISIBLE = {"tests/test_policy.py": _sec.PY_PRELUDE + dd(r'''
    import policy as m

    POLICY = {
        "roles": {"editor": ["viewer"]},
        "rules": [
            {"effect": "allow", "roles": ["viewer"], "actions": ["read"], "resources": ["/docs/*"]},
            {"effect": "deny", "roles": ["contractor"], "actions": ["*"], "resources": ["/docs/*"]},
        ],
    }


    class PolicyTest(unittest.TestCase):
        def test_viewer_reads(self):
            self.assertTrue(m.check(POLICY, {"name": "v", "roles": ["viewer"]}, "read", "/docs/a.txt"))

        def test_inherited_role(self):
            self.assertTrue(m.check(POLICY, {"name": "e", "roles": ["editor"]}, "read", "/docs/a.txt"))

        def test_explicit_deny(self):
            self.assertFalse(m.check(POLICY, {"name": "c", "roles": ["contractor"]}, "read", "/docs/a.txt"))


    if __name__ == "__main__":
        unittest.main()
''')}

POL_TEST = _sec.PY_PRELUDE + dd(r'''
    import copy
    import contextlib
    import signal

    import policy as m


    @contextlib.contextmanager
    def time_limit(seconds=8):
        def boom(signum, frame):
            raise TimeoutError("check took too long")
        old = signal.signal(signal.SIGALRM, boom)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)


    POLICY = {
        "roles": {"admin": ["editor"], "editor": ["viewer"], "viewer": [], "contractor": []},
        "rules": [
            {"effect": "allow", "roles": ["viewer"], "actions": ["read"], "resources": ["/docs/**"]},
            {"effect": "allow", "roles": ["editor"], "actions": ["write", "delete"], "resources": ["/docs/**"]},
            {"effect": "allow", "roles": ["contractor"], "actions": ["write"], "resources": ["/uploads/*"]},
            {"effect": "allow", "roles": ["admin"], "actions": ["*"], "resources": ["/**"]},
            {"effect": "deny", "roles": ["*"], "actions": ["*"], "resources": ["/docs/secret/**", "/audit/**"]},
            {"effect": "deny", "roles": ["editor"], "actions": ["delete"], "resources": ["/docs/locked/**"]},
        ],
    }

    ALLOW = [
        (["viewer"], "read", "/docs/a/b/c.txt"), (["viewer"], "read", "/docs"), (["editor"], "write", "/docs/a.txt"), (["editor"], "read", "/docs/a/b.txt"),
        (["editor"], "delete", "/docs/open/x"), (["editor"], "write", "/docs/locked/x"), (["contractor"], "write", "/uploads/a.png"), (["admin"], "delete", "/anything/at/all"),
        (["admin"], "read", "/"), (["admin"], "purge", "/x"), (["viewer"], "read", "/docs/./a//b"), (["viewer"], "read", "/docs/a/../b"), (["viewer"], "read", "/docs/a/"),
        (["viewer"], "read", "/docs/%2e%2e/private/x"), (["viewer"], "read", "/docs/secret.txt"), (["viewer"], "read", "/docs/secretary/x"), (["viewer", "contractor"], "write", "/uploads/x"),
        (["viewer"], "read", "/docs/secret/../public.txt"), (["admin"], "read", "/docs/x"), (["admin"], "read", "/auditor/x"),
    ]
    DENY = [
        (["viewer"], "write", "/docs/a"), (["viewer"], "delete", "/docs/a"), (["contractor"], "write", "/uploads/a/b.png"), (["contractor"], "write", "/uploads"), (["contractor"], "read", "/uploads/a"),
        ([], "read", "/docs/a"), (["nobody"], "read", "/docs/a"), (["Viewer"], "read", "/docs/a"), (["*"], "read", "/docs/a"), (["editor"], "purge", "/docs/a"), (["viewer"], "read", "/other/x"),
        (["admin"], "read", "/docs/secret/plan.txt"), (["admin"], "read", "/docs/secret"), (["admin"], "write", "/audit/log"), (["editor"], "read", "/docs/secret/x"),
        (["editor"], "delete", "/docs/locked/x"), (["admin"], "delete", "/docs/locked/x"),
        (["viewer"], "read", "/docs/../private/x"), (["viewer"], "read", "/docs/../../etc/passwd"), (["viewer"], "read", "/docs/public/../secret/x"), (["admin"], "read", "/docs/public/../secret/x"),
        (["admin"], "read", "/docs/secret/./x"), (["admin"], "read", "/docs//secret/x"), (["admin"], "read", "/docs/secret//"), (["admin"], "read", "/docs/x/../../audit/log"),
        (["viewer"], "read", "docs/a"), (["viewer"], "read", "/docs/a\\..\\b"), (["viewer"], "read", "/docs/a\x00"), (["admin"], "read", "/../x"), (["admin"], "read", ""), (["admin"], "read", None),
        (["admin"], "read", ["/x"]), (["admin"], None, "/x"), (["admin"], ["read"], "/x"), (["admin"], 5, "/x"),
    ]


    def can(roles, action, resource, policy=POLICY):
        try:
            return bool(m.check(policy, {"name": "u", "roles": roles}, action, resource))
        except Exception:  # noqa: BLE001  (a crash is as good as a denial for these tests)
            return False


    class PolicyTest(unittest.TestCase):
        def policies(self):
            rules = POLICY["rules"]
            for ordered in (rules, rules[::-1], rules[2:] + rules[:2], rules[3:] + rules[:3]):
                yield {"roles": POLICY["roles"], "rules": list(ordered)}

        def test_allowed(self):
            for policy in self.policies():
                for roles, action, resource in ALLOW:
                    self.assertTrue(can(roles, action, resource, policy), (roles, action, resource))

        def test_denied(self):
            for policy in self.policies():
                for roles, action, resource in DENY:
                    self.assertFalse(can(roles, action, resource, policy), (roles, action, resource))

        def test_malformed_users(self):
            for user in [None, "admin", 5, [], {"roles": "admin"}, {"roles": None}, {"roles": [None]}, {"roles": [["admin"]]}, {"roles": ["admin", 1]}, {"roles": {"admin": 1}}]:
                try:
                    result = m.check(POLICY, user, "read", "/docs/a")
                except Exception:  # noqa: BLE001
                    result = False
                self.assertFalse(result, user)
            self.assertFalse(can(["admin"], "read", "/docs/a", None) or can(["admin"], "read", "/docs/a", {}) or can(["admin"], "read", "/docs/a", "x"))

        def test_user_without_roles_key(self):
            policy = {"roles": {}, "rules": [{"effect": "allow", "roles": ["*"], "actions": ["read"], "resources": ["/public/**"]}]}
            self.assertTrue(m.check(policy, {"name": "anon"}, "read", "/public/x"))
            self.assertFalse(m.check(policy, {"name": "anon"}, "write", "/public/x"))

        def test_role_loops_terminate(self):
            policy = {"roles": {"a": ["b"], "b": ["a"], "self": ["self"]}, "rules": [{"effect": "allow", "roles": ["b"], "actions": ["read"], "resources": ["/x/*"]}]}
            with time_limit():
                self.assertTrue(can(["a"], "read", "/x/1", policy))
                self.assertTrue(can(["b"], "read", "/x/1", policy))
                self.assertFalse(can(["self"], "read", "/x/1", policy))
                self.assertFalse(can(["c"], "read", "/x/1", policy))

        def test_deep_hierarchies(self):
            roles = {"r%d" % i: ["r%d" % (i + 1)] for i in range(1500)}
            policy = {"roles": roles, "rules": [{"effect": "allow", "roles": ["r1500"], "actions": ["read"], "resources": ["/x/**"]}]}
            with time_limit():
                self.assertTrue(can(["r0"], "read", "/x/y", policy))
                self.assertTrue(can(["r1499"], "read", "/x/y", policy))
                self.assertFalse(can(["other"], "read", "/x/y", policy))

        def test_junk_rules_are_ignored(self):
            policy = {"roles": {}, "rules": [
                "junk", None, 5, {"effect": "permit", "roles": ["*"], "actions": ["*"], "resources": ["/**"]}, {"effect": "allow"},
                {"effect": "allow", "roles": "viewer", "actions": ["read"], "resources": ["/docs/**"]},
                {"effect": "allow", "roles": ["viewer"], "actions": "read", "resources": ["/docs/**"]},
                {"effect": "allow", "roles": ["viewer"], "actions": ["read"], "resources": "/docs/**"},
                {"effect": "allow", "roles": ["viewer"], "actions": ["read"], "resources": [None, 5, "docs/relative/**"]},
                {"effect": "allow", "roles": ["viewer"], "actions": ["read"], "resources": ["/ok/**"]},
            ]}
            self.assertTrue(can(["viewer"], "read", "/ok/x", policy))
            self.assertFalse(can(["viewer"], "read", "/docs/x", policy))
            self.assertFalse(can(["viewer"], "read", "/docs/relative/x", policy))
            self.assertFalse(can(["other"], "read", "/anything", policy))

        def test_patterns_are_not_regular_expressions(self):
            policy = {"roles": {}, "rules": [{"effect": "allow", "roles": ["*"], "actions": ["read"], "resources": ["/files/report[1].txt", "/files/q?.txt", "/files/a*b.txt", "/v1.0/**"]}]}
            self.assertTrue(can([], "read", "/files/report[1].txt", policy))
            self.assertFalse(can([], "read", "/files/report1.txt", policy))
            self.assertTrue(can([], "read", "/files/q1.txt", policy))
            self.assertFalse(can([], "read", "/files/q.txt", policy))
            self.assertFalse(can([], "read", "/files/q12.txt", policy))
            self.assertTrue(can([], "read", "/files/a-x-b.txt", policy))
            self.assertFalse(can([], "read", "/files/a/b.txt", policy))
            self.assertTrue(can([], "read", "/v1.0/x", policy))
            self.assertFalse(can([], "read", "/v1x0/x", policy))

        def test_many_wildcards_are_cheap(self):
            policy = {"roles": {}, "rules": [{"effect": "allow", "roles": ["*"], "actions": ["read"], "resources": ["/" + "a*" * 40 + "b"]}]}
            with time_limit():
                self.assertFalse(can([], "read", "/" + "a" * 3000, policy))
                self.assertTrue(can([], "read", "/" + "a" * 3000 + "b", policy))

        def test_no_mutation(self):
            policy, user = copy.deepcopy(POLICY), {"name": "u", "roles": ["admin", "viewer"]}
            before = copy.deepcopy((policy, user))
            for _, action, resource in ALLOW + DENY:
                try:
                    m.check(policy, user, action, resource)
                except Exception:  # noqa: BLE001
                    pass
            self.assertEqual((policy, user), before)


    if __name__ == "__main__":
        unittest.main()
''')

SC.append(dict(
    slug="policy-engine", d=4, product="the document store", func="check", cwe="CWE-285",
    finding=("`check` lets requests through that the policy should refuse: the first matching rule wins (a broad allow listed before a deny beats it), anything that no rule mentions is allowed, "
             "`*` in a resource pattern crosses `/` and the resource is not normalised so `/docs/public/../secret/x` matches `/docs/public/*`, and a role hierarchy with a loop crashes the check."),
    extra="README.md defines the exact semantics (deny by default, deny wins, role inheritance, segment-wise patterns, normalisation).",
    start={"policy.py": POL_START, "README.md": POL_README},
    solution={"policy.py": POL_SOL},
    visible=POL_VISIBLE,
    hidden={"tests/test_policy_security.py": POL_TEST},
    timeout_s=150,
))

# ---------------------------------------------------------------------------------------------------------------------------------
# link builder and link validator
LINK_START = dd(r'''
    """Links into the store (used in e-mails and redirects, see README.md)."""
    from urllib.parse import quote, urljoin, urlsplit

    BASE = "https://shop.example/store/"
    HOST = "shop.example"


    def build(path, params=None):
        """Absolute URL of `path` below the store root, with `params` as query string."""
        url = urljoin(BASE, quote(path))
        if params:
            url += "?" + "&".join("%s=%s" % (name, quote(str(value), safe="")) for name, value in sorted(params.items()))
        return url


    def is_ours(url):
        """True when `url` is a link into the store."""
        parts = urlsplit(url)
        return (parts.hostname or "").endswith(HOST) and parts.path.startswith("/store")
''')

LINK_SOL = dd(r'''
    """Links into the store (used in e-mails and redirects, see README.md)."""
    import re
    from urllib.parse import quote, unquote, urlsplit

    BASE = "https://shop.example/store/"
    HOST = "shop.example"
    MAX_URL = 2000
    CONTROL = re.compile(r"[\x00-\x1f\x7f]")
    BAD_URL_CHARS = re.compile(r"[\s\x00-\x20\x7f\\]")
    PARAM_NAME = re.compile(r"[A-Za-z0-9_.-]{1,40}\Z")


    def build(path, params=None):
        """Absolute URL of `path` below the store root, with `params` as query string."""
        if not isinstance(path, str) or CONTROL.search(path) or "\\" in path:
            raise ValueError("bad path")
        segments = path.split("/")
        if segments[0] == "":
            segments = segments[1:]
        trailing = bool(segments) and segments[-1] == ""
        if trailing:
            segments.pop()
        if any(segment in ("", ".", "..") for segment in segments):
            raise ValueError("empty or dot segment in path")
        url = BASE + "/".join(quote(segment, safe="") for segment in segments) + ("/" if trailing and segments else "")
        if params:
            if not isinstance(params, dict):
                raise ValueError("params must be a dict")
            pairs = []
            for name in params:
                if not isinstance(name, str) or not PARAM_NAME.match(name):
                    raise ValueError("bad parameter name")
                value = params[name]
                if isinstance(value, bool) or not isinstance(value, (str, int)):
                    raise ValueError("bad parameter value")
                pairs.append((name, quote(str(value), safe="")))
            url += "?" + "&".join("%s=%s" % pair for pair in sorted(pairs))
        if len(url) > MAX_URL:
            raise ValueError("URL too long")
        return url


    def is_ours(url):
        """True when `url` is a link into the store."""
        if not isinstance(url, str) or len(url) > MAX_URL or BAD_URL_CHARS.search(url):
            return False
        try:
            parts = urlsplit(url)
        except ValueError:
            return False
        if parts.scheme != "https" or parts.netloc.lower() not in (HOST, HOST + ":443"):
            return False
        if parts.path != "/store" and not parts.path.startswith("/store/"):
            return False
        for segment in parts.path.split("/")[1:]:
            decoded = unquote(segment)
            if decoded in (".", "..") or "/" in decoded or "\\" in decoded or CONTROL.search(decoded):
                return False
        return True
''')

LINK_README = readme("store links", r"""
The store lives at `https://shop.example/store/`. This module builds links to it for e-mails and decides whether a URL (for example a `return_to` parameter) points into the store before the application redirects there.

`build(path, params=None)` returns an absolute URL:

- `path` is a string of segments separated by `/`, relative to the store root. A leading `/` is ignored (`"/orders/7"` is `"orders/7"`), a single trailing `/` is kept, `""` and `"/"` give the root `https://shop.example/store/`.
- Every segment is a literal name and is quoted completely, so `"products/blue shirt"` gives `.../store/products/blue%20shirt`, `"tags/c++"` gives `c%2B%2B`, `"100%"` gives `100%25`, `"a?b#c"` gives `a%3Fb%23c`, non-ASCII text becomes UTF-8 percent escapes. Percent signs in the input are data, not escapes.
- `ValueError` for: a non-string path, empty segments inside the path (`a//b`), segments `.` or `..`, backslashes, control characters (below 0x20 or 0x7f). (Segments such as `...` or `..x` are ordinary names.)
- `params` is a dict (or `None`/empty). Names must match `[A-Za-z0-9_.-]{1,40}`, values must be `str` or `int` (not `bool`), anything else is a `ValueError`. The query is `?name=value&...` sorted by name, values quoted completely (`%20` for a space), an empty string value gives `name=`.
- The result is never longer than 2000 characters (`ValueError` otherwise) and always has scheme `https`, host `shop.example`, a path inside `/store/` and no fragment.

`is_ours(url)` is `True` only for URLs a browser would really load from the store: scheme `https`, host exactly `shop.example` (any letter case, optional `:443`, no user name or password, no other port), path `/store` or below `/store/`, no `.` or `..` segment
(also not percent-encoded), no encoded `/`, `\` or control character inside a segment, and no whitespace, control character or backslash anywhere. It never raises: everything else (relative URLs, other schemes, non-strings, longer than 2000 characters) is `False`.
Every URL made by `build` is accepted by `is_ours`.
""")

LINK_VISIBLE = {"tests/test_links.py": _sec.PY_PRELUDE + dd(r'''
    import links as m


    class LinkTest(unittest.TestCase):
        def test_build(self):
            self.assertEqual(m.build("products/blue shirt"), "https://shop.example/store/products/blue%20shirt")
            self.assertEqual(m.build("search/", {"q": "red shirt", "page": 2}), "https://shop.example/store/search/?page=2&q=red%20shirt")
            self.assertEqual(m.build(""), "https://shop.example/store/")

        def test_is_ours(self):
            self.assertTrue(m.is_ours("https://shop.example/store/products/1"))
            self.assertFalse(m.is_ours("https://evil.io/store/products/1"))
            self.assertTrue(m.is_ours(m.build("orders/7")))


    if __name__ == "__main__":
        unittest.main()
''')}

LINK_TEST = _sec.PY_PRELUDE + dd(r'''
    import re
    from urllib.parse import parse_qsl, unquote, urlsplit

    import links as m

    ROOT_URL = "https://shop.example/store/"

    BUILD_OK = [
        ("products/blue shirt", None, ROOT_URL + "products/blue%20shirt"),
        ("/orders/7", None, ROOT_URL + "orders/7"),
        ("", None, ROOT_URL), ("/", None, ROOT_URL),
        ("search/", None, ROOT_URL + "search/"),
        ("tags/c++", None, ROOT_URL + "tags/c%2B%2B"),
        ("100%", None, ROOT_URL + "100%25"),
        ("a?b#c", None, ROOT_URL + "a%3Fb%23c"),
        ("caf\u00e9/x", None, ROOT_URL + "caf%C3%A9/x"),
        ("a:b/c", None, ROOT_URL + "a%3Ab/c"),
        ("...", None, ROOT_URL + "..."),
        ("a/..b/c.d", None, ROOT_URL + "a/..b/c.d"),
        ("%2e%2e/%2e%2e/admin", None, ROOT_URL + "%252e%252e/%252e%252e/admin"),
        ("search", {"q": "red shirt", "page": 2}, ROOT_URL + "search?page=2&q=red%20shirt"),
        ("search", {"q": "a&b=c#d"}, ROOT_URL + "search?q=a%26b%3Dc%23d"),
        ("search", {"q": ""}, ROOT_URL + "search?q="),
        ("search", {}, ROOT_URL + "search"),
        ("search", {"b": 1, "a": "x", "c.d-e_f": "y"}, ROOT_URL + "search?a=x&b=1&c.d-e_f=y"),
        ("search", {"q": "line\r\nSet-Cookie: x=1"}, ROOT_URL + "search?q=line%0D%0ASet-Cookie%3A%20x%3D1"),
    ]

    BAD_PATHS = [
        "//evil.io/x", "///evil.io", "https://evil.io/", "http:/evil.io", "\\\\evil.io", "/\\evil.io", "..", "../..", "../../admin", "a/../../admin", "a/..", "./x", "a/./b", "a/../b",
        "a//b", "a/\t/b", "a\r\nb", "a\x00b", "a\x7fb", "@evil.io", "evil.io:80@x", " //evil.io", "\t//evil.io", "//", "a//", "x" * 3000, ("seg/" * 800),
        None, 5, ["a"], b"a", {"a": 1},
    ]
    BAD_PARAM_NAMES = ["a=1&admin", "q#x", "q\r\nSet-Cookie: x", "a b", "", "x" * 41, "caf\u00e9", "a&b", "a=b", "?x", "q%00"]


    class LinkTest(unittest.TestCase):
        def check_ours(self, url, pairs=None):
            parts = urlsplit(url)
            self.assertEqual((parts.scheme, parts.netloc), ("https", "shop.example"), url)
            self.assertTrue(parts.path == "/store" or parts.path.startswith("/store/"), url)
            self.assertEqual(parts.fragment, "", url)
            self.assertIsNone(re.search(r"[\x00-\x20\x7f\\]", url), url)
            for segment in parts.path.split("/")[1:]:
                self.assertNotIn(unquote(segment), (".", ".."), url)
            self.assertLessEqual(len(url), 2000)
            if pairs is not None:
                self.assertEqual(parse_qsl(parts.query, keep_blank_values=True, strict_parsing=bool(parts.query)), pairs, url)

        def test_build_documented(self):
            for path, params, want in BUILD_OK:
                self.assertEqual(m.build(path, params), want, (path, params))

        def test_build_hostile_paths(self):
            for path in BAD_PATHS:
                try:
                    url = m.build(path)
                except Exception:  # noqa: BLE001
                    continue
                self.check_ours(url)

        def test_build_rejects_unsafe_paths_with_value_error(self):
            for path in ["//evil.io/x", "https://evil.io/", "../../admin", "..", "a/../b", "a//b", "a/./b", "\\\\evil.io", "a\r\nb", None, 5]:
                with self.assertRaises(ValueError, msg=repr(path)):
                    m.build(path)

        def test_build_hostile_parameters(self):
            for name in BAD_PARAM_NAMES:
                try:
                    url = m.build("search", {name: "1"})
                except Exception:  # noqa: BLE001
                    continue
                self.check_ours(url, [(name, "1")])
            for name in BAD_PARAM_NAMES[:6]:
                with self.assertRaises(ValueError, msg=name):
                    m.build("search", {name: "1"})
            for value in ["a&admin=1", "x#frag", "line\r\nX: y", "%00", "100%", "p q+r", "\u00fc\u00f1", "=", "&", "a=b&c=d"]:
                url = m.build("search", {"q": value})
                self.check_ours(url, [("q", value)])

        def test_build_limits(self):
            for path in ["x" * 3000, "seg/" * 800]:
                with self.assertRaises(ValueError):
                    m.build(path)
            with self.assertRaises(ValueError):
                m.build("search", {"q": "y" * 3000})
            self.check_ours(m.build("a/" * 400 + "z"))

        def test_is_ours_accepts_store_links(self):
            for url in ["https://shop.example/store/products/1", "https://SHOP.example/store/", "https://shop.example:443/store/x?q=1#frag", "https://shop.example/store",
                        "https://shop.example/store/a%20b", "https://shop.example/store/a/..b", "https://shop.example/store/%2e%2ex", "https://shop.example/store/%252e%252e/x",
                        "HTTPS://shop.example/store/x", "https://shop.example/store/?next=https://evil.io/", "https://shop.example/store/a%3Fb"]:
                self.assertTrue(m.is_ours(url), url)
            for path, params, _ in BUILD_OK:
                self.assertTrue(m.is_ours(m.build(path, params)), path)

        def test_is_ours_rejects_everything_else(self):
            for url in ["http://shop.example/store/x", "https://evilshop.example/store/x", "https://shop.example.evil.io/store/x", "https://shop.example@evil.io/store/x", "https://evil.io/store/x",
                        "https://evil.io#@shop.example/store/x", "https://shop.example:8443/store/x", "https://shop.example:443@evil.io/store/", "https://user:pw@shop.example/store/x",
                        "https://evil.io@shop.example/store/x", "https://shop.example/storefront", "https://shop.example/stores/x", "https://shop.example/store/../admin",
                        "https://shop.example/store/%2e%2e/admin", "https://shop.example/store/%2E%2E%2Fadmin", "https://shop.example/store/a%2Fb", "https://shop.example/store/a%5Cb",
                        "https://shop.example/store/./x", "https://shop.example/store/a/../../admin", "https://shop.example/store/a%00b", "https://shop.example/store/a%0d%0ab",
                        "javascript://shop.example/store/%0Aalert(1)", "data://shop.example/store/x", "ftp://shop.example/store/x", "//shop.example/store/x", "/store/x", "store/x", "",
                        "https:shop.example/store/x", "https:///shop.example/store/x", "https://shop.example/store/x\n", " https://shop.example/store/x", "https://shop.example/store/x y",
                        "https://shop.example\\@evil.io/store/", "https://shop.example/store/x\\..\\y", "https://shop.example./store/x", "https://sh\u043fp.example/store/x",
                        "https://shop.example/store/" + "a" * 3000, "https://shop.example/store/\t../admin", "https://shop.example/store/x\u2028y", "https://shop.example:/store/x",
                        None, 5, b"https://shop.example/store/x", ["https://shop.example/store/x"]]:
                self.assertFalse(m.is_ours(url), repr(url))


    if __name__ == "__main__":
        unittest.main()
''')

SC.append(dict(
    slug="link-builder", d=4, product="the e-mail link builder", func="build / is_ours", cwe="CWE-601",
    finding=("`build` hands the path to `urljoin`, so `//evil.io/x` or `https://evil.io/` turn a store link into a link to another site and `../../admin` leaves the `/store/` prefix; "
             "query parameter names are not encoded (`a=1&admin` injects a parameter); and `is_ours`, used to vet `return_to` URLs, only checks that the host name ends with the store's host and that the path "
             "starts with `/store`, so `https://evilshop.example/store/x`, `javascript://shop.example/store/%0Aalert(1)` and `https://shop.example/store/../admin` all count as the store."),
    extra="Fix both functions; README.md has the exact rules.",
    start={"links.py": LINK_START, "README.md": LINK_README},
    solution={"links.py": LINK_SOL},
    visible=LINK_VISIBLE,
    hidden={"tests/test_links_security.py": LINK_TEST},
    timeout_s=120,
))

# ---------------------------------------------------------------------------------------------------------------------------------
# template sandbox
TPL_HEAD = dd(r'''
    """A small template engine for notification texts (see README.md)."""
    import html
    import re

    TOKEN = re.compile(r"(\{\{.*?\}\}|\{%.*?%\})", re.S)


    class TemplateError(Exception):
        """The template is invalid or too big."""


    FILTERS = {
        "upper": lambda v: str(v).upper(),
        "lower": lambda v: str(v).lower(),
        "length": lambda v: len(v) if isinstance(v, (str, list, tuple, dict)) else 0,
    }


    def parse(template):
        root = []
        stack = [["root", None, root]]
        for tok in TOKEN.split(template):
            if not tok:
                continue
            top = stack[-1]
            if tok.startswith("{{"):
                top[2].append(("var", tok[2:-2].strip()))
            elif tok.startswith("{%"):
                words = tok[2:-2].split()
                word = words[0] if words else ""
                if word == "if" and len(words) == 2:
                    node = ["if", words[1], [], []]
                    top[2].append(node)
                    stack.append(["if", node, node[2]])
                elif word == "else" and top[0] == "if":
                    top[2] = top[1][3]
                elif word == "endif" and top[0] == "if":
                    stack.pop()
                elif word == "for" and len(words) == 4 and words[2] == "in":
                    node = ["for", words[1], words[3], []]
                    top[2].append(node)
                    stack.append(["for", node, node[3]])
                elif word == "endfor" and top[0] == "for":
                    stack.pop()
                else:
                    raise TemplateError("bad tag: " + tok)
            else:
                top[2].append(("text", tok))
        if len(stack) != 1:
            raise TemplateError("unclosed block")
        return root


''')

TPL_STEP = dd(r'''
    def _step(obj, step):
        if isinstance(obj, dict):
            return obj.get(step)
        if isinstance(obj, (list, tuple)):
            return obj[int(step)] if step.isdigit() and int(step) < len(obj) else None
        value = getattr(obj, step, None)
        if callable(value):
            try:
                value = value()
            except TypeError:
                pass
        return value


    def lookup(ctx, path):
        head, *rest = path.split(".")
        value = ctx.get(head)
        for step in rest:
            if value is None:
                return None
            value = _step(value, step)
        return value


    def evaluate(ctx, expr):
        path, *filters = [part.strip() for part in expr.split("|")]
        value = lookup(ctx, path)
        for name in filters:
            if name not in FILTERS:
                raise TemplateError("unknown filter " + name)
            value = FILTERS[name](value)
        return value


''')

TPL_RUN = dd(r'''
    def run(nodes, ctx, out):
        for node in nodes:
            kind = node[0]
            if kind == "text":
                out.append(node[1])
            elif kind == "var":
                value = evaluate(ctx, node[1])
                out.append("" if value is None else html.escape(str(value)))
            elif kind == "if":
                run(node[2] if evaluate(ctx, node[1]) else node[3], ctx, out)
            else:
                items = lookup(ctx, node[2])
                if isinstance(items, (list, tuple)):
                    for item in items:
                        run(node[3], {**ctx, node[1]: item}, out)


    def render(template, context):
        """Render `template` with `context` (a dict) and return the text."""
        out = []
        run(parse(template), dict(context), out)
        return "".join(out)
''')

TPL_START = TPL_HEAD + TPL_STEP + TPL_RUN

TPL_HEAD_SOL = patched(
    TPL_HEAD,
    ("import html\nimport re\n", "import html\nimport re\nimport types\n"),
    ('TOKEN = re.compile(r"(\\{\\{.*?\\}\\}|\\{%.*?%\\})", re.S)\n',
     'TOKEN = re.compile(r"(\\{\\{.*?\\}\\}|\\{%.*?%\\})", re.S)\nPATH = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)*\\Z")\n\nMAX_TEMPLATE = 20_000\nMAX_DEPTH = 10\nMAX_LOOPS = 10_000\nMAX_OUTPUT = 100_000\n'),
    ("def parse(template):\n    root = []\n", 'def parse(template):\n    if not isinstance(template, str) or len(template) > MAX_TEMPLATE:\n        raise TemplateError("template too long")\n    root = []\n'),
    ('                stack.append(["if", node, node[2]])\n', '                stack.append(["if", node, node[2]])\n                if len(stack) > MAX_DEPTH + 1:\n                    raise TemplateError("blocks nested too deeply")\n'),
    ('                stack.append(["for", node, node[3]])\n', '                stack.append(["for", node, node[3]])\n                if len(stack) > MAX_DEPTH + 1:\n                    raise TemplateError("blocks nested too deeply")\n'),
)

TPL_STEP_SOL = dd(r'''
    def _public(value):
        """Templates only ever see plain data: no callables (methods, classes, functions) and no modules."""
        return None if callable(value) or isinstance(value, types.ModuleType) else value


    def _step(obj, step):
        if step.startswith("_"):
            return None
        if isinstance(obj, dict):
            return _public(obj.get(step))
        if isinstance(obj, (list, tuple)):
            return _public(obj[int(step)]) if step.isdigit() and int(step) < len(obj) else None
        if type(obj).__module__ == "builtins":
            return None
        try:
            return _public(getattr(obj, step, None))
        except Exception:  # noqa: BLE001  (a failing property is just missing data)
            return None


    def lookup(ctx, path):
        if not PATH.match(path):
            raise TemplateError("bad variable name: %r" % path)
        head, *rest = path.split(".")
        value = None if head.startswith("_") else _public(ctx.get(head))
        for step in rest:
            if value is None:
                return None
            value = _step(value, step)
        return value


    def evaluate(ctx, expr):
        path, *filters = [part.strip() for part in expr.split("|")]
        value = lookup(ctx, path)
        for name in filters:
            if name not in FILTERS:
                raise TemplateError("unknown filter " + name)
            value = FILTERS[name](value)
        return value


''')

TPL_RUN_SOL = dd(r'''
    class Budget:
        def __init__(self):
            self.loops = 0
            self.chars = 0


    def emit(out, budget, text):
        budget.chars += len(text)
        if budget.chars > MAX_OUTPUT:
            raise TemplateError("output too large")
        out.append(text)


    def run(nodes, ctx, out, budget):
        for node in nodes:
            kind = node[0]
            if kind == "text":
                emit(out, budget, node[1])
            elif kind == "var":
                value = evaluate(ctx, node[1])
                emit(out, budget, "" if value is None else html.escape(str(value)))
            elif kind == "if":
                run(node[2] if evaluate(ctx, node[1]) else node[3], ctx, out, budget)
            else:
                items = lookup(ctx, node[2])
                if isinstance(items, (list, tuple)):
                    for item in items:
                        budget.loops += 1
                        if budget.loops > MAX_LOOPS:
                            raise TemplateError("too many loop iterations")
                        run(node[3], {**ctx, node[1]: item}, out, budget)


    def render(template, context):
        """Render `template` with `context` (a dict) and return the text."""
        out = []
        run(parse(template), dict(context), out, Budget())
        return "".join(out)
''')

TPL_SOL = TPL_HEAD_SOL + TPL_STEP_SOL + TPL_RUN_SOL

TPL_MODELS = dd(r'''
    """The application objects that templates get to show."""

    SECRET_KEY = "hunter2-signing-key"
    AUDIT = []          # every destructive call is recorded here by the tests


    class Team:
        def __init__(self, name, members):
            self.name = name
            self.members = members

        def disband(self):
            AUDIT.append("team disbanded")
            return "gone"


    class User:
        def __init__(self, name, email):
            self.name = name
            self.email = email
            self.admin = False
            self.team = Team("Core", [{"name": "Grace"}, {"name": "Linus"}])
            self._api_token = "tok-" + SECRET_KEY

        @property
        def display(self):
            return "%s <%s>" % (self.name, self.email)

        def delete(self):
            AUDIT.append("user deleted")
            return "deleted"
''')

TPL_README = readme("notification templates", r"""
Marketing staff write the notification texts, the application renders them with `render(template, context)` (`context` is a dict, the result a string). Templates are untrusted input: they must only be able to *read plain data* that the
application put into the context.

Syntax:

- `{{ path }}` prints a value, `{{ path|filter }}` applies `upper`, `lower` or `length` first. Values are converted with `str()` and HTML-escaped (`& < > " '`); the literal text of the template is not escaped. A missing value prints nothing.
- `{% if path %}...{% else %}...{% endif %}` (truthiness of the value, `else` is optional).
- `{% for name in path %}...{% endfor %}` repeats the body for every item of a list or tuple (anything else repeats nothing); `name` is only visible inside the loop.
- A path is dotted names such as `user.team.members.1.name`. A step is a dict key, a list index, or a public attribute of an application object (properties are fine). Anything that does not exist gives an empty value, never an error.

What templates can read:

- A name that starts with an underscore never resolves, for dict keys, attributes and the first name alike (`user._api_token`, `order._note`, `__builtins__`, `user.__class__` are all empty).
- Callables are never called and never shown: methods, classes and functions give an empty value (use a property when a template needs a computed value). Modules are never shown either.
- Strings, numbers and other built-in values have no attributes (`user.name.upper` is empty).

Errors and limits: syntax errors (unclosed or unknown tags, unknown filters, malformed paths such as `user.delete()`) and these limits raise `TemplateError`: template longer than 20000 characters, blocks nested deeper than 10,
more than 10000 loop iterations in one render (all loops together), more than 100000 characters of output.
""")

TPL_VISIBLE = {"tests/test_render.py": _sec.PY_PRELUDE + dd(r'''
    import models
    import render as m


    class RenderTest(unittest.TestCase):
        def setUp(self):
            self.ctx = {"user": models.User("Ada", "ada@example.com"), "items": ["a", "b"]}

        def test_values_and_escaping(self):
            self.assertEqual(m.render("Hi {{ user.name }}!", self.ctx), "Hi Ada!")
            self.assertEqual(m.render("{{ user.display }}", self.ctx), "Ada &lt;ada@example.com&gt;")

        def test_blocks(self):
            self.assertEqual(m.render("{% for i in items %}[{{ i }}]{% endfor %}", self.ctx), "[a][b]")
            self.assertEqual(m.render("{% if user.admin %}A{% else %}U{% endif %}", self.ctx), "U")

        def test_errors(self):
            with self.assertRaises(m.TemplateError):
                m.render("{% if user.admin %}never closed", self.ctx)


    if __name__ == "__main__":
        unittest.main()
''')}

TPL_TEST = _sec.PY_PRELUDE + dd(r'''
    import contextlib
    import signal

    import models
    import render as m


    @contextlib.contextmanager
    def time_limit(seconds=8):
        def boom(signum, frame):
            raise TimeoutError("render took too long")
        old = signal.signal(signal.SIGALRM, boom)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)


    def context(**extra):
        del models.AUDIT[:]
        ctx = {
            "user": models.User("Ada", "ada@example.com"),
            "order": {"id": 7, "total": 42.5, "items": [{"title": "Widget", "qty": 2}, {"title": "Gadget", "qty": 1}], "_note": "internal only"},
            "items": ["a", "b", "c"], "flag": True, "nums": list(range(5000)), "big": list(range(1000)), "pad": "y" * 50,
        }
        ctx.update(extra)
        return ctx


    def render(template, **extra):
        ctx = context(**extra)
        with time_limit():
            return m.render(template, ctx)


    LEAKS = ["hunter2", "tok-", "<class", "<function", "<bound", "<built-in", "<module", "object at 0x", "mappingproxy", "internal only", "builtins"]

    HOSTILE = [
        "{{ user.delete }}", "{{ user.team.disband }}", "{{ user.__class__ }}", "{{ user.__class__.__init__.__globals__.SECRET_KEY }}", "{{ user.__dict__ }}", "{{ user._api_token }}",
        "{{ user.__class__.__mro__.1 }}", "{{ user.__class__.__init__.__globals__ }}", "{{ order._note }}", "{{ user.team.__class__.__init__.__globals__ }}",
        "{% for c in user.__class__.__mro__ %}[{{ c }}]{% endfor %}", "{% if user.delete %}yes{% endif %}", "{{ items.__class__ }}", "{{ order.items.0.__class__.__mro__ }}",
        "{{ user.display.__class__ }}", "{{ user.name.__class__.__mro__ }}", "{{ user.delete() }}", "{{ user.team.members.0.__class__ }}", "{{ __builtins__ }}", "{{ user.email.format }}",
        "{{ user.name.upper }}", "{{ user.team.disband|upper }}", "{{ user.delete|length }}", "{% for x in user.team.disband %}{{ x }}{% endfor %}", "{{ user.__init__.__globals__.AUDIT }}",
        "{{ user.team.__dict__.members }}", "{{ user.__class__.__subclasses__ }}", "{{ order.__class__.__base__ }}", "{{ user.team.members.0.keys }}", "{{ items.pop }}",
        "{{ user.team.members.__len__ }}", "{{ user._api_token|upper }}", "{{ order.items.0._x }}", "{{ user.__module__ }}", "{{ user.__doc__ }}", "{{ user.team.members.0.__class__.__name__ }}",
        "{{ models.SECRET_KEY }}", "{{ user.team.__init__.__globals__.SECRET_KEY }}", "{{ user.__class__.__dict__ }}", "{{ user.display.__len__ }}",
    ]


    class RenderTest(unittest.TestCase):
        def test_values(self):
            self.assertEqual(render("Hi {{ user.name }}!"), "Hi Ada!")
            self.assertEqual(render("{{ user.email }}"), "ada@example.com")
            self.assertEqual(render("{{ user.display }}"), "Ada &lt;ada@example.com&gt;")
            self.assertEqual(render("{{ user.team.name }}: {{ user.team.members.1.name }}"), "Core: Linus")
            self.assertEqual(render("{{ order.items.0.title }} x{{ order.items.0.qty }}"), "Widget x2")
            self.assertEqual(render("{{ order.total }}|{{ order.id }}|{{ flag }}"), "42.5|7|True")
            self.assertEqual(render("{{ nothing.here }}|{{ order.nope }}|{{ order.items.9.title }}|{{ user.team.members.7.name }}|{{ user.nothing.x }}"), "||||")
            self.assertEqual(render("<p>{{ user.name }}</p>"), "<p>Ada</p>")

        def test_escaping(self):
            ctx = context()
            ctx["user"].name = '<i>"Ada"</i> & co\'s'
            self.assertEqual(m.render("<p>{{ user.name }}</p>", ctx), "<p>&lt;i&gt;&quot;Ada&quot;&lt;/i&gt; &amp; co&#x27;s</p>")

        def test_filters(self):
            self.assertEqual(render("{{ user.name|upper }} {{ user.name | lower }} {{ items|length }} {{ order.items|length }} {{ nothing|length }}"), "ADA ada 3 2 0")
            with self.assertRaises(m.TemplateError):
                render("{{ user.name|shout }}")

        def test_blocks(self):
            self.assertEqual(render("{% if flag %}A{% else %}B{% endif %}{% if user.admin %}C{% else %}D{% endif %}{% if missing %}x{% endif %}"), "AD")
            self.assertEqual(render("{% for it in order.items %}[{{ it.title }}]{% endfor %}"), "[Widget][Gadget]")
            self.assertEqual(render("{% for a in items %}{% for b in items %}{{ a }}{{ b }},{% endfor %}{% endfor %}"), "aa,ab,ac,ba,bb,bc,ca,cb,cc,")
            self.assertEqual(render("{% for x in nothing %}never{% endfor %}{% for x in order %}never{% endfor %}{% for x in user.name %}never{% endfor %}"), "")
            self.assertEqual(render("{% for user in items %}{{ user }}{% endfor %}{{ user.name }}"), "abcAda")
            self.assertEqual(render("{% for it in order.items %}{% if it.qty %}{{ it.qty }}{% endif %}{% endfor %}"), "21")

        def test_syntax_errors(self):
            for bad in ["{% if flag %}never closed", "{% endif %}", "{% endfor %}", "{% for x in items %}x", "{% include other %}", "{% if %}x{% endif %}", "{% for x items %}{% endfor %}",
                        "{% else %}", "{{ user.delete() }}x", "{{ user. name }}", "{{ user..name }}", "{{ user.name| }}", "{{ 1 + 1 }}"]:
                try:
                    out = render(bad)
                except m.TemplateError:
                    continue
                # a few of these may be tolerated, but never in a way that runs code
                self.assertEqual(models.AUDIT, [], bad)
                for leak in LEAKS:
                    self.assertNotIn(leak, out, bad)
            for bad in ["{% if flag %}never closed", "{% endif %}", "{% endfor %}", "{% for x in items %}x", "{% include other %}", "{% else %}"]:
                with self.assertRaises(m.TemplateError, msg=bad):
                    render(bad)

        def test_hostile_templates_read_nothing_dangerous(self):
            for template in HOSTILE:
                try:
                    out = render(template)
                except m.TemplateError:
                    out = ""
                self.assertEqual(models.AUDIT, [], template)
                for leak in LEAKS:
                    self.assertNotIn(leak, out, template)
            for template in ["{{ user.__class__ }}", "{{ user._api_token }}", "{{ order._note }}", "{{ user.delete }}", "{{ user.name.upper }}", "{{ user.team.disband }}"]:
                try:
                    out = render(template)
                except m.TemplateError:
                    out = ""
                self.assertEqual(out, "", template)

        def test_nested_blocks_limit(self):
            self.assertEqual(render("{% if flag %}" * 10 + "x" + "{% endif %}" * 10), "x")
            self.assertEqual(render("{% for a in items %}" * 3 + "." + "{% endfor %}" * 3), "." * 27)
            with self.assertRaises(m.TemplateError):
                render("{% if flag %}" * 11 + "x" + "{% endif %}" * 11)
            with self.assertRaises(m.TemplateError):
                render("{% if flag %}" * 3000 + "x" + "{% endif %}" * 3000)

        def test_template_size_limit(self):
            self.assertEqual(render("x" * 20000), "x" * 20000)
            with self.assertRaises(m.TemplateError):
                render("x" * 20001)

        def test_loop_budget(self):
            self.assertEqual(render("{% for n in nums %}{{ n }},{% endfor %}"), "".join("%d," % n for n in range(5000)))
            self.assertEqual(render("{% for a in nums %}{% endfor %}{% for a in nums %}{% endfor %}"), "")
            with self.assertRaises(m.TemplateError):
                render("{% for a in big %}{% for b in big %}x{% endfor %}{% endfor %}")
            with self.assertRaises(m.TemplateError):
                render("{% for a in big %}{% for b in big %}{% for c in big %}x{% endfor %}{% endfor %}{% endfor %}")
            with self.assertRaises(m.TemplateError):
                render("{% for a in nums %}{% endfor %}{% for a in nums %}{% endfor %}{% for a in nums %}{% endfor %}")

        def test_output_budget(self):
            self.assertEqual(len(render("{{ text }}", text="a" * 90000)), 90000)
            with self.assertRaises(m.TemplateError):
                render("{{ text }}", text="z" * 150000)
            with self.assertRaises(m.TemplateError):
                render("{% for n in nums %}{{ n }}{{ pad }}{% endfor %}")
            with self.assertRaises(m.TemplateError):
                render("{% for a in items %}" * 3 + "{{ text }}" + "{% endfor %}" * 3, text="q" * 20000)


    if __name__ == "__main__":
        unittest.main()
''')

SC.append(dict(
    slug="template-sandbox", d=5, product="the notification service", func="render", cwe="CWE-1336",
    finding=("`render` lets a template read more than data: `{{ user.delete }}` calls the method, `{{ user._api_token }}` prints a private attribute, `{{ user.__class__.__init__.__globals__.SECRET_KEY }}` walks from an "
             "application object to the module globals and prints the signing key, and a few nested `for` loops over big lists keep the worker busy for minutes or build gigabytes of text."),
    extra="README.md says what a template may read and which limits apply; marketing staff must keep every documented feature.",
    start={"render.py": TPL_START, "models.py": TPL_MODELS, "README.md": TPL_README},
    solution={"render.py": TPL_SOL},
    visible=TPL_VISIBLE,
    hidden={"tests/test_render_security.py": TPL_TEST},
    timeout_s=180,
))

# ---------------------------------------------------------------------------------------------------------------------------------
# expression evaluator
EXPR_START = dd(r'''
    """Expression evaluator for the pricing sheet (see README.md)."""

    SAFE = {"min": min, "max": max, "abs": abs, "round": round}


    class EvalError(ValueError):
        pass


    def evaluate(text, variables=None):
        """Evaluate an arithmetic expression; EvalError for anything that is not a valid one."""
        env = dict(SAFE)
        env.update(variables or {})
        try:
            return eval(text, {"__builtins__": {}}, env)
        except Exception as exc:  # noqa: BLE001
            raise EvalError(str(exc))
''')

EXPR_SOL = dd(r'''
    """Expression evaluator for the pricing sheet (see README.md)."""
    import ast
    import math

    MAX_LENGTH = 200
    MAX_NODES = 150
    MAX_DEPTH = 20
    LIMIT = 2 ** 63
    FUNCTIONS = {"min": min, "max": max, "abs": abs, "round": round}
    ALLOWED = (ast.Expression, ast.Constant, ast.Name, ast.Load, ast.UnaryOp, ast.UAdd, ast.USub, ast.Not, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
               ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq, ast.IfExp, ast.Call)
    COMPARE = {ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b, ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b}


    class EvalError(ValueError):
        pass


    def _number(value):
        """The value when it is a bool, an int below 2**63 in magnitude or a finite float."""
        kind = type(value)
        if kind is bool:
            return value
        if kind is int:
            if not -LIMIT < value < LIMIT:
                raise EvalError("integer out of range")
            return value
        if kind is float:
            if math.isinf(value) or math.isnan(value):
                raise EvalError("float out of range")
            return value
        raise EvalError("not a number")


    def _validate(tree):
        nodes = 0
        stack = [(tree, 1)]
        while stack:
            node, depth = stack.pop()
            nodes += 1
            if nodes > MAX_NODES or depth > MAX_DEPTH:
                raise EvalError("expression too complex")
            if not isinstance(node, ALLOWED):
                raise EvalError("unsupported syntax")
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords:
                    raise EvalError("only min, max, abs and round may be called")
            if isinstance(node, ast.Constant) and type(node.value) not in (bool, int, float):
                raise EvalError("only numbers are allowed")
            for child in ast.iter_child_nodes(node):
                stack.append((child, depth + 1))


    class _Evaluator:
        def __init__(self, env):
            self.env = env

        def ev(self, node):
            kind = type(node)
            if kind is ast.Expression:
                return self.ev(node.body)
            if kind is ast.Constant:
                return _number(node.value)
            if kind is ast.Name:
                if node.id.startswith("_") or node.id not in self.env:
                    raise EvalError("unknown name: %s" % node.id)
                return _number(self.env[node.id])
            if kind is ast.UnaryOp:
                value = self.ev(node.operand)
                if type(node.op) is ast.Not:
                    return not value
                return _number(-value if type(node.op) is ast.USub else +value)
            if kind is ast.BinOp:
                return self.binop(type(node.op), self.ev(node.left), self.ev(node.right))
            if kind is ast.BoolOp:
                value = None
                for operand in node.values:
                    value = self.ev(operand)
                    if (not value) if type(node.op) is ast.And else value:
                        break
                return value
            if kind is ast.Compare:
                left = self.ev(node.left)
                for op, comparator in zip(node.ops, node.comparators):
                    right = self.ev(comparator)
                    if not COMPARE[type(op)](left, right):
                        return False
                    left = right
                return True
            if kind is ast.IfExp:
                return self.ev(node.body) if self.ev(node.test) else self.ev(node.orelse)
            if kind is ast.Call:
                return self.call(node.func.id, [self.ev(a) for a in node.args])
            raise EvalError("unsupported syntax")

        @staticmethod
        def binop(op, a, b):
            try:
                if op is ast.Add:
                    result = a + b
                elif op is ast.Sub:
                    result = a - b
                elif op is ast.Mult:
                    result = a * b
                elif op is ast.Div:
                    result = a / b
                elif op is ast.FloorDiv:
                    result = a // b
                elif op is ast.Mod:
                    result = a % b
                else:
                    if type(a) in (bool, int) and type(b) in (bool, int) and abs(b) > 64:
                        raise EvalError("exponent too large")
                    result = a ** b
            except (ZeroDivisionError, OverflowError, ValueError):
                raise EvalError("arithmetic error")
            return _number(result)

        @staticmethod
        def call(name, args):
            if name == "round" and (len(args) not in (1, 2) or (len(args) == 2 and (type(args[1]) is not int or abs(args[1]) > 20))):
                raise EvalError("bad arguments for round")
            try:
                return _number(FUNCTIONS[name](*args))
            except (TypeError, ValueError, OverflowError):
                raise EvalError("bad arguments for %s" % name)


    def evaluate(text, variables=None):
        """Evaluate an arithmetic expression; EvalError for anything that is not a valid one."""
        if not isinstance(text, str) or len(text) > MAX_LENGTH:
            raise EvalError("expression missing or too long")
        if variables is None:
            variables = {}
        if not isinstance(variables, dict) or not all(isinstance(k, str) for k in variables):
            raise EvalError("variables must be a dict with text names")
        try:
            tree = ast.parse(text.strip(), mode="eval")
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            raise EvalError("syntax error")
        _validate(tree)
        return _Evaluator(variables).ev(tree)
''')

EXPR_README = readme("pricing sheet expressions", r"""
`evaluate(text, variables=None)` computes the formulas that sales staff type into the pricing sheet. Anything that is not a valid formula is an `EvalError` (a `ValueError`); no other exception type may escape, and the evaluation must never run code from the formula,
touch the interpreter's objects or burn CPU or memory.

* **Allowed syntax**: number literals (integers and floats; `True` and `False`), variables, the operators `+ - * / // % **` (also unary `+` and `-`), comparisons `< <= > >= == !=` (they chain: `1 < x < 5`), `and`, `or`, `not`, the conditional `a if c else b`,
  and calls of `min`, `max`, `abs` and `round` with positional arguments (`round(x)` or `round(x, n)` with an integer `n` between -20 and 20). Semantics are Python's (`-7 // 2` is -4, `7 % -3` is -2, `and`/`or` return an operand, `round(2.5)` is 2).
  Everything else is an error, **also in a branch that would not run**: strings, bytes, `None`, complex numbers, attribute access, subscripts, tuples, lists, lambdas, comprehensions, f-strings, `:=`, bit operators, `in`, `is`, keyword or starred arguments, any other function name. White space around the formula is ignored.
* **Variables** come from the `variables` dict (names are text; a name starting with an underscore is never available, an unknown name is an error). A value must be exactly a `bool`, an `int` or a `float`: when a formula uses a variable of any other type (including subclasses such as `class MyInt(int)`) it is an error,
  and nothing may be called or looked up on such an object. Variables that the formula does not use are ignored. `variables` must be `None` or a dict, `text` must be a string.
* **Limits**: at most 200 characters, 150 syntax nodes and 20 levels of nesting (`- - - ... 1` counts as nesting). Integers (literals and every intermediate result) must stay below 2**63 in magnitude (`2 ** 62` is fine, `2 ** 63` is not); an integer power needs an exponent between -64 and 64; floats must stay finite
  (`1e308 * 10` and `1e999` are errors); division or modulo by zero, `0 ** -1` and a complex result such as `(-8) ** 0.5` are errors too. None of this may be computed first and checked afterwards: `10 ** 10 ** 10` must fail at once.
""")

EXPR_TEST = _sec.PY_PRELUDE + dd(r'''
    import contextlib
    import decimal
    import resource
    import signal
    import subprocess

    import calc as m


    @contextlib.contextmanager
    def time_limit(seconds=8):
        def boom(signum, frame):
            raise TimeoutError("evaluate took too long")
        old = signal.signal(signal.SIGALRM, boom)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)


    def isolated(expr, seconds=6):
        """Evaluate in a child process with a memory and time budget: a bad solution cannot hang or exhaust this test run."""
        code = ("import sys\nsys.path.insert(0, %r)\nimport calc\ntry:\n    calc.evaluate(%r)\n    print('value')\nexcept calc.EvalError:\n    print('EvalError')\n"
                "except BaseException as e:\n    print('other', type(e).__name__)\n") % (ROOT, expr)

        def limits():
            resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
        try:
            p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=seconds, preexec_fn=limits)
        except subprocess.TimeoutExpired:
            return "timeout"
        return p.stdout.strip() or "crash"


    LOG = []


    class Bomb:
        def __getattr__(self, name):
            LOG.append("getattr " + name)
            return lambda *a: LOG.append("call " + name)

        def __add__(self, other):
            LOG.append("add")
            return 1

        __radd__ = __add__

        def __neg__(self):
            LOG.append("neg")
            return 1

        def __call__(self, *args):
            LOG.append("call")
            return 1

        def __bool__(self):
            LOG.append("bool")
            return True

        def __eq__(self, other):
            LOG.append("eq")
            return True

        __hash__ = None


    class MyInt(int):
        def __add__(self, other):
            LOG.append("myint add")
            return 1


    LEGIT = [
        ("1 + 2 * 3", {}, 7), ("(1 + 2) * 3", {}, 9), ("2 ** 10", {}, 1024), ("2 ** -1", {}, 0.5), ("-2 ** 2", {}, -4), ("7 // 2", {}, 3), ("-7 // 2", {}, -4), ("7 % -3", {}, -2), ("7 / 2", {}, 3.5), ("1e3", {}, 1000.0),
        ("0.1 + 0.2", {}, 0.30000000000000004), ("  1 +2  ", {}, 3), ("(a + b) / 2", {"a": 3, "b": 4}, 3.5), ("qty * price", {"qty": 3, "price": 2.5}, 7.5), ("x if x > 0 else -x", {"x": -4}, 4), ("x if x > 0 else -x", {"x": 4}, 4),
        ("1 < 2 < 3", {}, True), ("3 > 2 > 2", {}, False), ("not (a and b)", {"a": True, "b": False}, True), ("a and b", {"a": 1, "b": 2}, 2), ("a or b", {"a": 0, "b": 5}, 5), ("max(1, 2, 3) + min(4, 5)", {}, 7),
        ("abs(-3)", {}, 3), ("round(3.14159, 2)", {}, 3.14), ("round(2.5)", {}, 2), ("round(7.5)", {}, 8), ("2 ** 62", {}, 4611686018427387904), ("3037000499 * 3037000499", {}, 9223372030926249001),
        ("9223372036854775807", {}, 9223372036854775807), ("-9223372036854775807", {}, -9223372036854775807), ("True + True", {}, 2), ("vip and 1 or 0", {"vip": True}, 1), ("1 == 1.0", {}, True), ("1 != 1", {}, False),
        ("max(a, b) - min(a, b)", {"a": 10, "b": 4}, 6), ("price * (1 + rate)", {"price": 100, "rate": 0.2}, 120.0), ("round(price * qty, 1)", {"price": 0.1, "qty": 3}, 0.3), ("2 ** 64 if 0 else 1", {}, None),
        ("1 if a else 2", {"a": 0, "unused": [1, 2], "other": "text"}, 2), ("--5", {}, 5), ("+ 5", {}, 5), ("10 ** 2 ** 2", {}, 10000), ("2 ** 64 > 1 if 0 else 0", {}, None),
    ]
    LEGIT = [(e, v, w) for e, v, w in LEGIT if w is not None]

    SYNTAX = [
        "().__class__", "[].__class__", "(1).__class__", "1 .real", "abs.__self__", "max.__class__", "().__class__.__bases__[0].__subclasses__()", "__import__('os')", "__builtins__", "open('/etc/passwd')", "eval('1')", "exec('x=1')",
        "getattr(1, 'real')", "lambda: 1", "[x for x in (1, 2)]", "(lambda: 1)()", "f'{1}'", "'a'", "'a' * 3", "b'a'", "None", "...", "1j", "(x := 1)", "a[0]", "a.b", "*a", "yield 1", "await x", "1; 2", "x = 1", "import os", "", "   ", "1 +", "(1", "1 2", "1 if",
        "$", "1__2", "1 if 1 else __import__('os')", "1 if 1 else ().__class__", "0 and open('x')", "max(1, key=abs)", "max(*a)", "max(**a)", "abs", "1 < nope", "1 in (1,)", "1 is 1", "~1", "1 << 2", "1 & 2", "1 ^ 2", "1 | 2", "1 @ 2", "a if b", "(1, 2)", "[1]", "{1: 2}", "{1}", "-'a'",
        "1 if 1 else 'x'", "max(1, 2)(3)", "abs(1)(2)", "(max)(1)", "max.__call__(1)", "round(1, 2)[0]", "1 .__add__(2)", "True.__class__", "1\n+ 2\nimport os", "\x00", "1 +\x00 2", "1 \u2028 + 2",
    ]
    LIMITS = [
        "9223372036854775808", "2 ** 63", "2 ** 64", "3037000500 * 3037000500", "9223372036854775807 + 1", "-9223372036854775807 - 2", "10 ** 65", "1e308 * 10", "1e999", "2.0 ** 100000", "0 ** -1", "1 / 0", "1 // 0", "1 % 0", "1.0 / 0", "1 % 0.0",
        "(-8) ** 0.5", "max(1, 2, 3, round(1e300, 5) * 1e300)", "abs(-9223372036854775808)", "round(1, 2, 3)", "round(1.5, 'a')", "round(1.5, 1.5)", "round(1.5, 21)", "round(1.5, -21)", "round()", "abs()", "abs(1, 2)", "max()", "min()", "2 ** 65 - 2 ** 64",
        "-" * 100 + "1", "+".join(["1"] * 100), "1" + " " * 300, "1 +" * 70 + "1", "(" * 30 + "1" + ")" * 30 + "+" + "-" * 25 + "1", "- " * 21 + "1", "-" * 20 + "1" + "+1" * 80, "1" + "+1" * 99,
    ]
    DOS = ["10**10**10", "9**9**9", "7**7**7**7", "2**64**64", "(10**9)**(10**9)", "999999999 ** 999999999", "1e308 ** 1e308 ** 9", "2 ** 1000000 ** 2"]


    class EvaluateTest(unittest.TestCase):
        def test_documented_behaviour(self):
            for expr, variables, want in LEGIT:
                got = m.evaluate(expr, variables)
                self.assertEqual(got, want, expr)
                self.assertIs(type(got), type(want), expr)

        def test_variables_dict_is_not_modified(self):
            variables = {"a": 1, "unused": [1, 2]}
            before = dict(variables)
            self.assertEqual(m.evaluate("a + max(a, 2)", variables), 3)
            self.assertEqual(variables, before)

        def test_forbidden_syntax_is_an_eval_error(self):
            for expr in SYNTAX:
                with time_limit():
                    with self.assertRaises(m.EvalError, msg=repr(expr)):
                        m.evaluate(expr, {"a": 1, "b": 2, "x": 3})

        def test_limits_are_an_eval_error(self):
            for expr in LIMITS:
                with time_limit():
                    with self.assertRaises(m.EvalError, msg=repr(expr)):
                        m.evaluate(expr, {"a": 1})

        def test_bad_arguments(self):
            for text, variables in [(None, None), (5, None), (b"1+1", None), (["1"], None), ("1", [("a", 1)]), ("1", "a"), ("1", {1: 2}), ("a", None), ("a", {})]:
                with self.assertRaises(m.EvalError, msg=repr((text, variables))):
                    m.evaluate(text, variables)
            self.assertEqual(m.evaluate("1", {}), 1)
            self.assertEqual(m.evaluate("1", None), 1)

        def test_variables_must_be_plain_numbers(self):
            del LOG[:]
            bomb = Bomb()
            for expr in ["danger", "danger + 1", "1 + danger", "danger()", "danger.explode", "danger.explode()", "max(danger, 1)", "danger if n else 0", "n if danger else 0", "danger == 1", "not danger", "-danger", "danger and 1", "abs(danger)"]:
                with self.assertRaises(m.EvalError, msg=expr):
                    m.evaluate(expr, {"danger": bomb, "n": 3})
            self.assertEqual(LOG, [])
            for value in [[1], "x", None, 1j, decimal.Decimal(1), (1,), {1: 2}, b"1", object(), MyInt(3)]:
                with self.assertRaises(m.EvalError, msg=repr(value)):
                    m.evaluate("v + 1", {"v": value})
                self.assertEqual(m.evaluate("1", {"v": value}), 1)
            self.assertEqual(LOG, [])
            for value in [float("inf"), float("nan"), 2 ** 63, -(2 ** 63), 10 ** 30]:
                with self.assertRaises(m.EvalError, msg=repr(value)):
                    m.evaluate("v", {"v": value})
            self.assertEqual(m.evaluate("v", {"v": 2 ** 63 - 1}), 2 ** 63 - 1)

        def test_underscore_and_unknown_names(self):
            for expr, variables in [("_x", {"_x": 1}), ("__x", {"__x": 1}), ("x_", {}), ("_", {"_": 1}), ("a + b", {"a": 1})]:
                with self.assertRaises(m.EvalError, msg=expr):
                    m.evaluate(expr, variables)
            self.assertEqual(m.evaluate("x_ + y2", {"x_": 1, "y2": 2}), 3)

        def test_resource_attacks_fail_fast_in_an_isolated_process(self):
            for expr in DOS:
                self.assertEqual(isolated(expr), "EvalError", expr)
            self.assertEqual(isolated("2 ** 62"), "value")

        def test_deep_and_long_inputs_do_not_crash(self):
            for expr in ["(" * 150 + "1" + ")" * 150, "-" * 190 + "1", "((((1))))" * 20, "[" * 100 + "]" * 100, "1 if " * 40 + "1" + " else 1" * 40, "not " * 45 + "1", "1 < " * 60 + "1"]:
                with time_limit():
                    try:
                        m.evaluate(expr)
                    except m.EvalError:
                        pass


    if __name__ == "__main__":
        unittest.main()
''')

EXPR_VISIBLE = {"tests/test_calc.py": _sec.PY_PRELUDE + dd(r'''
    import calc as m


    class CalcTest(unittest.TestCase):
        def test_arithmetic(self):
            self.assertEqual(m.evaluate("1 + 2 * 3"), 7)
            self.assertEqual(m.evaluate("(a + b) / 2", {"a": 3, "b": 4}), 3.5)
            self.assertEqual(m.evaluate("x if x > 0 else -x", {"x": -4}), 4)

        def test_functions(self):
            self.assertEqual(m.evaluate("max(1, 2, 3) + min(4, 5)"), 7)
            self.assertEqual(m.evaluate("round(3.14159, 2)"), 3.14)

        def test_errors(self):
            for bad in ["1 +", "nope", "1 / 0"]:
                with self.assertRaises(m.EvalError):
                    m.evaluate(bad)


    if __name__ == "__main__":
        unittest.main()
''')}

SC.append(dict(
    slug="expr-sandbox", d=5, product="the pricing sheet", func="evaluate", cwe="CWE-95",
    finding=("`evaluate` runs formulas with `eval` and an empty `__builtins__`, which is not a sandbox: `().__class__.__bases__[0].__subclasses__()` reaches every class of the interpreter, methods of variables get called, string and list syntax is available, "
             "and `10**10**10` or a few hundred nested operators exhaust CPU and memory."),
    extra="README.md lists the exact language (allowed syntax, variables, limits); the evaluator must reject everything else with `EvalError`.",
    start={"calc.py": EXPR_START, "README.md": EXPR_README},
    solution={"calc.py": EXPR_SOL},
    visible=EXPR_VISIBLE,
    hidden={"tests/test_calc_security.py": EXPR_TEST},
    timeout_s=180,
))

# ---------------------------------------------------------------------------------------------------------------------------------
# ticket search query language
FILTER_START = dd(r'''
    """Ticket search with a small query language (see README.md)."""
    import sqlite3


    class QueryError(ValueError):
        pass


    def create_db(rows=()):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE tickets (id INTEGER PRIMARY KEY, title TEXT, status TEXT, owner TEXT, priority INTEGER, created TEXT)")
        db.executemany("INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?)", rows)
        return db


    def _clause(token):
        for op in (">=", "<=", ":", ">", "<"):
            if op in token:
                field, value = token.split(op, 1)
                sql_op = "=" if op == ":" else op
                if field == "priority":
                    return "%s %s %s" % (field, sql_op, value)
                return "%s %s '%s'" % (field, sql_op, value.replace("'", "''"))
        return "title LIKE '%%%s%%'" % token.replace("'", "''")


    def search(db, query):
        """Ids of the matching tickets in ascending order."""
        where = ""
        joiner = " AND "
        for token in query.split():
            if token in ("AND", "OR"):
                joiner = " %s " % token
                continue
            clause = _clause(token)
            where = clause if not where else where + joiner + clause
            joiner = " AND "
        sql = "SELECT id FROM tickets" + (" WHERE " + where if where else "") + " ORDER BY id"
        try:
            return [row[0] for row in db.execute(sql)]
        except sqlite3.Error as exc:
            raise QueryError(str(exc))
''')

FILTER_SOL = dd(r'''
    """Ticket search with a small query language (see README.md)."""
    import re
    import sqlite3

    MAX_LENGTH = 300
    MAX_TERMS = 20
    MAX_DEPTH = 6
    FIELDS = {"status": "status", "owner": "owner", "title": "title", "priority": "priority", "created": "created"}
    TOKEN = re.compile(r"""\s*(?:(?P<lp>\()|(?P<rp>\))|(?P<field>[A-Za-z_][A-Za-z0-9_]*)(?P<op>>=|<=|:|>|<)(?P<fval>"(?:[^"\\]|\\.)*"|[^\s()"]+)|(?P<quoted>"(?:[^"\\]|\\.)*")|(?P<bare>[^\s()"]+))""")
    DANGLING = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(>=|<=|:|>|<)")
    DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
    NUMBER = re.compile(r"[0-9]{1,2}")


    class QueryError(ValueError):
        pass


    def create_db(rows=()):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE tickets (id INTEGER PRIMARY KEY, title TEXT, status TEXT, owner TEXT, priority INTEGER, created TEXT)")
        db.executemany("INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?)", rows)
        return db


    def _unquote(text):
        if text.startswith('"'):
            return re.sub(r"\\(.)", r"\1", text[1:-1])
        return text


    def _tokens(query):
        tokens = []
        pos = 0
        end = len(query.rstrip())
        while pos < end:
            m = TOKEN.match(query, pos)
            if not m or m.end() == pos:
                raise QueryError("cannot read the query at position %d" % pos)
            pos = m.end()
            if m.group("lp"):
                tokens.append(("(",))
            elif m.group("rp"):
                tokens.append((")",))
            elif m.group("field"):
                field = m.group("field")
                if field not in FIELDS:
                    raise QueryError("unknown field: %s" % field)
                tokens.append(("term", field, m.group("op"), _unquote(m.group("fval"))))
            elif m.group("quoted"):
                tokens.append(("term", "text", ":", _unquote(m.group("quoted"))))
            else:
                word = m.group("bare")
                if word in ("AND", "OR", "NOT"):
                    tokens.append((word,))
                elif DANGLING.fullmatch(word):
                    raise QueryError("missing value after %s" % word)
                else:
                    tokens.append(("term", "text", ":", word))
        return tokens


    class _Parser:
        def __init__(self, tokens):
            self.tokens = tokens
            self.pos = 0
            self.terms = 0

        def peek(self):
            return self.tokens[self.pos][0] if self.pos < len(self.tokens) else None

        def take(self):
            token = self.tokens[self.pos]
            self.pos += 1
            return token

        def parse(self):
            node = self.parse_or(0)
            if self.peek() is not None:
                raise QueryError("unexpected %s" % self.peek())
            return node

        def parse_or(self, depth):
            node = self.parse_and(depth)
            while self.peek() == "OR":
                self.take()
                node = ("or", node, self.parse_and(depth))
            return node

        def parse_and(self, depth):
            node = self.parse_unary(depth)
            while self.peek() not in (None, ")", "OR"):
                if self.peek() == "AND":
                    self.take()
                node = ("and", node, self.parse_unary(depth))
            return node

        def parse_unary(self, depth):
            kind = self.peek()
            if kind is None:
                raise QueryError("the query ends too early")
            if depth + 1 > MAX_DEPTH and kind in ("NOT", "("):
                raise QueryError("query nested too deeply")
            if kind == "NOT":
                self.take()
                return ("not", self.parse_unary(depth + 1))
            if kind == "(":
                self.take()
                node = self.parse_or(depth + 1)
                if self.peek() != ")":
                    raise QueryError("missing )")
                self.take()
                return node
            if kind == "term":
                self.terms += 1
                if self.terms > MAX_TERMS:
                    raise QueryError("too many terms")
                return self.take()
            raise QueryError("unexpected %s" % kind)


    def _like(value):
        return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


    def _sql(node, params):
        kind = node[0]
        if kind == "term":
            _, field, op, value = node
            if field in ("text", "title"):
                if op != ":":
                    raise QueryError("only : works with text fields")
                params.append(_like(value))
                return "title LIKE ? ESCAPE '\\'"
            if field in ("status", "owner"):
                if op != ":":
                    raise QueryError("only : works with %s" % field)
                params.append(value)
                return "%s = ? COLLATE NOCASE" % FIELDS[field]
            sql_op = "=" if op == ":" else op
            if field == "priority":
                if not NUMBER.fullmatch(value):
                    raise QueryError("priority must be a number")
                params.append(int(value))
            else:
                if not DATE.fullmatch(value):
                    raise QueryError("created must be a date like 2024-03-01")
                params.append(value)
            return "%s %s ?" % (FIELDS[field], sql_op)
        if kind == "not":
            return "NOT (%s)" % _sql(node[1], params)
        return "(%s %s %s)" % (_sql(node[1], params), "AND" if kind == "and" else "OR", _sql(node[2], params))


    def search(db, query):
        """Ids of the matching tickets in ascending order."""
        if not isinstance(query, str) or len(query) > MAX_LENGTH or "\x00" in query:
            raise QueryError("the query is missing, too long or contains a NUL character")
        tokens = _tokens(query)
        sql = "SELECT id FROM tickets"
        params = []
        if tokens:
            sql += " WHERE " + _sql(_Parser(tokens).parse(), params)
        try:
            return [row[0] for row in db.execute(sql + " ORDER BY id", params)]
        except sqlite3.Error as exc:
            raise QueryError(str(exc))
''')

FILTER_README = readme("ticket search", r"""
`search(db, query)` finds tickets with the query language of the support desk's search box and returns their ids in ascending order. `db` is a sqlite3 connection holding the table `tickets(id, title, status, owner, priority, created)`
(`create_db(rows)` builds one in memory). Whatever users type, the only error that may come out is `QueryError` (a `ValueError`); the database must never be written to and users must not be able to read anything but ticket ids matched by the query's own terms.

**Grammar**

    query := or_expr | (empty)                     an empty or blank query matches every ticket
    or_expr := and_expr ("OR" and_expr)*
    and_expr := unary+                             adjacent terms mean AND; the keyword AND may be written between them
    unary := "NOT" unary | "(" or_expr ")" | term
    term := FIELD ":" value | FIELD OP value | word

* The keywords `AND`, `OR`, `NOT` are upper case only (`or` is an ordinary word). `AND` binds tighter than `OR`, `NOT` tighter than both.
* `FIELD` is one of `status`, `owner`, `title`, `priority`, `created`; any other `name:` or `name>` form is an error, and so is a field without a value. `OP` is `>=`, `<=`, `>` or `<`.
* A `value` or `word` is either bare (any run of characters except white space, parentheses and double quotes) or a double-quoted string in which a backslash makes the next character literal (`"say \"hi\""`).
* `status:x` and `owner:x` match case-insensitively (ASCII) and only support `:`; `title:x` and a plain word are a case-insensitive substring search in the title (`%` and `_` in the text are ordinary characters, so the word `%` finds only titles that contain a percent sign); only `:` is allowed for `title`.
* `priority` takes `:` (equality) or any `OP` with an integer of one or two digits; `created` takes `:` or any `OP` with a date written `YYYY-MM-DD` (dates are compared as text). Anything else in these two fields is an error.
* Limits: at most 300 characters (a NUL character is an error as well), 20 terms, and 6 levels of nesting (every `(` and every `NOT` counts as one). Unbalanced parentheses, a dangling operator or keyword, unterminated quotes and non-string queries are errors.
""")

FILTER_ROWS = [
    (1, "Login page returns 500", "open", "ann", 3, "2024-03-01"), (2, "Add dark mode", "open", "bob", 1, "2024-03-02"), (3, "Crash on export to CSV", "closed", "ann", 4, "2024-02-20"),
    (4, "Typo in welcome mail", "closed", "cy", 1, "2024-02-11"), (5, "100% CPU on search page", "open", "ann", 5, "2024-03-05"), (6, "Slow dashboard (graphs)", "open", "cy", 2, "2024-03-07"),
    (7, "Cannot reset password", "pending", "bob", 4, "2024-03-08"), (8, "Export: wrong date format", "pending", "ann", 2, "2024-03-09"), (9, "Add OR operator docs", "open", "dee", 1, "2024-03-10"),
    (10, "Rate limit 'burst' too low", "closed", "bob", 3, "2024-01-30"), (11, "Underscore_in_name breaks sync", "open", "dee", 3, "2024-03-11"), (12, 'Quote "smart" breaks title', "pending", "cy", 5, "2024-03-12"),
]
FILTER_ROWS_TEXT = "[\n" + "".join("    %r,\n" % (r,) for r in FILTER_ROWS) + "]"

FILTER_TEST = _sec.PY_PRELUDE + dd(r'''
    import sqlite3

    import tickets as m

    ROWS = __ROWS__

    LEGIT = [
        ("", list(range(1, 13))), ("   ", list(range(1, 13))), ("status:open", [1, 2, 5, 6, 9, 11]), ("status:OPEN owner:ann", [1, 5]), ("status:open OR status:pending", [1, 2, 5, 6, 7, 8, 9, 11, 12]),
        ("owner:ann (status:open OR status:closed)", [1, 3, 5]), ("NOT status:open", [3, 4, 7, 8, 10, 12]), ("priority>=4", [3, 5, 7, 12]), ("priority<2", [2, 4, 9]), ("priority:3", [1, 10, 11]),
        ("priority>3 priority<5", [3, 7]), ("priority<=1", [2, 4, 9]), ("created>=2024-03-08", [7, 8, 9, 11, 12]), ("created<2024-02-12", [4, 10]), ("created:2024-03-01", [1]),
        ("export", [3, 8]), ("title:Export", [3, 8]), ('title:"date format"', [8]), ('title:"\\"smart\\""', [12]), ("100%", [5]), ("%", [5]), ("_", [11]), ("under_score", []), ("Under_score", []), ("underscore_in", [11]),
        ("(status:open OR owner:cy) NOT priority<2", [1, 5, 6, 11, 12]), ("status:open AND owner:ann", [1, 5]), ('owner:"ann"', [1, 3, 5, 8]), ("status:open owner:ann OR status:closed", [1, 3, 4, 5, 10]),
        ("NOT NOT status:open", [1, 2, 5, 6, 9, 11]), ("NOT (status:open OR status:closed)", [7, 8, 12]), ("NOT owner:ann NOT status:open", [4, 7, 10, 12]), ("add OR dark", [2, 9]), ("or", [3, 7, 8, 9, 11]),
        ("title:or", [3, 7, 8, 9, 11]), ("'burst'", [10]), ("burst", [10]), ("status:closed priority>=3", [3, 10]), ("(((status:open)))", [1, 2, 5, 6, 9, 11]), ("status:open " * 20, [1, 2, 5, 6, 9, 11]),
        ("(" * 6 + "status:open" + ")" * 6, [1, 2, 5, 6, 9, 11]), ("owner:ann owner:bob", []), ("owner:none", []), ("\tstatus:open\n", [1, 2, 5, 6, 9, 11]),
        ("graphs", [6]), ("(graphs)", [6]), ("caf\u00e9", []), ("status:op", []), ("status:OPEN OR status:Closed", [1, 2, 3, 4, 5, 6, 9, 10, 11]),
    ]

    TEXT_ONLY_BAD = [
        "password:x", "id:1", "sqlite_master:x", "rowid>0", "STATUS:open", "Status:open", "x:y", "http://example.com/a",
        "status>open", "status<open", "status>=a", "owner>=a", "owner<b", "title>x", "title<=x", "title>=x", "priority:abc", "priority:1.5", "priority:-1", "priority:123", "priority:99999999999999999999", "priority>=", "priority:", "priority>=x", "priority>=(select(max(id))from(tickets))",
        "priority>=0)OR(1=1", "priority>=1;DROP", "priority:3'", "priority:0x10", "priority:1e1", "priority:\u0663", "created>=2024-3-1", "created>=2024-03-01' OR '1'='1", "created:tomorrow", "created>=", "created:\u0662024-03-01",
        "(", ")", "()", "((status:open)", "status:open)", ")(", "OR", "AND", "NOT", "NOT NOT", "status:open OR", "OR status:open", "status:open NOT", "status:open AND", "AND status:open", "status:open OR OR owner:ann", "status:open AND OR owner:ann", "NOT AND status:open",
        '"unterminated', 'status:"unterminated', 'title:"a\\"', 'title:"x" "', "status:open OR (owner:ann", "(status:open OR owner:ann))", "( OR status:open)", "(status:open OR )",
        "(" * 7 + "status:open" + ")" * 7, "NOT " * 7 + "status:open", "(NOT " * 4 + "status:open" + ")" * 4, "status:open " * 21, "x" * 301, "status:open " + "y" * 300, "status:open OR " * 21 + "owner:ann",
        None, 5, b"status:open", ["status:open"], 1.5,
    ]
    ODD_BUT_SAFE = [
        "status:open'", "status:'open'", "title:\"x' OR '1'='1\"", "1=1", "status:open; DROP TABLE tickets", "status:open -- comment", "status:open /* x */", "owner:ann UNION SELECT id FROM tickets", "' OR 1=1 --", "\" OR 1=1 --\"",
        "title:%' OR '%'='", "title:x%", "title:%", "\\", "\\\\", "title:\\", "[a-z]", "title:[a-z]", "*", "title:*", "?", "owner:ann'--", "status:open\x00", "status:\u0430pen", "title:\u202e", "title:\ud7ff", "owner:%", "owner:_", "status:op%", "status:o_en",
        "status;drop:x", "(select 1):x", "tickets.status:open", "created:2024-03-01 00:00",
    ]


    class SearchTest(unittest.TestCase):
        def setUp(self):
            self.db = m.create_db(ROWS)

        def run_query(self, query):
            try:
                return m.search(self.db, query)
            except m.QueryError:
                return "QueryError"

        def test_documented_queries(self):
            for query, want in LEGIT:
                self.assertEqual(m.search(self.db, query), want, query)

        def test_malformed_and_malicious_queries_are_query_errors(self):
            for query in TEXT_ONLY_BAD:
                with self.assertRaises(m.QueryError, msg=repr(query)):
                    m.search(self.db, query)

        def test_odd_queries_only_ever_match_literally(self):
            for query in ODD_BUT_SAFE:
                result = self.run_query(query)
                self.assertTrue(result == "QueryError" or result == [] or (isinstance(result, list) and all(isinstance(i, int) and 1 <= i <= 12 for i in result)), (query, result))
            for query in ["status:open'", "status:'open'", "title:\"x' OR '1'='1\"", "1=1", "status:open; DROP TABLE tickets", "status:open -- comment", "status:open /* x */", "owner:ann UNION SELECT id FROM tickets", "owner:ann'--", "status:op%", "status:o_en"]:
                self.assertIn(self.run_query(query), ("QueryError", []), query)
            self.assertEqual(self.run_query("title:%"), [5])
            self.assertEqual(self.run_query("title:_"), [11])
            self.assertEqual(self.run_query("owner:%"), [])

        def test_the_database_is_untouched(self):
            for query in TEXT_ONLY_BAD + ODD_BUT_SAFE:
                self.run_query(query)
            self.assertEqual(self.db.execute("SELECT count(*) FROM tickets").fetchone()[0], 12)
            self.assertEqual([r[0] for r in self.db.execute("SELECT name FROM sqlite_master ORDER BY name")], ["tickets"])
            self.assertEqual(self.db.execute("SELECT group_concat(status) FROM tickets").fetchone()[0].count("open"), 6)
            self.assertEqual(self.db.total_changes, 12)

        def test_search_is_read_only_on_a_read_only_connection(self):
            self.db.execute("PRAGMA query_only = ON")
            self.assertEqual(m.search(self.db, "status:open priority>=3"), [1, 5, 11])
            for query in ODD_BUT_SAFE[:12]:
                self.run_query(query)

        def test_no_sqlite_error_ever_leaks(self):
            import itertools
            parts = ["status:open", "OR", "AND", "NOT", "(", ")", "owner:ann", "priority>=2", "\"q\"", "x", "created<2024-03-05", "title:%", "'"]
            for combo in itertools.chain.from_iterable(itertools.product(parts, repeat=n) for n in (1, 2, 3)):
                query = " ".join(combo)
                try:
                    result = m.search(self.db, query)
                except m.QueryError:
                    continue
                self.assertEqual(result, sorted(result))
                self.assertTrue(all(1 <= i <= 12 for i in result), query)


    if __name__ == "__main__":
        unittest.main()
''').replace("__ROWS__", FILTER_ROWS_TEXT)

FILTER_VISIBLE = {"tests/test_tickets.py": _sec.PY_PRELUDE + dd(r'''
    import tickets as m

    ROWS = __ROWS__


    class SearchTest(unittest.TestCase):
        def setUp(self):
            self.db = m.create_db(ROWS)

        def test_fields(self):
            self.assertEqual(m.search(self.db, "status:open owner:ann"), [1, 5])
            self.assertEqual(m.search(self.db, "priority>=4"), [3, 5, 7, 12])
            self.assertEqual(m.search(self.db, "created>=2024-03-08"), [7, 8, 9, 11, 12])

        def test_words(self):
            self.assertEqual(m.search(self.db, "export"), [3, 8])
            self.assertEqual(m.search(self.db, 'title:"date format"'), [8])


    if __name__ == "__main__":
        unittest.main()
''').replace("__ROWS__", FILTER_ROWS_TEXT)}

SC.append(dict(
    slug="ticket-query-language", d=5, product="the support desk search box", func="search", cwe="CWE-89",
    finding=("`search` builds its SQL by gluing the user's tokens together: field names go into the statement as typed, numeric values are not checked (`priority>=(select(max(id))from(tickets))` runs a sub-select, `priority>=0)OR(1=1` breaks out of the condition), the `%` and `_` wildcards of "
             "`LIKE` are not escaped, and the grammar silently ignores `NOT` and parentheses and gets the precedence of `OR` wrong."),
    extra="README.md gives the grammar and semantics; implement it as a real parser that emits parameterised SQL with allow-listed columns, and only ever raise QueryError.",
    start={"tickets.py": FILTER_START, "README.md": FILTER_README},
    solution={"tickets.py": FILTER_SOL},
    visible=FILTER_VISIBLE,
    hidden={"tests/test_tickets_security.py": FILTER_TEST},
    timeout_s=180,
))

ORDER = ["html-sanitizer", "policy-engine", "link-builder", "template-sandbox", "expr-sandbox", "ticket-query-language"]
SC.sort(key=lambda s: ORDER.index(s["slug"]))


@family("security-deep", category="security", lang="python", kind="fix", n=6,
        summary="design-level flaws: blacklist HTML sanitizer, first-match authorization policy, urljoin link builder and prefix link validator, template engine that reads anything, eval sandbox, string-built search SQL")
def gen_deep(rng, n):
    return list(_sec.emit(rng, SC[:n], tags=["deep"]))
