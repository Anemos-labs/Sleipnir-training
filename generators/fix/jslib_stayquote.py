"""Guesthouse stay pricing and availability (javascript): bugs injected into a date-range pricing library."""
from fx import Lib, dd
from generators.fix._lang2 import JS_VERIFY, PACKAGE_JSON, register_libs

README = dd(r'''
    # stayquote

    Prices stays at a small guesthouse and answers availability questions. CommonJS:
    `const { quote } = require('./src/quote')`, `const { nightsBetween, weekday, parseDate } = require('./src/dates')`,
    `const { freeWindows, overlaps } = require('./src/calendar')`.

    Dates are ISO strings `YYYY-MM-DD` (exactly that shape, and a real calendar date). A guest sleeps the *nights*
    from `checkIn` (included) to `checkOut` (excluded). Money is an integer number of cents.

    ## `src/dates.js`

    * `parseDate(text)` returns the number of whole days since 1970-01-01 (UTC) of that date. A malformed or impossible
      date (`'2025-02-30'`, `'2025-2-3'`, `'20250203'`) is a `TypeError`.
    * `weekday(text)` returns `0` for Monday up to `6` for Sunday.
    * `nightsBetween(checkIn, checkOut)` returns the number of nights. `checkOut` must be after `checkIn`, otherwise
      `RangeError`.
    * `formatDate(days)` is the inverse of `parseDate`.

    ## `src/calendar.js`

    A *booking* is `{ from, to }` (dates, `to` excluded), like a stay.

    * `overlaps(a, b)` is true when two bookings share at least one night. Bookings that merely touch (`a.to === b.from`)
      do not overlap.
    * `freeWindows(from, to, bookings)` returns the free `[from, to)` stretches inside the window as an array of
      `{ from, to }`, in date order, as date strings. Bookings may be unsorted, may overlap each other and may stick out
      of the window. Free windows are never empty and are separated by at least one booked night.

    ## `src/quote.js`

    `quote(checkIn, checkOut, rates)` returns
    `{ nights, perNight, subtotal, discount, cleaning, tax, total }` where `perNight` is the array of nightly prices.

    `rates` has: `base` (cents per night), `seasons` (array, may be empty), `weekendPct`, `longStay`, `cleaning`,
    `cleaningWaivedFrom` and `taxPct`.

    * **Season.** A season is `{ name, from: 'MM-DD', to: 'MM-DD', rate, minNights }`; it covers every night whose month
      and day lie between `from` and `to` inclusive. If `from` is after `to` the season wraps over New Year
      (`'12-20'` to `'01-05'`). The first matching season in the array wins; without a match the night costs `base`.
      A night's price is the season's `rate`.
    * **Weekend.** Friday and Saturday nights (the night that *starts* on that day) cost `weekendPct` percent more:
      `price + round(price * weekendPct / 100)`, rounded half up (`.5` goes up), per night.
    * **Minimum stay.** The season of the *check-in night* may carry `minNights`; a stay shorter than that is a
      `RangeError`. Seasons without `minNights` (and the base rate) have no minimum.
    * `subtotal` is the sum of the nightly prices.
    * **Long stay.** `longStay` is an array of `{ nights, pct }` tiers. The tier with the largest `nights` that is
      `<=` the stay applies: `discount = round(subtotal * pct / 100)` (half up). No tier, no discount (`0`).
    * **Cleaning.** `cleaning` cents are charged once per stay, except when the stay has at least `cleaningWaivedFrom`
      nights (then `0`). If `cleaningWaivedFrom` is missing the fee is never waived.
    * **Tax.** `tax = round((subtotal - discount + cleaning) * taxPct / 100)`, half up. `total` is
      `subtotal - discount + cleaning + tax`.
''')

