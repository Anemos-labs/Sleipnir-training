"""Identifier case conversion (typescript): bugs injected into a word splitter and style converter."""
from fx import Lib, dd
from generators.fix._lang2 import PACKAGE_JSON, TS_NODE_SHIM, TS_VERIFY, TSCONFIG, register_libs

README = dd(r'''
    # wordshape

    Identifier case conversion for a code generator that writes the same schema as SQL columns, JSON keys and class names.
    TypeScript, no dependencies. `import { splitWords, convert, STYLES } from './src/words'`, `import { convertKeys } from './src/keys'`.

    ## Words

    `splitWords(id)` cuts an identifier into words, keeping the letters as they are written:

    * Only the ASCII letters and digits belong to words. Every other character (underscore, hyphen, space, dot, a letter with an
      accent, ...) is a separator; runs of separators count as one and leading or trailing ones are ignored.
    * A new word starts at an upper-case letter that follows a lower-case letter or a digit: `fooBar` gives `foo`, `Bar`; `v2Api`
      gives `v2`, `Api`.
    * In a run of upper-case letters that is followed by a lower-case letter, the last upper-case letter starts a new word:
      `HTTPServer` gives `HTTP`, `Server`; `parseHTMLString` gives `parse`, `HTML`, `String`.
    * Digits stay with the letters before them, and lower-case letters after digits stay too: `base64Encode` gives `base64`,
      `Encode`; `x2y` is one word; `2fast` is one word; `HTTP2Server` gives `HTTP2`, `Server`.

    ## Styles

    `STYLES` is `['snake', 'kebab', 'screaming', 'camel', 'pascal', 'title']`. `convert(id, style)` writes the words of `id` in a
    style (`Error` for a style that is not in the list); an identifier without any word gives an empty string.

    | style | `parseHTMLString` becomes |
    |---|---|
    | `snake` | `parse_html_string` |
    | `kebab` | `parse-html-string` |
    | `screaming` | `PARSE_HTML_STRING` |
    | `camel` | `parseHtmlString` |
    | `pascal` | `ParseHtmlString` |
    | `title` | `Parse Html String` |

    In `camel`, `pascal` and `title` every word is written with a capital first letter and lower-case rest (so `HTTP` becomes
    `Http`), except the first word of `camel`, which is all lower-case. Digits are not changed. `toSnake`, `toKebab`, `toScreaming`,
    `toCamel`, `toPascal` and `toTitle` are shortcuts for `convert` with that style.

    ## `convertKeys(value, style)` (`src/keys.ts`)

    Returns a copy of a JSON-like value in which the keys of all plain objects (at any depth, also inside arrays) are converted
    with `convert`. Arrays keep their order, other values (strings, numbers, booleans, `null`) are returned as they are, and the
    input is not modified. The key order of an object is kept. If two keys of one object convert to the same key, or a key
    converts to an empty string, it is an `Error`.
''')

WORDS = dd(r'''
    export type Style = "snake" | "kebab" | "screaming" | "camel" | "pascal" | "title";

    export const STYLES: Style[] = ["snake", "kebab", "screaming", "camel", "pascal", "title"];

    const isUpper = (c: string): boolean => c >= "A" && c <= "Z";
    const isLower = (c: string): boolean => c >= "a" && c <= "z";
    const isDigit = (c: string): boolean => c >= "0" && c <= "9";

    export function splitWords(id: string): string[] {
      const words: string[] = [];
      let current = "";
      for (let i = 0; i < id.length; i++) {
        const c = id[i];
        if (!isUpper(c) && !isLower(c) && !isDigit(c)) {
          if (current !== "") {
            words.push(current);
            current = "";
          }
          continue;
        }
        if (current !== "" && isUpper(c)) {
          const prev = id[i - 1];
          const next = id[i + 1];
          if (isLower(prev) || isDigit(prev)) {
            words.push(current);
            current = "";
          } else if (isUpper(prev) && next !== undefined && isLower(next)) {
            words.push(current);
            current = "";
          }
        }
        current += c;
      }
      if (current !== "") words.push(current);
      return words;
    }

    function capital(word: string): string {
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    }

    export function convert(id: string, style: Style): string {
      const words = splitWords(id);
      switch (style) {
        case "snake":
          return words.map((w) => w.toLowerCase()).join("_");
        case "kebab":
          return words.map((w) => w.toLowerCase()).join("-");
        case "screaming":
          return words.map((w) => w.toUpperCase()).join("_");
        case "camel":
          return words.map((w, i) => (i === 0 ? w.toLowerCase() : capital(w))).join("");
        case "pascal":
          return words.map(capital).join("");
        case "title":
          return words.map(capital).join(" ");
        default:
          throw new Error(`unknown style: ${String(style)}`);
      }
    }

    export const toSnake = (id: string): string => convert(id, "snake");
    export const toKebab = (id: string): string => convert(id, "kebab");
    export const toScreaming = (id: string): string => convert(id, "screaming");
    export const toCamel = (id: string): string => convert(id, "camel");
    export const toPascal = (id: string): string => convert(id, "pascal");
    export const toTitle = (id: string): string => convert(id, "title");
''')

KEYS = dd(r'''
    import { Style, convert } from "./words";

    export function convertKeys(value: unknown, style: Style): unknown {
      if (Array.isArray(value)) return value.map((item) => convertKeys(item, style));
      if (value !== null && typeof value === "object") {
        const out: Record<string, unknown> = {};
        for (const [key, inner] of Object.entries(value as Record<string, unknown>)) {
          const name = convert(key, style);
          if (name === "") throw new Error(`key ${JSON.stringify(key)} has no words`);
          if (Object.prototype.hasOwnProperty.call(out, name)) throw new Error(`two keys become ${name}`);
          out[name] = convertKeys(inner, style);
        }
        return out;
      }
      return value;
    }
''')

