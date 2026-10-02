"""Parameterised WHERE/ORDER BY builder (javascript): bugs injected into a small query-builder library."""
from fx import Lib, dd
from generators.fix._lang2 import JS_VERIFY, PACKAGE_JSON, register_libs

README = dd(r'''
    # wherekit

    Builds the `WHERE` and `ORDER BY` parts of a SQL query from plain objects, with bound parameters. CommonJS:
    `const { buildWhere } = require('./src/where')` and `const { orderBy, limitOffset } = require('./src/order')`.

    ## Identifiers

    A column name is an identifier `[A-Za-z_][A-Za-z0-9_]*`, optionally qualified with one table name
    (`orders.total`). Anything else is a `TypeError`. With the option `quote: true` every part is wrapped in double
    quotes (`"orders"."total"`), otherwise names are written as they are.

    ## `buildWhere(filter, opts = {})` returns `{ sql, params }`

    `filter` is an object. Its entries are *conditions* joined with `AND` in key order. `undefined` values are skipped.
    An empty filter gives `{ sql: '', params: [] }`; otherwise `sql` starts with `WHERE `.

    Value forms for a column `c`:

    | value | SQL |
    |---|---|
    | string, number, boolean | `c = ?` |
    | `Date` | `c = ?` with the parameter `date.toISOString()` |
    | `null` | `c IS NULL` |
    | array | `c IN (?, ?, ...)`; an empty array gives `1 = 0`; `null` entries are removed from the list and add `OR c IS NULL`: `(c IN (?, ?) OR c IS NULL)`; if only nulls remain the condition is just `c IS NULL` |
    | object | one condition per operator key, in key order, joined with `AND` |

    Operators inside an object: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte` (symbols `=`, `<>`, `>`, `>=`, `<`, `<=`),
    `$like` (`c LIKE ?`), `$in`, `$nin` (`c NOT IN (?, ...)`), `$between` (`c BETWEEN ? AND ?`, the value must be an
    array of exactly two items, else `TypeError`) and `$null` (`true` gives `c IS NULL`, `false` gives
    `c IS NOT NULL`). `$eq: null` is `IS NULL`; `$ne: null` is `IS NOT NULL`. `$in: []` is `1 = 0`; `$nin: []` adds no
    condition at all. An unknown operator is a `TypeError`. When an object holds more than one operator, the
    conditions of that column are joined with `AND` and are not wrapped in parentheses.

    Logical keys: `$or` and `$and` take an array of filters, `$not` takes one filter. Each sub-filter is built as above
    and its conditions are joined with `AND`; a sub-filter with two or more conditions is wrapped in parentheses when it
    is combined.

    * `$or`: the sub-filters joined with `OR`. An empty array gives `1 = 0`. If one of the sub-filters is empty (it matches
      everything) the whole `$or` adds no condition.
    * `$and`: the sub-filters joined with `AND`; an empty array adds no condition.
    * `$not`: `NOT (<sub-filter>)`; an empty sub-filter gives `1 = 0`.
    * A group with more than one part is wrapped in parentheses: `(a = ? OR b = ?)`. A group with a single part is that
      part, unwrapped. The top-level conditions are never wrapped.

    Placeholders are `?` by default. With `placeholder: 'numbered'` they are `$1`, `$2`, ... in the order the
    parameters appear in the final text.

    ## `orderBy(spec, opts = {})`

    `spec` is a comma-separated string (`'-created, name'`) or an array of such items. A leading `-` means descending,
    anything else ascending; surrounding spaces are ignored and empty items are dropped. The result is
    `ORDER BY created DESC, name ASC` (identifier rules and `quote` as above), or `''` when there are no items.
    A column may appear only once: a repeated column is a `TypeError`.

    ## `limitOffset(limit, offset = 0)`

    `LIMIT n` or `LIMIT n OFFSET m`; `OFFSET` is left out when `offset` is `0`. `limit` must be an integer from `1` to
    `1000`, `offset` an integer `>= 0`, otherwise `RangeError`.
''')

