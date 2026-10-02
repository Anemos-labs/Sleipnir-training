"""Tag-filter query language: tokenizer, parser, evaluator (typescript): bugs injected into a small query engine."""
from fx import Lib, dd
from generators.fix._lang2 import PACKAGE_JSON, TS_NODE_SHIM, TS_VERIFY, TSCONFIG, register_libs

README = dd(r'''
    # tagquery

    The filter box of a photo-library app: people type things like `beach (sunset | sunrise) -blurry rating>=4`.
    TypeScript, no dependencies. `import { tokenize } from './src/lexer'`, `import { parse } from './src/parser'`,
    `import { matches, filter } from './src/eval'`, `import { format } from './src/format'`.

    ## Query syntax

    * A *word* is any run of characters other than whitespace, `(`, `)`, `|` and `"`. A word is a **tag** test, except that a
      word of the form `key:value`, `key>=N`, `key<=N`, `key>N`, `key<N` or `key=N` is a **field** test (`key` is
      `[A-Za-z_][A-Za-z0-9_]*`; for the comparison operators `N` must be a number such as `4` or `-2.5`, otherwise `SyntaxError`;
      `key:` with nothing after it is a `SyntaxError`).
    * `"two words"` is a quoted tag test; inside quotes `\"` is a quote and `\\` a backslash (a backslash before any other
      character just yields that character). A missing closing quote is a `SyntaxError`.
    * Writing terms next to each other means AND. `|` means OR and binds weaker than AND: `a b | c` is `(a b) | c`.
    * `-` directly in front of a term, group or another `-` negates it (`-blurry`, `-(a | b)`, `-"big cat"`). A `-` followed by
      whitespace, `)`, `|` or the end of the text is a `SyntaxError`.
    * Parentheses group. An empty operand (`a |`, `| a`, `()`, `a | | b`), a missing `)` or a stray `)` is a `SyntaxError`.
    * The empty query (nothing but whitespace) matches everything.

    ## `src/lexer.ts`

    `tokenize(text)` returns tokens `{ type, text, pos }` in order, where `type` is one of `'word'`, `'quoted'`, `'('`, `')'`,
    `'|'`, `'-'`, `text` is the token's text (for `'quoted'` without the quotes and with escapes resolved) and `pos` the
    index of its first character in `text`. Dangling minus signs and unterminated quotes are `SyntaxError`s here.

    ## `src/parser.ts`

    `parse(text)` returns a tree of nodes: `{ kind: 'tag', text, quoted }`, `{ kind: 'field', key, op, value }` (`op` is the
    operator text, `value` the text after it), `{ kind: 'not', child }`, `{ kind: 'and', children }` and
    `{ kind: 'or', children }`. An AND or OR with a single operand is replaced by that operand; the empty query is
    `{ kind: 'and', children: [] }`. Parenthesised groups keep their own node (`a (b c)` is an AND of `a` and an AND).

    ## `src/eval.ts`

    An item is `{ tags, fields? }`. `matches(node, item)`:

    * `tag`: some tag of the item equals the text, ignoring letter case. For an unquoted tag ending in `*`, the rest of the text
      is a prefix (`sun*` matches `Sunset`). Quoted tags never use `*`.
    * `field` with `:`: the item has a field `key` whose value, as text (`String(value)`), equals `value` ignoring case; a
      `value` ending in `*` is a prefix test. A missing field never matches.
    * `field` with a comparison: the field's value must be a number, or a string that looks like a number (`-?digits` with
      an optional `.digits`); it is compared with `Number(value)`. Anything else, and a missing field, does not match.
    * `not`, `and` (every child), `or` (some child); an empty AND is true.

    `filter(text, items)` returns the matching items in their original order.

    ## `src/format.ts`

    `format(node)` writes a node back as a normalised query: tags as written (quoted ones in `"` with `"` and `\` escaped),
    fields as `key<op>value`, `not` as `-` plus its child, AND children separated by one space, OR children by `' | '`. An OR that
    is a child of an AND or of a `not` is wrapped in parentheses, and so is an AND that is a child of an AND or of a `not`.
    The empty AND formats as `''`.
''')

