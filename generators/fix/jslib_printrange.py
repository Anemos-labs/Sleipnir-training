"""Print-dialog page ranges (javascript): bugs injected into a tiny range parser and formatter."""
from fx import Lib, dd
from generators.fix._lang2 import JS_VERIFY, PACKAGE_JSON, register_libs

README = dd(r'''
    # printrange

    Page-range handling for the print dialog of a report viewer. CommonJS:
    `const { parseRanges, formatRanges, countPages, sheetsNeeded } = require('./src/ranges')`.

    ## `parseRanges(spec, pageCount)`

    Turns what the user typed into the sorted list of page numbers to print. Pages are numbered `1..pageCount`
    (`pageCount` must be an integer `>= 1`, else `RangeError`).

    The spec is a comma-separated list of items; spaces around items and around the dash are ignored:

    | item | pages |
    |---|---|
    | `N` | page N |
    | `A-B` | pages A to B |
    | `A-` | page A to the last page |
    | `-B` | page 1 to B |

    Rules:

    * An empty spec (or only spaces) means every page. An empty item between commas (`'1,,3'`) is a `TypeError`, as is
      anything that is not one of the four forms (letters, `1-2-3`, `0`, `+3`, `-` on its own, ...). Page numbers are
      written without a sign and `0` is not a page (`TypeError`).
    * `A-B` with `A > B` is a `RangeError`.
    * Pages beyond `pageCount` are cut off: `'8-20'` with 10 pages is pages 8 to 10, `'5-'` is 5 to the last page. An item
      that lies completely beyond the last page (`'12'`, `'11-15'`, `'11-'`) is a `RangeError`.
    * The result has no duplicates: `'3, 1-4'` is `[1, 2, 3, 4]`.

    ## `formatRanges(pages)`

    The inverse: writes a list of page numbers (any order, duplicates allowed, all integers `>= 1`, else `RangeError`) as a
    compact spec. Runs of three or more consecutive pages become `A-B`; shorter runs are listed one by one; items are
    joined with `', '`. `[]` gives `''`. For example `[1, 2, 3, 5, 8, 9, 10]` is `'1-3, 5, 8-10'` and `[4, 5]` is `'4, 5'`.

    ## `countPages(spec, pageCount)`

    How many pages the spec selects (`parseRanges(...).length`).

    ## `sheetsNeeded(pages, opts = {})`

    How many sheets of paper `pages` pages need. `opts.perSheet` is the number of pages printed on one side (default `1`,
    an integer `>= 1`), `opts.duplex` says both sides are used (default `false`). The number of sides is
    `ceil(pages / perSheet)`, the number of sheets is `ceil(sides / 2)` when duplex, else `sides`. `pages` must be an integer
    `>= 0` (`RangeError`); `0` pages need `0` sheets.
''')

