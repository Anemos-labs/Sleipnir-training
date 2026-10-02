"""Security families: cross-site scripting in HTML generators, and HTTP header / link injection."""
from fx import dd, family

from . import _sec

HTML_PRELUDE = _sec.PY_PRELUDE + dd('''
    from html.parser import HTMLParser


    class Collector(HTMLParser):
        """Parses generated HTML; records start tags with their attributes (in order) and all text (a <br> counts as a line feed)."""

        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.tags = []
            self.chunks = []
            self.stack = []
            self.by_tag = {}

        VOID = {"br", "img", "hr", "input", "meta", "link", "wbr"}

        def _void(self, tag):
            if tag == "br":
                self.chunks.append("\\n")
                if self.stack:
                    self.by_tag.setdefault(self.stack[-1], []).append("\\n")

        def handle_starttag(self, tag, attrs):
            self.tags.append((tag, list(attrs)))
            if tag in self.VOID:
                self._void(tag)
                return
            self.stack.append(tag)
            self.by_tag.setdefault(tag, [])

        def handle_startendtag(self, tag, attrs):
            self.tags.append((tag, list(attrs)))
            self._void(tag)

        def handle_endtag(self, tag):
            if self.stack and self.stack[-1] == tag:
                self.stack.pop()

        def handle_data(self, data):
            self.chunks.append(data)
            if self.stack:
                self.by_tag.setdefault(self.stack[-1], []).append(data)

        @property
        def text(self):
            return "".join(self.chunks)

        def text_of(self, tag):
            return "".join(self.by_tag.get(tag, []))

        @property
        def names(self):
            return [t for t, _ in self.tags]


    def parse(html):
        c = Collector()
        c.feed(html)
        c.close()
        return c


    def dangerous(url):
        """True when the (entity-decoded) URL starts with a scheme that can run code."""
        flat = "".join(ch for ch in url if ch > " " and ord(ch) != 0x7F).lower()
        return flat.startswith(("javascript:", "vbscript:", "data:"))


''')


def readme(title, body):
    return f"# {title}\n\n{body.strip()}\n"


SC = []

