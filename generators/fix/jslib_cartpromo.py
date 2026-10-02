"""Shopping-cart pricing with promotions (javascript): bugs injected into a promotion engine."""
from fx import Lib, dd
from generators.fix._lang2 import JS_VERIFY, PACKAGE_JSON, register_libs

README = dd(r'''
    # cartpromo

    Prices a shop cart with promotions. Money is an integer number of cents. CommonJS:
    `const { priceCart } = require('./src/cart')`, `const { isActive, matches, lineDiscount, roundHalfUp } = require('./src/promos')`.

    ## Input

    * A cart *line* is `{ sku, qty, unit, tags }`: `qty` a positive integer, `unit` a non-negative integer (cents per
      unit), `tags` an optional array of strings. A bad `qty` or `unit` is a `RangeError`.
    * A *promotion* has a `type` and optional `code`, `validFrom`, `validTo`:
      * `{ type: 'percent', pct, appliesTo?, minQty? }`: `pct` percent off a line's gross amount (`qty * unit`).
      * `{ type: 'bundle', sku, buy, pay }`: for line `sku`, in every complete group of `buy` units only `pay` units are
        charged, i.e. `floor(qty / buy) * (buy - pay) * unit` is taken off.
      * `{ type: 'fixed', cents, minSubtotal? }`: a cart-level amount off.
    * `appliesTo` is `{ skus?, tag? }`: a line matches when its sku is in `skus` (if given) *and* it carries `tag` (if
      given). No `appliesTo` matches every line. A percent promotion with `minQty` only applies to lines with
      `qty >= minQty`.
    * Options: `codes` (what the shopper typed), `today` (`'YYYY-MM-DD'`), `shipping` (`{ flat, freeOver }`) and
      `maxDiscountPct` (default `60`).

    ## `isActive(promo, codes, today)` (`src/promos.js`)

    `codes` is a `Set` of already normalised codes. A promotion with a `code` applies only when that code, normalised, is
    in the set; promotions without a `code` apply automatically. The normal form of a code is
    `String(code).trim().toUpperCase()`. When `today` is `undefined` the date window is ignored; otherwise the promotion
    needs `today >= validFrom` (if present) and `today <= validTo` (if present), both inclusive, compared as strings.

    ## `priceCart(lines, promos, opts = {})` (`src/cart.js`)

    1. *Line level.* Every line gets at most **one** line promotion (`percent` or `bundle`): among the active, matching ones
       the one with the largest discount; the first of them in the `promos` array wins a tie. A bundle matches only the line
       whose sku equals its `sku` (and its `appliesTo`, if any). A line's discount never exceeds its gross amount. A
       percent discount is `roundHalfUp(gross * pct / 100)`, where `roundHalfUp(n, d)` is `n / d` rounded half up. The
       line's `promo` is the promotion's `code`, or its `type` when it has none; `null` without a discount.
    2. *Cart level.* With `afterLines = subtotal - lineDiscount`, the active `fixed` promotions are applied in array order.
       One applies only if `afterLines - cartDiscount >= minSubtotal` (default `0`; the comparison is inclusive). It takes
       off `cents`, but never more than what is left to pay, and never more than the discount allowance left under the cap:
       the total discount (line plus cart) may not exceed `floor(subtotal * maxDiscountPct / 100)`; line discounts are
       never cut, so when they already use up the allowance a fixed promotion takes off `0`. A fixed promotion that took
       off something is listed in `applied` under its `code`, or `'fixed'`.
    3. *Shipping.* `net = afterLines - cartDiscount`. Shipping is `0` without `opts.shipping`, for an empty cart, when every
       line has the tag `'digital'`, or when `net >= freeOver`; otherwise `flat`.
    4. *Result.* `{ lines, subtotal, lineDiscount, cartDiscount, shipping, total, applied }`: each `lines` entry is
       `{ sku, qty, unit, gross, discount, net, promo }` in input order; `subtotal` is the sum of the gross amounts,
       `total = net + shipping`, and `applied` lists the distinct line promotion labels in line order, followed by the
       fixed promotions that took something off.
''')