RANGES = dd(r'''
    'use strict';

    function parseRanges(spec, pageCount) {
      if (!Number.isInteger(pageCount) || pageCount < 1) throw new RangeError('pageCount must be an integer >= 1');
      if (spec.trim() === '') return Array.from({ length: pageCount }, (_, i) => i + 1);
      const pages = new Set();
      for (const raw of spec.split(',')) {
        const item = raw.trim();
        const m = /^(\d+)?\s*(-)?\s*(\d+)?$/.exec(item);
        if (item === '' || m === null || (m[1] === undefined && m[3] === undefined)) throw new TypeError(`bad page range: '${item}'`);
        let from;
        let to;
        if (m[2] === undefined) {
          if (m[3] !== undefined && m[1] !== undefined) throw new TypeError(`bad page range: '${item}'`);
          from = to = Number(m[1]);
        } else {
          from = m[1] === undefined ? 1 : Number(m[1]);
          to = m[3] === undefined ? pageCount : Number(m[3]);
        }
        if (from < 1 || to < 1) throw new TypeError(`page numbers start at 1: '${item}'`);
        if (from > to) throw new RangeError(`range runs backwards: '${item}'`);
        if (from > pageCount) throw new RangeError(`beyond the last page: '${item}'`);
        for (let p = from; p <= Math.min(to, pageCount); p++) pages.add(p);
      }
      return [...pages].sort((a, b) => a - b);
    }

    function formatRanges(pages) {
      for (const p of pages) {
        if (!Number.isInteger(p) || p < 1) throw new RangeError(`bad page number: ${p}`);
      }
      const sorted = [...new Set(pages)].sort((a, b) => a - b);
      const items = [];
      let i = 0;
      while (i < sorted.length) {
        let j = i;
        while (j + 1 < sorted.length && sorted[j + 1] === sorted[j] + 1) j++;
        if (j - i >= 2) {
          items.push(`${sorted[i]}-${sorted[j]}`);
        } else {
          for (let k = i; k <= j; k++) items.push(String(sorted[k]));
        }
        i = j + 1;
      }
      return items.join(', ');
    }

    function countPages(spec, pageCount) {
      return parseRanges(spec, pageCount).length;
    }

    function sheetsNeeded(pages, opts = {}) {
      const perSheet = opts.perSheet === undefined ? 1 : opts.perSheet;
      if (!Number.isInteger(pages) || pages < 0) throw new RangeError('pages must be an integer >= 0');
      if (!Number.isInteger(perSheet) || perSheet < 1) throw new RangeError('perSheet must be an integer >= 1');
      const sides = Math.ceil(pages / perSheet);
      return opts.duplex ? Math.ceil(sides / 2) : sides;
    }

    module.exports = { parseRanges, formatRanges, countPages, sheetsNeeded };
''')

VISIBLE = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { parseRanges, formatRanges } = require('../src/ranges');

    test('simple specs', () => {
      assert.deepEqual(parseRanges('1-3, 5', 10), [1, 2, 3, 5]);
      assert.deepEqual(parseRanges('', 3), [1, 2, 3]);
    });

    test('format', () => {
      assert.equal(formatRanges([1, 2, 3, 5]), '1-3, 5');
    });