DATES = dd(r'''
    'use strict';

    const SHAPE = /^(\d{4})-(\d{2})-(\d{2})$/;
    const DAY_MS = 86400000;

    function parseDate(text) {
      const m = typeof text === 'string' ? SHAPE.exec(text) : null;
      if (!m) throw new TypeError(`not a date: ${String(text)}`);
      const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
      const ms = Date.UTC(y, mo - 1, d);
      const back = new Date(ms);
      if (back.getUTCFullYear() !== y || back.getUTCMonth() !== mo - 1 || back.getUTCDate() !== d) {
        throw new TypeError(`not a calendar date: ${text}`);
      }
      return Math.round(ms / DAY_MS);
    }

    function formatDate(days) {
      return new Date(days * DAY_MS).toISOString().slice(0, 10);
    }

    function weekday(text) {
      const days = parseDate(text);
      return (((days + 3) % 7) + 7) % 7;
    }

    function nightsBetween(checkIn, checkOut) {
      const n = parseDate(checkOut) - parseDate(checkIn);
      if (n <= 0) throw new RangeError('check-out must be after check-in');
      return n;
    }

    module.exports = { parseDate, formatDate, weekday, nightsBetween };
''')

CALENDAR = dd(r'''
    'use strict';

    const { parseDate, formatDate } = require('./dates');

    function overlaps(a, b) {
      return parseDate(a.from) < parseDate(b.to) && parseDate(b.from) < parseDate(a.to);
    }

    function freeWindows(from, to, bookings) {
      const lo = parseDate(from);
      const hi = parseDate(to);
      const busy = bookings
        .map((b) => [parseDate(b.from), parseDate(b.to)])
        .filter(([s, e]) => e > lo && s < hi)
        .sort((x, y) => x[0] - y[0]);
      const out = [];
      let cursor = lo;
      for (const [s, e] of busy) {
        if (s > cursor) out.push({ from: formatDate(cursor), to: formatDate(s) });
        if (e > cursor) cursor = e;
      }
      if (cursor < hi) out.push({ from: formatDate(cursor), to: formatDate(hi) });
      return out;
    }

    module.exports = { overlaps, freeWindows };
''')

QUOTE = dd(r'''
    'use strict';

    const { parseDate, formatDate, weekday, nightsBetween } = require('./dates');

    function roundHalfUp(numerator, denominator) {
      return Math.floor((2 * numerator + denominator) / (2 * denominator));
    }

    function inSeason(season, monthDay) {
      if (season.from <= season.to) return monthDay >= season.from && monthDay <= season.to;
      return monthDay >= season.from || monthDay <= season.to;
    }

    function seasonFor(date, seasons) {
      const monthDay = date.slice(5);
      return seasons.find((s) => inSeason(s, monthDay)) || null;
    }

    function quote(checkIn, checkOut, rates) {
      const nights = nightsBetween(checkIn, checkOut);
      const first = parseDate(checkIn);
      const seasons = rates.seasons || [];

      const opening = seasonFor(checkIn, seasons);
      if (opening && opening.minNights && nights < opening.minNights) {
        throw new RangeError(`minimum stay in ${opening.name} is ${opening.minNights} nights`);
      }

      const perNight = [];
      for (let i = 0; i < nights; i++) {
        const date = formatDate(first + i);
        const season = seasonFor(date, seasons);
        let price = season ? season.rate : rates.base;
        const dow = weekday(date);
        if (dow === 4 || dow === 5) price += roundHalfUp(price * (rates.weekendPct || 0), 100);
        perNight.push(price);
      }
      const subtotal = perNight.reduce((a, b) => a + b, 0);

      let pct = 0;
      let best = 0;
      for (const tier of rates.longStay || []) {
        if (tier.nights <= nights && tier.nights > best) {
          best = tier.nights;
          pct = tier.pct;
        }
      }
      const discount = roundHalfUp(subtotal * pct, 100);

      const waived = rates.cleaningWaivedFrom !== undefined && nights >= rates.cleaningWaivedFrom;
      const cleaning = waived ? 0 : rates.cleaning || 0;

      const tax = roundHalfUp((subtotal - discount + cleaning) * (rates.taxPct || 0), 100);
      return { nights, perNight, subtotal, discount, cleaning, tax, total: subtotal - discount + cleaning + tax };
    }

    module.exports = { quote };
''')