PROMOS = dd(r'''
    'use strict';

    function normCode(code) {
      return String(code).trim().toUpperCase();
    }

    function roundHalfUp(n, d) {
      return Math.floor((2 * n + d) / (2 * d));
    }

    function isActive(promo, codes, today) {
      if (promo.code !== undefined && !codes.has(normCode(promo.code))) return false;
      if (today !== undefined) {
        if (promo.validFrom !== undefined && today < promo.validFrom) return false;
        if (promo.validTo !== undefined && today > promo.validTo) return false;
      }
      return true;
    }

    function matches(promo, line) {
      const scope = promo.appliesTo;
      if (!scope) return true;
      if (scope.skus && !scope.skus.includes(line.sku)) return false;
      if (scope.tag && !(line.tags || []).includes(scope.tag)) return false;
      return true;
    }

    function lineDiscount(promo, line) {
      const gross = line.qty * line.unit;
      if (promo.type === 'percent') {
        if (promo.minQty && line.qty < promo.minQty) return 0;
        return roundHalfUp(gross * promo.pct, 100);
      }
      if (promo.type === 'bundle') {
        if (line.sku !== promo.sku) return 0;
        return Math.floor(line.qty / promo.buy) * (promo.buy - promo.pay) * line.unit;
      }
      return 0;
    }

    module.exports = { normCode, roundHalfUp, isActive, matches, lineDiscount };
''')

CART = dd(r'''
    'use strict';

    const { normCode, isActive, matches, lineDiscount } = require('./promos');

    function checkLine(line) {
      if (!Number.isInteger(line.qty) || line.qty < 1) throw new RangeError(`bad qty for ${line.sku}`);
      if (!Number.isInteger(line.unit) || line.unit < 0) throw new RangeError(`bad unit price for ${line.sku}`);
    }

    function priceCart(lines, promos, opts = {}) {
      const codes = new Set((opts.codes || []).map(normCode));
      const active = promos.filter((p) => isActive(p, codes, opts.today));
      const linePromos = active.filter((p) => p.type === 'percent' || p.type === 'bundle');

      const priced = lines.map((line) => {
        checkLine(line);
        const gross = line.qty * line.unit;
        let best = 0;
        let label = null;
        for (const p of linePromos) {
          if (!matches(p, line)) continue;
          const d = Math.min(gross, lineDiscount(p, line));
          if (d > best) {
            best = d;
            label = p.code !== undefined ? p.code : p.type;
          }
        }
        return { sku: line.sku, qty: line.qty, unit: line.unit, gross, discount: best, net: gross - best, promo: label };
      });

      const subtotal = priced.reduce((sum, l) => sum + l.gross, 0);
      const lineTotal = priced.reduce((sum, l) => sum + l.discount, 0);
      const afterLines = subtotal - lineTotal;
      const allowance = Math.floor((subtotal * (opts.maxDiscountPct === undefined ? 60 : opts.maxDiscountPct)) / 100);

      let cartDiscount = 0;
      const applied = [];
      for (const l of priced) {
        if (l.promo !== null && !applied.includes(l.promo)) applied.push(l.promo);
      }
      for (const p of active) {
        if (p.type !== 'fixed') continue;
        if (afterLines - cartDiscount < (p.minSubtotal || 0)) continue;
        const room = allowance - lineTotal - cartDiscount;
        const d = Math.max(0, Math.min(p.cents, afterLines - cartDiscount, room));
        if (d > 0) {
          cartDiscount += d;
          applied.push(p.code !== undefined ? p.code : 'fixed');
        }
      }

      const net = afterLines - cartDiscount;
      let shipping = 0;
      if (opts.shipping && lines.length > 0) {
        const allDigital = lines.every((l) => (l.tags || []).includes('digital'));
        if (!allDigital && net < opts.shipping.freeOver) shipping = opts.shipping.flat;
      }
      return { lines: priced, subtotal, lineDiscount: lineTotal, cartDiscount, shipping, total: net + shipping, applied };
    }

    module.exports = { priceCart };
''')