SC.append(dict(
    slug="comment-widget", d=1, product="the comment widget", func="render_comment", cwe="CWE-79",
    finding="`render_comment` inserts the author and the comment text into the HTML as they are, so a comment containing `<script>` (or `<img onerror=...>`) is stored XSS for everybody who views the page.",
    start={
        "widget.py": dd('''
            """HTML for the comment widget."""


            def render_comment(author, text):
                """HTML of one comment: `<div class="comment"><b>AUTHOR</b>: TEXT</div>`. Author and text are plain text supplied by users."""
                return '<div class="comment"><b>%s</b>: %s</div>' % (author, text)
        '''),
        "README.md": readme("widget", "`render_comment(author, text)` returns `<div class=\"comment\"><b>AUTHOR</b>: TEXT</div>`. Author and text are plain text: the page must show them exactly as typed (including `<`, `&`, quotes), and they must never become markup."),
    },
    solution={"widget.py": dd('''
        """HTML for the comment widget."""
        import html


        def render_comment(author, text):
            """HTML of one comment: `<div class="comment"><b>AUTHOR</b>: TEXT</div>`. Author and text are plain text supplied by users."""
            return '<div class="comment"><b>%s</b>: %s</div>' % (html.escape(author), html.escape(text))
    ''')},
    hidden={"tests/test_widget_security.py": HTML_PRELUDE + dd('''
        import widget as m


        class WidgetTest(unittest.TestCase):
            def test_text_is_text(self):
                samples = [("ann", "hello"), ("o'neil", "I <3 you & \\"you\\""), ("<b>bold</b>", "<script>alert(1)</script>"), ("x", "<img src=x onerror=alert(1)>"), ("a&amp;b", "&lt;i&gt; &#60;"), ("ünï", "snowman \\u2603 </div><div>"),
                           ("", ""), ("a", "text with 'single' and \\"double\\""), ("<!-- c -->", "<![CDATA[x]]>")]
                for author, text in samples:
                    p = parse(m.render_comment(author, text))
                    self.assertEqual(p.names, ["div", "b"], (author, text))
                    self.assertEqual(p.tags[0], ("div", [("class", "comment")]))
                    self.assertEqual(p.text, author + ": " + text, (author, text))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SC.append(dict(
    slug="link-scheme", d=2, product="the link list", func="render_link", cwe="CWE-79",
    finding="`render_link` writes the URL straight into the `href` attribute: a quote in the URL adds attributes (`\" onmouseover=\"...`), and `javascript:` URLs (also in disguised forms such as `JaVaScRiPt:`, with tabs inside, or via character references) run script when clicked.",
    start={
        "links.py": dd('''
            """Link rendering for user-submitted bookmarks."""


            def render_link(url, label):
                """HTML `<a href="URL">LABEL</a>` for a bookmark. `url` and `label` are plain text supplied by users.
                Only http, https and mailto URLs and relative URLs (no scheme) may become links; for any other scheme the href is `#`."""
                return '<a href="%s">%s</a>' % (url, label)
        '''),
        "README.md": readme("links", "`render_link(url, label)` returns `<a href=\"URL\">LABEL</a>`. The label is shown as plain text. `http`, `https` and `mailto` URLs (any letter case) and relative URLs (`/docs`, `page.html`, `?q=1`, `#top`) are kept exactly as given (after the browser decodes the attribute); a URL with any other scheme - however it is written - gets `href=\"#\"`. The element has no attributes other than `href`."),
    },
    solution={"links.py": dd('''
        """Link rendering for user-submitted bookmarks."""
        import html
        import re

        SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")


        def _safe(url):
            flat = "".join(ch for ch in url if ch > " " and ord(ch) != 0x7F)
            m = SCHEME.match(flat)
            if m and m.group(1).lower() not in ("http", "https", "mailto"):
                return "#"
            return url


        def render_link(url, label):
            """HTML `<a href="URL">LABEL</a>` for a bookmark. `url` and `label` are plain text supplied by users.
            Only http, https and mailto URLs and relative URLs (no scheme) may become links; for any other scheme the href is `#`."""
            return '<a href="%s">%s</a>' % (html.escape(_safe(url), quote=True), html.escape(label))
    ''')},
    hidden={"tests/test_links_security.py": HTML_PRELUDE + dd('''
        import links as m


        class LinkTest(unittest.TestCase):
            def test_kept(self):
                for url in ["https://example.com/?a=1&b=2", "http://x.io/path", "HTTP://UPPER.example/", "mailto:a@b.co", "/docs/page", "page.html", "?q=1", "#top", "../up/one.html", 'https://x.io/?q="a"&r=\\'b\\'', "https://x.io/a<b>c", ""]:
                    p = parse(m.render_link(url, "label"))
                    self.assertEqual(p.names, ["a"], url)
                    self.assertEqual(p.tags[0][1], [("href", url)], url)
                    self.assertEqual(p.text, "label")

            def test_label_is_text(self):
                for label in ["<script>alert(1)</script>", "a & b", "\\"quoted\\"", "x</a><a href=javascript:alert(1)>y"]:
                    p = parse(m.render_link("/x", label))
                    self.assertEqual(p.names, ["a"], label)
                    self.assertEqual(p.text, label)

            def test_exploits(self):
                evil = ["javascript:alert(1)", "JaVaScRiPt:alert(1)", " javascript:alert(1)", "java\\tscript:alert(1)", "java\\nscript:alert(1)", "\\x01javascript:alert(1)", "data:text/html,<script>alert(1)</script>",
                        "vbscript:msgbox(1)", "&#106;avascript:alert(1)", "&#x6A;avascript:alert(1)", "javascript&colon;alert(1)", "jav&#x09;ascript:alert(1)", 'x" onmouseover="alert(1)', "x\\" onclick=\\"alert(1)\\" x=\\"",
                        "x' onfocus='alert(1)", 'x"><script>alert(1)</script>', "ftp://files.example/x", "file:///etc/passwd", "custom+scheme:thing"]
                for url in evil:
                    p = parse(m.render_link(url, "click"))
                    self.assertEqual(p.names, ["a"], url)
                    attrs = p.tags[0][1]
                    self.assertEqual([k for k, _ in attrs], ["href"], url)
                    href = attrs[0][1]
                    self.assertFalse(dangerous(href), (url, href))
                for url in ["javascript:alert(1)", "JaVaScRiPt:alert(1)", " javascript:alert(1)", "java\\tscript:alert(1)", "data:text/html,x", "ftp://files.example/x", "file:///etc/passwd", "vbscript:x"]:
                    self.assertEqual(parse(m.render_link(url, "c")).tags[0][1], [("href", "#")], url)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SC.append(dict(
    slug="form-values", d=2, product="the settings form", func="render_input", cwe="CWE-79",
    finding="`render_input` pastes the field name and its current value into double-quoted attributes; a value that contains a double quote closes the attribute and can add `onfocus`/`autofocus` handlers (reflected XSS when the form is redisplayed after a validation error).",
    start={
        "forms.py": dd('''
            """Form widgets for the settings page."""


            def render_input(name, value):
                """HTML of a text field: `<input type="text" name="NAME" value="VALUE">`; the value is whatever the user typed."""
                return '<input type="text" name="%s" value="%s">' % (name, value)


            def render_textarea(name, value):
                """HTML of a multi-line field: `<textarea name="NAME">VALUE</textarea>`."""
                return '<textarea name="%s">%s</textarea>' % (name, value)
        '''),
        "README.md": readme("forms", "`render_input(name, value)` and `render_textarea(name, value)` redisplay what the user typed. Names and values are arbitrary text: after the browser parses the HTML, the `name`/`value` attributes (or the textarea text) must be exactly the given strings, and no other attribute or element may appear."),
    },
    solution={"forms.py": dd('''
        """Form widgets for the settings page."""
        import html


        def render_input(name, value):
            """HTML of a text field: `<input type="text" name="NAME" value="VALUE">`; the value is whatever the user typed."""
            return '<input type="text" name="%s" value="%s">' % (html.escape(name, quote=True), html.escape(value, quote=True))


        def render_textarea(name, value):
            """HTML of a multi-line field: `<textarea name="NAME">VALUE</textarea>`."""
            return '<textarea name="%s">%s</textarea>' % (html.escape(name, quote=True), html.escape(value, quote=True))
    ''')},
    hidden={"tests/test_forms_security.py": HTML_PRELUDE + dd('''
        import forms as m

        VALUES = ["plain", 'say "hi"', "it's", '" onfocus="alert(1)" autofocus="', "' onfocus='alert(1)' autofocus='", "<script>alert(1)</script>", "a&b &amp; &lt;", "x\\">\\u003cimg src=x onerror=alert(1)>", "", " ", "\\u00fc\\u4e2d\\U0001f600", "line1\\nline2"]


        class FormTest(unittest.TestCase):
            def test_input(self):
                for v in VALUES:
                    p = parse(m.render_input("title", v))
                    self.assertEqual(p.names, ["input"], v)
                    self.assertEqual(p.tags[0][1], [("type", "text"), ("name", "title"), ("value", v)], v)
                for n in VALUES:
                    p = parse(m.render_input(n, "v"))
                    self.assertEqual(p.tags[0][1], [("type", "text"), ("name", n), ("value", "v")], n)

            def test_textarea(self):
                for v in VALUES:
                    p = parse(m.render_textarea("bio", v))
                    self.assertEqual(p.names, ["textarea"], v)
                    self.assertEqual(p.tags[0][1], [("name", "bio")])
                    self.assertEqual(p.text_of("textarea"), v)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SC.append(dict(
    slug="inline-config", d=3, product="the single-page app shell", func="render_config_script", cwe="CWE-79",
    finding="`render_config_script` embeds the app settings as JSON inside a `<script>` block; `json.dumps` does not escape `</script>`, so a setting value such as `</script><script>alert(1)</script>` (a user's display name, for instance) ends the block early and injects script.",
    start={
        "shell.py": dd('''
            """Page shell of the single-page app."""
            import json


            def render_config_script(settings):
                """The script block that hands the settings (a JSON-compatible dict) to the front end: `<script>window.CONFIG = <JSON>;</script>`."""
                return "<script>window.CONFIG = %s;</script>" % json.dumps(settings)
        '''),
        "README.md": readme("shell", "`render_config_script(settings)` returns one `<script>` element: `<script>window.CONFIG = <JSON>;</script>`. The JSON must parse back to exactly `settings`; the element must not be terminable from inside the data (values may contain `</script>`, `<!--`, `&`, quotes, and the characters U+2028/U+2029)."),
    },
    solution={"shell.py": dd('''
        """Page shell of the single-page app."""
        import json


        def render_config_script(settings):
            """The script block that hands the settings (a JSON-compatible dict) to the front end: `<script>window.CONFIG = <JSON>;</script>`."""
            data = json.dumps(settings)
            for ch, esc in (("<", "\\\\u003c"), (">", "\\\\u003e"), ("&", "\\\\u0026"), ("\\u2028", "\\\\u2028"), ("\\u2029", "\\\\u2029")):
                data = data.replace(ch, esc)
            return "<script>window.CONFIG = %s;</script>" % data
    ''')},
    hidden={"tests/test_shell_security.py": HTML_PRELUDE + dd('''
        import json

        import shell as m


        class ShellTest(unittest.TestCase):
            def roundtrip(self, settings):
                html = m.render_config_script(settings)
                p = parse(html)
                self.assertEqual(p.names, ["script"], html)
                self.assertEqual(html.lower().count("</script"), 1, html)
                self.assertNotIn("<!--", html)
                body = p.text_of("script")
                self.assertTrue(body.startswith("window.CONFIG = ") and body.endswith(";"), body)
                self.assertEqual(json.loads(body[len("window.CONFIG = "):-1]), settings)

            def test_normal(self):
                self.roundtrip({"user": "ann", "n": 3, "flags": [True, None], "nested": {"a": [1, 2, {"b": "c"}]}, "unicode": "\\u00fc\\u4e2d\\U0001f600"})
                self.roundtrip({})

            def test_hostile(self):
                for name in ["</script><script>alert(1)</script>", "</SCRIPT >", "<!-- <script>", "a & b < c > d", 'quote " and \\' and \\\\', "line\\u2028sep\\u2029para", "<scr" + "ipt>", "]]>", "</script/x>"]:
                    self.roundtrip({"name": name, "list": [name, {"k": name}], name: 1})


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SC.append(dict(
    slug="markup-lite", d=3, product="the wiki", func="render_markup", cwe="CWE-79",
    finding="`render_markup` turns the wiki's light markup (`**bold**`, `_italic_`, `[label](url)`) into HTML by regex substitution on the raw text, so raw HTML typed into a page passes straight through, and `[x](javascript:alert(1))` becomes a script link.",
    start={
        "wikitext.py": dd('''
            """Light markup for the wiki."""
            import re


            def render_markup(text):
                """HTML for a wiki page. Paragraphs are separated by blank lines (`<p>...</p>`); `**x**` is `<strong>x</strong>`, `_x_` is `<em>x</em>` (the underscores must not touch a word character on the outside),
                `[label](url)` is `<a href="url">label</a>`. Only http, https, mailto and relative URLs become links; other links are written as the plain text of their label. Everything else is plain text."""
                paragraphs = [p for p in re.split(r"\\n\\s*\\n", text.strip()) if p.strip()]
                out = []
                for para in paragraphs:
                    para = re.sub(r"\\*\\*(.+?)\\*\\*", r"<strong>\\1</strong>", para)
                    para = re.sub(r"(?<!\\w)_(.+?)_(?!\\w)", r"<em>\\1</em>", para)
                    para = re.sub(r"\\[([^\\]]+)\\]\\(([^)\\s]+)\\)", r'<a href="\\2">\\1</a>', para)
                    out.append("<p>%s</p>" % para)
                return "\\n".join(out)
        '''),
        "README.md": readme("wikitext", "`render_markup(text)` converts wiki text to HTML (rules in the docstring). Typed `<`, `>`, `&` and quotes are literal text, not markup. Emphasis and links may nest in the obvious way (`**[a](/x)**`). Text without paragraphs gives an empty string."),
    },
    solution={"wikitext.py": dd('''
        """Light markup for the wiki."""
        import html
        import re

        SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")


        def _link(m):
            label, url = m.group(1), html.unescape(m.group(2))
            flat = "".join(ch for ch in url if ch > " " and ord(ch) != 0x7F)
            sm = SCHEME.match(flat)
            if sm and sm.group(1).lower() not in ("http", "https", "mailto"):
                return label
            return '<a href="%s">%s</a>' % (html.escape(url, quote=True), label)


        def render_markup(text):
            """HTML for a wiki page. Paragraphs are separated by blank lines (`<p>...</p>`); `**x**` is `<strong>x</strong>`, `_x_` is `<em>x</em>` (the underscores must not touch a word character on the outside),
            `[label](url)` is `<a href="url">label</a>`. Only http, https, mailto and relative URLs become links; other links are written as the plain text of their label. Everything else is plain text."""
            paragraphs = [p for p in re.split(r"\\n\\s*\\n", text.strip()) if p.strip()]
            out = []
            for para in paragraphs:
                para = html.escape(para, quote=False)
                para = re.sub(r"\\*\\*(.+?)\\*\\*", r"<strong>\\1</strong>", para)
                para = re.sub(r"(?<!\\w)_(.+?)_(?!\\w)", r"<em>\\1</em>", para)
                para = re.sub(r"\\[([^\\]]+)\\]\\(([^)\\s]+)\\)", _link, para)
                out.append("<p>%s</p>" % para)
            return "\\n".join(out)
    ''')},
    hidden={"tests/test_wikitext_security.py": HTML_PRELUDE + dd('''
        import wikitext as m

        ALLOWED = {"p", "strong", "em", "a"}


        class WikiTest(unittest.TestCase):
            def test_markup(self):
                p = parse(m.render_markup("Hello **big** and _small_ world\\n\\nSecond [site](https://x.io/a?b=1&c=2) & [rel](/docs) ok"))
                self.assertEqual(p.names, ["p", "strong", "em", "p", "a", "a"])
                self.assertEqual(p.text.replace("\\n", ""), "Hello big and small worldSecond site & rel ok")
                self.assertEqual(p.tags[4][1], [("href", "https://x.io/a?b=1&c=2")])
                self.assertEqual(p.tags[5][1], [("href", "/docs")])
                self.assertEqual(m.render_markup(""), "")
                self.assertEqual(m.render_markup("  \\n\\n  "), "")
                self.assertEqual(parse(m.render_markup("snake_case_name and _it_")).names, ["p", "em"])
                self.assertEqual(parse(m.render_markup("**[a](/x)**")).names, ["p", "strong", "a"])

            def test_literal_text(self):
                for raw in ["1 < 2 & 3 > 2", "<b>not bold</b>", '"quotes" and \\'single\\'', "&amp; &lt;", "x </p><p> y", "<img src=x onerror=alert(1)>"]:
                    p = parse(m.render_markup(raw))
                    self.assertEqual(p.names, ["p"], raw)
                    self.assertEqual(p.text, raw)

            def test_hostile(self):
                payloads = ["<script>alert(1)</script>", "**<script>alert(1)</script>**", "[x](javascript:alert(1))", "[x](JaVaScRiPt:alert(1))", "[x](data:text/html,hi)", "[<img src=x onerror=alert(1)>](/ok)",
                            "[x](http://a.io/\\"onmouseover=\\"alert(1))", "[click](vbscript:x)", "[x](&#106;avascript:alert(1))", "[x](java\\tscript:alert(1))", "_<i onclick=alert(1)>x</i>_", '[a"b](/p"q)']
                for raw in payloads:
                    p = parse(m.render_markup(raw))
                    self.assertTrue(set(p.names) <= ALLOWED, (raw, p.names))
                    for tag, attrs in p.tags:
                        if tag == "a":
                            self.assertEqual([k for k, _ in attrs], ["href"], raw)
                            self.assertFalse(dangerous(attrs[0][1]), (raw, attrs))
                        else:
                            self.assertEqual(attrs, [], (raw, tag))
                self.assertEqual(parse(m.render_markup("[x](javascript:run)")).names, ["p"])
                self.assertEqual(parse(m.render_markup("[x](javascript:run)")).text, "x")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SC.append(dict(
    slug="autoescape", d=3, product="the notification templates", func="render", cwe="CWE-79",
    finding="the template engine substitutes every `{{ value }}` into the page verbatim; only `{{{ value }}}` is supposed to be raw, but both forms skip escaping, so any template variable holding user text is an XSS hole.",
    start={
        "microtpl.py": dd('''
            """A tiny template engine for notification pages."""
            import re

            VAR = re.compile(r"\\{\\{\\{\\s*([\\w.]+)\\s*\\}\\}\\}|\\{\\{\\s*([\\w.]+)\\s*\\}\\}")


            def _lookup(ctx, dotted):
                cur = ctx
                for part in dotted.split("."):
                    if isinstance(cur, dict) and part in cur:
                        cur = cur[part]
                    else:
                        return ""
                return cur


            def render(template, ctx):
                """Substitute variables. `{{ name }}` inserts the HTML-escaped text of the value, `{{{ name }}}` inserts it raw (for trusted fragments). Dotted names look into nested dicts; unknown names give "";
                values that are not strings are converted with str()."""
                def sub(m):
                    raw = m.group(1) is not None
                    value = _lookup(ctx, m.group(1) or m.group(2))
                    return str(value)
                return VAR.sub(sub, template)
        '''),
        "README.md": readme("microtpl", "`render(template, ctx)`: `{{ name }}` is replaced by the **HTML-escaped** text of the variable (so `<b>` is shown as text), `{{{ name }}}` by its raw text (for fragments the application itself produced). Spaces inside the braces are optional, dotted names (`user.name`) read nested dicts, unknown names give an empty string, other types are converted with `str()` before escaping."),
    },
    solution={"microtpl.py": dd('''
        """A tiny template engine for notification pages."""
        import html
        import re

        VAR = re.compile(r"\\{\\{\\{\\s*([\\w.]+)\\s*\\}\\}\\}|\\{\\{\\s*([\\w.]+)\\s*\\}\\}")


        def _lookup(ctx, dotted):
            cur = ctx
            for part in dotted.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return ""
            return cur


        def render(template, ctx):
            """Substitute variables. `{{ name }}` inserts the HTML-escaped text of the value, `{{{ name }}}` inserts it raw (for trusted fragments). Dotted names look into nested dicts; unknown names give "";
            values that are not strings are converted with str()."""
            def sub(m):
                raw = m.group(1) is not None
                value = str(_lookup(ctx, m.group(1) or m.group(2)))
                return value if raw else html.escape(value, quote=True)
            return VAR.sub(sub, template)
    ''')},
    hidden={"tests/test_microtpl_security.py": HTML_PRELUDE + dd('''
        import microtpl as m


        class TplTest(unittest.TestCase):
            def test_normal(self):
                self.assertEqual(m.render("Hi {{ user.name }}!", {"user": {"name": "Ann"}}), "Hi Ann!")
                self.assertEqual(m.render("{{a}}-{{ b }}-{{c}}", {"a": 1, "b": 2.5, "c": None}), "1-2.5-None")
                self.assertEqual(m.render("[{{ missing }}][{{ a.b }}]", {"a": "str"}), "[][]")
                self.assertEqual(m.render("{{{ frag }}}", {"frag": "<b>ok</b>"}), "<b>ok</b>")
                self.assertEqual(m.render("{{ x }} & {{{ x }}}", {"x": "<i>"}), "&lt;i&gt; & <i>")
                self.assertEqual(m.render("no vars", {}), "no vars")

            def test_escaped(self):
                values = ["<script>alert(1)</script>", 'a "quoted" \\'name\\'', "x & y", "<img src=x onerror=alert(1)>", "&lt;already&gt;", "a</p><p>b"]
                for v in values:
                    p = parse(m.render("<p title=\\"{{ v }}\\">{{ v }}</p>", {"v": v}))
                    self.assertEqual(p.names, ["p"], v)
                    self.assertEqual(p.tags[0][1], [("title", v)], v)
                    self.assertEqual(p.text, v)
                p = parse(m.render("<p>{{ user.bio }}</p>", {"user": {"bio": "<script>alert(1)</script>"}}))
                self.assertEqual(p.names, ["p"])


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SC.append(dict(
    slug="error-page", d=4, product="the web framework", func="render_error", cwe="CWE-79",
    finding="the error page template reflects the requested path (attacker-controlled) into several HTML contexts - the `<title>`, a `<meta content=\"...\">` attribute and the body - without escaping, so a crafted link to a missing page runs script in the victim's browser (reflected XSS).",
    start={
        "errorpage.py": dd('''
            """Error pages of the web framework."""

            REASONS = {404: "Not Found", 403: "Forbidden", 500: "Server Error"}


            def render_error(status, path, detail=""):
                """HTML error page for `status` (a key of REASONS) for the request `path` (raw request target, attacker-controlled) with an optional `detail` message from the application."""
                reason = REASONS[status]
                page = (
                    "<html><head><title>%d %s: %s</title><meta name=\\"error-path\\" content=\\"%s\\"></head>"
                    "<body><h1>%s</h1><p>The page <code>%s</code> could not be served.</p>%s</body></html>"
                ) % (status, reason, path, path, reason, path, ("<p class=\\"detail\\">%s</p>" % detail) if detail else "")
                return page
        '''),
        "README.md": readme("errorpage", "`render_error(status, path, detail='')` returns the page: title `<status> <reason>: <path>`, a `meta` element named `error-path` whose `content` is the path, an `h1` with the reason, a `p` with the path inside `code`, and (only when `detail` is non-empty) `<p class=\"detail\">` with the detail text. `path` and `detail` are plain text and must show up exactly as given when the page is parsed; an unknown status raises `KeyError`."),
    },
    solution={"errorpage.py": dd('''
        """Error pages of the web framework."""
        import html

        REASONS = {404: "Not Found", 403: "Forbidden", 500: "Server Error"}


        def render_error(status, path, detail=""):
            """HTML error page for `status` (a key of REASONS) for the request `path` (raw request target, attacker-controlled) with an optional `detail` message from the application."""
            reason = REASONS[status]
            p = html.escape(path, quote=True)
            d = html.escape(detail, quote=True)
            page = (
                "<html><head><title>%d %s: %s</title><meta name=\\"error-path\\" content=\\"%s\\"></head>"
                "<body><h1>%s</h1><p>The page <code>%s</code> could not be served.</p>%s</body></html>"
            ) % (status, reason, p, p, reason, p, ("<p class=\\"detail\\">%s</p>" % d) if detail else "")
            return page
    ''')},
    hidden={"tests/test_errorpage_security.py": HTML_PRELUDE + dd('''
        import errorpage as m

        PATHS = ["/missing", "/a b?x=1&y=2", "/</title><script>alert(1)</script>", '/"><script>alert(1)</script>', "/' onload='alert(1)", "/<img src=x onerror=alert(1)>", "/&amp;", "/\\u00fc\\u4e2d", "/%3Cscript%3E"]


        class ErrorTest(unittest.TestCase):
            def test_structure(self):
                for path in PATHS:
                    p = parse(m.render_error(404, path))
                    self.assertEqual(p.names, ["html", "head", "title", "meta", "body", "h1", "p", "code"], path)
                    self.assertEqual(p.tags[3][1], [("name", "error-path"), ("content", path)], path)
                    self.assertEqual(p.text_of("title"), "404 Not Found: " + path, path)
                    self.assertEqual(p.text_of("code"), path, path)
                    self.assertEqual(p.text_of("h1"), "Not Found")

            def test_detail(self):
                for detail in ["disk full", "<script>alert(1)</script>", 'a "b" & c']:
                    p = parse(m.render_error(500, "/x", detail))
                    self.assertEqual(p.names[-1], "p", detail)
                    self.assertEqual([t for t in p.tags if t[0] == "p"][-1][1], [("class", "detail")])
                    self.assertEqual(p.text_of("p").endswith(detail), True, detail)
                    self.assertEqual(p.names.count("script"), 0)
                self.assertNotIn("detail", m.render_error(403, "/x"))

            def test_status(self):
                with self.assertRaises(KeyError):
                    m.render_error(418, "/x")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SC.append(dict(
    slug="profile-card", d=4, product="the community site", func="render_profile", cwe="CWE-79",
    finding="`render_profile` builds the member card from profile fields that members edit themselves: name and bio go into the page unescaped, `avatar` and `website` are written into `src`/`href` attributes without quoting or scheme checks (`x\" onerror=\"...`, `javascript:` links).",
    start={
        "cards.py": dd('''
            """Member cards of the community site."""

            DEFAULT_AVATAR = "/static/default.png"


            def render_profile(p):
                """HTML card for the profile dict `p` with the keys name, avatar, website, bio (all plain text; website and avatar may be empty).

                `<div class="card"><img src="AVATAR" alt="NAME"><h2>NAME</h2>[<a href="WEBSITE">WEBSITE</a>]<p>BIO</p></div>`; newlines in the bio become `<br>`. The avatar must be an http(s) URL or a path starting with `/`,
                otherwise DEFAULT_AVATAR is used. The website link is only shown for http(s) URLs."""
                avatar = p.get("avatar") or DEFAULT_AVATAR
                site = p.get("website") or ""
                link = '<a href="%s">%s</a>' % (site, site) if site else ""
                return '<div class="card"><img src="%s" alt="%s"><h2>%s</h2>%s<p>%s</p></div>' % (avatar, p["name"], p["name"], link, p.get("bio", "").replace("\\n", "<br>"))
        '''),
        "README.md": readme("cards", "`render_profile(p)` returns the card described in the docstring. Name, bio, website and avatar are user-supplied text: parsed back, the `alt` and the `h2` text equal the name, the link text and the `href` equal the website, the `src` equals the avatar (when it is allowed) and the paragraph text equals the bio, with `<br>` standing for each line feed. Avatars other than http(s) URLs or `/`-paths fall back to the default image; websites other than http(s) URLs produce no link at all."),
    },
    solution={"cards.py": dd('''
        """Member cards of the community site."""
        import html

        DEFAULT_AVATAR = "/static/default.png"


        def _scheme_ok(url, schemes=("http", "https")):
            flat = "".join(ch for ch in url if ch > " " and ord(ch) != 0x7F)
            if ":" in flat.split("/", 1)[0]:
                return flat.split(":", 1)[0].lower() in schemes
            return False


        def render_profile(p):
            """HTML card for the profile dict `p` with the keys name, avatar, website, bio (all plain text; website and avatar may be empty).

            `<div class="card"><img src="AVATAR" alt="NAME"><h2>NAME</h2>[<a href="WEBSITE">WEBSITE</a>]<p>BIO</p></div>`; newlines in the bio become `<br>`. The avatar must be an http(s) URL or a path starting with `/`,
            otherwise DEFAULT_AVATAR is used. The website link is only shown for http(s) URLs."""
            avatar = p.get("avatar") or DEFAULT_AVATAR
            if not (avatar.startswith("/") and not avatar.startswith("//") or _scheme_ok(avatar)):
                avatar = DEFAULT_AVATAR
            site = p.get("website") or ""
            link = '<a href="%s">%s</a>' % (html.escape(site, quote=True), html.escape(site)) if site and _scheme_ok(site) else ""
            name = html.escape(p["name"], quote=True)
            bio = "<br>".join(html.escape(line) for line in p.get("bio", "").split("\\n"))
            return '<div class="card"><img src="%s" alt="%s"><h2>%s</h2>%s<p>%s</p></div>' % (html.escape(avatar, quote=True), name, name, link, bio)
    ''')},
    hidden={"tests/test_cards_security.py": HTML_PRELUDE + dd('''
        import cards as m

        ALLOWED_TAGS = {"div", "img", "h2", "a", "p", "br"}


        class CardTest(unittest.TestCase):
            def card(self, **kw):
                profile = {"name": "Ann", "avatar": "", "website": "", "bio": ""}
                profile.update(kw)
                return parse(m.render_profile(profile))

            def test_normal(self):
                p = self.card(name="Ann O'Neil <3", avatar="https://cdn.example/a.png?s=1&t=2", website="https://ann.example/~ann", bio="line one\\nline & two\\n\\nlast")
                self.assertEqual(p.names, ["div", "img", "h2", "a", "p", "br", "br", "br"])
                self.assertEqual(p.tags[1][1], [("src", "https://cdn.example/a.png?s=1&t=2"), ("alt", "Ann O'Neil <3")])
                self.assertEqual(p.text_of("h2"), "Ann O'Neil <3")
                self.assertEqual(p.tags[3][1], [("href", "https://ann.example/~ann")])
                self.assertEqual(p.text_of("a"), "https://ann.example/~ann")
                self.assertEqual(p.text_of("p"), "line one\\nline & two\\n\\nlast")
                self.assertEqual(self.card(avatar="/img/me.png").tags[1][1][0], ("src", "/img/me.png"))
                q = self.card()
                self.assertEqual(q.tags[1][1][0], ("src", "/static/default.png"))
                self.assertEqual(q.names, ["div", "img", "h2", "p"])

            def test_text_fields_are_text(self):
                for s in ["<script>alert(1)</script>", '" onmouseover="alert(1)', "<img src=x onerror=alert(1)>", "</p><p>x", "&amp; &lt;"]:
                    p = self.card(name=s, bio=s)
                    self.assertTrue(set(p.names) <= ALLOWED_TAGS, (s, p.names))
                    self.assertEqual(p.tags[1][1][1], ("alt", s))
                    self.assertEqual(p.text_of("h2"), s)
                    self.assertEqual(p.text_of("p"), s)
                    self.assertEqual([k for k, _ in p.tags[1][1]], ["src", "alt"])

            def test_urls(self):
                for bad in ["javascript:alert(1)", "JaVaScRiPt:alert(1)", " javascript:alert(1)", "data:text/html,<script>alert(1)</script>", 'x" onerror="alert(1)', "//evil.example/x.png", "vbscript:x", "relative/path.png", "ftp://x/y"]:
                    p = self.card(avatar=bad)
                    self.assertEqual(p.tags[1][1][0], ("src", "/static/default.png"), bad)
                    self.assertEqual([k for k, _ in p.tags[1][1]], ["src", "alt"], bad)
                for bad in ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "java\\tscript:alert(1)", "data:text/html,x", 'x" onclick="alert(1)', "mailto:a@b.c", "ftp://x/y", "//evil.example/", "&#106;avascript:alert(1)", "www.example.com"]:
                    p = self.card(website=bad)
                    self.assertNotIn("a", p.names, bad)
                    self.assertFalse(any(dangerous(v) for _, attrs in p.tags for _, v in attrs if v), bad)
                self.assertEqual(self.card(website="HTTP://UPPER.example/").names.count("a"), 1)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))


@family("security-xss", category="security", lang="python", kind="fix", n=8,
        summary="escape user text in every HTML context: text, attributes, URLs, inline script, markup, templates")
def gen_xss(rng, n):
    return list(_sec.emit(rng, SC[:n], tags=["html"]))