LEXER = dd(r'''
    export interface Token {
      type: "word" | "quoted" | "(" | ")" | "|" | "-";
      text: string;
      pos: number;
    }

    const BREAKS = /[\s()|"]/;

    export function tokenize(src: string): Token[] {
      const out: Token[] = [];
      let i = 0;
      while (i < src.length) {
        const ch = src[i];
        if (/\s/.test(ch)) {
          i++;
        } else if (ch === "(" || ch === ")" || ch === "|") {
          out.push({ type: ch, text: ch, pos: i });
          i++;
        } else if (ch === '"') {
          let j = i + 1;
          let text = "";
          while (j < src.length && src[j] !== '"') {
            if (src[j] === "\\" && j + 1 < src.length) {
              text += src[j + 1];
              j += 2;
            } else {
              text += src[j];
              j++;
            }
          }
          if (j >= src.length) throw new SyntaxError(`unterminated quote at ${i}`);
          out.push({ type: "quoted", text, pos: i });
          i = j + 1;
        } else if (ch === "-") {
          if (i + 1 >= src.length || /[\s)|]/.test(src[i + 1])) throw new SyntaxError(`dangling - at ${i}`);
          out.push({ type: "-", text: "-", pos: i });
          i++;
        } else {
          let j = i;
          while (j < src.length && !BREAKS.test(src[j])) j++;
          out.push({ type: "word", text: src.slice(i, j), pos: i });
          i = j;
        }
      }
      return out;
    }
''')

PARSER = dd(r'''
    import { Token, tokenize } from "./lexer";

    export type Op = ":" | ">=" | "<=" | ">" | "<" | "=";

    export type Node =
      | { kind: "tag"; text: string; quoted: boolean }
      | { kind: "field"; key: string; op: Op; value: string }
      | { kind: "not"; child: Node }
      | { kind: "and"; children: Node[] }
      | { kind: "or"; children: Node[] };

    const FIELD = /^([A-Za-z_][A-Za-z0-9_]*)(>=|<=|:|>|<|=)(.*)$/;
    const NUMBER = /^-?\d+(\.\d+)?$/;

    class Parser {
      private at = 0;

      constructor(private readonly tokens: Token[]) {}

      done(): boolean {
        return this.at >= this.tokens.length;
      }

      private peek(): Token | undefined {
        return this.tokens[this.at];
      }

      parseOr(): Node {
        const kids = [this.parseAnd()];
        while (this.peek()?.type === "|") {
          this.at++;
          kids.push(this.parseAnd());
        }
        return kids.length === 1 ? kids[0] : { kind: "or", children: kids };
      }

      private parseAnd(): Node {
        const kids: Node[] = [];
        for (;;) {
          const t = this.peek();
          if (t === undefined || t.type === "|" || t.type === ")") break;
          kids.push(this.parseUnary());
        }
        if (kids.length === 0) {
          const t = this.peek();
          throw new SyntaxError(`missing operand at ${t === undefined ? "the end" : t.pos}`);
        }
        return kids.length === 1 ? kids[0] : { kind: "and", children: kids };
      }

      private parseUnary(): Node {
        if (this.peek()?.type === "-") {
          this.at++;
          return { kind: "not", child: this.parseUnary() };
        }
        return this.parseAtom();
      }

      private parseAtom(): Node {
        const t = this.tokens[this.at++];
        if (t.type === "(") {
          const inner = this.parseOr();
          const close = this.tokens[this.at++];
          if (close === undefined || close.type !== ")") throw new SyntaxError(`missing ) for the ( at ${t.pos}`);
          return inner;
        }
        if (t.type === "quoted") return { kind: "tag", text: t.text, quoted: true };
        const m = FIELD.exec(t.text);
        if (m === null) return { kind: "tag", text: t.text, quoted: false };
        const op = m[2] as Op;
        if (m[3] === "") throw new SyntaxError(`missing value after ${m[1]}${op} at ${t.pos}`);
        if (op !== ":" && !NUMBER.test(m[3])) throw new SyntaxError(`${m[1]}${op} needs a number at ${t.pos}`);
        return { kind: "field", key: m[1], op, value: m[3] };
      }
    }

    export function parse(text: string): Node {
      const tokens = tokenize(text);
      if (tokens.length === 0) return { kind: "and", children: [] };
      const p = new Parser(tokens);
      const node = p.parseOr();
      if (!p.done()) throw new SyntaxError("unexpected )");
      return node;
    }
''')

