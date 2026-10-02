"""stallcart (javascript): a market-stall checkout library extended with bulk prices, codes, tax, limits, plugins, cache."""
import json
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # stallcart

    A tiny checkout library for farmers'-market stalls (Node.js, CommonJS, no dependencies). Money is always an integer
    number of cents. Run the tests with `npm test` (`node --test test/*.test.js`).

    ## Layout

    * `index.js`: exports `Cart` and `money`.
    * `src/cart.js`: the `Cart` class.
    * `src/format.js`: `money()`.

    ## Basics

    The catalogue is a plain object `{ sku: { name, price } }` with `price` in cents.

    * `new Cart(catalog, options = {})`.
    * `cart.add(sku, qty = 1)`: `qty` must be a positive integer (`RangeError` otherwise); an unknown sku throws an `Error`.
      Adding a sku that is already in the cart increases its quantity. `add` returns nothing.
    * `cart.remove(sku, qty)`: removes `qty` units, or the whole line when `qty` is omitted. An sku that is not in the
      cart throws an `Error`; a `qty` that is not a positive integer or exceeds the quantity in the cart throws a
      `RangeError`; a line that reaches zero disappears.
    * `cart.lines()`: array of `{ sku, name, qty, unitPrice, amount }` ordered by sku.
    * `cart.subtotal()`: the sum of the line amounts. `cart.total()`: what the customer pays; for now the subtotal.
    * `money(cents)`: text such as `$12.50` (`-$0.05` for negative amounts).
''')

CART = '''\
'use strict';
const { money } = require('./format');
@@uniq requires

// n / d rounded to the nearest integer, halves up (n >= 0, d > 0)
const roundHalfUp = (n, d) => Math.floor((2 * n + d) / (2 * d));

class Cart {
  constructor(catalog, options = {}) {
    this.catalog = catalog;
    this.items = new Map();
    @@slot init
  }

  @@default unit_price
  unitPrice(sku, qty) {
    return this.catalog[sku].price;
  }
  @@end

  add(sku, qty = 1) {
    if (!Number.isInteger(qty) || qty < 1) throw new RangeError('qty must be a positive integer');
    if (!this.catalog[sku]) throw new Error(`unknown sku: ${sku}`);
    @@slot add_checks
    this.items.set(sku, (this.items.get(sku) || 0) + qty);
    @@slot on_add
    @@default add_return
    @@end
  }

  remove(sku, qty) {
    const have = this.items.get(sku);
    if (have === undefined) throw new Error(`not in cart: ${sku}`);
    if (qty === undefined) qty = have;
    if (!Number.isInteger(qty) || qty < 1 || qty > have) throw new RangeError(`cannot remove ${qty} of ${sku} (have ${have})`);
    if (qty === have) this.items.delete(sku);
    else this.items.set(sku, have - qty);
    @@slot on_remove
  }

  lines() {
    return [...this.items.keys()].sort().map((sku) => {
      const qty = this.items.get(sku);
      const unitPrice = this.unitPrice(sku, qty);
      return { sku, name: this.catalog[sku].name, qty, unitPrice, amount: unitPrice * qty };
    });
  }

  subtotal() {
    return this.lines().reduce((sum, l) => sum + l.amount, 0);
  }

  total() {
    @@slot total_enter
    let amount = this.subtotal();
    @@slot total_steps
    @@slot total_leave
    return amount;
  }

  _money(cents) {
    @@default money_call
    return money(cents);
    @@end
  }

  @@blocks methods
}

module.exports = { Cart, roundHalfUp };
'''

FORMAT = '''\
'use strict';

@@default money_fn
function money(cents) {
  const abs = Math.abs(cents);
  return `${cents < 0 ? '-' : ''}$${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`;
}
@@end

module.exports = { money };
'''

INDEX = '''\
'use strict';
const { Cart } = require('./src/cart');
const { money } = require('./src/format');

module.exports = { Cart, money };
'''

TEST_HEAD = '''\
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
@@uniq requires
const { Cart, money } = require('../index.js');

const CATALOG = {
  'AP-1': { name: 'Apples 1kg', price: 450 },
  'HN-1': { name: 'Honey jar', price: 1100 },
  'CH-2': { name: 'Goat cheese', price: 780 },
  'EG-6': { name: 'Eggs (6)', price: 360 },
  'BR-1': { name: 'Sourdough', price: 620 },
};
const mk = (options) => new Cart(CATALOG, options);
'''

VISIBLE = TEST_HEAD + '''
test('add, lines and subtotal', () => {
  const c = mk();
  c.add('EG-6', 2);
  c.add('AP-1');
  c.add('EG-6');
  assert.deepEqual(c.lines(), [
    { sku: 'AP-1', name: 'Apples 1kg', qty: 1, unitPrice: 450, amount: 450 },
    { sku: 'EG-6', name: 'Eggs (6)', qty: 3, unitPrice: 360, amount: 1080 },
  ]);
  assert.equal(c.subtotal(), 1530);
  assert.equal(c.total(), 1530);
});

test('remove', () => {
  const c = mk();
  c.add('BR-1', 3);
  c.remove('BR-1', 1);
  assert.equal(c.lines()[0].qty, 2);
  c.remove('BR-1');
  assert.deepEqual(c.lines(), []);
  assert.throws(() => c.remove('BR-1'), Error);
});

