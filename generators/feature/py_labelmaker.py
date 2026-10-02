"""labelmaker (python): a text template engine for shipping labels extended with names, batches, escapes, paths, defaults, filters, conditionals and loops."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # labelmaker

    A small template engine for the shipping labels and order mails of a web shop (Python 3, standard library only). Run the
    tests with `python3 -m unittest discover -s tests`.

    ## Layout

    * `labelmaker/template.py`: `Template`, `TemplateError`, `MissingValue`.
    * `tests/`: tests.

    ## Basics

    * `Template(text)` parses a template (`TypeError` for anything but a string). A tag is `[[ name ]]`: two opening brackets, a
      name made of letters, digits and underscores that does not start with a digit, optional white space around it (including
      line breaks) and two closing brackets. Everything else is literal text and is copied unchanged. A tag with anything else in
      it (an empty tag, a bad name) and an opening `[[` without a closing `]]` are errors at parse time: `TemplateError`. A
      stray `]]` is literal text. `template.source` is the original text.
    * `template.render(data)` fills the tags from the dict `data` (`TypeError` for anything else) and returns the text. A value
      is written with `str()`, except `None`, which is written as an empty string. A name that `data` does not have raises
      `MissingValue`. Templates can be rendered any number of times and `data` is never modified.
    * `TemplateError` is an `Exception`; `MissingValue` is both a `TemplateError` and a `KeyError` and has the attribute `name`.
''')

TEMPLATE = '''\
"""A small template engine."""
import re
@@uniq imports


class TemplateError(Exception):
    pass


class MissingValue(TemplateError, KeyError):
    def __init__(self, name):
        super().__init__(name)
        self.name = name

    def __str__(self):
        return f"no value for {self.name!r}"


_TAG = re.compile(r"\\[\\[(.*?)\\]\\]", re.S)

@@default name_re
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
@@end

@@blocks helpers


def _lit(s):
    @@default lit_body
    return s
    @@end


@@default resolve_fn
def _resolve(scope, name):
    """The value of `name` in one scope; raises KeyError when it is not there."""
    return scope[name]
@@end


def _lookup(scopes, name):
    for scope in reversed(scopes):
        try:
            return _resolve(scope, name)
        except (KeyError, IndexError, TypeError):
            continue
    raise MissingValue(name)


@@default value_of
def _value_of(node, scopes):
    return _lookup(scopes, node[1])
@@end


def _var_node(tag):
    expr = tag
    filters = []
    default = None
    @@slot var_syntax
    if not _NAME.fullmatch(expr):
        raise TemplateError(f"bad tag: {tag!r}")
    return ("var", expr, filters, default)


def _parse(text):
    @@slot pre_scan
    root = []
    stack = []
    current = root
    pos = 0
    for m in _TAG.finditer(text):
        if m.start() > pos:
            current.append(("text", _lit(text[pos:m.start()])))
        pos = m.end()
        tag = m.group(1).strip()
        @@slot block_tags
        current.append(_var_node(tag))
    if "[[" in text[pos:]:
        raise TemplateError("unterminated tag")
    if pos < len(text):
        current.append(("text", _lit(text[pos:])))
    if stack:
        raise TemplateError(f"unclosed block: {stack[-1]['kind']}")
    return root


def _render(nodes, scopes):
    out = []
    for node in nodes:
        kind = node[0]
        if kind == "text":
            out.append(node[1])
        elif kind == "var":
            value = _value_of(node, scopes)
            text = "" if value is None else str(value)
            @@slot apply_filters
            out.append(text)
        @@slot render_kinds
    return "".join(out)


class Template:
    def __init__(self, text):
        if not isinstance(text, str):
            raise TypeError("a template is a string")
        self.source = text
        self._nodes = _parse(text)

    def render(self, data):
        if not isinstance(data, dict):
            raise TypeError("data must be a dict")
        return _render(self._nodes, [data])

    @@blocks methods
'''

INIT = '''\
"""Templates."""
from .template import MissingValue, Template, TemplateError
@@uniq exports
'''

HELPERS = '''\
import unittest
@@uniq imports

from labelmaker import MissingValue, Template, TemplateError


def render(text, data=None):
    return Template(text).render(data or {})

'''

VISIBLE = HELPERS + '''
class BasicTests(unittest.TestCase):
    def test_render(self):
        self.assertEqual(render("Hello, [[name]]!", {"name": "Ana"}), "Hello, Ana!")
        self.assertEqual(render("[[ a ]]-[[b]]", {"a": 1, "b": None}), "1-")
        self.assertEqual(Template("x").source, "x")

    def test_errors(self):
        with self.assertRaises(MissingValue):
            render("[[nope]]")
        with self.assertRaises(TemplateError):
            Template("Hi [[name")
        with self.assertRaises(TemplateError):
            Template("[[ 1abc ]]")
        with self.assertRaises(TypeError):
            Template(5)
    @@blocks tests
'''

HIDDEN = HELPERS + '''
class FeatureTests(unittest.TestCase):
    def test_base_parsing(self):
        self.assertEqual(render("plain text"), "plain text")
        self.assertEqual(render(""), "")
        self.assertEqual(render("[[a]][[b]]", {"a": "x", "b": "y"}), "xy")
        self.assertEqual(render("[[ name ]]|[[\\tname\\n]]|[[name]]", {"name": "N"}), "N|N|N")
        self.assertEqual(render("line1\\n[[a]]\\n\\nline3", {"a": "A"}), "line1\\nA\\n\\nline3")
        self.assertEqual(render("a ]] b [ c ] [[x]] [", {"x": "X"}), "a ]] b [ c ] X [")
        self.assertEqual(render("[[_private]] [[a_1]] [[A]]", {"_private": 1, "a_1": 2, "A": 3}), "1 2 3")
        for bad in ["[[]]", "[[ ]]", "[[1abc]]", "[[a b]]", "[[a-b]]", "[[a,b]]", "[[ a ]", "x [[", "[[a]] [[b", "[[[a]]", "[[a]]]]x[["]:
            with self.assertRaises(TemplateError, msg=bad):
                Template(bad)

    def test_base_values(self):
        self.assertEqual(render("[[n]] [[f]] [[b]] [[z]] [[e]] [[l]]", {"n": 5, "f": 2.5, "b": True, "z": None, "e": "", "l": [1, 2]}), "5 2.5 True   [1, 2]")
        self.assertEqual(render("[[a]] [[a]] [[a]]", {"a": "x"}), "x x x")
        t = Template("Hi [[name]]")
        data = {"name": "Ana", "unused": 1}
        self.assertEqual(t.render(data), "Hi Ana")
        self.assertEqual(t.render({"name": "Bo"}), "Hi Bo")
        self.assertEqual(data, {"name": "Ana", "unused": 1})
        self.assertEqual(t.source, "Hi [[name]]")

    def test_base_errors(self):
        with self.assertRaises(MissingValue) as cm:
            render("Hi [[name]]", {"other": 1})
        self.assertEqual(cm.exception.name, "name")
        self.assertIsInstance(cm.exception, KeyError)
        self.assertIsInstance(cm.exception, TemplateError)
        with self.assertRaises(MissingValue):
            render("[[a]] [[b]]", {"a": 1})
        for bad in [5, None, b"x", ["a"], {"a": 1}]:
            with self.assertRaises(TypeError, msg=repr(bad)):
                Template(bad)
        t = Template("x")
        for bad in [None, [], "x", 5, ("a", 1)]:
            with self.assertRaises(TypeError, msg=repr(bad)):
                t.render(bad)
        self.assertEqual(t.render({}), "x")
        self.assertTrue(issubclass(MissingValue, TemplateError))
    @@blocks tests
'''


def make_slices(rng: random.Random):
    ell = rng.choice(["…", "..."])
    S = []

    S.append(Slice(
        id="names", title="Listing the names a template uses", d=1,
        pitch=("The order mail template changed and nobody knows which fields the shop has to supply.",
               "Callers want to know which values a template needs."),
        reqs=("`template.names()` returns the sorted list of the distinct names used in the template's tags, exactly as written in the tag. A template without tags gives an empty list.",),
        code={
            "labelmaker/template.py::helpers": '''
                def _collect(nodes, out):
                    for node in nodes:
                        if node[0] == "var":
                            out.add(node[1])
                        @@slot collect_kinds
            ''',
            "labelmaker/template.py::methods": '''
                def names(self):
                    out = set()
                    _collect(self._nodes, out)
                    return sorted(out)
            ''',
        },
        readme="## Listing the names a template uses\n\n`template.names()` is the sorted list of the distinct names in the tags.\n",
        vtests='''
            def test_names_basic(self):
                self.assertEqual(Template("[[b]] [[a]] [[b]]").names(), ["a", "b"])
        ''',
        tests='''
            def test_names(self):
                self.assertEqual(Template("Dear [[name]], your order [[ order_id ]] ships to [[city]]. [[name]]!").names(), ["city", "name", "order_id"])
                self.assertEqual(Template("no tags here").names(), [])
                self.assertEqual(Template("").names(), [])
                self.assertEqual(Template("[[B]][[a]][[_c]]").names(), ["B", "_c", "a"])
        ''',
        cross={
            "paths": {"tests": '''
                def test_names_with_paths(self):
                    self.assertEqual(Template("[[a.b.c]] [[a.b.c]] [[d]] [[items.0.sku]]").names(), ["a.b.c", "d", "items.0.sku"])
            '''},
            "if": {
                "reqs": ("Names used in conditions and in both branches of a block count.",),
                "code": {"labelmaker/template.py::collect_kinds": '''
                    elif node[0] == "if":
                        out.add(node[1])
                        _collect(node[2], out)
                        _collect(node[3], out)
                '''},
                "tests": '''
                    def test_names_in_conditionals(self):
                        self.assertEqual(Template("[[#if vip]]Hi [[name]][[else]]Hello [[guest]][[/if]]").names(), ["guest", "name", "vip"])
                '''},
            "each": {
                "reqs": ("The name of the list and the names used inside the loop body count (a name inside the body may refer to a key of the items); `this` and the `@` variables do not count.",),
                "code": {"labelmaker/template.py::collect_kinds": '''
                    elif node[0] == "each":
                        out.add(node[1])
                        inner = set()
                        _collect(node[2], inner)
                        out.update(inner - {"this", "@index", "@number"})
                '''},
                "tests": '''
                    def test_names_in_loops(self):
                        self.assertEqual(Template("[[#each items]][[this]] [[@index]] [[sku]][[/each]]").names(), ["items", "sku"])
                '''},
        },
    ))

    S.append(Slice(
        id="render-many", title="Rendering a batch", d=1,
        pitch=("Printing a day's labels means calling render in a loop and collecting the strings by hand.",
               "Callers want to render the same template for many records at once."),
        reqs=("`template.render_many(rows)` renders the template once for every item of `rows` (any iterable) and returns the list of results in the same order. Every item must be a dict (`TypeError` otherwise). The first error stops the batch and is raised as it is. An empty iterable gives an empty list.",),
        code={
            "labelmaker/template.py::methods": '''
                def render_many(self, rows):
                    return [self.render(row) for row in rows]
            ''',
        },
        readme="## Rendering a batch\n\n`template.render_many(rows)` renders once per item (dicts only) and returns the list of results.\n",
        vtests='''
            def test_render_many_basic(self):
                self.assertEqual(Template("x [[n]]").render_many([{"n": 1}, {"n": 2}]), ["x 1", "x 2"])
        ''',
        tests='''
            def test_render_many(self):
                t = Template("Label [[n]]: [[who]]")
                rows = [{"n": 1, "who": "Ana"}, {"n": 2, "who": "Bo"}, {"n": 3, "who": None}]
                self.assertEqual(t.render_many(rows), ["Label 1: Ana", "Label 2: Bo", "Label 3: "])
                self.assertEqual(t.render_many(iter(rows[:1])), ["Label 1: Ana"])
                self.assertEqual(t.render_many([]), [])
                self.assertEqual(t.render_many(r for r in rows[1:]), ["Label 2: Bo", "Label 3: "])
                self.assertEqual(Template("fixed").render_many([{}, {}]), ["fixed", "fixed"])

            def test_render_many_errors(self):
                t = Template("[[a]]")
                with self.assertRaises(MissingValue):
                    t.render_many([{"a": 1}, {"b": 2}])
                with self.assertRaises(TypeError):
                    t.render_many([{"a": 1}, "not a dict"])
                with self.assertRaises(TypeError):
                    t.render_many([["a", 1]])
                seen = []

                def rows():
                    for r in [{"a": 1}, {"b": 2}, {"a": 3}]:
                        seen.append(r)
                        yield r

                with self.assertRaises(MissingValue):
                    t.render_many(rows())
                self.assertEqual(len(seen), 2)
        ''',
    ))

    S.append(Slice(
        id="escape", title="Escaped brackets", d=2,
        pitch=("Help texts that explain the template syntax cannot show a literal tag.",
               "Templates need a way to contain a literal `[[`."),
        reqs=("A backslash directly in front of `[[` escapes it: the backslash disappears and the two brackets are literal text, so what follows (including a matching `]]`) is not a tag. Every other backslash is literal, so `\\\\[[x]]` is a literal backslash followed by an escaped `[[` (rendered as `\\[[x]]`). An escaped `[[` does not need a closing `]]`.",),
        code={
            "labelmaker/template.py::pre_scan": 'text = text.replace("\\\\[[", "\\x00")',
            "labelmaker/template.py::helpers": '''
                def _unescape(s):
                    return s.replace("\\x00", "[[")
            ''',
            "labelmaker/template.py::lit_body": "return _unescape(s)",
        },
        readme="## Escaped brackets\n\n`\\[[` renders a literal `[[` (the backslash disappears); other backslashes are literal.\n",
        vtests='''
            def test_escape_basic(self):
                self.assertEqual(render("\\\\[[a]] [[a]]", {"a": 1}), "[[a]] 1")
        ''',
        tests='''
            def test_escaped_brackets(self):
                self.assertEqual(render("Use \\\\[[name]] to insert a name: [[name]]", {"name": "Ana"}), "Use [[name]] to insert a name: Ana")
                self.assertEqual(render("\\\\[[ \\\\[[ \\\\[[", {}), "[[ [[ [[")
                self.assertEqual(render("never closed: \\\\[[ and [[a]]", {"a": 1}), "never closed: [[ and 1")
                self.assertEqual(render("C:\\\\temp [[name]] a\\\\b", {"name": "Ana"}), "C:\\\\temp Ana a\\\\b")
                self.assertEqual(render("\\\\\\\\[[name]]", {"name": "Ana"}), "\\\\[[name]]")
                self.assertEqual(render("\\\\[[name]] and \\\\[[other]]", {}), "[[name]] and [[other]]")
                self.assertEqual(render("[[a]]\\\\[[b]]", {"a": "A"}), "A[[b]]")
                self.assertEqual(render("\\\\[[a]]]]", {}), "[[a]]]]")

            def test_unescaped_errors_remain(self):
                with self.assertRaises(TemplateError):
                    Template("\\\\[[ ok but [[ not closed")
                with self.assertRaises(MissingValue):
                    render("\\\\[[ a ]] [[b]]")
        ''',
    ))

    S.append(Slice(
        id="paths", title="Dotted paths", d=2,
        pitch=("Orders are nested dicts and the shop has to flatten them before every render.",
               "Tags should be able to reach into nested data."),
        reqs=("A name can be a dotted path such as `customer.address.city` or `items.0.sku`: the parts are separated by single dots, the first part is a name as before and the others are names or whole numbers (`[A-Za-z_][A-Za-z0-9_]*` or digits); anything else (`a..b`, `.a`, `a.`, `a.-1`, `1.a`) is a `TemplateError` at parse time. The value is found by walking the data: a dict part is looked up as a key, a number part indexes a list or tuple. When a part is missing, out of range or the value along the way is anything else (`None`, a string, a number), the whole path is missing: `MissingValue` with the full path as `name`. A key that itself contains a dot is not found by its name; paths always walk.",),
        code={
            "labelmaker/template.py::name_re": '''
                _NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\\.([A-Za-z_][A-Za-z0-9_]*|[0-9]+))*")
            ''',
            "labelmaker/template.py::resolve_fn": '''
                def _resolve(scope, name):
                    cur = scope
                    for part in name.split("."):
                        if isinstance(cur, dict):
                            cur = cur[part]
                        elif isinstance(cur, (list, tuple)) and part.isdigit():
                            cur = cur[int(part)]
                        else:
                            raise KeyError(name)
                    return cur
            ''',
        },
        readme="## Dotted paths\n\n`[[customer.address.city]]` and `[[items.0.sku]]` walk dicts and lists; a broken path is `MissingValue` with the full path.\n",
        vtests='''
            def test_paths_basic(self):
                self.assertEqual(render("[[a.b]]", {"a": {"b": "x"}}), "x")
        ''',
        tests='''
            DATA = {"customer": {"name": "Ana", "address": {"city": "Oslo"}, "nick": None},
                    "items": [{"sku": "A1"}, {"sku": "B2"}], "pair": (7, 8), "n": None, "flat": {"a.b": "no"}}

            def test_paths(self):
                self.assertEqual(render("[[customer.address.city]], [[ customer.name ]]", self.DATA), "Oslo, Ana")
                self.assertEqual(render("[[items.0.sku]] [[items.1.sku]] [[pair.1]] [[pair.0]]", self.DATA), "A1 B2 8 7")
                self.assertEqual(render("[[customer.nick]]|", self.DATA), "|")
                self.assertEqual(render("[[customer]]", self.DATA), str(self.DATA["customer"]))
                self.assertEqual(render("[[items.0]]", self.DATA), "{'sku': 'A1'}")
                self.assertEqual(render("[[n]]", self.DATA), "")

            def test_missing_paths(self):
                for path in ["customer.phone", "items.5.sku", "items.sku", "n.x", "customer.name.x", "pair.2", "nothing.here", "flat.a.b", "customer.nick.x"]:
                    with self.assertRaises(MissingValue, msg=path) as cm:
                        render("[[" + path + "]]", self.DATA)
                    self.assertEqual(cm.exception.name, path)

            def test_path_syntax(self):
                for bad in ["a..b", ".a", "a.", "a.-1", "1.a", "a.b-c", "a. b", "a.b.", "..", "a.1b"]:
                    with self.assertRaises(TemplateError, msg=bad):
                        Template("[[" + bad + "]]")
                self.assertEqual(render("[[a.0.b.1]]", {"a": [{"b": [0, 9]}]}), "9")
                self.assertEqual(render("[[a.00]]", {"a": [5]}), "5")
        ''',
    ))

    S.append(Slice(
        id="defaults", title="Fallback texts", d=2,
        pitch=("Labels show 'None' or an empty gap when the customer has no company name.",
               "Tags need a fallback for values that are missing or empty."),
        reqs=("A tag can carry a fallback: `[[ nick or \"friend\" ]]` (the name, the word `or` between blanks, and a text in double quotes that contains no double quote; it may be empty and may contain blanks). The fallback is used when the name is missing, `None` or an empty string; any other value (including `0` and `False`) is written as usual. A tag with a fallback never raises `MissingValue`. A malformed fallback (no quotes, an unterminated quote, nothing after `or`) is a `TemplateError` at parse time.",),
        code={
            "labelmaker/template.py::var_syntax": '''
                m = re.fullmatch(r'(\\S+)\\s+or\\s+"([^"]*)"', expr)
                if m:
                    expr, default = m.group(1), m.group(2)
            ''',
            "labelmaker/template.py::value_of": '''
                def _value_of(node, scopes):
                    default = node[3]
                    try:
                        value = _lookup(scopes, node[1])
                    except MissingValue:
                        if default is None:
                            raise
                        return default
                    if default is not None and (value is None or value == ""):
                        return default
                    return value
            ''',
        },
        readme="## Fallback texts\n\n`[[ nick or \"friend\" ]]` writes the fallback when the value is missing, `None` or empty.\n",
        vtests='''
            def test_default_basic(self):
                self.assertEqual(render('[[ nick or "friend" ]]', {}), "friend")
        ''',
        tests='''
            def test_defaults(self):
                t = Template('Hi [[ nick or "dear friend" ]]!')
                self.assertEqual(t.render({}), "Hi dear friend!")
                self.assertEqual(t.render({"nick": None}), "Hi dear friend!")
                self.assertEqual(t.render({"nick": ""}), "Hi dear friend!")
                self.assertEqual(t.render({"nick": "Ana"}), "Hi Ana!")
                self.assertEqual(t.render({"nick": 0}), "Hi 0!")
                self.assertEqual(t.render({"nick": False}), "Hi False!")
                self.assertEqual(t.render({"nick": " "}), "Hi  !")
                self.assertEqual(render('[[a or ""]]|[[b or "x y"]]', {"b": None}), "|x y")
                self.assertEqual(render('[[a   or   "x"]]', {}), "x")
                self.assertEqual(render('[[ a or "[b]" ]]', {}), "[b]")

            def test_default_syntax_errors(self):
                for bad in ['a or friend', 'a or "unterminated', 'a or', 'a or "x" "y"', 'a or "x"y', 'a or "a"b"', 'a "x"', 'a or \\'x\\'']:
                    with self.assertRaises(TemplateError, msg=bad):
                        Template("[[" + bad + "]]")
                with self.assertRaises(MissingValue):
                    render("[[a]]")
        ''',
        cross={
            "paths": {"tests": '''
                def test_defaults_with_paths(self):
                    self.assertEqual(render('[[ customer.nick or "anon" ]]', {"customer": {"nick": None}}), "anon")
                    self.assertEqual(render('[[ customer.nick or "anon" ]]', {}), "anon")
                    self.assertEqual(render('[[ customer.nick or "anon" ]]', {"customer": "text"}), "anon")
                    self.assertEqual(render('[[ customer.nick or "anon" ]]', {"customer": {"nick": "Bo"}}), "Bo")
            '''},
        },
    ))

    S.append(Slice(
        id="filters", title="Filters", d=3,
        pitch=("Names arrive in all capitals or with stray blanks and the label printer has a 20 character limit.",
               "Tags should be able to transform the value before it is written."),
        reqs=(f"A tag can end in a chain of filters separated by `|`: `[[ name | trim | upper ]]`. The filters work on the text of the value (`None` is the empty string) from left to right: `upper`, `lower`, `title` (Python's `str.title`), `trim` (`str.strip`), `trunc:N` (when the text is longer than N characters, its first N - 1 characters followed by `{ell}`, otherwise unchanged; N at least 1) and `pad:N` (pad on the right with blanks to N characters; N at least 0, no cutting). Arguments follow the colon directly and contain no blanks. Unknown filters, a missing or invalid argument, an argument for a filter without one, and an empty filter (`name |`) are a `TemplateError` at parse time. Filters are applied after the value was found (and after a fallback, if the tag has one).",),
        code={
            "labelmaker/template.py::helpers": f'''
                def _make_filter(name, arg, tag):
                    if name in ("upper", "lower", "title", "trim"):
                        if arg != "":
                            raise TemplateError(f"filter {{name}} takes no argument: {{tag!r}}")
                        return {{"upper": str.upper, "lower": str.lower, "title": str.title, "trim": str.strip}}[name]
                    if name in ("trunc", "pad"):
                        if not re.fullmatch(r"[0-9]+", arg) or (name == "trunc" and int(arg) < 1):
                            raise TemplateError(f"filter {{name}} needs a number argument: {{tag!r}}")
                        n = int(arg)
                        if name == "pad":
                            return lambda s: s.ljust(n)
                        return lambda s: s if len(s) <= n else s[: n - 1] + "{ell}"
                    raise TemplateError(f"unknown filter {{name!r}}: {{tag!r}}")
            ''',
            "labelmaker/template.py::var_syntax": '''
                m = re.fullmatch(r"(.*?)((?:\\s*\\|\\s*[A-Za-z_]+(?::[^|\\s]*)?)+)\\s*", expr, re.S)
                if m:
                    expr = m.group(1).strip()
                    for part in m.group(2).split("|")[1:]:
                        fname, _, arg = part.strip().partition(":")
                        filters.append(_make_filter(fname, arg, tag))
            ''',
            "labelmaker/template.py::apply_filters": '''
                for f in node[2]:
                    text = f(text)
            ''',
        },
        readme=f"## Filters\n\n`[[ name | trim | upper ]]`: `upper`, `lower`, `title`, `trim`, `trunc:N` (cut with `{ell}`) and `pad:N`. Unknown filters and bad arguments are a `TemplateError` at parse time.\n",
        vtests='''
            def test_filters_basic(self):
                self.assertEqual(render("[[a | upper]]", {"a": "x"}), "X")
        ''',
        tests=fmt('''
            def test_filters(self):
                self.assertEqual(render("[[ name | upper ]]", {"name": "Ana"}), "ANA")
                self.assertEqual(render("[[name|lower]]", {"name": "ANA"}), "ana")
                self.assertEqual(render("[[ name | title ]]", {"name": "hello wORLD"}), "Hello World")
                self.assertEqual(render("[[ name | trim | upper ]]", {"name": "  ana  "}), "ANA")
                self.assertEqual(render("[[ name | upper | trim ]]", {"name": "  ana  "}), "ANA")
                self.assertEqual(render("[[ n | pad:4 ]]|", {"n": 5}), "5   |")
                self.assertEqual(render("[[ n | pad:0 ]][[ n | pad:1 ]]", {"n": "abc"}), "abcabc")
                self.assertEqual(render("[[ z | upper ]]|[[ z | pad:2 ]]|", {"z": None}), "|  |")
                self.assertEqual(render("[[a | trim | pad:6 | upper]]|", {"a": " ab "}), "AB    |")

            def test_trunc(self):
                self.assertEqual(render("[[ t | trunc:5 ]]", {"t": "abcdefgh"}), "abcd__E__")
                self.assertEqual(render("[[ t | trunc:5 ]]", {"t": "abcde"}), "abcde")
                self.assertEqual(render("[[ t | trunc:5 ]]", {"t": "abc"}), "abc")
                self.assertEqual(render("[[ t | trunc:1 ]]", {"t": "ab"}), "__E__")
                self.assertEqual(render("[[ t | trunc:1 ]]", {"t": "a"}), "a")
                self.assertEqual(render("[[ t | trunc:3 | upper ]]", {"t": "abcdef"}), "AB__E__")
                self.assertEqual(render("[[ t | upper | trunc:3 ]]", {"t": "abcdef"}), "AB__E__")

            def test_filter_syntax_errors(self):
                for bad in ["a | shout", "a | upper:1", "a | trunc", "a | trunc:", "a | trunc:x", "a | trunc:0", "a | trunc:-1", "a | pad", "a | pad:x",
                            "a |", "| upper", "a | | upper", "a | trunc: 5", "a | up per", "a | 5"]:
                    with self.assertRaises(TemplateError, msg=bad):
                        Template("[[" + bad + "]]")
                with self.assertRaises(MissingValue):
                    render("[[ a | upper ]]")
        ''', E=ell),
        cross={
            "defaults": {
                "reqs": ("Filters also apply to the fallback text.",),
                "tests": '''
                    def test_filters_after_defaults(self):
                        self.assertEqual(render('[[ nick or "my friend" | title ]]', {}), "My Friend")
                        self.assertEqual(render('[[ nick or "a | b" | upper ]]', {"nick": None}), "A | B")
                        self.assertEqual(render('[[ nick or "x" | pad:3 ]]|', {"nick": ""}), "x  |")
                        self.assertEqual(render('[[ nick or "x" | upper ]]', {"nick": "ana"}), "ANA")
                '''},
            "paths": {"tests": '''
                def test_filters_with_paths(self):
                    self.assertEqual(render("[[ customer.name | upper ]]", {"customer": {"name": "ana"}}), "ANA")
                    with self.assertRaises(MissingValue) as cm:
                        render("[[ customer.name | upper ]]", {"customer": {}})
                    self.assertEqual(cm.exception.name, "customer.name")
            '''},
            "escape": {"tests": '''
                def test_filters_and_escapes(self):
                    self.assertEqual(render("\\\\[[a | upper]] [[a | upper]]", {"a": "x"}), "[[a | upper]] X")
            '''},
        },
    ))

    S.append(Slice(
        id="if", title="Conditional blocks", d=4,
        pitch=("Labels for premium customers carry an extra line and the shop keeps two template files.",
               "Templates need blocks that only appear when a value is set."),
        reqs=("`[[#if name]] ... [[else]] ... [[/if]]` renders the first part when the name is truthy and the second part (if there is one) otherwise. The name follows the rules of tag names (so dotted paths work when the template supports them). A value is truthy when Python says so (`bool(value)`: `None`, `False`, `0`, `\"\"`, `[]` and `{}` are not, `\"0\"` is), and a name that is missing counts as not truthy without raising an error. Only the chosen part is rendered, so names that are only used in the other part may be missing. Blocks can be nested.",
              "Parse errors, all `TemplateError`: an `#if` without a name or with a bad name, `[[else]]` or `[[/if]]` outside of an `#if` block (or inside another kind of block), a second `[[else]]` in the same block, and an `#if` that is never closed."),
        code={
            "labelmaker/template.py::block_tags": '''
                if tag == "#if" or tag.startswith("#if "):
                    cond = tag[3:].strip()
                    if not _NAME.fullmatch(cond):
                        raise TemplateError(f"bad condition: {tag!r}")
                    node = ("if", cond, [], [])
                    current.append(node)
                    stack.append({"kind": "if", "node": node, "parent": current, "else": False})
                    current = node[2]
                    continue
                if tag == "else":
                    if not stack or stack[-1]["kind"] != "if" or stack[-1]["else"]:
                        raise TemplateError("unexpected [[else]]")
                    stack[-1]["else"] = True
                    current = stack[-1]["node"][3]
                    continue
                if tag == "/if":
                    if not stack or stack[-1]["kind"] != "if":
                        raise TemplateError("unexpected [[/if]]")
                    current = stack.pop()["parent"]
                    continue
            ''',
            "labelmaker/template.py::helpers": '''
                def _truthy(scopes, name):
                    try:
                        return bool(_lookup(scopes, name))
                    except MissingValue:
                        return False
            ''',
            "labelmaker/template.py::render_kinds": '''
                elif kind == "if":
                    out.append(_render(node[2] if _truthy(scopes, node[1]) else node[3], scopes))
            ''',
        },
        readme="## Conditional blocks\n\n`[[#if name]]...[[else]]...[[/if]]` renders by truthiness (missing counts as false); blocks nest; malformed blocks are a `TemplateError` at parse time.\n",
        vtests='''
            def test_if_basic(self):
                self.assertEqual(render("[[#if vip]]VIP[[/if]]", {"vip": True}), "VIP")
        ''',
        tests='''
            def test_if_else(self):
                t = Template("[[#if vip]]VIP [[name]][[else]]guest[[/if]]!")
                self.assertEqual(t.render({"vip": True, "name": "Ana"}), "VIP Ana!")
                for falsy in [False, None, 0, "", [], {}, 0.0]:
                    self.assertEqual(t.render({"vip": falsy}), "guest!", repr(falsy))
                self.assertEqual(t.render({}), "guest!")
                for truthy in [True, 1, "0", "x", [0], {"a": 1}, -1]:
                    self.assertEqual(t.render({"vip": truthy, "name": "N"}), "VIP N!", repr(truthy))
                self.assertEqual(render("[[#if a]]yes[[/if]]|", {"a": 0}), "|")
                self.assertEqual(render("[[#if   a  ]]yes[[/if]]", {"a": 1}), "yes")
                self.assertEqual(render("a[[#if x]][[/if]]b[[#if x]][[else]][[/if]]c", {"x": 1}), "abc")

            def test_only_the_chosen_part_is_rendered(self):
                t = Template("[[#if a]][[x]][[else]][[y]][[/if]]")
                self.assertEqual(t.render({"a": 1, "x": "X"}), "X")
                self.assertEqual(t.render({"a": 0, "y": "Y"}), "Y")
                with self.assertRaises(MissingValue) as cm:
                    t.render({"a": 1})
                self.assertEqual(cm.exception.name, "x")

            def test_nested_ifs(self):
                t = Template("[[#if a]]A[[#if b]]B[[else]]b[[/if]]C[[else]]a[[#if b]]B[[/if]][[/if]]")
                self.assertEqual(t.render({"a": 1, "b": 1}), "ABC")
                self.assertEqual(t.render({"a": 1, "b": 0}), "AbC")
                self.assertEqual(t.render({"a": 0, "b": 1}), "aB")
                self.assertEqual(t.render({}), "a")

            def test_if_syntax_errors(self):
                for bad in ["[[#if]]x[[/if]]", "[[#if 1a]]x[[/if]]", "[[#if a b]]x[[/if]]", "[[else]]", "[[/if]]", "x[[/if]][[#if a]][[/if]]",
                            "[[#if a]]x", "[[#if a]][[#if b]]x[[/if]]", "[[#if a]]x[[else]]y[[else]]z[[/if]]", "[[#if a]][[else]][[else]][[/if]]",
                            "[[#iff a]]x[[/if]]", "[[ #if a ]] [[ /iff ]]"]:
                    with self.assertRaises(TemplateError, msg=bad):
                        Template(bad)
                self.assertEqual(Template("[[ #if a ]]x[[ else ]]y[[ /if ]]").render({"a": 1}), "x")
        ''',
        cross={
            "paths": {"tests": '''
                def test_if_with_paths(self):
                    t = Template("[[#if customer.vip]]VIP[[else]]std[[/if]]")
                    self.assertEqual(t.render({"customer": {"vip": True}}), "VIP")
                    self.assertEqual(t.render({"customer": {"vip": False}}), "std")
                    self.assertEqual(t.render({"customer": None}), "std")
                    self.assertEqual(t.render({}), "std")
                    self.assertEqual(render("[[#if items.1]]two[[/if]]", {"items": [1]}), "")
            '''},
            "filters": {"tests": '''
                def test_filters_inside_blocks(self):
                    self.assertEqual(render("[[#if a]][[ name | upper ]][[/if]]", {"a": 1, "name": "x"}), "X")
                    with self.assertRaises(TemplateError):
                        Template("[[#if a | upper]]x[[/if]]")
            '''},
            "escape": {"tests": '''
                def test_escaped_block_tags(self):
                    self.assertEqual(render("\\\\[[#if a]]x\\\\[[/if]]", {}), "[[#if a]]x[[/if]]")
            '''},
            "defaults": {"tests": '''
                def test_defaults_inside_blocks(self):
                    self.assertEqual(render('[[#if a]][[ b or "none" ]][[/if]]', {"a": 1}), "none")
                    with self.assertRaises(TemplateError):
                        Template('[[#if a or "x"]]y[[/if]]')
            '''},
        },
    ))

    S.append(Slice(
        id="each", title="Loops", d=4,
        pitch=("Order confirmations list the items and the template has a fixed number of item lines.",
               "Templates need a loop over a list."),
        reqs=("`[[#each name]] ... [[/each]]` renders its body once for every item of the list (or tuple) that `name` refers to and joins the results; an empty list renders nothing. A name that is missing raises `MissingValue` as for any tag; a value that is not a list or tuple is a `TemplateError` raised while rendering.",
              "Inside the body names are looked up first in the current item and then in the surrounding data, innermost first. A dict item provides its keys; any other item is available as `this` (also for nested lists, so `[[#each this]]` loops over an inner list). `[[@index]]` is the 0-based and `[[@number]]` the 1-based position of the item; they can only be used inside a loop (elsewhere they are missing, `MissingValue`), and nothing set by the loop outlives it. Items are never modified. Loops can be nested.",
              "Parse errors, all `TemplateError`: an `#each` without a name or with a bad name, a `[[/each]]` outside of an `#each` block, and an `#each` that is never closed."),
        code={
            "labelmaker/template.py::var_syntax": '''
                if expr in ("@index", "@number"):
                    return ("var", expr, filters, default)
            ''',
            "labelmaker/template.py::block_tags": '''
                if tag == "#each" or tag.startswith("#each "):
                    name = tag[5:].strip()
                    if not _NAME.fullmatch(name):
                        raise TemplateError(f"bad loop: {tag!r}")
                    node = ("each", name, [])
                    current.append(node)
                    stack.append({"kind": "each", "node": node, "parent": current})
                    current = node[2]
                    continue
                if tag == "/each":
                    if not stack or stack[-1]["kind"] != "each":
                        raise TemplateError("unexpected [[/each]]")
                    current = stack.pop()["parent"]
                    continue
            ''',
            "labelmaker/template.py::render_kinds": '''
                elif kind == "each":
                    items = _lookup(scopes, node[1])
                    if not isinstance(items, (list, tuple)):
                        raise TemplateError(f"{node[1]} is not a list")
                    for i, item in enumerate(items):
                        scope = dict(item) if isinstance(item, dict) else {"this": item}
                        scope["@index"] = i
                        scope["@number"] = i + 1
                        out.append(_render(node[2], scopes + [scope]))
            ''',
        },
        readme="## Loops\n\n`[[#each items]]...[[/each]]` renders the body per item (dict keys or `this`, `[[@index]]`, `[[@number]]`); missing lists raise `MissingValue`, non-lists a `TemplateError`.\n",
        vtests='''
            def test_each_basic(self):
                self.assertEqual(render("[[#each xs]][[this]],[[/each]]", {"xs": [1, 2]}), "1,2,")
        ''',
        tests='''
            def test_each(self):
                self.assertEqual(render("[[#each items]][[this]],[[/each]]", {"items": ["a", "b", "c"]}), "a,b,c,")
                people = [{"name": "Ana", "age": 3}, {"name": "Bo", "age": 4}]
                self.assertEqual(render("[[#each people]][[name]]:[[age]];[[/each]]", {"people": people}), "Ana:3;Bo:4;")
                self.assertEqual(render("[[#each items]][[prefix]][[this]] [[/each]]", {"items": ["a", "b"], "prefix": "#"}), "#a #b ")
                self.assertEqual(render("[[#each xs]][[name]][[/each]]", {"xs": [{"name": "inner"}], "name": "outer"}), "inner")
                self.assertEqual(render("[[#each xs]][[name]][[/each]]", {"xs": [{"other": 1}], "name": "outer"}), "outer")
                self.assertEqual(render("[[#each items]][[@number]]. [[this]]\\n[[/each]]", {"items": ["a", "b"]}), "1. a\\n2. b\\n")
                self.assertEqual(render("[[#each items]][[@index]][[/each]]", {"items": ["a", "b", "c"]}), "012")
                self.assertEqual(render("[[#each items]][[this]][[/each]]", {"items": ("x", "y")}), "xy")
                self.assertEqual(render("<[[#each items]]x[[/each]]>", {"items": []}), "<>")
                self.assertEqual(render("[[#each items]][[this]][[/each]]", {"items": [0, None, False]}), "0False")

            def test_each_scopes(self):
                self.assertEqual(render("[[#each rows]][[#each this]][[this]] [[/each]]|[[/each]]", {"rows": [[1, 2], [3]]}), "1 2 |3 |")
                self.assertEqual(render("[[#each a]][[#each b]][[@number]][[/each]]-[[@number]];[[/each]]", {"a": [1, 2], "b": ["x", "y", "z"]}), "123-1;123-2;")
                items = [{"n": 1}]
                render("[[#each items]][[n]][[/each]]", {"items": items})
                self.assertEqual(items, [{"n": 1}])
                with self.assertRaises(MissingValue) as cm:
                    render("[[#each items]][[this]][[/each]][[@index]]", {"items": [1]})
                self.assertEqual(cm.exception.name, "@index")
                with self.assertRaises(MissingValue):
                    render("[[@number]]")

            def test_each_errors(self):
                with self.assertRaises(MissingValue) as cm:
                    render("[[#each things]]x[[/each]]", {})
                self.assertEqual(cm.exception.name, "things")
                for bad in ["text", 5, {"a": 1}, None, {1, 2}]:
                    with self.assertRaises(TemplateError, msg=repr(bad)) as cm:
                        render("[[#each xs]]x[[/each]]", {"xs": bad})
                    self.assertNotIsInstance(cm.exception, MissingValue)
                for bad in ["[[#each]]x[[/each]]", "[[#each 1a]]x[[/each]]", "[[#each a b]]x[[/each]]", "[[/each]]", "[[#each a]]x", "x[[/each]][[#each a]][[/each]]",
                            "[[#eachx a]][[/each]]"]:
                    with self.assertRaises(TemplateError, msg=bad):
                        Template(bad)
        ''',
        cross={
            "if": {
                "reqs": ("`#if` blocks and loops nest freely, but must be closed in the right order: closing a block of the other kind is an error.",),
                "tests": '''
                    def test_if_inside_each(self):
                        people = [{"name": "Ana", "vip": True}, {"name": "Bo"}, {"name": "Cy", "vip": 0}]
                        self.assertEqual(render("[[#each people]][[#if vip]]*[[/if]][[name]] [[/each]]", {"people": people}), "*Ana Bo Cy ")
                        self.assertEqual(render("[[#if people]][[#each people]][[name]][[/each]][[else]]nobody[[/if]]", {"people": people}), "AnaBoCy")
                        self.assertEqual(render("[[#if people]][[#each people]][[name]][[/each]][[else]]nobody[[/if]]", {"people": []}), "nobody")
                        self.assertEqual(render("[[#each xs]][[#if this]][[this]][[else]]-[[/if]][[/each]]", {"xs": ["a", "", "b", None]}), "a-b-")
                        for bad in ["[[#each a]][[#if b]][[/each]][[/if]]", "[[#if a]][[#each b]][[/if]][[/each]]", "[[#each a]][[else]][[/each]]", "[[#if a]][[/each]][[/if]]"]:
                            with self.assertRaises(TemplateError, msg=bad):
                                Template(bad)
                '''},
            "paths": {"tests": '''
                def test_each_with_paths(self):
                    data = {"order": {"id": 7, "lines": [{"sku": "A1", "qty": 2}, {"sku": "B2", "qty": 1}]}}
                    self.assertEqual(render("[[order.id]]: [[#each order.lines]][[sku]]x[[qty]] [[/each]]", data), "7: A1x2 B2x1 ")
                    self.assertEqual(render("[[#each rows]][[this.0]]/[[this.1]] [[/each]]", {"rows": [[1, 2], [3, 4]]}), "1/2 3/4 ")
                    self.assertEqual(render("[[#each order.lines]][[order.id]][[/each]]", data), "77")
                    with self.assertRaises(MissingValue) as cm:
                        render("[[#each order.nothing]]x[[/each]]", data)
                    self.assertEqual(cm.exception.name, "order.nothing")
            '''},
            "filters": {"tests": '''
                def test_filters_inside_loops(self):
                    self.assertEqual(render("[[#each xs]][[ this | upper ]][[ @number | pad:2 ]]|[[/each]]", {"xs": ["a", "b"]}), "A1 |B2 |")
            '''},
            "defaults": {"tests": '''
                def test_defaults_inside_loops(self):
                    people = [{"name": "Ana", "nick": "A"}, {"name": "Bo"}, {"name": "Cy", "nick": ""}]
                    self.assertEqual(render('[[#each people]][[name]]=[[ nick or "-" ]] [[/each]]', {"people": people}), "Ana=A Bo=- Cy=- ")
            '''},
            "escape": {"tests": '''
                def test_escaped_loop_tags(self):
                    self.assertEqual(render("\\\\[[#each xs]][[#each xs]]x[[/each]]", {"xs": [1]}), "[[#each xs]]x")
            '''},
        },
    ))
    order = ["names", "render-many", "escape", "paths", "filters", "defaults", "if", "each"]
    S.sort(key=lambda x: order.index(x.id))
    return S


APP = App(
    name="labelmaker", lang="python", title="the label template library", role="a web shop developer", key="LABEL",
    base={
        "README.md": README + "\n@@blocks features\n",
        "labelmaker/__init__.py": INIT,
        "labelmaker/template.py": TEMPLATE,
        ".gitignore": "__pycache__/\n*.pyc\n",
    },
    visible={"tests/test_basic.py": VISIBLE},
    hidden={"tests/test_features.py": HIDDEN},
)

register_app("feature-py-labelmaker", APP, make_slices, n=18, summary="label templates: names, batches, escapes, dotted paths, fallbacks, filters, conditionals, loops")
