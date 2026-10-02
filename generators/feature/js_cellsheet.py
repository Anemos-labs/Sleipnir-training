"""cellsheet (javascript): a small spreadsheet extended with rows, ranges, formats, formulas, functions, CSV, undo, fill."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # cellsheet

    A tiny spreadsheet engine for a budgeting tool (Node.js, CommonJS, no dependencies). Run the tests with `npm test`
    (`node --test test/*.test.js`).

    ## Layout

    * `index.js`: exports `Sheet`.
    * `src/address.js`: cell addresses.
    * `src/sheet.js`: the sheet.

    ## Basics

    A sheet has columns `A` to `Z` and rows 1 to 99. An address is a capital letter followed by the row number without
    leading zeros (`A1`, `Z99`); anything else is a `RangeError`.

    * `new Sheet()`.
    * `sheet.set(addr, value)` stores a number (finite, else `TypeError`) or a string. `null`, `undefined` and `''` empty the
      cell; any other type is a `TypeError`. The address is checked before the value. Strings are text: a leading `=` has no
      special meaning yet.
    * `sheet.get(addr)` returns the value of a cell, `null` when it is empty.
    * `sheet.size()` is the number of non-empty cells; `sheet.addresses()` lists them ordered by row, then column.
    * `sheet.used()` returns `{ columns, rows }`: the number of the last non-empty column (A = 1) and the last non-empty row, both
      0 for an empty sheet. `sheet.grid()` is an array of `rows` arrays with `columns` values each (`null` for empty cells).
''')

ADDRESS = '''\
'use strict';

const ADDR = /^([A-Z])([1-9][0-9]?)$/;

/** Parses an address into 1-based column and row numbers. */
function parse(addr) {
  const m = typeof addr === 'string' ? ADDR.exec(addr) : null;
  if (!m) throw new RangeError(`bad address: ${addr}`);
  return { col: m[1].charCodeAt(0) - 64, row: Number(m[2]) };
}

function format(col, row) {
  return String.fromCharCode(64 + col) + row;
}

/** Parses `A1:B3` (or a single address) into a normalised rectangle of 1-based columns and rows. */
function parseRange(range) {
  if (typeof range !== 'string') throw new RangeError(`bad range: ${range}`);
  const parts = range.split(':');
  if (parts.length > 2) throw new RangeError(`bad range: ${range}`);
  const a = parse(parts[0]);
  const b = parse(parts[parts.length - 1]);
  return { c1: Math.min(a.col, b.col), r1: Math.min(a.row, b.row), c2: Math.max(a.col, b.col), r2: Math.max(a.row, b.row) };
}

module.exports = { ADDR, parse, format, parseRange };
'''

SHEET = '''\
'use strict';
const { ADDR, parse, format, parseRange } = require('./address');
@@uniq requires

@@blocks helpers

class Sheet {
  constructor() {
    this.cells = new Map();
    @@slot init
  }

  set(addr, value) {
    const { col, row } = parse(addr);
    let raw = value;
    if (value === null || value === undefined || value === '') {
      raw = null;
    } else if (typeof value === 'number') {
      if (!Number.isFinite(value)) throw new TypeError('numbers must be finite');
    } else if (typeof value !== 'string') {
      throw new TypeError('a cell holds a number or a string');
    }
    this._apply([[format(col, row), raw]]);
  }

  /** Applies [key, raw-or-null] changes. Every mutation of the cells goes through here. */
  _apply(changes) {
    @@slot apply_pre
    for (const [key, raw] of changes) {
      if (raw === null) this.cells.delete(key);
      else this.cells.set(key, raw);
    }
    @@slot apply_post
  }

  @@default eval_method
  _eval(key) {
    return this.cells.has(key) ? this.cells.get(key) : null;
  }
  @@end

  get(addr) {
    const { col, row } = parse(addr);
    return this._eval(format(col, row));
  }

  size() {
    return this.cells.size;
  }

  addresses() {
    const key = (a) => {
      const p = parse(a);
      return [p.row, p.col];
    };
    return [...this.cells.keys()].sort((a, b) => {
      const [ra, ca] = key(a);
      const [rb, cb] = key(b);
      return ra - rb || ca - cb;
    });
  }

  used() {
    let columns = 0;
    let rows = 0;
    for (const k of this.cells.keys()) {
      const p = parse(k);
      columns = Math.max(columns, p.col);
      rows = Math.max(rows, p.row);
    }
    return { columns, rows };
  }

  grid() {
    const { columns, rows } = this.used();
    const out = [];
    for (let r = 1; r <= rows; r++) {
      const line = [];
      for (let c = 1; c <= columns; c++) line.push(this.get(format(c, r)));
      out.push(line);
    }
    return out;
  }

  @@blocks methods
}

module.exports = { Sheet };
'''

HEAD = '''\
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
@@uniq requires
const { Sheet } = require('../index.js');

/** A1 10, B1 'apples', A2 5, B2 'pears, ripe', C3 2.5 */
const mk = () => {
  const s = new Sheet();
  s.set('A1', 10);
  s.set('B1', 'apples');
  s.set('A2', 5);
  s.set('B2', 'pears, ripe');
  s.set('C3', 2.5);
  return s;
};
'''

VISIBLE = HEAD + '''
test('set and get', () => {
  const s = mk();
  assert.equal(s.get('A1'), 10);
  assert.equal(s.get('B2'), 'pears, ripe');
  assert.equal(s.get('Z99'), null);
  s.set('A1', null);
  assert.equal(s.get('A1'), null);
  assert.equal(s.size(), 4);
  assert.throws(() => s.set('a1', 1), RangeError);
  assert.throws(() => s.set('A1', true), TypeError);
});

test('layout helpers', () => {
  const s = mk();
  assert.deepEqual(s.addresses(), ['A1', 'B1', 'A2', 'B2', 'C3']);
  assert.deepEqual(s.used(), { columns: 3, rows: 3 });
  assert.deepEqual(s.grid()[2], [null, null, 2.5]);
});
@@blocks tests
'''

HIDDEN = HEAD + '''
test('base: addresses', () => {
  const s = new Sheet();
  for (const bad of ['a1', 'A0', 'A100', 'AA1', '1A', 'A01', 'A', '', ' A1', 'A1 ', null, undefined, 5, {}]) {
    assert.throws(() => s.set(bad, 1), RangeError, String(bad));
    assert.throws(() => s.get(bad), RangeError, String(bad));
  }
  s.set('Z99', 1);
  s.set('A1', 2);
  s.set('M13', 3);
  assert.equal(s.get('Z99'), 1);
  assert.equal(s.get('M13'), 3);
  assert.equal(s.size(), 3);
  assert.throws(() => s.set('A100', true), RangeError, 'the address is checked before the value');
});

test('base: values', () => {
  const s = new Sheet();
  for (const bad of [true, false, {}, [], NaN, Infinity, -Infinity, () => 1, Symbol('x')]) {
    assert.throws(() => s.set('A1', bad), TypeError, String(typeof bad));
  }
  assert.equal(s.size(), 0);
  s.set('A1', 0);
  s.set('A2', -3.5);
  s.set('A3', '  padded  ');
  assert.equal(s.get('A1'), 0);
  assert.equal(s.get('A2'), -3.5);
  assert.equal(s.get('A3'), '  padded  ');
  assert.equal(s.size(), 3);
  s.set('A1', '');
  s.set('A2', undefined);
  s.set('A3', null);
  assert.equal(s.size(), 0);
  assert.equal(s.get('A1'), null);
  s.set('A1', 'x');
  s.set('A1', 7);
  assert.equal(s.get('A1'), 7);
  s.set('B1', 'text that is not a formula');
  assert.equal(s.get('B1'), 'text that is not a formula');
});

test('base: layout', () => {
  const s = new Sheet();
  assert.deepEqual(s.used(), { columns: 0, rows: 0 });
  assert.deepEqual(s.grid(), []);
  assert.deepEqual(s.addresses(), []);
  s.set('C2', 'c2');
  s.set('A9', 'a9');
  s.set('B2', 'b2');
  s.set('A1', 'a1');
  assert.deepEqual(s.addresses(), ['A1', 'B2', 'C2', 'A9']);
  assert.deepEqual(s.used(), { columns: 3, rows: 9 });
  const g = s.grid();
  assert.equal(g.length, 9);
  assert.deepEqual(g[0], ['a1', null, null]);
  assert.deepEqual(g[1], [null, 'b2', 'c2']);
  assert.deepEqual(g[8], ['a9', null, null]);
  s.set('A9', null);
  assert.deepEqual(s.used(), { columns: 3, rows: 2 });
  s.set('C2', null);
  assert.deepEqual(s.used(), { columns: 2, rows: 2 });
});
@@blocks tests
'''

FORMULA_HELPERS = '''\
class FormulaError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

@@default formula_ops
const OPS = '+-*/()';
@@end

function tokenizeFormula(src) {
  const out = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (c === ' ' || c === '\\t') {
      i++;
      continue;
    }
    const rest = src.slice(i);
    let m = /^\\d+(\\.\\d+)?/.exec(rest);
    if (m) {
      out.push({ t: 'num', v: Number(m[0]) });
      i += m[0].length;
    } else if ((m = /^[A-Za-z][A-Za-z0-9]*/.exec(rest))) {
      out.push({ t: 'id', v: m[0].toUpperCase() });
      i += m[0].length;
    } else if (OPS.includes(c)) {
      out.push({ t: c });
      i++;
    } else {
      throw new FormulaError('#SYNTAX!');
    }
  }
  return out;
}

function parseFormula(tokens) {
  let pos = 0;
  const peek = () => tokens[pos];
  const is = (t) => peek() !== undefined && peek().t === t;

  function expr() {
    let a = term();
    while (is('+') || is('-')) {
      const op = tokens[pos++].t;
      a = { t: 'bin', op, a, b: term() };
    }
    return a;
  }

  function term() {
    let a = unary();
    while (is('*') || is('/')) {
      const op = tokens[pos++].t;
      a = { t: 'bin', op, a, b: unary() };
    }
    return a;
  }

  function unary() {
    if (is('-')) {
      pos++;
      return { t: 'neg', a: unary() };
    }
    return primary();
  }

  function primary() {
    const tk = tokens[pos++];
    if (!tk) throw new FormulaError('#SYNTAX!');
    if (tk.t === 'num') return { t: 'num', v: tk.v };
    if (tk.t === '(') {
      const e = expr();
      if (!is(')')) throw new FormulaError('#SYNTAX!');
      pos++;
      return e;
    }
    if (tk.t === 'id') {
      @@slot primary_id
      return { t: 'ref', id: tk.v };
    }
    throw new FormulaError('#SYNTAX!');
  }

  @@slot parse_helpers

  const ast = expr();
  if (pos !== tokens.length) throw new FormulaError('#SYNTAX!');
  return ast;
}

function evaluateFormula(sheet, node) {
  switch (node.t) {
    case 'num':
      return node.v;
    case 'ref':
      return sheet._cellNumber(node.id);
    case 'neg':
      return 0 - evaluateFormula(sheet, node.a);
    case 'bin': {
      const a = evaluateFormula(sheet, node.a);
      const b = evaluateFormula(sheet, node.b);
      if (node.op === '+') return a + b;
      if (node.op === '-') return a - b;
      if (node.op === '*') return a * b;
      if (b === 0) throw new FormulaError('#DIV/0!');
      return a / b;
    }
    @@slot eval_cases
    default:
      throw new FormulaError('#SYNTAX!');
  }
}
'''

FORMULA_METHODS = '''\
_isFormula(raw) {
  return typeof raw === 'string' && raw.startsWith('=');
}

/** The value of a cell; throws a FormulaError for error values. */
_evalKey(key) {
  const raw = this.cells.get(key);
  if (raw === undefined) return null;
  if (!this._isFormula(raw)) return raw;
  if (this._stack.has(key)) throw new FormulaError('#CYCLE!');
  this._stack.add(key);
  try {
    return evaluateFormula(this, parseFormula(tokenizeFormula(raw.slice(1))));
  } finally {
    this._stack.delete(key);
  }
}

_eval(key) {
  try {
    return this._evalKey(key);
  } catch (e) {
    if (e instanceof FormulaError) return e.code;
    throw e;
  }
}

_cellNumber(id) {
  if (!ADDR.test(id)) throw new FormulaError('#NAME?');
  const v = this._evalKey(id);
  if (v === null) return 0;
  if (typeof v === 'number') return v;
  throw new FormulaError('#VALUE!');
}

/** The source of a formula cell (starting with `=`), or null. */
formula(addr) {
  const { col, row } = parse(addr);
  const raw = this.cells.get(format(col, row));
  return this._isFormula(raw) ? raw : null;
}
'''


def make_slices(rng: random.Random):
    undo_limit = rng.choice([3, 5, 10])
    max_dec = rng.choice([4, 6])
    avg = rng.choice(["AVG", "AVERAGE"])
    other_avg = "AVERAGE" if avg == "AVG" else "AVG"
    S = []

    S.append(Slice(
        id="row-col", title="Rows and columns", d=1,
        pitch=("The report page needs the whole of column C as a list and nobody wants to loop over addresses.",
               "People want to read a complete row or column of the sheet at once."),
        reqs=("`sheet.row(n)` returns an array with the values of row `n` from column A up to the last used column (`sheet.used().columns`), `null` for empty cells; `sheet.column(letter)` returns the values of that column from row 1 to the last used row. An empty sheet gives `[]`. A row outside 1 to 99 (or not an integer) and a column that is not a single capital letter throw a `RangeError`; rows and columns beyond the used area are valid and are filled with `null`.",),
        code={
            "src/sheet.js::methods": '''
                row(n) {
                  if (!Number.isInteger(n) || n < 1 || n > 99) throw new RangeError(`bad row: ${n}`);
                  const out = [];
                  for (let c = 1; c <= this.used().columns; c++) out.push(this.get(format(c, n)));
                  return out;
                }

                column(letter) {
                  if (typeof letter !== 'string' || !/^[A-Z]$/.test(letter)) throw new RangeError(`bad column: ${letter}`);
                  const col = letter.charCodeAt(0) - 64;
                  const out = [];
                  for (let r = 1; r <= this.used().rows; r++) out.push(this.get(format(col, r)));
                  return out;
                }
            ''',
        },
        readme="## Rows and columns\n\n`sheet.row(n)` and `sheet.column(letter)` return the values of a whole row (up to the last used column) or column (down to the last used row); `null` for empty cells, `RangeError` for invalid arguments.\n",
        vtests='''
          test('row and column', () => {
            const s = mk();
            assert.deepEqual(s.row(1), [10, 'apples', null]);
            assert.deepEqual(s.column('A'), [10, 5, null]);
          });
        ''',
        tests='''
          test('row and column values', () => {
            const s = mk();
            assert.deepEqual(s.row(2), [5, 'pears, ripe', null]);
            assert.deepEqual(s.row(3), [null, null, 2.5]);
            assert.deepEqual(s.row(50), [null, null, null]);
            assert.deepEqual(s.column('B'), ['apples', 'pears, ripe', null]);
            assert.deepEqual(s.column('C'), [null, null, 2.5]);
            assert.deepEqual(s.column('Z'), [null, null, null]);
            const empty = new Sheet();
            assert.deepEqual(empty.row(1), []);
            assert.deepEqual(empty.column('A'), []);
          });

          test('row and column validation', () => {
            const s = mk();
            for (const bad of [0, 100, 1.5, -1, '1', null, undefined, NaN]) assert.throws(() => s.row(bad), RangeError, String(bad));
            for (const bad of ['a', 'AA', '', 1, null, '1', ' A']) assert.throws(() => s.column(bad), RangeError, String(bad));
          });
        ''',
    ))

    S.append(Slice(
        id="clear-range", title="Clearing a range", d=1,
        pitch=("Last month's numbers have to be wiped before the new month starts and that is dozens of calls.",
               "Users want to empty a block of cells in one step."),
        reqs=("`sheet.clearRange(range)` empties every cell of a rectangle and returns how many non-empty cells it emptied. A range is written `A1:B3`; the two corners can be given in any order (`B3:A1` is the same rectangle) and a single address (`C3`) is a one-cell range. Anything else (`A1:`, `:B2`, `a1:b2`, `A1:B100`, a non-string) is a `RangeError` and nothing is cleared.",),
        code={
            "src/sheet.js::methods": '''
                clearRange(range) {
                  const { c1, r1, c2, r2 } = parseRange(range);
                  const changes = [];
                  for (let r = r1; r <= r2; r++) {
                    for (let c = c1; c <= c2; c++) {
                      const key = format(c, r);
                      if (this.cells.has(key)) changes.push([key, null]);
                    }
                  }
                  this._apply(changes);
                  return changes.length;
                }
            ''',
        },
        readme="## Clearing a range\n\n`sheet.clearRange('A1:B3')` empties a rectangle (corners in any order, a single address is fine) and returns the number of cells it emptied; invalid ranges are a `RangeError`.\n",
        vtests='''
          test('clear range', () => {
            const s = mk();
            assert.equal(s.clearRange('A1:B2'), 4);
            assert.equal(s.size(), 1);
          });
        ''',
        tests='''
          test('clearRange', () => {
            const s = mk();
            assert.equal(s.clearRange('B2:A1'), 4);
            assert.equal(s.get('A1'), null);
            assert.equal(s.get('B2'), null);
            assert.equal(s.get('C3'), 2.5);
            assert.equal(s.clearRange('A1:B2'), 0);
            assert.equal(s.clearRange('C3'), 1);
            assert.equal(s.size(), 0);
            const t = mk();
            assert.equal(t.clearRange('B1:C3'), 3);
            assert.deepEqual(t.addresses(), ['A1', 'A2']);
            const u = mk();
            assert.equal(u.clearRange('A1:Z99'), 5);
            assert.equal(u.size(), 0);
          });

          test('clearRange validation', () => {
            const s = mk();
            for (const bad of ['A1:', ':B2', 'a1:b2', 'A1:B100', 'A1:B2:C3', '', 'A1-B2', null, 12, undefined]) {
              assert.throws(() => s.clearRange(bad), RangeError, String(bad));
            }
            assert.equal(s.size(), 5);
          });
        ''',
    ))

    S.append(Slice(
        id="format", title="Display formats", d=2,
        pitch=("Money shows up as 1234.5 in the exported report and the accountants complain.",
               "Cells need display formats such as currency symbols and a fixed number of decimals."),
        reqs=(f"`sheet.setFormat(addr, opts)` attaches a display format to a cell, whether it is empty or not. `opts` is an object with the optional keys `decimals` (an integer from 0 to {max_dec}), `prefix` and `suffix` (strings); unknown keys, a non-object or wrong types are a `TypeError`, a `decimals` outside the range a `RangeError`. `null` removes the format. A format replaces the previous one. `sheet.getFormat(addr)` returns a copy of the stored options or `null`.",
              "`sheet.display(addr)` returns the text of a cell: `''` for an empty cell, the string itself for text, and for a number `prefix + n.toFixed(decimals) + suffix` (`String(n)` when no `decimals` is given; prefix and suffix are only applied to numbers). Without a format a number is `String(n)`."),
        code={
            "src/sheet.js::init": "this.formats = new Map();",
            "src/sheet.js::methods": f'''
                setFormat(addr, opts) {{
                  const {{ col, row }} = parse(addr);
                  const key = format(col, row);
                  if (opts === null) {{
                    this.formats.delete(key);
                    return;
                  }}
                  if (typeof opts !== 'object' || Array.isArray(opts)) throw new TypeError('format options must be an object');
                  for (const k of Object.keys(opts)) {{
                    if (!['decimals', 'prefix', 'suffix'].includes(k)) throw new TypeError(`unknown format option: ${{k}}`);
                  }}
                  if (opts.decimals !== undefined) {{
                    if (!Number.isInteger(opts.decimals)) throw new TypeError('decimals must be an integer');
                    if (opts.decimals < 0 || opts.decimals > {max_dec}) throw new RangeError('decimals must be between 0 and {max_dec}');
                  }}
                  for (const k of ['prefix', 'suffix']) {{
                    if (opts[k] !== undefined && typeof opts[k] !== 'string') throw new TypeError(`${{k}} must be a string`);
                  }}
                  this.formats.set(key, {{ ...opts }});
                }}

                getFormat(addr) {{
                  const {{ col, row }} = parse(addr);
                  const f = this.formats.get(format(col, row));
                  return f ? {{ ...f }} : null;
                }}

                display(addr) {{
                  const v = this.get(addr);
                  if (v === null) return '';
                  if (typeof v !== 'number') return String(v);
                  const f = this.getFormat(addr);
                  if (!f) return String(v);
                  const body = f.decimals !== undefined ? v.toFixed(f.decimals) : String(v);
                  return (f.prefix || '') + body + (f.suffix || '');
                }}
            ''',
        },
        readme=f"## Display formats\n\n`sheet.setFormat(addr, {{ decimals, prefix, suffix }})` (decimals 0 to {max_dec}; `null` removes it), `sheet.getFormat(addr)` and `sheet.display(addr)`, which renders numbers with `toFixed(decimals)` plus prefix and suffix and leaves text alone.\n",
        vtests='''
          test('display basic', () => {
            const s = mk();
            s.setFormat('A1', { decimals: 2, prefix: '$' });
            assert.equal(s.display('A1'), '$10.00');
          });
        ''',
        tests=fmt('''
          test('display formats numbers', () => {
            const s = mk();
            assert.equal(s.display('A1'), '10');
            assert.equal(s.display('C3'), '2.5');
            s.setFormat('C3', { decimals: 2 });
            assert.equal(s.display('C3'), '2.50');
            s.setFormat('C3', { decimals: 0 });
            assert.equal(s.display('C3'), '3');
            s.setFormat('A1', { prefix: '$', suffix: ' total' });
            assert.equal(s.display('A1'), '$10 total');
            s.setFormat('A2', { decimals: __M__, suffix: '%' });
            assert.equal(s.display('A2'), '5.' + '0'.repeat(__M__) + '%');
            s.setFormat('A1', { decimals: 1 });
            assert.equal(s.display('A1'), '10.0');
          });

          test('display leaves text and empty cells alone', () => {
            const s = mk();
            s.setFormat('B1', { decimals: 2, prefix: '$', suffix: '!' });
            assert.equal(s.display('B1'), 'apples');
            s.setFormat('D4', { prefix: '$' });
            assert.equal(s.display('D4'), '');
            assert.equal(s.display('Z99'), '');
            s.set('D4', 1);
            assert.equal(s.display('D4'), '$1');
          });

          test('formats can be read, replaced and removed', () => {
            const s = mk();
            assert.equal(s.getFormat('A1'), null);
            s.setFormat('A1', { decimals: 1, prefix: '#' });
            assert.deepEqual(s.getFormat('A1'), { decimals: 1, prefix: '#' });
            s.getFormat('A1').decimals = 5;
            assert.equal(s.getFormat('A1').decimals, 1);
            s.setFormat('A1', { suffix: 'x' });
            assert.deepEqual(s.getFormat('A1'), { suffix: 'x' });
            assert.equal(s.display('A1'), '10x');
            s.setFormat('A1', null);
            assert.equal(s.getFormat('A1'), null);
            assert.equal(s.display('A1'), '10');
            s.setFormat('A1', {});
            assert.deepEqual(s.getFormat('A1'), {});
            assert.equal(s.display('A1'), '10');
          });

          test('format validation', () => {
            const s = mk();
            assert.throws(() => s.setFormat('A1', { decimals: -1 }), RangeError);
            assert.throws(() => s.setFormat('A1', { decimals: __M__ + 1 }), RangeError);
            assert.throws(() => s.setFormat('A1', { decimals: 1.5 }), TypeError);
            assert.throws(() => s.setFormat('A1', { decimals: '2' }), TypeError);
            assert.throws(() => s.setFormat('A1', { prefix: 5 }), TypeError);
            assert.throws(() => s.setFormat('A1', { suffix: null }), TypeError);
            assert.throws(() => s.setFormat('A1', { color: 'red' }), TypeError);
            assert.throws(() => s.setFormat('A1', 'bold'), TypeError);
            assert.throws(() => s.setFormat('A1', ['x']), TypeError);
            assert.throws(() => s.setFormat('A0', {}), RangeError);
            assert.equal(s.getFormat('A1'), null);
            assert.throws(() => s.getFormat('nope'), RangeError);
            assert.throws(() => s.display('nope'), RangeError);
          });
        ''', M=max_dec),
        cross={
            "formulas": {"tests": '''
              test('display of a formula cell', () => {
                const s = new Sheet();
                s.set('A1', 10);
                s.set('A2', 4);
                s.set('B1', '=A1/A2');
                s.set('B2', '=A1/0');
                s.setFormat('B1', { decimals: 1, suffix: 'x' });
                s.setFormat('B2', { decimals: 1, prefix: '$' });
                assert.equal(s.display('B1'), '2.5x');
                assert.equal(s.display('B2'), '#DIV/0!');
              });
            '''},
        },
    ))

    S.append(Slice(
        id="formulas", title="Formulas", d=4,
        pitch=("The budget sheet is only a table of numbers and every total is typed in by hand.",
               "Cells should be able to compute their value from other cells."),
        reqs=("A string that starts with `=` is now a formula. `sheet.get(addr)` returns its current value, computed from the cells it refers to every time it is asked (so changing a cell changes everything that depends on it), and `sheet.formula(addr)` returns the source text, `null` for cells that are not formulas. `grid()` and `display`-style readers see the computed values.",
              "Syntax: numbers (`12`, `1.5`), cell references (`A1`; case-insensitive), the binary operators `+ - * /` (`*` and `/` bind tighter, all left to right), unary minus, parentheses, and blanks between tokens. A reference to an empty cell counts as 0.",
              "A formula whose value cannot be computed does not throw: `get` returns an error string instead. `#SYNTAX!` for text that does not parse (including `=` alone), `#NAME?` for an identifier that is not a valid cell address (`FOO`, `A100`, `AA1`), `#VALUE!` for a reference to a text cell, `#DIV/0!` for a division by zero and `#CYCLE!` for formulas that depend on themselves, directly or through other cells (every cell on the cycle, and every formula that depends on one, reports it). Parsing comes first: a formula with a syntax error is `#SYNTAX!` even if it also divides by zero. An error in a referenced cell is passed on: the formula gets the same error string."),
        code={
            "src/sheet.js::helpers": FORMULA_HELPERS,
            "src/sheet.js::init": "this._stack = new Set();",
            "src/sheet.js::eval_method": FORMULA_METHODS,
        },
        readme="## Formulas\n\nStrings starting with `=` are formulas (`+ - * /`, unary minus, parentheses, cell references, numbers). `get` returns the computed value or an error string (`#SYNTAX!`, `#NAME?`, `#VALUE!`, `#DIV/0!`, `#CYCLE!`); `formula(addr)` returns the source.\n",
        vtests='''
          test('formulas basic', () => {
            const s = mk();
            s.set('D1', '=A1+A2*2');
            assert.equal(s.get('D1'), 20);
            assert.equal(s.formula('D1'), '=A1+A2*2');
          });
        ''',
        tests='''
          function sheet() {
            const s = new Sheet();
            s.set('A1', 10);
            s.set('A2', 4);
            s.set('C1', 'abc');
            return s;
          }

          test('formulas compute', () => {
            const s = sheet();
            const cases = [
              ['=A1+A2*2', 18], ['=(A1+A2)*2', 28], ['=A1/A2', 2.5], ['=-A1+3', -7], ['= 1 + 2 ', 3], ['=2*3+4*5', 26],
              ['=10-4-3', 3], ['=100/10/5', 2], ['=1.5*2', 3], ['=a1+a2', 14], ['=B9+1', 1], ['=--A2', 4], ['=A1-(A2-1)', 7],
              ['=(((5)))', 5], ['=-(A1+A2)', -14], ['=7', 7],
            ];
            for (const [src, want] of cases) {
              s.set('E1', src);
              assert.equal(s.get('E1'), want, src);
            }
          });

          test('formulas are live and chainable', () => {
            const s = sheet();
            s.set('B1', '=A1+A2');
            s.set('B2', '=B1*2');
            s.set('B3', '=B2+B1+A1');
            assert.equal(s.get('B3'), 52);
            s.set('A1', 20);
            assert.equal(s.get('B1'), 24);
            assert.equal(s.get('B3'), 92);
            s.set('B1', 1);
            assert.equal(s.get('B2'), 2);
            assert.equal(s.formula('B1'), null);
            assert.equal(s.formula('B2'), '=B1*2');
            assert.equal(s.formula('A1'), null);
            assert.equal(s.formula('C1'), null);
            assert.equal(s.formula('D9'), null);
            assert.throws(() => s.formula('nope'), RangeError);
          });

          test('only a leading equals sign makes a formula', () => {
            const s = sheet();
            s.set('B1', ' =A1');
            s.set('B2', 'A1+A2');
            assert.equal(s.get('B1'), ' =A1');
            assert.equal(s.get('B2'), 'A1+A2');
            assert.equal(s.formula('B1'), null);
            s.set('B3', '=A1');
            assert.deepEqual(s.grid()[2], [null, 10, null]);
            assert.deepEqual(s.grid()[0], [10, ' =A1', 'abc']);
          });

          test('formula errors', () => {
            const s = sheet();
            const cases = [
              ['=A1/0', '#DIV/0!'], ['=A1/(A2-4)', '#DIV/0!'], ['=C1+1', '#VALUE!'], ['=1+', '#SYNTAX!'], ['=(1+2', '#SYNTAX!'],
              ['=1 2', '#SYNTAX!'], ['=', '#SYNTAX!'], ['=1 $ 2', '#SYNTAX!'], ['=)', '#SYNTAX!'], ['=*2', '#SYNTAX!'],
              ['=FOO', '#NAME?'], ['=A100', '#NAME?'], ['=AA1', '#NAME?'], ['=A0+1', '#NAME?'], ['=.5', '#SYNTAX!'],
              ['=1/0+', '#SYNTAX!'], ['=C1/0', '#VALUE!'],
            ];
            for (const [src, want] of cases) {
              assert.doesNotThrow(() => s.set('E1', src), src);
              assert.equal(s.get('E1'), want, src);
            }
          });

          test('errors are passed on', () => {
            const s = sheet();
            s.set('D1', '=A1/0');
            s.set('D2', '=D1+1');
            s.set('D3', '=D2*2+A1');
            s.set('D4', '=(1+');
            s.set('D5', '=D4+D1');
            s.set('D6', '=D1+D4');
            assert.deepEqual([s.get('D1'), s.get('D2'), s.get('D3'), s.get('D4')], ['#DIV/0!', '#DIV/0!', '#DIV/0!', '#SYNTAX!']);
            assert.equal(s.get('D5'), '#SYNTAX!');
            assert.equal(s.get('D6'), '#DIV/0!');
            s.set('D7', '#DIV/0!');
            s.set('D8', '=D7+1');
            assert.equal(s.get('D7'), '#DIV/0!');
            assert.equal(s.get('D8'), '#VALUE!');
            s.set('A1', 5);
            assert.equal(s.get('D1'), '#DIV/0!');
            s.set('D1', 8);
            assert.deepEqual([s.get('D2'), s.get('D3')], [9, 23]);
          });

          test('cycles', () => {
            const s = sheet();
            s.set('E1', '=E2');
            s.set('E2', '=E1');
            s.set('F1', '=F1');
            s.set('G1', '=E1+1');
            s.set('G2', '=A1+F1');
            assert.deepEqual(['E1', 'E2', 'F1', 'G1', 'G2'].map((a) => s.get(a)), Array(5).fill('#CYCLE!'));
            s.set('E2', 5);
            assert.equal(s.get('E1'), 5);
            assert.equal(s.get('G1'), 6);
            assert.equal(s.get('F1'), '#CYCLE!');
            s.set('H1', '=H2+1');
            s.set('H2', '=H3*2');
            s.set('H3', '=H1');
            assert.equal(s.get('H2'), '#CYCLE!');
            s.set('H3', 1);
            assert.equal(s.get('H1'), 3);
          });
        ''',
    ))

    S.append(Slice(
        id="functions", title="Spreadsheet functions", d=3, needs=("formulas",),
        pitch=("Summing a column means typing a formula with twenty plus signs.",
               "Formulas need the usual aggregate functions over ranges of cells."),
        reqs=(f"Formulas can call `SUM`, `{avg}`, `MIN`, `MAX` and `COUNT` (names are case-insensitive). Arguments are separated by commas and each is either a range `A1:B3` (a rectangle, corners in any order) or an ordinary expression, which must evaluate to a number; calls can be nested in expressions and in arguments. At least one argument is required.",
              f"Inside a range, empty and text cells are ignored; an error value in a range cell is passed on (the first one in row order). `SUM` of nothing is 0, `{avg}` is the sum divided by the number of numbers (`#DIV/0!` when there are none), `MIN` and `MAX` of nothing are 0 and `COUNT` is the number of numeric values among all arguments. A single reference argument to a text cell is `#VALUE!` as everywhere else.",
              f"An unknown function name (including `{other_avg}`) is `#NAME?`, checked before the arguments are evaluated. Missing arguments, a missing parenthesis, a trailing comma or a range outside a function call is `#SYNTAX!`; a range with an invalid corner (`A1:A100`) is `#NAME?`. Cells that refer to themselves through a range are `#CYCLE!`."),
        code={
            "src/sheet.js::formula_ops": "const OPS = '+-*/(),:';",
            "src/sheet.js::parse_helpers": '''
                function argument() {
                  if (tokens[pos] && tokens[pos].t === 'id' && tokens[pos + 1] && tokens[pos + 1].t === ':') {
                    const a = tokens[pos].v;
                    const second = tokens[pos + 2];
                    if (!second || second.t !== 'id') throw new FormulaError('#SYNTAX!');
                    pos += 3;
                    return { t: 'range', a, b: second.v };
                  }
                  return expr();
                }
            ''',
            "src/sheet.js::primary_id": '''
                if (is('(')) {
                  pos++;
                  const args = [argument()];
                  while (is(',')) {
                    pos++;
                    args.push(argument());
                  }
                  if (!is(')')) throw new FormulaError('#SYNTAX!');
                  pos++;
                  return { t: 'call', name: tk.v, args };
                }
            ''',
            "src/sheet.js::eval_cases": f'''
                case 'call': {{
                  const fn = {{
                    SUM: (xs) => xs.reduce((a, b) => a + b, 0),
                    {avg}: (xs) => {{
                      if (xs.length === 0) throw new FormulaError('#DIV/0!');
                      return xs.reduce((a, b) => a + b, 0) / xs.length;
                    }},
                    MIN: (xs) => (xs.length ? Math.min(...xs) : 0),
                    MAX: (xs) => (xs.length ? Math.max(...xs) : 0),
                    COUNT: (xs) => xs.length,
                  }}[node.name];
                  if (!fn) throw new FormulaError('#NAME?');
                  const values = [];
                  for (const arg of node.args) {{
                    if (arg.t === 'range') values.push(...sheet._rangeNumbers(arg));
                    else values.push(evaluateFormula(sheet, arg));
                  }}
                  return fn(values);
                }}
                case 'range':
                  throw new FormulaError('#SYNTAX!');
            ''',
            "src/sheet.js::methods": '''
                /** The numbers inside a range; text and empty cells are skipped, errors are passed on. */
                _rangeNumbers(range) {
                  if (!ADDR.test(range.a) || !ADDR.test(range.b)) throw new FormulaError('#NAME?');
                  const a = parse(range.a);
                  const b = parse(range.b);
                  const out = [];
                  for (let r = Math.min(a.row, b.row); r <= Math.max(a.row, b.row); r++) {
                    for (let c = Math.min(a.col, b.col); c <= Math.max(a.col, b.col); c++) {
                      const v = this._evalKey(format(c, r));
                      if (typeof v === 'number') out.push(v);
                    }
                  }
                  return out;
                }
            ''',
        },
        readme=f"## Spreadsheet functions\n\nFormulas can call `SUM`, `{avg}`, `MIN`, `MAX` and `COUNT` with ranges (`A1:B3`) and expressions as comma-separated arguments. Empty and text cells inside ranges are ignored; `{avg}` of nothing is `#DIV/0!`; unknown names are `#NAME?`.\n",
        vtests='''
          test('functions basic', () => {
            const s = mk();
            s.set('D1', '=SUM(A1:A2)');
            assert.equal(s.get('D1'), 15);
          });
        ''',
        tests=fmt('''
          function data() {
            const s = new Sheet();
            s.set('A1', 10);
            s.set('A2', 4);
            s.set('A3', 'text');
            s.set('B1', 2);
            s.set('B2', 6);
            return s;
          }

          test('functions over ranges', () => {
            const s = data();
            const cases = [
              ['=SUM(A1:A4)', 14], ['=SUM(A1:B2)', 22], ['=SUM(B2:A1)', 22], ['=SUM(A1, B1, 5)', 17], ['=SUM(A1:A2, 100)', 114],
              ['=__AVG__(A1:A3)', 7], ['=MIN(A1:B2)', 2], ['=MAX(A1:B2)', 10], ['=MIN(C1:C3)', 0], ['=MAX(C1:C3)', 0],
              ['=COUNT(A1:B4)', 4], ['=SUM(A1:A2)*2', 28], ['=SUM(A1:A2)+SUM(B1:B2)', 22], ['=sum(a1:a2)', 14],
              ['=SUM(A1:A2, MIN(B1:B2))', 16], ['=COUNT(A1:A2, 7, B1)', 4], ['=SUM(C1:C3)', 0], ['=MAX(A1:B2)-MIN(A1:B2)', 8],
              ['=SUM(A1)', 10], ['=-SUM(A2:B2)', -10], ['=SUM(SUM(A1:A2), 1)', 15],
            ];
            for (const [src, want] of cases) {
              s.set('E1', src);
              assert.equal(s.get('E1'), want, src);
            }
          });

          test('function errors', () => {
            const s = data();
            s.set('C1', '=1/0');
            const cases = [
              ['=__AVG__(D1:D3)', '#DIV/0!'], ['=FOO(A1)', '#NAME?'], ['=__OTHER__(A1:A2)', '#NAME?'],
              ['=SUM()', '#SYNTAX!'], ['=SUM(A1:A2', '#SYNTAX!'], ['=A1:A2', '#SYNTAX!'], ['=SUM(A1:)', '#SYNTAX!'],
              ['=SUM(A1,)', '#SYNTAX!'], ['=SUM(,A1)', '#SYNTAX!'], ['=SUM(A1:A100)', '#NAME?'], ['=SUM(A3)', '#VALUE!'],
              ['=SUM(C1:C2)', '#DIV/0!'], ['=FOO()', '#SYNTAX!'], ['=FOO(1/0)', '#NAME?'], ['=SUM(1/0)', '#DIV/0!'],
              ['=SUM(A1:A2)+', '#SYNTAX!'], ['=MIN(A1:B2) MAX(A1:B2)', '#SYNTAX!'], ['=SUM(A1:A2:B2)', '#SYNTAX!'],
            ];
            for (const [src, want] of cases) {
              s.set('E1', src);
              assert.equal(s.get('E1'), want, src);
            }
          });

          test('function cycles', () => {
            const s = data();
            s.set('A5', '=SUM(A1:A5)');
            assert.equal(s.get('A5'), '#CYCLE!');
            s.set('B5', '=A5+1');
            assert.equal(s.get('B5'), '#CYCLE!');
            s.set('A5', '=SUM(A1:A4)');
            assert.equal(s.get('A5'), 14);
            assert.equal(s.get('B5'), 15);
          });
        ''', AVG=avg, OTHER=other_avg),
    ))

    S.append(Slice(
        id="csv", title="CSV export and import", d=3,
        pitch=("The finance people live in another spreadsheet program and send their numbers around as text files.",
               "Sheets must be exportable to and importable from CSV."),
        reqs=("`sheet.toCsv()` writes the used rectangle (column A to the last used column, row 1 to the last used row): one line per row, fields separated by commas, every line ending in `\\n`; numbers as `String(n)`, empty cells as nothing, text as it is unless it contains a comma, a double quote or a line break, in which case it is wrapped in double quotes with inner quotes doubled. An empty sheet gives `''`.",
              "`Sheet.fromCsv(text)` is a static method that builds a new sheet: fields are separated by commas, a quoted field may contain commas, doubled quotes and line breaks, lines end with `\\n` or `\\r\\n`, and the line break after the last row is optional. A field is a number when it looks like `-12` or `3.5` (also when it was quoted), empty fields are empty cells, everything else is text. Rows may have different lengths. An unterminated quote is a `SyntaxError`; more than 26 columns or 99 rows is a `RangeError`. `''` gives an empty sheet."),
        code={
            "src/sheet.js::helpers": '''
                function csvField(v) {
                  if (v === null) return '';
                  if (typeof v === 'number') return String(v);
                  return /[",\\r\\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
                }

                function parseCsv(text) {
                  const rows = [];
                  let row = [];
                  let field = '';
                  let quoted = false;
                  let pending = false;
                  for (let i = 0; i < text.length; i++) {
                    const c = text[i];
                    if (quoted) {
                      if (c === '"' && text[i + 1] === '"') {
                        field += '"';
                        i++;
                      } else if (c === '"') {
                        quoted = false;
                      } else {
                        field += c;
                      }
                      continue;
                    }
                    if (c === '"') {
                      quoted = true;
                      pending = true;
                    } else if (c === ',') {
                      row.push(field);
                      field = '';
                      pending = true;
                    } else if (c === '\\n' || (c === '\\r' && text[i + 1] === '\\n')) {
                      if (c === '\\r') i++;
                      row.push(field);
                      rows.push(row);
                      row = [];
                      field = '';
                      pending = false;
                    } else {
                      field += c;
                      pending = true;
                    }
                  }
                  if (quoted) throw new SyntaxError('unterminated quote');
                  if (pending) {
                    row.push(field);
                    rows.push(row);
                  }
                  return rows;
                }
            ''',
            "src/sheet.js::methods": '''
                toCsv() {
                  const { columns, rows } = this.used();
                  let out = '';
                  for (let r = 1; r <= rows; r++) {
                    const line = [];
                    for (let c = 1; c <= columns; c++) {
                      const key = format(c, r);
                      line.push(csvField(this.cells.has(key) ? this.cells.get(key) : null));
                    }
                    out += line.join(',') + '\\n';
                  }
                  return out;
                }

                static fromCsv(text) {
                  const rows = parseCsv(String(text));
                  if (rows.length > 99) throw new RangeError('too many rows');
                  const sheet = new Sheet();
                  rows.forEach((fields, r) => {
                    if (fields.length > 26) throw new RangeError('too many columns');
                    fields.forEach((f, c) => {
                      sheet.set(format(c + 1, r + 1), /^-?\\d+(\\.\\d+)?$/.test(f) ? Number(f) : f);
                    });
                  });
                  return sheet;
                }
            ''',
        },
        readme="## CSV export and import\n\n`sheet.toCsv()` writes the used rectangle as CSV (quotes only where needed); `Sheet.fromCsv(text)` reads it back (numbers like `-12` and `3.5` become numbers, empty fields stay empty, `SyntaxError` for an unterminated quote, `RangeError` beyond the grid).\n",
        vtests='''
          test('csv basic', () => {
            const s = mk();
            assert.equal(s.toCsv().split('\\n')[0], '10,apples,');
          });
        ''',
        tests='''
          test('toCsv', () => {
            assert.equal(new Sheet().toCsv(), '');
            assert.equal(mk().toCsv(), '10,apples,\\n5,"pears, ripe",\\n,,2.5\\n');
            const s = new Sheet();
            s.set('A1', 'say "hi"');
            s.set('B1', 'two\\nlines');
            s.set('C1', ' spaced ');
            s.set('A2', -3);
            s.set('C2', 0.25);
            assert.equal(s.toCsv(), '"say ""hi""","two\\nlines", spaced \\n-3,,0.25\\n');
          });

          test('fromCsv', () => {
            const s = Sheet.fromCsv('name,qty\\r\\napples,3\\r\\n"pears, ripe",-2.5\\n,\\n"say ""hi""","a\\nb"\\n');
            assert.deepEqual(s.grid(), [['name', 'qty'], ['apples', 3], ['pears, ripe', -2.5], [null, null], ['say "hi"', 'a\\nb']]);
            const ragged = Sheet.fromCsv('1,2,3\\n4\\n\\n7,,9');
            assert.deepEqual(ragged.grid(), [[1, 2, 3], [4, null, null], [null, null, null], [7, null, 9]]);
            assert.equal(Sheet.fromCsv('').size(), 0);
            assert.equal(Sheet.fromCsv('\\n').size(), 0);
            assert.equal(Sheet.fromCsv('"5",007,1.,.5,1e3,x').get('A1'), 5);
            assert.deepEqual(Sheet.fromCsv('"5",007,1.,.5,1e3,x').grid(), [[5, 7, '1.', '.5', '1e3', 'x']]);
          });

          test('csv round trip and errors', () => {
            const s = mk();
            s.set('D2', 'quote " and, comma');
            const back = Sheet.fromCsv(s.toCsv());
            assert.deepEqual(back.grid(), s.grid());
            assert.equal(back.toCsv(), s.toCsv());
            assert.throws(() => Sheet.fromCsv('a,"b'), SyntaxError);
            assert.throws(() => Sheet.fromCsv('"abc'), SyntaxError);
            assert.throws(() => Sheet.fromCsv(Array(27).fill('x').join(',')), RangeError);
            assert.equal(Sheet.fromCsv(Array(26).fill('x').join(',')).size(), 26);
            assert.throws(() => Sheet.fromCsv('x\\n'.repeat(100)), RangeError);
            assert.equal(Sheet.fromCsv('x\\n'.repeat(99)).size(), 99);
          });
        ''',
        cross={
            "formulas": {
                "reqs": ("Formula cells are written as their source text (so `=A1+1`, not the computed value) and read back as formulas: a field that starts with `=` becomes a formula, like with `set`.",),
                "tests": '''
                  test('csv keeps formulas', () => {
                    const s = new Sheet();
                    s.set('A1', 4);
                    s.set('B1', '=A1*2');
                    s.set('C1', '=1/0');
                    assert.equal(s.toCsv(), '4,=A1*2,=1/0\\n');
                    const back = Sheet.fromCsv(s.toCsv());
                    assert.equal(back.formula('B1'), '=A1*2');
                    assert.deepEqual(back.grid(), [[4, 8, '#DIV/0!']]);
                  });
                '''},
            "functions": {"tests": '''
              test('csv quotes formulas with commas', () => {
                const s = new Sheet();
                s.set('A1', 1);
                s.set('A2', 2);
                s.set('B1', '=SUM(A1, A2)');
                assert.equal(s.toCsv(), '1,"=SUM(A1, A2)"\\n2,\\n');
                assert.equal(Sheet.fromCsv(s.toCsv()).get('B1'), 3);
              });
            '''},
        },
    ))

    S.append(Slice(
        id="undo", title="Undo and redo", d=3,
        pitch=("Somebody pasted over a column of numbers and the only fix was to retype it from an email.",
               "The sheet needs undo and redo for changes to cell contents."),
        reqs=(f"`sheet.undo()` reverts the latest change and `sheet.redo()` re-applies the latest reverted one; both return `true` when they did something and `false` when there was nothing to do. `sheet.canUndo()` and `sheet.canRedo()` tell which of them would do something.",
              f"Every `set` is one step, and a call that changes nothing (same value, or emptying an empty cell) is not a step. The sheet remembers the last {undo_limit} steps; older ones are forgotten. A new change after an `undo` discards the steps that could have been redone. `Sheet.fromCsv` and other readers are not steps."),
        code={
            "src/sheet.js::init": f'''
                this._undo = [];
                this._redo = [];
                this._replaying = false;
                this._undoLimit = {undo_limit};
            ''',
            "src/sheet.js::apply_pre": "if (!this._replaying) this._record(changes);",
            "src/sheet.js::methods": '''
                _record(changes) {
                  const undo = [];
                  const redo = [];
                  for (const [key, raw] of changes) {
                    const prev = this.cells.has(key) ? this.cells.get(key) : null;
                    if (prev !== raw) {
                      undo.push([key, prev]);
                      redo.push([key, raw]);
                    }
                  }
                  if (undo.length === 0) return;
                  this._undo.push({ undo, redo });
                  if (this._undo.length > this._undoLimit) this._undo.shift();
                  this._redo = [];
                }

                _replay(changes) {
                  this._replaying = true;
                  try {
                    this._apply(changes);
                  } finally {
                    this._replaying = false;
                  }
                }

                canUndo() {
                  return this._undo.length > 0;
                }

                canRedo() {
                  return this._redo.length > 0;
                }

                undo() {
                  const step = this._undo.pop();
                  if (!step) return false;
                  this._replay(step.undo);
                  this._redo.push(step);
                  return true;
                }

                redo() {
                  const step = this._redo.pop();
                  if (!step) return false;
                  this._replay(step.redo);
                  this._undo.push(step);
                  return true;
                }
            ''',
        },
        readme=f"## Undo and redo\n\n`undo()`, `redo()` (return whether they did something), `canUndo()`, `canRedo()`. Each `set` that changes something is one step; the last {undo_limit} steps are kept; a new change clears the redo history.\n",
        vtests='''
          test('undo basic', () => {
            const s = mk();
            s.set('A1', 99);
            assert.equal(s.undo(), true);
            assert.equal(s.get('A1'), 10);
          });
        ''',
        tests=fmt('''
          test('undo and redo walk through the history', () => {
            const s = new Sheet();
            assert.deepEqual([s.canUndo(), s.canRedo(), s.undo(), s.redo()], [false, false, false, false]);
            s.set('A1', 1);
            s.set('A1', 2);
            s.set('B1', 'x');
            assert.equal(s.canUndo(), true);
            assert.equal(s.undo(), true);
            assert.equal(s.get('B1'), null);
            assert.equal(s.canRedo(), true);
            assert.equal(s.undo(), true);
            assert.equal(s.get('A1'), 1);
            assert.equal(s.undo(), true);
            assert.equal(s.get('A1'), null);
            assert.equal(s.size(), 0);
            assert.deepEqual([s.canUndo(), s.undo()], [false, false]);
            assert.equal(s.redo(), true);
            assert.equal(s.redo(), true);
            assert.equal(s.redo(), true);
            assert.deepEqual([s.get('A1'), s.get('B1')], [2, 'x']);
            assert.deepEqual([s.canRedo(), s.redo()], [false, false]);
            assert.equal(s.undo(), true);
            assert.equal(s.redo(), true);
            assert.equal(s.get('B1'), 'x');
          });

          test('new changes discard the redo history, no-ops are not steps', () => {
            const s = new Sheet();
            s.set('A1', 1);
            s.set('A1', 1);
            s.set('B1', null);
            s.set('C1', '');
            assert.equal(s.undo(), true);
            assert.equal(s.get('A1'), null);
            assert.equal(s.undo(), false);
            s.set('A1', 1);
            s.set('A1', 2);
            s.undo();
            assert.equal(s.canRedo(), true);
            s.set('B1', 'x');
            assert.equal(s.canRedo(), false);
            assert.equal(s.redo(), false);
            s.set('B1', 'x');
            assert.equal(s.canRedo(), false);
            s.undo();
            assert.equal(s.canRedo(), true);
            s.set('B1', 'x');
            assert.equal(s.canRedo(), false);
            assert.equal(s.get('A1'), 1);
          });

          test('the history is limited', () => {
            const s = new Sheet();
            const n = __N__ + 2;
            for (let i = 1; i <= n; i++) s.set('A' + i, i);
            let undone = 0;
            while (s.undo()) undone++;
            assert.equal(undone, __N__);
            assert.equal(s.size(), 2);
            let redone = 0;
            while (s.redo()) redone++;
            assert.equal(redone, __N__);
            assert.equal(s.size(), n);
          });
        ''', N=undo_limit),
        cross={
            "clear-range": {"tests": '''
              test('clearing a range is one step', () => {
                const s = mk();
                s.clearRange('A1:B2');
                assert.equal(s.size(), 1);
                assert.equal(s.undo(), true);
                assert.deepEqual(s.addresses(), ['A1', 'B1', 'A2', 'B2', 'C3']);
                assert.equal(s.get('B2'), 'pears, ripe');
                assert.equal(s.redo(), true);
                assert.equal(s.size(), 1);
                const t = mk();
                const before = t.size();
                t.clearRange('E5:F6');
                assert.equal(t.size(), before);
                t.set('E5', 1);
                assert.equal(t.undo(), true);
                assert.equal(t.get('E5'), null);
                assert.equal(t.get('A1'), 10);
              });
            '''},
            "format": {
                "reqs": ("Formats are not part of the history: `setFormat` is not a step and `undo` leaves formats alone.",),
                "tests": '''
                  test('formats are not undone', () => {
                    const s = new Sheet();
                    s.set('A1', 5);
                    s.setFormat('A1', { prefix: '$' });
                    s.set('A1', 6);
                    assert.equal(s.undo(), true);
                    assert.equal(s.display('A1'), '$5');
                    assert.equal(s.undo(), true);
                    assert.equal(s.undo(), false);
                    assert.deepEqual(s.getFormat('A1'), { prefix: '$' });
                  });
                '''},
            "formulas": {"tests": '''
              test('undo restores formulas', () => {
                const s = new Sheet();
                s.set('A1', 2);
                s.set('B1', '=A1*10');
                s.set('B1', 7);
                assert.equal(s.get('B1'), 7);
                s.undo();
                assert.equal(s.formula('B1'), '=A1*10');
                assert.equal(s.get('B1'), 20);
                s.set('A1', 3);
                assert.equal(s.get('B1'), 30);
                s.undo();
                assert.equal(s.get('B1'), 20);
              });
            '''},
            "fill": {"tests": '''
              test('a fill is one step', () => {
                const s = new Sheet();
                s.set('A1', 1);
                s.set('B1', '=A1+1');
                s.fillDown('B1:B4');
                assert.equal(s.undo(), true);
                assert.deepEqual(s.addresses(), ['A1', 'B1']);
                assert.equal(s.redo(), true);
                assert.equal(s.formula('B4'), '=A4+1');
              });
            '''},
        },
    ))

    S.append(Slice(
        id="fill", title="Fill down", d=4, needs=("formulas",),
        pitch=("Copying a formula down a column of three hundred rows... is fine, but doing it cell by cell is not.",
               "Users want to drag a formula down a column like in any other spreadsheet."),
        reqs=("`sheet.fillDown(range)` copies the top cell of a one-column range into the cells below it and returns how many cells it wrote (the number of rows minus one). The range is written as for `clearRange`-style ranges (`C1:C5`, corners in any order; a range that spans more than one column is a `RangeError`, and so is any invalid range). A one-row range changes nothing and returns 0.",
              "Numbers and text are copied as they are; an empty top cell empties the cells below. For a formula the cell references (`A1`, case kept) are moved down by the distance from the top cell, so `=B1*2` copied three rows down becomes `=B4*2`; references to empty or text cells are shifted too and numbers are left alone. If any shifted reference would leave rows 1 to 99, nothing at all is changed and a `RangeError` is thrown. Formats are not copied."),
        code={
            "src/sheet.js::helpers": '''
                /** Moves the cell references of a formula down by `delta` rows. */
                function shiftFormula(src, delta) {
                  return src.replace(/(?<![A-Za-z0-9.])([A-Za-z])([0-9]{1,2})(?![A-Za-z0-9(])/g, (m, letter, row) => {
                    const n = Number(row) + delta;
                    if (n < 1 || n > 99) throw new RangeError(`the fill would leave the grid at ${m}`);
                    return letter + n;
                  });
                }
            ''',
            "src/sheet.js::methods": '''
                fillDown(range) {
                  const { c1, r1, c2, r2 } = parseRange(range);
                  if (c1 !== c2) throw new RangeError('fillDown needs a single column');
                  const top = format(c1, r1);
                  const source = this.cells.has(top) ? this.cells.get(top) : null;
                  const changes = [];
                  for (let r = r1 + 1; r <= r2; r++) {
                    let raw = source;
                    if (typeof source === 'string' && source.startsWith('=')) raw = shiftFormula(source, r - r1);
                    changes.push([format(c1, r), raw]);
                  }
                  this._apply(changes);
                  return changes.length;
                }
            ''',
        },
        readme="## Fill down\n\n`sheet.fillDown('C1:C5')` copies the top cell down a one-column range, shifting the cell references of formulas by the row distance; it returns the number of cells written and throws a `RangeError` (changing nothing) for bad ranges or when a reference would leave the grid.\n",
        vtests='''
          test('fill basic', () => {
            const s = mk();
            assert.equal(s.fillDown('A1:A3'), 2);
            assert.equal(s.get('A3'), 10);
          });
        ''',
        tests='''
          test('fillDown shifts formulas', () => {
            const s = new Sheet();
            s.set('A1', 1);
            [10, 20, 30].forEach((v, i) => s.set('B' + (i + 1), v));
            s.set('C1', '=B1*2+A1');
            assert.equal(s.fillDown('C1:C3'), 2);
            assert.equal(s.formula('C2'), '=B2*2+A2');
            assert.equal(s.formula('C3'), '=B3*2+A3');
            assert.deepEqual([s.get('C1'), s.get('C2'), s.get('C3')], [21, 40, 60]);
            s.set('D3', '=b3+a3+2.5');
            assert.equal(s.fillDown('D6:D3'), 3);
            assert.equal(s.formula('D6'), '=b6+a6+2.5');
            assert.equal(s.formula('D4'), '=b4+a4+2.5');
            assert.equal(s.formula('D3'), '=b3+a3+2.5');
          });

          test('fillDown copies plain values and empties', () => {
            const col = (sh, letter) => [1, 2, 3, 4].map((r) => sh.get(letter + r));
            const s = new Sheet();
            s.set('A1', 7);
            s.set('B1', 'text');
            s.set('B3', 'old');
            s.set('C2', 'old');
            s.set('C3', 'old');
            assert.equal(s.fillDown('A1:A4'), 3);
            assert.deepEqual(col(s, 'A'), [7, 7, 7, 7]);
            assert.equal(s.fillDown('B1:B3'), 2);
            assert.deepEqual(col(s, 'B'), ['text', 'text', 'text', null]);
            assert.equal(s.fillDown('C1:C3'), 2);
            assert.deepEqual(col(s, 'C'), [null, null, null, null]);
            assert.equal(s.fillDown('A2:A2'), 0);
            assert.equal(s.fillDown('A2'), 0);
          });

          test('fillDown validation is all or nothing', () => {
            const s = new Sheet();
            s.set('B98', 5);
            s.set('H97', '=B98+1');
            s.set('H98', 'keep');
            assert.throws(() => s.fillDown('H97:H99'), RangeError);
            assert.equal(s.get('H98'), 'keep');
            assert.equal(s.get('H99'), null);
            s.set('H1', '=B1');
            assert.equal(s.fillDown('H1:H3'), 2);
            assert.equal(s.formula('H3'), '=B3');
          });

          test('fillDown range errors', () => {
            const s = new Sheet();
            s.set('A1', 1);
            for (const bad of ['A1:B3', 'A1:', 'a1:a3', 'A1:A100', '', null, 5]) assert.throws(() => s.fillDown(bad), RangeError, String(bad));
            assert.equal(s.size(), 1);
          });
        ''',
        cross={
            "functions": {"tests": '''
              test('fillDown shifts ranges inside functions', () => {
                const s = new Sheet();
                [1, 2, 3, 4].forEach((v, i) => s.set('A' + (i + 1), v));
                s.set('B1', '=SUM(A1:A2)+MAX(a1:a1, 0)');
                s.fillDown('B1:B3');
                assert.equal(s.formula('B2'), '=SUM(A2:A3)+MAX(a2:a2, 0)');
                assert.equal(s.formula('B3'), '=SUM(A3:A4)+MAX(a3:a3, 0)');
                assert.deepEqual([s.get('B1'), s.get('B2'), s.get('B3')], [4, 7, 10]);
                s.set('C1', '=SUM(A1:A99)');
                assert.throws(() => s.fillDown('C1:C2'), RangeError);
              });
            '''},
        },
    ))

    return S


APP = App(
    name="cellsheet", lang="javascript", title="the spreadsheet engine", role="a budgeting tool developer", key="CELL",
    base={
        "README.md": README + "\n@@blocks features\n",
        "package.json": '{\n  "name": "cellsheet",\n  "version": "1.0.0",\n  "private": true,\n  "main": "index.js",\n  "scripts": {\n    "test": "node --test test/*.test.js"\n  }\n}\n',
        "index.js": "'use strict';\nmodule.exports = require('./src/sheet');\n",
        "src/address.js": ADDRESS,
        "src/sheet.js": SHEET,
        ".gitignore": "node_modules/\n",
    },
    visible={"test/basic.test.js": VISIBLE},
    hidden={"test/features.test.js": HIDDEN},
    verify="node --test test/*.test.js",
)

register_app("feature-js-cellsheet", APP, make_slices, n=18, summary="spreadsheet engine: rows, ranges, formats, formulas, functions, CSV, undo, fill")