VISIBLE = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { splitWords, toSnake } from "../src/words";

    test("splits at case changes", () => {
      assert.deepEqual(splitWords("fooBar"), ["foo", "Bar"]);
    });

    test("snake case", () => {
      assert.equal(toSnake("parseHTMLString"), "parse_html_string");
    });
''')

HIDDEN = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { STYLES, Style, convert, splitWords, toCamel, toKebab, toPascal, toScreaming, toSnake, toTitle } from "../src/words";
    import { convertKeys } from "../src/keys";

      test("splitWords", () => {
        assert.deepEqual(splitWords("fooBar"), ["foo", "Bar"]);
        assert.deepEqual(splitWords("FooBar"), ["Foo", "Bar"]);
        assert.deepEqual(splitWords("foo_bar"), ["foo", "bar"]);
        assert.deepEqual(splitWords("foo-bar"), ["foo", "bar"]);
        assert.deepEqual(splitWords("foo bar"), ["foo", "bar"]);
        assert.deepEqual(splitWords("HTTPServer"), ["HTTP", "Server"]);
        assert.deepEqual(splitWords("parseHTMLString"), ["parse", "HTML", "String"]);
        assert.deepEqual(splitWords("getHTTPResponseCode"), ["get", "HTTP", "Response", "Code"]);
        assert.deepEqual(splitWords("v2Api"), ["v2", "Api"]);
        assert.deepEqual(splitWords("ID3Tag"), ["ID3", "Tag"]);
        assert.deepEqual(splitWords("HTTP2Server"), ["HTTP2", "Server"]);
        assert.deepEqual(splitWords("base64Encode"), ["base64", "Encode"]);
        assert.deepEqual(splitWords("base64"), ["base64"]);
        assert.deepEqual(splitWords("x2y"), ["x2y"]);
        assert.deepEqual(splitWords("2fast"), ["2fast"]);
        assert.deepEqual(splitWords("A"), ["A"]);
        assert.deepEqual(splitWords("a"), ["a"]);
        assert.deepEqual(splitWords("AB"), ["AB"]);
        assert.deepEqual(splitWords("ABc"), ["A", "Bc"]);
        assert.deepEqual(splitWords("aBC"), ["a", "BC"]);
        assert.deepEqual(splitWords("ABCd"), ["AB", "Cd"]);
        assert.deepEqual(splitWords("XMLHttpRequest"), ["XML", "Http", "Request"]);
        assert.deepEqual(splitWords("iOS"), ["i", "OS"]);
        assert.deepEqual(splitWords("iPhone12Pro"), ["i", "Phone12", "Pro"]);
        assert.deepEqual(splitWords("foo__bar"), ["foo", "bar"]);
        assert.deepEqual(splitWords("__init__"), ["init"]);
        assert.deepEqual(splitWords("--flag-name"), ["flag", "name"]);
        assert.deepEqual(splitWords(" spaced  out "), ["spaced", "out"]);
        assert.deepEqual(splitWords("foo.bar/baz"), ["foo", "bar", "baz"]);
        assert.deepEqual(splitWords("SCREAMING_SNAKE_CASE"), ["SCREAMING", "SNAKE", "CASE"]);
        assert.deepEqual(splitWords("Mixed_Case-and Spaces"), ["Mixed", "Case", "and", "Spaces"]);
        assert.deepEqual(splitWords(""), []);
        assert.deepEqual(splitWords("___"), []);
        assert.deepEqual(splitWords("na\u00efveCase"), ["na", "ve", "Case"]);
        assert.deepEqual(splitWords("caf\u00e9"), ["caf"]);
        assert.deepEqual(splitWords("user2fa"), ["user2fa"]);
        assert.deepEqual(splitWords("OAuth2Token"), ["O", "Auth2", "Token"]);
        assert.deepEqual(splitWords("a1B2c3"), ["a1", "B2c3"]);
        assert.deepEqual(splitWords("HTML"), ["HTML"]);
        assert.deepEqual(splitWords("HTMLParser"), ["HTML", "Parser"]);
        assert.deepEqual(splitWords("parseHTML"), ["parse", "HTML"]);
        assert.deepEqual(splitWords("42"), ["42"]);
        assert.deepEqual(splitWords("4x4Grid"), ["4x4", "Grid"]);
        assert.deepEqual(splitWords("tab\tseparated\nlines"), ["tab", "separated", "lines"]);
        assert.deepEqual(splitWords("snake_Case_Mixed"), ["snake", "Case", "Mixed"]);
        assert.deepEqual(splitWords("lowerUPPERlower"), ["lower", "UPPE", "Rlower"]);
        assert.deepEqual(splitWords("TheQuickBrownFox"), ["The", "Quick", "Brown", "Fox"]);
        assert.deepEqual(splitWords("the-quick_brown fox"), ["the", "quick", "brown", "fox"]);
        assert.deepEqual(splitWords("v10Api"), ["v10", "Api"]);
        assert.deepEqual(splitWords("x0y"), ["x0y"]);
        assert.deepEqual(splitWords("a0B"), ["a0", "B"]);
        assert.deepEqual(splitWords("ID9Tag"), ["ID9", "Tag"]);
        assert.deepEqual(splitWords("HTTP9Server"), ["HTTP9", "Server"]);
        assert.deepEqual(splitWords("09abc"), ["09abc"]);
        assert.deepEqual(splitWords("item9"), ["item9"]);
        assert.deepEqual(splitWords("item9Count"), ["item9", "Count"]);
        assert.deepEqual(splitWords("A0"), ["A0"]);
        assert.deepEqual(splitWords("Z9a"), ["Z9a"]);
      });

      test("convert to snake", () => {
        assert.equal(convert("fooBar", "snake"), "foo_bar");
        assert.equal(convert("FooBar", "snake"), "foo_bar");
        assert.equal(convert("foo_bar", "snake"), "foo_bar");
        assert.equal(convert("foo-bar", "snake"), "foo_bar");
        assert.equal(convert("foo bar", "snake"), "foo_bar");
        assert.equal(convert("HTTPServer", "snake"), "http_server");
        assert.equal(convert("parseHTMLString", "snake"), "parse_html_string");
        assert.equal(convert("getHTTPResponseCode", "snake"), "get_http_response_code");
        assert.equal(convert("v2Api", "snake"), "v2_api");
        assert.equal(convert("ID3Tag", "snake"), "id3_tag");
        assert.equal(convert("HTTP2Server", "snake"), "http2_server");
        assert.equal(convert("base64Encode", "snake"), "base64_encode");
        assert.equal(convert("base64", "snake"), "base64");
        assert.equal(convert("x2y", "snake"), "x2y");
        assert.equal(convert("2fast", "snake"), "2fast");
        assert.equal(convert("A", "snake"), "a");
        assert.equal(convert("a", "snake"), "a");
        assert.equal(convert("AB", "snake"), "ab");
        assert.equal(convert("ABc", "snake"), "a_bc");
        assert.equal(convert("aBC", "snake"), "a_bc");
        assert.equal(convert("ABCd", "snake"), "ab_cd");
        assert.equal(convert("XMLHttpRequest", "snake"), "xml_http_request");
        assert.equal(convert("iOS", "snake"), "i_os");
        assert.equal(convert("iPhone12Pro", "snake"), "i_phone12_pro");
        assert.equal(convert("foo__bar", "snake"), "foo_bar");
        assert.equal(convert("__init__", "snake"), "init");
        assert.equal(convert("--flag-name", "snake"), "flag_name");
        assert.equal(convert(" spaced  out ", "snake"), "spaced_out");
        assert.equal(convert("foo.bar/baz", "snake"), "foo_bar_baz");
        assert.equal(convert("SCREAMING_SNAKE_CASE", "snake"), "screaming_snake_case");
        assert.equal(convert("Mixed_Case-and Spaces", "snake"), "mixed_case_and_spaces");
        assert.equal(convert("", "snake"), "");
        assert.equal(convert("___", "snake"), "");
        assert.equal(convert("na\u00efveCase", "snake"), "na_ve_case");
        assert.equal(convert("caf\u00e9", "snake"), "caf");
        assert.equal(convert("user2fa", "snake"), "user2fa");
        assert.equal(convert("OAuth2Token", "snake"), "o_auth2_token");
        assert.equal(convert("a1B2c3", "snake"), "a1_b2c3");
        assert.equal(convert("HTML", "snake"), "html");
        assert.equal(convert("HTMLParser", "snake"), "html_parser");
        assert.equal(convert("parseHTML", "snake"), "parse_html");
        assert.equal(convert("42", "snake"), "42");
        assert.equal(convert("4x4Grid", "snake"), "4x4_grid");
        assert.equal(convert("tab\tseparated\nlines", "snake"), "tab_separated_lines");
        assert.equal(convert("snake_Case_Mixed", "snake"), "snake_case_mixed");
        assert.equal(convert("lowerUPPERlower", "snake"), "lower_uppe_rlower");
        assert.equal(convert("TheQuickBrownFox", "snake"), "the_quick_brown_fox");
        assert.equal(convert("the-quick_brown fox", "snake"), "the_quick_brown_fox");
        assert.equal(convert("v10Api", "snake"), "v10_api");
        assert.equal(convert("x0y", "snake"), "x0y");
        assert.equal(convert("a0B", "snake"), "a0_b");
        assert.equal(convert("ID9Tag", "snake"), "id9_tag");
        assert.equal(convert("HTTP9Server", "snake"), "http9_server");
        assert.equal(convert("09abc", "snake"), "09abc");
        assert.equal(convert("item9", "snake"), "item9");
        assert.equal(convert("item9Count", "snake"), "item9_count");
        assert.equal(convert("A0", "snake"), "a0");
        assert.equal(convert("Z9a", "snake"), "z9a");
      });

      test("convert to kebab", () => {
        assert.equal(convert("fooBar", "kebab"), "foo-bar");
        assert.equal(convert("FooBar", "kebab"), "foo-bar");
        assert.equal(convert("foo_bar", "kebab"), "foo-bar");
        assert.equal(convert("foo-bar", "kebab"), "foo-bar");
        assert.equal(convert("foo bar", "kebab"), "foo-bar");
        assert.equal(convert("HTTPServer", "kebab"), "http-server");
        assert.equal(convert("parseHTMLString", "kebab"), "parse-html-string");
        assert.equal(convert("getHTTPResponseCode", "kebab"), "get-http-response-code");
        assert.equal(convert("v2Api", "kebab"), "v2-api");
        assert.equal(convert("ID3Tag", "kebab"), "id3-tag");
        assert.equal(convert("HTTP2Server", "kebab"), "http2-server");
        assert.equal(convert("base64Encode", "kebab"), "base64-encode");
        assert.equal(convert("base64", "kebab"), "base64");
        assert.equal(convert("x2y", "kebab"), "x2y");
        assert.equal(convert("2fast", "kebab"), "2fast");
        assert.equal(convert("A", "kebab"), "a");
        assert.equal(convert("a", "kebab"), "a");
        assert.equal(convert("AB", "kebab"), "ab");
        assert.equal(convert("ABc", "kebab"), "a-bc");
        assert.equal(convert("aBC", "kebab"), "a-bc");
        assert.equal(convert("ABCd", "kebab"), "ab-cd");
        assert.equal(convert("XMLHttpRequest", "kebab"), "xml-http-request");
        assert.equal(convert("iOS", "kebab"), "i-os");
        assert.equal(convert("iPhone12Pro", "kebab"), "i-phone12-pro");
        assert.equal(convert("foo__bar", "kebab"), "foo-bar");
        assert.equal(convert("__init__", "kebab"), "init");
        assert.equal(convert("--flag-name", "kebab"), "flag-name");
        assert.equal(convert(" spaced  out ", "kebab"), "spaced-out");
        assert.equal(convert("foo.bar/baz", "kebab"), "foo-bar-baz");
        assert.equal(convert("SCREAMING_SNAKE_CASE", "kebab"), "screaming-snake-case");
        assert.equal(convert("Mixed_Case-and Spaces", "kebab"), "mixed-case-and-spaces");
        assert.equal(convert("", "kebab"), "");
        assert.equal(convert("___", "kebab"), "");
        assert.equal(convert("na\u00efveCase", "kebab"), "na-ve-case");
        assert.equal(convert("caf\u00e9", "kebab"), "caf");
        assert.equal(convert("user2fa", "kebab"), "user2fa");
        assert.equal(convert("OAuth2Token", "kebab"), "o-auth2-token");
        assert.equal(convert("a1B2c3", "kebab"), "a1-b2c3");
        assert.equal(convert("HTML", "kebab"), "html");
        assert.equal(convert("HTMLParser", "kebab"), "html-parser");
        assert.equal(convert("parseHTML", "kebab"), "parse-html");
        assert.equal(convert("42", "kebab"), "42");
        assert.equal(convert("4x4Grid", "kebab"), "4x4-grid");
        assert.equal(convert("tab\tseparated\nlines", "kebab"), "tab-separated-lines");
        assert.equal(convert("snake_Case_Mixed", "kebab"), "snake-case-mixed");
        assert.equal(convert("lowerUPPERlower", "kebab"), "lower-uppe-rlower");
        assert.equal(convert("TheQuickBrownFox", "kebab"), "the-quick-brown-fox");
        assert.equal(convert("the-quick_brown fox", "kebab"), "the-quick-brown-fox");
        assert.equal(convert("v10Api", "kebab"), "v10-api");
        assert.equal(convert("x0y", "kebab"), "x0y");
        assert.equal(convert("a0B", "kebab"), "a0-b");
        assert.equal(convert("ID9Tag", "kebab"), "id9-tag");
        assert.equal(convert("HTTP9Server", "kebab"), "http9-server");
        assert.equal(convert("09abc", "kebab"), "09abc");
        assert.equal(convert("item9", "kebab"), "item9");
        assert.equal(convert("item9Count", "kebab"), "item9-count");
        assert.equal(convert("A0", "kebab"), "a0");
        assert.equal(convert("Z9a", "kebab"), "z9a");
      });

      test("convert to screaming", () => {
        assert.equal(convert("fooBar", "screaming"), "FOO_BAR");
        assert.equal(convert("FooBar", "screaming"), "FOO_BAR");
        assert.equal(convert("foo_bar", "screaming"), "FOO_BAR");
        assert.equal(convert("foo-bar", "screaming"), "FOO_BAR");
        assert.equal(convert("foo bar", "screaming"), "FOO_BAR");
        assert.equal(convert("HTTPServer", "screaming"), "HTTP_SERVER");
        assert.equal(convert("parseHTMLString", "screaming"), "PARSE_HTML_STRING");
        assert.equal(convert("getHTTPResponseCode", "screaming"), "GET_HTTP_RESPONSE_CODE");
        assert.equal(convert("v2Api", "screaming"), "V2_API");
        assert.equal(convert("ID3Tag", "screaming"), "ID3_TAG");
        assert.equal(convert("HTTP2Server", "screaming"), "HTTP2_SERVER");
        assert.equal(convert("base64Encode", "screaming"), "BASE64_ENCODE");
        assert.equal(convert("base64", "screaming"), "BASE64");
        assert.equal(convert("x2y", "screaming"), "X2Y");
        assert.equal(convert("2fast", "screaming"), "2FAST");
        assert.equal(convert("A", "screaming"), "A");
        assert.equal(convert("a", "screaming"), "A");
        assert.equal(convert("AB", "screaming"), "AB");
        assert.equal(convert("ABc", "screaming"), "A_BC");
        assert.equal(convert("aBC", "screaming"), "A_BC");
        assert.equal(convert("ABCd", "screaming"), "AB_CD");
        assert.equal(convert("XMLHttpRequest", "screaming"), "XML_HTTP_REQUEST");
        assert.equal(convert("iOS", "screaming"), "I_OS");
        assert.equal(convert("iPhone12Pro", "screaming"), "I_PHONE12_PRO");
        assert.equal(convert("foo__bar", "screaming"), "FOO_BAR");
        assert.equal(convert("__init__", "screaming"), "INIT");
        assert.equal(convert("--flag-name", "screaming"), "FLAG_NAME");
        assert.equal(convert(" spaced  out ", "screaming"), "SPACED_OUT");
        assert.equal(convert("foo.bar/baz", "screaming"), "FOO_BAR_BAZ");
        assert.equal(convert("SCREAMING_SNAKE_CASE", "screaming"), "SCREAMING_SNAKE_CASE");
        assert.equal(convert("Mixed_Case-and Spaces", "screaming"), "MIXED_CASE_AND_SPACES");
        assert.equal(convert("", "screaming"), "");
        assert.equal(convert("___", "screaming"), "");
        assert.equal(convert("na\u00efveCase", "screaming"), "NA_VE_CASE");
        assert.equal(convert("caf\u00e9", "screaming"), "CAF");
        assert.equal(convert("user2fa", "screaming"), "USER2FA");
        assert.equal(convert("OAuth2Token", "screaming"), "O_AUTH2_TOKEN");
        assert.equal(convert("a1B2c3", "screaming"), "A1_B2C3");
        assert.equal(convert("HTML", "screaming"), "HTML");
        assert.equal(convert("HTMLParser", "screaming"), "HTML_PARSER");
        assert.equal(convert("parseHTML", "screaming"), "PARSE_HTML");
        assert.equal(convert("42", "screaming"), "42");
        assert.equal(convert("4x4Grid", "screaming"), "4X4_GRID");
        assert.equal(convert("tab\tseparated\nlines", "screaming"), "TAB_SEPARATED_LINES");
        assert.equal(convert("snake_Case_Mixed", "screaming"), "SNAKE_CASE_MIXED");
        assert.equal(convert("lowerUPPERlower", "screaming"), "LOWER_UPPE_RLOWER");
        assert.equal(convert("TheQuickBrownFox", "screaming"), "THE_QUICK_BROWN_FOX");
        assert.equal(convert("the-quick_brown fox", "screaming"), "THE_QUICK_BROWN_FOX");
        assert.equal(convert("v10Api", "screaming"), "V10_API");
        assert.equal(convert("x0y", "screaming"), "X0Y");
        assert.equal(convert("a0B", "screaming"), "A0_B");
        assert.equal(convert("ID9Tag", "screaming"), "ID9_TAG");
        assert.equal(convert("HTTP9Server", "screaming"), "HTTP9_SERVER");
        assert.equal(convert("09abc", "screaming"), "09ABC");
        assert.equal(convert("item9", "screaming"), "ITEM9");
        assert.equal(convert("item9Count", "screaming"), "ITEM9_COUNT");
        assert.equal(convert("A0", "screaming"), "A0");
        assert.equal(convert("Z9a", "screaming"), "Z9A");
      });

      test("convert to camel", () => {
        assert.equal(convert("fooBar", "camel"), "fooBar");
        assert.equal(convert("FooBar", "camel"), "fooBar");
        assert.equal(convert("foo_bar", "camel"), "fooBar");
        assert.equal(convert("foo-bar", "camel"), "fooBar");
        assert.equal(convert("foo bar", "camel"), "fooBar");
        assert.equal(convert("HTTPServer", "camel"), "httpServer");
        assert.equal(convert("parseHTMLString", "camel"), "parseHtmlString");
        assert.equal(convert("getHTTPResponseCode", "camel"), "getHttpResponseCode");
        assert.equal(convert("v2Api", "camel"), "v2Api");
        assert.equal(convert("ID3Tag", "camel"), "id3Tag");
        assert.equal(convert("HTTP2Server", "camel"), "http2Server");
        assert.equal(convert("base64Encode", "camel"), "base64Encode");
        assert.equal(convert("base64", "camel"), "base64");
        assert.equal(convert("x2y", "camel"), "x2y");
        assert.equal(convert("2fast", "camel"), "2fast");
        assert.equal(convert("A", "camel"), "a");
        assert.equal(convert("a", "camel"), "a");
        assert.equal(convert("AB", "camel"), "ab");
        assert.equal(convert("ABc", "camel"), "aBc");
        assert.equal(convert("aBC", "camel"), "aBc");
        assert.equal(convert("ABCd", "camel"), "abCd");
        assert.equal(convert("XMLHttpRequest", "camel"), "xmlHttpRequest");
        assert.equal(convert("iOS", "camel"), "iOs");
        assert.equal(convert("iPhone12Pro", "camel"), "iPhone12Pro");
        assert.equal(convert("foo__bar", "camel"), "fooBar");
        assert.equal(convert("__init__", "camel"), "init");
        assert.equal(convert("--flag-name", "camel"), "flagName");
        assert.equal(convert(" spaced  out ", "camel"), "spacedOut");
        assert.equal(convert("foo.bar/baz", "camel"), "fooBarBaz");
        assert.equal(convert("SCREAMING_SNAKE_CASE", "camel"), "screamingSnakeCase");
        assert.equal(convert("Mixed_Case-and Spaces", "camel"), "mixedCaseAndSpaces");
        assert.equal(convert("", "camel"), "");
        assert.equal(convert("___", "camel"), "");
        assert.equal(convert("na\u00efveCase", "camel"), "naVeCase");
        assert.equal(convert("caf\u00e9", "camel"), "caf");
        assert.equal(convert("user2fa", "camel"), "user2fa");
        assert.equal(convert("OAuth2Token", "camel"), "oAuth2Token");
        assert.equal(convert("a1B2c3", "camel"), "a1B2c3");
        assert.equal(convert("HTML", "camel"), "html");
        assert.equal(convert("HTMLParser", "camel"), "htmlParser");
        assert.equal(convert("parseHTML", "camel"), "parseHtml");
        assert.equal(convert("42", "camel"), "42");
        assert.equal(convert("4x4Grid", "camel"), "4x4Grid");
        assert.equal(convert("tab\tseparated\nlines", "camel"), "tabSeparatedLines");
        assert.equal(convert("snake_Case_Mixed", "camel"), "snakeCaseMixed");
        assert.equal(convert("lowerUPPERlower", "camel"), "lowerUppeRlower");
        assert.equal(convert("TheQuickBrownFox", "camel"), "theQuickBrownFox");
        assert.equal(convert("the-quick_brown fox", "camel"), "theQuickBrownFox");
        assert.equal(convert("v10Api", "camel"), "v10Api");
        assert.equal(convert("x0y", "camel"), "x0y");
        assert.equal(convert("a0B", "camel"), "a0B");
        assert.equal(convert("ID9Tag", "camel"), "id9Tag");
        assert.equal(convert("HTTP9Server", "camel"), "http9Server");
        assert.equal(convert("09abc", "camel"), "09abc");
        assert.equal(convert("item9", "camel"), "item9");
        assert.equal(convert("item9Count", "camel"), "item9Count");
        assert.equal(convert("A0", "camel"), "a0");
        assert.equal(convert("Z9a", "camel"), "z9a");
      });

      test("convert to pascal", () => {
        assert.equal(convert("fooBar", "pascal"), "FooBar");
        assert.equal(convert("FooBar", "pascal"), "FooBar");
        assert.equal(convert("foo_bar", "pascal"), "FooBar");
        assert.equal(convert("foo-bar", "pascal"), "FooBar");
        assert.equal(convert("foo bar", "pascal"), "FooBar");
        assert.equal(convert("HTTPServer", "pascal"), "HttpServer");
        assert.equal(convert("parseHTMLString", "pascal"), "ParseHtmlString");
        assert.equal(convert("getHTTPResponseCode", "pascal"), "GetHttpResponseCode");
        assert.equal(convert("v2Api", "pascal"), "V2Api");
        assert.equal(convert("ID3Tag", "pascal"), "Id3Tag");
        assert.equal(convert("HTTP2Server", "pascal"), "Http2Server");
        assert.equal(convert("base64Encode", "pascal"), "Base64Encode");
        assert.equal(convert("base64", "pascal"), "Base64");
        assert.equal(convert("x2y", "pascal"), "X2y");
        assert.equal(convert("2fast", "pascal"), "2fast");
        assert.equal(convert("A", "pascal"), "A");
        assert.equal(convert("a", "pascal"), "A");
        assert.equal(convert("AB", "pascal"), "Ab");
        assert.equal(convert("ABc", "pascal"), "ABc");
        assert.equal(convert("aBC", "pascal"), "ABc");
        assert.equal(convert("ABCd", "pascal"), "AbCd");
        assert.equal(convert("XMLHttpRequest", "pascal"), "XmlHttpRequest");
        assert.equal(convert("iOS", "pascal"), "IOs");
        assert.equal(convert("iPhone12Pro", "pascal"), "IPhone12Pro");
        assert.equal(convert("foo__bar", "pascal"), "FooBar");
        assert.equal(convert("__init__", "pascal"), "Init");
        assert.equal(convert("--flag-name", "pascal"), "FlagName");
        assert.equal(convert(" spaced  out ", "pascal"), "SpacedOut");
        assert.equal(convert("foo.bar/baz", "pascal"), "FooBarBaz");
        assert.equal(convert("SCREAMING_SNAKE_CASE", "pascal"), "ScreamingSnakeCase");
        assert.equal(convert("Mixed_Case-and Spaces", "pascal"), "MixedCaseAndSpaces");
        assert.equal(convert("", "pascal"), "");
        assert.equal(convert("___", "pascal"), "");
        assert.equal(convert("na\u00efveCase", "pascal"), "NaVeCase");
        assert.equal(convert("caf\u00e9", "pascal"), "Caf");
        assert.equal(convert("user2fa", "pascal"), "User2fa");
        assert.equal(convert("OAuth2Token", "pascal"), "OAuth2Token");
        assert.equal(convert("a1B2c3", "pascal"), "A1B2c3");
        assert.equal(convert("HTML", "pascal"), "Html");
        assert.equal(convert("HTMLParser", "pascal"), "HtmlParser");
        assert.equal(convert("parseHTML", "pascal"), "ParseHtml");
        assert.equal(convert("42", "pascal"), "42");
        assert.equal(convert("4x4Grid", "pascal"), "4x4Grid");
        assert.equal(convert("tab\tseparated\nlines", "pascal"), "TabSeparatedLines");
        assert.equal(convert("snake_Case_Mixed", "pascal"), "SnakeCaseMixed");
        assert.equal(convert("lowerUPPERlower", "pascal"), "LowerUppeRlower");
        assert.equal(convert("TheQuickBrownFox", "pascal"), "TheQuickBrownFox");
        assert.equal(convert("the-quick_brown fox", "pascal"), "TheQuickBrownFox");
        assert.equal(convert("v10Api", "pascal"), "V10Api");
        assert.equal(convert("x0y", "pascal"), "X0y");
        assert.equal(convert("a0B", "pascal"), "A0B");
        assert.equal(convert("ID9Tag", "pascal"), "Id9Tag");
        assert.equal(convert("HTTP9Server", "pascal"), "Http9Server");
        assert.equal(convert("09abc", "pascal"), "09abc");
        assert.equal(convert("item9", "pascal"), "Item9");
        assert.equal(convert("item9Count", "pascal"), "Item9Count");
        assert.equal(convert("A0", "pascal"), "A0");
        assert.equal(convert("Z9a", "pascal"), "Z9a");
      });

      test("convert to title", () => {
        assert.equal(convert("fooBar", "title"), "Foo Bar");
        assert.equal(convert("FooBar", "title"), "Foo Bar");
        assert.equal(convert("foo_bar", "title"), "Foo Bar");
        assert.equal(convert("foo-bar", "title"), "Foo Bar");
        assert.equal(convert("foo bar", "title"), "Foo Bar");
        assert.equal(convert("HTTPServer", "title"), "Http Server");
        assert.equal(convert("parseHTMLString", "title"), "Parse Html String");
        assert.equal(convert("getHTTPResponseCode", "title"), "Get Http Response Code");
        assert.equal(convert("v2Api", "title"), "V2 Api");
        assert.equal(convert("ID3Tag", "title"), "Id3 Tag");
        assert.equal(convert("HTTP2Server", "title"), "Http2 Server");
        assert.equal(convert("base64Encode", "title"), "Base64 Encode");
        assert.equal(convert("base64", "title"), "Base64");
        assert.equal(convert("x2y", "title"), "X2y");
        assert.equal(convert("2fast", "title"), "2fast");
        assert.equal(convert("A", "title"), "A");
        assert.equal(convert("a", "title"), "A");
        assert.equal(convert("AB", "title"), "Ab");
        assert.equal(convert("ABc", "title"), "A Bc");
        assert.equal(convert("aBC", "title"), "A Bc");
        assert.equal(convert("ABCd", "title"), "Ab Cd");
        assert.equal(convert("XMLHttpRequest", "title"), "Xml Http Request");
        assert.equal(convert("iOS", "title"), "I Os");
        assert.equal(convert("iPhone12Pro", "title"), "I Phone12 Pro");
        assert.equal(convert("foo__bar", "title"), "Foo Bar");
        assert.equal(convert("__init__", "title"), "Init");
        assert.equal(convert("--flag-name", "title"), "Flag Name");
        assert.equal(convert(" spaced  out ", "title"), "Spaced Out");
        assert.equal(convert("foo.bar/baz", "title"), "Foo Bar Baz");
        assert.equal(convert("SCREAMING_SNAKE_CASE", "title"), "Screaming Snake Case");
        assert.equal(convert("Mixed_Case-and Spaces", "title"), "Mixed Case And Spaces");
        assert.equal(convert("", "title"), "");
        assert.equal(convert("___", "title"), "");
        assert.equal(convert("na\u00efveCase", "title"), "Na Ve Case");
        assert.equal(convert("caf\u00e9", "title"), "Caf");
        assert.equal(convert("user2fa", "title"), "User2fa");
        assert.equal(convert("OAuth2Token", "title"), "O Auth2 Token");
        assert.equal(convert("a1B2c3", "title"), "A1 B2c3");
        assert.equal(convert("HTML", "title"), "Html");
        assert.equal(convert("HTMLParser", "title"), "Html Parser");
        assert.equal(convert("parseHTML", "title"), "Parse Html");
        assert.equal(convert("42", "title"), "42");
        assert.equal(convert("4x4Grid", "title"), "4x4 Grid");
        assert.equal(convert("tab\tseparated\nlines", "title"), "Tab Separated Lines");
        assert.equal(convert("snake_Case_Mixed", "title"), "Snake Case Mixed");
        assert.equal(convert("lowerUPPERlower", "title"), "Lower Uppe Rlower");
        assert.equal(convert("TheQuickBrownFox", "title"), "The Quick Brown Fox");
        assert.equal(convert("the-quick_brown fox", "title"), "The Quick Brown Fox");
        assert.equal(convert("v10Api", "title"), "V10 Api");
        assert.equal(convert("x0y", "title"), "X0y");
        assert.equal(convert("a0B", "title"), "A0 B");
        assert.equal(convert("ID9Tag", "title"), "Id9 Tag");
        assert.equal(convert("HTTP9Server", "title"), "Http9 Server");
        assert.equal(convert("09abc", "title"), "09abc");
        assert.equal(convert("item9", "title"), "Item9");
        assert.equal(convert("item9Count", "title"), "Item9 Count");
        assert.equal(convert("A0", "title"), "A0");
        assert.equal(convert("Z9a", "title"), "Z9a");
      });

      test("shortcuts", () => {
        assert.equal(toSnake("parseHTMLString"), "parse_html_string");
        assert.equal(toKebab("parseHTMLString"), "parse-html-string");
        assert.equal(toScreaming("parseHTMLString"), "PARSE_HTML_STRING");
        assert.equal(toCamel("parse_html_string"), "parseHtmlString");
        assert.equal(toPascal("parse_html_string"), "ParseHtmlString");
        assert.equal(toTitle("parse_html_string"), "Parse Html String");
        assert.equal(toSnake("Already_Snake"), "already_snake");
        assert.equal(toCamel("X"), "x");
        assert.equal(toPascal("x"), "X");
      });

      test("STYLES and unknown styles", () => {
        assert.deepEqual(STYLES, ["snake", "kebab", "screaming", "camel", "pascal", "title"]);
        assert.throws(() => convert("fooBar", "dotted" as unknown as Style), Error);
        assert.throws(() => convert("", "nope" as unknown as Style), Error);
        assert.throws(() => convert("fooBar", "Snake" as unknown as Style), Error);
        for (const s of STYLES) assert.equal(convert("", s), "");
        for (const s of STYLES) assert.equal(convert("__", s), "");
      });

      test("convertKeys converts nested keys", () => {
        const input = { userName: "Ann", homeAddress: { streetName: "Elm", ZIPCode: 12345, geoPoint: { lat: 1.5, LNG: 2 } }, phoneNumbers: [{ phoneType: "cell", isPrimary: true }, "plain", 7, null] };
        const before = JSON.stringify(input);
        const out = convertKeys(input, "snake");
        assert.deepEqual(out, { user_name: "Ann", home_address: { street_name: "Elm", zip_code: 12345, geo_point: { lat: 1.5, lng: 2 } }, phone_numbers: [{ phone_type: "cell", is_primary: true }, "plain", 7, null] });
        assert.equal(JSON.stringify(input), before);
        assert.notEqual(out, input);
        assert.deepEqual(convertKeys({ "first-name": "A", "last name": "B" }, "camel"), { firstName: "A", lastName: "B" });
        assert.deepEqual(convertKeys({ first_name: [{ nick_name: "x" }, [{ deep_key: 1 }]] }, "pascal"), { FirstName: [{ NickName: "x" }, [{ DeepKey: 1 }]] });
        assert.deepEqual(Object.keys(convertKeys({ b_two: 1, a_one: 2, c_three: 3 }, "camel") as object), ["bTwo", "aOne", "cThree"]);
        assert.deepEqual(convertKeys({ aB: 1 }, "screaming"), { A_B: 1 });
        assert.deepEqual(convertKeys({ aB: 1 }, "title"), { "A B": 1 });
      });

      test("convertKeys leaves other values alone", () => {
        assert.equal(convertKeys("fooBar", "snake"), "fooBar");
        assert.equal(convertKeys(5, "snake"), 5);
        assert.equal(convertKeys(null, "snake"), null);
        assert.equal(convertKeys(true, "snake"), true);
        assert.deepEqual(convertKeys([], "snake"), []);
        assert.deepEqual(convertKeys({}, "snake"), {});
        assert.deepEqual(convertKeys(["aB", { cD: "eF" }], "snake"), ["aB", { c_d: "eF" }]);
        assert.deepEqual(convertKeys([[1, [2]], { xY: [{ zW: 0 }] }], "kebab"), [[1, [2]], { "x-y": [{ "z-w": 0 }] }]);
      });

      test("convertKeys rejects collisions and empty keys", () => {
        assert.throws(() => convertKeys({ fooBar: 1, foo_bar: 2 }, "snake"), Error);
        assert.throws(() => convertKeys({ a: { fooBar: 1, "foo-bar": 2 } }, "camel"), Error);
        assert.throws(() => convertKeys([{ x_y: 1, xY: 2 }], "snake"), Error);
        assert.throws(() => convertKeys({ "___": 1 }, "snake"), Error);
        assert.throws(() => convertKeys({ ok: { "": 1 } }, "snake"), Error);
        assert.deepEqual(convertKeys({ fooBar: 1, foo_baz: 2 }, "snake"), { foo_bar: 1, foo_baz: 2 });
        assert.deepEqual(convertKeys({ a: { fooBar: 1 }, b: { foo_bar: 2 } }, "snake"), { a: { foo_bar: 1 }, b: { foo_bar: 2 } });
        assert.throws(() => convertKeys({ fooBar: 1, FooBar: 2 }, "title"), Error);
        assert.deepEqual(convertKeys({ fooBar: 1, foo_baz: 2 }, "title"), { "Foo Bar": 1, "Foo Baz": 2 });
      });
''')

