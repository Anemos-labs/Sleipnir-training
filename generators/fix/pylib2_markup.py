"""Text-format libraries (python), batch: template language, lightweight markup, version ranges."""
from fx import Lib, dd, register_libs

# ======================================================================================================================
# tmplbrace: a small template language ({{ var | filter }}, #each, #if)
# ======================================================================================================================

BRACE_README = dd(r'''
    # tmplbrace

    The template language of the release-notes generator. `render(template, context, strict=False) -> str`.
    A template error raises `TemplateError` (a `ValueError`) before anything is rendered.

    ## Tags
    Everything between `{{` and `}}` is a tag; all other text is copied. A backslash directly before `{{` removes
    itself and makes the tag literal text: `\{{ x }}` renders as `{{ x }}`.

    * `{{ path | filter arg ... | filter ... }}` output a value (see below).
    * `{{!anything}}` a comment, renders nothing.
    * `{{#each path}} ... {{/each}}` repeats the body for every item.
    * `{{#if path}} ... {{#else}} ... {{/if}}` the `{{#else}}` part is optional; `{{#if not path}}` inverts the test.
      Python truthiness decides, except that a missing path is false.
    * Block tags must nest properly; a closing tag that does not match, a `{{#else}}` outside an `if` (or a second one
      in the same `if`), or a block left open at the end is a `TemplateError`. Unknown tags such as `{{#foo x}}` too.

    ### Whitespace control
    A tag written `{{- ... }}` removes all whitespace (including newlines) directly before it; `{{ ... -}}` removes all
    whitespace directly after it. This applies to every kind of tag, and to both sides independently.

    ## Paths and scopes
    A path is names separated by dots: `user.name`. A name selects a dict key, or a list item when the name is a
    decimal index (`items.0`). A missing step makes the whole path *missing*. `.` is the current item and `@name`
    is loop information, see below.

    The first name of a path is looked up in the scopes from the innermost loop outwards: inside `#each`, the keys of
    the current item (if it is a dict) shadow the outer context. The context given to `render` is the outermost scope.

    ### `#each`
    Iterates over a list or tuple; over a dict it iterates over its entries sorted by key, each item being the dict
    `{"key": k, "value": v}`; a missing path, `None` or anything else renders nothing. Inside the body:
    `.` is the item, `@index` the 0-based and `@number` the 1-based position, `@first` and `@last` booleans, `@count`
    the number of items. `@` names refer to the innermost loop only and are missing outside of loops.

    ## Output and filters
    Values are written as: `None` nothing; `True`/`False` as `true`/`false`; lists and tuples as their items written
    this way and joined with `", "`; everything else with `str()`. A missing path writes nothing, or with
    `strict=True` raises `KeyError(path)` unless a `default` filter is present in that tag.

    Filters apply left to right (filter name, then its arguments separated by blanks; arguments are non-negative
    integers or double-quoted strings without escapes). The value flowing through is the raw value, converted to text only
    by the filters that need it. An unknown filter, a wrong number of arguments or a bad argument is a `TemplateError`.

    | filter | meaning |
    |---|---|
    | `default X` | `X` if the value is missing, `None` or `""`, else the value unchanged (`0` and `False` are kept) |
    | `upper`, `lower`, `trim` | on the text of the value |
    | `join "sep"` | join the items of a list/tuple (each written as above) with `sep`; other values are just written |
    | `pad N` / `lpad N` | pad the text with spaces to width `N` on the right / left (never shortens) |
    | `trunc N` | if the text is longer than `N`: its first `N-3` characters plus `...` (just the first `N` characters when `N < 3`) |
    | `count` | `len` of a list, tuple, dict or string; `0` for anything else |
''')

BRACE_SRC = dd(r'''
    """A small template language."""
    import re


    class TemplateError(ValueError):
        pass


    _TAG = re.compile(r"\{\{(-?)(.*?)(-?)\}\}", re.S)


    def _tokenize(src):
        toks = []
        pos = 0
        strip_next = False
        pending = []

        def flush():
            text = "".join(pending)
            del pending[:]
            if text:
                toks.append(("text", text))

        for m in _TAG.finditer(src):
            text = src[pos:m.start()]
            pos = m.end()
            if strip_next:
                text = text.lstrip()
                strip_next = False
            if text.endswith("\\"):
                pending.append(text[:-1] + m.group(0))
                continue
            if m.group(1) == "-":
                text = text.rstrip()
            pending.append(text)
            flush()
            toks.append(("tag", m.group(2).strip()))
            strip_next = m.group(3) == "-"
        tail = src[pos:]
        if strip_next:
            tail = tail.lstrip()
        pending.append(tail)
        flush()
        return toks


    def _split_outside_quotes(s, sep=None):
        parts, buf = [], []
        quoted = False
        for c in s:
            if c == '"':
                quoted = not quoted
                buf.append(c)
            elif not quoted and ((c == sep) if sep else c.isspace()):
                parts.append("".join(buf))
                buf = []
            else:
                buf.append(c)
        if quoted:
            raise TemplateError("unterminated string")
        parts.append("".join(buf))
        return parts


    _ARITY = {"default": 1, "upper": 0, "lower": 0, "trim": 0, "join": 1, "pad": 1, "lpad": 1, "trunc": 1, "count": 0}
    _INT_ARGS = {"pad", "lpad", "trunc"}


    def _parse_expr(text):
        pieces = _split_outside_quotes(text, "|")
        path = pieces[0].strip()
        if not path or " " in path:
            raise TemplateError("bad path: %r" % path)
        filters = []
        for piece in pieces[1:]:
            words = [w for w in _split_outside_quotes(piece.strip()) if w != ""]
            if not words:
                raise TemplateError("empty filter")
            name, raw = words[0], words[1:]
            if name not in _ARITY:
                raise TemplateError("unknown filter: %s" % name)
            if len(raw) != _ARITY[name]:
                raise TemplateError("filter %s takes %d argument(s)" % (name, _ARITY[name]))
            args = []
            for w in raw:
                if w.startswith('"') and w.endswith('"') and len(w) >= 2:
                    arg = w[1:-1]
                    if name in _INT_ARGS:
                        raise TemplateError("filter %s needs a number" % name)
                elif w.isdigit():
                    arg = int(w)
                    if name not in _INT_ARGS and name != "default":
                        raise TemplateError("filter %s needs a string" % name)
                else:
                    raise TemplateError("bad argument: %s" % w)
                args.append(arg)
            filters.append((name, args))
        return path, filters


    def _parse(toks):
        root = []
        body = root
        stack = []
        for kind, val in toks:
            if kind == "text":
                body.append(("text", val))
                continue
            if val.startswith("!"):
                continue
            if val.startswith("#each ") or val.startswith("#if "):
                if val.startswith("#each "):
                    node = ["each", val[6:].strip(), []]
                    inner = node[2]
                else:
                    arg = val[4:].strip()
                    neg = False
                    if arg.startswith("not "):
                        neg, arg = True, arg[4:].strip()
                    node = ["if", neg, arg, [], None]
                    inner = node[3]
                body.append(node)
                stack.append((node, body))
                body = inner
            elif val == "#else":
                if not stack or stack[-1][0][0] != "if" or stack[-1][0][4] is not None:
                    raise TemplateError("unexpected #else")
                stack[-1][0][4] = []
                body = stack[-1][0][4]
            elif val in ("/each", "/if"):
                if not stack or stack[-1][0][0] != val[1:]:
                    raise TemplateError("unexpected %s" % val)
                body = stack.pop()[1]
            elif val.startswith("#") or val.startswith("/"):
                raise TemplateError("unknown tag: %s" % val)
            else:
                path, filters = _parse_expr(val)
                body.append(("var", path, filters))
        if stack:
            raise TemplateError("unclosed block: %s" % stack[-1][0][0])
        return root


    def _text(v):
        if v is None:
            return ""
        if v is True:
            return "true"
        if v is False:
            return "false"
        if isinstance(v, (list, tuple)):
            return ", ".join(_text(x) for x in v)
        return str(v)


    _FILTERS = {
        "default": lambda v, d: d if v is None or v == "" else v,
        "upper": lambda v: _text(v).upper(),
        "lower": lambda v: _text(v).lower(),
        "trim": lambda v: _text(v).strip(),
        "join": lambda v, sep: sep.join(_text(x) for x in v) if isinstance(v, (list, tuple)) else _text(v),
        "pad": lambda v, n: _text(v).ljust(n),
        "lpad": lambda v, n: _text(v).rjust(n),
        "trunc": lambda v, n: _text(v) if len(_text(v)) <= n else (_text(v)[:n - 3] + "..." if n >= 3 else _text(v)[:n]),
        "count": lambda v: len(v) if isinstance(v, (list, tuple, dict, str)) else 0,
    }


    def _walk(value, names):
        for name in names:
            if isinstance(value, dict) and name in value:
                value = value[name]
            elif isinstance(value, (list, tuple)) and name.isdigit() and int(name) < len(value):
                value = value[int(name)]
            else:
                return False, None
        return True, value


    def _resolve(path, scopes):
        if path == ".":
            return True, scopes[-1]["item"]
        if path.startswith("@"):
            meta = scopes[-1]["meta"]
            if meta is not None and path in meta:
                return True, meta[path]
            return False, None
        names = path.split(".")
        for scope in reversed(scopes):
            if names[0] in scope["dict"]:
                return _walk(scope["dict"][names[0]], names[1:])
        return False, None


    def _render(nodes, scopes, strict, out):
        for node in nodes:
            kind = node[0]
            if kind == "text":
                out.append(node[1])
            elif kind == "var":
                found, value = _resolve(node[1], scopes)
                if not found:
                    value = None
                    if strict and not any(name == "default" for name, _ in node[2]):
                        raise KeyError(node[1])
                for name, args in node[2]:
                    value = _FILTERS[name](value, *args)
                out.append(_text(value))
            elif kind == "if":
                found, value = _resolve(node[2], scopes)
                truth = bool(found and value)
                if truth != node[1]:
                    _render(node[3], scopes, strict, out)
                elif node[4] is not None:
                    _render(node[4], scopes, strict, out)
            else:
                found, value = _resolve(node[1], scopes)
                if isinstance(value, dict):
                    items = [{"key": k, "value": value[k]} for k in sorted(value)]
                elif isinstance(value, (list, tuple)):
                    items = list(value)
                else:
                    items = []
                for i, item in enumerate(items):
                    meta = {"@index": i, "@number": i + 1, "@first": i == 0, "@last": i == len(items) - 1, "@count": len(items)}
                    scope = {"item": item, "dict": item if isinstance(item, dict) else {}, "meta": meta}
                    _render(node[2], scopes + [scope], strict, out)


    def render(template, context, strict=False):
        nodes = _parse(_tokenize(template))
        out = []
        root = context if isinstance(context, dict) else {}
        _render(nodes, [{"item": context, "dict": root, "meta": None}], strict, out)
        return "".join(out)
''')