IDENT = dd(r'''
    'use strict';

    const IDENT = /^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$/;

    function column(name, quote) {
      if (typeof name !== 'string' || !IDENT.test(name)) {
        throw new TypeError(`bad column name: ${String(name)}`);
      }
      if (!quote) return name;
      return name.split('.').map((part) => `"${part}"`).join('.');
    }

    module.exports = { column };
''')

WHERE = dd(r'''
    'use strict';

    const { column } = require('./ident');

    const SYMBOLS = { $eq: '=', $ne: '<>', $gt: '>', $gte: '>=', $lt: '<', $lte: '<=' };

    function bindable(v) {
      return v instanceof Date ? v.toISOString() : v;
    }

    function join(parts, word) {
      return parts.length > 1 ? `(${parts.join(` ${word} `)})` : parts[0];
    }

    function inList(col, values, negate, out) {
      const list = values.filter((v) => v !== null);
      const hasNull = list.length !== values.length;
      if (list.length === 0) {
        if (hasNull) return `${col} IS ${negate ? 'NOT ' : ''}NULL`;
        return negate ? null : '1 = 0';
      }
      for (const v of list) out.push(bindable(v));
      const marks = list.map(() => '?').join(', ');
      if (negate) {
        const base = `${col} NOT IN (${marks})`;
        return hasNull ? `(${base} AND ${col} IS NOT NULL)` : base;
      }
      const base = `${col} IN (${marks})`;
      return hasNull ? `(${base} OR ${col} IS NULL)` : base;
    }

    function operatorConditions(col, spec, out) {
      const parts = [];
      for (const op of Object.keys(spec)) {
        const v = spec[op];
        if (v === undefined) continue;
        if (op in SYMBOLS) {
          if (v === null && (op === '$eq' || op === '$ne')) {
            parts.push(`${col} IS ${op === '$ne' ? 'NOT ' : ''}NULL`);
          } else {
            out.push(bindable(v));
            parts.push(`${col} ${SYMBOLS[op]} ?`);
          }
        } else if (op === '$like') {
          out.push(v);
          parts.push(`${col} LIKE ?`);
        } else if (op === '$in' || op === '$nin') {
          if (!Array.isArray(v)) throw new TypeError(`${op} needs an array`);
          const text = inList(col, v, op === '$nin', out);
          if (text !== null) parts.push(text);
        } else if (op === '$between') {
          if (!Array.isArray(v) || v.length !== 2) throw new TypeError('$between needs [low, high]');
          out.push(bindable(v[0]), bindable(v[1]));
          parts.push(`${col} BETWEEN ? AND ?`);
        } else if (op === '$null') {
          parts.push(`${col} IS ${v ? '' : 'NOT '}NULL`);
        } else {
          throw new TypeError(`unknown operator ${op}`);
        }
      }
      return parts;
    }

    function conditions(filter, quote, out) {
      const parts = [];
      for (const key of Object.keys(filter)) {
        const v = filter[key];
        if (v === undefined) continue;
        if (key === '$or' || key === '$and') {
          if (!Array.isArray(v)) throw new TypeError(`${key} needs an array`);
          const bound = [];
          const subs = v.map((f) => conditions(f, quote, bound));
          if (key === '$or') {
            if (subs.length === 0) {
              parts.push('1 = 0');
            } else if (!subs.some((s) => s.length === 0)) {
              out.push(...bound);
              parts.push(join(subs.map((s) => join(s, 'AND')), 'OR'));
            }
          } else {
            const flat = subs.filter((s) => s.length > 0).map((s) => join(s, 'AND'));
            out.push(...bound);
            if (flat.length > 0) parts.push(join(flat, 'AND'));
          }
        } else if (key === '$not') {
          const sub = conditions(v, quote, out);
          parts.push(sub.length === 0 ? '1 = 0' : `NOT (${sub.join(' AND ')})`);
        } else {
          const col = column(key, quote);
          if (v === null) {
            parts.push(`${col} IS NULL`);
          } else if (Array.isArray(v)) {
            parts.push(inList(col, v, false, out));
          } else if (typeof v === 'object' && !(v instanceof Date)) {
            parts.push(...operatorConditions(col, v, out));
          } else {
            out.push(bindable(v));
            parts.push(`${col} = ?`);
          }
        }
      }
      return parts;
    }

    function buildWhere(filter, opts = {}) {
      const params = [];
      const parts = conditions(filter, !!opts.quote, params);
      if (parts.length === 0) return { sql: '', params: [] };
      let sql = parts.join(' AND ');
      if (opts.placeholder === 'numbered') {
        let n = 0;
        sql = sql.replace(/\?/g, () => `$${++n}`);
      }
      return { sql: `WHERE ${sql}`, params };
    }

    module.exports = { buildWhere };
''')

