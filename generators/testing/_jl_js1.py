"""JavaScript libraries for the testing families: recipe scaling, chore rota, cron-like schedules."""
from __future__ import annotations

from fx import dd

from ._engine import TLib

WHERE_JS = ("Put your tests in `test/` as `*.test.js` files (CommonJS, `node:test` and `node:assert` only; there is nothing to install). "
            "They are run with `node --test` from the repository root.")
PKG = '{\n  "name": "%s",\n  "version": "1.0.0",\n  "private": true\n}\n'

# ---------------------------------------------------------------------------------------------------------------------
# recipe scaler
# ---------------------------------------------------------------------------------------------------------------------

RECIPE_README = dd('''
    # recipe-scaler

    Scaling helpers for the Quillon Street community kitchen's recipe cards.

    ## `parseAmount(text) -> number`
    Reads `"2"`, `"2.5"`, `"3/4"` and mixed numbers like `"1 1/2"` (a whole number, one space, a fraction). Surrounding blanks are
    ignored. A zero denominator, a negative number, an empty string or anything else throws a `RangeError`.

    ## `formatAmount(x) -> string`
    Rounds `x` to the nearest eighth (halves round up) and writes a mixed number with a reduced fraction: `1.5` is `"1 1/2"`, `0.25` is
    `"1/4"`, `2` is `"2"`, `0.06` rounds to zero and is `"0"`. Negative or non-finite numbers throw a `RangeError`.

    ## `convert(amount, unit) -> {amount, unit}`
    Writes a volume in its most natural unit. The units are `tsp`, `tbsp` (1 tbsp = 3 tsp) and `cup` (1 cup = 16 tbsp = 48 tsp). The amount
    is expressed in teaspoons first; 48 tsp or more becomes cups, otherwise 3 tsp or more becomes tbsp, otherwise it stays in tsp. Any other
    unit (`g`, `ml`, the empty unit for countable things) is returned unchanged.

    ## `scaleIngredient({name, amount, unit}, factor) -> {name, amount, unit}`
    `factor` must be a number above 0 (`RangeError` otherwise). The amount is multiplied by it; volume units are then passed through
    `convert`; countable items (unit `""`) are rounded **up** to a whole number; other units are just multiplied.

    ## `scaleRecipe(recipe, servings) -> recipe`
    `recipe` is `{name, servings, ingredients: [...]}`. The result has the new `servings` and every ingredient scaled by `servings / recipe.servings`.
    `servings` must be a positive integer (`RangeError` otherwise). The input is not modified.
''')

RECIPE_SRC = dd('''
    'use strict';

    const TSP = { tsp: 1, tbsp: 3, cup: 48 };

    function parseAmount(text) {
      const s = String(text).trim();
      let m = /^(\\d+)$/.exec(s) || /^(\\d+\\.\\d+)$/.exec(s);
      if (m) return Number(m[1]);
      m = /^(?:(\\d+) )?(\\d+)\\/(\\d+)$/.exec(s);
      if (!m) throw new RangeError(`bad amount: ${text}`);
      const den = Number(m[3]);
      if (den === 0) throw new RangeError(`zero denominator: ${text}`);
      return (m[1] ? Number(m[1]) : 0) + Number(m[2]) / den;
    }

    function gcd(a, b) {
      return b === 0 ? a : gcd(b, a % b);
    }

    function formatAmount(x) {
      if (!Number.isFinite(x) || x < 0) throw new RangeError(`bad amount: ${x}`);
      const eighths = Math.floor(x * 8 + 0.5);
      const whole = Math.floor(eighths / 8);
      const rest = eighths % 8;
      if (rest === 0) return String(whole);
      const g = gcd(rest, 8);
      const frac = `${rest / g}/${8 / g}`;
      return whole === 0 ? frac : `${whole} ${frac}`;
    }

    function convert(amount, unit) {
      if (!Object.hasOwn(TSP, unit)) return { amount, unit };
      const t = amount * TSP[unit];
      if (t >= 48) return { amount: t / 48, unit: 'cup' };
      if (t >= 3) return { amount: t / 3, unit: 'tbsp' };
      return { amount: t, unit: 'tsp' };
    }

    function scaleIngredient(ing, factor) {
      if (typeof factor !== 'number' || !(factor > 0)) throw new RangeError(`bad factor: ${factor}`);
      const scaled = ing.amount * factor;
      if (ing.unit === '') return { ...ing, amount: Math.ceil(scaled - 1e-9) };
      if (Object.hasOwn(TSP, ing.unit)) return { name: ing.name, ...convert(scaled, ing.unit) };
      return { ...ing, amount: scaled };
    }

    function scaleRecipe(recipe, servings) {
      if (!Number.isInteger(servings) || servings < 1) throw new RangeError(`bad servings: ${servings}`);
      const factor = servings / recipe.servings;
      return { ...recipe, servings, ingredients: recipe.ingredients.map((i) => scaleIngredient(i, factor)) };
    }

    module.exports = { parseAmount, formatAmount, convert, scaleIngredient, scaleRecipe };
''')