''')

HIDDEN = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { parseRanges, formatRanges, countPages, sheetsNeeded } = require('../src/ranges');

    test('single pages and ranges', () => {
      assert.deepEqual(parseRanges('4', 10), [4]);
      assert.deepEqual(parseRanges('1', 1), [1]);
      assert.deepEqual(parseRanges('3-5', 10), [3, 4, 5]);
      assert.deepEqual(parseRanges('7-7', 10), [7]);
      assert.deepEqual(parseRanges('1-3, 5, 8-9', 10), [1, 2, 3, 5, 8, 9]);
      assert.deepEqual(parseRanges('10', 10), [10]);
      assert.deepEqual(parseRanges('10-10', 10), [10]);
    });

    test('open ended ranges', () => {
      assert.deepEqual(parseRanges('-4', 10), [1, 2, 3, 4]);
      assert.deepEqual(parseRanges('8-', 10), [8, 9, 10]);
      assert.deepEqual(parseRanges('10-', 10), [10]);
      assert.deepEqual(parseRanges('-1', 5), [1]);
      assert.deepEqual(parseRanges('-3, 8-', 10), [1, 2, 3, 8, 9, 10]);
      assert.deepEqual(parseRanges('1-', 3), [1, 2, 3]);
    });

    test('spaces are ignored', () => {
      assert.deepEqual(parseRanges('  2 - 4 ,  7 ', 10), [2, 3, 4, 7]);
      assert.deepEqual(parseRanges(' - 2', 10), [1, 2]);
      assert.deepEqual(parseRanges('3 -', 5), [3, 4, 5]);
    });

    test('empty spec means every page', () => {
      assert.deepEqual(parseRanges('', 4), [1, 2, 3, 4]);
      assert.deepEqual(parseRanges('   ', 2), [1, 2]);
      assert.deepEqual(parseRanges('', 1), [1]);
    });

    test('duplicates and order', () => {
      assert.deepEqual(parseRanges('3, 1-4', 10), [1, 2, 3, 4]);
      assert.deepEqual(parseRanges('9, 2, 9, 5-6, 6-7', 10), [2, 5, 6, 7, 9]);
      assert.deepEqual(parseRanges('5-', 8).length, 4);
    });

    test('ranges are clipped to the document', () => {
      assert.deepEqual(parseRanges('8-20', 10), [8, 9, 10]);
      assert.deepEqual(parseRanges('1-99', 3), [1, 2, 3]);
      assert.deepEqual(parseRanges('10-10', 10), [10]);
      assert.deepEqual(parseRanges('2, 9-12', 10), [2, 9, 10]);
    });

    test('items beyond the last page are errors', () => {
      assert.throws(() => parseRanges('12', 10), RangeError);
      assert.throws(() => parseRanges('11', 10), RangeError);
      assert.throws(() => parseRanges('11-15', 10), RangeError);
      assert.throws(() => parseRanges('11-', 10), RangeError);
      assert.throws(() => parseRanges('1-3, 20', 10), RangeError);
      assert.throws(() => parseRanges('2', 1), RangeError);
    });

    test('backwards ranges are errors', () => {
      assert.throws(() => parseRanges('5-3', 10), RangeError);
      assert.throws(() => parseRanges('10-9', 10), RangeError);
      assert.doesNotThrow(() => parseRanges('3-3', 10));
    });

    test('syntax errors', () => {
      for (const bad of ['a', '1-b', '1,,3', ',', '1,', ',1', '-', '--3', '1-2-3', '+3', '1.5', '0', '0-3', '-0', '1 2', '3-4 5', 'all', '1;2']) {
        assert.throws(() => parseRanges(bad, 10), TypeError, JSON.stringify(bad));
      }
    });

    test('pageCount is validated', () => {
      assert.throws(() => parseRanges('1', 0), RangeError);
      assert.throws(() => parseRanges('', 0), RangeError);
      assert.throws(() => parseRanges('1', -2), RangeError);
      assert.throws(() => parseRanges('1', 2.5), RangeError);
      assert.throws(() => parseRanges('1', '3'), RangeError);
    });

    test('formatRanges', () => {
      assert.equal(formatRanges([]), '');
      assert.equal(formatRanges([5]), '5');
      assert.equal(formatRanges([1, 2, 3, 5, 8, 9, 10]), '1-3, 5, 8-10');
      assert.equal(formatRanges([4, 5]), '4, 5');
      assert.equal(formatRanges([1, 2]), '1, 2');
      assert.equal(formatRanges([1, 2, 3]), '1-3');
      assert.equal(formatRanges([1, 3, 5]), '1, 3, 5');
      assert.equal(formatRanges([2, 3, 4, 5, 6, 7]), '2-7');
      assert.equal(formatRanges([1, 2, 4, 5, 7, 8, 9]), '1, 2, 4, 5, 7-9');
      assert.equal(formatRanges([9, 8, 7, 1, 3, 2]), '1-3, 7-9');
      assert.equal(formatRanges([3, 3, 4, 4, 5, 9, 9]), '3-5, 9');
      assert.equal(formatRanges([10, 11, 12, 20]), '10-12, 20');
    });

    test('formatRanges errors and no side effects', () => {
      assert.throws(() => formatRanges([0]), RangeError);
      assert.throws(() => formatRanges([1, -2]), RangeError);
      assert.throws(() => formatRanges([1.5]), RangeError);
      assert.throws(() => formatRanges(['2']), RangeError);
      assert.throws(() => formatRanges([NaN]), RangeError);
      const input = [3, 1, 2];
      formatRanges(input);
      assert.deepEqual(input, [3, 1, 2]);
    });

    test('format then parse round trips', () => {
      for (const pages of [[1], [1, 2, 3, 4], [2, 4, 6, 7, 8, 12], [1, 5, 6, 7, 10, 11]]) {
        assert.deepEqual(parseRanges(formatRanges(pages), 20), pages);
      }
    });

    test('countPages', () => {
      assert.equal(countPages('1-3, 5', 10), 4);
      assert.equal(countPages('', 7), 7);
      assert.equal(countPages('8-', 10), 3);
      assert.equal(countPages('1-3, 2-4', 10), 4);
      assert.throws(() => countPages('x', 10), TypeError);
    });

    test('sheetsNeeded', () => {
      assert.equal(sheetsNeeded(0), 0);
      assert.equal(sheetsNeeded(5), 5);
      assert.equal(sheetsNeeded(5, { duplex: true }), 3);
      assert.equal(sheetsNeeded(6, { duplex: true }), 3);
      assert.equal(sheetsNeeded(1, { duplex: true }), 1);
      assert.equal(sheetsNeeded(9, { perSheet: 2 }), 5);
      assert.equal(sheetsNeeded(8, { perSheet: 2 }), 4);
      assert.equal(sheetsNeeded(9, { perSheet: 2, duplex: true }), 3);
      assert.equal(sheetsNeeded(8, { perSheet: 4, duplex: true }), 1);
      assert.equal(sheetsNeeded(9, { perSheet: 4, duplex: true }), 2);
      assert.equal(sheetsNeeded(0, { perSheet: 4, duplex: true }), 0);
      assert.equal(sheetsNeeded(7, { perSheet: 1, duplex: false }), 7);
    });

    test('sheetsNeeded errors', () => {
      assert.throws(() => sheetsNeeded(-1), RangeError);
      assert.throws(() => sheetsNeeded(2.5), RangeError);
      assert.throws(() => sheetsNeeded(3, { perSheet: 0 }), RangeError);
      assert.throws(() => sheetsNeeded(3, { perSheet: 1.5 }), RangeError);
      assert.throws(() => sheetsNeeded('3'), RangeError);
    });
''')