test('money', () => {
  assert.equal(money(1250), '$12.50');
  assert.equal(money(5), '$0.05');
  assert.equal(money(-5), '-$0.05');
});
@@blocks tests
'''

HIDDEN = TEST_HEAD + '''
test('base validation', () => {
  const c = mk();
  assert.throws(() => c.add('NOPE'), /unknown sku: NOPE/);
  for (const bad of [0, -1, 1.5, '2']) assert.throws(() => c.add('AP-1', bad), RangeError);
  assert.deepEqual(c.lines(), []);
  c.add('AP-1', 2);
  assert.throws(() => c.remove('AP-1', 3), RangeError);
  assert.throws(() => c.remove('AP-1', 0), RangeError);
  assert.throws(() => c.remove('EG-6'), /not in cart/);
  assert.equal(c.lines()[0].qty, 2);
});

test('base money and ordering', () => {
  const c = mk();
  c.add('HN-1');
  c.add('AP-1');
  assert.deepEqual(c.lines().map((l) => l.sku), ['AP-1', 'HN-1']);
  assert.equal(c.total(), 1550);
  assert.equal(money(0), '$0.00');
  assert.equal(money(100000), '$1000.00');
});
@@blocks tests
'''


def make_slices(rng: random.Random):
    bulk_min = rng.choice([3, 4, 5])
    pct = rng.choice([10, 15, 20])
    off, off_min = rng.choice([(500, 2000), (300, 1500), (700, 3000)])
    taxbp = rng.choice([800, 1000, 1250, 1900])
    per_line = rng.choice([3, 5, 8])
    max_lines = rng.choice([2, 3, 4])
    curs = rng.sample([
        ("GBP", "£{}", "£12.50", ".", "£1.00", "£1234.56"),
        ("EUR", "{} €", "12,50 €", ",", "1,00 €", "1234,56 €"),
        ("CHF", "CHF {}", "CHF 12.50", ".", "CHF 1.00", "CHF 1234.56"),
        ("SEK", "{} kr", "12,50 kr", ",", "1,00 kr", "1234,56 kr"),
    ], 2)
    width = rng.choice([30, 32, 36])
    S = []

    S.append(Slice(
        id="bulk-price", title="Bulk prices", d=2,
        pitch=("Honey and eggs sell better when the stall can offer a lower unit price for bigger purchases.",
               "The stall wants quantity discounts that do not need a manual price change at the till."),
        reqs=(f"A catalogue entry may carry `bulk: {{ min, price }}` (integers; `min` units or more of that sku in the cart are charged `price` cents **each**, all of them, not only the extra ones). Below `min` the normal `price` applies.",
              "The line's `unitPrice` and `amount` in `lines()` show the price in force, and `subtotal()` and `total()` follow. Entries without `bulk` behave as before."),
        code={
            "src/cart.js::unit_price": '''
                unitPrice(sku, qty) {
                  const item = this.catalog[sku];
                  return item.bulk && qty >= item.bulk.min ? item.bulk.price : item.price;
                }
            ''',
        },
        readme=dd('''
            ## Bulk prices

            A catalogue entry can have `bulk: { min, price }`: when a line holds `min` or more units, every unit is charged `price`
            cents. `lines()`, `subtotal()` and `total()` use the price in force.
        '''),
        vtests='''
            test('bulk price applies from min', () => {
              const c = new Cart({ X: { name: 'X', price: 100, bulk: { min: 3, price: 80 } } });
              c.add('X', 3);
              assert.equal(c.subtotal(), 240);
            });
        ''',
        tests=fmt('''
            test('bulk price thresholds', () => {
              const cat = { ...CATALOG, 'HN-1': { name: 'Honey jar', price: 1100, bulk: { min: __MIN__, price: 1000 } } };
              const c = new Cart(cat);
              c.add('HN-1', __MIN__ - 1);
              assert.equal(c.lines()[0].unitPrice, 1100);
              assert.equal(c.subtotal(), 1100 * (__MIN__ - 1));
              c.add('HN-1');
              assert.deepEqual(c.lines()[0], { sku: 'HN-1', name: 'Honey jar', qty: __MIN__, unitPrice: 1000, amount: 1000 * __MIN__ });
              assert.equal(c.total(), 1000 * __MIN__);
              c.remove('HN-1', 1);
              assert.equal(c.lines()[0].unitPrice, 1100);
            });

            test('bulk only on entries that have it', () => {
              const cat = { ...CATALOG, 'EG-6': { name: 'Eggs (6)', price: 360, bulk: { min: 2, price: 300 } } };
              const c = new Cart(cat);
              c.add('EG-6', 10);
              c.add('AP-1', 10);
              assert.deepEqual(c.lines().map((l) => l.unitPrice), [450, 300]);
              assert.equal(c.subtotal(), 4500 + 3000);
            });
        ''', MIN=bulk_min),
    ))

    S.append(Slice(
        id="promo-codes", title="Promo codes", d=3,
        pitch=("The stall hands out printed vouchers at the weekend market and the till has to honour them.",
               "Marketing wants to give out voucher codes; the checkout needs to understand them."),
        reqs=("The `Cart` option `codes` maps a code to a rule: `{ percent: N }` (an integer from 1 to 100) or `{ off: cents, min: cents }` (`min` optional, default 0).",
              "`cart.applyCode(code)` activates a code, matching it ignoring case against the keys of `codes`; an unknown code throws an `Error` and leaves the previously active code (if any) in place. Applying a code replaces the active one. `cart.clearCode()` removes it. `cart.code` is the active code as it is spelled in `codes`, or `null`.",
              "`cart.discount()` is the discount in cents on the current subtotal: for `percent`, `percent` % of the subtotal rounded to the nearest cent, halves up; for `off`, `off` when the subtotal is at least `min` (otherwise 0), never more than the subtotal. It is 0 without an active code. `cart.total()` is `subtotal() - discount()`; the code stays active while the cart changes, so the discount is always computed on the current subtotal."),
        code={
            "src/cart.js::init": "this.codes = options.codes || {};\nthis.code = null;",
            "src/cart.js::total_steps": "amount -= this.discount();",
            "src/cart.js::methods": '''
                applyCode(code) {
                  const key = Object.keys(this.codes).find((k) => k.toLowerCase() === String(code).toLowerCase());
                  if (key === undefined) throw new Error(`unknown code: ${code}`);
                  this.code = key;
                  @@slot code_changed
                }

                clearCode() {
                  this.code = null;
                  @@slot code_changed
                }

                discount() {
                  if (this.code === null) return 0;
                  const rule = this.codes[this.code];
                  const sub = this.subtotal();
                  if (rule.percent !== undefined) return roundHalfUp(sub * rule.percent, 100);
                  return sub >= (rule.min || 0) ? Math.min(rule.off, sub) : 0;
                }
            ''',
        },
        readme=dd('''
            ## Promo codes

            `new Cart(catalog, { codes })` with rules `{ percent }` or `{ off, min }`. `applyCode(code)` (case-insensitive; unknown
            codes throw and keep the old one), `clearCode()`, `cart.code`. `discount()` is the percentage (rounded half up) or the
            fixed amount (only from `min` upwards, never above the subtotal); `total()` subtracts it.
        '''),
        vtests='''
            test('percent code basics', () => {
              const c = mk({ codes: { HALF: { percent: 50 } } });
              c.add('AP-1', 2);
              c.applyCode('half');
              assert.equal(c.discount(), 450);
              assert.equal(c.total(), 450);
            });
        ''',
        tests=fmt('''
            test('percent codes round half up', () => {
              const c = mk({ codes: { SPRING: { percent: __PCT__ }, HALF: { percent: 50 } } });
              c.add('AP-1', 3);
              c.applyCode('Spring');
              assert.equal(c.code, 'SPRING');
              assert.equal(c.discount(), Math.floor((1350 * __PCT__ * 2 + 100) / 200));
              assert.equal(c.total(), 1350 - c.discount());
              c.applyCode('half');
              assert.equal(c.discount(), 675);
              const odd = mk({ codes: { HALF: { percent: 50 } } });
              odd.add('EG-6');
              odd.add('BR-1');
              odd.add('AP-1');
              odd.applyCode('HALF');
              assert.equal(odd.subtotal(), 1430);
              assert.equal(odd.discount(), 715);
              odd.add('CH-2');
              assert.equal(odd.discount(), 1105);
              const rnd = mk({ codes: { P: { percent: 10 } } });
              rnd.add('AP-1');
              rnd.applyCode('P');
              assert.equal(rnd.discount(), 45);
              rnd.add('CH-2');
              assert.equal(rnd.subtotal(), 1230);
              assert.equal(rnd.discount(), 123);
              const hf = mk({ codes: { Q: { percent: 15 } } });
              hf.add('AP-1');
              hf.add('CH-2');
              hf.applyCode('Q');
              assert.equal(hf.discount(), 185);
            });

            test('fixed codes need their minimum', () => {
              const c = mk({ codes: { FIXED: { off: __OFF__, min: __MIN__ }, FREE: { off: 100000 } } });
              c.add('BR-1');
              c.applyCode('FIXED');
              assert.equal(c.discount(), 0);
              assert.equal(c.total(), 620);
              c.add('HN-1', Math.ceil(__MIN__ / 1100));
              assert.equal(c.discount(), __OFF__);
              assert.equal(c.total(), c.subtotal() - __OFF__);
              c.applyCode('free');
              assert.equal(c.discount(), c.subtotal());
              assert.equal(c.total(), 0);
              c.clearCode();
              assert.equal(c.discount(), 0);
              assert.equal(c.code, null);
            });

            test('codes: unknown, replace, follow the cart', () => {
              const c = mk({ codes: { A: { percent: 10 }, B: { percent: 20 } } });
              assert.equal(c.code, null);
              c.add('HN-1');
              assert.throws(() => c.applyCode('NOPE'), /unknown code/);
              assert.equal(c.code, null);
              c.applyCode('A');
              assert.throws(() => c.applyCode('C'), Error);
              assert.equal(c.code, 'A');
              c.applyCode('B');
              assert.equal(c.total(), 880);
              c.add('HN-1');
              assert.equal(c.total(), 1760);
              assert.equal(mk().discount(), 0);
            });
        ''', PCT=pct, OFF=off, MIN=off_min),
    ))

    S.append(Slice(
        id="tax", title="Sales tax", d=2,
        pitch=("From next month the stall has to show tax on every sale.",
               "The till total must include sales tax."),
        reqs=(f"The `Cart` option `taxBp` is the tax rate in basis points (1 bp = 0.01 %; `{taxbp}` means {taxbp / 100:g} %), a non-negative integer, default 0. Anything else makes the constructor throw a `RangeError`.",
              "`cart.tax()` is the tax in cents on the subtotal, rounded to the nearest cent (halves up) once for the whole cart, not per line. `cart.total()` is `subtotal() + tax()`."),
        code={
            "src/cart.js::init": "this.taxBp = options.taxBp === undefined ? 0 : options.taxBp;\nif (!Number.isInteger(this.taxBp) || this.taxBp < 0) throw new RangeError('taxBp must be a non-negative integer');",
            "src/cart.js::total_steps": "amount += this.tax();",
            "src/cart.js::methods": '''
                tax() {
                  @@default tax_base
                  const base = this.subtotal();
                  @@end
                  return roundHalfUp(base * this.taxBp, 10000);
                }
            ''',
        },
        readme=dd('''
            ## Sales tax

            Option `taxBp` (basis points, non-negative integer, default 0). `tax()` is `subtotal * taxBp / 10000` rounded half up
            once per cart; `total()` adds it.
        '''),
        vtests='''
            test('tax basics', () => {
              const c = mk({ taxBp: 1000 });
              c.add('BR-1', 5);
              assert.equal(c.tax(), 310);
            });
        ''',
        tests=fmt('''
            test('tax is rounded once per cart', () => {
              const c = mk({ taxBp: __BP__ });
              c.add('EG-6');
              c.add('AP-1');
              c.add('BR-1');
              const sub = 360 + 450 + 620;
              const expected = Math.floor((2 * sub * __BP__ + 10000) / 20000);
              assert.equal(c.tax(), expected);
              assert.equal(c.total(), sub + expected);
              const perLine = [360, 450, 620].reduce((s, a) => s + Math.floor((2 * a * __BP__ + 10000) / 20000), 0);
              if (perLine !== expected) assert.notEqual(c.tax(), perLine);
            });

            test('tax defaults and validation', () => {
              const c = mk();
              c.add('AP-1');
              assert.equal(c.tax(), 0);
              assert.equal(c.total(), 450);
              for (const bad of [-1, 12.5, '800']) assert.throws(() => mk({ taxBp: bad }), RangeError);
              const half = mk({ taxBp: 5000 });
              half.add('EG-6');
              half.add('AP-1');
              assert.equal(half.tax(), 405);
              assert.equal(mk({ taxBp: 1000 }).tax(), 0);
              const r = mk({ taxBp: 50 });
              r.add('AP-1');
              assert.equal(r.tax(), 2);
            });
        ''', BP=taxbp),
        cross={
            "promo-codes": {
                "reqs": ("Tax is computed on the amount after the discount: `tax() = round(( subtotal() - discount() ) * taxBp / 10000)`, so `total()` is `subtotal() - discount() + tax()`.",),
                "code": {"src/cart.js::tax_base": "const base = this.subtotal() - this.discount();"},
                "tests": '''
                    test('tax applies after the discount', () => {
                      const c = mk({ taxBp: 1000, codes: { HALF: { percent: 50 } } });
                      c.add('HN-1', 2);
                      c.applyCode('HALF');
                      assert.equal(c.discount(), 1100);
                      assert.equal(c.tax(), 110);
                      assert.equal(c.total(), 1100 + 110);
                    });
                '''},
        },
    ))

    S.append(Slice(
        id="limits", title="Purchase limits", d=2,
        pitch=("The cheese is scarce and the stall wants to stop one customer taking the whole table.",
               "Customers sometimes key in absurd quantities; the till should refuse them."),
        reqs=(f"The `Cart` option `limits` is an object with optional `perLine` and `lines`, positive integers (anything else makes the constructor throw a `TypeError`).",
              "`add` throws a `RangeError` and changes nothing when the resulting quantity of that sku would exceed `perLine`, or when it would start a new line while the cart already has `lines` lines. Without `limits` nothing changes."),
        code={
            "src/cart.js::init": '''
                this.limits = options.limits || {};
                for (const k of ['perLine', 'lines']) {
                  const v = this.limits[k];
                  if (v !== undefined && (!Number.isInteger(v) || v < 1)) throw new TypeError(`limits.${k} must be a positive integer`);
                }
            ''',
            "src/cart.js::add_checks": '''
                const already = this.items.get(sku) || 0;
                if (this.limits.perLine !== undefined && already + qty > this.limits.perLine) throw new RangeError(`at most ${this.limits.perLine} of ${sku}`);
                if (this.limits.lines !== undefined && already === 0 && this.items.size >= this.limits.lines) throw new RangeError(`at most ${this.limits.lines} lines`);
            ''',
        },
        readme=dd('''
            ## Purchase limits

            Option `limits: { perLine, lines }`: `add` throws a `RangeError` (and changes nothing) if a line would hold more than
            `perLine` units or the cart would get more than `lines` lines.
        '''),
        vtests='''
            test('per line limit', () => {
              const c = mk({ limits: { perLine: 2 } });
              c.add('AP-1', 2);
              assert.throws(() => c.add('AP-1'), RangeError);
            });
        ''',
        tests=fmt('''
            test('perLine limit', () => {
              const c = mk({ limits: { perLine: __PL__ } });
              c.add('AP-1', __PL__ - 1);
              c.add('AP-1');
              assert.throws(() => c.add('AP-1'), RangeError);
              assert.throws(() => c.add('EG-6', __PL__ + 1), RangeError);
              assert.equal(c.lines()[0].qty, __PL__);
              assert.equal(c.lines().length, 1);
              c.remove('AP-1', 1);
              c.add('AP-1');
              c.add('EG-6', __PL__);
              assert.equal(c.subtotal(), 450 * __PL__ + 360 * __PL__);
            });

            test('lines limit', () => {
              const skus = ['AP-1', 'BR-1', 'CH-2', 'EG-6', 'HN-1'];
              const c = mk({ limits: { lines: __ML__ } });
              for (const s of skus.slice(0, __ML__)) c.add(s);
              assert.throws(() => c.add(skus[__ML__]), RangeError);
              c.add(skus[0], 40);
              assert.equal(c.lines().length, __ML__);
              c.remove(skus[1]);
              c.add(skus[__ML__]);
              assert.equal(c.lines().length, __ML__);
            });

            test('limits validation', () => {
              for (const bad of [{ perLine: 0 }, { lines: -2 }, { perLine: 1.5 }, { lines: '3' }]) assert.throws(() => mk({ limits: bad }), TypeError);
              const c = mk({ limits: {} });
              c.add('AP-1', 500);
              assert.equal(c.lines()[0].qty, 500);
            });
        ''', PL=per_line, ML=max_lines),
    ))
    S.append(Slice(
        id="plugins", title="Cart plugins", d=4,
        pitch=("The stall's loyalty app and the allergy-warning screen both need to hook into the cart without patching it.",
               "Partners want to extend checkout behaviour (veto items, react to adds, adjust the total) from their own code."),
        reqs=("`cart.use(plugin)` registers a plugin, a plain object with optional methods `beforeAdd(sku, qty)`, `afterAdd(sku, qty)` and `adjustTotal(amount, cart)`; anything that is not an object is a `TypeError`. Plugins are consulted in registration order and their methods are called as methods of the plugin object.",
              "`add` calls every `beforeAdd` after the existing checks have passed (argument validation and any limits), with the quantity to add (default 1). A `beforeAdd` that returns exactly `false` vetoes the add: nothing changes, later plugins are not asked, and `add` returns `false`. After a successful add every `afterAdd` is called with the same arguments (the line is already updated) and `add` returns `true`.",
              "`total()` passes its amount through every `adjustTotal(amount, cart)` after everything else that contributes to it (discounts, tax); each must return a non-negative integer, otherwise `total()` throws a `RangeError`."),
        code={
            "src/cart.js::init": "this._plugins = [];",
            "src/cart.js::add_checks": '''
                for (const p of this._plugins) {
                  if (typeof p.beforeAdd === 'function' && p.beforeAdd(sku, qty) === false) return false;
                }
            ''',
            "src/cart.js::on_add": '''
                for (const p of this._plugins) {
                  if (typeof p.afterAdd === 'function') p.afterAdd(sku, qty);
                }
            ''',
            "src/cart.js::add_return": "return true;",
            "src/cart.js::total_steps": '''
                for (const p of this._plugins) {
                  if (typeof p.adjustTotal === 'function') {
                    amount = p.adjustTotal(amount, this);
                    if (!Number.isInteger(amount) || amount < 0) throw new RangeError('adjustTotal must return a non-negative integer');
                  }
                }
            ''',
            "src/cart.js::methods": '''
                use(plugin) {
                  if (plugin === null || typeof plugin !== 'object') throw new TypeError('plugin must be an object');
                  this._plugins.push(plugin);
                  @@slot plugin_added
                }
            ''',
        },
        readme=dd('''
            ## Plugins

            `cart.use(plugin)` with optional `beforeAdd(sku, qty)` (return `false` to veto; `add` then returns `false`),
            `afterAdd(sku, qty)` and `adjustTotal(amount, cart)` (non-negative integer). Plugins run in registration order;
            `add` returns `true` when it added something.
        '''),
        vtests='''
            test('plugin can veto', () => {
              const c = mk();
              c.use({ beforeAdd: (sku) => sku !== 'HN-1' });
              assert.equal(c.add('HN-1'), false);
              assert.equal(c.add('AP-1'), true);
              assert.deepEqual(c.lines().map((l) => l.sku), ['AP-1']);
            });
        ''',
        tests='''
            test('plugin hooks run in order with the right arguments', () => {
              const c = mk();
              const log = [];
              c.use({ tag: 'a', beforeAdd(sku, qty) { log.push(`${this.tag}:before:${sku}:${qty}`); }, afterAdd(sku, qty) { log.push(`${this.tag}:after:${sku}:${qty}:${c.lines().length}`); } });
              c.use({ tag: 'b', beforeAdd(sku, qty) { log.push(`${this.tag}:before:${sku}:${qty}`); return true; } });
              assert.equal(c.add('AP-1'), true);
              assert.deepEqual(log, ['a:before:AP-1:1', 'b:before:AP-1:1', 'a:after:AP-1:1:1']);
              log.length = 0;
              c.add('EG-6', 3);
              assert.deepEqual(log, ['a:before:EG-6:3', 'b:before:EG-6:3', 'a:after:EG-6:3:2']);
            });

            test('veto stops everything', () => {
              const c = mk();
              const log = [];
              c.use({ beforeAdd(sku) { log.push('first'); return sku !== 'CH-2'; }, afterAdd() { log.push('after'); } });
              c.use({ beforeAdd() { log.push('second'); } });
              assert.equal(c.add('CH-2'), false);
              assert.deepEqual(log, ['first']);
              assert.deepEqual(c.lines(), []);
              assert.equal(c.total(), 0);
              assert.throws(() => c.add('NOPE'), /unknown sku/);
              assert.throws(() => c.add('AP-1', 0), RangeError);
              assert.deepEqual(log, ['first']);
            });

            test('adjustTotal chain and validation', () => {
              const c = mk();
              c.add('AP-1', 2);
              c.use({ adjustTotal: (amount) => amount - 100 });
              c.use({ adjustTotal: (amount, cart) => amount + cart.lines().length });
              assert.equal(c.total(), 801);
              const bad = mk();
              bad.add('AP-1');
              bad.use({ adjustTotal: () => -1 });
              assert.throws(() => bad.total(), RangeError);
              const frac = mk();
              frac.use({ adjustTotal: () => 1.5 });
              assert.throws(() => frac.total(), RangeError);
              for (const p of [null, 5, 'x', undefined]) assert.throws(() => mk().use(p), TypeError);
              const empty = mk();
              empty.use({});
              empty.add('BR-1');
              assert.equal(empty.total(), 620);
            });
        ''',
        cross={
            "promo-codes": {"tests": '''
                test('adjustTotal sees the discounted amount', () => {
                  const c = mk({ codes: { HALF: { percent: 50 } } });
                  const seen = [];
                  c.use({ adjustTotal(amount) { seen.push(amount); return amount + 5; } });
                  c.add('HN-1', 2);
                  c.applyCode('half');
                  assert.equal(c.total(), 1105);
                  assert.deepEqual(seen, [1100]);
                });
            '''},
            "tax": {"tests": '''
                test('adjustTotal sees the taxed amount', () => {
                  const c = mk({ taxBp: 1000 });
                  c.use({ adjustTotal: (amount) => amount * 2 });
                  c.add('HN-1', 1);
                  assert.equal(c.total(), 2420);
                });
            '''},
            "limits": {"tests": '''
                test('limits are checked before beforeAdd', () => {
                  const c = mk({ limits: { perLine: 1 } });
                  const seen = [];
                  c.use({ beforeAdd(sku) { seen.push(sku); } });
                  assert.equal(c.add('AP-1'), true);
                  assert.throws(() => c.add('AP-1'), RangeError);
                  assert.deepEqual(seen, ['AP-1']);
                });
            '''},
        },
    ))

    S.append(Slice(
        id="cache", title="Cached totals", d=3,
        pitch=("The customer display recalculates the whole total on every redraw and the old tablet struggles.",
               "`total()` is called many times between changes; it should not redo the arithmetic each time."),
        reqs=("`cart.total()` remembers its result and returns it again until the cart changes. The remembered value is dropped by every successful `add` and `remove`; calls that throw leave it alone.",
              "`cart.computations` is a read-only count of how many times `total()` really computed the amount (0 for a new cart; a call answered from the memory does not count). `subtotal()` and `lines()` are not cached."),
        code={
            "src/cart.js::init": "this._cache = null;\nthis._computations = 0;",
            "src/cart.js::total_enter": "if (this._cache !== null) return this._cache;",
            "src/cart.js::total_leave": "this._cache = amount;\nthis._computations += 1;",
            "src/cart.js::on_add": "this._cache = null;",
            "src/cart.js::on_remove": "this._cache = null;",
            "src/cart.js::methods": '''
                get computations() {
                  return this._computations;
                }
            ''',
        },
        readme=dd('''
            ## Cached totals

            `total()` is remembered until the cart changes (successful `add`/`remove`). `cart.computations` counts the real
            computations (cache hits do not count).
        '''),
        vtests='''
            test('total is cached', () => {
              const c = mk();
              c.add('AP-1');
              c.total();
              c.total();
              assert.equal(c.computations, 1);
            });
        ''',
        tests='''
            test('total is cached until the cart changes', () => {
              const c = mk();
              assert.equal(c.computations, 0);
              c.add('AP-1', 2);
              assert.equal(c.total(), 900);
              assert.equal(c.total(), 900);
              assert.equal(c.computations, 1);
              c.add('EG-6');
              assert.equal(c.total(), 1260);
              assert.equal(c.computations, 2);
              assert.throws(() => c.add('NOPE'));
              assert.throws(() => c.add('AP-1', 0));
              assert.throws(() => c.remove('AP-1', 9));
              assert.throws(() => c.remove('BR-1'));
              assert.equal(c.total(), 1260);
              assert.equal(c.computations, 2);
              c.remove('EG-6');
              assert.equal(c.total(), 900);
              assert.equal(c.computations, 3);
              c.subtotal();
              c.lines();
              assert.equal(c.computations, 3);
            });

            test('computations is read-only and per cart', () => {
              const a = mk();
              const b = mk();
              a.add('AP-1');
              a.total();
              assert.equal(b.computations, 0);
              assert.throws(() => { 'use strict'; a.computations = 5; }, TypeError);
              assert.equal(a.computations, 1);
            });
        ''',
        cross={
            "promo-codes": {
                "reqs": ("`applyCode` and `clearCode` also drop the remembered total (a failed `applyCode` does not).",),
                "code": {"src/cart.js::code_changed": "this._cache = null;"},
                "tests": '''
                    test('cached total follows code changes', () => {
                      const c = mk({ codes: { HALF: { percent: 50 } } });
                      c.add('HN-1', 2);
                      assert.equal(c.total(), 2200);
                      c.applyCode('HALF');
                      assert.equal(c.total(), 1100);
                      assert.equal(c.total(), 1100);
                      assert.equal(c.computations, 2);
                      assert.throws(() => c.applyCode('NOPE'));
                      c.total();
                      assert.equal(c.computations, 2);
                      c.clearCode();
                      assert.equal(c.total(), 2200);
                      assert.equal(c.computations, 3);
                    });
                '''},
            "plugins": {
                "reqs": ("`use` also drops the remembered total; a vetoed `add` does not.",),
                "code": {"src/cart.js::plugin_added": "this._cache = null;"},
                "tests": '''
                    test('cached total follows plugin registration', () => {
                      const c = mk();
                      c.add('AP-1');
                      assert.equal(c.total(), 450);
                      c.use({ adjustTotal: (a) => a + 1 });
                      assert.equal(c.total(), 451);
                      assert.equal(c.total(), 451);
                      assert.equal(c.computations, 2);
                      c.use({ beforeAdd: () => false });
                      c.total();
                      assert.equal(c.computations, 3);
                      assert.equal(c.add('BR-1'), false);
                      c.total();
                      assert.equal(c.computations, 3);
                    });
                '''},
        },
    ))

    S.append(Slice(
        id="receipt", title="Text receipt", d=2,
        pitch=("Customers ask for a paper slip and the little thermal printer takes plain text.",
               "The stall wants a printable receipt of the cart."),
        reqs=(f"`cart.receipt(width = {width})` returns the receipt as text. `width` must be an integer of at least 20, otherwise `RangeError`.",
              "A row is `LEFT RIGHT` where `RIGHT` is an amount written with the cart's money format and `LEFT` is padded with spaces on the right, or cut off, so that the row is exactly `width` characters, always with one space before `RIGHT`. Every row ends with a newline.",
              "The receipt has one row per line of the cart in `lines()` order (`LEFT` is `NAME xQTY`, `RIGHT` the line amount), then a row of `width` dashes, then the row `TOTAL` with `total()`. An empty cart gives only the dash row and the `TOTAL` row."),
        code={
            "src/cart.js::methods": fmt('''
                receipt(width = __W__) {
                  if (!Number.isInteger(width) || width < 20) throw new RangeError('width must be an integer of at least 20');
                  const row = (left, right) => {
                    const room = width - right.length - 1;
                    return `${left.slice(0, room).padEnd(room)} ${right}\\n`;
                  };
                  let out = '';
                  for (const l of this.lines()) out += row(`${l.name} x${l.qty}`, this._money(l.amount));
                  @@slot receipt_extra
                  out += `${'-'.repeat(width)}\\n`;
                  out += row('TOTAL', this._money(this.total()));
                  return out;
                }
            ''', W=width),
        },
        readme=fmt(dd('''
            ## Receipt

            `cart.receipt(width = __W__)`: one `NAME xQTY ... AMOUNT` row per line (exactly `width` characters, amount right-aligned),
            a row of dashes, then `TOTAL`. `width` is an integer of at least 20.
        '''), W=width),
        vtests='''
            test('receipt has a total row', () => {
              const c = mk();
              c.add('AP-1');
              assert.ok(c.receipt().endsWith('$4.50\\n'));
            });
        ''',
        tests=fmt('''
            const rrow = (left, right, w) => `${left.slice(0, w - right.length - 1).padEnd(w - right.length - 1)} ${right}\\n`;

            test('receipt layout', () => {
              const c = mk();
              c.add('EG-6', 2);
              c.add('AP-1');
              const w = __W__;
              assert.equal(c.receipt(), rrow('Apples 1kg x1', '$4.50', w) + rrow('Eggs (6) x2', '$7.20', w) + '-'.repeat(w) + '\\n' + rrow('TOTAL', '$11.70', w));
              assert.equal(c.receipt(24), rrow('Apples 1kg x1', '$4.50', 24) + rrow('Eggs (6) x2', '$7.20', 24) + '-'.repeat(24) + '\\n' + rrow('TOTAL', '$11.70', 24));
              for (const line of c.receipt(40).split('\\n').slice(0, 2)) assert.equal(line.length, 40);
            });

            test('receipt truncates long names and handles empty carts', () => {
              const cat = { LONG: { name: 'Extra long name of a very special preserve', price: 123456 } };
              const c = new Cart(cat);
              c.add('LONG');
              const lines = c.receipt(24).split('\\n');
              assert.equal(`${lines[0]}\n`, rrow('Extra long name of a very special preserve x1', '$1234.56', 24));
              assert.equal(lines[0].length, 24);
              assert.ok(lines[0].endsWith(' $1234.56'));
              assert.equal(new Cart(cat).receipt(20), '-'.repeat(20) + '\\n' + rrow('TOTAL', '$0.00', 20));
              for (const bad of [19, 25.5, '30']) assert.throws(() => c.receipt(bad), RangeError);
            });
        ''', W=width),
        cross={
            "promo-codes": {
                "reqs": ("When the discount is greater than 0 the receipt has, after the line rows, a row `Discount (CODE)` with the discount written as a negative amount (for example `-$4.50`).",),
                "code": {"src/cart.js::receipt_extra": "if (this.discount() > 0) out += row(`Discount (${this.code})`, this._money(-this.discount()));"},
                "tests": '''
                    test('receipt shows the discount row', () => {
                      const c = mk({ codes: { HALF: { percent: 50 } } });
                      c.add('AP-1', 2);
                      assert.ok(!c.receipt().includes('Discount'));
                      c.applyCode('half');
                      const lines = c.receipt(30).split('\\n');
                      assert.equal(`${lines[1]}\n`, rrow('Discount (HALF)', '-$4.50', 30));
                      assert.equal(lines[2], '-'.repeat(30));
                      assert.equal(`${lines[3]}\n`, rrow('TOTAL', '$4.50', 30));
                    });
                '''},
            "tax": {
                "reqs": ("When the tax is greater than 0 the receipt has a row `Tax` with the tax amount, after the discount row (if any) and before the dashes.",),
                "code": {"src/cart.js::receipt_extra": "if (this.tax() > 0) out += row('Tax', this._money(this.tax()));"},
                "tests": '''
                    test('receipt shows the tax row', () => {
                      const c = mk({ taxBp: 1000 });
                      c.add('HN-1');
                      const lines = c.receipt(30).split('\\n');
                      assert.equal(`${lines[1]}\n`, rrow('Tax', '$1.10', 30));
                      assert.equal(lines[2], '-'.repeat(30));
                      assert.equal(`${lines[3]}\n`, rrow('TOTAL', '$12.10', 30));
                    });
                '''},
        },
    ))

    S.append(Slice(
        id="currency", title="Currencies", d=2,
        pitch=("The border-market stalls take payments in several currencies.",
               "Not every stall prices in dollars."),
        reqs=("`money(cents, currency = 'USD')` formats for a currency code and throws a `RangeError` for an unknown one. Supported: `USD` (`$12.50`), " + ", ".join(f"`{c[0]}` (`{c[2]}`)" for c in curs) + ". The number always has two decimals (the separator shown in the examples) and no thousands separator; a negative amount starts with `-` before everything else (`-£1.00`).",
              "The `Cart` option `currency` (default `'USD'`) selects the currency the cart reports in: `cart.currency`, and the `money` formatting used by the cart's own text output. An unknown currency makes the constructor throw a `RangeError`."),
        code={
            "src/format.js::money_fn": "const FORMATS = {\n  USD: { pattern: '$' + '{}', dec: '.' },\n" + "".join(f"  {c[0]}: {{ pattern: {c[1]!r}, dec: {c[3]!r} }},\n" for c in curs) + '''};

