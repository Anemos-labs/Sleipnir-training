"""Plural categories and count formatting for invented languages (javascript): bugs injected into a localisation helper."""
from fx import Lib, dd
from generators.fix._lang2 import JS_VERIFY, PACKAGE_JSON, register_libs

README = dd(r'''
    # pluralis

    Plural and ordinal helpers for the three languages of the *Tidewater* board game's rule books (the languages are
    invented). CommonJS: `const { category, languages } = require('./src/rules')`,
    `const { plural, ordinal, formatCount } = require('./src/format')`.

    ## `src/rules.js`

    * `languages()` returns the language codes, sorted: `['norren', 'quell', 'tavish']`.
    * `category(lang, n)` returns the plural category of the number `n`:
      * an unknown `lang` is a `RangeError`; so is an `n` that is not a finite number;
      * the sign is ignored (`-1` behaves like `1`), and a number with a fractional part is always `'other'`;
      * `tavish`: `'one'` for 1; `'few'` for 2 to 6; `'heap'` for positive multiples of 7; `'other'` otherwise (also 0);
      * `norren`: `'zero'` for 0, `'one'` for 1, `'dual'` for 2, `'other'` otherwise;
      * `quell`: `'one'` when the number ends in 1 but not in 11; `'two'` when it ends in 2 but not in 12; `'other'`
        otherwise (so 21 and 101 are `'one'`, 11 and 111 are `'other'`).

    ## `src/format.js`

    * `formatCount(n, opts = {})` writes a number for display. `maxFrac` (default `2`) is the largest number of decimals:
      the absolute value is rounded half up to that many decimals (`Math.round(abs * 10 ** maxFrac) / 10 ** maxFrac`),
      trailing zeros of the fraction are dropped, and so is the point if nothing remains. The integer part is grouped in
      threes with commas (`1,234,567`) unless `opts.group === false`. A `-` is put in front for negative numbers, except
      when the rounded value is zero (`-0.001` is `'0'`).
    * `plural(lang, forms, n, opts)` picks the entry of `forms` (an object keyed by category) for `category(lang, n)`; if
      the category has no entry the `other` entry is used; if that is missing too it is a `TypeError`. Every `{n}` in the
      chosen text is replaced by `formatCount(n, opts)`.
    * `ordinal(lang, n)` writes an ordinal; `n` must be a non-negative integer (else `RangeError`):
      * `tavish`: positive multiples of 7 give `<n>-vel`; otherwise by the last digit: 1 gives `<n>-ka`, 2 `<n>-sa`, 3
        `<n>-ra`, any other digit `<n>-ta`;
      * `norren`: `<n>.` (a full stop);
      * `quell`: ends in 1 but not 11: `<n>-i`; ends in 2 but not 12: `<n>-ii`; anything else `<n>-x`.
      The number is written plainly, without grouping.
''')

RULES = dd(r'''
    'use strict';

    const RULES = {
      tavish(n) {
        if (n === 1) return 'one';
        if (n >= 2 && n <= 6) return 'few';
        if (n > 0 && n % 7 === 0) return 'heap';
        return 'other';
      },
      norren(n) {
        if (n === 0) return 'zero';
        if (n === 1) return 'one';
        if (n === 2) return 'dual';
        return 'other';
      },
      quell(n) {
        const last = n % 10;
        const lastTwo = n % 100;
        if (last === 1 && lastTwo !== 11) return 'one';
        if (last === 2 && lastTwo !== 12) return 'two';
        return 'other';
      },
    };

    function languages() {
      return Object.keys(RULES).sort();
    }

    function category(lang, n) {
      if (!Object.prototype.hasOwnProperty.call(RULES, lang)) throw new RangeError(`unknown language ${lang}`);
      if (typeof n !== 'number' || !Number.isFinite(n)) throw new RangeError('n must be a finite number');
      const abs = Math.abs(n);
      if (!Number.isInteger(abs)) return 'other';
      return RULES[lang](abs);
    }

    module.exports = { languages, category };
''')

