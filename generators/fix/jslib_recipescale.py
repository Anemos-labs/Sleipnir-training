"""Recipe-card amount scaling (javascript): bugs injected into a tiny quantity reader and formatter."""
from fx import Lib, dd
from generators.fix._lang2 import JS_VERIFY, PACKAGE_JSON, register_libs

README = dd(r'''
    # recipescale

    Scaling the ingredient lines of a recipe card for more or fewer servings. CommonJS: `const { parseQty, formatQty } =
    require('./src/qty')` and `const { scaleLine, scaleRecipe } = require('./src/scale')`.

    ## `src/qty.js`

    ### `parseQty(text)`

    The amount written in `text` as a number, or `null` when `text` is not exactly one amount (surrounding white space is ignored).
    An amount is any of:

    * a whole number or a decimal: `2`, `1.5`, `.5`;
    * a fraction `3/4` (a zero denominator is not an amount);
    * a mixed number with an ASCII fraction: `1 1/2` (at least one space between the parts);
    * one of the fraction glyphs `¼ ½ ¾ ⅓ ⅔ ⅛ ⅜ ⅝ ⅞`, alone (`½`) or after a whole number with or without a space (`1½`, `1 ½`).

    There are no negative amounts, no exponents and no decimal commas.

    ### `readQty(text)`

    Reads an amount at the very start of `text` (no leading white space is skipped) and returns `{ value, length }`, where `length`
    is the number of characters it used, or `null` if the text does not start with an amount. It takes the longest form that fits:
    in `1 1/2 cups` it reads `1 1/2`, in `3/4 tsp` it reads `3/4`, in `2 cups` just `2`, in `1 ½ cups` it reads `1 ½`.

    ### `formatQty(x)`

    Writes an amount for a recipe card: rounded to the nearest eighth (a tie goes up), as a whole number, a fraction in lowest terms
    or a mixed number with an ASCII fraction (`1 1/2`, `3/4`, `2`). A positive amount never prints as `0`: whatever is below one
    eighth shows as `1/8`. `formatQty(0)` is `0`. A negative number, `NaN` or an infinite number is a `RangeError`.

    ## `src/scale.js`

    ### `scaleLine(line, factor)`

    Multiplies the amount at the start of an ingredient line by `factor` (a finite number above 0, else `RangeError`) and writes it
    with `formatQty`; the rest of the line is left exactly as it was. Leading white space in the line is kept. A line that does not
    start with an amount comes back unchanged. A range of two amounts joined by a plain `-` right after the first one (`2-3 apples`,
    `1/2-3/4 tsp salt`) scales both ends and is written with a `-` between them.

    `scaleLine('1 1/2 cups flour', 2)` is `'3 cups flour'`; `scaleLine('1/2 tsp salt', 3)` is `'1 1/2 tsp salt'`;
    `scaleLine('pinch of salt', 4)` is `'pinch of salt'`.

    ### `scaleRecipe(lines, from, to)`

    The lines scaled from a recipe for `from` servings to one for `to` servings (factor `to / from`); `from` and `to` must be finite
    numbers above 0, else `RangeError`. Returns a new array.
''')

QTY = dd(r'''
    'use strict';

    const GLYPHS = {
      '¼': 0.25,
      '½': 0.5,
      '¾': 0.75,
      '⅓': 1 / 3,
      '⅔': 2 / 3,
      '⅛': 0.125,
      '⅜': 0.375,
      '⅝': 0.625,
      '⅞': 0.875,
    };
    const GLYPH_CLASS = '[¼½¾⅓⅔⅛⅜⅝⅞]';

    function readQty(text) {
      let m = /^(\d+) +(\d+)\/(\d+)(?!\d)/.exec(text);
      if (m && Number(m[3]) !== 0) {
        return { value: Number(m[1]) + Number(m[2]) / Number(m[3]), length: m[0].length };
      }
      m = new RegExp('^(\\d+) ?(' + GLYPH_CLASS + ')').exec(text);
      if (m) return { value: Number(m[1]) + GLYPHS[m[2]], length: m[0].length };
      m = /^(\d+)\/(\d+)(?!\d)/.exec(text);
      if (m && Number(m[2]) !== 0) {
        return { value: Number(m[1]) / Number(m[2]), length: m[0].length };
      }
      m = /^(\d*\.\d+|\d+)/.exec(text);
      if (m) return { value: Number(m[1]), length: m[0].length };
      m = new RegExp('^(' + GLYPH_CLASS + ')').exec(text);
      if (m) return { value: GLYPHS[m[1]], length: 1 };
      return null;
    }

    function parseQty(text) {
      const t = text.trim();
      const q = readQty(t);
      return q !== null && q.length === t.length ? q.value : null;
    }

    function formatQty(x) {
      if (typeof x !== 'number' || !(x >= 0) || !Number.isFinite(x)) {
        throw new RangeError('quantity must be a finite number, not negative');
      }
      if (x === 0) return '0';
      let eighths = Math.round(x * 8);
      if (eighths === 0) eighths = 1;
      const whole = Math.floor(eighths / 8);
      let num = eighths % 8;
      let den = 8;
      while (num > 0 && num % 2 === 0) {
        num /= 2;
        den /= 2;
      }
      if (num === 0) return String(whole);
      return whole === 0 ? num + '/' + den : whole + ' ' + num + '/' + den;
    }

    module.exports = { parseQty, readQty, formatQty };
''')