RECIPE_TEST = dd('''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { parseAmount, formatAmount, convert, scaleIngredient, scaleRecipe } = require('../src/recipe.js');

    test('parseAmount reads integers, decimals, fractions and mixed numbers', () => {
      assert.equal(parseAmount('2'), 2);
      assert.equal(parseAmount('0'), 0);
      assert.equal(parseAmount('2.5'), 2.5);
      assert.equal(parseAmount('0.125'), 0.125);
      assert.equal(parseAmount('3/4'), 0.75);
      assert.equal(parseAmount('1/3'), 1 / 3);
      assert.equal(parseAmount('1 1/2'), 1.5);
      assert.equal(parseAmount('2 3/8'), 2.375);
      assert.equal(parseAmount('  7/8  '), 0.875);
      assert.equal(parseAmount('10 1/4'), 10.25);
    });

    test('parseAmount rejects everything else', () => {
      for (const bad of ['', ' ', 'abc', '-1', '-1/2', '1/0', '1 1/0', '1.5/2', '1  1/2', '1 1/2/3', '.5', '5.', '1,5', '1 2', '1/ 2', '1 /2', '+3', '1e3', '0x10']) {
        assert.throws(() => parseAmount(bad), RangeError, JSON.stringify(bad));
      }
    });

    test('formatAmount writes eighths as reduced mixed numbers', () => {
      const cases = [[0, '0'], [1, '1'], [2, '2'], [0.125, '1/8'], [0.25, '1/4'], [0.375, '3/8'], [0.5, '1/2'], [0.625, '5/8'], [0.75, '3/4'], [0.875, '7/8'],
        [1.5, '1 1/2'], [2.25, '2 1/4'], [10.125, '10 1/8'], [3.875, '3 7/8']];
      for (const [x, want] of cases) assert.equal(formatAmount(x), want, String(x));
    });

    test('formatAmount rounds to the nearest eighth, halves up', () => {
      assert.equal(formatAmount(0.06), '0');
      assert.equal(formatAmount(0.0625), '1/8');
      assert.equal(formatAmount(0.07), '1/8');
      assert.equal(formatAmount(0.18), '1/8');
      assert.equal(formatAmount(0.1875), '1/4');
      assert.equal(formatAmount(0.3), '1/4');
      assert.equal(formatAmount(1.9375), '2');
      assert.equal(formatAmount(1.93), '1 7/8');
      assert.equal(formatAmount(2.9999), '3');
      assert.equal(formatAmount(0.9), '7/8');
    });

    test('formatAmount rejects negative and non-finite numbers', () => {
      for (const bad of [-1, -0.5, NaN, Infinity, -Infinity]) assert.throws(() => formatAmount(bad), RangeError);
    });

    test('convert picks the natural unit', () => {
      assert.deepEqual(convert(1, 'tsp'), { amount: 1, unit: 'tsp' });
      assert.deepEqual(convert(2.5, 'tsp'), { amount: 2.5, unit: 'tsp' });
      assert.deepEqual(convert(3, 'tsp'), { amount: 1, unit: 'tbsp' });
      assert.deepEqual(convert(4, 'tsp'), { amount: 4 / 3, unit: 'tbsp' });
      assert.deepEqual(convert(2, 'tbsp'), { amount: 2, unit: 'tbsp' });
      assert.deepEqual(convert(0.5, 'tbsp'), { amount: 1.5, unit: 'tsp' });
      assert.deepEqual(convert(15, 'tbsp'), { amount: 15, unit: 'tbsp' });
      assert.deepEqual(convert(16, 'tbsp'), { amount: 1, unit: 'cup' });
      assert.deepEqual(convert(47, 'tsp'), { amount: 47 / 3, unit: 'tbsp' });
      assert.deepEqual(convert(48, 'tsp'), { amount: 1, unit: 'cup' });
      assert.deepEqual(convert(0.25, 'cup'), { amount: 4, unit: 'tbsp' });
          assert.deepEqual(convert(2, 'cup'), { amount: 2, unit: 'cup' });
      assert.deepEqual(convert(0, 'tsp'), { amount: 0, unit: 'tsp' });
    });

    test('convert leaves other units alone', () => {
      assert.deepEqual(convert(500, 'g'), { amount: 500, unit: 'g' });
      assert.deepEqual(convert(250, 'ml'), { amount: 250, unit: 'ml' });
      assert.deepEqual(convert(3, ''), { amount: 3, unit: '' });
      assert.deepEqual(convert(100, 'cups'), { amount: 100, unit: 'cups' });
      assert.deepEqual(convert(1, 'constructor'), { amount: 1, unit: 'constructor' });
    });

    test('scaleIngredient multiplies and normalises', () => {
      assert.deepEqual(scaleIngredient({ name: 'flour', amount: 200, unit: 'g' }, 1.5), { name: 'flour', amount: 300, unit: 'g' });
      assert.deepEqual(scaleIngredient({ name: 'salt', amount: 1, unit: 'tsp' }, 3), { name: 'salt', amount: 1, unit: 'tbsp' });
      assert.deepEqual(scaleIngredient({ name: 'oil', amount: 4, unit: 'tbsp' }, 4), { name: 'oil', amount: 1, unit: 'cup' });
      assert.deepEqual(scaleIngredient({ name: 'milk', amount: 1, unit: 'cup' }, 0.25), { name: 'milk', amount: 4, unit: 'tbsp' });
      assert.deepEqual(scaleIngredient({ name: 'milk', amount: 1, unit: 'cup' }, 1), { name: 'milk', amount: 1, unit: 'cup' });
      assert.deepEqual(scaleIngredient({ name: 'sugar', amount: 1, unit: 'tbsp' }, 0.5), { name: 'sugar', amount: 1.5, unit: 'tsp' });
    });

    test('scaleIngredient rounds countable items up', () => {
      assert.deepEqual(scaleIngredient({ name: 'eggs', amount: 3, unit: '' }, 0.5), { name: 'eggs', amount: 2, unit: '' });
      assert.deepEqual(scaleIngredient({ name: 'eggs', amount: 2, unit: '' }, 1.5), { name: 'eggs', amount: 3, unit: '' });
      assert.deepEqual(scaleIngredient({ name: 'eggs', amount: 2, unit: '' }, 2), { name: 'eggs', amount: 4, unit: '' });
      assert.deepEqual(scaleIngredient({ name: 'onions', amount: 1, unit: '' }, 0.1), { name: 'onions', amount: 1, unit: '' });
      assert.deepEqual(scaleIngredient({ name: 'eggs', amount: 3, unit: '' }, 1), { name: 'eggs', amount: 3, unit: '' });
    });

    test('scaleIngredient rejects bad factors and keeps extra fields', () => {
      for (const bad of [0, -1, NaN, '2', null, undefined]) assert.throws(() => scaleIngredient({ name: 'x', amount: 1, unit: 'g' }, bad), RangeError);
      assert.deepEqual(scaleIngredient({ name: 'rice', amount: 100, unit: 'g', note: 'rinsed' }, 2), { name: 'rice', amount: 200, unit: 'g', note: 'rinsed' });
    });

    test('scaleRecipe scales every ingredient and leaves the input alone', () => {
      const recipe = { name: 'pancakes', servings: 4, ingredients: [{ name: 'flour', amount: 200, unit: 'g' }, { name: 'eggs', amount: 2, unit: '' }, { name: 'milk', amount: 0.5, unit: 'cup' }, { name: 'salt', amount: 1, unit: 'tsp' }] };
      const copy = JSON.parse(JSON.stringify(recipe));
      const six = scaleRecipe(recipe, 6);
      assert.equal(six.name, 'pancakes');
      assert.equal(six.servings, 6);
      assert.deepEqual(six.ingredients, [{ name: 'flour', amount: 300, unit: 'g' }, { name: 'eggs', amount: 3, unit: '' }, { name: 'milk', amount: 12, unit: 'tbsp' }, { name: 'salt', amount: 1.5, unit: 'tsp' }]);
      assert.deepEqual(recipe, copy);
      const one = scaleRecipe(recipe, 1);
      assert.deepEqual(one.ingredients, [{ name: 'flour', amount: 50, unit: 'g' }, { name: 'eggs', amount: 1, unit: '' }, { name: 'milk', amount: 2, unit: 'tbsp' }, { name: 'salt', amount: 0.25, unit: 'tsp' }]);
    });

    test('scaleRecipe validates servings', () => {
      const recipe = { name: 'x', servings: 2, ingredients: [] };
      for (const bad of [0, -2, 1.5, '4', NaN, undefined]) assert.throws(() => scaleRecipe(recipe, bad), RangeError);
      assert.deepEqual(scaleRecipe(recipe, 2), { name: 'x', servings: 2, ingredients: [] });
    });
''')