VISIBLE = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { nightsBetween, weekday } = require('../src/dates');
    const { quote } = require('../src/quote');

    test('nights and weekday', () => {
      assert.equal(nightsBetween('2025-03-01', '2025-03-04'), 3);
      assert.equal(weekday('2025-03-03'), 0);
    });

    test('flat quote', () => {
      const q = quote('2025-03-03', '2025-03-05', { base: 10000 });
      assert.deepEqual(q.perNight, [10000, 10000]);
      assert.equal(q.total, 20000);
    });
''')

HIDDEN = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { parseDate, formatDate, weekday, nightsBetween } = require('../src/dates');
    const { overlaps, freeWindows } = require('../src/calendar');
    const { quote } = require('../src/quote');

    test('parseDate counts days since the epoch', () => {
      assert.equal(parseDate('1970-01-01'), 0);
      assert.equal(parseDate('1970-01-02'), 1);
      assert.equal(parseDate('1969-12-31'), -1);
      assert.equal(parseDate('2000-03-01'), 11017);
      assert.equal(parseDate('2024-03-01') - parseDate('2024-02-01'), 29);
      assert.equal(parseDate('2025-03-01') - parseDate('2025-02-01'), 28);
    });

    test('parseDate rejects bad dates', () => {
      for (const bad of ['2025-02-30', '2025-2-3', '20250203', '2025-13-01', '2025-00-10', '2025-04-31', '2023-02-29', '', ' 2025-01-01', '2025-01-01 ', 'x', '2025-01-001']) {
        assert.throws(() => parseDate(bad), TypeError, bad);
      }
      assert.throws(() => parseDate(20250101), TypeError);
      assert.throws(() => parseDate(null), TypeError);
      assert.doesNotThrow(() => parseDate('2024-02-29'));
      assert.doesNotThrow(() => parseDate('2000-02-29'));
      assert.throws(() => parseDate('1900-02-29'), TypeError);
    });

    test('formatDate inverts parseDate', () => {
      for (const d of ['1970-01-01', '1969-12-31', '2024-02-29', '2025-12-31', '2100-01-01', '1999-09-09']) {
        assert.equal(formatDate(parseDate(d)), d);
      }
      assert.equal(formatDate(0), '1970-01-01');
      assert.equal(formatDate(11017), '2000-03-01');
    });

    test('weekday: Monday is 0', () => {
      assert.equal(weekday('2025-03-03'), 0);
      assert.equal(weekday('2025-03-04'), 1);
      assert.equal(weekday('2025-03-05'), 2);
      assert.equal(weekday('2025-03-06'), 3);
      assert.equal(weekday('2025-03-07'), 4);
      assert.equal(weekday('2025-03-08'), 5);
      assert.equal(weekday('2025-03-09'), 6);
      assert.equal(weekday('1970-01-01'), 3);
      assert.equal(weekday('1969-12-31'), 2);
      assert.equal(weekday('1969-12-29'), 0);
      assert.equal(weekday('1960-06-15'), 2);
    });

    test('nightsBetween', () => {
      assert.equal(nightsBetween('2025-03-01', '2025-03-02'), 1);
      assert.equal(nightsBetween('2024-02-27', '2024-03-02'), 4);
      assert.equal(nightsBetween('2024-12-30', '2025-01-02'), 3);
      assert.throws(() => nightsBetween('2025-03-01', '2025-03-01'), RangeError);
      assert.throws(() => nightsBetween('2025-03-02', '2025-03-01'), RangeError);
      assert.throws(() => nightsBetween('2025-03-02', 'nope'), TypeError);
    });

    test('overlaps', () => {
      const b = (from, to) => ({ from, to });
      assert.equal(overlaps(b('2025-05-01', '2025-05-05'), b('2025-05-04', '2025-05-08')), true);
      assert.equal(overlaps(b('2025-05-04', '2025-05-08'), b('2025-05-01', '2025-05-05')), true);
      assert.equal(overlaps(b('2025-05-01', '2025-05-05'), b('2025-05-05', '2025-05-08')), false);
      assert.equal(overlaps(b('2025-05-05', '2025-05-08'), b('2025-05-01', '2025-05-05')), false);
      assert.equal(overlaps(b('2025-05-01', '2025-05-10'), b('2025-05-03', '2025-05-04')), true);
      assert.equal(overlaps(b('2025-05-03', '2025-05-04'), b('2025-05-01', '2025-05-10')), true);
      assert.equal(overlaps(b('2025-05-01', '2025-05-03'), b('2025-05-06', '2025-05-09')), false);
      assert.equal(overlaps(b('2025-05-01', '2025-05-02'), b('2025-05-01', '2025-05-02')), true);
    });

    test('freeWindows: no bookings', () => {
      assert.deepEqual(freeWindows('2025-06-01', '2025-06-10', []), [{ from: '2025-06-01', to: '2025-06-10' }]);
    });

    test('freeWindows: bookings split the window', () => {
      const got = freeWindows('2025-06-01', '2025-06-30', [
        { from: '2025-06-10', to: '2025-06-12' },
        { from: '2025-06-03', to: '2025-06-05' },
      ]);
      assert.deepEqual(got, [
        { from: '2025-06-01', to: '2025-06-03' },
        { from: '2025-06-05', to: '2025-06-10' },
        { from: '2025-06-12', to: '2025-06-30' },
      ]);
    });

    test('freeWindows: touching or overlapping bookings merge', () => {
      const got = freeWindows('2025-06-01', '2025-06-20', [
        { from: '2025-06-05', to: '2025-06-08' },
        { from: '2025-06-08', to: '2025-06-09' },
        { from: '2025-06-07', to: '2025-06-12' },
        { from: '2025-06-09', to: '2025-06-10' },
      ]);
      assert.deepEqual(got, [
        { from: '2025-06-01', to: '2025-06-05' },
        { from: '2025-06-12', to: '2025-06-20' },
      ]);
    });

    test('freeWindows: a long booking swallows later short ones', () => {
      const got = freeWindows('2025-06-01', '2025-06-20', [
        { from: '2025-06-02', to: '2025-06-15' },
        { from: '2025-06-04', to: '2025-06-06' },
      ]);
      assert.deepEqual(got, [
        { from: '2025-06-01', to: '2025-06-02' },
        { from: '2025-06-15', to: '2025-06-20' },
      ]);
    });

    test('freeWindows: bookings outside or sticking out of the window', () => {
      assert.deepEqual(freeWindows('2025-06-10', '2025-06-20', [
        { from: '2025-06-01', to: '2025-06-10' },
        { from: '2025-06-20', to: '2025-06-25' },
      ]), [{ from: '2025-06-10', to: '2025-06-20' }]);
      assert.deepEqual(freeWindows('2025-06-10', '2025-06-20', [
        { from: '2025-06-01', to: '2025-06-12' },
        { from: '2025-06-18', to: '2025-06-30' },
      ]), [{ from: '2025-06-12', to: '2025-06-18' }]);
      assert.deepEqual(freeWindows('2025-06-10', '2025-06-20', [{ from: '2025-06-01', to: '2025-07-01' }]), []);
      assert.deepEqual(freeWindows('2025-06-10', '2025-06-20', [{ from: '2025-06-10', to: '2025-06-20' }]), []);
      assert.deepEqual(freeWindows('2025-06-10', '2025-06-20', [{ from: '2025-06-11', to: '2025-06-12' }]), [
        { from: '2025-06-10', to: '2025-06-11' },
        { from: '2025-06-12', to: '2025-06-20' },
      ]);
    });

    test('freeWindows: empty window', () => {
      assert.deepEqual(freeWindows('2025-06-10', '2025-06-10', []), []);
    });

    test('freeWindows does not reorder the callers array', () => {
      const bookings = [{ from: '2025-06-10', to: '2025-06-12' }, { from: '2025-06-03', to: '2025-06-05' }];
      freeWindows('2025-06-01', '2025-06-30', bookings);
      assert.equal(bookings[0].from, '2025-06-10');
    });

    const RATES = {
      base: 10000,
      seasons: [
        { name: 'winter', from: '12-20', to: '01-05', rate: 15000, minNights: 3 },
        { name: 'summer', from: '07-01', to: '08-31', rate: 12000, minNights: 2 },
        { name: 'fair', from: '09-05', to: '09-07', rate: 20000 },
      ],
      weekendPct: 10,
      longStay: [{ nights: 7, pct: 10 }, { nights: 28, pct: 25 }, { nights: 14, pct: 15 }],
      cleaning: 4000,
      cleaningWaivedFrom: 5,
      taxPct: 8,
    };

    test('quote: base rate, weekdays only', () => {
      const q = quote('2025-03-03', '2025-03-06', { base: 10000 });
      assert.deepEqual(q, { nights: 3, perNight: [10000, 10000, 10000], subtotal: 30000, discount: 0, cleaning: 0, tax: 0, total: 30000 });
    });

    test('quote: only friday and saturday nights carry the weekend surcharge', () => {
      const q = quote('2025-03-06', '2025-03-10', { base: 10000, weekendPct: 10 });
      // Thu Fri Sat Sun
      assert.deepEqual(q.perNight, [10000, 11000, 11000, 10000]);
      assert.equal(q.subtotal, 42000);
    });

    test('quote: weekend surcharge rounds half up per night', () => {
      const q = quote('2025-03-07', '2025-03-09', { base: 10005, weekendPct: 5 });
      // 10005 * 5% = 500.25 -> 500
      assert.deepEqual(q.perNight, [10505, 10505]);
      const r = quote('2025-03-07', '2025-03-08', { base: 9990, weekendPct: 5 });
      // 499.5 -> 500
      assert.deepEqual(r.perNight, [10490]);
      const s = quote('2025-03-07', '2025-03-08', { base: 9989, weekendPct: 5 });
      // 499.45 -> 499
      assert.deepEqual(s.perNight, [10488]);
    });

    test('quote: season rate replaces base, per night', () => {
      const q = quote('2025-06-29', '2025-07-03', { base: 10000, seasons: RATES.seasons });
      assert.deepEqual(q.perNight, [10000, 10000, 12000, 12000]);
    });

    test('quote: season boundaries are inclusive', () => {
      const a = quote('2025-08-30', '2025-09-02', { base: 10000, seasons: RATES.seasons });
      assert.deepEqual(a.perNight, [12000, 12000, 10000]);
      const b = quote('2025-09-04', '2025-09-08', { base: 10000, seasons: RATES.seasons });
      assert.deepEqual(b.perNight, [10000, 20000, 20000, 20000]);
    });

    test('quote: wrapping season covers new year', () => {
      const q = quote('2024-12-18', '2025-01-08', { base: 10000, seasons: RATES.seasons });
      assert.equal(q.nights, 21);
      const expect = [];
      for (let i = 0; i < 21; i++) expect.push(i >= 2 && i <= 18 ? 15000 : 10000);
      assert.deepEqual(q.perNight, expect);
    });

    test('quote: the first matching season wins', () => {
      const seasons = [
        { name: 'a', from: '03-01', to: '03-31', rate: 1000 },
        { name: 'b', from: '03-15', to: '04-15', rate: 2000 },
      ];
      assert.deepEqual(quote('2025-03-30', '2025-04-02', { base: 5, seasons }).perNight, [1000, 1000, 2000]);
    });

    test('quote: minimum stay comes from the check-in night season', () => {
      assert.throws(() => quote('2024-12-24', '2024-12-26', RATES), RangeError);
      assert.doesNotThrow(() => quote('2024-12-24', '2024-12-27', RATES));
      assert.throws(() => quote('2025-07-10', '2025-07-11', RATES), RangeError);
      assert.doesNotThrow(() => quote('2025-07-10', '2025-07-12', RATES));
      // season without a minimum, and a check-in outside every season
      assert.doesNotThrow(() => quote('2025-09-05', '2025-09-06', RATES));
      assert.doesNotThrow(() => quote('2025-10-10', '2025-10-11', RATES));
      // a check-in just before the season is not bound by it
      assert.doesNotThrow(() => quote('2025-06-30', '2025-07-01', RATES));
      // a check-in on the last night of the season is
      assert.throws(() => quote('2025-08-31', '2025-09-01', RATES), RangeError);
    });

    test('quote: long stay tiers pick the largest applicable', () => {
      const flat = { base: 1000, longStay: RATES.longStay };
      assert.equal(quote('2025-03-03', '2025-03-09', flat).discount, 0);
      assert.equal(quote('2025-03-03', '2025-03-10', flat).discount, 700);
      assert.equal(quote('2025-03-03', '2025-03-16', flat).discount, 1300);
      assert.equal(quote('2025-03-03', '2025-03-17', flat).discount, 2100);
      assert.equal(quote('2025-03-03', '2025-03-30', flat).discount, 4050);
      assert.equal(quote('2025-03-03', '2025-03-31', flat).discount, 7000);
      assert.equal(quote('2025-03-03', '2025-04-10', flat).discount, 9500);
    });

    test('quote: discount rounds half up', () => {
      const q = quote('2025-03-03', '2025-03-10', { base: 1005, longStay: [{ nights: 7, pct: 10 }] });
      // 7035 * 10% = 703.5 -> 704
      assert.equal(q.subtotal, 7035);
      assert.equal(q.discount, 704);
      const r = quote('2025-03-03', '2025-03-10', { base: 1004, longStay: [{ nights: 7, pct: 10 }] });
      // 7028 * 10% = 702.8 -> 703
      assert.equal(r.discount, 703);
      const s = quote('2025-03-03', '2025-03-10', { base: 1001, longStay: [{ nights: 7, pct: 10 }] });
      // 7007 * 10% = 700.7 -> 701
      assert.equal(s.discount, 701);
    });

    test('quote: cleaning fee and its waiver', () => {
      const base = { base: 1000, cleaning: 4000, cleaningWaivedFrom: 5 };
      assert.equal(quote('2025-03-03', '2025-03-04', base).cleaning, 4000);
      assert.equal(quote('2025-03-03', '2025-03-07', base).cleaning, 4000);
      assert.equal(quote('2025-03-03', '2025-03-08', base).cleaning, 0);
      assert.equal(quote('2025-03-03', '2025-03-10', base).cleaning, 0);
      assert.equal(quote('2025-03-03', '2025-03-20', { base: 1000, cleaning: 4000 }).cleaning, 4000);
      assert.equal(quote('2025-03-03', '2025-03-04', { base: 1000 }).cleaning, 0);
      assert.equal(quote('2025-03-03', '2025-03-04', { base: 1000, cleaning: 4000, cleaningWaivedFrom: 0 }).cleaning, 0);
    });

    test('quote: tax applies after discount and cleaning, half up', () => {
      const q = quote('2025-03-03', '2025-03-05', { base: 10000, cleaning: 4000, taxPct: 8 });
      assert.equal(q.tax, 1920);
      assert.equal(q.total, 25920);
      const r = quote('2025-03-03', '2025-03-04', { base: 1006, taxPct: 5 });
      // 50.3 -> 50
      assert.equal(r.tax, 50);
      const s = quote('2025-03-03', '2025-03-04', { base: 1010, taxPct: 5 });
      // 50.5 -> 51
      assert.equal(s.tax, 51);
      assert.equal(s.total, 1061);
    });

    test('quote: everything together', () => {
      // 2025-07-04 (Fri) .. 2025-07-14: 10 nights in summer at 12000; Fri 4, Sat 5, Fri 11, Sat 12 carry +10%
      const q = quote('2025-07-04', '2025-07-14', RATES);
      assert.equal(q.nights, 10);
      assert.deepEqual(q.perNight, [13200, 13200, 12000, 12000, 12000, 12000, 12000, 13200, 13200, 12000]);
      assert.equal(q.subtotal, 124800);
      assert.equal(q.discount, 12480);
      assert.equal(q.cleaning, 0);
      assert.equal(q.tax, 8986);
      assert.equal(q.total, 121306);
    });

    test('quote: short stay with cleaning and tax', () => {
      const q = quote('2024-12-31', '2025-01-03', RATES);
      // Tue Wed Thu in winter: 3 * 15000 = 45000; cleaning 4000; tax 8% of 49000 = 3920
      assert.deepEqual(q, { nights: 3, perNight: [15000, 15000, 15000], subtotal: 45000, discount: 0, cleaning: 4000, tax: 3920, total: 52920 });
    });

    test('quote: input errors', () => {
      assert.throws(() => quote('2025-03-05', '2025-03-05', RATES), RangeError);
      assert.throws(() => quote('2025-03-05', '2025-03-01', RATES), RangeError);
      assert.throws(() => quote('soon', '2025-03-01', RATES), TypeError);
    });
''')