SCALE = dd(r'''
    'use strict';

    const { readQty, formatQty } = require('./qty');

    function positive(x, name) {
      if (typeof x !== 'number' || !Number.isFinite(x) || x <= 0) {
        throw new RangeError(name + ' must be a finite number above 0');
      }
    }

    function scaleLine(line, factor) {
      positive(factor, 'factor');
      const lead = /^\s*/.exec(line)[0];
      const body = line.slice(lead.length);
      const first = readQty(body);
      if (first === null) return line;
      let out = formatQty(first.value * factor);
      let used = first.length;
      if (body[used] === '-') {
        const second = readQty(body.slice(used + 1));
        if (second !== null) {
          out += '-' + formatQty(second.value * factor);
          used += 1 + second.length;
        }
      }
      return lead + out + body.slice(used);
    }

    function scaleRecipe(lines, from, to) {
      positive(from, 'from');
      positive(to, 'to');
      const factor = to / from;
      return lines.map((line) => scaleLine(line, factor));
    }

    module.exports = { scaleLine, scaleRecipe };
''')

VISIBLE = dd(r'''
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { formatQty } = require('../src/qty');
    const { scaleLine } = require('../src/scale');

    test('formatQty writes mixed numbers', () => {
      assert.equal(formatQty(1.5), '1 1/2');
      assert.equal(formatQty(2), '2');
    });

    test('scaleLine scales the leading amount', () => {
      assert.equal(scaleLine('1 1/2 cups flour', 2), '3 cups flour');
    });
''')