ORDER = dd(r'''
    'use strict';

    const { column } = require('./ident');

    function orderBy(spec, opts = {}) {
      const items = (Array.isArray(spec) ? spec : [spec]).flatMap((s) => String(s).split(','));
      const seen = new Set();
      const parts = [];
      for (const raw of items) {
        const item = raw.trim();
        if (item === '') continue;
        const desc = item.startsWith('-');
        const name = desc ? item.slice(1).trim() : item;
        if (seen.has(name)) throw new TypeError(`column ordered twice: ${name}`);
        seen.add(name);
        parts.push(`${column(name, !!opts.quote)} ${desc ? 'DESC' : 'ASC'}`);
      }
      return parts.length === 0 ? '' : `ORDER BY ${parts.join(', ')}`;
    }

    function limitOffset(limit, offset = 0) {
      if (!Number.isInteger(limit) || limit < 1 || limit > 1000) throw new RangeError('limit must be an integer from 1 to 1000');
      if (!Number.isInteger(offset) || offset < 0) throw new RangeError('offset must be an integer >= 0');
      return offset === 0 ? `LIMIT ${limit}` : `LIMIT ${limit} OFFSET ${offset}`;
    }

    module.exports = { orderBy, limitOffset };
''')

VISIBLE = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { buildWhere } = require('../src/where');
    const { orderBy } = require('../src/order');

    test('plain equality and null', () => {
      assert.deepEqual(buildWhere({ status: 'open', owner: null }), {
        sql: 'WHERE status = ? AND owner IS NULL',
        params: ['open'],
      });
    });

    test('empty filter', () => {
      assert.deepEqual(buildWhere({}), { sql: '', params: [] });
    });

    test('order by', () => {
      assert.equal(orderBy('-created,name'), 'ORDER BY created DESC, name ASC');
    });