FORMAT = dd(r'''
    'use strict';

    const { category } = require('./rules');

    function formatCount(n, opts = {}) {
      const maxFrac = opts.maxFrac === undefined ? 2 : opts.maxFrac;
      const factor = 10 ** maxFrac;
      const rounded = Math.round(Math.abs(n) * factor) / factor;
      const parts = rounded.toFixed(maxFrac).split('.');
      let whole = parts[0];
      const frac = (parts[1] || '').replace(/0+$/, '');
      if (opts.group !== false) whole = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
      const sign = n < 0 && rounded !== 0 ? '-' : '';
      return sign + whole + (frac === '' ? '' : '.' + frac);
    }

    function plural(lang, forms, n, opts) {
      const cat = category(lang, n);
      const form = forms[cat] !== undefined ? forms[cat] : forms.other;
      if (form === undefined) throw new TypeError(`no form for ${cat} and no 'other' form`);
      return form.replace(/\{n\}/g, formatCount(n, opts));
    }

    function ordinal(lang, n) {
      if (!Number.isInteger(n) || n < 0) throw new RangeError('ordinal needs a non-negative integer');
      if (lang === 'norren') return `${n}.`;
      const last = n % 10;
      const lastTwo = n % 100;
      if (lang === 'tavish') {
        if (n > 0 && n % 7 === 0) return `${n}-vel`;
        if (last === 1) return `${n}-ka`;
        if (last === 2) return `${n}-sa`;
        if (last === 3) return `${n}-ra`;
        return `${n}-ta`;
      }
      if (lang === 'quell') {
        if (last === 1 && lastTwo !== 11) return `${n}-i`;
        if (last === 2 && lastTwo !== 12) return `${n}-ii`;
        return `${n}-x`;
      }
      throw new RangeError(`unknown language ${lang}`);
    }

    module.exports = { formatCount, plural, ordinal };
''')

VISIBLE = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { category } = require('../src/rules');
    const { plural } = require('../src/format');

    test('tavish one and few', () => {
      assert.equal(category('tavish', 1), 'one');
      assert.equal(category('tavish', 3), 'few');
    });

    test('plural picks a form', () => {
      const forms = { one: '{n} reef', other: '{n} reefs' };
      assert.equal(plural('norren', forms, 1), '1 reef');
      assert.equal(plural('norren', forms, 5), '5 reefs');
    });
