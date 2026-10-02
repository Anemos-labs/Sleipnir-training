"""Regular expression bugs: greedy matches, anchors, unicode classes, literal versus pattern (python log parser, ruby tag kit)."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A (python): web access log lines.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd(r'''
    # logscan

    Parser for web server access logs in the "combined" format:

        203.0.113.7 - alice [10/Oct/2025:13:55:36 +0200] "GET /a/b?x=1 HTTP/1.1" 200 2326 "https://ref.example/" "Mozilla/5.0 (X11)"

    `logscan.parser.parse_line(line)` returns a dict or `None` when the line is not a valid log line. A trailing line terminator (`\n` or `\r\n`) is ignored; **the
    whole line must be a log line**: nothing before it, nothing after it, exactly two quoted fields after the request and the numbers.

    Fields: `ip` (IPv4 or IPv6 text), `user` (`None` for `-`), `time` (the text inside the brackets), `method`, `path`, `status` (`int`, exactly three ASCII digits),
    `size` (`int`; `-` means 0), `referer` (`None` for `-`) and `agent`. The ident field (second column) is skipped. The quoted fields may contain spaces and
    backslash-escaped quotes (`\"`) and backslashes (`\\`); the returned text is unescaped.

    `parse_all(lines)` returns `(records, bad_count)`: the parsed records in order and the number of non-empty lines that were not valid.
''')

A_PARSER = dd(r'''
    import re

    _LINE = re.compile(
        r'(?P<ip>[0-9a-fA-F:.]+) \S+ (?P<user>\S+) \[(?P<time>[^\]]+)\] '
        r'"(?P<method>[A-Z]+) (?P<path>\S+) HTTP/[0-9.]+" '
        r'(?P<status>[0-9]{3}) (?P<size>[0-9]+|-) '
        r'"(?P<referer>(?:[^"\\]|\\.)*)" "(?P<agent>(?:[^"\\]|\\.)*)"'
    )


    def _unescape(text):
        return re.sub(r'\\(["\\])', r'\1', text)


    def parse_line(line):
        if line.endswith("\r\n"):
            line = line[:-2]
        elif line.endswith("\n"):
            line = line[:-1]
        m = _LINE.fullmatch(line)
        if not m:
            return None
        d = m.groupdict()
        return {
            "ip": d["ip"],
            "user": None if d["user"] == "-" else d["user"],
            "time": d["time"],
            "method": d["method"],
            "path": d["path"],
            "status": int(d["status"]),
            "size": 0 if d["size"] == "-" else int(d["size"]),
            "referer": None if d["referer"] == "-" else _unescape(d["referer"]),
            "agent": _unescape(d["agent"]),
        }


    def parse_all(lines):
        records = []
        bad = 0
        for line in lines:
            if not line.strip():
                continue
            rec = parse_line(line)
            if rec is None:
                bad += 1
            else:
                records.append(rec)
        return records, bad
''')

A_VISIBLE = {
    "tests/test_parser.py": dd(r'''
        import unittest

        from logscan.parser import parse_all, parse_line

        LINE = r'203.0.113.7 - alice [10/Oct/2025:13:55:36 +0200] "GET /a/b?x=1 HTTP/1.1" 200 2326 "https://ref.example/" "Mozilla/5.0 (X11)"'


        class ParserTests(unittest.TestCase):
            def test_basic_line(self):
                rec = parse_line(LINE)
                self.assertEqual(rec["ip"], "203.0.113.7")
                self.assertEqual(rec["user"], "alice")
                self.assertEqual((rec["method"], rec["path"], rec["status"], rec["size"]), ("GET", "/a/b?x=1", 200, 2326))
                self.assertEqual(rec["agent"], "Mozilla/5.0 (X11)")

            def test_garbage_is_none(self):
                self.assertIsNone(parse_line("not a log line"))
                self.assertEqual(parse_all([LINE, "", "junk"])[1], 1)


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_parser.py": dd(r'''
        import unittest

        from logscan.parser import parse_all, parse_line

        BASE = r'203.0.113.7 - alice [10/Oct/2025:13:55:36 +0200] "GET /a/b?x=1 HTTP/1.1" 200 2326 "https://ref.example/" "Mozilla/5.0 (X11; Linux)"'


        def line(ip="203.0.113.7", user="alice", status="200", size="2326", referer="https://ref.example/", agent="curl/8.0"):
            return f'{ip} - {user} [10/Oct/2025:13:55:36 +0200] "GET /x HTTP/1.1" {status} {size} "{referer}" "{agent}"'


        class Fields(unittest.TestCase):
            def test_a_normal_line(self):
                rec = parse_line(BASE)
                self.assertEqual(rec, {"ip": "203.0.113.7", "user": "alice", "time": "10/Oct/2025:13:55:36 +0200", "method": "GET", "path": "/a/b?x=1",
                                       "status": 200, "size": 2326, "referer": "https://ref.example/", "agent": "Mozilla/5.0 (X11; Linux)"})

            def test_dashes(self):
                rec = parse_line(line(user="-", size="-", referer="-"))
                self.assertEqual((rec["user"], rec["size"], rec["referer"]), (None, 0, None))

            def test_ipv6(self):
                for ip in ("2001:db8::1", "::1", "fe80::1ff:fe23:4567:890a"):
                    self.assertEqual(parse_line(line(ip=ip))["ip"], ip)

            def test_escaped_quotes_and_backslashes(self):
                rec = parse_line(line(agent=r'Mozilla \"Gecko\" x\\y', referer=r'http://a.test/?q=\"x\"'))
                self.assertEqual(rec["agent"], r'Mozilla "Gecko" x\y')
                self.assertEqual(rec["referer"], 'http://a.test/?q="x"')

            def test_an_escaped_quote_followed_by_a_space_is_not_a_field_separator(self):
                rec = parse_line(line(agent=r'a\" \"b', referer="-"))
                self.assertEqual(rec["agent"], 'a" "b')
                self.assertIsNone(rec["referer"])

            def test_spaces_inside_quoted_fields(self):
                rec = parse_line(line(agent="Some Long Agent String 1.0", referer="http://x.test/a b"))
                self.assertEqual(rec["agent"], "Some Long Agent String 1.0")
                self.assertEqual(rec["referer"], "http://x.test/a b")

            def test_line_terminators_are_ignored(self):
                for end in ("\n", "\r\n"):
                    self.assertEqual(parse_line(BASE + end)["status"], 200)


        class WholeLine(unittest.TestCase):
            def test_trailing_garbage(self):
                self.assertIsNone(parse_line(BASE + " extra"))
                self.assertIsNone(parse_line(BASE + ' "third field"'))
                self.assertIsNone(parse_line(BASE + "\n" + BASE))

            def test_leading_garbage(self):
                self.assertIsNone(parse_line("junk " + BASE))
                self.assertIsNone(parse_line("2025-10-10 " + BASE))

            def test_three_quoted_fields_are_too_many(self):
                self.assertIsNone(parse_line(line(referer='-" "A', agent="B")[:-3] + '"'))
                self.assertIsNone(parse_line(BASE[:-1] + '" "B"'))

            def test_missing_pieces(self):
                for bad in (BASE.replace('"GET /a/b?x=1 HTTP/1.1"', "GET /a/b HTTP/1.1"), BASE.replace(" 200 2326", " 2326"), BASE.replace("[10/Oct/2025:13:55:36 +0200]", ""),
                            BASE.replace('"https://ref.example/" ', ""), "", "   "):
                    self.assertIsNone(parse_line(bad), bad)


        class Numbers(unittest.TestCase):
            def test_status_is_exactly_three_ascii_digits(self):
                self.assertIsNone(parse_line(line(status="\u0662\u0660\u0660")))
                self.assertIsNone(parse_line(line(status="20")))
                self.assertIsNone(parse_line(line(status="2000")))
                self.assertIsNone(parse_line(line(status="2x0")))
                self.assertEqual(parse_line(line(status="404"))["status"], 404)

            def test_size_is_ascii_digits_or_dash(self):
                self.assertIsNone(parse_line(line(size="\u0661\u0662\u0663")))
                self.assertIsNone(parse_line(line(size="12.5")))
                self.assertIsNone(parse_line(line(size="-5")))
                self.assertEqual(parse_line(line(size="0"))["size"], 0)
                self.assertEqual(parse_line(line(size="123456789012"))["size"], 123456789012)


        class Streams(unittest.TestCase):
            def test_parse_all(self):
                lines = [BASE, "", "   ", "garbage", line(status="500"), "junk " + BASE, line(ip="::1") + "\n"]
                records, bad = parse_all(lines)
                self.assertEqual([r["status"] for r in records], [200, 500, 200])
                self.assertEqual(bad, 2)
                self.assertEqual(parse_all([]), ([], 0))


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["greedy"] = (
        "Malformed access log lines with an extra quoted field are accepted and attributed to the wrong columns: `\"-\" \"A\" \"B\"` is parsed with the referer "
        "`-\" \"A` and the agent `B`. A valid line has exactly two quoted fields after the request. Our line regex uses `.*` for the quoted fields."
    )
    p["unicode-digits"] = (
        "The parser accepts a status code written in Arabic-Indic digits (\u0662\u0660\u0660) and returns `200`, which polluted our dashboard when a corrupted log "
        "got through. Status and size must be plain ASCII digits."
    )
    p["search"] = (
        "Lines with a timestamp prepended by our log shipper (`2025-10-10 203.0.113.7 - ...`) are parsed as if they were fine, but we want them reported as bad "
        "lines (the shipper config is wrong and we want to notice). The whole line must be a log line."
    )
    p["trailing"] = (
        "Two concatenated log lines (a missing newline after a crash) are parsed as the first line and the rest is silently dropped. Trailing "
        "garbage after the last quoted field must make the line invalid."
    )
    p["ipv4"] = (
        "All IPv6 clients are missing from the statistics: their lines are counted as bad. The `ip` field must accept IPv6 addresses like `2001:db8::1` as well."
    )
    p["size-dash"] = (
        "304 responses are logged with `-` as the size and those lines show up as bad lines in the report. A `-` size means 0."
    )
    p["escapes"] = lambda c: (
        "User agents that contain quotes (the server escapes them as `\\\"`) make the line unparseable: `parse_line` returns "
        + c.probe("from logscan.parser import parse_line\nline = '1.2.3.4 - - [10/Oct/2025:13:55:36 +0200] \"GET / HTTP/1.1\" 200 5 \"-\" \"Mozilla \\\\\"Gecko\\\\\" x\"'\nprint(parse_line(line))\n")[1]
        + " for them. Escaped quotes and backslashes must be allowed inside the quoted fields (and unescaped in the result)."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "logscan/__init__.py": '"""Access log parsing."""\n', "logscan/parser.py": A_PARSER}
    pa = "logscan/parser.py"
    bugs = [
        Bug("status-and-size-accept-any-unicode-digit", 3, {pa: [("    r'(?P<status>[0-9]{3}) (?P<size>[0-9]+|-) '\n", "    r'(?P<status>\\d{3}) (?P<size>\\d+|-) '\n")]}, P["unicode-digits"]),
        Bug("size-dash-not-allowed", 1, {pa: [("(?P<size>[0-9]+|-)", "(?P<size>[0-9]+)")]}, P["size-dash"]),
        Bug("ipv4-only", 3, {pa: [("r'(?P<ip>[0-9a-fA-F:.]+) \\S+", "r'(?P<ip>[0-9]{1,3}(?:\\.[0-9]{1,3}){3}) \\S+")]}, P["ipv4"]),
        Bug("trailing-garbage-allowed", 1, {pa: [("    m = _LINE.fullmatch(line)\n", "    m = _LINE.match(line)\n")]}, P["trailing"]),
        Bug("leading-garbage-allowed", 3, {pa: [("    m = _LINE.fullmatch(line)\n", "    m = _LINE.search(line)\n")]}, P["search"]),
        Bug("quoted-fields-are-greedy", 3, {pa: [("    r'\"(?P<referer>(?:[^\"\\\\]|\\\\.)*)\" \"(?P<agent>(?:[^\"\\\\]|\\\\.)*)\"'\n", "    r'\"(?P<referer>.*)\" \"(?P<agent>.*)\"'\n")]}, P["greedy"]),
        Bug("quoted-fields-ignore-escapes", 4, {pa: [("    r'\"(?P<referer>(?:[^\"\\\\]|\\\\.)*)\" \"(?P<agent>(?:[^\"\\\\]|\\\\.)*)\"'\n", "    r'\"(?P<referer>[^\"]*)\" \"(?P<agent>[^\"]*)\"'\n")]}, P["escapes"]),
    ]
    return Base("logscan", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (ruby): text tools for a blogging platform.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd(r'''
    # tagkit

    Text tools of a blogging platform (Ruby 3, minitest).

    * `Tagkit.valid_slug?(s)`: a String of 1 to 40 characters made of lower-case ASCII letters and digits in groups separated by **single** hyphens; no hyphen at either
      end. The **whole** string must match: a newline anywhere makes it invalid.
    * `Tagkit.extract_hashtags(text)`: the hashtags of a text, down-cased, **unique**, in order of first appearance. A hashtag is `#` followed by 1 to 30 Unicode letters,
      digits or underscores (`#café`, `#日本語`, `#a_1`) that are not followed by another such character (a longer word is not a tag at all); the `#` must not be
      preceded by a letter, digit, underscore or another `#` (so `a#b`, `##x` and `page#top` contain no tag).
    * `Tagkit.strip_brackets(text)`: removes every `[...]` segment that has no brackets inside it (`"a [b] c [d]"` becomes `"a  c "`; `"[a [b] c]"` becomes `"[a  c]"`).
    * `Tagkit.redact(text, secret)`: replaces every occurrence of the **literal** text `secret` by `[REDACTED]` (no pattern syntax: `a.c` only matches `a.c`, `(` is just a
      parenthesis); an empty or nil secret changes nothing.
    * `Tagkit.render(template, vars)`: replaces `{{name}}` by `vars[:name].to_s`, inserted **literally** (backslashes in a value stay as they are; a value that contains `{{other}}` is
      not expanded again); placeholders without a value stay as they are.
''')

B_LIB = dd(r'''
    module Tagkit
      SLUG = /\A[a-z0-9]+(?:-[a-z0-9]+)*\z/

      def self.valid_slug?(s)
        s.is_a?(String) && s.length <= 40 && SLUG.match?(s)
      end

      def self.extract_hashtags(text)
        text.scan(/(?<![\p{L}\p{N}_#])#([\p{L}\p{N}_]{1,30})(?![\p{L}\p{N}_])/).flatten.map(&:downcase).uniq
      end

      def self.strip_brackets(text)
        text.gsub(/\[[^\[\]]*\]/, "")
      end

      def self.redact(text, secret)
        return text if secret.nil? || secret.empty?

        text.gsub(secret, "[REDACTED]")
      end

      def self.render(template, vars)
        template.gsub(/\{\{(\w+)\}\}/) do
          name = Regexp.last_match(1)
          vars.key?(name.to_sym) ? vars[name.to_sym].to_s : "{{#{name}}}"
        end
      end
    end
''')

B_MAIN = 'require "tagkit"\n'

B_VISIBLE = {
    "test/test_basic.rb": dd(r'''
        require "minitest/autorun"
        require "tagkit"

        class TestBasic < Minitest::Test
          def test_slug
            assert Tagkit.valid_slug?("my-first-post")
            refute Tagkit.valid_slug?("My Post")
          end

          def test_tags
            assert_equal %w[ruby tips], Tagkit.extract_hashtags("learning #Ruby and #tips")
          end

          def test_render
            assert_equal "Hi Ann", Tagkit.render("Hi {{name}}", name: "Ann")
          end
        end
    '''),
}

B_HIDDEN = {
    "test/test_hidden_tagkit.rb": dd(r'''
        require "minitest/autorun"
        require "tagkit"

        class TestHiddenTagkit < Minitest::Test
          def test_slugs
            %w[a a1 my-first-post 2025-recap x-y-z].each { |s| assert Tagkit.valid_slug?(s), s }
            ["", "-a", "a-", "a--b", "A", "a_b", "a b", "caf\u00e9", "a.b", "-"].each { |s| refute Tagkit.valid_slug?(s), s.inspect }
            refute Tagkit.valid_slug?("a" * 41)
            assert Tagkit.valid_slug?("a" * 40)
            refute Tagkit.valid_slug?(nil)
            refute Tagkit.valid_slug?(42)
          end

          def test_a_slug_with_a_newline_is_not_valid
            refute Tagkit.valid_slug?("ok\nrm-rf")
            refute Tagkit.valid_slug?("ok\n")
            refute Tagkit.valid_slug?("\nok")
            refute Tagkit.valid_slug?("first\nsecond")
          end

          def test_hashtags_basics
            assert_equal %w[ruby tips], Tagkit.extract_hashtags("learning #Ruby and #tips, #RUBY again")
            assert_equal %w[a_1], Tagkit.extract_hashtags("#a_1")
            assert_equal %w[one two], Tagkit.extract_hashtags("#one,#two")
            assert_equal [], Tagkit.extract_hashtags("no tags here # nothing")
          end

          def test_hashtags_with_non_ascii_letters
            assert_equal ["caf\u00e9"], Tagkit.extract_hashtags("a #caf\u00e9 break")
            assert_equal ["\u65e5\u672c\u8a9e"], Tagkit.extract_hashtags("#\u65e5\u672c\u8a9e")
            assert_equal ["\u00fcber", "stra\u00dfe"], Tagkit.extract_hashtags("#\u00dcber #Stra\u00dfe")
          end

          def test_hashtag_boundaries
            assert_equal [], Tagkit.extract_hashtags("a#b")
            assert_equal [], Tagkit.extract_hashtags("##x")
            assert_equal [], Tagkit.extract_hashtags("page#top")
            assert_equal [], Tagkit.extract_hashtags("x" * 31 + " #" + "y" * 31)
            assert_equal ["y" * 30], Tagkit.extract_hashtags("#" + "y" * 30)
            assert_equal ["end"], Tagkit.extract_hashtags("(#end)")
          end

          def test_strip_brackets
            assert_equal "a  c ", Tagkit.strip_brackets("a [b] c [d]")
            assert_equal "[a  c]", Tagkit.strip_brackets("[a [b] c]")
            assert_equal "no brackets", Tagkit.strip_brackets("no brackets")
            assert_equal "x", Tagkit.strip_brackets("x[]")
            assert_equal "keep [ this", Tagkit.strip_brackets("keep [ this")
            assert_equal "one  two", Tagkit.strip_brackets("one [1] two")
          end

          def test_redact_is_literal
            assert_equal "pw is [REDACTED] and [REDACTED]", Tagkit.redact("pw is a.c and a.c", "a.c")
            assert_equal "abc stays", Tagkit.redact("abc stays", "a.c")
            assert_equal "call [REDACTED]x", Tagkit.redact("call (x", "(")
            assert_equal "a [REDACTED] b", Tagkit.redact("a $5 b", "$5")
            assert_equal "plain", Tagkit.redact("plain", "")
            assert_equal "plain", Tagkit.redact("plain", nil)
            assert_equal "[REDACTED][REDACTED]", Tagkit.redact("++", "+")
          end

          def test_render_inserts_values_literally
            assert_equal "Hi Ann, you are 7", Tagkit.render("Hi {{name}}, you are {{age}}", name: "Ann", age: 7)
            assert_equal 'dir C:\temp\1 ok', Tagkit.render("dir {{path}} ok", path: 'C:\temp\1')
            assert_equal 'a\\b', Tagkit.render("{{x}}", x: 'a\\b')
            assert_equal 'back \0 ref \1', Tagkit.render("{{v}}", v: 'back \0 ref \1')
          end

          def test_render_does_not_expand_inserted_text_again
            assert_equal "{{b}} and B", Tagkit.render("{{a}} and {{b}}", a: "{{b}}", b: "B")
            assert_equal "x{{a}}", Tagkit.render("{{a}}", a: "x{{a}}")
          end

          def test_render_leaves_unknown_placeholders
            assert_equal "Hi {{who}}!", Tagkit.render("Hi {{who}}!", {})
            assert_equal "a {{b}} c", Tagkit.render("{{a}} {{b}} c", a: "a")
            assert_equal "", Tagkit.render("", name: "x")
          end
        end
    '''),
}


def _b_prompts():
    p = {}
    p["anchors"] = (
        "Security review: `valid_slug?(\"ok\\nrm-rf\")` returns true, because a slug check that looks at lines lets a second line through "
        "(we put slugs in file paths and shell commands). The whole string must be a slug."
    )
    p["ascii-tags"] = (
        "Hashtags in French, German and Japanese posts are cut or ignored: `#café` becomes the tag `caf` and `#日本語` is not found at all. Letters "
        "and digits of every script count."
    )
    p["greedy-brackets"] = (
        "`strip_brackets(\"a [b] c [d]\")` returns \"a \" instead of \"a  c \": everything between the first `[` and the last `]` is removed. "
        "Each bracketed segment is meant to be removed on its own."
    )
    p["redact-regexp"] = (
        "The audit log redaction treats the secret as a regular expression: a password like `a.c` also redacts `abc`, and a password with a `(` "
        "(or `+`, `$`) in it raises `RegexpError` or does not match itself. It must be a literal match."
    )
    p["render-sequential"] = (
        "Template rendering mangles values with backslashes (a Windows path `C:\\temp\\1` comes out as `C:\\temp` followed by the whole matched text or nothing) and "
        "a value that itself looks like a tag for another variable (two opening braces, a name, two closing braces) gets expanded a second time. Values must be inserted literally, once."
    )
    p["dedupe"] = (
        "The tag cloud shows `Ruby` and `ruby` as two different tags for a post that uses both spellings. The README says tags are down-cased "
        "before the duplicates are removed."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "lib/tagkit.rb": B_LIB, "package.txt": "tagkit\n"}
    good.pop("package.txt")
    lib = "lib/tagkit.rb"
    bugs = [
        Bug("tags-duplicated-by-case", 1, {lib: [(".flatten.map(&:downcase).uniq\n", ".flatten.uniq.map(&:downcase)\n")]}, P["dedupe"]),
        Bug("brackets-matched-greedily", 1, {lib: [("    text.gsub(/\\[[^\\[\\]]*\\]/, \"\")\n", "    text.gsub(/\\[.*\\]/, \"\")\n")]}, P["greedy-brackets"]),
        Bug("slug-anchors-per-line", 3, {lib: [("  SLUG = /\\A[a-z0-9]+(?:-[a-z0-9]+)*\\z/\n", "  SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/\n")]}, P["anchors"]),
        Bug("hashtags-ascii-only", 3, {lib: [("    text.scan(/(?<![\\p{L}\\p{N}_#])#([\\p{L}\\p{N}_]{1,30})(?![\\p{L}\\p{N}_])/).flatten.map(&:downcase).uniq\n", "    text.scan(/(?<![A-Za-z0-9_#])#([A-Za-z0-9_]{1,30})(?![A-Za-z0-9_])/).flatten.map(&:downcase).uniq\n")]}, P["ascii-tags"]),
        Bug("secret-used-as-a-pattern", 3, {lib: [("    text.gsub(secret, \"[REDACTED]\")\n", "    text.gsub(Regexp.new(secret), \"[REDACTED]\")\n")]}, P["redact-regexp"]),
        Bug("render-by-repeated-gsub", 4, {lib: [("    template.gsub(/\\{\\{(\\w+)\\}\\}/) do\n      name = Regexp.last_match(1)\n      vars.key?(name.to_sym) ? vars[name.to_sym].to_s : \"{{#{name}}}\"\n    end\n",
                                                  "    out = template.dup\n    vars.each { |k, v| out = out.gsub(\"{{#{k}}}\", v.to_s) }\n    out\n")]}, P["render-sequential"]),
    ]
    return Base("tagkit", "ruby", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-regex-parse", category="fix", lang="python", kind="fix", n=13,
        summary="regular expressions: greedy matches, anchors, unicode classes, literal versus pattern (python log parser, ruby tag kit)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