RECIPE_STUB = dd('''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { parseAmount } = require('../src/recipe.js');

    test('smoke', () => {
      assert.equal(typeof parseAmount, 'function');
    });
''')


def recipe(rng) -> TLib:
    files = {"README.md": RECIPE_README, "package.json": PKG % "recipe-scaler", "src/recipe.js": RECIPE_SRC}
    wrong = [
        ("test/recipe.gold.test.js", "assert.equal(parseAmount('2 3/8'), 2.375);", "assert.equal(parseAmount('2 3/8'), 2.425);"),
        ("test/recipe.gold.test.js", "[1.5, '1 1/2']", "[1.5, '1/2']"),
        ("test/recipe.gold.test.js", "assert.equal(formatAmount(0.0625), '1/8');", "assert.equal(formatAmount(0.0625), '0');"),
        ("test/recipe.gold.test.js", "assert.deepEqual(convert(3, 'tsp'), { amount: 1, unit: 'tbsp' });", "assert.deepEqual(convert(3, 'tsp'), { amount: 3, unit: 'tsp' });"),
        ("test/recipe.gold.test.js", "{ name: 'eggs', amount: 2, unit: '' }, 1.5), { name: 'eggs', amount: 3, unit: '' });", "{ name: 'eggs', amount: 2, unit: '' }, 1.5), { name: 'eggs', amount: 4, unit: '' });"),
    ]
    return TLib(
        name="js-recipe", lang="javascript", title="the recipe-card scaler", blurb="The community kitchen's recipe cards are rescaled for the number of people attending.",
        files=files, stub={"test/smoke.test.js": RECIPE_STUB}, gold={"test/recipe.gold.test.js": RECIPE_TEST}, mutate=["src/recipe.js"], cmd="node --test",
        where=WHERE_JS, difficulty=3, wrong_edits=wrong, timeout=40, focus="the accepted number formats, rounding to eighths, the unit ladder thresholds, and rounding up countable items",
    )


