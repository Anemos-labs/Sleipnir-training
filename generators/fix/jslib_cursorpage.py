"""Keyset pagination with opaque cursors (javascript): bugs injected into a small list-endpoint helper."""
from fx import Lib, dd
from generators.fix._lang2 import JS_VERIFY, PACKAGE_JSON, register_libs

README = dd(r'''
    # cursorpage

    Pagination helpers for list endpoints. Items are plain objects with a unique `id` (string or number).
    CommonJS, no dependencies: `const { paginate, encodeCursor, decodeCursor } = require('./src/cursor')` and
    `const { clampLimit, pageCount, describeRange, pageWindow } = require('./src/pager')`.

    ## Cursors (`src/cursor.js`)

    A *position* is `{ key, id }` where `key` is the value of the sort field and `id` the item's id. Both must be
    strings or finite numbers.

    * `encodeCursor(position)` returns an opaque string. The body is `JSON.stringify([key, id])`, followed by a dot and a
      checksum, and the whole text is encoded as unpadded base64url. The checksum of a text is computed by folding its
      UTF-16 code units: `sum = (sum * 31 + unit) % 9973`, starting at 0, and written in base 36. A key or id that is not a
      string or a finite number is a `TypeError`.
    * `decodeCursor(text)` is the inverse. It returns `null` (never throws) for anything that is not a cursor made by
      `encodeCursor`: not a string, empty, no dot, checksum mismatch, body that is not a JSON array of exactly two
      scalars (string or finite number).

    ## `paginate(items, opts)` (`src/cursor.js`)

    Returns `{ items, next, prev, total }` for one page of `items`. The input array is not modified and the returned
    items are the original objects.

    Options:

    * `sort`: name of the field to sort by, default `'id'`. All values of that field share one type (all numbers or all
      strings, compared with `<` and `>`).
    * `dir`: `'asc'` (default) or `'desc'`. Items are ordered by `(item[sort], item.id)`; the id breaks ties in the same
      direction as the sort.
    * `limit`: page size, normalised with `clampLimit`.
    * `after`: a cursor; the page starts with the first item strictly after that position in the chosen order.
    * `before`: a cursor; the page is the `limit` items that come immediately before that position (the items
      *before* the cursor, the page ends with the last of them), still listed in the chosen order.
    * Giving both `after` and `before` is a `TypeError`. A cursor that `decodeCursor` rejects is a `RangeError`.
      A position that matches no item still works: it simply splits the ordered list.

    Result fields: `total` is the number of input items. `next` is a cursor for the last item on the page, or `null`
    when no item follows the page. `prev` is a cursor for the first item on the page, or `null` when no item precedes
    the page. An empty page has `next` and `prev` both `null`.

    ## Page helpers (`src/pager.js`)

    * `clampLimit(raw, fallback = 20, max = 100)`: `null`, `undefined` and values that are not numbers (after
      `Number(raw)`, so numeric strings work) give `fallback`; otherwise the value is rounded down and kept in
      `[1, max]`.
    * `pageCount(total, perPage)`: number of pages needed for `total` items, `0` when `total <= 0`. `perPage` below `1`
      is a `RangeError`.
    * `describeRange(page, perPage, total)`: human text for 1-based `page`, such as `'21-40 of 95'`. The last page is
      cut at `total` (`'81-95 of 95'`), a single item reads `'7 of 7'`, an empty list reads `'0 of 0'`, and a page
      beyond the last one reads `'none of 95'`.
    * `pageWindow(current, total, around = 1)`: the page links to render, as an array of page numbers and the string
      `'...'`. It always contains page `1` and page `total`, the pages within `around` of `current` (`current` is first
      limited to `[1, total]`), in ascending order. A gap of exactly one hidden page is filled with that page number;
      a longer gap becomes a single `'...'`. `total < 1` gives `[]`.
''')