BRACE_VISIBLE = dd(r'''
    import unittest

    from tmplbrace import TemplateError, render


    class BasicTests(unittest.TestCase):
        def test_variable(self):
            self.assertEqual(render("Hello {{ user.name }}!", {"user": {"name": "Ada"}}), "Hello Ada!")

        def test_each(self):
            self.assertEqual(render("{{#each xs}}[{{.}}]{{/each}}", {"xs": [1, 2]}), "[1][2]")

        def test_if_else(self):
            self.assertEqual(render("{{#if a}}Y{{#else}}N{{/if}}", {"a": 0}), "N")

        def test_error(self):
            with self.assertRaises(TemplateError):
                render("{{#each xs}}", {})


    if __name__ == "__main__":
        unittest.main()
''')

BRACE_HIDDEN = dd(r'''
    import unittest

    from tmplbrace import TemplateError, render


    class Variables(unittest.TestCase):
        def test_plain_and_paths(self):
            ctx = {"a": "x", "u": {"n": "Ada", "tags": ["p", "q"], "deep": {"k": 1}}}
            self.assertEqual(render("{{a}}|{{ a }}|{{   a   }}", ctx), "x|x|x")
            self.assertEqual(render("{{ u.n }} {{ u.deep.k }} {{ u.tags.1 }} {{ u.tags.0 }}", ctx), "Ada 1 q p")

        def test_missing_is_empty(self):
            self.assertEqual(render("[{{ nope }}][{{ u.nope }}][{{ u.tags.5 }}][{{ a.b }}]", {"u": {"tags": [1]}, "a": "s"}), "[][][][]")

        def test_value_writing(self):
            ctx = {"n": None, "t": True, "f": False, "z": 0, "fl": 2.5, "l": [1, "a", None, True, [2, 3]], "e": ""}
            self.assertEqual(render("{{n}}|{{t}}|{{f}}|{{z}}|{{fl}}|{{l}}|{{e}}|", ctx), "|true|false|0|2.5|1, a, , true, 2, 3||")

        def test_text_untouched(self):
            self.assertEqual(render("a { b } {c} {{x}} }}{ {", {"x": 1}), "a { b } {c} 1 }}{ {")
            self.assertEqual(render("", {}), "")
            self.assertEqual(render("plain\n  text\n", {}), "plain\n  text\n")

        def test_comments(self):
            self.assertEqual(render("a{{! hidden }}b{{!}}c", {}), "abc")

        def test_escaped_tags(self):
            self.assertEqual(render(r"\{{ x }} {{ x }}", {"x": 1}), "{{ x }} 1")
            self.assertEqual(render(r"a\{{#each x}}b", {}), "a{{#each x}}b")
            self.assertEqual(render("c:\\\\ {{ x }}", {"x": 1}), "c:\\\\ 1")

        def test_strict(self):
            with self.assertRaises(KeyError) as cm:
                render("{{ nope }}", {}, strict=True)
            self.assertEqual(cm.exception.args, ("nope",))
            with self.assertRaises(KeyError) as cm:
                render("{{ a.b | upper }}", {}, strict=True)
            self.assertEqual(cm.exception.args, ("a.b",))
            with self.assertRaises(KeyError):
                render("{{ a.b }}", {"a": {}}, strict=True)
            self.assertEqual(render("{{ nope | default \"d\" }}", {}, strict=True), "d")
            self.assertEqual(render("{{ a }}{{ b }}", {"a": None, "b": ""}, strict=True), "")
            self.assertEqual(render("{{#if nope}}x{{/if}}{{#each nope}}x{{/each}}", {}, strict=True), "")


    class Filters(unittest.TestCase):
        def test_default(self):
            ctx = {"e": "", "n": None, "z": 0, "f": False, "v": "val"}
            self.assertEqual(render('{{ e | default "d" }}|{{ n | default "d" }}|{{ m | default "d" }}|{{ z | default "d" }}|{{ f | default "d" }}|{{ v | default "d" }}', ctx),
                             "d|d|d|0|false|val")
            self.assertEqual(render("{{ m | default 7 }}", {}), "7")

        def test_case_and_trim(self):
            self.assertEqual(render("{{ a | upper }}{{ a | lower }}{{ b | trim }}|", {"a": "aB", "b": "  x y  "}), "ABabx y|")
            self.assertEqual(render("{{ t | upper }}", {"t": True}), "TRUE")
            self.assertEqual(render("{{ m | upper }}|", {}), "|")

        def test_join(self):
            self.assertEqual(render('{{ l | join "-" }}', {"l": [1, "b", None, False]}), "1-b--false")
            self.assertEqual(render('{{ s | join "-" }}', {"s": "abc"}), "abc")
            self.assertEqual(render('{{ l | join ", " }}', {"l": ("x", "y")}), "x, y")
            self.assertEqual(render('{{ l | join "|" }}', {"l": ["a", "b"]}), "a|b")
            self.assertEqual(render('{{ l | join "" }}', {"l": ["a", "b"]}), "ab")

        def test_pad(self):
            self.assertEqual(render("[{{ a | pad 5 }}][{{ a | lpad 5 }}][{{ a | pad 2 }}][{{ a | lpad 0 }}]", {"a": "abc"}), "[abc  ][  abc][abc][abc]")
            self.assertEqual(render("[{{ n | pad 4 }}]", {"n": 7}), "[7   ]")

        def test_trunc(self):
            self.assertEqual(render("{{ a | trunc 10 }}", {"a": "abcdefghij"}), "abcdefghij")
            self.assertEqual(render("{{ a | trunc 9 }}", {"a": "abcdefghij"}), "abcdef...")
            self.assertEqual(render("{{ a | trunc 3 }}", {"a": "abcdefghij"}), "...")
            self.assertEqual(render("{{ a | trunc 2 }}", {"a": "abcdefghij"}), "ab")
            self.assertEqual(render("{{ a | trunc 0 }}", {"a": "abc"}), "")
            self.assertEqual(render("{{ a | trunc 5 }}", {"a": "abc"}), "abc")

        def test_count(self):
            ctx = {"l": [1, 2, 3], "d": {"a": 1}, "s": "four", "n": 5, "t": (1,)}
            self.assertEqual(render("{{ l | count }} {{ d | count }} {{ s | count }} {{ n | count }} {{ m | count }} {{ t | count }}", ctx), "3 1 4 0 0 1")

        def test_chains(self):
            self.assertEqual(render('{{ a | trim | upper | pad 6 }}|', {"a": " ab "}), "AB    |")
            self.assertEqual(render('{{ m | default "none" | upper }}', {}), "NONE")
            self.assertEqual(render('{{ l | join "," | trunc 5 }}', {"l": ["aaa", "bbb"]}), "aa...")

        def test_pipe_inside_quotes(self):
            self.assertEqual(render('{{ l | join " | " }}', {"l": [1, 2]}), "1 | 2")
            self.assertEqual(render('{{ m | default "a|b" }}', {}), "a|b")

        def test_bad_filters(self):
            for tpl in ("{{ a | nope }}", "{{ a | pad }}", "{{ a | upper 3 }}", '{{ a | pad "x" }}', "{{ a | join 3 }}", "{{ a | pad x }}",
                        "{{ a | }}", "{{ | upper }}", '{{ a | default "x }}', "{{ a | pad 1 2 }}", "{{ a b }}", "{{ }}"):
                with self.assertRaises(TemplateError, msg=tpl):
                    render(tpl, {"a": 1})


    class Conditionals(unittest.TestCase):
        def test_truthiness(self):
            for val, want in ((1, "Y"), (0, "N"), ("", "N"), ("x", "Y"), ([], "N"), ([0], "Y"), ({}, "N"), (None, "N"), (False, "N"), (True, "Y")):
                self.assertEqual(render("{{#if v}}Y{{#else}}N{{/if}}", {"v": val}), want, repr(val))
            self.assertEqual(render("{{#if v}}Y{{#else}}N{{/if}}", {}), "N")

        def test_not(self):
            self.assertEqual(render("{{#if not v}}Y{{#else}}N{{/if}}", {"v": 0}), "Y")
            self.assertEqual(render("{{#if not v}}Y{{#else}}N{{/if}}", {"v": 1}), "N")
            self.assertEqual(render("{{#if not v}}Y{{#else}}N{{/if}}", {}), "Y")
            self.assertEqual(render("{{#if not v}}Y{{/if}}", {"v": 1}), "")

        def test_without_else(self):
            self.assertEqual(render("a{{#if v}}b{{/if}}c", {"v": 1}), "abc")
            self.assertEqual(render("a{{#if v}}b{{/if}}c", {"v": 0}), "ac")

        def test_paths_in_condition(self):
            self.assertEqual(render("{{#if u.admin}}A{{/if}}{{#if u.tags.0}}T{{/if}}", {"u": {"admin": True, "tags": ["x"]}}), "AT")

        def test_nested_ifs(self):
            tpl = "{{#if a}}1{{#if b}}2{{#else}}3{{/if}}4{{#else}}5{{#if b}}6{{/if}}{{/if}}"
            self.assertEqual(render(tpl, {"a": 1, "b": 1}), "124")
            self.assertEqual(render(tpl, {"a": 1, "b": 0}), "134")
            self.assertEqual(render(tpl, {"a": 0, "b": 1}), "56")
            self.assertEqual(render(tpl, {"a": 0, "b": 0}), "5")


    class Loops(unittest.TestCase):
        def test_items(self):
            self.assertEqual(render("{{#each xs}}<{{.}}>{{/each}}", {"xs": ["a", "b", "c"]}), "<a><b><c>")
            self.assertEqual(render("{{#each xs}}<{{.}}>{{/each}}", {"xs": ("a",)}), "<a>")

        def test_empty_and_non_iterables(self):
            for val in ([], None, 5, "abc", True):
                self.assertEqual(render("[{{#each xs}}x{{/each}}]", {"xs": val}), "[]", repr(val))
            self.assertEqual(render("[{{#each xs}}x{{/each}}]", {}), "[]")

        def test_meta(self):
            tpl = "{{#each xs}}{{@index}}/{{@number}}/{{@count}}/{{@first}}/{{@last}};{{/each}}"
            self.assertEqual(render(tpl, {"xs": ["a", "b", "c"]}), "0/1/3/true/false;1/2/3/false/false;2/3/3/false/true;")
            self.assertEqual(render(tpl, {"xs": ["a"]}), "0/1/1/true/true;")

        def test_meta_outside_loop_is_missing(self):
            self.assertEqual(render("[{{@index}}]", {"@index": 5}), "[]")
            with self.assertRaises(KeyError):
                render("{{@index}}", {}, strict=True)

        def test_dict_items_are_fields(self):
            ctx = {"people": [{"name": "Ada", "age": 36}, {"name": "Bob"}]}
            self.assertEqual(render("{{#each people}}{{name}}:{{age | default \"?\"}};{{/each}}", ctx), "Ada:36;Bob:?;")

        def test_outer_scope_visible_and_shadowed(self):
            ctx = {"title": "T", "name": "outer", "people": [{"name": "Ada"}, {}]}
            self.assertEqual(render("{{#each people}}{{title}}-{{name}};{{/each}}", ctx), "T-Ada;T-outer;")

        def test_nested_loops_and_meta_innermost(self):
            ctx = {"rows": [[1, 2], [3]]}
            tpl = "{{#each rows}}r{{@index}}:{{#each .}}{{.}}@{{@index}} {{/each}}|{{/each}}"
            self.assertEqual(render(tpl, ctx), "r0:1@0 2@1 |r1:3@0 |")

        def test_dot_is_context_outside_loops(self):
            self.assertEqual(render("{{#each .}}{{.}}{{/each}}", [1, 2]), "12")
            self.assertEqual(render("{{ . }}", "hi"), "hi")

        def test_dict_iteration_sorted(self):
            ctx = {"m": {"b": 2, "a": 1, "c": 3}}
            self.assertEqual(render("{{#each m}}{{key}}={{value}},{{/each}}", ctx), "a=1,b=2,c=3,")
            self.assertEqual(render("{{#each m}}{{@index}}{{@last}} {{/each}}", ctx), "0false 1false 2true ")

        def test_if_inside_loop_sees_item(self):
            ctx = {"xs": [{"on": True, "v": "a"}, {"on": False, "v": "b"}, {"on": True, "v": "c"}]}
            self.assertEqual(render("{{#each xs}}{{#if on}}{{v}}{{#else}}-{{/if}}{{/each}}", ctx), "a-c")
            self.assertEqual(render("{{#each xs}}{{v}}{{#if not @last}},{{/if}}{{/each}}", ctx), "a,b,c")

        def test_path_through_loop_item(self):
            ctx = {"xs": [{"p": {"q": "deep"}}]}
            self.assertEqual(render("{{#each xs}}{{p.q}}{{/each}}", ctx), "deep")

        def test_context_not_modified(self):
            ctx = {"xs": [1, 2], "m": {"a": 1}}
            render("{{#each xs}}{{.}}{{/each}}{{#each m}}{{key}}{{/each}}", ctx)
            self.assertEqual(ctx, {"xs": [1, 2], "m": {"a": 1}})


    class Whitespace(unittest.TestCase):
        def test_left(self):
            self.assertEqual(render("a  \n  {{- x }}", {"x": "X"}), "aX")

        def test_right(self):
            self.assertEqual(render("{{ x -}}  \n  b", {"x": "X"}), "Xb")

        def test_both(self):
            self.assertEqual(render("a \n{{- x -}}\n b", {"x": "X"}), "aXb")

        def test_only_adjacent_whitespace(self):
            self.assertEqual(render("a b {{- x }} c", {"x": "X"}), "a bX c")
            self.assertEqual(render("a {{ x -}} b c", {"x": "X"}), "a Xb c")

        def test_block_tags(self):
            tpl = "<ul>\n  {{#each xs -}}\n  <li>{{.}}</li>\n  {{- /each -}}\n</ul>"
            self.assertEqual(render(tpl, {"xs": [1, 2]}), "<ul>\n  <li>1</li><li>2</li></ul>")

        def test_if_tags(self):
            self.assertEqual(render("a\n{{- #if v -}}\n b\n{{- #else -}}\n c\n{{- /if -}}\n d", {"v": 1}), "abd")
            self.assertEqual(render("a {{- #if v -}} b {{- #else -}} c {{- /if -}} d", {"v": 0}), "acd")

        def test_comment_tags_strip(self):
            self.assertEqual(render("a  {{-! note -}}  b", {}), "ab")

        def test_adjacent_tags(self):
            self.assertEqual(render("{{ a -}} {{- b }}", {"a": 1, "b": 2}), "12")
            self.assertEqual(render("{{ a -}}\n{{ b }}", {"a": 1, "b": 2}), "12")
            self.assertEqual(render("{{ a }}\n{{ b }}", {"a": 1, "b": 2}), "1\n2")

        def test_all_whitespace_text(self):
            self.assertEqual(render("{{ a -}}   \n  ", {"a": 1}), "1")
            self.assertEqual(render("  \n {{- a }}", {"a": 1}), "1")

        def test_dash_on_escaped_tag_text(self):
            self.assertEqual(render("a \\{{- x -}} b", {}), "a {{- x -}} b")


    class Structure(unittest.TestCase):
        def test_errors(self):
            for tpl in ("{{#each xs}}", "{{/each}}", "{{#if a}}", "{{#if a}}{{/each}}", "{{#each a}}{{/if}}", "{{#else}}",
                        "{{#each a}}{{#else}}{{/each}}", "{{#if a}}{{#else}}{{#else}}{{/if}}", "{{#foo x}}", "{{/foo}}",
                        "{{#if a}}{{#each b}}{{/if}}{{/each}}"):
                with self.assertRaises(TemplateError, msg=tpl):
                    render(tpl, {})

        def test_error_is_value_error(self):
            self.assertTrue(issubclass(TemplateError, ValueError))

        def test_errors_raised_even_if_branch_not_taken(self):
            with self.assertRaises(TemplateError):
                render("{{#if a}}{{ x | nope }}{{/if}}", {"a": 0})

        def test_realistic_document(self):
            tpl = (
                "# {{ project | upper }} {{ version }}\n"
                "{{#each sections -}}\n"
                "## {{ title }}\n"
                "{{#each items -}}\n"
                "{{ @number | lpad 2 }}. {{ text | trunc 12 }}{{#if breaking}} (!){{/if}}\n"
                "{{/each -}}\n"
                "{{/each}}"
            )
            ctx = {
                "project": "lantern", "version": "1.2",
                "sections": [
                    {"title": "Fixes", "items": [{"text": "short"}, {"text": "a much longer entry", "breaking": True}]},
                    {"title": "Docs", "items": []},
                ],
            }
            want = "# LANTERN 1.2\n## Fixes\n 1. short\n 2. a much lo... (!)\n## Docs\n"
            self.assertEqual(render(tpl, ctx), want)


    if __name__ == "__main__":
        unittest.main()
''')