VISIBLE = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { priceCart } = require('../src/cart');

    const lines = [
      { sku: 'tee', qty: 3, unit: 2000, tags: ['apparel'] },
      { sku: 'mug', qty: 2, unit: 1250, tags: ['kitchen'] },
    ];

    test('no promotions', () => {
      const r = priceCart(lines, []);
      assert.equal(r.subtotal, 8500);
      assert.equal(r.total, 8500);
      assert.deepEqual(r.applied, []);
    });

    test('ten percent on one sku', () => {
      const r = priceCart(lines, [{ type: 'percent', pct: 10, appliesTo: { skus: ['tee'] } }]);
      assert.equal(r.lines[0].discount, 600);
      assert.equal(r.total, 7900);
    });
''')

HIDDEN = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { priceCart } = require('../src/cart');
    const { isActive, matches, lineDiscount, roundHalfUp, normCode } = require('../src/promos');

    const TEE = { sku: 'tee', qty: 3, unit: 2000, tags: ['apparel'] };
    const MUG = { sku: 'mug', qty: 2, unit: 1250, tags: ['kitchen'] };
    const BOOK = { sku: 'ebook', qty: 1, unit: 900, tags: ['digital'] };
    const CART = [TEE, MUG, BOOK];

    test('roundHalfUp and normCode', () => {
      assert.equal(roundHalfUp(0, 100), 0);
      assert.equal(roundHalfUp(49, 100), 0);
      assert.equal(roundHalfUp(50, 100), 1);
      assert.equal(roundHalfUp(149, 100), 1);
      assert.equal(roundHalfUp(150, 100), 2);
      assert.equal(roundHalfUp(7, 2), 4);
      assert.equal(normCode('  spring10 '), 'SPRING10');
      assert.equal(normCode(12), '12');
    });

    test('isActive: codes', () => {
      const none = new Set();
      const some = new Set(['SPRING10']);
      assert.equal(isActive({ type: 'percent', pct: 5 }, none, undefined), true);
      assert.equal(isActive({ type: 'percent', pct: 5, code: 'spring10' }, none, undefined), false);
      assert.equal(isActive({ type: 'percent', pct: 5, code: 'spring10' }, some, undefined), true);
      assert.equal(isActive({ type: 'percent', pct: 5, code: ' Spring10 ' }, some, undefined), true);
      assert.equal(isActive({ type: 'percent', pct: 5, code: 'other' }, some, undefined), false);
    });

    test('isActive: date window is inclusive and ignored without today', () => {
      const p = { type: 'percent', pct: 5, validFrom: '2025-03-01', validTo: '2025-03-31' };
      const s = new Set();
      assert.equal(isActive(p, s, '2025-02-28'), false);
      assert.equal(isActive(p, s, '2025-03-01'), true);
      assert.equal(isActive(p, s, '2025-03-15'), true);
      assert.equal(isActive(p, s, '2025-03-31'), true);
      assert.equal(isActive(p, s, '2025-04-01'), false);
      assert.equal(isActive(p, s, undefined), true);
      assert.equal(isActive({ type: 'fixed', cents: 1, validFrom: '2025-03-01' }, s, '2025-02-01'), false);
      assert.equal(isActive({ type: 'fixed', cents: 1, validFrom: '2025-03-01' }, s, '2030-01-01'), true);
      assert.equal(isActive({ type: 'fixed', cents: 1, validTo: '2025-03-01' }, s, '2025-02-01'), true);
      assert.equal(isActive({ type: 'fixed', cents: 1, validTo: '2025-03-01' }, s, '2030-01-01'), false);
    });

    test('matches', () => {
      assert.equal(matches({ type: 'percent' }, TEE), true);
      assert.equal(matches({ appliesTo: { skus: ['tee', 'mug'] } }, MUG), true);
      assert.equal(matches({ appliesTo: { skus: ['tee'] } }, MUG), false);
      assert.equal(matches({ appliesTo: { tag: 'kitchen' } }, MUG), true);
      assert.equal(matches({ appliesTo: { tag: 'kitchen' } }, TEE), false);
      assert.equal(matches({ appliesTo: { tag: 'kitchen' } }, { sku: 'x', qty: 1, unit: 1 }), false);
      assert.equal(matches({ appliesTo: { skus: ['tee'], tag: 'kitchen' } }, TEE), false);
      assert.equal(matches({ appliesTo: { skus: ['mug'], tag: 'kitchen' } }, MUG), true);
      assert.equal(matches({ appliesTo: {} }, TEE), true);
    });

    test('lineDiscount: percent', () => {
      assert.equal(lineDiscount({ type: 'percent', pct: 10 }, TEE), 600);
      assert.equal(lineDiscount({ type: 'percent', pct: 15 }, { sku: 'm', qty: 1, unit: 1250 }), 188);
      assert.equal(lineDiscount({ type: 'percent', pct: 15 }, { sku: 'm', qty: 1, unit: 1249 }), 187);
      assert.equal(lineDiscount({ type: 'percent', pct: 100 }, TEE), 6000);
      assert.equal(lineDiscount({ type: 'percent', pct: 0 }, TEE), 0);
    });

    test('lineDiscount: minQty', () => {
      const p = { type: 'percent', pct: 10, minQty: 5 };
      assert.equal(lineDiscount(p, { sku: 'a', qty: 4, unit: 1000 }), 0);
      assert.equal(lineDiscount(p, { sku: 'a', qty: 5, unit: 1000 }), 500);
      assert.equal(lineDiscount(p, { sku: 'a', qty: 6, unit: 1000 }), 600);
    });

    test('lineDiscount: bundle', () => {
      const p = { type: 'bundle', sku: 'tee', buy: 3, pay: 2 };
      assert.equal(lineDiscount(p, { sku: 'tee', qty: 2, unit: 2000 }), 0);
      assert.equal(lineDiscount(p, { sku: 'tee', qty: 3, unit: 2000 }), 2000);
      assert.equal(lineDiscount(p, { sku: 'tee', qty: 5, unit: 2000 }), 2000);
      assert.equal(lineDiscount(p, { sku: 'tee', qty: 7, unit: 2000 }), 4000);
      assert.equal(lineDiscount(p, { sku: 'tee', qty: 6, unit: 100 }), 200);
      assert.equal(lineDiscount(p, { sku: 'mug', qty: 6, unit: 2000 }), 0);
      assert.equal(lineDiscount({ type: 'bundle', sku: 'a', buy: 4, pay: 1 }, { sku: 'a', qty: 9, unit: 10 }), 60);
      assert.equal(lineDiscount({ type: 'fixed', cents: 5 }, TEE), 0);
    });

    test('no promotions', () => {
      const r = priceCart(CART, []);
      assert.equal(r.subtotal, 9400);
      assert.equal(r.lineDiscount, 0);
      assert.equal(r.cartDiscount, 0);
      assert.equal(r.shipping, 0);
      assert.equal(r.total, 9400);
      assert.deepEqual(r.applied, []);
      assert.deepEqual(r.lines[0], { sku: 'tee', qty: 3, unit: 2000, gross: 6000, discount: 0, net: 6000, promo: null });
    });

    test('empty cart', () => {
      const r = priceCart([], [{ type: 'fixed', cents: 500 }], { shipping: { flat: 599, freeOver: 5000 } });
      assert.deepEqual(r, { lines: [], subtotal: 0, lineDiscount: 0, cartDiscount: 0, shipping: 0, total: 0, applied: [] });
    });

    test('percent by sku and by tag', () => {
      const r = priceCart(CART, [{ type: 'percent', pct: 10, appliesTo: { skus: ['tee'] } }]);
      assert.deepEqual(r.lines.map((l) => l.discount), [600, 0, 0]);
      assert.deepEqual(r.lines.map((l) => l.promo), ['percent', null, null]);
      assert.equal(r.lineDiscount, 600);
      assert.equal(r.total, 8800);
      const t = priceCart(CART, [{ type: 'percent', pct: 20, appliesTo: { tag: 'kitchen' } }]);
      assert.deepEqual(t.lines.map((l) => l.discount), [0, 500, 0]);
      assert.equal(t.total, 8900);
    });

    test('coupon codes switch promotions on', () => {
      const promo = { type: 'percent', code: 'Kitchen15', pct: 15, appliesTo: { tag: 'kitchen' } };
      assert.equal(priceCart(CART, [promo]).lineDiscount, 0);
      assert.equal(priceCart(CART, [promo], { codes: ['nothing'] }).lineDiscount, 0);
      const on = priceCart(CART, [promo], { codes: [' kitchen15 '] });
      assert.equal(on.lineDiscount, 375);
      assert.deepEqual(on.lines[1].promo, 'Kitchen15');
      assert.deepEqual(on.applied, ['Kitchen15']);
    });

    test('bundle on the tee line', () => {
      const r = priceCart(CART, [{ type: 'bundle', sku: 'tee', buy: 3, pay: 2 }]);
      assert.deepEqual(r.lines[0], { sku: 'tee', qty: 3, unit: 2000, gross: 6000, discount: 2000, net: 4000, promo: 'bundle' });
      assert.equal(r.total, 7400);
      const six = priceCart([{ sku: 'tee', qty: 7, unit: 2000 }], [{ type: 'bundle', sku: 'tee', buy: 3, pay: 2 }]);
      assert.equal(six.lineDiscount, 4000);
      assert.equal(six.total, 10000);
    });

    test('one line promotion per line: the larger discount wins', () => {
      const bundle = { type: 'bundle', sku: 'tee', buy: 3, pay: 2 };
      const half = { type: 'percent', pct: 50, appliesTo: { skus: ['tee'] } };
      const fifth = { type: 'percent', pct: 20, appliesTo: { skus: ['tee'] } };
      const a = priceCart([TEE], [bundle, half]);
      assert.equal(a.lines[0].discount, 3000);
      assert.equal(a.lines[0].promo, 'percent');
      const b = priceCart([TEE], [fifth, bundle]);
      assert.equal(b.lines[0].discount, 2000);
      assert.equal(b.lines[0].promo, 'bundle');
      assert.equal(b.total, 4000);
    });

    test('ties go to the first promotion in the array', () => {
      const line = { sku: 'a', qty: 2, unit: 1000 };
      const bundle = { type: 'bundle', sku: 'a', buy: 2, pay: 1 };
      const half = { type: 'percent', pct: 50 };
      assert.equal(priceCart([line], [bundle, half]).lines[0].promo, 'bundle');
      assert.equal(priceCart([line], [half, bundle]).lines[0].promo, 'percent');
      assert.equal(priceCart([line], [bundle, half]).lines[0].discount, 1000);
    });

    test('minQty', () => {
      const p = { type: 'percent', pct: 10, minQty: 5, appliesTo: { skus: ['tee'] } };
      assert.equal(priceCart([{ sku: 'tee', qty: 4, unit: 1000 }], [p]).lineDiscount, 0);
      assert.equal(priceCart([{ sku: 'tee', qty: 5, unit: 1000 }], [p]).lineDiscount, 500);
    });

    test('a discount never exceeds the gross amount', () => {
      const r = priceCart([{ sku: 'a', qty: 1, unit: 300 }], [{ type: 'percent', pct: 150 }]);
      assert.equal(r.lines[0].discount, 300);
      assert.equal(r.lines[0].net, 0);
      assert.equal(r.total, 0);
    });

    test('applied lists distinct labels in line order', () => {
      const promos = [
        { type: 'percent', code: 'T10', pct: 10, appliesTo: { tag: 'apparel' } },
        { type: 'percent', pct: 5, appliesTo: { tag: 'kitchen' } },
        { type: 'percent', pct: 5, appliesTo: { tag: 'digital' } },
      ];
      const r = priceCart(CART, promos, { codes: ['t10'] });
      assert.deepEqual(r.applied, ['T10', 'percent']);
    });

    test('fixed promotion and its minimum', () => {
      const take5 = { type: 'fixed', code: 'TAKE5', cents: 500, minSubtotal: 3000 };
      const r = priceCart(CART, [take5], { codes: ['take5'] });
      assert.equal(r.cartDiscount, 500);
      assert.equal(r.total, 8900);
      assert.deepEqual(r.applied, ['TAKE5']);
      assert.equal(priceCart(CART, [take5]).cartDiscount, 0);
      const edge = [{ sku: 'a', qty: 1, unit: 3000 }];
      assert.equal(priceCart(edge, [take5], { codes: ['TAKE5'] }).cartDiscount, 500);
      const below = [{ sku: 'a', qty: 1, unit: 2999 }];
      assert.equal(priceCart(below, [take5], { codes: ['TAKE5'] }).cartDiscount, 0);
    });

    test('the fixed minimum is checked after line discounts', () => {
      const p = [{ type: 'percent', pct: 50 }, { type: 'fixed', cents: 100, minSubtotal: 3000 }];
      const cart = [{ sku: 'a', qty: 1, unit: 5000 }];
      assert.equal(priceCart(cart, p).cartDiscount, 0);
      const cart2 = [{ sku: 'a', qty: 1, unit: 6000 }];
      const r = priceCart(cart2, p);
      assert.equal(r.cartDiscount, 100);
      assert.deepEqual(r.applied, ['percent', 'fixed']);
      assert.equal(r.total, 2900);
    });

    test('a fixed promotion cannot take more than is left', () => {
      const r = priceCart([{ sku: 'a', qty: 1, unit: 400 }], [{ type: 'fixed', cents: 1000 }], { maxDiscountPct: 100 });
      assert.equal(r.cartDiscount, 400);
      assert.equal(r.total, 0);
    });

    test('default cap is 60 percent of the subtotal', () => {
      const promos = [{ type: 'percent', pct: 30, appliesTo: { skus: ['tee'] } }, { type: 'fixed', cents: 5000 }];
      const r = priceCart([{ sku: 'tee', qty: 1, unit: 6000 }, { sku: 'mug', qty: 1, unit: 4000 }], promos);
      // subtotal 10000, allowance 6000, line discount 1800 -> 4200 left for the fixed amount
      assert.equal(r.lineDiscount, 1800);
      assert.equal(r.cartDiscount, 4200);
      assert.equal(r.total, 4000);
    });

    test('the cap allowance is floored', () => {
      const r = priceCart([{ sku: 'a', qty: 1, unit: 1005 }], [{ type: 'fixed', cents: 5000 }]);
      // floor(1005 * 60 / 100) = 603
      assert.equal(r.cartDiscount, 603);
      assert.equal(r.total, 402);
    });

    test('custom cap and line discounts that already exceed it', () => {
      const cart = [{ sku: 'a', qty: 1, unit: 10000 }];
      assert.equal(priceCart(cart, [{ type: 'fixed', cents: 2000 }], { maxDiscountPct: 10 }).cartDiscount, 1000);
      assert.equal(priceCart(cart, [{ type: 'fixed', cents: 500 }], { maxDiscountPct: 10 }).cartDiscount, 500);
      const both = priceCart(cart, [{ type: 'percent', pct: 40 }, { type: 'fixed', cents: 500 }], { maxDiscountPct: 30 });
      assert.equal(both.lineDiscount, 4000);
      assert.equal(both.cartDiscount, 0);
      assert.equal(both.total, 6000);
      assert.deepEqual(both.applied, ['percent']);
      assert.equal(priceCart(cart, [{ type: 'fixed', cents: 500 }], { maxDiscountPct: 0 }).cartDiscount, 0);
    });

    test('several fixed promotions stack in array order', () => {
      const promos = [
        { type: 'fixed', code: 'A', cents: 700, minSubtotal: 5000 },
        { type: 'fixed', code: 'B', cents: 700, minSubtotal: 5000 },
        { type: 'fixed', cents: 100 },
      ];
      const r = priceCart([{ sku: 'a', qty: 1, unit: 5600 }], promos, { codes: ['a', 'b'] });
      // A: 5600 >= 5000 takes 700 (4900 left); B: 4900 < 5000 so it does not apply; the last one takes 100
      assert.equal(r.cartDiscount, 800);
      assert.deepEqual(r.applied, ['A', 'fixed']);
      assert.equal(r.total, 4800);
    });

    test('date windows', () => {
      const promos = [{ type: 'percent', pct: 10, validFrom: '2025-03-01', validTo: '2025-03-31' }];
      const cart = [{ sku: 'a', qty: 1, unit: 1000 }];
      assert.equal(priceCart(cart, promos, { today: '2025-02-28' }).lineDiscount, 0);
      assert.equal(priceCart(cart, promos, { today: '2025-03-01' }).lineDiscount, 100);
      assert.equal(priceCart(cart, promos, { today: '2025-03-31' }).lineDiscount, 100);
      assert.equal(priceCart(cart, promos, { today: '2025-04-01' }).lineDiscount, 0);
      assert.equal(priceCart(cart, promos).lineDiscount, 100);
    });

    test('shipping', () => {
      const ship = { flat: 599, freeOver: 5000 };
      const cart = (unit) => [{ sku: 'a', qty: 1, unit }];
      assert.equal(priceCart(cart(4999), [], { shipping: ship }).shipping, 599);
      assert.equal(priceCart(cart(4999), [], { shipping: ship }).total, 5598);
      assert.equal(priceCart(cart(5000), [], { shipping: ship }).shipping, 0);
      assert.equal(priceCart(cart(5001), [], { shipping: ship }).shipping, 0);
      assert.equal(priceCart(cart(100), []).shipping, 0);
    });

    test('shipping looks at the discounted amount', () => {
      const ship = { flat: 599, freeOver: 5000 };
      const cart = [{ sku: 'a', qty: 1, unit: 5500 }];
      assert.equal(priceCart(cart, [{ type: 'fixed', cents: 600 }], { shipping: ship }).shipping, 599);
      assert.equal(priceCart(cart, [{ type: 'fixed', cents: 500 }], { shipping: ship }).shipping, 0);
      assert.equal(priceCart(cart, [{ type: 'percent', pct: 5 }], { shipping: ship }).shipping, 0);
      assert.equal(priceCart(cart, [{ type: 'percent', pct: 10 }], { shipping: ship }).shipping, 599);
      assert.equal(priceCart(cart, [{ type: 'percent', pct: 10 }], { shipping: ship }).total, 5549);
      assert.equal(priceCart(cart, [{ type: 'percent', pct: 20 }], { shipping: ship }).total, 4400 + 599);
    });

    test('digital goods do not ship', () => {
      const ship = { flat: 599, freeOver: 5000 };
      assert.equal(priceCart([BOOK], [], { shipping: ship }).shipping, 0);
      assert.equal(priceCart([BOOK, BOOK], [], { shipping: ship }).shipping, 0);
      assert.equal(priceCart([BOOK, MUG], [], { shipping: ship }).shipping, 599);
      assert.equal(priceCart([{ sku: 'x', qty: 1, unit: 100 }], [], { shipping: ship }).shipping, 599);
    });

    test('line validation', () => {
      const bad = [
        { sku: 'a', qty: 0, unit: 100 },
        { sku: 'a', qty: -1, unit: 100 },
        { sku: 'a', qty: 1.5, unit: 100 },
        { sku: 'a', qty: 1, unit: -1 },
        { sku: 'a', qty: 1, unit: 10.5 },
        { sku: 'a', qty: '2', unit: 100 },
      ];
      for (const line of bad) assert.throws(() => priceCart([line], []), RangeError);
      assert.equal(priceCart([{ sku: 'a', qty: 1, unit: 0 }], []).total, 0);
    });

    test('input is not modified', () => {
      const cart = [{ sku: 'tee', qty: 3, unit: 2000, tags: ['apparel'] }];
      const copy = JSON.stringify(cart);
      priceCart(cart, [{ type: 'percent', pct: 10 }]);
      assert.equal(JSON.stringify(cart), copy);
    });
''')