function money(cents, currency = 'USD') {
  const f = FORMATS[currency];
  if (!f) throw new RangeError(`unknown currency: ${currency}`);
  const abs = Math.abs(cents);
  const num = `${Math.floor(abs / 100)}${f.dec}${String(abs % 100).padStart(2, '0')}`;
  return (cents < 0 ? '-' : '') + f.pattern.replace('{}', num);
}''',
            "src/cart.js::init": "this.currency = options.currency === undefined ? 'USD' : options.currency;\nmoney(0, this.currency);",
            "src/cart.js::money_call": "return money(cents, this.currency);",
        },
        readme=dd('''
            ## Currencies

            `money(cents, currency = 'USD')` formats for ''' + ", ".join(f"`{c[0]}`" for c in curs) + ''' or `USD` (unknown codes throw a
            `RangeError`). `new Cart(catalog, { currency })` sets `cart.currency` and the format used in the cart's text output.
        '''),
        vtests='''
            test('usd stays the default', () => {
              assert.equal(money(1250, 'USD'), '$12.50');
            });
        ''',
        tests=fmt('''
            test('money per currency', () => {
              assert.equal(money(1250), '$12.50');
              assert.equal(money(1250, 'USD'), '$12.50');
              assert.equal(money(5, 'USD'), '$0.05');
              for (const [code, expected, neg] of __CASES__) {
                assert.equal(money(1250, code), expected);
                assert.equal(money(-100, code), neg);
              }
              assert.equal(money(123456, __FIRST__), __FIRSTBIG__);
              assert.throws(() => money(100, 'XXX'), RangeError);
            });

            test('cart currency option', () => {
              assert.equal(mk().currency, 'USD');
              const c = mk({ currency: __FIRST__ });
              assert.equal(c.currency, __FIRST__);
              assert.throws(() => mk({ currency: 'XXX' }), RangeError);
            });
        ''', CASES=json.dumps([[c[0], c[2], "-" + c[4]] for c in curs], ensure_ascii=False), FIRST=json.dumps(curs[0][0]), FIRSTBIG=json.dumps(curs[0][5], ensure_ascii=False)),
        cross={
            "receipt": {"tests": fmt('''
                test('receipt uses the cart currency', () => {
                  const c = mk({ currency: __CUR__ });
                  c.add('AP-1');
                  const lines = c.receipt(30).split('\\n');
                  assert.ok(lines[0].endsWith(' ' + money(450, __CUR__)));
                  assert.equal(lines[0].length, 30);
                  assert.ok(lines[2].endsWith(' ' + money(450, __CUR__)));
                });
            ''', CUR=json.dumps(curs[0][0]))},
        },
    ))

    return S


APP = App(
    name="stallcart", lang="javascript", title="the market checkout library", role="a stallholder at the market", key="STALL",
    base={
        "README.md": README + "\n@@blocks features\n",
        "package.json": '{\n  "name": "stallcart",\n  "version": "1.0.0",\n  "private": true,\n  "main": "index.js",\n  "scripts": {\n    "test": "node --test test/*.test.js"\n  }\n}\n',
        "index.js": INDEX,
        "src/cart.js": CART,
        "src/format.js": FORMAT,
        ".gitignore": "node_modules/\n",
    },
    visible={"test/basic.test.js": VISIBLE},
    hidden={"test/features.test.js": HIDDEN},
    verify="node --test test/*.test.js",
)

register_app("feature-js-stallcart", APP, make_slices, n=16, summary="market stall checkout: bulk prices, codes, tax, limits, plugins, cache, receipt, currency")