# ---------------------------------------------------------------------------------------------------------------------
# cron-like schedules
# ---------------------------------------------------------------------------------------------------------------------

CRON_README = dd('''
    # cronlite

    Tiny schedule expressions for the Fernhill allotment's watering robot. Everything is in UTC.

    ## Expressions
    All lower case, single spaces:

        daily at HH:MM
        weekly on <days> at HH:MM          <days>: comma separated list of mon tue wed thu fri sat sun
        monthly on <D> at HH:MM            <D>: 1..31
        monthly on the <ord> <day> at HH:MM    <ord>: first second third fourth last;  <day>: mon .. sun

    `HH` is 00..23 and `MM` is 00..59, both with two digits. Repeated days in a list are allowed and collapse.

    ## `parse(spec) -> schedule`
    Parses an expression. Anything else (wrong words, wrong case, extra spaces, out-of-range numbers, an empty list entry) throws a
    `SyntaxError` whose message starts with `cronlite:`. The shape of the returned schedule is private: pass it to the other functions.

    ## `describe(schedule) -> string`
    The canonical text of a schedule: weekly days in Monday-to-Sunday order without repeats, numbers as in the examples above (`monthly on 5 at
    07:05`, `weekly on mon,wed at 09:30`, `monthly on the last fri at 18:00`).

    ## `nextRun(schedule, from) -> Date`
    The first run time strictly after `from` (a `Date`). A monthly run on day `D` of a month that has fewer days happens on that month's last
    day instead (`monthly on 31` runs on 30 April and on 28 or 29 February). `monthly on the last fri` is the last Friday of the month; `first`
    to `fourth` are the 1st to 4th occurrence of that weekday in the month.

    ## `runsBetween(schedule, from, to) -> Date[]`
    Every run time `r` with `from < r <= to`, in order. `RangeError` if there would be more than 500.
''')

