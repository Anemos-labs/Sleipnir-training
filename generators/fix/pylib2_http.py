"""Text-format libraries (python), batch: HTTP media types, caching headers, virtual paths."""
from fx import Lib, dd, register_libs

# ======================================================================================================================
# negotiator: media ranges, Accept parsing and weighted content negotiation
# ======================================================================================================================

NEG_README = dd(r'''
    # negotiator

    Content negotiation for the report server: parse `Accept`-style headers and choose which representation to send.
    Weights (`q`) are handled as integers in thousandths (`1000` is `q=1`) so comparisons are exact.

    ## `parse_q(text) -> int`
    Reads `0`, `0.`, `0.5`, `0.123`, `1`, `1.`, `1.0`, `1.00`, `1.000`: a `0` or `1` and optionally a dot with up to
    three digits (after `1` only zeros). Anything else (`1.5`, `0.1234`, `.5`, `-1`, ``) is a `ValueError`. The
    result is the value times 1000: `parse_q("0.7") == 700`.

    ## `parse_media(text) -> Media`
    `Media` is a `namedtuple` `(type, subtype, params, q)`; `params` is a `dict`.
    * `text` is `type/subtype` followed by `;name=value` parameters; blanks around the pieces are ignored and empty
      parameters (`;;`) are skipped. Type, subtype and parameter names are lower-cased.
    * type and subtype consist of `a-z 0-9 ! # $ & ^ _ . + -` (after lower-casing) or are `*`. `*/*` is a valid
      range, `type/*` too, but `*/sub` is not. A missing `/` or an empty part is a `ValueError`.
    * A parameter value may be a double-quoted string (a backslash makes the next character literal; `;` and `,`
      inside quotes are ordinary characters); the quotes are removed. A parameter without `=` or with an empty name is
      a `ValueError`. A repeated name keeps its last value.
    * The parameter `q` is not stored in `params`: it sets the weight (`parse_q` rules), default `1000`.

    ## `parse_accept(header) -> list[Media]`
    Splits a header on commas that are not inside double quotes, skips blank items and parses each with `parse_media`,
    keeping the order. An empty header gives `[]`.

    ## `specificity(media) -> tuple`
    `(level, number of params)` where level is `0` for `*/*`, `1` for `type/*`, `2` for `type/subtype`.

    ## `matches(rng, offered) -> bool`
    True when `rng` covers the `offered` media: the type (unless `*`) and subtype (unless `*`) are equal and every
    parameter of `rng` is present in `offered.params` with an equal value.

    ## `negotiate(header, offered) -> str or None`
    `offered` is a list of media strings the server can produce; each may carry its own `q` parameter, the server's
    preference weight for that representation (default `1000`).
    * No `offered` entries: `None`. A `None` or blank `header` means "no preference": the first offered entry.
    * For every offered entry the client range with the highest `specificity` among those that `matches` it decides
      (on equal specificity the one listed first). The entry's score is that range's `q` times the entry's own `q`
      (both in thousandths, so the score is their product). Entries without a matching range, or with score `0`, are
      not acceptable.
    * The winner is the acceptable entry with the highest score; on equal scores the one whose deciding range is
      more specific (compare `specificity` tuples); then the one listed first in `offered`.
    * The result is the winning entry exactly as it appears in `offered`; `None` if nothing is acceptable.
''')

NEG_SRC = dd(r'''
    """Media ranges and content negotiation."""
    import re
    from collections import namedtuple

    Media = namedtuple("Media", "type subtype params q")

    _TOKEN = re.compile(r"[a-z0-9!#$&^_.+-]+")
    _Q = re.compile(r"(0(\.\d{0,3})?|1(\.0{0,3})?)")


    def parse_q(text):
        if not _Q.fullmatch(text):
            raise ValueError("bad q value: %r" % text)
        whole, _, frac = text.partition(".")
        return int(whole) * 1000 + int((frac + "000")[:3])


    def _split(s, sep):
        parts, buf = [], []
        quoted = False
        i = 0
        while i < len(s):
            c = s[i]
            if quoted:
                buf.append(c)
                if c == "\\" and i + 1 < len(s):
                    i += 1
                    buf.append(s[i])
                elif c == '"':
                    quoted = False
            elif c == '"':
                quoted = True
                buf.append(c)
            elif c == sep:
                parts.append("".join(buf))
                buf = []
            else:
                buf.append(c)
            i += 1
        parts.append("".join(buf))
        return parts


    def _unquote(v):
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            return re.sub(r"\\(.)", r"\1", v[1:-1])
        return v


    def parse_media(text):
        head, *plist = _split(text, ";")
        typ, slash, sub = head.strip().lower().partition("/")
        if not slash or not typ or not sub:
            raise ValueError("bad media type: %r" % text)
        for part in (typ, sub):
            if part != "*" and not _TOKEN.fullmatch(part):
                raise ValueError("bad media type: %r" % text)
        if typ == "*" and sub != "*":
            raise ValueError("bad media range: %r" % text)
        params = {}
        q = 1000
        for p in plist:
            p = p.strip()
            if not p:
                continue
            name, eq, value = p.partition("=")
            name = name.strip().lower()
            if not eq or not name:
                raise ValueError("bad parameter: %r" % p)
            value = _unquote(value.strip())
            if name == "q":
                q = parse_q(value)
            else:
                params[name] = value
        return Media(typ, sub, params, q)


    def parse_accept(header):
        return [parse_media(p) for p in _split(header, ",") if p.strip()]


    def specificity(media):
        level = 0 if media.type == "*" else 1 if media.subtype == "*" else 2
        return (level, len(media.params))


    def matches(rng, offered):
        if rng.type != "*" and rng.type != offered.type:
            return False
        if rng.subtype != "*" and rng.subtype != offered.subtype:
            return False
        return all(offered.params.get(k) == v for k, v in rng.params.items())


    def negotiate(header, offered):
        if not offered:
            return None
        if header is None or not header.strip():
            return offered[0]
        ranges = parse_accept(header)
        best = None  # ((score, specificity), entry)
        for entry in offered:
            media = parse_media(entry)
            cands = [r for r in ranges if matches(r, media)]
            if not cands:
                continue
            top = max(cands, key=specificity)
            score = top.q * media.q
            if score == 0:
                continue
            key = (score, specificity(top))
            if best is None or key > best[0]:
                best = (key, entry)
        return best[1] if best else None
''')