''')

HIDDEN = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { category, languages } = require('../src/rules');
    const { plural, ordinal, formatCount } = require('../src/format');

    const cats = (lang, ns) => ns.map((n) => category(lang, n));

    test('languages are sorted', () => {
      assert.deepEqual(languages(), ['norren', 'quell', 'tavish']);
    });

    test('tavish categories', () => {
      assert.deepEqual(cats('tavish', [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 13, 14, 15, 21, 28, 70, 100]), [
        'other', 'one', 'few', 'few', 'few', 'few', 'few', 'heap', 'other', 'other', 'other', 'heap', 'other', 'heap', 'heap', 'heap', 'other',
      ]);
    });

    test('norren categories', () => {
      assert.deepEqual(cats('norren', [0, 1, 2, 3, 10, 11, 12, 100]), ['zero', 'one', 'dual', 'other', 'other', 'other', 'other', 'other']);
    });

    test('quell categories', () => {
      assert.deepEqual(cats('quell', [0, 1, 2, 3, 10, 11, 12, 13, 21, 22, 31, 101, 111, 112, 102, 1001, 1011, 1012]), [
        'other', 'one', 'two', 'other', 'other', 'other', 'other', 'other', 'one', 'two', 'one', 'one', 'other', 'other', 'two', 'one', 'other', 'other',
      ]);
    });

    test('signs are ignored and fractions are other', () => {
      assert.equal(category('tavish', -1), 'one');
      assert.equal(category('tavish', -3), 'few');
      assert.equal(category('tavish', -14), 'heap');
      assert.equal(category('norren', -2), 'dual');
      assert.equal(category('quell', -21), 'one');
      assert.equal(category('tavish', 1.5), 'other');
      assert.equal(category('norren', 0.5), 'other');
      assert.equal(category('quell', 21.25), 'other');
      assert.equal(category('quell', -1.1), 'other');
      assert.equal(category('norren', 2.0), 'dual');
      assert.equal(category('norren', -0), 'zero');
    });

    test('category errors', () => {
      assert.throws(() => category('elvish', 1), RangeError);
      assert.throws(() => category('constructor', 1), RangeError);
      assert.throws(() => category('toString', 1), RangeError);
      assert.throws(() => category('tavish', NaN), RangeError);
      assert.throws(() => category('tavish', Infinity), RangeError);
      assert.throws(() => category('tavish', '3'), RangeError);
      assert.throws(() => category('tavish', null), RangeError);
    });

    test('formatCount groups and trims', () => {
      assert.equal(formatCount(0), '0');
      assert.equal(formatCount(7), '7');
      assert.equal(formatCount(999), '999');
      assert.equal(formatCount(1000), '1,000');
      assert.equal(formatCount(12345), '12,345');
      assert.equal(formatCount(1234567), '1,234,567');
      assert.equal(formatCount(100000), '100,000');
      assert.equal(formatCount(1234567.5), '1,234,567.5');
      assert.equal(formatCount(2.5), '2.5');
      assert.equal(formatCount(2.0), '2');
      assert.equal(formatCount(0.125), '0.13');
      assert.equal(formatCount(3.1), '3.1');
    });

    test('formatCount options', () => {
      assert.equal(formatCount(1234567, { group: false }), '1234567');
      assert.equal(formatCount(1234.5, { group: false }), '1234.5');
      assert.equal(formatCount(1234.5678, { group: true }), '1,234.57');
      assert.equal(formatCount(0.125, { maxFrac: 3 }), '0.125');
      assert.equal(formatCount(0.125, { maxFrac: 1 }), '0.1');
      assert.equal(formatCount(0.75, { maxFrac: 1 }), '0.8');
      assert.equal(formatCount(2.5, { maxFrac: 0 }), '3');
      assert.equal(formatCount(2.4, { maxFrac: 0 }), '2');
      assert.equal(formatCount(1234.5, { maxFrac: 0 }), '1,235');
      assert.equal(formatCount(999.999, { maxFrac: 2 }), '1,000');
      assert.equal(formatCount(0.999, { maxFrac: 2 }), '1');
    });

    test('formatCount negatives', () => {
      assert.equal(formatCount(-1), '-1');
      assert.equal(formatCount(-1234.5), '-1,234.5');
      assert.equal(formatCount(-0.25), '-0.25');
      assert.equal(formatCount(-0.001), '0');
      assert.equal(formatCount(-0), '0');
      assert.equal(formatCount(-2.5, { maxFrac: 0 }), '-3');
      assert.equal(formatCount(-0.4, { maxFrac: 0 }), '0');
    });

    test('plural picks by category and falls back to other', () => {
      const forms = { one: '{n} pebble', few: '{n} pebbles (a few)', heap: 'a heap of {n}', other: '{n} pebbles' };
      assert.equal(plural('tavish', forms, 1), '1 pebble');
      assert.equal(plural('tavish', forms, 4), '4 pebbles (a few)');
      assert.equal(plural('tavish', forms, 14), 'a heap of 14');
      assert.equal(plural('tavish', forms, 8), '8 pebbles');
      assert.equal(plural('tavish', forms, 0), '0 pebbles');
      assert.equal(plural('tavish', forms, 1.5), '1.5 pebbles');
      assert.equal(plural('tavish', { other: 'x{n}' }, 1), 'x1');
      assert.equal(plural('norren', { zero: 'none', other: '{n} left' }, 0), 'none');
      assert.equal(plural('norren', { zero: 'none', other: '{n} left' }, 2), '2 left');
    });

    test('plural replaces every {n} and formats the number', () => {
      assert.equal(plural('quell', { other: '{n} of {n}' }, 1234), '1,234 of 1,234');
      assert.equal(plural('quell', { one: '{n}!', other: '{n}?' }, 21), '21!');
      assert.equal(plural('quell', { one: '{n}!', other: '{n}?' }, 11), '11?');
      assert.equal(plural('tavish', { other: '{n}' }, 1234567, { group: false }), '1234567');
      assert.equal(plural('tavish', { other: '{n}' }, 2.256, { maxFrac: 1 }), '2.3');
      assert.equal(plural('norren', { other: 'no number here' }, 5), 'no number here');
      assert.equal(plural('norren', { other: '{n}' }, -4), '-4');
    });

    test('plural errors', () => {
      assert.throws(() => plural('tavish', { one: '{n}' }, 5), TypeError);
      assert.throws(() => plural('tavish', {}, 1), TypeError);
      assert.throws(() => plural('nope', { other: '{n}' }, 1), RangeError);
      assert.throws(() => plural('tavish', { other: '{n}' }, NaN), RangeError);
    });

    test('plural: an empty string is a form', () => {
      assert.equal(plural('norren', { zero: '', other: '{n}' }, 0), '');
    });

    test('tavish ordinals', () => {
      assert.deepEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 13, 14, 21, 22, 23, 100, 101, 1000].map((n) => ordinal('tavish', n)), [
        '0-ta', '1-ka', '2-sa', '3-ra', '4-ta', '5-ta', '6-ta', '7-vel', '8-ta', '11-ka', '12-sa', '13-ra', '14-vel', '21-vel', '22-sa', '23-ra', '100-ta', '101-ka', '1000-ta',
      ]);
    });

    test('norren and quell ordinals', () => {
      assert.deepEqual([0, 1, 2, 3, 22, 1000].map((n) => ordinal('norren', n)), ['0.', '1.', '2.', '3.', '22.', '1000.']);
      assert.deepEqual([0, 1, 2, 3, 9, 10, 11, 12, 13, 21, 22, 111, 112, 121, 1002].map((n) => ordinal('quell', n)), [
        '0-x', '1-i', '2-ii', '3-x', '9-x', '10-x', '11-x', '12-x', '13-x', '21-i', '22-ii', '111-x', '112-x', '121-i', '1002-ii',
      ]);
    });

    test('ordinal errors', () => {
      assert.throws(() => ordinal('tavish', -1), RangeError);
      assert.throws(() => ordinal('tavish', 1.5), RangeError);
      assert.throws(() => ordinal('tavish', '2'), RangeError);
      assert.throws(() => ordinal('tavish', NaN), RangeError);
      assert.throws(() => ordinal('elvish', 1), RangeError);
      assert.throws(() => ordinal('norren', -2), RangeError);
    });
''')