CRON_SRC = dd('''
    'use strict';

    const DAYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];
    const ORD = ['first', 'second', 'third', 'fourth', 'last'];

    function fail(msg) {
      throw new SyntaxError(`cronlite: ${msg}`);
    }

    function clock(text) {
      const m = /^([01]\\d|2[0-3]):([0-5]\\d)$/.exec(text);
      if (!m) fail(`bad time ${text}`);
      return { hour: Number(m[1]), minute: Number(m[2]) };
    }

    function parse(spec) {
      if (typeof spec !== 'string') fail('spec must be a string');
      let m = /^daily at (\\S+)$/.exec(spec);
      if (m) return { kind: 'daily', ...clock(m[1]) };
      m = /^weekly on (\\S+) at (\\S+)$/.exec(spec);
      if (m) {
        const days = new Set();
        for (const name of m[1].split(',')) {
          const i = DAYS.indexOf(name);
          if (i < 0) fail(`bad day ${name}`);
          days.add(i);
        }
        return { kind: 'weekly', days: [...days].sort((a, b) => ((a + 6) % 7) - ((b + 6) % 7)), ...clock(m[2]) };
      }
      m = /^monthly on (\\d{1,2}) at (\\S+)$/.exec(spec);
      if (m) {
        const day = Number(m[1]);
        if (day < 1 || day > 31) fail(`bad day of month ${m[1]}`);
        return { kind: 'monthly', day, ...clock(m[2]) };
      }
      m = /^monthly on the (\\S+) (\\S+) at (\\S+)$/.exec(spec);
      if (m) {
        const ord = ORD.indexOf(m[1]);
        const weekday = DAYS.indexOf(m[2]);
        if (ord < 0 || weekday < 0) fail(`bad ordinal day ${m[1]} ${m[2]}`);
        return { kind: 'ordinal', ord, weekday, ...clock(m[3]) };
      }
      return fail(`cannot parse ${JSON.stringify(spec)}`);
    }

    const hhmm = (s) => `${String(s.hour).padStart(2, '0')}:${String(s.minute).padStart(2, '0')}`;

    function describe(s) {
      switch (s.kind) {
        case 'daily':
          return `daily at ${hhmm(s)}`;
        case 'weekly':
          return `weekly on ${s.days.map((d) => DAYS[d]).join(',')} at ${hhmm(s)}`;
        case 'monthly':
          return `monthly on ${s.day} at ${hhmm(s)}`;
        default:
          return `monthly on the ${ORD[s.ord]} ${DAYS[s.weekday]} at ${hhmm(s)}`;
      }
    }

    function daysInMonth(year, month) {
      return new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
    }

    function matches(s, date) {
      const dom = date.getUTCDate();
      const dow = date.getUTCDay();
      switch (s.kind) {
        case 'daily':
          return true;
        case 'weekly':
          return s.days.includes(dow);
        case 'monthly':
          return dom === Math.min(s.day, daysInMonth(date.getUTCFullYear(), date.getUTCMonth()));
        default: {
          if (dow !== s.weekday) return false;
          if (s.ord === 4) return dom + 7 > daysInMonth(date.getUTCFullYear(), date.getUTCMonth());
          return Math.ceil(dom / 7) === s.ord + 1;
        }
      }
    }

    function nextRun(s, from) {
      const start = Date.UTC(from.getUTCFullYear(), from.getUTCMonth(), from.getUTCDate());
      for (let i = 0; i < 800; i++) {
        const day = new Date(start + i * 86400000);
        if (!matches(s, day)) continue;
        const at = new Date(Date.UTC(day.getUTCFullYear(), day.getUTCMonth(), day.getUTCDate(), s.hour, s.minute));
        if (at > from) return at;
      }
      throw new RangeError('no run found');
    }

    function runsBetween(s, from, to) {
      const out = [];
      let t = from;
      for (;;) {
        t = nextRun(s, t);
        if (t > to) return out;
        if (out.length >= 500) throw new RangeError('too many runs');
        out.push(t);
      }
    }

    module.exports = { parse, describe, nextRun, runsBetween };
''')