NEG_VISIBLE = dd(r'''
    import unittest

    from negotiator import negotiate, parse_accept, parse_media, parse_q


    class BasicTests(unittest.TestCase):
        def test_parse_q(self):
            self.assertEqual(parse_q("0.7"), 700)
            self.assertEqual(parse_q("1"), 1000)

        def test_parse_media(self):
            m = parse_media("Text/HTML; Level=1; q=0.5")
            self.assertEqual((m.type, m.subtype, m.params, m.q), ("text", "html", {"level": "1"}, 500))

        def test_negotiate_simple(self):
            self.assertEqual(negotiate("text/html, application/json;q=0.5", ["application/json", "text/html"]), "text/html")


    if __name__ == "__main__":
        unittest.main()
''')

NEG_HIDDEN = dd(r'''
    import unittest

    from negotiator import Media, matches, negotiate, parse_accept, parse_media, parse_q, specificity


    class ParseQ(unittest.TestCase):
        def test_valid(self):
            for text, want in (("0", 0), ("0.", 0), ("0.5", 500), ("0.05", 50), ("0.123", 123), ("1", 1000), ("1.", 1000),
                               ("1.0", 1000), ("1.00", 1000), ("1.000", 1000), ("0.9", 900), ("0.001", 1), ("0.50", 500)):
                self.assertEqual(parse_q(text), want, text)

        def test_invalid(self):
            for text in ("1.5", "0.1234", ".5", "-1", "", "2", "1.001", "0.5x", " 0.5", "1.0000", "00.5", "0,5"):
                with self.assertRaises(ValueError, msg=text):
                    parse_q(text)


    class ParseMedia(unittest.TestCase):
        def test_basic(self):
            self.assertEqual(parse_media("text/html"), Media("text", "html", {}, 1000))
            self.assertEqual(parse_media("  Application/JSON  "), Media("application", "json", {}, 1000))

        def test_params_and_q(self):
            m = parse_media("text/html ; Level=1 ; q=0.3 ;; charset=UTF-8")
            self.assertEqual(m, Media("text", "html", {"level": "1", "charset": "UTF-8"}, 300))
            self.assertEqual(parse_media("a/b; ; x=1;   ").params, {"x": "1"})

        def test_q_is_not_a_param_and_last_wins(self):
            m = parse_media("a/b;q=0.2;q=0.4;x=1;x=2")
            self.assertEqual((m.params, m.q), ({"x": "2"}, 400))

        def test_quoted_values(self):
            m = parse_media('a/b;title="x;y,z";k="a \\"q\\" b";e=""')
            self.assertEqual(m.params, {"title": "x;y,z", "k": 'a "q" b', "e": ""})
            self.assertEqual(parse_media('a/b;k="\\\\"').params, {"k": "\\"})
            self.assertEqual(parse_media('a/b;Q="0.5"').q, 500)

        def test_wildcards(self):
            self.assertEqual(parse_media("*/*"), Media("*", "*", {}, 1000))
            self.assertEqual(parse_media("image/*;q=0.1"), Media("image", "*", {}, 100))

        def test_token_characters(self):
            self.assertEqual(parse_media("application/vnd.api+json").subtype, "vnd.api+json")
            self.assertEqual(parse_media("x-y/z_1.2-3").type, "x-y")

        def test_errors(self):
            for text in ("", "text", "text/", "/html", "*/html", "text/ht ml", "te xt/html", "text/html;q", "text/html;=1",
                         "text/html;q=2", "text/html;q=0.1234", "a/b/c", "téxt/html", "text/(x)"):
                with self.assertRaises(ValueError, msg=text):
                    parse_media(text)


    class ParseAccept(unittest.TestCase):
        def test_list(self):
            got = parse_accept("text/html, application/json;q=0.5,*/*;q=0.1")
            self.assertEqual([(m.type, m.subtype, m.q) for m in got], [("text", "html", 1000), ("application", "json", 500), ("*", "*", 100)])

        def test_blank_items_skipped(self):
            self.assertEqual(len(parse_accept("a/b,, ,c/d,")), 2)
            self.assertEqual(parse_accept(""), [])
            self.assertEqual(parse_accept("   "), [])

        def test_comma_inside_quotes(self):
            got = parse_accept('a/b;x="1,2", c/d')
            self.assertEqual([m.subtype for m in got], ["b", "d"])
            self.assertEqual(got[0].params, {"x": "1,2"})
            got = parse_accept('a/b;x="q\\",z", c/d')
            self.assertEqual(len(got), 2)

        def test_error_propagates(self):
            with self.assertRaises(ValueError):
                parse_accept("a/b, oops")


    class Specificity(unittest.TestCase):
        def test_levels(self):
            self.assertEqual(specificity(parse_media("*/*")), (0, 0))
            self.assertEqual(specificity(parse_media("text/*")), (1, 0))
            self.assertEqual(specificity(parse_media("text/html")), (2, 0))
            self.assertEqual(specificity(parse_media("text/html;level=1;x=y;q=0.5")), (2, 2))
            self.assertEqual(specificity(parse_media("*/*;a=b")), (0, 1))
            self.assertTrue(specificity(parse_media("text/*;a=b")) < specificity(parse_media("text/html")))


    class Matches(unittest.TestCase):
        def m(self, rng, off):
            return matches(parse_media(rng), parse_media(off))

        def test_wildcards(self):
            self.assertTrue(self.m("*/*", "a/b"))
            self.assertTrue(self.m("a/*", "a/b"))
            self.assertFalse(self.m("a/*", "c/b"))
            self.assertTrue(self.m("a/b", "a/b"))
            self.assertFalse(self.m("a/b", "a/c"))
            self.assertFalse(self.m("a/b", "c/b"))
            self.assertTrue(self.m("A/B", "a/b"))

        def test_params(self):
            self.assertTrue(self.m("a/b;x=1", "a/b;x=1;y=2"))
            self.assertFalse(self.m("a/b;x=1", "a/b"))
            self.assertFalse(self.m("a/b;x=1", "a/b;x=2"))
            self.assertTrue(self.m("a/b", "a/b;x=1"))
            self.assertTrue(self.m("a/b;x=1;y=2", "a/b;y=2;x=1"))
            self.assertFalse(self.m("a/b;x=1;y=2", "a/b;x=1"))
            self.assertTrue(self.m("*/*;x=1", "q/r;x=1"))
            self.assertFalse(self.m("*/*;x=1", "q/r;x=2"))
            self.assertTrue(self.m("a/b;q=0.5", "a/b"))


    class Negotiate(unittest.TestCase):
        def test_no_preference(self):
            self.assertEqual(negotiate(None, ["a/b", "c/d"]), "a/b")
            self.assertEqual(negotiate("", ["a/b", "c/d"]), "a/b")
            self.assertEqual(negotiate("  ", ["c/d", "a/b"]), "c/d")
            self.assertEqual(negotiate("a/b", []), None)
            self.assertEqual(negotiate(None, []), None)

        def test_highest_q_wins(self):
            self.assertEqual(negotiate("text/html;q=0.5, application/json", ["text/html", "application/json"]), "application/json")
            self.assertEqual(negotiate("text/html, application/json;q=0.5", ["application/json", "text/html"]), "text/html")

        def test_zero_excludes(self):
            self.assertEqual(negotiate("text/html;q=0, application/json;q=0.1", ["text/html", "application/json"]), "application/json")
            self.assertEqual(negotiate("text/html;q=0", ["text/html"]), None)
            self.assertEqual(negotiate("*/*;q=0", ["text/html"]), None)
            self.assertEqual(negotiate("*/*, text/html;q=0", ["text/html"]), None)
            self.assertEqual(negotiate("*/*, text/html;q=0", ["text/html", "text/plain"]), "text/plain")

        def test_nothing_matches(self):
            self.assertEqual(negotiate("image/png", ["text/html"]), None)
            self.assertEqual(negotiate("text/css, image/*", ["text/html", "application/json"]), None)

        def test_most_specific_range_decides(self):
            hdr = "text/*;q=0.3, text/html;q=0.9, */*;q=0.1"
            self.assertEqual(negotiate(hdr, ["text/plain", "text/html"]), "text/html")
            self.assertEqual(negotiate(hdr, ["text/plain", "image/png"]), "text/plain")
            self.assertEqual(negotiate("text/html;q=0.2, text/*", ["text/html"]), "text/html")
            hdr = "text/html, text/html;level=1;q=0.4"
            self.assertEqual(negotiate(hdr, ["text/html;level=1", "text/html"]), "text/html")

        def test_params_matter(self):
            hdr = "text/html;level=2, text/html;q=0.2"
            self.assertEqual(negotiate(hdr, ["text/html;level=1", "text/html;level=2"]), "text/html;level=2")
            self.assertEqual(negotiate("text/html;level=3", ["text/html;level=1"]), None)

        def test_server_weights(self):
            self.assertEqual(negotiate("a/x, a/y", ["a/x;q=0.5", "a/y"]), "a/y")
            self.assertEqual(negotiate("a/x;q=0.5, a/y;q=0.3", ["a/x;q=0.7", "a/y"]), "a/x;q=0.7")
            self.assertEqual(negotiate("a/x;q=0.5, a/y;q=0.8", ["a/x;q=0.9", "a/y;q=0.5"]), "a/x;q=0.9")
            self.assertEqual(negotiate("a/x", ["a/x;q=0"]), None)

        def test_exact_product_comparison(self):
            self.assertEqual(negotiate("a/x;q=0.3, a/y;q=0.9", ["a/x;q=0.9", "a/y;q=0.3"]), "a/x;q=0.9")
            self.assertEqual(negotiate("*/*;q=0.001", ["a/x"]), "a/x")

        def test_tie_prefers_more_specific_range_then_order(self):
            self.assertEqual(negotiate("text/html, */*", ["application/json", "text/html"]), "text/html")
            self.assertEqual(negotiate("*/*, text/html", ["application/json", "text/html"]), "text/html")
            self.assertEqual(negotiate("*/*", ["application/json", "text/html"]), "application/json")
            self.assertEqual(negotiate("text/*, text/html", ["text/plain", "text/html"]), "text/html")
            self.assertEqual(negotiate("a/b, c/d", ["c/d", "a/b"]), "c/d")

        def test_range_ties_use_first_listed(self):
            self.assertEqual(negotiate("a/b;q=0.2, a/b;q=0.9", ["a/b"]), "a/b")
            self.assertEqual(negotiate("a/b;q=0, a/b;q=0.9", ["a/b", "c/d"]), None)

        def test_returns_entry_as_given(self):
            self.assertEqual(negotiate("TEXT/HTML", ["Text/Html;Charset=UTF-8"]), "Text/Html;Charset=UTF-8")

        def test_quoted_params_in_header(self):
            self.assertEqual(negotiate('a/b;note="x,y";q=0.5, c/d;q=0.6', ["a/b", "c/d"]), "c/d")

        def test_bad_header(self):
            with self.assertRaises(ValueError):
                negotiate("garbage", ["a/b"])


    if __name__ == "__main__":
        unittest.main()
''')