LIB = Lib(
    name="cartpromo", lang="javascript", title="the cartpromo pricing engine",
    blurb="The web shop's checkout calls cartpromo to turn a basket and the active promotions into line discounts, shipping and a total.",
    files={"package.json": PACKAGE_JSON % "cartpromo", "src/promos.js": PROMOS, "src/cart.js": CART, "README.md": README, ".gitignore": "node_modules/\n"},
    visible_tests={"test/basic.test.js": VISIBLE},
    hidden_tests={"test/full.test.js": HIDDEN},
    mutate=["src/cart.js", "src/promos.js"], difficulty=3, tags=["pricing", "promotions", "checkout"],
    verify=JS_VERIFY,
    probe_import="const { priceCart } = require('./src/cart');\nconst { isActive, matches, lineDiscount, roundHalfUp } = require('./src/promos');",
    probes=[
        'roundHalfUp(50, 100)',
        "lineDiscount({ type: 'percent', pct: 15 }, { sku: 'm', qty: 1, unit: 1250 })",
        "lineDiscount({ type: 'bundle', sku: 'tee', buy: 3, pay: 2 }, { sku: 'tee', qty: 7, unit: 2000 })",
        "lineDiscount({ type: 'percent', pct: 10, minQty: 5 }, { sku: 'a', qty: 5, unit: 1000 })",
        "isActive({ type: 'percent', pct: 5, code: ' Spring10 ' }, new Set(['SPRING10']), undefined)",
        "isActive({ type: 'percent', pct: 5, validFrom: '2025-03-01', validTo: '2025-03-31' }, new Set(), '2025-03-31')",
        "matches({ appliesTo: { skus: ['tee'], tag: 'kitchen' } }, { sku: 'tee', qty: 1, unit: 1, tags: ['apparel'] })",
        "priceCart([{ sku: 'tee', qty: 3, unit: 2000 }, { sku: 'mug', qty: 2, unit: 1250 }], [{ type: 'percent', pct: 10, appliesTo: { skus: ['tee'] } }]).total",
        "priceCart([{ sku: 'tee', qty: 3, unit: 2000 }], [{ type: 'bundle', sku: 'tee', buy: 3, pay: 2 }, { type: 'percent', pct: 50 }]).lines[0]",
        "priceCart([{ sku: 'tee', qty: 3, unit: 2000 }], [{ type: 'percent', pct: 20 }, { type: 'bundle', sku: 'tee', buy: 3, pay: 2 }]).lines[0].promo",
        "priceCart([{ sku: 'a', qty: 1, unit: 3000 }], [{ type: 'fixed', code: 'TAKE5', cents: 500, minSubtotal: 3000 }], { codes: ['take5'] }).cartDiscount",
        "priceCart([{ sku: 'a', qty: 1, unit: 1005 }], [{ type: 'fixed', cents: 5000 }]).cartDiscount",
        "priceCart([{ sku: 'a', qty: 1, unit: 10000 }], [{ type: 'percent', pct: 40 }, { type: 'fixed', cents: 500 }], { maxDiscountPct: 30 }).total",
        "priceCart([{ sku: 'a', qty: 1, unit: 4999 }], [], { shipping: { flat: 599, freeOver: 5000 } }).total",
        "priceCart([{ sku: 'ebook', qty: 1, unit: 900, tags: ['digital'] }], [], { shipping: { flat: 599, freeOver: 5000 } }).shipping",
        "priceCart([{ sku: 'a', qty: 1, unit: 5500 }], [{ type: 'fixed', cents: 600 }], { shipping: { flat: 599, freeOver: 5000 } }).shipping",
        "priceCart([{ sku: 'a', qty: 1, unit: 100 }], [{ type: 'percent', pct: 10, validFrom: '2025-03-01' }], { today: '2025-03-01' }).lineDiscount",
        "priceCart([{ sku: 'a', qty: 0, unit: 100 }], [])",
    ],
)

register_libs([LIB], n=8)