HIDDEN = dd(r'''
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { parseQty, readQty, formatQty } = require('../src/qty');
    const { scaleLine, scaleRecipe } = require('../src/scale');

    function near(actual, expected) {
      assert.ok(actual !== null && Math.abs(actual - expected) < 1e-9, `expected ${expected} but got ${actual}`);
    }

    function readIs(text, value, length) {
      const r = readQty(text);
      assert.ok(r !== null, `no amount read from ${JSON.stringify(text)}`);
      near(r.value, value);
      assert.equal(r.length, length);
    }

        test("parseQty reads one amount", () => {
          near(parseQty("2"), 2);
          near(parseQty("1.5"), 1.5);
          near(parseQty(".5"), 0.5);
          near(parseQty("3/4"), 0.75);
          near(parseQty("1 1/2"), 1.5);
          near(parseQty("1  1/2"), 1.5);
          near(parseQty("10 3/8"), 10.375);
          near(parseQty("\u00bd"), 0.5);
          near(parseQty("1\u00bd"), 1.5);
          near(parseQty("1 \u00bd"), 1.5);
          near(parseQty("\u00be"), 0.75);
          near(parseQty("\u2153"), 0.3333333333333333);
          near(parseQty("2\u2154"), 2.6666666666666665);
          near(parseQty("\u215b"), 0.125);
          near(parseQty("3 \u215e"), 3.875);
          near(parseQty(" 7 "), 7);
          near(parseQty("\t1/4 "), 0.25);
          near(parseQty("0"), 0);
          near(parseQty("0.25"), 0.25);
          near(parseQty("12"), 12);
          near(parseQty("007"), 7);
          near(parseQty("5/4"), 1.25);
          near(parseQty("12.75"), 12.75);
        });

        test("parseQty is null for everything else", () => {
          assert.equal(parseQty(""), null);
          assert.equal(parseQty("  "), null);
          assert.equal(parseQty("abc"), null);
          assert.equal(parseQty("2x"), null);
          assert.equal(parseQty("1/0"), null);
          assert.equal(parseQty("3/0"), null);
          assert.equal(parseQty("1 1/0"), null);
          assert.equal(parseQty("1."), null);
          assert.equal(parseQty("1,5"), null);
          assert.equal(parseQty("-1"), null);
          assert.equal(parseQty("+2"), null);
          assert.equal(parseQty("1e3"), null);
          assert.equal(parseQty("1/2/3"), null);
          assert.equal(parseQty("1 1 1/2"), null);
          assert.equal(parseQty("1  \u00bd"), null);
          assert.equal(parseQty("1\u00bd\u00bd"), null);
          assert.equal(parseQty("\u00bd \u00bd"), null);
          assert.equal(parseQty("1 / 2"), null);
          assert.equal(parseQty("1/ 2"), null);
          assert.equal(parseQty("1 /2"), null);
          assert.equal(parseQty("\u00bc1"), null);
          assert.equal(parseQty("1/2 cup"), null);
          assert.equal(parseQty("2 cups"), null);
          assert.equal(parseQty("one"), null);
          assert.equal(parseQty("."), null);
          assert.equal(parseQty("1..5"), null);
          assert.equal(parseQty("1.5.2"), null);
          assert.equal(parseQty("\u00bd\u00be"), null);
          assert.equal(parseQty("2-3"), null);
          assert.equal(parseQty("1 1/2 1/2"), null);
        });

        test("readQty takes the longest amount at the start", () => {
          readIs("1 1/2 cups", 1.5, 5);
          readIs("3/4 tsp", 0.75, 3);
          readIs("2 cups", 2, 1);
          readIs("1 \u00bd cups", 1.5, 3);
          readIs("1\u00bd cups", 1.5, 2);
          readIs("12 eggs", 12, 2);
          readIs("1 1/0 cups", 1, 1);
          readIs("3/0 x", 3, 1);
          readIs(".5 l", 0.5, 2);
          readIs("\u00be cup", 0.75, 1);
          readIs("1.25 kg", 1.25, 4);
          readIs("2 1/2-3 cups", 2.5, 5);
          readIs("4 / 5", 4, 1);
          assert.equal(readQty(" 2 cups"), null);
          assert.equal(readQty("x 2"), null);
          assert.equal(readQty(""), null);
          readIs("10 3/8x", 10.375, 6);
          readIs("1 2/34", 1.0588235294117647, 6);
          readIs("7 \u215b", 7.125, 3);
          readIs("1  1/2 pinch", 1.5, 6);
        });

        test("formatQty rounds to eighths", () => {
          assert.equal(formatQty(0), "0");
          assert.equal(formatQty(0.01), "1/8");
          assert.equal(formatQty(0.0625), "1/8");
          assert.equal(formatQty(0.0626), "1/8");
          assert.equal(formatQty(0.07), "1/8");
          assert.equal(formatQty(0.125), "1/8");
          assert.equal(formatQty(0.18), "1/8");
          assert.equal(formatQty(0.1875), "1/4");
          assert.equal(formatQty(0.2), "1/4");
          assert.equal(formatQty(0.25), "1/4");
          assert.equal(formatQty(0.3), "1/4");
          assert.equal(formatQty(0.3125), "3/8");
          assert.equal(formatQty(1 / 3), "3/8");
          assert.equal(formatQty(0.4), "3/8");
          assert.equal(formatQty(0.4375), "1/2");
          assert.equal(formatQty(0.5), "1/2");
          assert.equal(formatQty(0.56), "1/2");
          assert.equal(formatQty(0.6), "5/8");
          assert.equal(formatQty(2 / 3), "5/8");
          assert.equal(formatQty(0.7), "3/4");
          assert.equal(formatQty(0.75), "3/4");
          assert.equal(formatQty(0.8), "3/4");
          assert.equal(formatQty(0.9), "7/8");
          assert.equal(formatQty(0.9375), "1");
          assert.equal(formatQty(0.94), "1");
          assert.equal(formatQty(0.99), "1");
          assert.equal(formatQty(1), "1");
          assert.equal(formatQty(1.0625), "1 1/8");
          assert.equal(formatQty(1.1), "1 1/8");
          assert.equal(formatQty(1.5), "1 1/2");
          assert.equal(formatQty(1.9), "1 7/8");
          assert.equal(formatQty(2.9375), "3");
          assert.equal(formatQty(2.97), "3");
          assert.equal(formatQty(3.99), "4");
          assert.equal(formatQty(4), "4");
          assert.equal(formatQty(10.5), "10 1/2");
          assert.equal(formatQty(12.125), "12 1/8");
          assert.equal(formatQty(99.99), "100");
          assert.equal(formatQty(100), "100");
          assert.equal(formatQty(1234.5), "1234 1/2");
        });

        test("formatQty rejects bad numbers", () => {
          assert.throws(() => formatQty(-1), RangeError);
          assert.throws(() => formatQty(-0.01), RangeError);
          assert.throws(() => formatQty(NaN), RangeError);
          assert.throws(() => formatQty(Infinity), RangeError);
          assert.throws(() => formatQty(-Infinity), RangeError);
          assert.doesNotThrow(() => formatQty(0));
        });

        test("scaleLine", () => {
          assert.equal(scaleLine("1 1/2 cups flour", 2), "3 cups flour");
          assert.equal(scaleLine("1/2 tsp salt", 3), "1 1/2 tsp salt");
          assert.equal(scaleLine("pinch of salt", 4), "pinch of salt");
          assert.equal(scaleLine("2 eggs", 1.5), "3 eggs");
          assert.equal(scaleLine("2 eggs", 0.5), "1 eggs");
          assert.equal(scaleLine("1 egg", 0.25), "1/4 egg");
          assert.equal(scaleLine("3 apples", 0.1), "1/4 apples");
          assert.equal(scaleLine("\u00bd cup milk", 2), "1 cup milk");
          assert.equal(scaleLine("1\u00bd cups sugar", 3), "4 1/2 cups sugar");
          assert.equal(scaleLine("1 cup oil", 1), "1 cup oil");
          assert.equal(scaleLine("2-3 apples", 2), "4-6 apples");
          assert.equal(scaleLine("1/2-3/4 tsp salt", 3), "1 1/2-2 1/4 tsp salt");
          assert.equal(scaleLine("  1 1/2 cups flour", 2), "  3 cups flour");
          assert.equal(scaleLine("1 1/2 cups flour 1 cup", 2), "3 cups flour 1 cup");
          assert.equal(scaleLine("1-2", 1.5), "1 1/2-3");
          assert.equal(scaleLine("2- 3 apples", 2), "4- 3 apples");
          assert.equal(scaleLine("2 -3 apples", 2), "4 -3 apples");
          assert.equal(scaleLine("4-x apples", 2), "8-x apples");
          assert.equal(scaleLine("4- apples", 2), "8- apples");
          assert.equal(scaleLine("10 g butter", 0.25), "2 1/2 g butter");
          assert.equal(scaleLine("250 g flour", 0.5), "125 g flour");
          assert.equal(scaleLine("3/4 cup", 2), "1 1/2 cup");
          assert.equal(scaleLine("1 1/4 cups", 0.5), "5/8 cups");
          assert.equal(scaleLine("2.5 kg potatoes", 4), "10 kg potatoes");
          assert.equal(scaleLine("1 tbsp (15 ml) oil", 2), "2 tbsp (15 ml) oil");
          assert.equal(scaleLine("1/3 cup", 3), "1 cup");
          assert.equal(scaleLine("1/3 cup", 2), "5/8 cup");
          assert.equal(scaleLine("", 2), "");
          assert.equal(scaleLine("   ", 2), "   ");
          assert.equal(scaleLine("-3 apples", 2), "-3 apples");
          assert.equal(scaleLine("2-3-4", 2), "4-6-4");
          assert.equal(scaleLine("1 1/0 cups", 2), "2 1/0 cups");
          assert.equal(scaleLine("3 \u215b cups", 2), "6 1/4 cups");
        });

        test("scaleLine rejects bad factors", () => {
          assert.throws(() => scaleLine('1 cup', 0), RangeError);
          assert.throws(() => scaleLine('1 cup', -2), RangeError);
          assert.throws(() => scaleLine('1 cup', NaN), RangeError);
          assert.throws(() => scaleLine('1 cup', Infinity), RangeError);
          assert.throws(() => scaleLine('pinch', 0), RangeError);
          assert.throws(() => scaleLine('pinch', NaN), RangeError);
          assert.throws(() => scaleLine('pinch', Infinity), RangeError);
          assert.throws(() => scaleLine('pinch', -1), RangeError);
          assert.equal(scaleLine('1 cup', 0.01), '1/8 cup');
        });

        test("scaleRecipe", () => {
          assert.deepEqual(scaleRecipe(["2 cups flour", "1/2 tsp salt", "3 eggs", "salt to taste", "1 1/2 cups milk"], 4, 6), ["3 cups flour", "3/4 tsp salt", "4 1/2 eggs", "salt to taste", "2 1/4 cups milk"]);
          assert.deepEqual(scaleRecipe(["2 cups flour", "1/2 tsp salt", "3 eggs", "salt to taste", "1 1/2 cups milk"], 4, 1), ["1/2 cups flour", "1/8 tsp salt", "3/4 eggs", "salt to taste", "3/8 cups milk"]);
          assert.deepEqual(scaleRecipe(["1 cup rice", "2-3 cloves garlic"], 2, 2), ["1 cup rice", "2-3 cloves garlic"]);
          assert.deepEqual(scaleRecipe(["1 cup rice", "2-3 cloves garlic"], 3, 12), ["4 cup rice", "8-12 cloves garlic"]);
          assert.deepEqual(scaleRecipe([], 2, 4), []);
          assert.deepEqual(scaleRecipe(["\u00bd cup oil"], 1, 8), ["4 cup oil"]);
          const original = ['2 cups flour', '1 egg'];
          const scaled = scaleRecipe(original, 1, 2);
          assert.deepEqual(original, ['2 cups flour', '1 egg']);
          assert.notEqual(scaled, original);
          assert.throws(() => scaleRecipe(['1 cup'], 0, 2), RangeError);
          assert.throws(() => scaleRecipe(['1 cup'], 2, 0), RangeError);
          assert.throws(() => scaleRecipe(['1 cup'], -1, 2), RangeError);
          assert.throws(() => scaleRecipe(['1 cup'], 2, -1), RangeError);
          assert.throws(() => scaleRecipe(['1 cup'], NaN, 2), RangeError);
          assert.throws(() => scaleRecipe(['1 cup'], 2, Infinity), RangeError);
          assert.throws(() => scaleRecipe([], 0, 2), RangeError);
          assert.throws(() => scaleRecipe([], 2, 0), RangeError);
          assert.throws(() => scaleRecipe([], 2, -1), RangeError);
          assert.throws(() => scaleRecipe([], NaN, 2), RangeError);
          assert.throws(() => scaleRecipe([], 2, NaN), RangeError);
          assert.throws(() => scaleRecipe([], Infinity, 2), RangeError);
        });
''')