EVAL = dd(r'''
    import { Node, parse } from "./parser";

    export interface Item {
      tags: string[];
      fields?: Record<string, string | number>;
    }

    const NUMBER = /^-?\d+(\.\d+)?$/;

    function textMatch(pattern: string, value: string, allowStar: boolean): boolean {
      const p = pattern.toLowerCase();
      const v = value.toLowerCase();
      if (allowStar && p.endsWith("*")) return v.startsWith(p.slice(0, -1));
      return v === p;
    }

    function numeric(value: string | number | undefined): number {
      if (typeof value === "number") return value;
      if (typeof value === "string" && NUMBER.test(value)) return Number(value);
      return NaN;
    }

    export function matches(node: Node, item: Item): boolean {
      switch (node.kind) {
        case "and":
          return node.children.every((c) => matches(c, item));
        case "or":
          return node.children.some((c) => matches(c, item));
        case "not":
          return !matches(node.child, item);
        case "tag":
          return item.tags.some((t) => textMatch(node.text, t, !node.quoted));
        case "field": {
          const actual = item.fields?.[node.key];
          if (actual === undefined) return false;
          if (node.op === ":") return textMatch(node.value, String(actual), true);
          const n = numeric(actual);
          const want = Number(node.value);
          if (Number.isNaN(n)) return false;
          if (node.op === ">") return n > want;
          if (node.op === ">=") return n >= want;
          if (node.op === "<") return n < want;
          if (node.op === "<=") return n <= want;
          return n === want;
        }
      }
    }

    export function filter(text: string, items: Item[]): Item[] {
      const node = parse(text);
      return items.filter((item) => matches(node, item));
    }
''')

FORMAT = dd(r'''
    import { Node } from "./parser";

    function quote(text: string): string {
      return `"${text.replace(/[\\"]/g, (c) => "\\" + c)}"`;
    }

    function wrapped(node: Node, inAnd: boolean): string {
      const text = format(node);
      const needs = inAnd && (node.kind === "or" || (node.kind === "and" && node.children.length > 0));
      return needs ? `(${text})` : text;
    }

    export function format(node: Node): string {
      switch (node.kind) {
        case "tag":
          return node.quoted ? quote(node.text) : node.text;
        case "field":
          return `${node.key}${node.op}${node.value}`;
        case "not":
          return "-" + wrapped(node.child, true);
        case "and":
          return node.children.map((c) => wrapped(c, true)).join(" ");
        case "or":
          return node.children.map((c) => wrapped(c, false)).join(" | ");
      }
    }
''')

VISIBLE = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { parse } from "../src/parser";
    import { filter } from "../src/eval";

    test("two tags are an AND", () => {
      assert.deepEqual(parse("a b"), { kind: "and", children: [{ kind: "tag", text: "a", quoted: false }, { kind: "tag", text: "b", quoted: false }] });
    });

    test("filter by tag", () => {
      const items = [{ tags: ["beach"] }, { tags: ["city"] }];
      assert.deepEqual(filter("beach", items), [items[0]]);
    });