NEG = Lib(
    name="negotiator", lang="python", title="the content negotiation helpers (`negotiator.py`)",
    blurb="The report server picks a response format for each request with this module.",
    files={"negotiator.py": NEG_SRC, "README.md": NEG_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": NEG_VISIBLE},
    hidden_tests={"tests/test_full.py": NEG_HIDDEN},
    mutate=["negotiator.py"], difficulty=3, tags=["http", "parsing"],
    probes=[
        'parse_q("0.07")',
        'parse_media("Text/HTML;Level=1;q=0.3;x=\\"a;b\\"")',
        'len(parse_accept("a/b;x=\\"1,2\\", c/d,, "))',
        'specificity(parse_media("text/html;level=1"))',
        'negotiate("text/html;q=0.5, application/json", ["text/html", "application/json"])',
        'negotiate("*/*, text/html;q=0", ["text/html", "text/plain"])',
        'negotiate("text/*;q=0.3, text/html;q=0.9, */*;q=0.1", ["text/plain", "text/html"])',
        'negotiate("a/x;q=0.5, a/y;q=0.8", ["a/x;q=0.9", "a/y;q=0.5"])',
        'negotiate("*/*, text/html", ["application/json", "text/html"])',
        'negotiate(None, ["a/b", "c/d"])',
    ],
    probe_import="from negotiator import *",
)


# ======================================================================================================================
# cachelens: Cache-Control parsing, freshness and Vary keys
# ======================================================================================================================

CACHE_README = dd(r'''
    # cachelens

    Helpers for the edge cache of the asset proxy: read `Cache-Control`, decide how long a response stays fresh and
    build the secondary cache key from `Vary`.

    ## `split_list(value) -> list[str]`
    Splits a header value on commas that are outside double quotes (a backslash inside quotes makes the next
    character literal), strips every item and drops empty ones.

    ## `parse_cache_control(value) -> dict`
    Maps each directive name (lower-cased) to its value:
    * a directive without `=` has the value `True`;
    * with `=`, the text after it is stripped and, if it is double-quoted, unquoted (backslash escapes resolved);
    * the directives `max-age`, `s-maxage`, `stale-while-revalidate` and `stale-if-error` carry **non-negative
      integers**: the value is converted to `int`; if it is not a plain run of digits, the directive is ignored as if
      it were absent;
    * when a name occurs more than once, the first valid occurrence wins.
    An empty or blank value gives `{}`.

    ## `freshness_lifetime(cc, shared=False, expires_delta=None, last_modified_delta=None) -> int`
    Seconds a stored response may be served without revalidation. `cc` is a parsed Cache-Control dict.
    1. `no-store` or `no-cache` in `cc`: `0`.
    2. `shared` is true and `private` in `cc`: `0`.
    3. `shared` is true and `s-maxage` in `cc`: its value.
    4. `max-age` in `cc`: its value.
    5. `expires_delta` is not `None` (seconds from the `Date` header to `Expires`, possibly negative): that, but never
       below `0`.
    6. `last_modified_delta` is not `None` (seconds from `Last-Modified` to `Date`): one tenth of it, rounded down,
       but never below `0`.
    7. otherwise `0`.

    ## `state(cc, age, shared=False, **kw) -> str`
    Classifies a stored response of the given `age` in seconds, with `lifetime = freshness_lifetime(cc, shared, **kw)`:
    * `"fresh"` if `age < lifetime`;
    * otherwise `"stale-usable"` if `stale-while-revalidate` is present in `cc` and `age < lifetime + that value`, and
      `must-revalidate` is not present, and `proxy-revalidate` is not present for a shared cache;
    * otherwise `"stale"`.

    ## `vary_key(vary, request_headers) -> tuple or None`
    The secondary key of a stored response. `vary` is the response's `Vary` header value, `request_headers` a dict of
    the original request's headers (names compared case-insensitively; a repeated name in different case: the last
    one wins). `vary` blank gives `()`. If any item of `vary` is `*` the response must not be reused: `None`.
    Otherwise the key is a tuple of `(name, value)` pairs, one per distinct header name in `vary` (names lower-cased),
    sorted by name; `value` is the request's value with runs of whitespace collapsed to one space and stripped, or
    `""` when the request lacks that header.
''')

CACHE_SRC = dd(r'''
    """Cache-Control, freshness and Vary."""
    import re

    _NUMERIC = ("max-age", "s-maxage", "stale-while-revalidate", "stale-if-error")


    def split_list(value):
        items, buf = [], []
        quoted = False
        i = 0
        while i < len(value):
            c = value[i]
            if quoted:
                buf.append(c)
                if c == "\\" and i + 1 < len(value):
                    i += 1
                    buf.append(value[i])
                elif c == '"':
                    quoted = False
            elif c == '"':
                quoted = True
                buf.append(c)
            elif c == ",":
                items.append("".join(buf))
                buf = []
            else:
                buf.append(c)
            i += 1
        items.append("".join(buf))
        return [x.strip() for x in items if x.strip()]


    def _unquote(text):
        if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
            return re.sub(r"\\(.)", r"\1", text[1:-1])
        return text


    def parse_cache_control(value):
        out = {}
        for item in split_list(value):
            name, eq, raw = item.partition("=")
            name = name.strip().lower()
            if not name or name in out:
                continue
            if not eq:
                out[name] = True
                continue
            val = _unquote(raw.strip())
            if name in _NUMERIC:
                if not re.fullmatch(r"[0-9]+", val):
                    continue
                out[name] = int(val)
            else:
                out[name] = val
        return out


    def freshness_lifetime(cc, shared=False, expires_delta=None, last_modified_delta=None):
        if "no-store" in cc or "no-cache" in cc:
            return 0
        if shared and "private" in cc:
            return 0
        if shared and "s-maxage" in cc:
            return cc["s-maxage"]
        if "max-age" in cc:
            return cc["max-age"]
        if expires_delta is not None:
            return max(0, expires_delta)
        if last_modified_delta is not None:
            return max(0, last_modified_delta // 10)
        return 0


    def state(cc, age, shared=False, **kw):
        lifetime = freshness_lifetime(cc, shared, **kw)
        if age < lifetime:
            return "fresh"
        window = cc.get("stale-while-revalidate")
        if window is not None and age < lifetime + window:
            if "must-revalidate" not in cc and not (shared and "proxy-revalidate" in cc):
                return "stale-usable"
        return "stale"


    def vary_key(vary, request_headers):
        names = split_list(vary)
        if "*" in names:
            return None
        lowered = {}
        for k, v in request_headers.items():
            lowered[k.lower()] = v
        key = []
        for name in sorted({n.lower() for n in names}):
            val = " ".join(lowered.get(name, "").split())
            key.append((name, val))
        return tuple(key)
''')

CACHE_VISIBLE = dd(r'''
    import unittest

    from cachelens import freshness_lifetime, parse_cache_control, split_list


    class BasicTests(unittest.TestCase):
        def test_split(self):
            self.assertEqual(split_list('a, b="x,y" ,, c'), ["a", 'b="x,y"', "c"])

        def test_parse(self):
            self.assertEqual(parse_cache_control("Max-Age=60, no-cache"), {"max-age": 60, "no-cache": True})

        def test_lifetime(self):
            self.assertEqual(freshness_lifetime({"max-age": 30}), 30)


    if __name__ == "__main__":
        unittest.main()
''')

CACHE_HIDDEN = dd(r'''
    import unittest

    from cachelens import freshness_lifetime, parse_cache_control, split_list, state, vary_key


    class SplitList(unittest.TestCase):
        def test_basic(self):
            self.assertEqual(split_list("a,b, c ,d"), ["a", "b", "c", "d"])
            self.assertEqual(split_list(""), [])
            self.assertEqual(split_list(" , ,"), [])
            self.assertEqual(split_list("one"), ["one"])

        def test_quotes(self):
            self.assertEqual(split_list('a="1,2", b'), ['a="1,2"', "b"])
            self.assertEqual(split_list('a="x\\",y", b'), ['a="x\\",y"', "b"])
            self.assertEqual(split_list('a="x\\\\", b'), ['a="x\\\\"', "b"])
            self.assertEqual(split_list('"a,b","c"'), ['"a,b"', '"c"'])


    class ParseCC(unittest.TestCase):
        def test_flags_and_numbers(self):
            self.assertEqual(parse_cache_control("public, max-age=300, must-revalidate"),
                             {"public": True, "max-age": 300, "must-revalidate": True})

        def test_names_lowercased_and_spacing(self):
            self.assertEqual(parse_cache_control("  No-Store ,MAX-AGE = 5 "), {"no-store": True, "max-age": 5})

        def test_quoted_values(self):
            self.assertEqual(parse_cache_control('private="set-cookie, x", no-cache'), {"private": "set-cookie, x", "no-cache": True})
            self.assertEqual(parse_cache_control('ext="a\\"b"'), {"ext": 'a"b'})
            self.assertEqual(parse_cache_control("ext=plain"), {"ext": "plain"})
            self.assertEqual(parse_cache_control('ext=""'), {"ext": ""})

        def test_quoted_numbers_accepted(self):
            self.assertEqual(parse_cache_control('max-age="60"'), {"max-age": 60})

        def test_invalid_numbers_ignored(self):
            for v in ("max-age=abc", "max-age=-1", "max-age=1.5", "max-age=", "max-age= 5x", "max-age=+3"):
                self.assertEqual(parse_cache_control(v), {}, v)
            self.assertEqual(parse_cache_control("s-maxage=x, stale-if-error=-2, stale-while-revalidate=1_0"), {})

        def test_all_numeric_directives(self):
            got = parse_cache_control("max-age=1, s-maxage=2, stale-while-revalidate=3, stale-if-error=4")
            self.assertEqual(got, {"max-age": 1, "s-maxage": 2, "stale-while-revalidate": 3, "stale-if-error": 4})

        def test_zero_and_leading_zeros(self):
            self.assertEqual(parse_cache_control("max-age=0"), {"max-age": 0})
            self.assertEqual(parse_cache_control("max-age=007"), {"max-age": 7})

        def test_first_valid_occurrence_wins(self):
            self.assertEqual(parse_cache_control("max-age=10, max-age=20"), {"max-age": 10})
            self.assertEqual(parse_cache_control("max-age=x, max-age=20"), {"max-age": 20})
            self.assertEqual(parse_cache_control("no-cache, NO-CACHE"), {"no-cache": True})
            self.assertEqual(parse_cache_control("ext=a, ext=b"), {"ext": "a"})

        def test_empty(self):
            self.assertEqual(parse_cache_control(""), {})
            self.assertEqual(parse_cache_control("  ,  "), {})
            self.assertEqual(parse_cache_control("=5"), {})

        def test_commas_inside_quotes_do_not_split(self):
            self.assertEqual(parse_cache_control('x="a, max-age=9", max-age=1'), {"x": "a, max-age=9", "max-age": 1})


    class Lifetime(unittest.TestCase):
        def test_precedence(self):
            cc = {"max-age": 60, "s-maxage": 600}
            self.assertEqual(freshness_lifetime(cc), 60)
            self.assertEqual(freshness_lifetime(cc, shared=True), 600)
            self.assertEqual(freshness_lifetime({"max-age": 60}, shared=True), 60)
            self.assertEqual(freshness_lifetime({"s-maxage": 600}), 0)
            self.assertEqual(freshness_lifetime({"max-age": 60}, expires_delta=999), 60)

        def test_blockers(self):
            self.assertEqual(freshness_lifetime({"no-store": True, "max-age": 60}), 0)
            self.assertEqual(freshness_lifetime({"no-cache": True, "max-age": 60}), 0)
            self.assertEqual(freshness_lifetime({"no-cache": True}, expires_delta=100), 0)
            self.assertEqual(freshness_lifetime({"private": True, "max-age": 60}, shared=True), 0)
            self.assertEqual(freshness_lifetime({"private": True, "max-age": 60}, shared=False), 60)
            self.assertEqual(freshness_lifetime({"private": True, "s-maxage": 5}, shared=True), 0)

        def test_expires(self):
            self.assertEqual(freshness_lifetime({}, expires_delta=100), 100)
            self.assertEqual(freshness_lifetime({}, expires_delta=0), 0)
            self.assertEqual(freshness_lifetime({}, expires_delta=-50), 0)
            self.assertEqual(freshness_lifetime({}, expires_delta=-50, last_modified_delta=1000), 0)
            self.assertEqual(freshness_lifetime({"public": True}, expires_delta=7), 7)

        def test_heuristic(self):
            self.assertEqual(freshness_lifetime({}, last_modified_delta=1000), 100)
            self.assertEqual(freshness_lifetime({}, last_modified_delta=1009), 100)
            self.assertEqual(freshness_lifetime({}, last_modified_delta=9), 0)
            self.assertEqual(freshness_lifetime({}, last_modified_delta=-100), 0)
            self.assertEqual(freshness_lifetime({}, last_modified_delta=10), 1)

        def test_nothing(self):
            self.assertEqual(freshness_lifetime({}), 0)
            self.assertEqual(freshness_lifetime({"max-age": 0}, expires_delta=50), 0)


    class State(unittest.TestCase):
        def test_fresh_boundary(self):
            cc = {"max-age": 10}
            self.assertEqual(state(cc, 0), "fresh")
            self.assertEqual(state(cc, 9), "fresh")
            self.assertEqual(state(cc, 10), "stale")
            self.assertEqual(state(cc, 500), "stale")

        def test_zero_lifetime(self):
            self.assertEqual(state({}, 0), "stale")
            self.assertEqual(state({"max-age": 0}, 0), "stale")

        def test_stale_while_revalidate(self):
            cc = {"max-age": 10, "stale-while-revalidate": 5}
            self.assertEqual(state(cc, 9), "fresh")
            self.assertEqual(state(cc, 10), "stale-usable")
            self.assertEqual(state(cc, 14), "stale-usable")
            self.assertEqual(state(cc, 15), "stale")

        def test_must_revalidate_blocks_stale_usable(self):
            cc = {"max-age": 10, "stale-while-revalidate": 5, "must-revalidate": True}
            self.assertEqual(state(cc, 12), "stale")
            self.assertEqual(state(cc, 3), "fresh")

        def test_proxy_revalidate_only_for_shared(self):
            cc = {"max-age": 10, "stale-while-revalidate": 5, "proxy-revalidate": True}
            self.assertEqual(state(cc, 12, shared=True), "stale")
            self.assertEqual(state(cc, 12, shared=False), "stale-usable")

        def test_shared_lifetime_used(self):
            cc = {"max-age": 10, "s-maxage": 100}
            self.assertEqual(state(cc, 50, shared=True), "fresh")
            self.assertEqual(state(cc, 50), "stale")

        def test_extra_arguments(self):
            self.assertEqual(state({}, 50, expires_delta=100), "fresh")
            self.assertEqual(state({}, 150, expires_delta=100), "stale")
            self.assertEqual(state({"stale-while-revalidate": 20}, 105, expires_delta=100), "stale-usable")
            self.assertEqual(state({}, 5, last_modified_delta=100), "fresh")
            self.assertEqual(state({}, 10, last_modified_delta=100), "stale")

        def test_swr_zero(self):
            self.assertEqual(state({"max-age": 5, "stale-while-revalidate": 0}, 5), "stale")


    class Vary(unittest.TestCase):
        H = {"Accept-Encoding": "gzip, br", "ACCEPT": "text/html", "X-Empty": ""}

        def test_basic(self):
            self.assertEqual(vary_key("Accept-Encoding", self.H), (("accept-encoding", "gzip, br"),))

        def test_sorted_and_deduplicated(self):
            self.assertEqual(vary_key("Accept, accept-encoding, ACCEPT", self.H),
                             (("accept", "text/html"), ("accept-encoding", "gzip, br")))

        def test_missing_header_is_empty_string(self):
            self.assertEqual(vary_key("X-Nope, accept", self.H), (("accept", "text/html"), ("x-nope", "")))

        def test_blank_vary(self):
            self.assertEqual(vary_key("", self.H), ())
            self.assertEqual(vary_key(" , ", self.H), ())

        def test_star(self):
            self.assertEqual(vary_key("*", self.H), None)
            self.assertEqual(vary_key("accept, *", self.H), None)

        def test_whitespace_normalised(self):
            h = {"User-Agent": "  Mozilla   5.0 \t (X11) "}
            self.assertEqual(vary_key("user-agent", h), (("user-agent", "Mozilla 5.0 (X11)"),))

        def test_case_insensitive_names_last_wins(self):
            h = {"accept": "a", "Accept": "b"}
            self.assertEqual(vary_key("ACCEPT", h), (("accept", "b"),))

        def test_request_headers_untouched(self):
            h = dict(self.H)
            vary_key("accept", h)
            self.assertEqual(h, self.H)


    if __name__ == "__main__":
        unittest.main()
''')

CACHE = Lib(
    name="cachelens", lang="python", title="the edge-cache helpers (`cachelens.py`)",
    blurb="The asset proxy's edge cache uses this module to interpret `Cache-Control` and `Vary`.",
    files={"cachelens.py": CACHE_SRC, "README.md": CACHE_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": CACHE_VISIBLE},
    hidden_tests={"tests/test_full.py": CACHE_HIDDEN},
    mutate=["cachelens.py"], difficulty=2, tags=["http", "cache"],
    probes=[
        'split_list("a=\\"1,2\\", b,, c")',
        'parse_cache_control("No-Store, MAX-AGE = 5, ext=\\"a, b\\"")',
        'parse_cache_control("max-age=abc, max-age=20, max-age=30")',
        'freshness_lifetime({"max-age": 60, "s-maxage": 600}, shared=True)',
        'freshness_lifetime({"private": True, "max-age": 60}, shared=True)',
        'freshness_lifetime({}, expires_delta=-50)',
        'freshness_lifetime({}, last_modified_delta=1009)',
        'state({"max-age": 10, "stale-while-revalidate": 5}, 10)',
        'state({"max-age": 10, "stale-while-revalidate": 5, "proxy-revalidate": True}, 12, shared=True)',
        'vary_key("Accept, accept-encoding, ACCEPT", {"Accept": "x  y", "accept-encoding": "gzip"})',
        'vary_key("accept, *", {})',
    ],
    probe_import="from cachelens import *",
)


# ======================================================================================================================
# mountpath: virtual path normalisation and mount-table resolution
# ======================================================================================================================

MOUNT_README = dd(r'''
    # mountpath

    Virtual paths for the file-gateway. Paths are `/`-separated strings; they never touch the real file system.

    ## `normalize(path) -> str`
    `path` must start with `/` (else `ValueError`). Empty segments (`//`) and `.` segments are dropped; a `..` segment
    removes the previous segment, and at the root it does nothing (`/..` is `/`). The result starts with `/`, has no
    trailing slash except for the root itself, and `...` or any other dotted name is an ordinary segment.

    ## `join(base, *parts) -> str`
    Starts with `base` and applies each part in turn: a part that starts with `/` replaces everything so far, any other
    part is appended after a `/`. The result is `normalize`d. `base` must be absolute (`ValueError` otherwise).

    ## `segments(path) -> list[str]`
    The segments of `normalize(path)`; the root has none.

    ## `is_within(path, root) -> bool`
    True when the normalized `path` equals the normalized `root` or lies below it, compared per segment
    (`/srv/data2` is not within `/srv/data`). Everything is within `/`.

    ## `relative(src, dst) -> str`
    The relative path that leads from directory `src` to `dst` (both normalized first): `..` for every segment of `src`
    after the common prefix, followed by the rest of `dst`. Equal paths give `"."`.

    ## `resolve(path, mounts) -> str`
    `mounts` maps virtual prefixes to targets (absolute paths). `path` and the prefixes are normalized; the mount whose
    prefix is the longest one that `path` is within wins; the result is `join(target, relative-part)` where the
    relative part is what is left of `path` below the prefix (nothing left: just the normalized target). One
    substitution only. No mount applies: the normalized `path`.
''')

MOUNT_SRC = dd(r'''
    """Virtual path helpers."""


    def _check_abs(path):
        if not path.startswith("/"):
            raise ValueError("path must be absolute: %r" % path)


    def segments(path):
        _check_abs(path)
        out = []
        for seg in path.split("/"):
            if seg == "" or seg == ".":
                continue
            if seg == "..":
                if out:
                    out.pop()
                continue
            out.append(seg)
        return out


    def normalize(path):
        return "/" + "/".join(segments(path))


    def join(base, *parts):
        _check_abs(base)
        cur = base
        for part in parts:
            if part.startswith("/"):
                cur = part
            else:
                cur = cur + "/" + part
        return normalize(cur)


    def is_within(path, root):
        p, r = segments(path), segments(root)
        return len(p) >= len(r) and p[:len(r)] == r


    def relative(src, dst):
        a, b = segments(src), segments(dst)
        n = 0
        while n < len(a) and n < len(b) and a[n] == b[n]:
            n += 1
        parts = [".."] * (len(a) - n) + b[n:]
        return "/".join(parts) if parts else "."


    def resolve(path, mounts):
        p = segments(path)
        best = None
        for prefix, target in mounts.items():
            pre = segments(prefix)
            if len(pre) <= len(p) and p[:len(pre)] == pre:
                if best is None or len(pre) > len(best[0]):
                    best = (pre, target)
        if best is None:
            return normalize(path)
        pre, target = best
        rest = p[len(pre):]
        return join(target, *rest) if rest else normalize(target)
''')

MOUNT_VISIBLE = dd(r'''
    import unittest

    from mountpath import is_within, join, normalize, resolve


    class BasicTests(unittest.TestCase):
        def test_normalize(self):
            self.assertEqual(normalize("/a//b/./c/../d/"), "/a/b/d")

        def test_join(self):
            self.assertEqual(join("/srv", "data", "x.txt"), "/srv/data/x.txt")

        def test_within(self):
            self.assertTrue(is_within("/srv/data/x", "/srv"))

        def test_resolve(self):
            self.assertEqual(resolve("/pub/a.txt", {"/pub": "/srv/public"}), "/srv/public/a.txt")


    if __name__ == "__main__":
        unittest.main()
''')

MOUNT_HIDDEN = dd(r'''
    import unittest

    from mountpath import is_within, join, normalize, relative, resolve, segments


    class Normalize(unittest.TestCase):
        def test_basic(self):
            for src, want in (("/", "/"), ("//", "/"), ("/a", "/a"), ("/a/", "/a"), ("/a//b", "/a/b"), ("/./a/./b/.", "/a/b"),
                              ("/a/b/..", "/a"), ("/a/b/../..", "/"), ("/a/../b", "/b"), ("/a/./../b/c/..", "/b"),
                              ("/..", "/"), ("/../..", "/"), ("/../a", "/a"), ("/a/../../b", "/b"), ("/.", "/")):
                self.assertEqual(normalize(src), want, src)

        def test_dotted_names_are_segments(self):
            for src, want in (("/...", "/..."), ("/a/.../b", "/a/.../b"), ("/.hidden/x", "/.hidden/x"), ("/a../b", "/a../b"),
                              ("/a/..b", "/a/..b")):
                self.assertEqual(normalize(src), want, src)

        def test_relative_input_rejected(self):
            for src in ("", "a", "./a", "a/b", "../a"):
                with self.assertRaises(ValueError):
                    normalize(src)

        def test_idempotent(self):
            for src in ("/a//b/../c/./d/", "/../x", "/"):
                self.assertEqual(normalize(normalize(src)), normalize(src))


    class Segments(unittest.TestCase):
        def test_values(self):
            self.assertEqual(segments("/"), [])
            self.assertEqual(segments("/a/b/../c"), ["a", "c"])
            self.assertEqual(segments("/a/b/"), ["a", "b"])
            with self.assertRaises(ValueError):
                segments("a")


    class Join(unittest.TestCase):
        def test_basic(self):
            self.assertEqual(join("/a"), "/a")
            self.assertEqual(join("/a", "b"), "/a/b")
            self.assertEqual(join("/a/", "b/", "c"), "/a/b/c")
            self.assertEqual(join("/", "x"), "/x")
            self.assertEqual(join("/", "/"), "/")

        def test_absolute_part_restarts(self):
            self.assertEqual(join("/a", "/b", "c"), "/b/c")
            self.assertEqual(join("/a", "b", "/c/d", "e"), "/c/d/e")

        def test_dotdot(self):
            self.assertEqual(join("/a/b", "../c"), "/a/c")
            self.assertEqual(join("/a/b", "..", ".."), "/")
            self.assertEqual(join("/a", "../../.."), "/")
            self.assertEqual(join("/a", "b/../../c"), "/c")

        def test_empty_part(self):
            self.assertEqual(join("/a", ""), "/a")
            self.assertEqual(join("/a", "", "b"), "/a/b")

        def test_relative_base_rejected(self):
            with self.assertRaises(ValueError):
                join("a", "b")
            with self.assertRaises(ValueError):
                join("a", "/b")
            with self.assertRaises(ValueError):
                join("", "/b")


    class IsWithin(unittest.TestCase):
        def test_values(self):
            self.assertTrue(is_within("/srv/data/x", "/srv/data"))
            self.assertTrue(is_within("/srv/data", "/srv/data"))
            self.assertTrue(is_within("/srv/data/", "/srv/data"))
            self.assertFalse(is_within("/srv/data2", "/srv/data"))
            self.assertFalse(is_within("/srv", "/srv/data"))
            self.assertTrue(is_within("/anything", "/"))
            self.assertTrue(is_within("/", "/"))
            self.assertFalse(is_within("/", "/a"))
            self.assertFalse(is_within("/srv/other", "/srv/data"))

        def test_normalizes_both(self):
            self.assertTrue(is_within("/srv/data/../data/x", "/srv//data/."))
            self.assertFalse(is_within("/srv/data/../other", "/srv/data"))
            self.assertTrue(is_within("/srv/../etc", "/"))
            self.assertFalse(is_within("/srv/data/x", "/srv/data/x/y"))


    class Relative(unittest.TestCase):
        def test_values(self):
            for src, dst, want in (("/a/b", "/a/b/c/d", "c/d"), ("/a/b/c", "/a", "../.."), ("/a/b", "/a/c", "../c"),
                                   ("/a", "/a", "."), ("/", "/x/y", "x/y"), ("/x/y", "/", "../.."), ("/a/b/c", "/d", "../../../d"),
                                   ("/a/b", "/a/bc", "../bc"), ("/", "/", ".")):
                self.assertEqual(relative(src, dst), want, (src, dst))

        def test_normalizes_inputs(self):
            self.assertEqual(relative("/a/./b/", "/a//c/../b/x"), "x")
            self.assertEqual(relative("/a/b/..", "/a/"), ".")

        def test_round_trip_with_join(self):
            for src, dst in (("/a/b", "/a/c/d"), ("/x", "/y/z"), ("/p/q/r", "/p")):
                self.assertEqual(join(src, relative(src, dst)), normalize(dst))


    class Resolve(unittest.TestCase):
        M = {"/pub": "/srv/public", "/pub/private": "/vault", "/": "/srv/main", "/tmp//x/": "/scratch/"}

        def test_longest_prefix(self):
            self.assertEqual(resolve("/pub/a.txt", self.M), "/srv/public/a.txt")
            self.assertEqual(resolve("/pub/private/k", self.M), "/vault/k")
            self.assertEqual(resolve("/pub/privateer", self.M), "/srv/public/privateer")

        def test_exact_prefix_gives_target(self):
            self.assertEqual(resolve("/pub", self.M), "/srv/public")
            self.assertEqual(resolve("/pub/", self.M), "/srv/public")
            self.assertEqual(resolve("/pub/private", self.M), "/vault")
            self.assertEqual(resolve("/tmp/x", self.M), "/scratch")

        def test_root_mount_is_default(self):
            self.assertEqual(resolve("/etc/passwd", self.M), "/srv/main/etc/passwd")
            self.assertEqual(resolve("/", self.M), "/srv/main")

        def test_no_mount(self):
            self.assertEqual(resolve("/a//b/../c", {"/z": "/q"}), "/a/c")
            self.assertEqual(resolve("/a", {}), "/a")

        def test_normalizes_before_matching(self):
            self.assertEqual(resolve("/pub/x/../private/k", self.M), "/vault/k")
            self.assertEqual(resolve("/pub/../etc", self.M), "/srv/main/etc")
            self.assertEqual(resolve("/pub/../../../pub/a", self.M), "/srv/public/a")
            self.assertEqual(resolve("/tmp/x/deep/er", self.M), "/scratch/deep/er")

        def test_single_substitution(self):
            m = {"/a": "/b", "/b": "/c"}
            self.assertEqual(resolve("/a/x", m), "/b/x")

        def test_target_normalized(self):
            self.assertEqual(resolve("/a/x", {"/a": "/t//u/../v/"}), "/t/v/x")
            self.assertEqual(resolve("/a", {"/a": "/t//u/../v/"}), "/t/v")

        def test_dotdot_cannot_escape_target(self):
            self.assertEqual(resolve("/a/../../a/y", {"/a": "/t"}), "/t/y")

        def test_relative_path_rejected(self):
            with self.assertRaises(ValueError):
                resolve("a/b", self.M)


    if __name__ == "__main__":
        unittest.main()
''')

MOUNT = Lib(
    name="mountpath", lang="python", title="the virtual path helpers (`mountpath.py`)",
    blurb="The file gateway maps client-visible paths to storage locations with this module.",
    files={"mountpath.py": MOUNT_SRC, "README.md": MOUNT_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": MOUNT_VISIBLE},
    hidden_tests={"tests/test_full.py": MOUNT_HIDDEN},
    mutate=["mountpath.py"], difficulty=2, tags=["paths"],
    probes=[
        'normalize("/a/b/../../../c/./d//")',
        'normalize("/a/.../b/..x")',
        'join("/a/b", "../c", "/x", "y/../z")',
        'is_within("/srv/data2", "/srv/data")',
        'is_within("/srv/data/../data/x", "/srv//data/.")',
        'relative("/a/b/c", "/a/d")',
        'relative("/a/b", "/a/bc")',
        'resolve("/pub/private/k", {"/pub": "/srv/public", "/pub/private": "/vault"})',
        'resolve("/pub/privateer", {"/pub": "/srv/public", "/pub/private": "/vault"})',
        'resolve("/etc/hosts", {"/": "/srv/main"})',
    ],
    probe_import="from mountpath import *",
)


LIBS = [NEG, CACHE, MOUNT]
register_libs(LIBS, n=10)