LIB = Lib(
    name="recipescale", lang="javascript", title="the recipescale helpers",
    blurb="The recipe site resizes ingredient lists for more or fewer servings with recipescale.",
    files={"package.json": PACKAGE_JSON % "recipescale", "src/qty.js": QTY, "src/scale.js": SCALE, "README.md": README, ".gitignore": "node_modules/\n"},
    visible_tests={"test/basic.test.js": VISIBLE},
    hidden_tests={"test/full.test.js": HIDDEN},
    mutate=["src/qty.js", "src/scale.js"], difficulty=1, tags=["recipes", "fractions", "formatting"],
    verify=JS_VERIFY,
    probe_import="const { parseQty, readQty, formatQty } = require('./src/qty');\nconst { scaleLine, scaleRecipe } = require('./src/scale');",
    probes=[
        "parseQty('1 1/2')",
        "parseQty('1\\u00bd')",
        "parseQty('1/0')",
        "parseQty('2x')",
        "readQty('1 1/2 cups')",
        "readQty('3/4 tsp')",
        "readQty('1 1/0 cups')",
        "formatQty(0.07)",
        "formatQty(0.3125)",
        "formatQty(0.9375)",
        "formatQty(2.97)",
        "formatQty(1 / 3)",
        "formatQty(12.125)",
        "scaleLine('1/2 tsp salt', 3)",
        "scaleLine('2-3 apples', 2)",
        "scaleLine('  1 1/2 cups flour', 2)",
        "scaleLine('1/3 cup', 2)",
        "scaleLine('pinch of salt', 4)",
        "scaleRecipe(['2 cups flour', '3 eggs', 'salt to taste'], 4, 6)",
        "scaleRecipe(['1 cup'], 0, 2)",
    ],
)

register_libs([LIB], n=8)
