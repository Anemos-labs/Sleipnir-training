"""Escaping and quoting: regex, HTML and URL handling in a snippet renderer (python); shell, CSV and SQL quoting (js)."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A (python): rendering search hits as HTML.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd(r'''
    # snippets

    HTML rendering for the search result page of a documentation site.

    ## `snippets.render.render_snippet(text, terms)`
    `text` is **plain text**; `terms` is a string or a list of strings. Returns HTML in which every occurrence of a term, matched
    case-insensitively and **literally** (a term such as `c++` or `a.b` or `(` has no regex meaning), is wrapped in `<mark>...</mark>`
    (keeping the original letters). All text is HTML-escaped (`& < > " '`). Matching is done on the original text, never on its
    escaped form: searching `amp` or `lt` does not match inside `&amp;` or `&lt;`. When terms overlap or share a start, the longest
    one wins (`ab` and `abc` on `abcd` mark `abc`). Empty terms are ignored.

    ## `snippets.render.link(url, label)`
    Returns `<a href="URL">LABEL</a>` with both parts HTML-escaped (quotes included). The URL's scheme (read the way a browser does:
    surrounding whitespace is ignored, tab, CR and LF characters are ignored anywhere, case does not matter) must be `http`,
    `https` or `mailto`; relative URLs (no scheme) are fine. Any other scheme (`javascript:`, `data:`, `vbscript:` ...) makes the
    link `href="#"`. Safe URLs are emitted as written (stripped of surrounding whitespace).
''')

A_RENDER = dd(r'''
    import html
    import re

    SAFE_SCHEMES = {"http", "https", "mailto"}


    def _pattern(terms):
        parts = sorted({t for t in terms if t}, key=lambda t: (-len(t), t))
        if not parts:
            return None
        return re.compile("|".join(re.escape(t) for t in parts), re.IGNORECASE)


    def render_snippet(text, terms):
        if isinstance(terms, str):
            terms = [terms]
        pattern = _pattern(terms)
        if pattern is None:
            return html.escape(text)
        out = []
        pos = 0
        for m in pattern.finditer(text):
            out.append(html.escape(text[pos:m.start()]))
            out.append("<mark>" + html.escape(m.group(0)) + "</mark>")
            pos = m.end()
        out.append(html.escape(text[pos:]))
        return "".join(out)


    def _scheme(url):
        cleaned = url.strip().translate({9: None, 10: None, 13: None})
        m = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*):", cleaned)
        return m.group(1).lower() if m else None


    def link(url, label):
        scheme = _scheme(url)
        href = url.strip() if scheme is None or scheme in SAFE_SCHEMES else "#"
        return f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>'
''')

A_VISIBLE = {
    "tests/test_render.py": dd('''
        import unittest

        from snippets.render import link, render_snippet


        class RenderTests(unittest.TestCase):
            def test_marks(self):
                self.assertEqual(render_snippet("Hello World", "world"), "Hello <mark>World</mark>")

            def test_escapes_html(self):
                self.assertEqual(render_snippet("<b>hi</b>", "zzz"), "&lt;b&gt;hi&lt;/b&gt;")

            def test_plain_link(self):
                self.assertEqual(link("https://example.test/a", "A"), '<a href="https://example.test/a">A</a>')


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_render.py": dd(r'''
        import unittest

        from snippets.render import link, render_snippet


        class Matching(unittest.TestCase):
            def test_case_insensitive_keeping_the_original_letters(self):
                self.assertEqual(render_snippet("Hello HELLO hello", "HeLLo"), "<mark>Hello</mark> <mark>HELLO</mark> <mark>hello</mark>")

            def test_terms_are_literal(self):
                self.assertEqual(render_snippet("1+1=2, a.b and aXb", "a.b"), "1+1=2, <mark>a.b</mark> and aXb")
                self.assertEqual(render_snippet("I like C++ and c", "c++"), "I like <mark>C++</mark> and c")
                self.assertEqual(render_snippet("f(x) = [x] * 2", "(x)"), "f<mark>(x)</mark> = [x] * 2")
                self.assertEqual(render_snippet("a|b", "a|b"), "<mark>a|b</mark>")
                self.assertEqual(render_snippet("cost $5 ^ 2", "$5 ^"), "cost <mark>$5 ^</mark> 2")
                self.assertEqual(render_snippet("back\\slash", "\\"), "back<mark>\\</mark>slash")

            def test_not_matching_inside_entities(self):
                self.assertEqual(render_snippet("fish & chips <ok>", "amp"), "fish &amp; chips &lt;ok&gt;")
                self.assertEqual(render_snippet("a < b, salt", "lt"), "a &lt; b, sa<mark>lt</mark>")
                self.assertEqual(render_snippet("x > y", "gt"), "x &gt; y")
                self.assertEqual(render_snippet("it's \"fine\"", "quot"), "it&#x27;s &quot;fine&quot;")
                self.assertEqual(render_snippet("it's", "39"), "it&#x27;s")

            def test_marked_text_is_escaped_too(self):
                self.assertEqual(render_snippet("a <b> c", "<b>"), "a <mark>&lt;b&gt;</mark> c")
                self.assertEqual(render_snippet("Tom & Jerry", "&"), "Tom <mark>&amp;</mark> Jerry")

            def test_quotes(self):
                self.assertEqual(render_snippet("say \"hi\" it's", "hi"), "say &quot;<mark>hi</mark>&quot; it&#x27;s")

            def test_several_terms_longest_first(self):
                self.assertEqual(render_snippet("abcd ab", ["ab", "abc"]), "<mark>abc</mark>d <mark>ab</mark>")
                self.assertEqual(render_snippet("foo foobar", ["foo", "foobar", "bar"]), "<mark>foo</mark> <mark>foobar</mark>")
                self.assertEqual(render_snippet("one two", ["two", "one"]), "<mark>one</mark> <mark>two</mark>")

            def test_empty_and_missing_terms(self):
                self.assertEqual(render_snippet("a<b", ""), "a&lt;b")
                self.assertEqual(render_snippet("a<b", []), "a&lt;b")
                self.assertEqual(render_snippet("a<b", ["", ""]), "a&lt;b")
                self.assertEqual(render_snippet("", "x"), "")
                self.assertEqual(render_snippet("aaa", ["a", "a"]), "<mark>a</mark><mark>a</mark><mark>a</mark>")


        class Links(unittest.TestCase):
            def test_escaping(self):
                self.assertEqual(link("https://x.test/?a=1&b=2", 'A "quoted" <label>'), '<a href="https://x.test/?a=1&amp;b=2">A &quot;quoted&quot; &lt;label&gt;</a>')

            def test_attribute_injection(self):
                self.assertEqual(link('https://x.test/" onmouseover="alert(1)', "x"), '<a href="https://x.test/&quot; onmouseover=&quot;alert(1)">x</a>')

            def test_safe_schemes_and_relative_urls(self):
                for url in ("https://a.test/x", "http://a.test", "HTTPS://A.TEST/X", "mailto:me@a.test", "/docs/a.html", "docs/a:b.html", "../up", "#frag", "?q=a:b", "page.html"):
                    self.assertEqual(link(url, "t"), f'<a href="{url}">t</a>', url)
                self.assertEqual(link("  https://a.test/x  ", "t"), '<a href="https://a.test/x">t</a>')

            def test_dangerous_schemes_in_every_disguise(self):
                for url in ("javascript:alert(1)", "JaVaScRiPt:alert(1)", "  javascript:alert(1)", "java\tscript:alert(1)", "java\nscript:alert(1)",
                            "\tjavascript:alert(1)", "data:text/html;base64,AAA", "vbscript:msgbox(1)", "DATA:text/html,x", "jav&#x61;script:x".replace("&#x61;", "a"), "file:///etc/passwd"):
                    self.assertEqual(link(url, "t"), '<a href="#">t</a>', repr(url))


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["regex"] = lambda c: (
        "Searching the docs for `vector(` makes the results page fail with a server error, and searching for `a.b` also highlights `aXb`. "
        "This is the failure we log for the first one:\n\n```\n"
        + c.bad_run("from snippets.render import render_snippet\nrender_snippet('use vector( here', 'vector(')\n").splitlines()[-1]
        + "\n```\n\nSearch terms must be matched literally."
    )
    p["escape-late"] = (
        "The result page shows the text `<mark>` literally around the hits and the highlighted words are not highlighted. It started "
        "when somebody moved the HTML escaping to the end \"to be safe\". Escaping has to happen without destroying the markup we add."
    )
    p["entities"] = (
        "Searching for `amp` highlights part of the `&amp;` in results where the text only contains an ampersand, and the page source "
        "then contains broken entities like `&<mark>amp</mark>;`. The text is matched after being escaped; matching must be on the original text."
    )
    p["quotes"] = (
        "Security: a document link with the target `https://x.test/\" onmouseover=\"alert(1)` renders with the quotes intact and the "
        "attribute is closed early. Attribute values need their quotes escaped."
    )
    p["scheme"] = (
        "XSS report: `javascript:` links are replaced by `#` but `JaVaScRiPt:alert(1)`, ` javascript:alert(1)` (leading space) and "
        "`java<TAB>script:alert(1)` all pass through unchanged, as does `data:text/html,...`. Only http, https, mailto and "
        "relative links are safe, and the scheme must be read like a browser does."
    )
    p["order"] = (
        "When two search terms overlap (`ab` and `abc`) we highlight `ab` and leave the `c` unmarked, depending on the order of the "
        "terms. The longest term should win wherever they overlap."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "snippets/__init__.py": '"""HTML rendering of search hits."""\n', "snippets/render.py": A_RENDER}
    r = "snippets/render.py"
    late = ('''    out = []
    pos = 0
    for m in pattern.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        out.append("<mark>" + html.escape(m.group(0)) + "</mark>")
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)
''', '''    out = []
    pos = 0
    for m in pattern.finditer(text):
        out.append(text[pos:m.start()])
        out.append("<mark>" + m.group(0) + "</mark>")
        pos = m.end()
    out.append(text[pos:])
    return html.escape("".join(out))
''')
    entity = ('''    out = []
    pos = 0
    for m in pattern.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        out.append("<mark>" + html.escape(m.group(0)) + "</mark>")
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)
''', '''    escaped = html.escape(text)
    return pattern.sub(lambda m: "<mark>" + m.group(0) + "</mark>", escaped)
''')
    bugs = [
        Bug("terms-are-regexes", 2, {r: [('return re.compile("|".join(re.escape(t) for t in parts), re.IGNORECASE)', 'return re.compile("|".join(parts), re.IGNORECASE)')]}, P["regex"]),
        Bug("quotes-not-escaped-in-attributes", 2, {r: [('html.escape(href, quote=True)', 'html.escape(href, quote=False)')]}, P["quotes"]),
        Bug("markup-escaped-after-wrapping", 3, {r: [late]}, P["escape-late"]),
        Bug("scheme-check-is-naive", 3, {r: [('    scheme = _scheme(url)\n    href = url.strip() if scheme is None or scheme in SAFE_SCHEMES else "#"\n',
                                              '    href = "#" if url.startswith("javascript:") else url.strip()\n')]}, P["scheme"]),
        Bug("terms-in-given-order", 3, {r: [('    parts = sorted({t for t in terms if t}, key=lambda t: (-len(t), t))\n', '    parts = [t for t in terms if t]\n')]}, P["order"]),
        Bug("matching-inside-escaped-text", 4, {r: [entity]}, P["entities"]),
    ]
    return Base("snippets", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (javascript): quoting for shell, CSV and SQL.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd(r'''
    # quoting

    Quoting helpers for a deployment tool (CommonJS). Every function must make its output **round-trip**: whatever the input, the
    receiver (a POSIX shell, a CSV reader, an SQL parser) sees exactly the original value.

    * `shellQuote(arg)`: one word for `sh`. An empty string is `''`. A string made only of the characters `A-Z a-z 0-9 _ / . : = @ % + , -`
      is returned unchanged. Anything else is wrapped in single quotes, with every single quote inside written as `'\''`.
    * `shellJoin(args)`: the quoted arguments joined with single spaces.
    * `csvLine(fields)`: one CSV record (RFC 4180 style, no trailing newline). `null` and `undefined` are empty fields; other values are
      converted with `String`. A field is wrapped in double quotes when it contains a comma, a double quote, CR or LF, or begins or ends with
      white space; double quotes inside are doubled.
    * `sqlLiteral(value)`: `null`/`undefined` is `NULL`; finite numbers are written as is (`NaN` and the infinities are a `RangeError`);
      booleans are `TRUE`/`FALSE`; everything else is converted with `String` and written between single quotes with every
      single quote doubled.
''')

B_QUOTE = dd(r'''
    'use strict';

    function shellQuote(arg) {
      const s = String(arg);
      if (s === '') return "''";
      if (/^[A-Za-z0-9_\/.:=@%+,-]+$/.test(s)) return s;
      return "'" + s.replace(/'/g, "'\\''") + "'";
    }

    function shellJoin(args) {
      return args.map(shellQuote).join(' ');
    }

    function csvField(v) {
      const s = v === null || v === undefined ? '' : String(v);
      if (/[",\r\n]/.test(s) || /^\s|\s$/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
      return s;
    }

    function csvLine(fields) {
      return fields.map(csvField).join(',');
    }

    function sqlLiteral(v) {
      if (v === null || v === undefined) return 'NULL';
      if (typeof v === 'number') {
        if (!Number.isFinite(v)) throw new RangeError('not a finite number');
        return String(v);
      }
      if (typeof v === 'boolean') return v ? 'TRUE' : 'FALSE';
      return "'" + String(v).replace(/'/g, "''") + "'";
    }

    module.exports = { shellQuote, shellJoin, csvField, csvLine, sqlLiteral };
''')

B_VISIBLE = {
    "test/quote.test.js": dd(r'''
        const test = require('node:test');
        const assert = require('node:assert');
        const { shellQuote, csvLine, sqlLiteral } = require('../src/quote');

        test('simple values', () => {
          assert.strictEqual(shellQuote('file.txt'), 'file.txt');
          assert.strictEqual(shellQuote('two words'), "'two words'");
          assert.strictEqual(csvLine(['a', 'b']), 'a,b');
          assert.strictEqual(sqlLiteral('x'), "'x'");
          assert.strictEqual(sqlLiteral(5), '5');
        });
    '''),
}

B_HIDDEN = {
    "test/hidden_quote.test.js": dd(r'''
        const test = require('node:test');
        const assert = require('node:assert');
        const { execFileSync } = require('node:child_process');
        const { shellQuote, shellJoin, csvLine, sqlLiteral } = require('../src/quote');

        const NASTY = [
          'plain', 'with space', "it's", 'a;b', '$HOME', '`id`', '$(id)', 'a"b', 'back\\slash', 'new\nline', '*', '~', '!', 'tab\t', 'ünï', 'a&b',
          'x|y', '>', '#c', '{a,b}', "'", "''", "'a'b'", ' lead', 'trail ', '-n', '--', 'a=b', 'a\\', '\\n',
        ];

        function viaShell(args) {
          const out = execFileSync('sh', ['-c', "printf '%s\\0' " + shellJoin(args)], { encoding: 'utf8' });
          const parts = out.split('\0');
          parts.pop();
          return parts;
        }

        test('a real shell reads back exactly the arguments', () => {
          assert.deepStrictEqual(viaShell(NASTY), NASTY);
          assert.deepStrictEqual(viaShell(['']), ['']);
          assert.deepStrictEqual(viaShell(['', 'x', '']), ['', 'x', '']);
        });

        test('quoting each argument separately also works', () => {
          for (const arg of NASTY) assert.deepStrictEqual(viaShell([arg]), [arg], JSON.stringify(arg));
        });

        test('shellQuote details', () => {
          assert.strictEqual(shellQuote(''), "''");
          assert.strictEqual(shellQuote('abc-1.2/x:y=z@w%v+u,t_'), 'abc-1.2/x:y=z@w%v+u,t_');
          assert.strictEqual(shellQuote("it's"), "'it'\\''s'");
          assert.strictEqual(shellQuote('a b'), "'a b'");
          assert.strictEqual(shellQuote('$HOME'), "'$HOME'");
          assert.strictEqual(shellQuote(42), '42');
          assert.strictEqual(shellJoin(['ls', '-l', 'my dir']), "ls -l 'my dir'");
          assert.strictEqual(shellJoin([]), '');
        });

        function parseCsv(line) {
          const fields = [];
          let i = 0;
          for (;;) {
            let value = '';
            if (line[i] === '"') {
              i += 1;
              for (;;) {
                if (i >= line.length) throw new Error('unterminated quote');
                if (line[i] === '"') {
                  if (line[i + 1] === '"') { value += '"'; i += 2; continue; }
                  i += 1;
                  break;
                }
                value += line[i++];
              }
            } else {
              while (i < line.length && line[i] !== ',') value += line[i++];
            }
            fields.push(value);
            if (i >= line.length) return fields;
            if (line[i] !== ',') throw new Error('garbage after a quoted field');
            i += 1;
          }
        }

        test('csv lines read back as the original fields', () => {
          const rows = [
            ['a', 'b,c', 'say "hi"', 'line\nbreak', ' lead', 'trail ', '', 'x'],
            ['"', '""', ',', ',,', '\r\n', 'tab\there'],
            ['', ''],
            ['only'],
          ];
          for (const row of rows) assert.deepStrictEqual(parseCsv(csvLine(row)), row, JSON.stringify(row));
        });

        test('csv exact output', () => {
          assert.strictEqual(csvLine(['a', 'b,c', 'say "hi"']), 'a,"b,c","say ""hi"""');
          assert.strictEqual(csvLine(['line\nbreak', 'cr\rhere']), '"line\nbreak","cr\rhere"');
          assert.strictEqual(csvLine([' lead', 'trail ', 'in ner']), '" lead","trail ",in ner');
          assert.strictEqual(csvLine([null, undefined, 5, true, '']), ',,5,true,');
          assert.strictEqual(csvLine([]), '');
        });

        test('sqlLiteral', () => {
          assert.strictEqual(sqlLiteral(null), 'NULL');
          assert.strictEqual(sqlLiteral(undefined), 'NULL');
          assert.strictEqual(sqlLiteral(-1.5), '-1.5');
          assert.strictEqual(sqlLiteral(0), '0');
          assert.strictEqual(sqlLiteral(true), 'TRUE');
          assert.strictEqual(sqlLiteral(false), 'FALSE');
          assert.strictEqual(sqlLiteral("O'Brien"), "'O''Brien'");
          assert.strictEqual(sqlLiteral("'; DROP TABLE x; --"), ["'", "'", "'", "; DROP TABLE x; --", "'"].join(''));
          assert.strictEqual(sqlLiteral("''"), "'".repeat(6));
          assert.strictEqual(sqlLiteral(''), "''");
          assert.strictEqual(sqlLiteral('back\\slash'), "'back\\slash'");
          for (const bad of [NaN, Infinity, -Infinity]) assert.throws(() => sqlLiteral(bad), RangeError);
        });
    '''),
}


def _b_prompts():
    p = {}
    p["shell-quote"] = lambda c: (
        "The deploy tool breaks on file names with an apostrophe: `shellQuote(\"it's\")` produces `"
        + c.probe("const { shellQuote } = require('./src/quote');\nconsole.log(shellQuote(\"it's\"));\n")[1]
        + "`, which the shell reads as an unterminated string. Quoting of embedded single quotes is wrong."
    )
    p["shell-double"] = (
        "Command lines built by the deploy tool expand variables and backticks that were meant to be literal: an argument containing `$HOME` "
        "or `$(whoami)` is evaluated by the remote shell. Arguments must reach the shell exactly as given, unexpanded."
    )
    p["shell-empty"] = (
        "A command like `git commit -m \"\"` loses its empty argument: the built command line is `git commit -m ` and git then complains "
        "that `-m` needs a value. The empty string must stay an argument."
    )
    p["csv-quotes"] = (
        "Exports that contain a field with quotes (`say \"hi\"`) cannot be read back by the customer's spreadsheet: the field is wrapped "
        "in quotes but the quotes inside are not doubled."
    )
    p["csv-newline"] = (
        "Fields with line breaks are written bare, so a multi-line comment turns into two CSV rows in the customer's tool. Fields "
        "containing CR or LF (and fields with leading or trailing spaces) must be quoted."
    )
    p["sql-quote"] = (
        "Security scan: building an INSERT with `sqlLiteral(\"O'Brien\")` yields `'O'Brien'`, which is invalid SQL and, with a crafted "
        "name, an injection. Single quotes inside strings must be doubled."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "src/quote.js": B_QUOTE, "package.json": '{\n  "name": "quoting",\n  "version": "1.0.0",\n  "private": true\n}\n'}
    q = "src/quote.js"
    bugs = [
        Bug("shell-empty-argument-vanishes", 2, {q: [("  if (s === '') return \"''\";\n", "  if (s === '') return '';\n")]}, P["shell-empty"]),
        Bug("csv-multiline-fields-unquoted", 2, {q: [("  if (/[\",\\r\\n]/.test(s) || /^\\s|\\s$/.test(s)) return", "  if (/[\",]/.test(s)) return")]}, P["csv-newline"]),
        Bug("sql-quotes-not-doubled", 2, {q: [("  return \"'\" + String(v).replace(/'/g, \"''\") + \"'\";\n", "  return \"'\" + String(v) + \"'\";\n")]}, P["sql-quote"]),
        Bug("shell-single-quote-unescaped", 3, {q: [("  return \"'\" + s.replace(/'/g, \"'\\\\''\") + \"'\";\n", "  return \"'\" + s + \"'\";\n")]}, P["shell-quote"]),
        Bug("shell-uses-double-quotes", 3, {q: [("  return \"'\" + s.replace(/'/g, \"'\\\\''\") + \"'\";\n", "  return '\"' + s.replace(/([\"\\\\])/g, '\\\\$1') + '\"';\n")]}, P["shell-double"]),
        Bug("csv-quotes-not-doubled", 3, {q: [("return '\"' + s.replace(/\"/g, '\"\"') + '\"';", "return '\"' + s + '\"';")]}, P["csv-quotes"]),
    ]
    return Base("quoting", "javascript", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-escaping", category="fix", lang="python", kind="fix", n=12,
        summary="escaping and quoting: regex, HTML, URL schemes (python snippets); shell, CSV and SQL quoting (js)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