''')

HIDDEN = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { buildWhere } = require('../src/where');
    const { orderBy, limitOffset } = require('../src/order');
    const { column } = require('../src/ident');

    const w = (filter, opts) => buildWhere(filter, opts);

    test('scalars bind in key order', () => {
      assert.deepEqual(w({ a: 1, b: 'x', c: true, d: 0, e: '' }), {
        sql: 'WHERE a = ? AND b = ? AND c = ? AND d = ? AND e = ?',
        params: [1, 'x', true, 0, ''],
      });
    });

    test('undefined values are skipped, null is not', () => {
      assert.deepEqual(w({ a: undefined, b: null }), { sql: 'WHERE b IS NULL', params: [] });
      assert.deepEqual(w({ a: undefined }), { sql: '', params: [] });
    });

    test('dates bind as ISO strings', () => {
      const d = new Date(Date.UTC(2024, 1, 29, 12, 30, 0));
      assert.deepEqual(w({ at: d }), { sql: 'WHERE at = ?', params: ['2024-02-29T12:30:00.000Z'] });
      assert.deepEqual(w({ at: { $gte: d } }), { sql: 'WHERE at >= ?', params: ['2024-02-29T12:30:00.000Z'] });
      assert.deepEqual(w({ at: { $between: [d, d] } }).params, ['2024-02-29T12:30:00.000Z', '2024-02-29T12:30:00.000Z']);
      assert.deepEqual(w({ at: [d] }).params, ['2024-02-29T12:30:00.000Z']);
    });

    test('arrays become IN lists', () => {
      assert.deepEqual(w({ id: [1, 2, 3] }), { sql: 'WHERE id IN (?, ?, ?)', params: [1, 2, 3] });
      assert.deepEqual(w({ id: [7] }), { sql: 'WHERE id IN (?)', params: [7] });
    });

    test('empty arrays match nothing', () => {
      assert.deepEqual(w({ id: [] }), { sql: 'WHERE 1 = 0', params: [] });
      assert.deepEqual(w({ id: { $in: [] } }), { sql: 'WHERE 1 = 0', params: [] });
      assert.deepEqual(w({ a: 1, id: [] }), { sql: 'WHERE a = ? AND 1 = 0', params: [1] });
    });

    test('nulls inside arrays', () => {
      assert.deepEqual(w({ id: [1, null, 2] }), { sql: 'WHERE (id IN (?, ?) OR id IS NULL)', params: [1, 2] });
      assert.deepEqual(w({ id: [null] }), { sql: 'WHERE id IS NULL', params: [] });
      assert.deepEqual(w({ id: [null, null] }), { sql: 'WHERE id IS NULL', params: [] });
      assert.deepEqual(w({ id: { $nin: [null] } }), { sql: 'WHERE id IS NOT NULL', params: [] });
      assert.deepEqual(w({ id: { $nin: [3, null] } }), { sql: 'WHERE (id NOT IN (?) AND id IS NOT NULL)', params: [3] });
    });

    test('comparison operators', () => {
      assert.deepEqual(w({ n: { $eq: 1 } }), { sql: 'WHERE n = ?', params: [1] });
      assert.deepEqual(w({ n: { $ne: 1 } }), { sql: 'WHERE n <> ?', params: [1] });
      assert.deepEqual(w({ n: { $gt: 1 } }), { sql: 'WHERE n > ?', params: [1] });
      assert.deepEqual(w({ n: { $gte: 1 } }), { sql: 'WHERE n >= ?', params: [1] });
      assert.deepEqual(w({ n: { $lt: 1 } }), { sql: 'WHERE n < ?', params: [1] });
      assert.deepEqual(w({ n: { $lte: 0 } }), { sql: 'WHERE n <= ?', params: [0] });
    });

    test('null comparisons', () => {
      assert.deepEqual(w({ n: { $eq: null } }), { sql: 'WHERE n IS NULL', params: [] });
      assert.deepEqual(w({ n: { $ne: null } }), { sql: 'WHERE n IS NOT NULL', params: [] });
      assert.deepEqual(w({ n: { $null: true } }), { sql: 'WHERE n IS NULL', params: [] });
      assert.deepEqual(w({ n: { $null: false } }), { sql: 'WHERE n IS NOT NULL', params: [] });
      assert.deepEqual(w({ n: { $null: 0 } }), { sql: 'WHERE n IS NOT NULL', params: [] });
    });

    test('like, in, nin, between', () => {
      assert.deepEqual(w({ name: { $like: 'ab%' } }), { sql: 'WHERE name LIKE ?', params: ['ab%'] });
      assert.deepEqual(w({ n: { $in: [1, 2] } }), { sql: 'WHERE n IN (?, ?)', params: [1, 2] });
      assert.deepEqual(w({ n: { $nin: [1, 2] } }), { sql: 'WHERE n NOT IN (?, ?)', params: [1, 2] });
      assert.deepEqual(w({ n: { $nin: [] } }), { sql: '', params: [] });
      assert.deepEqual(w({ a: 1, n: { $nin: [] }, b: 2 }), { sql: 'WHERE a = ? AND b = ?', params: [1, 2] });
      assert.deepEqual(w({ n: { $between: [5, 9] } }), { sql: 'WHERE n BETWEEN ? AND ?', params: [5, 9] });
    });

    test('several operators on one column are ANDed without parentheses', () => {
      assert.deepEqual(w({ n: { $gte: 3, $lt: 9, $ne: 5 } }), { sql: 'WHERE n >= ? AND n < ? AND n <> ?', params: [3, 9, 5] });
      assert.deepEqual(w({ a: 1, n: { $gt: 1, $lt: 4 }, b: 2 }), { sql: 'WHERE a = ? AND n > ? AND n < ? AND b = ?', params: [1, 1, 4, 2] });
      assert.deepEqual(w({ n: { $gt: undefined, $lt: 4 } }), { sql: 'WHERE n < ?', params: [4] });
      assert.deepEqual(w({ n: {} }), { sql: '', params: [] });
    });

    test('operator errors', () => {
      assert.throws(() => w({ n: { $regex: 'x' } }), TypeError);
      assert.throws(() => w({ n: { $in: 3 } }), TypeError);
      assert.throws(() => w({ n: { $nin: 'ab' } }), TypeError);
      assert.throws(() => w({ n: { $between: [1] } }), TypeError);
      assert.throws(() => w({ n: { $between: [1, 2, 3] } }), TypeError);
      assert.throws(() => w({ n: { $between: 4 } }), TypeError);
      assert.throws(() => w({ $or: {} }), TypeError);
      assert.throws(() => w({ $and: { a: 1 } }), TypeError);
    });

    test('$or groups', () => {
      assert.deepEqual(w({ $or: [{ a: 1 }, { b: 2 }] }), { sql: 'WHERE (a = ? OR b = ?)', params: [1, 2] });
      assert.deepEqual(w({ $or: [{ a: 1 }] }), { sql: 'WHERE a = ?', params: [1] });
      assert.deepEqual(w({ x: 0, $or: [{ a: 1 }, { b: 2 }, { c: 3 }] }), { sql: 'WHERE x = ? AND (a = ? OR b = ? OR c = ?)', params: [0, 1, 2, 3] });
    });

    test('$or with multi-condition members wraps them', () => {
      assert.deepEqual(w({ $or: [{ a: 1, b: 2 }, { c: 3 }] }), { sql: 'WHERE ((a = ? AND b = ?) OR c = ?)', params: [1, 2, 3] });
      assert.deepEqual(w({ $or: [{ a: 1 }, { b: 2, c: 3 }] }), { sql: 'WHERE (a = ? OR (b = ? AND c = ?))', params: [1, 2, 3] });
    });

    test('$or edge cases', () => {
      assert.deepEqual(w({ $or: [] }), { sql: 'WHERE 1 = 0', params: [] });
      assert.deepEqual(w({ a: 1, $or: [] }), { sql: 'WHERE a = ? AND 1 = 0', params: [1] });
      assert.deepEqual(w({ $or: [{ a: 1 }, {}] }), { sql: '', params: [] });
      assert.deepEqual(w({ a: 9, $or: [{}, { a: 1 }] }), { sql: 'WHERE a = ?', params: [9] });
      assert.deepEqual(w({ a: 9, $or: [{ b: 2 }, { c: 3 }, {}], d: 4 }), { sql: 'WHERE a = ? AND d = ?', params: [9, 4] });
    });

    test('$and groups', () => {
      assert.deepEqual(w({ $and: [{ a: 1 }, { b: 2 }] }), { sql: 'WHERE (a = ? AND b = ?)', params: [1, 2] });
      assert.deepEqual(w({ $and: [{ a: 1 }] }), { sql: 'WHERE a = ?', params: [1] });
      assert.deepEqual(w({ $and: [] }), { sql: '', params: [] });
      assert.deepEqual(w({ $and: [{}, { a: 1 }, {}] }), { sql: 'WHERE a = ?', params: [1] });
      assert.deepEqual(w({ $and: [{ a: 1, b: 2 }, { c: 3 }] }), { sql: 'WHERE ((a = ? AND b = ?) AND c = ?)', params: [1, 2, 3] });
    });

    test('$not', () => {
      assert.deepEqual(w({ $not: { a: 1 } }), { sql: 'WHERE NOT (a = ?)', params: [1] });
      assert.deepEqual(w({ $not: { a: 1, b: 2 } }), { sql: 'WHERE NOT (a = ? AND b = ?)', params: [1, 2] });
      assert.deepEqual(w({ $not: {} }), { sql: 'WHERE 1 = 0', params: [] });
      assert.deepEqual(w({ $not: { $or: [{ a: 1 }, { b: 2 }] } }), { sql: 'WHERE NOT ((a = ? OR b = ?))', params: [1, 2] });
    });

    test('nesting keeps parameter order', () => {
      const f = { a: 1, $or: [{ b: { $gt: 2 } }, { $and: [{ c: [3, 4] }, { d: { $between: [5, 6] } }] }], e: 7 };
      assert.deepEqual(w(f), {
        sql: 'WHERE a = ? AND (b > ? OR (c IN (?, ?) AND d BETWEEN ? AND ?)) AND e = ?',
        params: [1, 2, 3, 4, 5, 6, 7],
      });
    });

    test('qualified and quoted identifiers', () => {
      assert.deepEqual(w({ 'orders.total': { $gt: 10 } }), { sql: 'WHERE orders.total > ?', params: [10] });
      assert.deepEqual(w({ 'orders.total': { $gt: 10 }, status: 'x' }, { quote: true }), { sql: 'WHERE "orders"."total" > ? AND "status" = ?', params: [10, 'x'] });
      assert.deepEqual(w({ _a1: null }, { quote: true }), { sql: 'WHERE "_a1" IS NULL', params: [] });
      assert.deepEqual(w({ $or: [{ 'a.b': 1 }, { c: [] }] }, { quote: true }), { sql: 'WHERE ("a"."b" = ? OR 1 = 0)', params: [1] });
    });

    test('bad column names', () => {
      for (const bad of ['1a', 'a b', 'a-b', 'a.b.c', '.a', 'a.', 'a;drop', '"a"', '']) {
        assert.throws(() => w({ [bad]: 1 }), TypeError, bad);
      }
      assert.throws(() => column(5), TypeError);
      assert.equal(column('t.x'), 't.x');
      assert.equal(column('t.x', true), '"t"."x"');
    });

    test('numbered placeholders', () => {
      assert.deepEqual(w({ a: 1, b: [2, 3], $or: [{ c: 4 }, { d: { $between: [5, 6] } }] }, { placeholder: 'numbered' }), {
        sql: 'WHERE a = $1 AND b IN ($2, $3) AND (c = $4 OR d BETWEEN $5 AND $6)',
        params: [1, 2, 3, 4, 5, 6],
      });
      const many = w({ a: 1, b: 2, c: 3, d: 4, e: 5, f: 6, g: 7, h: 8, i: 9, j: 10, k: 11 }, { placeholder: 'numbered' });
      assert.ok(many.sql.endsWith('j = $10 AND k = $11'), many.sql);
      assert.deepEqual(w({}, { placeholder: 'numbered' }), { sql: '', params: [] });
      assert.deepEqual(w({ a: 1 }, { placeholder: '?' }), { sql: 'WHERE a = ?', params: [1] });
    });

    test('question marks inside values are left alone', () => {
      assert.deepEqual(w({ a: 'what?' }, { placeholder: 'numbered' }), { sql: 'WHERE a = $1', params: ['what?'] });
    });

    test('orderBy', () => {
      assert.equal(orderBy('name'), 'ORDER BY name ASC');
      assert.equal(orderBy('-name'), 'ORDER BY name DESC');
      assert.equal(orderBy('-created, name ,-id'), 'ORDER BY created DESC, name ASC, id DESC');
      assert.equal(orderBy(['-a', 'b,c']), 'ORDER BY a DESC, b ASC, c ASC');
      assert.equal(orderBy(' - a '), 'ORDER BY a DESC');
      assert.equal(orderBy('t.col'), 'ORDER BY t.col ASC');
      assert.equal(orderBy('-t.col, u', { quote: true }), 'ORDER BY "t"."col" DESC, "u" ASC');
    });

    test('orderBy empties and errors', () => {
      assert.equal(orderBy(''), '');
      assert.equal(orderBy(' , ,'), '');
      assert.equal(orderBy([]), '');
      assert.throws(() => orderBy('a, -a'), TypeError);
      assert.throws(() => orderBy('a,a'), TypeError);
      assert.throws(() => orderBy('a b'), TypeError);
      assert.throws(() => orderBy('--a'), TypeError);
      assert.throws(() => orderBy('-'), TypeError);
    });

    test('limitOffset', () => {
      assert.equal(limitOffset(10), 'LIMIT 10');
      assert.equal(limitOffset(10, 0), 'LIMIT 10');
      assert.equal(limitOffset(10, 30), 'LIMIT 10 OFFSET 30');
      assert.equal(limitOffset(1), 'LIMIT 1');
      assert.equal(limitOffset(1000, 1), 'LIMIT 1000 OFFSET 1');
      assert.throws(() => limitOffset(0), RangeError);
      assert.throws(() => limitOffset(1001), RangeError);
      assert.throws(() => limitOffset(-1), RangeError);
      assert.throws(() => limitOffset(2.5), RangeError);
      assert.throws(() => limitOffset('5'), RangeError);
      assert.throws(() => limitOffset(5, -1), RangeError);
      assert.throws(() => limitOffset(5, 1.5), RangeError);
    });
''')