LIB = Lib(
    name="pluralis", lang="javascript", title="the pluralis library",
    blurb="The rule-book generator of the Tidewater board game uses pluralis to write counts and ordinals in its three invented languages.",
    files={"package.json": PACKAGE_JSON % "pluralis", "src/rules.js": RULES, "src/format.js": FORMAT, "README.md": README, ".gitignore": "node_modules/\n"},
    visible_tests={"test/basic.test.js": VISIBLE},
    hidden_tests={"test/full.test.js": HIDDEN},
    mutate=["src/rules.js", "src/format.js"], difficulty=1, tags=["i18n", "plural", "formatting"],
    verify=JS_VERIFY,
    probe_import="const { category, languages } = require('./src/rules');\nconst { plural, ordinal, formatCount } = require('./src/format');",
    probes=[
        "category('tavish', 14)", "category('tavish', 7)", "category('tavish', 6)", "category('tavish', 0)", "category('tavish', -1)", "category('tavish', 1.5)",
        "category('norren', 2)", "category('norren', 0)", "category('quell', 21)", "category('quell', 111)", "category('quell', 12)", "category('quell', 1012)",
        "formatCount(1234567)", "formatCount(100000)", "formatCount(0.125)", "formatCount(-0.001)", "formatCount(-1234.5)", "formatCount(2.5, { maxFrac: 0 })",
        "formatCount(1234567, { group: false })", "formatCount(999.999)",
        "plural('tavish', { one: '{n} pebble', few: '{n} few', heap: 'a heap of {n}', other: '{n} pebbles' }, 14)",
        "plural('tavish', { other: '{n}' }, 2.256, { maxFrac: 1 })", "plural('quell', { other: '{n} of {n}' }, 1234)",
        "ordinal('tavish', 21)", "ordinal('tavish', 11)", "ordinal('tavish', 100)", "ordinal('quell', 112)", "ordinal('quell', 121)", "ordinal('norren', 3)", "ordinal('tavish', -1)",
    ],
)

register_libs([LIB], n=8)