PAGER = dd(r'''
    'use strict';

    function clampLimit(raw, fallback = 20, max = 100) {
      if (raw === null || raw === undefined) return fallback;
      const n = Math.floor(Number(raw));
      if (!Number.isFinite(n)) return fallback;
      if (n < 1) return 1;
      if (n > max) return max;
      return n;
    }

    function pageCount(total, perPage) {
      if (perPage < 1) throw new RangeError('perPage must be at least 1');
      if (total <= 0) return 0;
      return Math.ceil(total / perPage);
    }

    function describeRange(page, perPage, total) {
      if (total === 0) return '0 of 0';
      const first = (page - 1) * perPage + 1;
      if (first > total) return `none of ${total}`;
      const last = Math.min(page * perPage, total);
      if (first === last) return `${first} of ${total}`;
      return `${first}-${last} of ${total}`;
    }

    function pageWindow(current, total, around = 1) {
      if (total < 1) return [];
      const cur = Math.min(Math.max(current, 1), total);
      const keep = new Set([1, total]);
      for (let p = cur - around; p <= cur + around; p++) {
        if (p >= 1 && p <= total) keep.add(p);
      }
      const pages = [...keep].sort((a, b) => a - b);
      const out = [];
      for (let i = 0; i < pages.length; i++) {
        if (i > 0) {
          const gap = pages[i] - pages[i - 1];
          if (gap === 2) out.push(pages[i] - 1);
          else if (gap > 2) out.push('...');
        }
        out.push(pages[i]);
      }
      return out;
    }

    module.exports = { clampLimit, pageCount, describeRange, pageWindow };
''')

CURSOR = dd(r'''
    'use strict';

    const { clampLimit } = require('./pager');

    function isScalar(v) {
      return typeof v === 'string' || (typeof v === 'number' && Number.isFinite(v));
    }

    function checksum(text) {
      let sum = 0;
      for (let i = 0; i < text.length; i++) {
        sum = (sum * 31 + text.charCodeAt(i)) % 9973;
      }
      return sum.toString(36);
    }

    function encodeCursor(pos) {
      if (!isScalar(pos.key) || !isScalar(pos.id)) throw new TypeError('cursor key and id must be strings or finite numbers');
      const body = JSON.stringify([pos.key, pos.id]);
      return Buffer.from(body + '.' + checksum(body), 'utf8').toString('base64url');
    }

    function decodeCursor(text) {
      if (typeof text !== 'string' || text === '') return null;
      const raw = Buffer.from(text, 'base64url').toString('utf8');
      const dot = raw.lastIndexOf('.');
      if (dot < 0) return null;
      const body = raw.slice(0, dot);
      if (checksum(body) !== raw.slice(dot + 1)) return null;
      let arr;
      try {
        arr = JSON.parse(body);
      } catch (e) {
        return null;
      }
      if (!Array.isArray(arr) || arr.length !== 2) return null;
      if (!isScalar(arr[0]) || !isScalar(arr[1])) return null;
      return { key: arr[0], id: arr[1] };
    }

    function compareValues(a, b) {
      if (a < b) return -1;
      if (a > b) return 1;
      return 0;
    }

    function comparePositions(a, b) {
      const c = compareValues(a.key, b.key);
      return c !== 0 ? c : compareValues(a.id, b.id);
    }

    function positionOf(item, sort) {
      return { key: item[sort], id: item.id };
    }

    function mustDecode(cursor) {
      const pos = decodeCursor(cursor);
      if (pos === null) throw new RangeError('invalid cursor');
      return pos;
    }

    function paginate(items, opts = {}) {
      const sort = opts.sort || 'id';
      const sign = opts.dir === 'desc' ? -1 : 1;
      const limit = clampLimit(opts.limit);
      const hasAfter = opts.after !== undefined && opts.after !== null;
      const hasBefore = opts.before !== undefined && opts.before !== null;
      if (hasAfter && hasBefore) throw new TypeError('after and before cannot be combined');

      const ordered = items.slice().sort((a, b) => sign * comparePositions(positionOf(a, sort), positionOf(b, sort)));
      const firstIndexWhere = (test) => {
        const i = ordered.findIndex(test);
        return i < 0 ? ordered.length : i;
      };

      let start = 0;
      let end = Math.min(limit, ordered.length);
      if (hasAfter) {
        const pos = mustDecode(opts.after);
        start = firstIndexWhere((it) => sign * comparePositions(positionOf(it, sort), pos) > 0);
        end = Math.min(start + limit, ordered.length);
      } else if (hasBefore) {
        const pos = mustDecode(opts.before);
        end = firstIndexWhere((it) => sign * comparePositions(positionOf(it, sort), pos) >= 0);
        start = Math.max(0, end - limit);
      }

      const page = ordered.slice(start, end);
      const next = page.length > 0 && end < ordered.length ? encodeCursor(positionOf(page[page.length - 1], sort)) : null;
      const prev = page.length > 0 && start > 0 ? encodeCursor(positionOf(page[0], sort)) : null;
      return { items: page, next, prev, total: ordered.length };
    }

    module.exports = { encodeCursor, decodeCursor, paginate };
''')

