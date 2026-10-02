"""Scenarios (reproduction scripts) for the javascript slot modules of the review bank."""
from __future__ import annotations

from fx import dd

CART_SCENARIO = dd('''
    'use strict';
    // Replays a typical afternoon of the shop back end and prints what the helpers return.
    const cart = require('./src/cart.js');

    function show(label, fn) {
      try {
        console.log(`${label}: ${JSON.stringify(fn())}`);
      } catch (e) {
        console.log(`${label}: threw ${e.name}: ${e.message}`);
      }
    }

    const items = [
      { sku: 'TEA', name: 'Loose <leaf> tea', pence: 450, qty: 3, discountPct: 10 },
      { sku: 'MUG', name: 'Enamel mug', pence: 1299, qty: 1 },
      { sku: 'SPN', name: 'Spoon "set" & case', pence: 275, qty: 6, discountPct: 15 },
    ];

    for (const q of ['7', ' 12 ', '99', '100', '0', 'abc', '0x10', '1e1']) {
      show(`parseQty(${JSON.stringify(q)})`, () => cart.parseQty(q));
    }

    for (const it of items) {
      show(`lineTotal(${it.sku})`, () => cart.lineTotal(it));
    }
    show('lineTotal(CUP)', () => cart.lineTotal({ sku: 'CUP', pence: 333, qty: 1, discountPct: 10 }));

    for (const code of [undefined, 'SPRING10', 'WELCOME5', 'FREESHIP', 'NOPE']) {
      show(`cartTotal(${code})`, () => cart.cartTotal(items, code));
    }
    show('cartTotal(small cart, WELCOME5)', () => cart.cartTotal([{ sku: 'PEN', pence: 300, qty: 1 }], 'WELCOME5'));

    const a = [
      { sku: 'TEA', name: 'Loose tea', pence: 450, qty: 3 },
      { sku: 'MUG', name: 'Enamel mug', pence: 1299, qty: 1 },
    ];
    const b = [
      { sku: 'TEA', name: 'Loose tea', pence: 450, qty: 2 },
      { sku: 'SPN', name: 'Spoon', pence: 275, qty: 4 },
    ];
    show('mergeCarts(a, b)', () => cart.mergeCarts(a, b).map((i) => `${i.sku}x${i.qty}`));
    show('cart a afterwards', () => a.map((i) => `${i.sku}x${i.qty}`));

    show('sortByPrice(items)', () => cart.sortByPrice(items).map((i) => i.sku));
    show('items afterwards', () => items.map((i) => i.sku));

    for (const [total, country] of [[4999, 'GB'], [5000, 'GB'], [3000, 'IE'], [3000, 'FR'], [3000, 'US'], [100, 'GB']]) {
      show(`shippingFor(${total}, ${country})`, () => cart.shippingFor(total, country));
    }

    show('escapeHtml', () => cart.escapeHtml(`Tom & Jerry's <b class="x">`));
    show('renderReceipt', () => cart.renderReceipt(items, '<script>alert(1)</script>'));

    async function main() {
      const log = [];
      const warehouse = {
        reserve: async (sku, qty) => {
          log.push(`reserve ${sku} x${qty}`);
          if (sku === 'BAD') throw new Error(`out of stock: ${sku}`);
          await new Promise((resolve) => setTimeout(resolve, sku === 'MUG' ? 6 : 1));
          return `R-${sku}-${qty}`;
        },
      };
      try {
        console.log('reserveAll(items):', JSON.stringify(await cart.reserveAll(items, warehouse)));
      } catch (e) {
        console.log('reserveAll(items) rejected:', e.message);
      }
      try {
        console.log('reserveAll(with BAD):', JSON.stringify(await cart.reserveAll([...items, { sku: 'BAD', qty: 1 }], warehouse)));
      } catch (e) {
        console.log('reserveAll(with BAD) rejected:', e.message);
      }
      console.log('warehouse calls:', JSON.stringify(log));
    }

    main().then(() => console.log('done'));
''')

TIMESHEET_SCENARIO = dd('''
    'use strict';
    // Month-end run for the workshop: the kiosk that prints the sheets is set to New Zealand time.
    process.env.TZ = 'Pacific/Auckland';
    const ts = require('./src/timesheet.js');

    function show(label, fn) {
      try {
        console.log(`${label}: ${JSON.stringify(fn())}`);
      } catch (e) {
        console.log(`${label}: threw ${e.name}: ${e.message}`);
      }
    }

    for (const t of ['2025-03-14', '2024-02-29', '2025-02-30', '2025-13-01', '2025-3-4', 'soon']) {
      show(`parseDay(${t})`, () => ts.toIso(ts.parseDay(t)));
    }

    for (const t of ['2025-03-14', '2025-03-15', '2025-03-16', '2025-03-17']) {
      show(`isWeekend(${t})`, () => ts.isWeekend(ts.parseDay(t)));
    }

    const day = (t) => ts.parseDay(t);
    show('workingDays(Mon..Sun)', () => ts.workingDays(day('2025-03-10'), day('2025-03-16')));
    show('workingDays(Mon..Fri)', () => ts.workingDays(day('2025-03-10'), day('2025-03-14')));
    show('workingDays(one Tuesday)', () => ts.workingDays(day('2025-03-11'), day('2025-03-11')));
    show('workingDays(backwards)', () => ts.workingDays(day('2025-03-14'), day('2025-03-10')));

    for (const t of ['2025-03-12', '2025-03-16', '2025-03-10']) {
      show(`weekStart(${t})`, () => ts.toIso(ts.weekStart(day(t))));
    }

    for (const h of [1.1, 1.125, 1.37, 2.6, 7.5]) {
      show(`roundHours(${h})`, () => ts.roundHours(h));
    }

    const entries = [
      { day: '2025-03-12', hours: 7.5 },
      { day: '2025-03-10', hours: 8 },
      { day: '2025-03-19', hours: 3 },
      { day: '2025-03-20', hours: 2.5 },
      { day: '2025-03-04', hours: 9 },
    ];
    show('summarise', () => ts.summarise(entries));
''')

SCENARIOS = {"js-linden-cart": CART_SCENARIO, "js-timesheet": TIMESHEET_SCENARIO}