BRACE = Lib(
    name="tmplbrace", lang="python", title="the template renderer (`tmplbrace.py`)",
    blurb="The release-notes generator renders its output through this small template language.",
    files={"tmplbrace.py": BRACE_SRC, "README.md": BRACE_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": BRACE_VISIBLE},
    hidden_tests={"tests/test_full.py": BRACE_HIDDEN},
    mutate=["tmplbrace.py"], difficulty=4, tags=["templates", "parsing"],
    probes=[
        'render("a  \\n  {{- x -}}  \\n  b", {"x": "X"})',
        'render("{{ m | default \\"d\\" }}|{{ z | default \\"d\\" }}", {"z": 0})',
        'render("{{ a | trunc 9 }}|{{ a | trunc 2 }}", {"a": "abcdefghij"})',
        'render("{{#each xs}}{{@number}}/{{@count}}{{#if @last}}.{{/if}} {{/each}}", {"xs": [7, 8, 9]})',
        'render("{{#if not v}}empty{{#else}}full{{/if}}", {"v": []})',
        'render("{{#each people}}{{title}}-{{name}};{{/each}}", {"title": "T", "name": "o", "people": [{"name": "Ada"}, {}]})',
        'render("{{ l | join \\" | \\" }} {{ l | count }}", {"l": [1, None, True]})',
        'render("{{#each m}}{{key}}={{value}},{{/each}}", {"m": {"b": 2, "a": 1}})',
        'render("\\\\{{ x }} {{ x }}", {"x": 1})',
    ],
    probe_import="from tmplbrace import *",
)


# ======================================================================================================================
# inkmark: "ink", a lightweight markup of its own, rendered to HTML
# ======================================================================================================================

INK_README = dd(r'''
    # inkmark

    Renderer for *ink*, the markup the help-centre authors write. `render(source, base_url=None) -> str` returns
    HTML: one line per block, blocks separated by a single `\n`, no trailing newline. `\r\n` in the source counts
    as `\n`. Text is HTML-escaped (`&`, `<`, `>`; also `"` inside attribute values).

    ## Blocks
    A block ends at a blank line (whitespace only) or when the next line starts a different kind of block.

    | source | output |
    |---|---|
    | `= text` to `==== text` (1 to 4 `=`, then one or more spaces, then text) | `<h1>` .. `<h4>` with the inline-rendered, stripped text. Five or more `=` is not a heading. |
    | a line of four or more `-` (trailing blanks allowed) | `<hr>` |
    | `{{{` alone on a line (blanks around allowed) up to a line that is `}}}` alone | `<pre><code>` + the lines between, **unchanged** (not stripped) apart from escaping, joined by `\n` + `</code></pre>`. Without a closing line the block runs to the end of the source. Inline rules do not apply. |
    | consecutive lines starting with `> ` (or being just `>`) | `<blockquote>` + the lines (marker removed, stripped) joined by one space, inline-rendered + `</blockquote>` |
    | consecutive lines starting with `- ` | `<ul>` of `<li>` items; `+ ` lines give `<ol>`. A line that starts with two spaces continues the previous item (stripped, joined by one space). A line of the other list kind starts a new list. |
    | anything else | `<p>` + the lines (each stripped) joined by one space, inline-rendered + `</p>` |

    The text of a list item is what follows the marker (stripped), inline-rendered. A marker needs the space after
    it: `-x` is paragraph text.

    ## Inline
    * `*text*` is `<strong>`, `~text~` is `<em>`, `=text=` is `<code>`.
      A delimiter opens a span when it is at the start of the text or right after whitespace or one of `( [ { " '`, and the next
      character exists and is not whitespace. The span ends at the first later delimiter of the same kind that is at least two
      characters after the opener, is not preceded by whitespace or by a backslash, and is followed by the end of the text,
      whitespace or one of `. , ; : ! ? ) ] } " '`. Without such a closer the delimiter is literal text (`a*b*c` and `x = y = z` have no
      spans). The inside of `*` and `~` spans is rendered recursively; the inside of `=` is code: literal, only escaped.
    * `<<url|label>>` is `<a href="url">label</a>`; `<<url>>` uses the url as label. Both parts are stripped; the label is
      plain text (escaped, no spans) and a blank label falls back to the url; an empty url (or no closing `>>`) leaves the
      text as it is. When `base_url` is given and the url is relative, `base_url` without trailing `/`, a `/`, and the url
      are used as href. Relative means: it does not start with `/` or `#` and contains neither `:` nor `//`.
    * A backslash followed by one of `* ~ = < \` outputs that character literally. Any other backslash is literal.
''')

INK_SRC = dd(r'''
    """Renderer for the ink markup."""
    import re

    _OPEN_BEFORE = set(" \t([{\"'")
    _CLOSE_AFTER = set(" \t.,;:!?)]}\"'")
    _TAGS = {"*": "strong", "~": "em", "=": "code"}
    _ESCAPABLE = "*~=<\\"


    def esc(text, attr=False):
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return text.replace('"', "&quot;") if attr else text


    def _find_close(text, i):
        c = text[i]
        for j in range(i + 2, len(text)):
            if text[j] != c or text[j - 1].isspace() or text[j - 1] == "\\":
                continue
            if j + 1 == len(text) or text[j + 1] in _CLOSE_AFTER:
                return j
        return -1


    def _href(url, base_url):
        if base_url and not url.startswith(("/", "#")) and ":" not in url and "//" not in url:
            return base_url.rstrip("/") + "/" + url
        return url


    def inline(text, base_url=None):
        out = []
        i = 0
        while i < len(text):
            c = text[i]
            if c == "\\" and i + 1 < len(text) and text[i + 1] in _ESCAPABLE:
                out.append(esc(text[i + 1]))
                i += 2
                continue
            if c == "<" and text.startswith("<<", i):
                end = text.find(">>", i + 2)
                if end > 0:
                    url, bar, label = text[i + 2:end].partition("|")
                    url, label = url.strip(), label.strip()
                    if url:
                        out.append('<a href="%s">%s</a>' % (esc(_href(url, base_url), True), esc(label or url)))
                        i = end + 2
                        continue
            if c in _TAGS and (i == 0 or text[i - 1] in _OPEN_BEFORE) and i + 1 < len(text) and not text[i + 1].isspace():
                j = _find_close(text, i)
                if j > 0:
                    inner = text[i + 1:j]
                    body = esc(inner) if c == "=" else inline(inner, base_url)
                    out.append("<%s>%s</%s>" % (_TAGS[c], body, _TAGS[c]))
                    i = j + 1
                    continue
            out.append(esc(c))
            i += 1
        return "".join(out)


    def _kind(line):
        if re.fullmatch(r"={1,4} +\S.*", line.rstrip()):
            return "heading"
        if re.fullmatch(r"-{4,}\s*", line):
            return "rule"
        if line.strip() == "{{{":
            return "fence"
        if line.startswith("> ") or line.rstrip() == ">":
            return "quote"
        if line.startswith("- "):
            return "ul"
        if line.startswith("+ "):
            return "ol"
        return "text"


    def render(source, base_url=None):
        lines = source.replace("\r\n", "\n").split("\n")
        out = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            kind = _kind(line)
            if kind == "heading":
                m = re.fullmatch(r"(={1,4}) +(.*\S)\s*", line)
                n = len(m.group(1))
                out.append("<h%d>%s</h%d>" % (n, inline(m.group(2), base_url), n))
                i += 1
            elif kind == "rule":
                out.append("<hr>")
                i += 1
            elif kind == "fence":
                j = i + 1
                body = []
                while j < len(lines) and lines[j].strip() != "}}}":
                    body.append(lines[j])
                    j += 1
                out.append("<pre><code>%s</code></pre>" % esc("\n".join(body)))
                i = j + 1
            elif kind == "quote":
                parts = []
                while i < len(lines) and _kind(lines[i]) == "quote":
                    parts.append(lines[i][1:].strip())
                    i += 1
                out.append("<blockquote>%s</blockquote>" % inline(" ".join(p for p in parts if p), base_url))
            elif kind in ("ul", "ol"):
                items = []
                while i < len(lines):
                    k = _kind(lines[i])
                    if k == kind:
                        items.append([lines[i][2:].strip()])
                    elif lines[i].startswith("  ") and lines[i].strip() and items:
                        items[-1].append(lines[i].strip())
                    else:
                        break
                    i += 1
                lis = "".join("<li>%s</li>" % inline(" ".join(p), base_url) for p in items)
                out.append("<%s>%s</%s>" % (kind, lis, kind))
            else:
                parts = []
                while i < len(lines) and lines[i].strip() and (not parts or _kind(lines[i]) == "text"):
                    parts.append(lines[i].strip())
                    i += 1
                out.append("<p>%s</p>" % inline(" ".join(parts), base_url))
        return "\n".join(out)
''')

INK_VISIBLE = dd(r'''
    import unittest

    from inkmark import render


    class BasicTests(unittest.TestCase):
        def test_heading_and_paragraph(self):
            self.assertEqual(render("== Intro\n\nHello *world*"), "<h2>Intro</h2>\n<p>Hello <strong>world</strong></p>")

        def test_list(self):
            self.assertEqual(render("- a\n- b"), "<ul><li>a</li><li>b</li></ul>")

        def test_escape(self):
            self.assertEqual(render("1 < 2 & 3"), "<p>1 &lt; 2 &amp; 3</p>")


    if __name__ == "__main__":
        unittest.main()
''')

INK_HIDDEN = dd(r'''
    import unittest

    from inkmark import render


    class Headings(unittest.TestCase):
        def test_levels(self):
            for n in (1, 2, 3, 4):
                self.assertEqual(render("=" * n + " Title"), "<h%d>Title</h%d>" % (n, n))

        def test_five_is_text(self):
            self.assertTrue(render("===== Title").startswith("<p>"))
            self.assertTrue(render("====== Title").startswith("<p>"))

        def test_needs_space_and_text(self):
            self.assertEqual(render("==Title"), "<p>==Title</p>")
            self.assertEqual(render("== "), "<p>==</p>")
            self.assertEqual(render("=="), "<p>==</p>")

        def test_spacing_and_inline(self):
            self.assertEqual(render("==    Wide   gap   \t"), "<h2>Wide   gap</h2>")
            self.assertEqual(render("= A *bold* <<x|y>>"), '<h1>A <strong>bold</strong> <a href="x">y</a></h1>')

        def test_indented_is_not_heading(self):
            self.assertEqual(render(" == Title"), "<p>== Title</p>")


    class Rules(unittest.TestCase):
        def test_rule(self):
            self.assertEqual(render("----"), "<hr>")
            self.assertEqual(render("--------  "), "<hr>")
            self.assertEqual(render("a\n----\nb"), "<p>a</p>\n<hr>\n<p>b</p>")

        def test_short_dashes_are_text(self):
            self.assertEqual(render("---"), "<p>---</p>")
            self.assertEqual(render("---- x"), "<p>---- x</p>")


    class Fences(unittest.TestCase):
        def test_basic(self):
            self.assertEqual(render("{{{\nx = 1\n}}}"), "<pre><code>x = 1</code></pre>")

        def test_content_verbatim(self):
            src = "{{{\n  indented *not bold* <b>\n\n  blank above & =x=\n}}}"
            self.assertEqual(render(src), "<pre><code>  indented *not bold* &lt;b&gt;\n\n  blank above &amp; =x=</code></pre>")

        def test_empty_and_unterminated(self):
            self.assertEqual(render("{{{\n}}}"), "<pre><code></code></pre>")
            self.assertEqual(render("{{{\na\nb"), "<pre><code>a\nb</code></pre>")
            self.assertEqual(render("{{{"), "<pre><code></code></pre>")

        def test_marker_lines_with_blanks(self):
            self.assertEqual(render("  {{{  \ncode\n  }}}  \nafter"), "<pre><code>code</code></pre>\n<p>after</p>")

        def test_fence_interrupts_paragraph(self):
            self.assertEqual(render("text\n{{{\ncode\n}}}\nmore"), "<p>text</p>\n<pre><code>code</code></pre>\n<p>more</p>")

        def test_closer_inside_text_is_not_a_closer(self):
            self.assertEqual(render("{{{\na }}} b\n}}}"), "<pre><code>a }}} b</code></pre>")


    class Quotes(unittest.TestCase):
        def test_basic(self):
            self.assertEqual(render("> one\n> two"), "<blockquote>one two</blockquote>")

        def test_bare_marker_and_extra_spaces(self):
            self.assertEqual(render(">\n> a\n>   b  \n>"), "<blockquote>a b</blockquote>")
            self.assertEqual(render(">x"), "<p>&gt;x</p>")

        def test_inline_inside(self):
            self.assertEqual(render("> *wise* words"), "<blockquote><strong>wise</strong> words</blockquote>")

        def test_interrupts_and_ends(self):
            self.assertEqual(render("para\n> q\ntail"), "<p>para</p>\n<blockquote>q</blockquote>\n<p>tail</p>")


    class Lists(unittest.TestCase):
        def test_bullets_and_numbers(self):
            self.assertEqual(render("- a\n- b\n- c"), "<ul><li>a</li><li>b</li><li>c</li></ul>")
            self.assertEqual(render("+ a\n+ b"), "<ol><li>a</li><li>b</li></ol>")

        def test_kind_switch_starts_new_list(self):
            self.assertEqual(render("- a\n+ b\n- c"), "<ul><li>a</li></ul>\n<ol><li>b</li></ol>\n<ul><li>c</li></ul>")

        def test_continuation(self):
            self.assertEqual(render("- first\n  second\n    third\n- next"), "<ul><li>first second third</li><li>next</li></ul>")
            self.assertEqual(render("- a\n  \n- b"), "<ul><li>a</li></ul>\n<ul><li>b</li></ul>")

        def test_blank_line_splits_lists(self):
            self.assertEqual(render("- a\n\n- b"), "<ul><li>a</li></ul>\n<ul><li>b</li></ul>")

        def test_marker_needs_space(self):
            self.assertEqual(render("-x\n+y"), "<p>-x +y</p>")
            self.assertEqual(render("-"), "<p>-</p>")

        def test_item_inline_and_spacing(self):
            self.assertEqual(render("-    spaced *x*  "), "<ul><li>spaced <strong>x</strong></li></ul>")

        def test_single_space_continuation_ends_list(self):
            self.assertEqual(render("- a\n b"), "<ul><li>a</li></ul>\n<p>b</p>")

        def test_list_interrupts_paragraph_and_heading_ends_list(self):
            self.assertEqual(render("intro\n- a\n== H"), "<p>intro</p>\n<ul><li>a</li></ul>\n<h2>H</h2>")

        def test_dash_rule_is_not_item(self):
            self.assertEqual(render("- a\n----\n- b"), "<ul><li>a</li></ul>\n<hr>\n<ul><li>b</li></ul>")


    class Paragraphs(unittest.TestCase):
        def test_join_and_split(self):
            self.assertEqual(render("one\n  two  \nthree\n\n\n\nfour"), "<p>one two three</p>\n<p>four</p>")

        def test_empty_and_blank(self):
            self.assertEqual(render(""), "")
            self.assertEqual(render("\n  \n\t\n"), "")

        def test_crlf(self):
            self.assertEqual(render("a\r\nb\r\n\r\n== H\r\n"), "<p>a b</p>\n<h2>H</h2>")

        def test_escaping(self):
            self.assertEqual(render('a & b <c> "d"'), "<p>a &amp; b &lt;c&gt; \"d\"</p>")

        def test_heading_line_interrupts(self):
            self.assertEqual(render("text\n== H\nmore"), "<p>text</p>\n<h2>H</h2>\n<p>more</p>")

        def test_block_mix_order(self):
            src = "= T\n\nintro\n\n- a\n- b\n\n> q\n\n----\n\n{{{\nc\n}}}\n"
            want = "<h1>T</h1>\n<p>intro</p>\n<ul><li>a</li><li>b</li></ul>\n<blockquote>q</blockquote>\n<hr>\n<pre><code>c</code></pre>"
            self.assertEqual(render(src), want)


    class Spans(unittest.TestCase):
        def test_the_three_kinds(self):
            self.assertEqual(render("*b* ~i~ =c="), "<p><strong>b</strong> <em>i</em> <code>c</code></p>")

        def test_boundaries_before(self):
            self.assertEqual(render("a*b*c"), "<p>a*b*c</p>")
            self.assertEqual(render("(*b*)"), "<p>(<strong>b</strong>)</p>")
            self.assertEqual(render("[~i~] {=c=}"), "<p>[<em>i</em>] {<code>c</code>}</p>")
            self.assertEqual(render("\"*b*\" '*c*'"), "<p>\"<strong>b</strong>\" '<strong>c</strong>'</p>")
            self.assertEqual(render("-*b*"), "<p>-*b*</p>")

        def test_boundaries_after(self):
            for ch in ".,;:!?)]}\"'":
                self.assertEqual(render("*b*" + ch), "<p><strong>b</strong>%s</p>" % ch)
            self.assertEqual(render("*b*x"), "<p>*b*x</p>")
            self.assertEqual(render("*b*-"), "<p>*b*-</p>")

        def test_opener_followed_by_space(self):
            self.assertEqual(render("* b*"), "<p>* b*</p>")
            self.assertEqual(render("2 * 3 * 4"), "<p>2 * 3 * 4</p>")
            self.assertEqual(render("x = y = z"), "<p>x = y = z</p>")

        def test_closer_not_after_space(self):
            self.assertEqual(render("*b *"), "<p>*b *</p>")
            self.assertEqual(render("*b * c*"), "<p><strong>b * c</strong></p>")

        def test_minimum_content(self):
            self.assertEqual(render("**"), "<p>**</p>")
            self.assertEqual(render("*a*"), "<p><strong>a</strong></p>")
            self.assertEqual(render("*a* *b*"), "<p><strong>a</strong> <strong>b</strong></p>")

        def test_first_valid_closer(self):
            self.assertEqual(render("*a* b*"), "<p><strong>a</strong> b*</p>")
            self.assertEqual(render("*a*b* c"), "<p><strong>a*b</strong> c</p>")

        def test_unclosed(self):
            self.assertEqual(render("*never closed"), "<p>*never closed</p>")
            self.assertEqual(render("~x"), "<p>~x</p>")

        def test_nesting(self):
            self.assertEqual(render("*a ~b~ c*"), "<p><strong>a <em>b</em> c</strong></p>")
            self.assertEqual(render("~*x*~"), "<p><em><strong>x</strong></em></p>")
            self.assertEqual(render("~ *x* ~"), "<p>~ <strong>x</strong> ~</p>")

        def test_code_is_literal(self):
            self.assertEqual(render("=a *b* <c>="), "<p><code>a *b* &lt;c&gt;</code></p>")
            self.assertEqual(render("=x= and =y="), "<p><code>x</code> and <code>y</code></p>")

        def test_escapes(self):
            self.assertEqual(render(r"\*not bold\*"), "<p>*not bold*</p>")
            self.assertEqual(render(r"a \\ b"), "<p>a \\ b</p>")
            self.assertEqual(render(r"\q \< \="), "<p>\\q &lt; =</p>")
            self.assertEqual(render(r"*a\*b*"), "<p><strong>a*b</strong></p>")
            self.assertEqual(render(r"*a\* b*"), "<p><strong>a* b</strong></p>")
            self.assertEqual(render("trailing \\"), "<p>trailing \\</p>")

        def test_escaped_delimiter_closes_nothing(self):
            self.assertEqual(render(r"*a\*"), "<p>*a*</p>")


    class Links(unittest.TestCase):
        def test_basic(self):
            self.assertEqual(render("<<https://x.org|the site>>"), '<p><a href="https://x.org">the site</a></p>')
            self.assertEqual(render("see <<https://x.org>> now"), '<p>see <a href="https://x.org">https://x.org</a> now</p>')

        def test_stripping_and_blank_label(self):
            self.assertEqual(render("<< a.html | label >>"), '<p><a href="a.html">label</a></p>')
            self.assertEqual(render("<<a.html|>>"), '<p><a href="a.html">a.html</a></p>')
            self.assertEqual(render("<<a.html|   >>"), '<p><a href="a.html">a.html</a></p>')

        def test_degenerate(self):
            self.assertEqual(render("<<>>"), "<p>&lt;&lt;&gt;&gt;</p>")
            self.assertEqual(render("<<|x>>"), "<p>&lt;&lt;|x&gt;&gt;</p>")
            self.assertEqual(render("<<open"), "<p>&lt;&lt;open</p>")
            self.assertEqual(render("a < b <c>"), "<p>a &lt; b &lt;c&gt;</p>")

        def test_label_is_plain_and_escaped(self):
            self.assertEqual(render("<<u|a *b* & <c>>"), '<p><a href="u">a *b* &amp; &lt;c</a></p>')

        def test_href_attribute_escaped(self):
            self.assertEqual(render('<<http://x/?a=1&b="2"|t>>'), '<p><a href="http://x/?a=1&amp;b=&quot;2&quot;">t</a></p>')

        def test_link_inside_span(self):
            self.assertEqual(render("*see <<u|x>>*"), '<p><strong>see <a href="u">x</a></strong></p>')

        def test_pipe_in_label_stays(self):
            self.assertEqual(render("<<u|a|b>>"), '<p><a href="u">a|b</a></p>')

        def test_base_url(self):
            self.assertEqual(render("<<a/b.html|t>>", base_url="https://h.io/docs/"), '<p><a href="https://h.io/docs/a/b.html">t</a></p>')
            self.assertEqual(render("<<a.html>>", base_url="https://h.io"), '<p><a href="https://h.io/a.html">a.html</a></p>')
            self.assertEqual(render("<<a.html>>", base_url="https://h.io///"), '<p><a href="https://h.io/a.html">a.html</a></p>')

        def test_base_url_not_applied(self):
            for url in ("/abs", "#frag", "https://o.org/x", "mailto:a@b.c", "//cdn.x/y", "x:y", "a//b"):
                want = '<p><a href="%s">t</a></p>' % url
                self.assertEqual(render("<<%s|t>>" % url, base_url="https://h.io"), want, url)
            self.assertEqual(render("<<rel>>", base_url=""), '<p><a href="rel">rel</a></p>')
            self.assertEqual(render("<<rel>>"), '<p><a href="rel">rel</a></p>')

        def test_base_url_in_headings_and_lists(self):
            out = render("= <<r|t>>\n\n- <<s|u>>", base_url="B")
            self.assertEqual(out, '<h1><a href="B/r">t</a></h1>\n<ul><li><a href="B/s">u</a></li></ul>')
            self.assertEqual(render("> <<r|t>>", base_url="B"), '<blockquote><a href="B/r">t</a></blockquote>')


    if __name__ == "__main__":
        unittest.main()
''')

INK = Lib(
    name="inkmark", lang="python", title="the ink markup renderer (`inkmark.py`)",
    blurb="The help-centre build turns articles written in *ink*, a house markup, into HTML with this module.",
    files={"inkmark.py": INK_SRC, "README.md": INK_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": INK_VISIBLE},
    hidden_tests={"tests/test_full.py": INK_HIDDEN},
    mutate=["inkmark.py"], difficulty=4, tags=["markup", "html"],
    probes=[
        'render("a*b* (*c*) *d*.")',
        'render("*a* b* c")',
        'render("x = y = z and 2 * 3 * 4")',
        'render("==Title\\n===== T\\n= ok")',
        'render("- a\\n  b\\n+ c")',
        'render("para\\n> q1\\n> q2\\n")',
        'render("{{{\\n  keep *this* <b>\\n\\n}}}")',
        'render("<<a/b.html|t>> <<#x>> <<>>", base_url="https://h.io/")',
        'render("\\\\*lit\\\\* and *a\\\\*b*")',
        'render("a\\n----\\n---\\nb")',
    ],
    probe_import="from inkmark import *",
)


# ======================================================================================================================
# verspan: version constraint resolution with a house range syntax
# ======================================================================================================================

SPAN_README = dd(r'''
    # verspan

    Version constraints for the plugin loader. Versions are `MAJOR.MINOR.PATCH` with an optional pre-release; the
    constraint language is a small house syntax.

    ## Versions
    ### `parse_version(text) -> Version`
    `Version` is a `namedtuple` `(major, minor, patch, pre)`; `pre` is a tuple of strings (`()` when there is none).
    `text` is `N.N.N`, optionally followed by `-` and dot-separated pre-release identifiers of `[0-9A-Za-z-]`, optionally
    followed by `+` and build metadata (accepted and dropped). Numbers have no leading zeros (`0` is fine); numeric
    pre-release identifiers have none either. Surrounding whitespace is **not** allowed. Anything else is a `ValueError`.

    ### `compare(a, b) -> int`
    `-1`, `0` or `1`; `a` and `b` are version strings or `Version`s. Order by major, minor, patch; a version with a
    pre-release is lower than the same numbers without. Pre-releases compare identifier by identifier: numeric
    identifiers numerically and lower than alphanumeric ones, alphanumeric ones by ASCII order, and when one list is a
    prefix of the other the shorter is lower.

    ## Constraints
    `parse_constraint(text) -> list` returns a list of groups (alternatives); each group is a list of `(op, Version)`
    pairs with `op` one of `>= > <= < = !=`. `explain(text) -> str` writes it back canonically: each pair as `op` +
    `M.m.p[-pre]`, joined by one space inside a group, and groups joined by ` || `.

    * `||` separates alternatives; inside a group, tokens are separated by whitespace and must all hold. A blank group is a
      `ValueError`.
    * `*` any version: `>=0.0.0`.
    * `>=V`, `>V`, `<=V`, `<V`, `=V`, `!V` (not equal; written `!=`): a bound. `V` may be partial (`1`, `1.2`): padded with zeros.
      Wildcards are not allowed after an operator.
    * `V~` same minor: `>=V` and `<M.(m+1).0`. `V^` same major: `>=V` and `<(M+1).0.0`; but when `M` is 0 it
      is `<0.(m+1).0`, and when `M` and `m` are both 0 it is `<0.0.(p+1)`. `V` may be partial (padded) and needs no wildcard.
    * `A..B` inclusive span: `>=A` and `<=B`, both padded.
    * A bare full version `1.2.3` (or with pre-release) is exactly that version: `=1.2.3`. A bare partial or wildcard
      version is a family: `1` and `1.x` (`x`, `X` or `*`) are `>=1.0.0` and `<2.0.0`; `1.2` and `1.2.x` are `>=1.2.0` and
      `<1.3.0`; a lone `x` is `>=0.0.0`. A wildcard can only be followed by more wildcards. A pre-release needs a full version.
    * Anything else is a `ValueError`.

    ## `satisfies(version, constraint, include_pre=False) -> bool`
    True when some group of `constraint` holds for `version` (a string or a `Version`). A version with a
    pre-release only counts for a group that itself mentions a pre-release in at least one of its bounds, unless
    `include_pre` is true.

    ## `best_match(versions, constraint, include_pre=False) -> str or None`
    The highest version (by `compare`) among the strings of `versions` that satisfy the constraint, returned as the
    string it was given as; `None` if there is none. Strings that are not valid versions are ignored. For equal
    versions (differing only in build metadata) the one listed first wins.
''')

SPAN_SRC = dd(r'''
    """House version-constraint language."""
    import re
    from collections import namedtuple

    Version = namedtuple("Version", "major minor patch pre")

    _VER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z.-]+)?")
    _PART = re.compile(r"(\d+|[xX*])(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?")


    def _check_pre(pre):
        for ident in pre:
            if ident.isdigit() and len(ident) > 1 and ident[0] == "0":
                raise ValueError("leading zero in pre-release identifier: %r" % ident)


    def parse_version(text):
        m = _VER.fullmatch(text)
        if not m:
            raise ValueError("bad version: %r" % text)
        pre = tuple(m.group(4).split(".")) if m.group(4) else ()
        _check_pre(pre)
        return Version(int(m.group(1)), int(m.group(2)), int(m.group(3)), pre)


    def _as_version(v):
        return parse_version(v) if isinstance(v, str) else v


    def _key(v):
        pre = tuple((0, int(i)) if i.isdigit() else (1, i) for i in v.pre)
        return (v.major, v.minor, v.patch, 0 if v.pre else 1, pre)


    def compare(a, b):
        ka, kb = _key(_as_version(a)), _key(_as_version(b))
        return (ka > kb) - (ka < kb)


    def _partial(text):
        m = _PART.fullmatch(text)
        if not m:
            raise ValueError("bad version: %r" % text)
        nums = []
        wild = False
        for g in m.groups()[:3]:
            if g is None:
                continue
            if g in ("x", "X", "*"):
                wild = True
            elif wild:
                raise ValueError("number after wildcard: %r" % text)
            elif len(g) > 1 and g[0] == "0":
                raise ValueError("leading zero: %r" % text)
            else:
                nums.append(int(g))
        pre = tuple(m.group(4).split(".")) if m.group(4) else ()
        _check_pre(pre)
        if pre and len(nums) < 3:
            raise ValueError("pre-release needs a full version: %r" % text)
        return nums, pre, wild


    def _padded(nums, pre=()):
        return Version(*(nums + [0] * (3 - len(nums))), pre)


    def _expand(tok):
        if tok == "*":
            return [(">=", Version(0, 0, 0, ()))]
        if ".." in tok:
            lo, _, hi = tok.partition("..")
            return [(">=", _span_end(lo)), ("<=", _span_end(hi))]
        m = re.fullmatch(r"(>=|<=|>|<|=|!)(.+)", tok)
        if m:
            op = "!=" if m.group(1) == "!" else m.group(1)
            nums, pre, wild = _partial(m.group(2))
            if wild or not nums:
                raise ValueError("wildcard after operator: %r" % tok)
            return [(op, _padded(nums, pre))]
        if tok[-1] in "~^":
            nums, pre, wild = _partial(tok[:-1])
            if wild or not nums:
                raise ValueError("wildcard before %s: %r" % (tok[-1], tok))
            base = _padded(nums, pre)
            if tok[-1] == "~":
                upper = Version(base.major, base.minor + 1, 0, ())
            elif base.major > 0:
                upper = Version(base.major + 1, 0, 0, ())
            elif base.minor > 0:
                upper = Version(0, base.minor + 1, 0, ())
            else:
                upper = Version(0, 0, base.patch + 1, ())
            return [(">=", base), ("<", upper)]
        nums, pre, wild = _partial(tok)
        if len(nums) == 3:
            return [("=", Version(nums[0], nums[1], nums[2], pre))]
        if not nums:
            return [(">=", Version(0, 0, 0, ()))]
        if len(nums) == 1:
            return [(">=", _padded(nums)), ("<", Version(nums[0] + 1, 0, 0, ()))]
        return [(">=", _padded(nums)), ("<", Version(nums[0], nums[1] + 1, 0, ()))]


    def _span_end(text):
        nums, pre, wild = _partial(text)
        if wild or not nums:
            raise ValueError("wildcard in span: %r" % text)
        return _padded(nums, pre)


    def parse_constraint(text):
        groups = []
        for chunk in text.split("||"):
            toks = chunk.split()
            if not toks:
                raise ValueError("empty alternative in %r" % text)
            group = []
            for tok in toks:
                group.extend(_expand(tok))
            groups.append(group)
        return groups


    def _fmt(v):
        s = "%d.%d.%d" % (v.major, v.minor, v.patch)
        return s + ("-" + ".".join(v.pre) if v.pre else "")


    def explain(text):
        return " || ".join(" ".join(op + _fmt(v) for op, v in group) for group in parse_constraint(text))


    def _holds(op, c):
        return {">=": c >= 0, ">": c > 0, "<=": c <= 0, "<": c < 0, "=": c == 0, "!=": c != 0}[op]


    def satisfies(version, constraint, include_pre=False):
        v = _as_version(version)
        for group in parse_constraint(constraint):
            if v.pre and not include_pre and not any(bound.pre for _, bound in group):
                continue
            if all(_holds(op, compare(v, bound)) for op, bound in group):
                return True
        return False


    def best_match(versions, constraint, include_pre=False):
        best = None
        best_v = None
        for text in versions:
            try:
                v = parse_version(text)
            except ValueError:
                continue
            if satisfies(v, constraint, include_pre) and (best is None or compare(v, best_v) > 0):
                best, best_v = text, v
        return best
''')

SPAN_VISIBLE = dd(r'''
    import unittest

    from verspan import best_match, compare, explain, parse_version, satisfies


    class BasicTests(unittest.TestCase):
        def test_parse(self):
            self.assertEqual(tuple(parse_version("1.2.3-rc.1+b5")), (1, 2, 3, ("rc", "1")))

        def test_compare(self):
            self.assertEqual(compare("1.2.3", "1.10.0"), -1)

        def test_explain(self):
            self.assertEqual(explain("1.2~"), ">=1.2.0 <1.3.0")

        def test_satisfies(self):
            self.assertTrue(satisfies("1.4.0", ">=1.2 <2"))

        def test_best(self):
            self.assertEqual(best_match(["1.0.0", "1.5.0", "2.0.0"], "1.x"), "1.5.0")


    if __name__ == "__main__":
        unittest.main()
''')

SPAN_HIDDEN = dd(r'''
    import unittest

    from verspan import Version, best_match, compare, explain, parse_constraint, parse_version, satisfies


    class ParseVersion(unittest.TestCase):
        def test_valid(self):
            self.assertEqual(parse_version("1.2.3"), Version(1, 2, 3, ()))
            self.assertEqual(parse_version("0.0.0"), Version(0, 0, 0, ()))
            self.assertEqual(parse_version("10.20.30"), Version(10, 20, 30, ()))
            self.assertEqual(parse_version("1.2.3-rc.1"), Version(1, 2, 3, ("rc", "1")))
            self.assertEqual(parse_version("1.2.3-alpha-2.x.0"), Version(1, 2, 3, ("alpha-2", "x", "0")))
            self.assertEqual(parse_version("1.2.3+build.5"), Version(1, 2, 3, ()))
            self.assertEqual(parse_version("1.2.3-rc.1+b"), Version(1, 2, 3, ("rc", "1")))
            self.assertEqual(parse_version("1.2.3-0a"), Version(1, 2, 3, ("0a",)))

        def test_invalid(self):
            for text in ("", "1", "1.2", "1.2.3.4", "01.2.3", "1.02.3", "1.2.03", "a.b.c", "1.2.3-", "1.2.3-rc..1", " 1.2.3", "1.2.3 ",
                         "v1.2.3", "1.2.3-01", "1.2.3-rc.01", "1.2.3+", "-1.2.3", "1.2.x"):
                with self.assertRaises(ValueError, msg=repr(text)):
                    parse_version(text)


    class Compare(unittest.TestCase):
        def test_numeric_order(self):
            self.assertEqual(compare("1.2.3", "1.2.3"), 0)
            self.assertEqual(compare("1.2.3", "1.2.4"), -1)
            self.assertEqual(compare("1.3.0", "1.2.9"), 1)
            self.assertEqual(compare("2.0.0", "1.99.99"), 1)
            self.assertEqual(compare("1.2.10", "1.2.9"), 1)
            self.assertEqual(compare("1.10.0", "1.9.0"), 1)
            self.assertEqual(compare("10.0.0", "9.0.0"), 1)

        def test_prerelease_below_release(self):
            self.assertEqual(compare("1.0.0-rc.1", "1.0.0"), -1)
            self.assertEqual(compare("1.0.0", "1.0.0-rc.1"), 1)
            self.assertEqual(compare("1.0.1-rc.1", "1.0.0"), 1)

        def test_prerelease_identifiers(self):
            order = ["1.0.0-1", "1.0.0-2", "1.0.0-10", "1.0.0-a", "1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-b", "1.0.0-rc.1", "1.0.0"]
            for i, a in enumerate(order):
                for j, b in enumerate(order):
                    want = (i > j) - (i < j)
                    self.assertEqual(compare(a, b), want, (a, b))

        def test_build_metadata_ignored(self):
            self.assertEqual(compare("1.0.0+a", "1.0.0+b"), 0)
            self.assertEqual(compare("1.0.0-rc.1+x", "1.0.0-rc.1"), 0)

        def test_accepts_version_objects(self):
            self.assertEqual(compare(Version(1, 0, 0, ()), "1.0.1"), -1)
            self.assertEqual(compare(Version(1, 0, 0, ("a",)), Version(1, 0, 0, ("a",))), 0)

        def test_bad_input(self):
            with self.assertRaises(ValueError):
                compare("1.0", "1.0.0")


    class Explain(unittest.TestCase):
        def check(self, text, want):
            self.assertEqual(explain(text), want, text)

        def test_bounds(self):
            self.check(">=1.2", ">=1.2.0")
            self.check(">1.2.3", ">1.2.3")
            self.check("<=2", "<=2.0.0")
            self.check("<2.1", "<2.1.0")
            self.check("=1.2.3", "=1.2.3")
            self.check("=1.2", "=1.2.0")
            self.check("!1.5.3", "!=1.5.3")
            self.check("!2", "!=2.0.0")
            self.check(">=1.0.0-rc.1", ">=1.0.0-rc.1")

        def test_exact_and_families(self):
            self.check("1.2.3", "=1.2.3")
            self.check("1.2.3-rc.1", "=1.2.3-rc.1")
            self.check("1", ">=1.0.0 <2.0.0")
            self.check("1.x", ">=1.0.0 <2.0.0")
            self.check("1.X", ">=1.0.0 <2.0.0")
            self.check("1.*", ">=1.0.0 <2.0.0")
            self.check("1.2", ">=1.2.0 <1.3.0")
            self.check("1.2.x", ">=1.2.0 <1.3.0")
            self.check("1.2.*", ">=1.2.0 <1.3.0")
            self.check("0.9", ">=0.9.0 <0.10.0")
            self.check("9.x", ">=9.0.0 <10.0.0")
            self.check("x", ">=0.0.0")
            self.check("*", ">=0.0.0")
            self.check("x.x.x", ">=0.0.0")
            self.check("1.x.x", ">=1.0.0 <2.0.0")

        def test_tilde(self):
            self.check("1.2~", ">=1.2.0 <1.3.0")
            self.check("1.2.5~", ">=1.2.5 <1.3.0")
            self.check("1~", ">=1.0.0 <1.1.0")
            self.check("0.0.7~", ">=0.0.7 <0.1.0")
            self.check("1.9.0-rc.1~", ">=1.9.0-rc.1 <1.10.0")

        def test_caret(self):
            self.check("1.2.3^", ">=1.2.3 <2.0.0")
            self.check("1.2^", ">=1.2.0 <2.0.0")
            self.check("1^", ">=1.0.0 <2.0.0")
            self.check("0.4.2^", ">=0.4.2 <0.5.0")
            self.check("0.4^", ">=0.4.0 <0.5.0")
            self.check("0.0.3^", ">=0.0.3 <0.0.4")
            self.check("0.0^", ">=0.0.0 <0.0.1")
            self.check("0^", ">=0.0.0 <0.0.1")
            self.check("9.9.9^", ">=9.9.9 <10.0.0")

        def test_span(self):
            self.check("1.2..1.9", ">=1.2.0 <=1.9.0")
            self.check("1.2.3..4", ">=1.2.3 <=4.0.0")
            self.check("1..2", ">=1.0.0 <=2.0.0")
            self.check("1.0.0-rc.1..1.0.0", ">=1.0.0-rc.1 <=1.0.0")

        def test_groups(self):
            self.check(">=1 <2", ">=1.0.0 <2.0.0")
            self.check(">=1.2   !1.5.3\t<2", ">=1.2.0 !=1.5.3 <2.0.0")
            self.check("1.2~ || 2.x", ">=1.2.0 <1.3.0 || >=2.0.0 <3.0.0")
            self.check("  1.0.0 ||2.0.0||  3.0.0  ", "=1.0.0 || =2.0.0 || =3.0.0")
            self.check("1.x !1.3.0 || *", ">=1.0.0 <2.0.0 !=1.3.0 || >=0.0.0")

        def test_errors(self):
            for text in ("", "   ", "||", "1.0.0 ||", "|| 1.0.0", "1.0.0 || || 2.0.0", ">=", ">=x", ">=1.x", "1.x.3", "x.2", "1.2.3.4", "^1.2",
                         "~1.2", "x~", "*^", "1.x~", "1.x-rc.1", "1.2-rc.1", "abc", "=>1", "1.2.3-01", "1.x..2", "1..x",
                         "..2", "1..", "01.2.3", ">=1.02", "!", "<>1"):
                with self.assertRaises(ValueError, msg=repr(text)):
                    parse_constraint(text)

        def test_structure(self):
            got = parse_constraint("1.2~ || =3.0.0")
            self.assertEqual(got, [[(">=", Version(1, 2, 0, ())), ("<", Version(1, 3, 0, ()))], [("=", Version(3, 0, 0, ()))]])


    class Satisfies(unittest.TestCase):
        def yes(self, v, c, **kw):
            self.assertTrue(satisfies(v, c, **kw), (v, c))

        def no(self, v, c, **kw):
            self.assertFalse(satisfies(v, c, **kw), (v, c))

        def test_bounds_and_edges(self):
            self.yes("1.2.0", ">=1.2")
            self.no("1.1.9", ">=1.2")
            self.yes("1.2.1", ">1.2")
            self.no("1.2.0", ">1.2")
            self.yes("1.2.0", "<=1.2")
            self.no("1.2.1", "<=1.2")
            self.yes("1.1.9", "<1.2")
            self.no("1.2.0", "<1.2")
            self.yes("1.2.0", "=1.2")
            self.no("1.2.1", "=1.2")
            self.yes("1.2.1", "!1.2")
            self.no("1.2.0", "!1.2")

        def test_exact_ignores_build(self):
            self.yes("1.2.3", "1.2.3")
            self.yes("1.2.3+b9", "1.2.3")
            self.no("1.2.4", "1.2.3")

        def test_families(self):
            self.yes("1.0.0", "1.x")
            self.yes("1.99.9", "1")
            self.no("2.0.0", "1.x")
            self.no("0.9.9", "1.x")
            self.yes("1.2.9", "1.2")
            self.no("1.3.0", "1.2.x")
            self.no("1.1.9", "1.2")
            self.yes("0.0.0", "*")
            self.yes("123.4.5", "x")

        def test_tilde_and_caret(self):
            self.yes("1.2.5", "1.2.3~")
            self.no("1.2.2", "1.2.3~")
            self.no("1.3.0", "1.2.3~")
            self.yes("1.9.9", "1.2.3^")
            self.no("2.0.0", "1.2.3^")
            self.no("1.2.2", "1.2.3^")
            self.yes("0.4.9", "0.4.2^")
            self.no("0.5.0", "0.4.2^")
            self.yes("0.0.3", "0.0.3^")
            self.no("0.0.4", "0.0.3^")

        def test_span_is_inclusive(self):
            self.yes("1.2.0", "1.2..1.9")
            self.yes("1.9.0", "1.2..1.9")
            self.no("1.9.1", "1.2..1.9")
            self.no("1.1.9", "1.2..1.9")
            self.yes("1.5.5", "1.2..1.9")

        def test_and_or(self):
            c = ">=1.2 !1.5.3 <2 || 3.x"
            self.yes("1.5.2", c)
            self.no("1.5.3", c)
            self.yes("1.5.4", c)
            self.no("2.0.0", c)
            self.yes("3.4.5", c)
            self.no("4.0.0", c)
            self.no("1.1.0", c)

        def test_prerelease_gate(self):
            self.no("1.5.0-rc.1", ">=1.0")
            self.no("1.5.0-rc.1", "1.x")
            self.no("2.0.0-rc.1", "<3")
            self.no("1.0.0-rc.1", "*")
            self.yes("1.5.0-rc.1", ">=1.0", include_pre=True)
            self.yes("1.5.0-rc.1", ">=1.5.0-alpha")
            self.no("1.5.0-rc.1", ">=1.5.0-rc.2")
            self.yes("1.5.0-rc.2", ">=1.5.0-rc.2")
            self.yes("1.0.0-rc.1", "1.0.0-rc.1")
            self.no("1.0.0-rc.1", "1.0.0")
            self.no("1.0.0", "1.0.0-rc.1")

        def test_prerelease_gate_is_per_group(self):
            c = ">=1.0.0-rc.1 <1.0.0 || >=2.0.0"
            self.yes("1.0.0-rc.5", c)
            self.no("2.1.0-beta.1", c)
            self.yes("2.1.0", c)
            self.yes("2.1.0-beta.1", c, include_pre=True)

        def test_prerelease_ordering_inside_bounds(self):
            self.yes("1.0.0-rc.1", "<1.0.0 >=0.9.0-0")
            self.no("1.0.0", "<1.0.0 >=0.9.0-0")
            self.no("0.8.0-9", ">=0.9.0-0 <1.0.0")

        def test_version_objects_and_bad_input(self):
            self.assertTrue(satisfies(Version(1, 2, 3, ()), "1.x"))
            with self.assertRaises(ValueError):
                satisfies("1.2", "1.x")
            with self.assertRaises(ValueError):
                satisfies("1.2.3", "nonsense")


    class BestMatch(unittest.TestCase):
        V = ["1.0.0", "1.2.0", "1.10.0", "1.9.9", "2.0.0", "2.1.0-rc.1", "0.9.0", "junk", "1.2", "1.11.0-beta.1"]

        def test_highest_wins_numerically(self):
            self.assertEqual(best_match(self.V, "1.x"), "1.10.0")
            self.assertEqual(best_match(self.V, ">=1.2 <1.10"), "1.9.9")
            self.assertEqual(best_match(self.V, "<1"), "0.9.0")

        def test_none(self):
            self.assertEqual(best_match(self.V, ">=3"), None)
            self.assertEqual(best_match([], "*"), None)
            self.assertEqual(best_match(["junk", "1.2"], "*"), None)

        def test_prereleases(self):
            self.assertEqual(best_match(self.V, ">=2"), "2.0.0")
            self.assertEqual(best_match(self.V, ">=2", include_pre=True), "2.1.0-rc.1")
            self.assertEqual(best_match(self.V, "1.x", include_pre=True), "1.11.0-beta.1")
            self.assertEqual(best_match(self.V, ">=2.1.0-alpha"), "2.1.0-rc.1")

        def test_or_groups(self):
            self.assertEqual(best_match(self.V, "0.x || 2.0.0"), "2.0.0")
            self.assertEqual(best_match(self.V, "0.x || 1.0..1.2"), "1.2.0")

        def test_equal_versions_first_listed_wins(self):
            self.assertEqual(best_match(["1.0.0+b", "1.0.0+a"], "1.x"), "1.0.0+b")
            self.assertEqual(best_match(["1.0.0", "1.0.0+z"], "1.x"), "1.0.0")

        def test_returns_given_string(self):
            self.assertEqual(best_match(["1.0.0+meta", "0.1.0"], "*"), "1.0.0+meta")

        def test_input_order_irrelevant(self):
            fwd = best_match(["1.0.0", "1.5.0", "1.3.0"], "1.x")
            rev = best_match(["1.3.0", "1.5.0", "1.0.0"], "1.x")
            self.assertEqual((fwd, rev), ("1.5.0", "1.5.0"))


    if __name__ == "__main__":
        unittest.main()
''')

SPAN = Lib(
    name="verspan", lang="python", title="the version-constraint resolver (`verspan.py`)",
    blurb="The plugin loader uses this module to pick the newest plugin build that satisfies a dependency constraint.",
    files={"verspan.py": SPAN_SRC, "README.md": SPAN_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": SPAN_VISIBLE},
    hidden_tests={"tests/test_full.py": SPAN_HIDDEN},
    mutate=["verspan.py"], difficulty=4, tags=["versions", "parsing"],
    probes=[
        'compare("1.2.10", "1.2.9")',
        'compare("1.0.0-alpha.1", "1.0.0-alpha.beta")',
        'compare("1.0.0-rc.1", "1.0.0")',
        'explain("0.4.2^ || 1.2~ || 3.x")',
        'explain("1.2..1.9 !1.5.3")',
        'explain("0^ 1^ 0.0.3^")',
        'satisfies("1.9.1", "1.2..1.9")',
        'satisfies("1.5.0-rc.1", ">=1.0")',
        'satisfies("1.5.0-rc.1", ">=1.5.0-alpha")',
        'best_match(["1.0.0", "1.10.0", "1.9.9", "2.0.0"], "1.x")',
        'best_match(["1.0.0+b", "1.0.0+a"], "1.x")',
        'parse_version("1.2.3-alpha-2.x.0+b")',
    ],
    probe_import="from verspan import *",
)


LIBS = [BRACE, INK, SPAN]
register_libs(LIBS, n=10)