VISIBLE = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { paginate, encodeCursor, decodeCursor } = require('../src/cursor');
    const { pageCount } = require('../src/pager');

    const rows = [1, 2, 3, 4, 5, 6, 7].map((n) => ({ id: n, name: `row${n}` }));

    test('first page', () => {
      const page = paginate(rows, { limit: 3 });
      assert.deepEqual(page.items.map((r) => r.id), [1, 2, 3]);
      assert.equal(page.prev, null);
      assert.notEqual(page.next, null);
    });

    test('cursor round trip', () => {
      const c = encodeCursor({ key: 'abc', id: 9 });
      assert.deepEqual(decodeCursor(c), { key: 'abc', id: 9 });
    });

    test('page count', () => {
      assert.equal(pageCount(95, 20), 5);
    });
''')

HIDDEN = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { paginate, encodeCursor, decodeCursor } = require('../src/cursor');
    const { clampLimit, pageCount, describeRange, pageWindow } = require('../src/pager');

    const ids = (page) => page.items.map((r) => r.id);
    const rows = (n) => Array.from({ length: n }, (_, i) => ({ id: i + 1, name: `row${i + 1}` }));
    const b64 = (s) => Buffer.from(s, 'utf8').toString('base64url');

    function sum(text) {
      let s = 0;
      for (let i = 0; i < text.length; i++) s = (s * 31 + text.charCodeAt(i)) % 9973;
      return s.toString(36);
    }

    test('encodeCursor layout is documented', () => {
      const body = '["ab",7]';
      assert.equal(encodeCursor({ key: 'ab', id: 7 }), b64(body + '.' + sum(body)));
      assert.equal(sum('["ab",7]'), '6rs');
      const body2 = '[12.5,"x"]';
      assert.equal(encodeCursor({ key: 12.5, id: 'x' }), b64(body2 + '.' + sum(body2)));
    });

    test('cursor text is url safe and unpadded', () => {
      for (const key of ['a', 'ab', 'abc', 'zzzz~~~???>>>', 'ünï'])  {
        const c = encodeCursor({ key, id: 1 });
        assert.match(c, /^[A-Za-z0-9_-]+$/);
      }
    });

    test('encodeCursor rejects non scalar parts', () => {
      assert.throws(() => encodeCursor({ key: NaN, id: 1 }), TypeError);
      assert.throws(() => encodeCursor({ key: 'a', id: Infinity }), TypeError);
      assert.throws(() => encodeCursor({ key: null, id: 1 }), TypeError);
      assert.throws(() => encodeCursor({ key: 'a', id: {} }), TypeError);
      assert.throws(() => encodeCursor({ key: true, id: 1 }), TypeError);
    });

    test('decodeCursor round trips', () => {
      const cases = [
        { key: 'a', id: 1 },
        { key: 0, id: 'z' },
        { key: -4.25, id: 'id.with.dots' },
        { key: 'dot.in.key', id: 3 },
        { key: 'ünï ☃', id: 'q' },
        { key: '', id: '' },
      ];
      for (const pos of cases) assert.deepEqual(decodeCursor(encodeCursor(pos)), pos);
    });

    test('decodeCursor rejects garbage with null', () => {
      assert.equal(decodeCursor(undefined), null);
      assert.equal(decodeCursor(null), null);
      assert.equal(decodeCursor(42), null);
      assert.equal(decodeCursor(''), null);
      assert.equal(decodeCursor('!!!'), null);
      assert.equal(decodeCursor(b64('no-dot-here')), null);
      assert.equal(decodeCursor(b64('[1,2].zzz')), null);
    });

    test('decodeCursor verifies the checksum', () => {
      const good = '["ab",7]';
      assert.deepEqual(decodeCursor(b64(good + '.' + sum(good))), { key: 'ab', id: 7 });
      assert.equal(decodeCursor(b64('["ab",8].' + sum(good))), null);
      assert.equal(decodeCursor(b64(good + '.' + sum(good) + '0')), null);
    });

    test('decodeCursor checks the shape of a correctly signed body', () => {
      const sign = (body) => b64(body + '.' + sum(body));
      assert.equal(decodeCursor(sign('not json')), null);
      assert.equal(decodeCursor(sign('{"key":1,"id":2}')), null);
      assert.equal(decodeCursor(sign('[1]')), null);
      assert.equal(decodeCursor(sign('[1,2,3]')), null);
      assert.equal(decodeCursor(sign('[null,2]')), null);
      assert.equal(decodeCursor(sign('[1,[2]]')), null);
      assert.equal(decodeCursor(sign('[true,2]')), null);
      assert.equal(decodeCursor(sign('[1,{"a":1}]')), null);
      assert.deepEqual(decodeCursor(sign('[1,"2"]')), { key: 1, id: '2' });
    });

    test('paginate: first page, defaults', () => {
      const all = rows(45);
      const p = paginate(all);
      assert.equal(p.items.length, 20);
      assert.deepEqual(ids(p).slice(0, 3), [1, 2, 3]);
      assert.equal(p.total, 45);
      assert.equal(p.prev, null);
      assert.deepEqual(decodeCursor(p.next), { key: 20, id: 20 });
      assert.strictEqual(p.items[0], all[0]);
    });

    test('paginate: walking forward visits every item once', () => {
      const all = rows(23);
      const seen = [];
      let cursor;
      let pages = 0;
      do {
        const p = paginate(all, { limit: 5, after: cursor });
        seen.push(...ids(p));
        cursor = p.next;
        pages++;
      } while (cursor);
      assert.equal(pages, 5);
      assert.deepEqual(seen, all.map((r) => r.id));
    });

    test('paginate: last page has no next and a prev', () => {
      const all = rows(23);
      const first = paginate(all, { limit: 20 });
      const last = paginate(all, { limit: 20, after: first.next });
      assert.deepEqual(ids(last), [21, 22, 23]);
      assert.equal(last.next, null);
      assert.deepEqual(decodeCursor(last.prev), { key: 21, id: 21 });
    });

    test('paginate: an exactly full final page has no next', () => {
      const all = rows(10);
      const p = paginate(all, { limit: 5, after: paginate(all, { limit: 5 }).next });
      assert.deepEqual(ids(p), [6, 7, 8, 9, 10]);
      assert.equal(p.next, null);
      const whole = paginate(all, { limit: 10 });
      assert.equal(whole.next, null);
      assert.equal(whole.prev, null);
    });

    test('paginate: walking backward with before', () => {
      const all = rows(23);
      let p = paginate(all, { limit: 5, before: encodeCursor({ key: 23, id: 23 }) });
      assert.deepEqual(ids(p), [18, 19, 20, 21, 22]);
      assert.deepEqual(decodeCursor(p.next), { key: 22, id: 22 });
      assert.deepEqual(decodeCursor(p.prev), { key: 18, id: 18 });
      p = paginate(all, { limit: 5, before: p.prev });
      assert.deepEqual(ids(p), [13, 14, 15, 16, 17]);
      p = paginate(all, { limit: 5, before: encodeCursor({ key: 4, id: 4 }) });
      assert.deepEqual(ids(p), [1, 2, 3]);
      assert.equal(p.prev, null);
      assert.deepEqual(decodeCursor(p.next), { key: 3, id: 3 });
    });

    test('paginate: before the first item is an empty page', () => {
      const p = paginate(rows(5), { limit: 3, before: encodeCursor({ key: 1, id: 1 }) });
      assert.deepEqual(p.items, []);
      assert.equal(p.next, null);
      assert.equal(p.prev, null);
      assert.equal(p.total, 5);
    });

    test('paginate: after the last item is an empty page', () => {
      const p = paginate(rows(5), { limit: 3, after: encodeCursor({ key: 5, id: 5 }) });
      assert.deepEqual(p.items, []);
      assert.equal(p.next, null);
      assert.equal(p.prev, null);
    });

    test('paginate: before the cursor never includes the cursor item', () => {
      const p = paginate(rows(9), { limit: 100, before: encodeCursor({ key: 5, id: 5 }) });
      assert.deepEqual(ids(p), [1, 2, 3, 4]);
      assert.deepEqual(decodeCursor(p.next), { key: 4, id: 4 });
      assert.equal(p.prev, null);
    });

    test('paginate: after is exclusive', () => {
      const p = paginate(rows(9), { limit: 2, after: encodeCursor({ key: 4, id: 4 }) });
      assert.deepEqual(ids(p), [5, 6]);
    });

    test('paginate: a cursor position that matches no item still splits the list', () => {
      const all = [{ id: 10 }, { id: 20 }, { id: 30 }, { id: 40 }];
      assert.deepEqual(ids(paginate(all, { limit: 2, after: encodeCursor({ key: 25, id: 25 }) })), [30, 40]);
      assert.deepEqual(ids(paginate(all, { limit: 2, before: encodeCursor({ key: 25, id: 25 }) })), [10, 20]);
    });

    test('paginate: sorts by a field and breaks ties by id', () => {
      const all = [
        { id: 'c', score: 5 },
        { id: 'a', score: 9 },
        { id: 'd', score: 5 },
        { id: 'b', score: 1 },
        { id: 'e', score: 9 },
      ];
      assert.deepEqual(ids(paginate(all, { sort: 'score', limit: 10 })), ['b', 'c', 'd', 'a', 'e']);
      const p = paginate(all, { sort: 'score', limit: 2 });
      assert.deepEqual(ids(p), ['b', 'c']);
      assert.deepEqual(decodeCursor(p.next), { key: 5, id: 'c' });
      const q = paginate(all, { sort: 'score', limit: 2, after: p.next });
      assert.deepEqual(ids(q), ['d', 'a']);
      const r = paginate(all, { sort: 'score', limit: 2, after: q.next });
      assert.deepEqual(ids(r), ['e']);
      assert.equal(r.next, null);
    });

    test('paginate: descending order reverses keys and ties', () => {
      const all = [
        { id: 'c', score: 5 },
        { id: 'a', score: 9 },
        { id: 'd', score: 5 },
        { id: 'b', score: 1 },
        { id: 'e', score: 9 },
      ];
      assert.deepEqual(ids(paginate(all, { sort: 'score', dir: 'desc', limit: 10 })), ['e', 'a', 'd', 'c', 'b']);
      const p = paginate(all, { sort: 'score', dir: 'desc', limit: 2 });
      assert.deepEqual(ids(p), ['e', 'a']);
      const q = paginate(all, { sort: 'score', dir: 'desc', limit: 2, after: p.next });
      assert.deepEqual(ids(q), ['d', 'c']);
      assert.equal(q.next === null, false);
      const back = paginate(all, { sort: 'score', dir: 'desc', limit: 2, before: q.prev });
      assert.deepEqual(ids(back), ['e', 'a']);
      assert.equal(back.prev, null);
    });

    test('paginate: string keys compare with < and >', () => {
      const all = [{ id: 1, name: 'pear' }, { id: 2, name: 'apple' }, { id: 3, name: 'fig' }, { id: 4, name: 'Zucchini' }];
      assert.deepEqual(ids(paginate(all, { sort: 'name', limit: 10 })), [4, 2, 3, 1]);
      assert.deepEqual(ids(paginate(all, { sort: 'name', dir: 'desc', limit: 2 })), [1, 3]);
    });

    test('paginate: does not modify its input', () => {
      const all = [{ id: 3 }, { id: 1 }, { id: 2 }];
      paginate(all, { limit: 2 });
      assert.deepEqual(all.map((r) => r.id), [3, 1, 2]);
    });

    test('paginate: empty input', () => {
      const p = paginate([]);
      assert.deepEqual(p, { items: [], next: null, prev: null, total: 0 });
    });

    test('paginate: option errors', () => {
      const c = encodeCursor({ key: 1, id: 1 });
      assert.throws(() => paginate(rows(3), { after: c, before: c }), TypeError);
      assert.throws(() => paginate(rows(3), { after: 'garbage' }), RangeError);
      assert.throws(() => paginate(rows(3), { before: 'garbage' }), RangeError);
      assert.throws(() => paginate(rows(3), { after: '' }), RangeError);
    });

    test('paginate: null cursors count as absent', () => {
      const p = paginate(rows(5), { limit: 2, after: null, before: null });
      assert.deepEqual(ids(p), [1, 2]);
      const q = paginate(rows(5), { limit: 2, after: undefined, before: encodeCursor({ key: 4, id: 4 }) });
      assert.deepEqual(ids(q), [2, 3]);
    });

    test('paginate: limit is normalised', () => {
      assert.equal(paginate(rows(300), { limit: 1000 }).items.length, 100);
      assert.equal(paginate(rows(300), { limit: '7' }).items.length, 7);
      assert.equal(paginate(rows(300), { limit: 0 }).items.length, 1);
      assert.equal(paginate(rows(300), { limit: -5 }).items.length, 1);
      assert.equal(paginate(rows(300), { limit: 2.9 }).items.length, 2);
      assert.equal(paginate(rows(300), { limit: 'many' }).items.length, 20);
    });

    test('clampLimit', () => {
      assert.equal(clampLimit(undefined), 20);
      assert.equal(clampLimit(null), 20);
      assert.equal(clampLimit(null, 5), 5);
      assert.equal(clampLimit(NaN, 8), 8);
      assert.equal(clampLimit('abc', 8), 8);
      assert.equal(clampLimit(Infinity), 20);
      assert.equal(clampLimit(10), 10);
      assert.equal(clampLimit('12'), 12);
      assert.equal(clampLimit(1), 1);
      assert.equal(clampLimit(0), 1);
      assert.equal(clampLimit(0.5), 1);
      assert.equal(clampLimit(-3), 1);
      assert.equal(clampLimit(100), 100);
      assert.equal(clampLimit(101), 100);
      assert.equal(clampLimit(500, 20, 50), 50);
      assert.equal(clampLimit(49.99, 20, 50), 49);
    });

    test('pageCount', () => {
      assert.equal(pageCount(0, 10), 0);
      assert.equal(pageCount(-4, 10), 0);
      assert.equal(pageCount(1, 10), 1);
      assert.equal(pageCount(10, 10), 1);
      assert.equal(pageCount(11, 10), 2);
      assert.equal(pageCount(95, 20), 5);
      assert.equal(pageCount(100, 20), 5);
      assert.equal(pageCount(7, 1), 7);
      assert.throws(() => pageCount(10, 0), RangeError);
      assert.throws(() => pageCount(0, 0), RangeError);
      assert.throws(() => pageCount(10, -1), RangeError);
    });

    test('describeRange', () => {
      assert.equal(describeRange(1, 20, 95), '1-20 of 95');
      assert.equal(describeRange(2, 20, 95), '21-40 of 95');
      assert.equal(describeRange(5, 20, 95), '81-95 of 95');
      assert.equal(describeRange(5, 19, 95), '77-95 of 95');
      assert.equal(describeRange(6, 20, 95), 'none of 95');
      assert.equal(describeRange(5, 20, 100), '81-100 of 100');
      assert.equal(describeRange(6, 20, 100), 'none of 100');
      assert.equal(describeRange(1, 20, 7), '1-7 of 7');
      assert.equal(describeRange(1, 5, 1), '1 of 1');
      assert.equal(describeRange(2, 5, 6), '6 of 6');
      assert.equal(describeRange(1, 10, 0), '0 of 0');
      assert.equal(describeRange(3, 10, 0), '0 of 0');
    });

    test('pageWindow: short ranges show every page', () => {
      assert.deepEqual(pageWindow(1, 1), [1]);
      assert.deepEqual(pageWindow(1, 2), [1, 2]);
      assert.deepEqual(pageWindow(2, 3), [1, 2, 3]);
      assert.deepEqual(pageWindow(3, 5), [1, 2, 3, 4, 5]);
      assert.deepEqual(pageWindow(1, 0), []);
      assert.deepEqual(pageWindow(4, -2), []);
    });

    test('pageWindow: ellipsis only hides two or more pages', () => {
      assert.deepEqual(pageWindow(1, 10), [1, 2, '...', 10]);
      assert.deepEqual(pageWindow(5, 10), [1, '...', 4, 5, 6, '...', 10]);
      assert.deepEqual(pageWindow(10, 10), [1, '...', 9, 10]);
      assert.deepEqual(pageWindow(4, 10), [1, 2, 3, 4, 5, '...', 10]);
      assert.deepEqual(pageWindow(7, 10), [1, '...', 6, 7, 8, 9, 10]);
      assert.deepEqual(pageWindow(3, 9), [1, 2, 3, 4, '...', 9]);
    });

    test('pageWindow: around widens the window', () => {
      assert.deepEqual(pageWindow(10, 20, 2), [1, '...', 8, 9, 10, 11, 12, '...', 20]);
      assert.deepEqual(pageWindow(2, 20, 0), [1, 2, '...', 20]);
      assert.deepEqual(pageWindow(10, 20, 0), [1, '...', 10, '...', 20]);
      assert.deepEqual(pageWindow(1, 8, 3), [1, 2, 3, 4, '...', 8]);
    });

    test('pageWindow: current is limited to the valid range', () => {
      assert.deepEqual(pageWindow(0, 10), [1, 2, '...', 10]);
      assert.deepEqual(pageWindow(-7, 10), [1, 2, '...', 10]);
      assert.deepEqual(pageWindow(99, 10), [1, '...', 9, 10]);
    });
''')