LIB = Lib(
    name="wordshape", lang="typescript", title="the wordshape case converter",
    blurb="The schema tool writes the same field names as SQL columns, JSON keys and class names with wordshape.",
    files={"package.json": PACKAGE_JSON % "wordshape", "tsconfig.json": TSCONFIG, "types/node-shim.d.ts": TS_NODE_SHIM,
           "src/words.ts": WORDS, "src/keys.ts": KEYS, "README.md": README, ".gitignore": "node_modules/\nbuild/\n"},
    visible_tests={"test/basic.test.ts": VISIBLE},
    hidden_tests={"test/full.test.ts": HIDDEN},
    mutate=["src/words.ts", "src/keys.ts"], difficulty=1, tags=["naming", "strings", "conversion"],
    verify=TS_VERIFY,
    probe_import="const { splitWords, convert } = require('./build/src/words');\nconst { convertKeys } = require('./build/src/keys');",
    probes=[
        "splitWords('HTTPServer')",
        "splitWords('parseHTMLString')",
        "splitWords('v2Api')",
        "splitWords('base64Encode')",
        "splitWords('x2y')",
        "splitWords('ABc')",
        "splitWords(' spaced  out ')",
        "splitWords('na\\u00efveCase')",
        "convert('parseHTMLString', 'camel')",
        "convert('parseHTMLString', 'title')",
        "convert('HTTP_server', 'pascal')",
        "convert('fooBar', 'screaming')",
        "convert('', 'snake')",
        "convert('fooBar', 'dotted')",
        "convertKeys({ userName: 'Ann', homeAddress: { ZIPCode: 1 }, tags: [{ tagName: 'x' }] }, 'snake')",
        "convertKeys({ fooBar: 1, foo_bar: 2 }, 'snake')",
        "convertKeys({ '___': 1 }, 'snake')",
    ],
)

register_libs([LIB], n=8)