CRON_TEST = dd('''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { parse, describe, nextRun, runsBetween } = require('../src/cronlite.js');

    const D = (s) => new Date(s);
    const iso = (d) => d.toISOString();
    const next = (spec, from) => iso(nextRun(parse(spec), D(from)));

    test('describe gives the canonical text', () => {
      const cases = [
        ['daily at 06:30', 'daily at 06:30'],
        ['daily at 00:00', 'daily at 00:00'],
        ['daily at 23:59', 'daily at 23:59'],
        ['weekly on wed,mon at 09:30', 'weekly on mon,wed at 09:30'],
        ['weekly on sun,sat,mon at 07:05', 'weekly on mon,sat,sun at 07:05'],
        ['weekly on fri,fri,fri at 18:00', 'weekly on fri at 18:00'],
        ['monthly on 5 at 07:05', 'monthly on 5 at 07:05'],
        ['monthly on 05 at 07:05', 'monthly on 5 at 07:05'],
        ['monthly on 31 at 12:00', 'monthly on 31 at 12:00'],
        ['monthly on 1 at 00:00', 'monthly on 1 at 00:00'],
        ['monthly on the last fri at 18:00', 'monthly on the last fri at 18:00'],
        ['monthly on the first mon at 08:15', 'monthly on the first mon at 08:15'],
        ['monthly on the fourth sun at 22:45', 'monthly on the fourth sun at 22:45'],
        ['monthly on the second tue at 10:10', 'monthly on the second tue at 10:10'],
        ['monthly on the third thu at 10:10', 'monthly on the third thu at 10:10'],
      ];
      for (const [spec, want] of cases) assert.equal(describe(parse(spec)), want, spec);
    });

    test('parse rejects malformed expressions', () => {
      const bad = ['', 'daily', 'daily at 6:30', 'daily at 24:00', 'daily at 12:60', 'daily at 12:5', 'daily at 12-30', 'Daily at 06:30', 'daily  at 06:30', 'daily at 06:30 ',
        'weekly on at 06:30', 'weekly on mon, tue at 06:30', 'weekly on mon,,tue at 06:30', 'weekly on monday at 06:30', 'weekly on mon at 25:00', 'weekly mon at 06:30',
        'monthly on 0 at 06:30', 'monthly on 32 at 06:30', 'monthly on 100 at 06:30', 'monthly on -1 at 06:30', 'monthly on x at 06:30',
        'monthly on the fifth mon at 06:30', 'monthly on the last monday at 06:30', 'monthly on the Last mon at 06:30', 'monthly on last mon at 06:30', 'yearly on 1 at 00:00', 'hourly'];
      for (const spec of bad) assert.throws(() => parse(spec), (e) => e instanceof SyntaxError && e.message.startsWith('cronlite:'), JSON.stringify(spec));
      for (const spec of [null, undefined, 42, {}]) assert.throws(() => parse(spec), SyntaxError);
    });

    test('daily runs', () => {
      assert.equal(next('daily at 06:30', '2025-03-10T05:00:00Z'), '2025-03-10T06:30:00.000Z');
      assert.equal(next('daily at 06:30', '2025-03-10T06:29:59.999Z'), '2025-03-10T06:30:00.000Z');
      assert.equal(next('daily at 06:30', '2025-03-10T06:30:00Z'), '2025-03-11T06:30:00.000Z');
      assert.equal(next('daily at 06:30', '2025-03-10T23:59:00Z'), '2025-03-11T06:30:00.000Z');
      assert.equal(next('daily at 00:00', '2025-12-31T00:00:00Z'), '2026-01-01T00:00:00.000Z');
      assert.equal(next('daily at 23:59', '2024-02-28T23:59:00Z'), '2024-02-29T23:59:00.000Z');
    });

    test('weekly runs', () => {
      const spec = 'weekly on mon,wed at 09:30';
      assert.equal(next(spec, '2025-03-10T09:29:00Z'), '2025-03-10T09:30:00.000Z'); // Monday
      assert.equal(next(spec, '2025-03-10T09:30:00Z'), '2025-03-12T09:30:00.000Z');
      assert.equal(next(spec, '2025-03-11T00:00:00Z'), '2025-03-12T09:30:00.000Z'); // Tuesday
      assert.equal(next(spec, '2025-03-12T10:00:00Z'), '2025-03-17T09:30:00.000Z');
      assert.equal(next(spec, '2025-03-16T23:00:00Z'), '2025-03-17T09:30:00.000Z'); // Sunday
      assert.equal(next('weekly on sun at 00:00', '2025-03-09T00:00:00Z'), '2025-03-16T00:00:00.000Z');
      assert.equal(next('weekly on sun at 00:00', '2025-03-08T12:00:00Z'), '2025-03-09T00:00:00.000Z');
      assert.equal(next('weekly on sat,sun at 10:00', '2025-03-15T10:00:00Z'), '2025-03-16T10:00:00.000Z');
      assert.equal(next('weekly on fri at 23:59', '2025-12-31T23:59:00Z'), '2026-01-02T23:59:00.000Z');
    });

    test('monthly by day number', () => {
      assert.equal(next('monthly on 15 at 08:00', '2025-03-10T00:00:00Z'), '2025-03-15T08:00:00.000Z');
      assert.equal(next('monthly on 15 at 08:00', '2025-03-15T08:00:00Z'), '2025-04-15T08:00:00.000Z');
      assert.equal(next('monthly on 15 at 08:00', '2025-12-20T00:00:00Z'), '2026-01-15T08:00:00.000Z');
      assert.equal(next('monthly on 1 at 00:00', '2025-03-01T00:00:00Z'), '2025-04-01T00:00:00.000Z');
      assert.equal(next('monthly on 31 at 12:00', '2025-01-31T12:00:00Z'), '2025-02-28T12:00:00.000Z');
      assert.equal(next('monthly on 31 at 12:00', '2024-01-31T12:00:00Z'), '2024-02-29T12:00:00.000Z');
      assert.equal(next('monthly on 31 at 12:00', '2025-03-31T12:00:00Z'), '2025-04-30T12:00:00.000Z');
      assert.equal(next('monthly on 31 at 12:00', '2025-04-30T12:00:00Z'), '2025-05-31T12:00:00.000Z');
      assert.equal(next('monthly on 30 at 12:00', '2025-01-30T12:00:00Z'), '2025-02-28T12:00:00.000Z');
      assert.equal(next('monthly on 29 at 12:00', '2025-01-29T12:00:00Z'), '2025-02-28T12:00:00.000Z');
      assert.equal(next('monthly on 29 at 12:00', '2024-01-29T12:00:00Z'), '2024-02-29T12:00:00.000Z');
      assert.equal(next('monthly on 28 at 12:00', '2025-02-27T00:00:00Z'), '2025-02-28T12:00:00.000Z');
      assert.equal(next('monthly on 30 at 12:00', '2025-02-28T12:30:00Z'), '2025-03-30T12:00:00.000Z');
    });

    test('monthly by ordinal weekday', () => {
      assert.equal(next('monthly on the first mon at 08:15', '2025-03-01T00:00:00Z'), '2025-03-03T08:15:00.000Z');
      assert.equal(next('monthly on the first mon at 08:15', '2025-03-03T08:15:00Z'), '2025-04-07T08:15:00.000Z');
      assert.equal(next('monthly on the first sat at 08:15', '2025-03-01T08:00:00Z'), '2025-03-01T08:15:00.000Z');
      assert.equal(next('monthly on the second tue at 10:10', '2025-03-01T00:00:00Z'), '2025-03-11T10:10:00.000Z');
      assert.equal(next('monthly on the third thu at 10:10', '2025-03-01T00:00:00Z'), '2025-03-20T10:10:00.000Z');
      assert.equal(next('monthly on the fourth sun at 22:45', '2025-03-01T00:00:00Z'), '2025-03-23T22:45:00.000Z');
      assert.equal(next('monthly on the last fri at 18:00', '2025-03-01T00:00:00Z'), '2025-03-28T18:00:00.000Z');
      assert.equal(next('monthly on the last fri at 18:00', '2025-03-28T18:00:00Z'), '2025-04-25T18:00:00.000Z');
      assert.equal(next('monthly on the last sun at 18:00', '2025-03-01T00:00:00Z'), '2025-03-30T18:00:00.000Z');
      assert.equal(next('monthly on the last mon at 18:00', '2025-03-01T00:00:00Z'), '2025-03-31T18:00:00.000Z');
      assert.equal(next('monthly on the last mon at 18:00', '2025-03-31T18:00:00Z'), '2025-04-28T18:00:00.000Z');
      assert.equal(next('monthly on the last sat at 18:00', '2024-02-01T00:00:00Z'), '2024-02-24T18:00:00.000Z');
      assert.equal(next('monthly on the fourth fri at 09:00', '2025-03-01T00:00:00Z'), '2025-03-28T09:00:00.000Z');
      assert.equal(next('monthly on the fourth sat at 09:00', '2025-03-01T00:00:00Z'), '2025-03-22T09:00:00.000Z');
      assert.equal(next('monthly on the first fri at 09:00', '2025-12-26T00:00:00Z'), '2026-01-02T09:00:00.000Z');
    });

    test('nextRun accepts any Date and does not modify it', () => {
      const from = D('2025-03-10T12:00:00Z');
      const copy = from.getTime();
      nextRun(parse('daily at 13:00'), from);
      assert.equal(from.getTime(), copy);
      assert.equal(iso(nextRun(parse('daily at 13:00'), new Date(Date.UTC(2025, 2, 10, 12, 0, 0, 1)))), '2025-03-10T13:00:00.000Z');
    });

    test('runsBetween is exclusive at the start and inclusive at the end', () => {
      const s = parse('daily at 06:00');
      const r = runsBetween(s, D('2025-03-10T06:00:00Z'), D('2025-03-13T06:00:00Z')).map(iso);
      assert.deepEqual(r, ['2025-03-11T06:00:00.000Z', '2025-03-12T06:00:00.000Z', '2025-03-13T06:00:00.000Z']);
      assert.deepEqual(runsBetween(s, D('2025-03-10T06:00:00Z'), D('2025-03-10T06:00:00Z')), []);
      assert.deepEqual(runsBetween(s, D('2025-03-10T07:00:00Z'), D('2025-03-11T05:59:59Z')), []);
      assert.deepEqual(runsBetween(s, D('2025-03-10T05:59:59Z'), D('2025-03-10T06:00:00Z')).map(iso), ['2025-03-10T06:00:00.000Z']);
    });

    test('runsBetween over a month and its limit', () => {
      const w = parse('weekly on mon,fri at 09:00');
      const r = runsBetween(w, D('2025-03-01T00:00:00Z'), D('2025-03-31T23:59:59Z')).map(iso);
      assert.equal(r.length, 9);
      assert.equal(r[0], '2025-03-03T09:00:00.000Z');
      assert.equal(r[8], '2025-03-31T09:00:00.000Z');
      assert.throws(() => runsBetween(parse('daily at 00:00'), D('2025-01-01T00:00:00Z'), D('2026-06-30T00:00:00Z')), RangeError);
      assert.equal(runsBetween(parse('daily at 00:00'), D('2025-01-01T00:00:00Z'), D('2026-05-15T00:00:00Z')).length, 499);
    });
''')