LIB = Lib(
    name="printrange", lang="javascript", title="the printrange helpers",
    blurb="The report viewer's print dialog uses printrange to read the page ranges people type and to count the sheets of paper.",
    files={"package.json": PACKAGE_JSON % "printrange", "src/ranges.js": RANGES, "README.md": README, ".gitignore": "node_modules/\n"},
    visible_tests={"test/basic.test.js": VISIBLE},
    hidden_tests={"test/full.test.js": HIDDEN},
    mutate=["src/ranges.js"], difficulty=1, tags=["printing", "parsing", "ranges"],
    verify=JS_VERIFY,
    probe_import="const { parseRanges, formatRanges, countPages, sheetsNeeded } = require('./src/ranges');",
    probes=[
        "parseRanges('1-3, 5, 8-9', 10)", "parseRanges('-4', 10)", "parseRanges('8-', 10)", "parseRanges('8-20', 10)", "parseRanges('  2 - 4 ,  7 ', 10)",
        "parseRanges('3, 1-4', 10)", "parseRanges('', 4)", "parseRanges('12', 10)", "parseRanges('5-3', 10)", "parseRanges('1,,3', 10)", "parseRanges('0', 10)",
        "formatRanges([1, 2, 3, 5, 8, 9, 10])", "formatRanges([4, 5])", "formatRanges([9, 8, 7, 1, 3, 2])", "formatRanges([3, 3, 4, 4, 5, 9, 9])",
        "countPages('1-3, 2-4', 10)", "sheetsNeeded(5, { duplex: true })", "sheetsNeeded(9, { perSheet: 2 })", "sheetsNeeded(9, { perSheet: 4, duplex: true })", "sheetsNeeded(0)",
    ],
)

register_libs([LIB], n=8)