LIB = Lib(
    name="cursorpage", lang="javascript", title="the cursorpage pagination library",
    blurb="The list endpoints of the admin API use these helpers to page through records with opaque cursors and to render page links.",
    files={"package.json": PACKAGE_JSON % "cursorpage", "src/cursor.js": CURSOR,
           "src/pager.js": PAGER, "README.md": README, ".gitignore": "node_modules/\n"},
    visible_tests={"test/basic.test.js": VISIBLE},
    hidden_tests={"test/full.test.js": HIDDEN},
    mutate=["src/cursor.js", "src/pager.js"], difficulty=2, tags=["pagination", "cursor", "api"],
    verify=JS_VERIFY,
    probe_import="const { paginate, encodeCursor, decodeCursor } = require('./src/cursor');\nconst { clampLimit, pageCount, describeRange, pageWindow } = require('./src/pager');",
    probes=[
        'clampLimit(500, 20, 50)',
        'clampLimit(null)',
        "clampLimit('12')",
        'clampLimit(0)',
        'pageCount(100, 20)',
        'pageCount(0, 20)',
        'describeRange(5, 20, 95)',
        'describeRange(6, 20, 95)',
        'describeRange(2, 5, 6)',
        'pageWindow(5, 10)',
        'pageWindow(1, 10)',
        'pageWindow(4, 10)',
        'pageWindow(10, 20, 2)',
        "decodeCursor(encodeCursor({ key: 'ab', id: 7 }))",
        "decodeCursor('garbage')",
        'paginate(Array.from({ length: 5 }, (_, i) => ({ id: i + 1 })), { limit: 2 }).items.map((r) => r.id)',
        'decodeCursor(paginate(Array.from({ length: 5 }, (_, i) => ({ id: i + 1 })), { limit: 2 }).next)',
        'paginate(Array.from({ length: 5 }, (_, i) => ({ id: i + 1 })), { limit: 2, after: encodeCursor({ key: 2, id: 2 }) }).items.map((r) => r.id)',
        'paginate(Array.from({ length: 5 }, (_, i) => ({ id: i + 1 })), { limit: 2, before: encodeCursor({ key: 4, id: 4 }) }).items.map((r) => r.id)',
        'paginate(Array.from({ length: 5 }, (_, i) => ({ id: i + 1 })), { limit: 2, after: encodeCursor({ key: 4, id: 4 }) }).next',
    ],
)

register_libs([LIB], n=8)