LIB = Lib(
    name="wherekit", lang="javascript", title="the wherekit query builder",
    blurb="The reporting service builds its list queries with wherekit: a filter object in, parameterised SQL out.",
    files={"package.json": PACKAGE_JSON % "wherekit", "src/ident.js": IDENT,
           "src/where.js": WHERE, "src/order.js": ORDER, "README.md": README, ".gitignore": "node_modules/\n"},
    visible_tests={"test/basic.test.js": VISIBLE},
    hidden_tests={"test/full.test.js": HIDDEN},
    mutate=["src/where.js", "src/order.js", "src/ident.js"], difficulty=3, tags=["sql", "query-builder"],
    verify=JS_VERIFY,
    probe_import="const { buildWhere } = require('./src/where');\nconst { orderBy, limitOffset } = require('./src/order');",
    probes=[
        'buildWhere({ id: [1, null, 2] })',
        'buildWhere({ n: { $gte: 3, $lt: 9 } })',
        'buildWhere({ $or: [{ a: 1 }, { b: 2, c: 3 }] })',
        'buildWhere({ id: [] })',
        'buildWhere({ n: { $nin: [] } })',
        'buildWhere({ n: { $nin: [3, null] } })',
        "orderBy('-created, name')",
        "orderBy('a, -a')",
        'limitOffset(10, 30)',
        'limitOffset(10)',
        "buildWhere({ a: 1, b: [2, 3], c: { $between: [4, 5] } }, { placeholder: 'numbered' })",
        "buildWhere({ 't.x': { $ne: null } }, { quote: true })",
        'buildWhere({ $not: { a: 1, b: 2 } })',
        'buildWhere({ a: 9, $or: [{}, { a: 1 }] })',
        'buildWhere({ n: { $null: false }, m: null })',
        'buildWhere({ $and: [{ a: 1 }, { b: 2 }] })',
        'buildWhere({ at: new Date(Date.UTC(2024, 1, 29)) })',
    ],
)

register_libs([LIB], n=8)