''')

HIDDEN = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { tokenize } from "../src/lexer";
    import { parse, Node } from "../src/parser";
    import { matches, filter, Item } from "../src/eval";
    import { format } from "../src/format";

    const tag = (text: string, quoted = false): Node => ({ kind: "tag", text, quoted });
    const and = (...children: Node[]): Node => ({ kind: "and", children });
    const or = (...children: Node[]): Node => ({ kind: "or", children });
    const not = (child: Node): Node => ({ kind: "not", child });
    const field = (key: string, op: ":" | ">=" | "<=" | ">" | "<" | "=", value: string): Node => ({ kind: "field", key, op, value });
    const syntaxError = (text: string) => assert.throws(() => parse(text), SyntaxError, JSON.stringify(text));

    test("tokenize: basic shapes and positions", () => {
      assert.deepEqual(tokenize(""), []);
      assert.deepEqual(tokenize("   "), []);
      assert.deepEqual(tokenize("a (b|c)  -d"), [
        { type: "word", text: "a", pos: 0 },
        { type: "(", text: "(", pos: 2 },
        { type: "word", text: "b", pos: 3 },
        { type: "|", text: "|", pos: 4 },
        { type: "word", text: "c", pos: 5 },
        { type: ")", text: ")", pos: 6 },
        { type: "-", text: "-", pos: 9 },
        { type: "word", text: "d", pos: 10 },
      ]);
    });

    test("tokenize: words, minus signs and quotes", () => {
      assert.deepEqual(tokenize("a-b"), [{ type: "word", text: "a-b", pos: 0 }]);
      assert.deepEqual(tokenize("x:-5"), [{ type: "word", text: "x:-5", pos: 0 }]);
      assert.deepEqual(tokenize("--a").map((t) => t.type), ["-", "-", "word"]);
      assert.deepEqual(tokenize('-"big cat"').map((t) => t.type), ["-", "quoted"]);
      assert.deepEqual(tokenize('"two words"x'), [{ type: "quoted", text: "two words", pos: 0 }, { type: "word", text: "x", pos: 11 }]);
      assert.deepEqual(tokenize('a"b"'), [{ type: "word", text: "a", pos: 0 }, { type: "quoted", text: "b", pos: 1 }]);
      assert.deepEqual(tokenize('"say \\"hi\\" \\\\ \\n"'), [{ type: "quoted", text: 'say "hi" \\ n', pos: 0 }]);
      assert.deepEqual(tokenize('""'), [{ type: "quoted", text: "", pos: 0 }]);
      assert.deepEqual(tokenize("tab\tsep"), [{ type: "word", text: "tab", pos: 0 }, { type: "word", text: "sep", pos: 4 }]);
    });

    test("tokenize: errors", () => {
      assert.throws(() => tokenize('"open'), SyntaxError);
      assert.throws(() => tokenize('a "b \\"'), SyntaxError);
      assert.throws(() => tokenize("a -"), SyntaxError);
      assert.throws(() => tokenize("- a"), SyntaxError);
      assert.throws(() => tokenize("-)"), SyntaxError);
      assert.throws(() => tokenize("-|a"), SyntaxError);
      assert.throws(() => tokenize("-"), SyntaxError);
      assert.doesNotThrow(() => tokenize("a-"));
    });

    test("parse: terms", () => {
      assert.deepEqual(parse("beach"), tag("beach"));
      assert.deepEqual(parse('"big cat"'), tag("big cat", true));
      assert.deepEqual(parse("sun*"), tag("sun*"));
      assert.deepEqual(parse("a-b"), tag("a-b"));
      assert.deepEqual(parse("http://x"), field("http", ":", "//x"));
      assert.deepEqual(parse("1:2"), tag("1:2"));
      assert.deepEqual(parse("x_1:ok"), field("x_1", ":", "ok"));
    });

    test("parse: fields", () => {
      assert.deepEqual(parse("rating>=4"), field("rating", ">=", "4"));
      assert.deepEqual(parse("rating<=4"), field("rating", "<=", "4"));
      assert.deepEqual(parse("rating>4"), field("rating", ">", "4"));
      assert.deepEqual(parse("rating<4"), field("rating", "<", "4"));
      assert.deepEqual(parse("rating=4"), field("rating", "=", "4"));
      assert.deepEqual(parse("rating>=-2.5"), field("rating", ">=", "-2.5"));
      assert.deepEqual(parse("camera:Nikon*"), field("camera", ":", "Nikon*"));
      assert.deepEqual(parse("size:10x20"), field("size", ":", "10x20"));
      assert.deepEqual(parse("a:b:c"), field("a", ":", "b:c"));
    });

    test("parse: AND, OR and precedence", () => {
      assert.deepEqual(parse("a b c"), and(tag("a"), tag("b"), tag("c")));
      assert.deepEqual(parse("a | b | c"), or(tag("a"), tag("b"), tag("c")));
      assert.deepEqual(parse("a b | c"), or(and(tag("a"), tag("b")), tag("c")));
      assert.deepEqual(parse("a | b c"), or(tag("a"), and(tag("b"), tag("c"))));
      assert.deepEqual(parse("a b | c d | e"), or(and(tag("a"), tag("b")), and(tag("c"), tag("d")), tag("e")));
      assert.deepEqual(parse("  a   b  "), and(tag("a"), tag("b")));
    });

    test("parse: groups and negation", () => {
      assert.deepEqual(parse("(a)"), tag("a"));
      assert.deepEqual(parse("((a b))"), and(tag("a"), tag("b")));
      assert.deepEqual(parse("a (b | c)"), and(tag("a"), or(tag("b"), tag("c"))));
      assert.deepEqual(parse("a (b c)"), and(tag("a"), and(tag("b"), tag("c"))));
      assert.deepEqual(parse("(a | b) c"), and(or(tag("a"), tag("b")), tag("c")));
      assert.deepEqual(parse("-a"), not(tag("a")));
      assert.deepEqual(parse("--a"), not(not(tag("a"))));
      assert.deepEqual(parse("-(a | b)"), not(or(tag("a"), tag("b"))));
      assert.deepEqual(parse('-"big cat" x'), and(not(tag("big cat", true)), tag("x")));
      assert.deepEqual(parse("a -b"), and(tag("a"), not(tag("b"))));
      assert.deepEqual(parse("-a b"), and(not(tag("a")), tag("b")));
      assert.deepEqual(parse("-rating>3"), not(field("rating", ">", "3")));
      assert.deepEqual(parse("a|-b"), or(tag("a"), not(tag("b"))));
    });

    test("parse: the empty query", () => {
      assert.deepEqual(parse(""), and());
      assert.deepEqual(parse("   "), and());
    });

    test("parse: syntax errors", () => {
      for (const bad of ["a |", "| a", "()", "a | | b", "(a", "a)", "(a))", "((a)", ")", "(", "|", "a ( | b)", "rating>=high", "rating>x", "rating<", "rating>=", "key:", "a -", '"open', "a (b |)", "-()", "()a", "a ()"]) {
        syntaxError(bad);
      }
    });

    const PHOTOS: Item[] = [
      { tags: ["Beach", "Sunset", "family"], fields: { rating: 5, camera: "Nikon D3", year: 2021 } },
      { tags: ["beach", "sunrise", "blurry"], fields: { rating: 2, camera: "Pixel 7", year: "2022" } },
      { tags: ["city", "night", "Big Cat"], fields: { rating: 4.5, camera: "nikon z6", year: 2020 } },
      { tags: ["sunday", "family"], fields: { rating: "3", camera: "", year: "n/a" } },
      { tags: [] },
    ];
    const find = (q: string) => filter(q, PHOTOS).map((p) => PHOTOS.indexOf(p));

    test("filter: tags ignore case and need exact text", () => {
      assert.deepEqual(find("beach"), [0, 1]);
      assert.deepEqual(find("BEACH"), [0, 1]);
      assert.deepEqual(find("sun"), []);
      assert.deepEqual(find("family"), [0, 3]);
      assert.deepEqual(find("nothing"), []);
      assert.deepEqual(find("beach family"), [0]);
    });

    test("filter: prefix tags", () => {
      assert.deepEqual(find("sun*"), [0, 1, 3]);
      assert.deepEqual(find("SUN*"), [0, 1, 3]);
      assert.deepEqual(find("SUNS*"), [0]);
      assert.deepEqual(find("sunr*"), [1]);
      assert.deepEqual(find("*"), [0, 1, 2, 3]);
      assert.deepEqual(find("c*"), [2]);
      assert.deepEqual(find("sunday*"), [3]);
      assert.deepEqual(find("sundayy*"), []);
    });

    test("filter: quoted tags are literal", () => {
      assert.deepEqual(find('"big cat"'), [2]);
      assert.deepEqual(find('"Big Cat"'), [2]);
      assert.deepEqual(find('"big"'), []);
      assert.deepEqual(find('"sun*"'), []);
      assert.deepEqual(find('"family"'), [0, 3]);
      assert.deepEqual(find('-"big cat"'), [0, 1, 3, 4]);
    });

    test("filter: OR, NOT and groups", () => {
      assert.deepEqual(find("sunset | sunrise"), [0, 1]);
      assert.deepEqual(find("beach -blurry"), [0]);
      assert.deepEqual(find("beach (sunset | sunrise) -blurry"), [0]);
      assert.deepEqual(find("-beach"), [2, 3, 4]);
      assert.deepEqual(find("--beach"), [0, 1]);
      assert.deepEqual(find("-(beach | city)"), [3, 4]);
      assert.deepEqual(find("city | family"), [0, 2, 3]);
      assert.deepEqual(find("family night | beach blurry"), [1]);
      assert.deepEqual(find("(family | night) (beach | city)"), [0, 2]);
      assert.deepEqual(find("-(beach family)"), [1, 2, 3, 4]);
    });

    test("filter: the empty query matches everything", () => {
      assert.deepEqual(find(""), [0, 1, 2, 3, 4]);
      assert.deepEqual(find("  "), [0, 1, 2, 3, 4]);
    });

    test("filter: text fields", () => {
      assert.deepEqual(find("camera:nikon*"), [0, 2]);
      assert.deepEqual(find("camera:Nikon"), []);
      assert.deepEqual(find('camera:pixel'), []);
      assert.deepEqual(find("camera:pixel*"), [1]);
      assert.deepEqual(find("year:2021"), [0]);
      assert.deepEqual(find("year:2022"), [1]);
      assert.deepEqual(find("year:20*"), [0, 1, 2]);
      assert.deepEqual(find("rating:5"), [0]);
      assert.deepEqual(find("rating:4.5"), [2]);
      assert.deepEqual(find("rating:3"), [3]);
      assert.deepEqual(find("lens:any"), []);
      assert.deepEqual(find("-lens:any"), [0, 1, 2, 3, 4]);
      assert.deepEqual(find("camera:*"), [0, 1, 2, 3]);
    });

    test("filter: numeric comparisons", () => {
      assert.deepEqual(find("rating>=4"), [0, 2]);
      assert.deepEqual(find("rating>4"), [0, 2]);
      assert.deepEqual(find("rating>4.5"), [0]);
      assert.deepEqual(find("rating>=4.5"), [0, 2]);
      assert.deepEqual(find("rating<3"), [1]);
      assert.deepEqual(find("rating<=3"), [1, 3]);
      assert.deepEqual(find("rating=3"), [3]);
      assert.deepEqual(find("rating=5"), [0]);
      assert.deepEqual(find("rating>=2 rating<=4"), [1, 3]);
      assert.deepEqual(find("year>=2021"), [0, 1]);
      assert.deepEqual(find("year<2021"), [2]);
      assert.deepEqual(find("camera>0"), []);
      assert.deepEqual(find("nofield<100"), []);
      assert.deepEqual(find("-year>=2021"), [2, 3, 4]);
    });

    test("matches works on parsed trees and does not modify items", () => {
      const item: Item = { tags: ["a", "b"], fields: { n: 3 } };
      assert.equal(matches(parse("a b n=3"), item), true);
      assert.equal(matches(parse("a c"), item), false);
      assert.equal(matches(parse("a | c"), item), true);
      assert.equal(matches(parse("-c"), item), true);
      assert.equal(matches(and(), item), true);
      assert.equal(matches(or(), item), false);
      assert.deepEqual(item, { tags: ["a", "b"], fields: { n: 3 } });
      assert.equal(matches(parse("a"), { tags: ["a"] }), true);
      assert.equal(matches(parse("n=3"), { tags: ["a"] }), false);
    });

    test("filter keeps the original order and objects", () => {
      const items: Item[] = [{ tags: ["z"] }, { tags: ["a"] }, { tags: ["z"] }];
      const got = filter("z", items);
      assert.equal(got.length, 2);
      assert.strictEqual(got[0], items[0]);
      assert.strictEqual(got[1], items[2]);
      assert.throws(() => filter("(", items), SyntaxError);
    });

    test("format: terms and fields", () => {
      assert.equal(format(parse("beach")), "beach");
      assert.equal(format(parse('"big cat"')), '"big cat"');
      assert.equal(format(parse('"say \\"hi\\" \\\\"')), '"say \\"hi\\" \\\\"');
      assert.equal(format(parse("rating>=4")), "rating>=4");
      assert.equal(format(parse("camera:Nikon*")), "camera:Nikon*");
      assert.equal(format(parse("")), "");
      assert.equal(format(parse("sun*")), "sun*");
    });

    test("format: structure and parentheses", () => {
      assert.equal(format(parse("a b c")), "a b c");
      assert.equal(format(parse("a|b|c")), "a | b | c");
      assert.equal(format(parse("a b|c")), "a b | c");
      assert.equal(format(parse("a (b|c)")), "a (b | c)");
      assert.equal(format(parse("(a | b) c")), "(a | b) c");
      assert.equal(format(parse("a (b c)")), "a (b c)");
      assert.equal(format(parse("-a")), "-a");
      assert.equal(format(parse("--a")), "--a");
      assert.equal(format(parse("-(a|b)")), "-(a | b)");
      assert.equal(format(parse("-(a b)")), "-(a b)");
      assert.equal(format(parse('-"big cat" x')), '-"big cat" x');
      assert.equal(format(parse("a|(b|c)")), "a | b | c");
      assert.equal(format(parse("  a    b ")), "a b");
    });

    test("format round trips through parse", () => {
      for (const q of ["a b | c d", "beach (sunset | sunrise) -blurry rating>=4", '-("big cat" | x:y) z', "a (b (c | d))", "--a | -(b c)"]) {
        const once = parse(q);
        assert.deepEqual(parse(format(once)), once, q);
      }
    });
''')

