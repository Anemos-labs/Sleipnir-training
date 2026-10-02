"""A layered javascript pricing pipeline (cart, volume and coupon rules, allocation, shipping, tax, receipt). Defects sit
in a different module than the symptom; review tickets combine causes."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

PKG = '{\n  "name": "cartflow",\n  "version": "1.0.0",\n  "private": true\n}\n'

README = dd('''
    # cartflow

    The pricing pipeline of a small web shop (CommonJS, `src/*.js`). **All money is integer cents.**

    ## Cart (`src/cart.js`)

    * `add(sku, qty = 1)` merges into an existing line of the same SKU. A quantity is a positive integer or a string of
      digits (`"3"`, from a form field); it is stored as a number. Anything else is a `RangeError`.
    * `setQty(sku, qty)` sets the quantity (same rules; `0` is allowed and removes the line). `remove(sku)` removes the line.
    * `lines()` returns a *new* array of *new* `{ sku, qty }` objects, in insertion order. `count()` is the total quantity.

    ## Rules (`src/rules.js`)

    * Volume discount per line: 10 % off the line from a quantity of 10, 15 % from 25. The best tier applies; tiers do not add up.
    * Coupons (at most one per cart): `SAVE10` is 10 % of the goods total after volume discounts, at most 25.00, and needs at
      least 30.00 after volume discounts; `FIVE` takes 5.00 off, never more than the goods total; `SHIPFREE` makes shipping
      free when the goods total after volume discounts is at least 20.00. `couponOff(coupon, goodsCents)` is the amount taken off the goods
      (0 for `SHIPFREE` and when the minimum is not reached).

    ## Pricing (`src/pricing.js`, `price(cart, catalog, { coupon })`)

    1. Lines are listed in SKU order. The list price of a line is unit price times quantity; the volume discount is a percentage of it (`percentOf`).
    2. The coupon discount is calculated on the goods total *after* volume discounts and is spread over the lines in proportion to
       their remaining amounts with `allocate` (largest remainder: the shares add up to exactly the discount).
    3. Tax is charged per tax class on the sum of the remaining line amounts of that class (rounded once per class, halves up):
       `standard` 20 %, `reduced` 5 %, `zero` 0 %.
    4. Shipping is by weight of the cart (`src/shipping.js`): up to and including 500 g 4.90, 2000 g 7.90, 10000 g 12.90, more 19.90;
       an empty cart ships for nothing. Shipping is free when the goods total after *all* discounts is at least 100.00, or with a
       valid `SHIPFREE`. Shipping is taxed at the standard rate (rounded separately, and added to the standard class).
    5. The result has `lines` (`sku, qty, unitCents, listCents, volumeOffCents, netCents`), `subtotalCents` (list total), `volumeOffCents`,
       `couponOffCents`, `shippingCents`, `taxByClass`, `taxCents`, `totalCents`.

    `price` never changes the cart. `src/format.js` has `money(cents)` (`-3.15`, never a float) and `receipt(priced)`.
''')

MONEY = dd('''
    'use strict';

    // Percent of an amount in cents, halves rounded up (amounts are not negative).
    function percentOf(cents, percent) {
      return Math.floor((cents * percent + 50) / 100);
    }

    // Split `total` cents over `weights` in proportion; the shares are integers that add up to exactly `total`
    // (largest remainder, ties go to the earlier index).
    function allocate(total, weights) {
      const sum = weights.reduce((a, b) => a + b, 0);
      if (sum === 0) return weights.map(() => 0);
      const shares = weights.map((w) => Math.floor((total * w) / sum));
      let left = total - shares.reduce((a, b) => a + b, 0);
      const order = weights
        .map((w, i) => ({ i, rem: (total * w) % sum }))
        .sort((a, b) => b.rem - a.rem || a.i - b.i);
      for (let k = 0; left > 0; k++, left--) shares[order[k].i] += 1;
      return shares;
    }

    module.exports = { percentOf, allocate };
''')

CATALOG = dd('''
    'use strict';

    const CATALOG = {
      pen: { name: 'Pen', priceCents: 150, taxClass: 'standard', weightG: 20 },
      clip: { name: 'Clip', priceCents: 102, taxClass: 'standard', weightG: 5 },
      pin: { name: 'Pin', priceCents: 102, taxClass: 'standard', weightG: 5 },
      book: { name: 'Book', priceCents: 1299, taxClass: 'reduced', weightG: 400 },
      tea: { name: 'Tea', priceCents: 899, taxClass: 'reduced', weightG: 250 },
      seed: { name: 'Seeds', priceCents: 199, taxClass: 'zero', weightG: 30 },
      lamp: { name: 'Lamp', priceCents: 4590, taxClass: 'standard', weightG: 1800 },
      desk: { name: 'Desk', priceCents: 25900, taxClass: 'standard', weightG: 18000 },
    };

    module.exports = { CATALOG };
''')

CART = dd('''
    'use strict';

    function toQty(q) {
      const n = typeof q === 'string' && /^[0-9]+$/.test(q) ? Number(q) : q;
      if (!Number.isInteger(n) || n < 0) throw new RangeError(`bad quantity ${JSON.stringify(q)}`);
      return n;
    }

    class Cart {
      constructor() {
        this._lines = [];
      }

      add(sku, qty = 1) {
        const n = toQty(qty);
        if (n === 0) throw new RangeError('bad quantity 0');
        const line = this._lines.find((l) => l.sku === sku);
        if (line) line.qty += n;
        else this._lines.push({ sku, qty: n });
        return this;
      }

      setQty(sku, qty) {
        const n = toQty(qty);
        if (n === 0) return this.remove(sku);
        const line = this._lines.find((l) => l.sku === sku);
        if (line) line.qty = n;
        else this._lines.push({ sku, qty: n });
        return this;
      }

      remove(sku) {
        this._lines = this._lines.filter((l) => l.sku !== sku);
        return this;
      }

      lines() {
        return this._lines.map((l) => ({ ...l }));
      }

      count() {
        return this._lines.reduce((a, l) => a + l.qty, 0);
      }
    }

    module.exports = { Cart };
''')

RULES = dd('''
    'use strict';

    const { percentOf } = require('./money');

    // Best tier wins; tiers do not add up.
    const VOLUME_TIERS = [
      { minQty: 25, percent: 15 },
      { minQty: 10, percent: 10 },
    ];

    function volumePercent(qty) {
      for (const t of VOLUME_TIERS) {
        if (qty >= t.minQty) return t.percent;
      }
      return 0;
    }

    const COUPONS = {
      SAVE10: { code: 'SAVE10', type: 'percent', percent: 10, maxOffCents: 2500, minGoodsCents: 3000 },
      FIVE: { code: 'FIVE', type: 'fixed', offCents: 500, minGoodsCents: 0 },
      SHIPFREE: { code: 'SHIPFREE', type: 'freeship', minGoodsCents: 2000 },
    };

    // Amount taken off the goods by a coupon, given the goods total after volume discounts.
    function couponOff(coupon, goodsCents) {
      if (!coupon || goodsCents < coupon.minGoodsCents) return 0;
      if (coupon.type === 'percent') return Math.min(percentOf(goodsCents, coupon.percent), coupon.maxOffCents);
      if (coupon.type === 'fixed') return Math.min(coupon.offCents, goodsCents);
      return 0;
    }

    module.exports = { COUPONS, volumePercent, couponOff };
''')

SHIPPING = dd('''
    'use strict';

    const TIERS = [
      { maxG: 500, cents: 490 },
      { maxG: 2000, cents: 790 },
      { maxG: 10000, cents: 1290 },
    ];
    const OVERSIZE_CENTS = 1990;
    const FREE_FROM_CENTS = 10000;

    function shippingCents(weightG) {
      for (const t of TIERS) {
        if (weightG <= t.maxG) return t.cents;
      }
      return OVERSIZE_CENTS;
    }

    module.exports = { shippingCents, FREE_FROM_CENTS };
''')

TAX = dd('''
    'use strict';

    const RATES_BP = { standard: 2000, reduced: 500, zero: 0 };

    // Tax on a net amount, halves rounded up.
    function taxOn(netCents, taxClass) {
      return Math.floor((netCents * RATES_BP[taxClass] + 5000) / 10000);
    }

    module.exports = { RATES_BP, taxOn };
''')

PRICING = dd('''
    'use strict';

    const { allocate, percentOf } = require('./money');
    const { volumePercent, couponOff } = require('./rules');
    const { shippingCents, FREE_FROM_CENTS } = require('./shipping');
    const { taxOn } = require('./tax');

    const sum = (xs) => xs.reduce((a, b) => a + b, 0);

    function price(cart, catalog, opts = {}) {
      const coupon = opts.coupon || null;
      const lines = [...cart.lines()]
        .sort((a, b) => (a.sku < b.sku ? -1 : a.sku > b.sku ? 1 : 0))
        .map((l) => {
          const item = catalog[l.sku];
          if (!item) throw new RangeError(`unknown sku ${l.sku}`);
          const listCents = item.priceCents * l.qty;
          const volumeOffCents = percentOf(listCents, volumePercent(l.qty));
          return {
            sku: l.sku,
            qty: l.qty,
            unitCents: item.priceCents,
            listCents,
            volumeOffCents,
            netCents: listCents - volumeOffCents,
            taxClass: item.taxClass,
            weightG: item.weightG * l.qty,
          };
        });

      const subtotalCents = sum(lines.map((l) => l.listCents));
      const volumeOffCents = sum(lines.map((l) => l.volumeOffCents));
      const afterVolume = subtotalCents - volumeOffCents;

      const couponOffCents = couponOff(coupon, afterVolume);
      const shares = allocate(couponOffCents, lines.map((l) => l.netCents));
      lines.forEach((l, i) => {
        l.netCents -= shares[i];
      });
      const goods = afterVolume - couponOffCents;

      const weight = sum(lines.map((l) => l.weightG));
      let shipping = weight === 0 ? 0 : shippingCents(weight);
      const freeCoupon = coupon && coupon.type === 'freeship' && afterVolume >= coupon.minGoodsCents;
      if (goods >= FREE_FROM_CENTS || freeCoupon) shipping = 0;

      const taxByClass = { standard: 0, reduced: 0, zero: 0 };
      for (const cls of Object.keys(taxByClass)) {
        taxByClass[cls] = taxOn(sum(lines.filter((l) => l.taxClass === cls).map((l) => l.netCents)), cls);
      }
      taxByClass.standard += taxOn(shipping, 'standard');
      const taxCents = sum(Object.values(taxByClass));

      return {
        lines: lines.map(({ taxClass, weightG, ...pub }) => pub),
        subtotalCents,
        volumeOffCents,
        couponOffCents,
        shippingCents: shipping,
        taxByClass,
        taxCents,
        totalCents: goods + shipping + taxCents,
      };
    }

    module.exports = { price };
''')

FORMAT = dd(r'''
    'use strict';

    // Integer cents as text: 1299 -> "12.99", -315 -> "-3.15".
    function money(cents) {
      const sign = cents < 0 ? '-' : '';
      const abs = Math.abs(cents);
      return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`;
    }

    function receipt(p) {
      const rows = p.lines.map(
        (l) => `${l.sku.padEnd(8)}${String(l.qty).padStart(3)} x ${money(l.unitCents).padStart(8)} ${money(l.listCents).padStart(9)}`
      );
      const sumRow = (label, cents) => `${label.padEnd(14)}${money(cents).padStart(12)}`;
      rows.push(sumRow('Subtotal', p.subtotalCents));
      if (p.volumeOffCents) rows.push(sumRow('Volume', -p.volumeOffCents));
      if (p.couponOffCents) rows.push(sumRow('Coupon', -p.couponOffCents));
      rows.push(sumRow('Shipping', p.shippingCents));
      rows.push(sumRow('Tax', p.taxCents));
      rows.push(sumRow('Total', p.totalCents));
      return rows.join('\n') + '\n';
    }

    module.exports = { money, receipt };
''')

VISIBLE = {
    "test/basic.test.js": dd('''
        'use strict';
        const test = require('node:test');
        const assert = require('node:assert');
        const { Cart } = require('../src/cart');
        const { CATALOG } = require('../src/catalog');
        const { price } = require('../src/pricing');

        test('same sku merges', () => {
          const c = new Cart().add('pen', 2).add('pen').add('book');
          assert.deepStrictEqual(c.lines(), [{ sku: 'pen', qty: 3 }, { sku: 'book', qty: 1 }]);
          assert.strictEqual(c.count(), 4);
        });

        test('a small order', () => {
          const c = new Cart().add('pen', 3).add('book');
          const p = price(c, CATALOG);
          assert.strictEqual(p.subtotalCents, 1749);
          assert.strictEqual(p.shippingCents, 490);
          assert.strictEqual(p.totalCents, 2492);
        });
    '''),
}

HIDDEN = {
    "test/hidden.test.js": dd(r'''
        'use strict';
        const test = require('node:test');
        const assert = require('node:assert');
        const { Cart } = require('../src/cart');
        const { CATALOG } = require('../src/catalog');
        const { price } = require('../src/pricing');
        const { COUPONS, volumePercent, couponOff } = require('../src/rules');
        const { shippingCents } = require('../src/shipping');
        const { allocate, percentOf } = require('../src/money');
        const { taxOn } = require('../src/tax');
        const { money, receipt } = require('../src/format');

        const cartOf = (pairs) => pairs.reduce((c, [sku, qty]) => c.add(sku, qty), new Cart());

        // ---- cart ------------------------------------------------------------------------------------------------

        test('quantities from forms are numbers', () => {
          const c = new Cart().add('pen', '2').add('pen', '3').add('book', 1);
          assert.deepStrictEqual(c.lines(), [{ sku: 'pen', qty: 5 }, { sku: 'book', qty: 1 }]);
          assert.strictEqual(typeof c.lines()[0].qty, 'number');
          assert.strictEqual(c.count(), 6);
          c.setQty('pen', '7');
          assert.strictEqual(c.lines()[0].qty, 7);
        });

        test('bad quantities are refused', () => {
          const c = new Cart();
          for (const bad of [0, -1, 1.5, 'x', '', '1.5', ' 2', NaN, null, true]) {
            assert.throws(() => c.add('pen', bad), RangeError, String(bad));
          }
          assert.throws(() => c.setQty('pen', -2), RangeError);
          assert.strictEqual(c.count(), 0);
        });

        test('set quantity zero removes the line', () => {
          const c = cartOf([['pen', 2], ['book', 1]]);
          c.setQty('pen', 0);
          assert.deepStrictEqual(c.lines(), [{ sku: 'book', qty: 1 }]);
          c.setQty('book', '0');
          assert.deepStrictEqual(c.lines(), []);
          c.setQty('tea', 3);
          assert.deepStrictEqual(c.lines(), [{ sku: 'tea', qty: 3 }]);
          c.remove('tea').remove('nothing');
          assert.strictEqual(c.count(), 0);
        });

        test('lines() hands out copies', () => {
          const c = cartOf([['pen', 2], ['book', 1]]);
          const first = c.lines();
          first.reverse();
          first[0].qty = 99;
          first.push({ sku: 'x', qty: 1 });
          assert.deepStrictEqual(c.lines(), [{ sku: 'pen', qty: 2 }, { sku: 'book', qty: 1 }]);
        });

        // ---- rules -----------------------------------------------------------------------------------------------

        test('volume tiers', () => {
          const got = [1, 9, 10, 11, 24, 25, 26, 100].map(volumePercent);
          assert.deepStrictEqual(got, [0, 0, 10, 10, 10, 15, 15, 15]);
        });

        test('coupons', () => {
          assert.strictEqual(couponOff(COUPONS.SAVE10, 2999), 0);
          assert.strictEqual(couponOff(COUPONS.SAVE10, 3000), 300);
          assert.strictEqual(couponOff(COUPONS.SAVE10, 3148), 315);
          assert.strictEqual(couponOff(COUPONS.SAVE10, 100000), 2500);
          assert.strictEqual(couponOff(COUPONS.SAVE10, 25000), 2500);
          assert.strictEqual(couponOff(COUPONS.FIVE, 300), 300);
          assert.strictEqual(couponOff(COUPONS.FIVE, 5000), 500);
          assert.strictEqual(couponOff(COUPONS.FIVE, 0), 0);
          assert.strictEqual(couponOff(COUPONS.SHIPFREE, 99999), 0);
          assert.strictEqual(couponOff(null, 5000), 0);
        });

        test('shipping tiers include their upper bound', () => {
          const got = [1, 500, 501, 2000, 2001, 10000, 10001, 18000].map(shippingCents);
          assert.deepStrictEqual(got, [490, 490, 790, 790, 1290, 1290, 1990, 1990]);
        });

        // ---- money helpers ---------------------------------------------------------------------------------------

        test('percentOf rounds halves up', () => {
          assert.strictEqual(percentOf(1500, 10), 150);
          assert.strictEqual(percentOf(145, 10), 15);
          assert.strictEqual(percentOf(3750, 15), 563);
          assert.strictEqual(percentOf(0, 15), 0);
        });

        test('allocate adds up exactly', () => {
          assert.deepStrictEqual(allocate(100, [1, 1, 1]), [34, 33, 33]);
          assert.deepStrictEqual(allocate(5, [3, 3]), [3, 2]);
          assert.deepStrictEqual(allocate(315, [1350, 1798]), [135, 180]);
          assert.deepStrictEqual(allocate(0, [5, 6]), [0, 0]);
          assert.deepStrictEqual(allocate(10, [0, 0]), [0, 0]);
          let seed = 7;
          const rnd = (n) => {
            seed = (seed * 48271) % 2147483647;
            return seed % n;
          };
          for (let i = 0; i < 300; i++) {
            const weights = Array.from({ length: 1 + rnd(5) }, () => rnd(5000));
            const total = rnd(3000);
            const shares = allocate(total, weights);
            const wsum = weights.reduce((a, b) => a + b, 0);
            if (wsum === 0) continue;
            assert.strictEqual(shares.reduce((a, b) => a + b, 0), total, JSON.stringify([total, weights]));
            shares.forEach((s, k) => {
              const exact = (total * weights[k]) / wsum;
              assert.ok(Math.abs(s - exact) < 1, JSON.stringify([total, weights, shares]));
            });
          }
        });

        // ---- worked examples -------------------------------------------------------------------------------------

        test('example: small order', () => {
          const p = price(cartOf([['pen', 3], ['book', 1]]), CATALOG);
          assert.strictEqual(p.subtotalCents, 1749);
          assert.strictEqual(p.shippingCents, 490);
          assert.deepStrictEqual(p.taxByClass, { standard: 90 + 98, reduced: 65, zero: 0 });
          assert.strictEqual(p.taxCents, 253);
          assert.strictEqual(p.totalCents, 2492);
          assert.deepStrictEqual(p.lines.map((l) => l.sku), ['book', 'pen']);
          assert.deepStrictEqual(Object.keys(p.lines[0]).sort(), ['listCents', 'netCents', 'qty', 'sku', 'unitCents', 'volumeOffCents']);
        });

        test('example: volume discount and a percent coupon with allocation', () => {
          const p = price(cartOf([['tea', 2], ['pen', 10]]), CATALOG, { coupon: COUPONS.SAVE10 });
          assert.strictEqual(p.subtotalCents, 3298);
          assert.strictEqual(p.volumeOffCents, 150);
          assert.strictEqual(p.couponOffCents, 315);
          assert.deepStrictEqual(p.lines.map((l) => [l.sku, l.netCents]), [['pen', 1215], ['tea', 1618]]);
          assert.strictEqual(p.shippingCents, 790);
          assert.deepStrictEqual(p.taxByClass, { standard: 243 + 158, reduced: 81, zero: 0 });
          assert.strictEqual(p.totalCents, 4105);
        });

        test('example: the 15 percent tier and the 500 g shipping boundary', () => {
          const p = price(cartOf([['pen', 25]]), CATALOG);
          assert.strictEqual(p.volumeOffCents, 563);
          assert.strictEqual(p.lines[0].netCents, 3187);
          assert.strictEqual(p.shippingCents, 490);
          assert.strictEqual(p.totalCents, 3187 + 490 + 637 + 98);
        });

        test('volume tiers do not stack', () => {
          const p = price(cartOf([['book', 30]]), CATALOG);
          assert.strictEqual(p.volumeOffCents, percentOf(38970, 15));
          const q = price(cartOf([['book', 10]]), CATALOG);
          assert.strictEqual(q.volumeOffCents, 1299);
        });

        test('the coupon minimum is judged after volume discounts', () => {
          // list 3000, after the 10 percent volume tier 2700: SAVE10 needs 3000 after volume discounts
          const p = price(cartOf([['pen', 20]]), CATALOG, { coupon: COUPONS.SAVE10 });
          assert.strictEqual(p.subtotalCents, 3000);
          assert.strictEqual(p.couponOffCents, 0);
          const q = price(cartOf([['pen', 20], ['seed', 2]]), CATALOG, { coupon: COUPONS.SAVE10 });
          assert.strictEqual(q.couponOffCents, 310);
        });

        test('a percent coupon is based on the discounted goods and capped', () => {
          const p = price(cartOf([['book', 20], ['lamp', 12]]), CATALOG, { coupon: COUPONS.SAVE10 });
          const after = 1299 * 20 - percentOf(1299 * 20, 10) + 4590 * 12 - percentOf(4590 * 12, 10);
          assert.strictEqual(p.couponOffCents, Math.min(percentOf(after, 10), 2500));
          assert.strictEqual(p.couponOffCents, 2500);
        });

        test('a fixed coupon never goes below zero goods', () => {
          const p = price(cartOf([['clip', 2]]), CATALOG, { coupon: COUPONS.FIVE });
          assert.strictEqual(p.couponOffCents, 204);
          assert.strictEqual(p.lines[0].netCents, 0);
          assert.strictEqual(p.taxByClass.standard, taxOn(490, 'standard'));
          assert.ok(p.totalCents >= 0);
        });

        test('free shipping starts at 100.00 of goods after all discounts', () => {
          assert.strictEqual(price(cartOf([['desk', 1]]), CATALOG).shippingCents, 0);
          const lines = [['pen', 2], ['lamp', 2], ['clip', 5], ['pin', 5]]; // 105.00 list
          const p = price(cartOf(lines), CATALOG, { coupon: COUPONS.FIVE }); // exactly 100.00 left
          assert.strictEqual(p.subtotalCents, 10500);
          assert.strictEqual(p.couponOffCents, 500);
          assert.strictEqual(p.shippingCents, 0);
          const lower = [['pen', 2], ['lamp', 2], ['clip', 5], ['pin', 4]]; // 103.98 list
          assert.strictEqual(price(cartOf(lower), CATALOG).shippingCents, 0);
          assert.strictEqual(price(cartOf(lower), CATALOG, { coupon: COUPONS.FIVE }).shippingCents, 1290); // 98.98 left
          // volume discounts count as well: 107.88 list, 97.09 after the 10 percent tier
          const tea = price(cartOf([['tea', 12]]), CATALOG);
          assert.strictEqual(tea.subtotalCents, 10788);
          assert.strictEqual(tea.shippingCents, 1290);
        });

        test('SHIPFREE needs its minimum after volume discounts', () => {
          const below = price(cartOf([['pen', 10], ['seed', 2]]), CATALOG, { coupon: COUPONS.SHIPFREE }); // 1500 -150 + 398 = 1748
          assert.strictEqual(below.shippingCents, 490);
          const ok = price(cartOf([['book', 2]]), CATALOG, { coupon: COUPONS.SHIPFREE }); // 2598
          assert.strictEqual(ok.shippingCents, 0);
          assert.strictEqual(ok.couponOffCents, 0);
        });

        test('tax is rounded once per class', () => {
          const p = price(cartOf([['clip', 1], ['pin', 1]]), CATALOG);
          // standard goods 204 -> 41 (not 20 + 20), shipping 490 -> 98
          assert.strictEqual(p.taxByClass.standard, 41 + 98);
          assert.strictEqual(p.taxCents, 139);
          assert.strictEqual(p.totalCents, 204 + 490 + 139);
        });

        test('shipping is taxed at the standard rate whatever is in the cart', () => {
          const p = price(cartOf([['book', 1]]), CATALOG);
          assert.deepStrictEqual(p.taxByClass, { standard: 98, reduced: 65, zero: 0 });
          assert.strictEqual(p.totalCents, 1299 + 490 + 65 + 98);
          const z = price(cartOf([['seed', 1]]), CATALOG);
          assert.deepStrictEqual(z.taxByClass, { standard: 98, reduced: 0, zero: 0 });
        });

        test('the cart is not touched by pricing', () => {
          const c = cartOf([['tea', 2], ['pen', 10], ['book', 1]]);
          const before = JSON.stringify(c.lines());
          const first = price(c, CATALOG, { coupon: COUPONS.SAVE10 });
          assert.strictEqual(JSON.stringify(c.lines()), before);
          assert.deepStrictEqual(c.lines().map((l) => l.sku), ['tea', 'pen', 'book']);
          const second = price(c, CATALOG, { coupon: COUPONS.SAVE10 });
          assert.deepStrictEqual(second, first);
        });

        test('empty carts and unknown skus', () => {
          const p = price(new Cart(), CATALOG, { coupon: COUPONS.FIVE });
          assert.deepStrictEqual(p, {
            lines: [], subtotalCents: 0, volumeOffCents: 0, couponOffCents: 0, shippingCents: 0,
            taxByClass: { standard: 0, reduced: 0, zero: 0 }, taxCents: 0, totalCents: 0,
          });
          assert.throws(() => price(cartOf([['ghost', 1]]), CATALOG), RangeError);
        });

        // ---- formatting ------------------------------------------------------------------------------------------

        test('money', () => {
          assert.strictEqual(money(0), '0.00');
          assert.strictEqual(money(5), '0.05');
          assert.strictEqual(money(1299), '12.99');
          assert.strictEqual(money(-50), '-0.50');
          assert.strictEqual(money(-150), '-1.50');
          assert.strictEqual(money(-315), '-3.15');
          assert.strictEqual(money(1000000), '10000.00');
        });

        test('receipt', () => {
          const p = price(cartOf([['tea', 2], ['pen', 10]]), CATALOG, { coupon: COUPONS.SAVE10 });
          const expected = [
            'pen        10 x     1.50     15.00',
            'tea         2 x     8.99     17.98',
            'Subtotal           32.98',
            'Volume             -1.50',
            'Coupon             -3.15',
            'Shipping            7.90',
            'Tax                 4.82',
            'Total              41.05',
            '',
          ];
          const norm = (s) => s.split('\n').map((l) => l.replace(/ +/g, ' ')).join('\n');
          assert.strictEqual(norm(receipt(p)), norm(expected.join('\n')));
          assert.ok(receipt(p).endsWith('\n'));
        });

        // ---- a model ---------------------------------------------------------------------------------------------

        test('random carts match an independent model', () => {
          let seed = 99;
          const rnd = (n) => {
            seed = (seed * 48271) % 2147483647;
            return Math.floor(seed / 7) % n;
          };
          const skus = Object.keys(CATALOG);
          const coupons = [null, COUPONS.SAVE10, COUPONS.FIVE, COUPONS.SHIPFREE];
          const half = (num, den) => Math.floor((2 * num + den) / (2 * den)); // round half up of num/den
          for (let n = 0; n < 250; n++) {
            const picked = skus.filter(() => rnd(2) === 0);
            if (picked.length === 0) picked.push(skus[rnd(skus.length)]);
            const entries = picked.map((s) => [s, 1 + (rnd(4) === 0 ? rnd(30) : rnd(4))]);
            const coupon = coupons[rnd(4)];
            const got = price(cartOf(entries), CATALOG, { coupon });

            const rows = entries
              .slice()
              .sort((a, b) => (a[0] < b[0] ? -1 : 1))
              .map(([sku, qty]) => {
                const unit = CATALOG[sku].priceCents;
                const list = unit * qty;
                const pct = qty >= 25 ? 15 : qty >= 10 ? 10 : 0;
                const off = half(list * pct, 100);
                return { sku, qty, list, off, net: list - off, cls: CATALOG[sku].taxClass, g: CATALOG[sku].weightG * qty };
              });
            const after = rows.reduce((a, r) => a + r.net, 0);
            let cOff = 0;
            if (coupon && coupon.type === 'percent' && after >= coupon.minGoodsCents) cOff = Math.min(half(after * coupon.percent, 100), coupon.maxOffCents);
            if (coupon && coupon.type === 'fixed') cOff = Math.min(coupon.offCents, after);
            // largest remainder
            const floors = rows.map((r) => Math.floor((cOff * r.net) / after));
            let rest = cOff - floors.reduce((a, b) => a + b, 0);
            const ranked = rows.map((r, i) => [i, (cOff * r.net) % after]).sort((a, b) => b[1] - a[1] || a[0] - b[0]);
            for (let k = 0; k < rest; k++) floors[ranked[k][0]] += 1;
            rows.forEach((r, i) => { r.net -= floors[i]; });
            const goods = after - cOff;
            const grams = rows.reduce((a, r) => a + r.g, 0);
            let ship = grams <= 500 ? 490 : grams <= 2000 ? 790 : grams <= 10000 ? 1290 : 1990;
            if (goods >= 10000 || (coupon && coupon.type === 'freeship' && after >= coupon.minGoodsCents)) ship = 0;
            const tax = { standard: 0, reduced: 0, zero: 0 };
            const bp = { standard: 20, reduced: 5, zero: 0 };
            for (const cls of Object.keys(tax)) {
              const net = rows.filter((r) => r.cls === cls).reduce((a, r) => a + r.net, 0);
              tax[cls] = half(net * bp[cls], 100);
            }
            tax.standard += half(ship * 20, 100);
            const total = goods + ship + tax.standard + tax.reduced + tax.zero;
            const label = JSON.stringify([entries, coupon && coupon.code]);
            assert.strictEqual(got.totalCents, total, label);
            assert.deepStrictEqual(got.taxByClass, tax, label);
            assert.strictEqual(got.shippingCents, ship, label);
            assert.strictEqual(got.couponOffCents, cOff, label);
            assert.deepStrictEqual(got.lines.map((l) => l.netCents), rows.map((r) => r.net), label);
          }
        });
    '''),
}


def _prompts() -> dict:
    p = {}
    p["stack"] = (
        "Large orders are cheaper than the price list says: a line of 30 books is discounted by 25 %, while the price list promises "
        "15 % from 25 pieces (and 10 % from 10), not both."
    )
    p["boundary"] = (
        "A customer who ordered exactly 10 pens got no volume discount; the price list says 'from 10 pieces'. The same happens at exactly 25."
    )
    p["cap"] = "SAVE10 took 74.00 off a big furniture order. The coupon terms say it is 10 % with a maximum of 25.00."
    p["fixed"] = (
        "Coupon FIVE on a very small cart (two clips, 2.04) leaves a negative goods amount on the invoice. A coupon never takes off more "
        "than the goods are worth."
    )
    p["coupon-base"] = (
        "SAVE10 is calculated on the prices *before* volume discounts: a customer with 20 pens (30.00 list, 27.00 after the volume tier) still "
        "gets the coupon, although its minimum of 30.00 and its 10 % both refer to the amount after volume discounts."
    )
    p["alloc"] = (
        "On some coupon orders the line amounts after the coupon (`netCents`) add up to a cent or two less than "
        "`subtotalCents - volumeOffCents - couponOffCents`. Finance cannot reconcile those invoices."
    )
    p["tax-line"] = (
        "Two lines of 1.02 each show 0.20 + 0.20 of 20 % tax on the invoice. Our tax rule is to round once per tax class on the sum of the "
        "amounts (2.04 gives 0.41)."
    )
    p["free-list"] = (
        "Orders where a coupon brings the goods below 100.00 still ship for free, because the list price was above 100.00. Free shipping is "
        "for orders whose goods cost at least 100.00 after all discounts."
    )
    p["ship-tax"] = (
        "A customer who ordered a single book (reduced rate) was charged 0.25 tax on the shipping instead of 0.98. The shipping seems to be "
        "taxed like the first item."
    )
    p["tier"] = (
        "A parcel of exactly 500 g (25 pens) is charged 7.90; the tariff says up to and including 500 g costs 4.90. Same at 2000 g and 10000 g."
    )
    p["qty-text"] = (
        "The quantity box of the web form posts text. Adding 2 pens and then 3 more gives 23 pens in the cart (and the line is priced as 23 "
        "pens). The README says form text is converted to a number."
    )
    p["leak"] = (
        "After the checkout preview, the items on the cart page are reordered alphabetically: we add `tea`, `pen` and `book` and afterwards "
        "see book, pen, tea. Looking at the module that builds the preview I do not see it assign to the cart. The cart must not be changed by pricing."
    )
    p["neg-format"] = (
        "Receipts show a discount of -1.50 as -2.50 and one of -0.50 as -1.50: the discount rows are off by a euro, positive amounts are right."
    )
    p["coupon-pair"] = (
        "Finance report on coupon orders, two findings. (1) SAVE10 is applied to the price before volume discounts, so both its minimum and its "
        "10 % are computed on the wrong amount. (2) After the coupon the line amounts do not add up to the goods total (a cent or two missing). "
        "Please fix both."
    )
    p["accountant"] = (
        "Our accountant compared 40 invoices with her own spreadsheet and found cent differences in three of them. All of them are in the tax "
        "lines or the totals: one order had several lines in the same tax class, one used a coupon, and one contained only reduced-rate items. "
        "Find out why and make the pricing follow the README."
    )
    return p


def _base() -> Base:
    P = _prompts()
    good = {
        "README.md": README, "package.json": PKG, "src/money.js": MONEY, "src/catalog.js": CATALOG, "src/cart.js": CART,
        "src/rules.js": RULES, "src/shipping.js": SHIPPING, "src/tax.js": TAX, "src/pricing.js": PRICING, "src/format.js": FORMAT,
    }
    mo, ca, ru, sh, pr, fo = "src/money.js", "src/cart.js", "src/rules.js", "src/shipping.js", "src/pricing.js", "src/format.js"
    stack = ("function volumePercent(qty) {\n  for (const t of VOLUME_TIERS) {\n    if (qty >= t.minQty) return t.percent;\n  }\n  return 0;\n}\n",
             "function volumePercent(qty) {\n  return VOLUME_TIERS.filter((t) => qty >= t.minQty).reduce((a, t) => a + t.percent, 0);\n}\n")
    boundary = ("    if (qty >= t.minQty) return t.percent;\n", "    if (qty > t.minQty) return t.percent;\n")
    cap = ("  if (coupon.type === 'percent') return Math.min(percentOf(goodsCents, coupon.percent), coupon.maxOffCents);\n",
           "  if (coupon.type === 'percent') return percentOf(goodsCents, coupon.percent);\n")
    fixed = ("  if (coupon.type === 'fixed') return Math.min(coupon.offCents, goodsCents);\n", "  if (coupon.type === 'fixed') return coupon.offCents;\n")
    tier = ("    if (weightG <= t.maxG) return t.cents;\n", "    if (weightG < t.maxG) return t.cents;\n")
    qty_text = ("  if (!Number.isInteger(n) || n < 0) throw new RangeError(`bad quantity ${JSON.stringify(q)}`);\n  return n;\n",
                "  if (!Number.isInteger(n) || n < 0) throw new RangeError(`bad quantity ${JSON.stringify(q)}`);\n  return q;\n")
    leak_cart = ("    return this._lines.map((l) => ({ ...l }));\n", "    return this._lines;\n")
    leak_pricing = ("  const lines = [...cart.lines()]\n", "  const lines = cart.lines()\n")
    base_bug = ("  const couponOffCents = couponOff(coupon, afterVolume);\n", "  const couponOffCents = couponOff(coupon, subtotalCents);\n")
    alloc = ("  for (let k = 0; left > 0; k++, left--) shares[order[k].i] += 1;\n", "")
    tax_line = ("    taxByClass[cls] = taxOn(sum(lines.filter((l) => l.taxClass === cls).map((l) => l.netCents)), cls);\n",
                "    taxByClass[cls] = sum(lines.filter((l) => l.taxClass === cls).map((l) => taxOn(l.netCents, cls)));\n")
    free_list = ("  if (goods >= FREE_FROM_CENTS || freeCoupon) shipping = 0;\n", "  if (subtotalCents >= FREE_FROM_CENTS || freeCoupon) shipping = 0;\n")
    ship_tax = ("  taxByClass.standard += taxOn(shipping, 'standard');\n",
                "  const shipClass = lines.length ? lines[0].taxClass : 'standard';\n  taxByClass[shipClass] += taxOn(shipping, shipClass);\n")
    neg = ("  const sign = cents < 0 ? '-' : '';\n  const abs = Math.abs(cents);\n  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`;\n",
           "  return `${Math.floor(cents / 100)}.${String(Math.abs(cents) % 100).padStart(2, '0')}`;\n")
    bugs = [
        Bug("volume-tiers-add-up", 2, {ru: [stack]}, P["stack"]),
        Bug("volume-starts-above-the-tier-quantity", 2, {ru: [boundary]}, P["boundary"]),
        Bug("percent-coupon-has-no-cap", 2, {ru: [cap]}, P["cap"]),
        Bug("fixed-coupon-can-exceed-the-goods", 2, {ru: [fixed]}, P["fixed"]),
        Bug("weight-tier-excludes-its-bound", 2, {sh: [tier]}, P["tier"]),
        Bug("form-quantities-stay-text", 2, {ca: [qty_text]}, P["qty-text"]),
        Bug("negative-amounts-round-down", 2, {fo: [neg]}, P["neg-format"]),
        Bug("coupon-computed-before-volume-discounts", 3, {pr: [base_bug]}, P["coupon-base"]),
        Bug("allocation-drops-the-remainder", 3, {mo: [alloc]}, P["alloc"]),
        Bug("tax-rounded-per-line", 3, {pr: [tax_line]}, P["tax-line"]),
        Bug("free-shipping-judged-on-list-prices", 3, {pr: [free_list]}, P["free-list"]),
        Bug("shipping-takes-the-class-of-the-first-line", 3, {pr: [ship_tax]}, P["ship-tax"]),
        Bug("cart-lines-leak-and-pricing-sorts-them", 4, {ca: [leak_cart], pr: [leak_pricing]}, P["leak"]),
        Bug("coupon-base-and-allocation", 4, {pr: [base_bug], mo: [alloc]}, P["coupon-pair"]),
        Bug("accountant-cent-differences", 5, {mo: [alloc], pr: [tax_line, ship_tax]}, P["accountant"]),
    ]
    return Base("cartflow", "javascript", good, VISIBLE, HIDDEN, bugs)


@family("fix-hand-cart-flow", category="fix", lang="javascript", kind="fix", n=15,
        summary="a layered javascript pricing pipeline (cart, volume and coupon rules, allocation, shipping, tax, receipt) with cross-module defects")
def gen(rng, n):
    return tasks_from([_base()])