LIB = Lib(
    name="stayquote", lang="javascript", title="the stayquote pricing library",
    blurb="The booking site of a small guesthouse uses stayquote to price stays and to find free date windows.",
    files={"package.json": PACKAGE_JSON % "stayquote", "src/dates.js": DATES,
           "src/calendar.js": CALENDAR, "src/quote.js": QUOTE, "README.md": README, ".gitignore": "node_modules/\n"},
    visible_tests={"test/basic.test.js": VISIBLE},
    hidden_tests={"test/full.test.js": HIDDEN},
    mutate=["src/quote.js", "src/calendar.js", "src/dates.js"], difficulty=3, tags=["dates", "pricing", "booking"],
    verify=JS_VERIFY,
    probe_import="const { parseDate, formatDate, weekday, nightsBetween } = require('./src/dates');\nconst { overlaps, freeWindows } = require('./src/calendar');\nconst { quote } = require('./src/quote');",
    probes=[
        "weekday('2025-03-07')",
        "weekday('1969-12-31')",
        "nightsBetween('2024-02-27', '2024-03-02')",
        "parseDate('2000-03-01')",
        "parseDate('2025-02-30')",
        'formatDate(11017)',
        "overlaps({ from: '2025-05-01', to: '2025-05-05' }, { from: '2025-05-05', to: '2025-05-08' })",
        "freeWindows('2025-06-01', '2025-06-30', [{ from: '2025-06-10', to: '2025-06-12' }, { from: '2025-06-03', to: '2025-06-05' }])",
        "freeWindows('2025-06-01', '2025-06-20', [{ from: '2025-06-02', to: '2025-06-15' }, { from: '2025-06-04', to: '2025-06-06' }])",
        "quote('2025-03-06', '2025-03-10', { base: 10000, weekendPct: 10 }).perNight",
        "quote('2025-06-29', '2025-07-03', { base: 10000, seasons: [{ name: 'summer', from: '07-01', to: '08-31', rate: 12000 }] }).perNight",
        "quote('2024-12-24', '2024-12-26', { base: 10000, seasons: [{ name: 'winter', from: '12-20', to: '01-05', rate: 15000, minNights: 3 }], weekendPct: 10, cleaning: 4000, cleaningWaivedFrom: 5, taxPct: 8 })",
        "quote('2025-03-03', '2025-03-17', { base: 1000, longStay: [{ nights: 7, pct: 10 }, { nights: 28, pct: 25 }, { nights: 14, pct: 15 }] }).discount",
        "quote('2025-03-03', '2025-03-10', { base: 1005, longStay: [{ nights: 7, pct: 10 }] }).discount",
        "quote('2025-03-03', '2025-03-08', { base: 1000, cleaning: 4000, cleaningWaivedFrom: 5 }).cleaning",
        "quote('2025-03-03', '2025-03-04', { base: 1010, taxPct: 5 })",
        "quote('2024-12-31', '2025-01-03', { base: 10000, seasons: [{ name: 'winter', from: '12-20', to: '01-05', rate: 15000, minNights: 3 }], weekendPct: 10, cleaning: 4000, cleaningWaivedFrom: 5, taxPct: 8 })",
    ],
)

register_libs([LIB], n=8)