LIB = Lib(
    name="tagquery", lang="typescript", title="the tagquery filter language",
    blurb="The photo library's filter box turns what people type into a tag-and-field query with tagquery.",
    files={"package.json": PACKAGE_JSON % "tagquery", "tsconfig.json": TSCONFIG, "types/node-shim.d.ts": TS_NODE_SHIM,
           "src/lexer.ts": LEXER, "src/parser.ts": PARSER, "src/eval.ts": EVAL, "src/format.ts": FORMAT, "README.md": README, ".gitignore": "node_modules/\nbuild/\n"},
    visible_tests={"test/basic.test.ts": VISIBLE},
    hidden_tests={"test/full.test.ts": HIDDEN},
    mutate=["src/parser.ts", "src/lexer.ts", "src/eval.ts", "src/format.ts"], difficulty=4, tags=["parser", "query-language", "search"],
    verify=TS_VERIFY,
    probe_import="const { tokenize } = require('./build/src/lexer');\nconst { parse } = require('./build/src/parser');\nconst { matches, filter } = require('./build/src/eval');\nconst { format } = require('./build/src/format');",
    probes=[
        "tokenize('a (b|c)  -d').map((t) => t.type + t.pos)",
        "tokenize('a-b').length",
        'tokenize(\'"two words"x\').map((t) => t.text)',
        "tokenize('a -')",
        "parse('a b | c')",
        "parse('a | b c')",
        "parse('(a)')",
        "parse('a (b c)')",
        "parse('--a')",
        "parse('-(a | b)')",
        "parse('rating>=-2.5')",
        "parse('a:b:c')",
        "parse('')",
        "parse('a |')",
        "parse('rating>=high')",
        "parse('(a))')",
        "filter('sun*', [{ tags: ['Sunset'] }, { tags: ['sun'] }, { tags: ['moon'] }])",
        'filter(\'"big cat"\', [{ tags: [\'Big Cat\'] }, { tags: [\'big\'] }])',
        "filter('beach (sunset | sunrise) -blurry', [{ tags: ['beach', 'sunset'] }, { tags: ['beach', 'sunrise', 'blurry'] }, { tags: ['sunset'] }])",
        "filter('-(beach | city)', [{ tags: ['beach'] }, { tags: ['city'] }, { tags: ['farm'] }, { tags: [] }])",
        "filter('camera:nikon*', [{ tags: [], fields: { camera: 'Nikon D3' } }, { tags: [], fields: { camera: 'Pixel 7' } }])",
        "filter('rating>4.5', [{ tags: [], fields: { rating: 5 } }, { tags: [], fields: { rating: 4.5 } }, { tags: [], fields: { rating: '4.6' } }])",
        "filter('rating<=3', [{ tags: [], fields: { rating: 2 } }, { tags: [], fields: { rating: '3' } }, { tags: [], fields: { rating: 4 } }, { tags: [] }])",
        "filter('-year>=2021', [{ tags: [], fields: { year: 2020 } }, { tags: [], fields: { year: '2022' } }, { tags: [] }])",
        "format(parse('a (b|c)'))",
        "format(parse('-(a b)'))",
        "format(parse('a|(b|c)'))",
        'format(parse(\'"say \\\\"hi\\\\""\'))',
        "format(parse('a (b c)'))",
    ],
)

register_libs([LIB], n=8)