CRON_STUB = dd('''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { parse } = require('../src/cronlite.js');

    test('smoke', () => {
      assert.equal(typeof parse, 'function');
    });
''')


def cronlite(rng) -> TLib:
    files = {"README.md": CRON_README, "package.json": PKG % "cronlite", "src/cronlite.js": CRON_SRC}
    wrong = [
        ("test/cronlite.gold.test.js", "assert.equal(next('daily at 06:30', '2025-03-10T06:30:00Z'), '2025-03-11T06:30:00.000Z');", "assert.equal(next('daily at 06:30', '2025-03-10T06:30:00Z'), '2025-03-10T06:30:00.000Z');"),
        ("test/cronlite.gold.test.js", "assert.equal(next('monthly on 31 at 12:00', '2025-03-31T12:00:00Z'), '2025-04-30T12:00:00.000Z');", "assert.equal(next('monthly on 31 at 12:00', '2025-03-31T12:00:00Z'), '2025-05-01T12:00:00.000Z');"),
        ("test/cronlite.gold.test.js", "assert.equal(next('monthly on the last fri at 18:00', '2025-03-01T00:00:00Z'), '2025-03-28T18:00:00.000Z');", "assert.equal(next('monthly on the last fri at 18:00', '2025-03-01T00:00:00Z'), '2025-03-21T18:00:00.000Z');"),
        ("test/cronlite.gold.test.js", "['weekly on wed,mon at 09:30', 'weekly on mon,wed at 09:30'],", "['weekly on wed,mon at 09:30', 'weekly on wed,mon at 09:30'],"),
    ]
    return TLib(
        name="js-cronlite", lang="javascript", title="the cronlite schedule expressions", blurb="The watering robot reads its schedule from one-line expressions parsed by `cronlite`.",
        files=files, stub={"test/smoke.test.js": CRON_STUB}, gold={"test/cronlite.gold.test.js": CRON_TEST}, mutate=["src/cronlite.js"], cmd="node --test",
        where=WHERE_JS, difficulty=4, wrong_edits=wrong, timeout=40, focus="the grammar's strictness, strictly-after semantics, short months, and the ordinal / last weekday rules",
    )
