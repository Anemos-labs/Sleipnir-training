"""Slot modules (javascript), part 1: shop cart, async job runner, timesheets."""
from fx import dd

from ._slots import Bad, Module, Slot, sub, validate_module

PKG = dd('''
    {
      "name": "linden-row",
      "version": "1.4.0",
      "private": true,
      "type": "commonjs"
    }
''')

# ---------------------------------------------------------------------------------------------------------------------
# shop cart
# ---------------------------------------------------------------------------------------------------------------------

CART_TEMPLATE = dd('''
    'use strict';
    // Cart maths for the Linden Row online shop. Money is an integer number of pence.

    const COUPONS = {
      SPRING10: { type: 'pct', value: 10 },
      WELCOME5: { type: 'off', value: 500 },
      FREESHIP: { type: 'ship', value: 0 },
    };

    @@qty@@

    @@line@@

    @@total@@

    @@merge@@

    @@sort@@

    @@shipping@@

    @@escape@@

    @@receipt@@

    @@reserve@@

    module.exports = { parseQty, lineTotal, cartTotal, mergeCarts, sortByPrice, shippingFor, escapeHtml, renderReceipt, reserveAll };
''')

_C_QTY = dd('''
    function parseQty(input) {
      const n = Number.parseInt(String(input).trim(), 10);
      if (!Number.isInteger(n) || n < 1 || n > 99) {
        throw new RangeError(`bad quantity: ${input}`);
      }
      return n;
    }
''')
_C_LINE = dd('''
    // price of one cart line after its percentage discount, rounded half up to a penny
    function lineTotal(item) {
      return Math.round((item.pence * item.qty * (100 - (item.discountPct || 0))) / 100);
    }
''')
_C_TOTAL = dd('''
    // sum of the lines, then one coupon (unknown codes are ignored); the total never goes below zero
    function cartTotal(items, couponCode) {
      let total = items.reduce((sum, item) => sum + lineTotal(item), 0);
      if (couponCode && Object.hasOwn(COUPONS, couponCode)) {
        const c = COUPONS[couponCode];
        if (c.type === 'pct') total -= Math.round((total * c.value) / 100);
        if (c.type === 'off') total -= c.value;
      }
      return Math.max(total, 0);
    }
''')
_C_MERGE = dd('''
    // combine two carts by SKU, adding the quantities; neither input is modified
    function mergeCarts(a, b) {
      const bySku = new Map();
      for (const item of [...a, ...b]) {
        const have = bySku.get(item.sku);
        bySku.set(item.sku, have ? { ...have, qty: have.qty + item.qty } : { ...item });
      }
      return [...bySku.values()];
    }
''')
_C_SORT = dd('''
    // cheapest first, without touching the caller's array
    function sortByPrice(items) {
      return [...items].sort((x, y) => x.pence - y.pence);
    }
''')
_C_SHIPPING = dd('''
    // shipping in pence: free from 5000, otherwise by destination
    function shippingFor(totalPence, country) {
      if (totalPence >= 5000) return 0;
      switch (country) {
        case 'GB':
          return 395;
        case 'IE':
        case 'FR':
          return 795;
        default:
          return 1295;
      }
    }
''')
_C_ESCAPE = dd('''
    function escapeHtml(s) {
      return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }
''')
_C_RECEIPT = dd('''
    function renderReceipt(items, customerName) {
      const rows = items
        .map((i) => `<tr><td>${escapeHtml(i.name)}</td><td>${i.qty}</td><td>${(lineTotal(i) / 100).toFixed(2)}</td></tr>`)
        .join('');
      return `<h1>Thank you, ${escapeHtml(customerName)}</h1><table>${rows}</table>`;
    }
''')
_C_RESERVE = dd('''
    // reserve every line in the warehouse; resolves to the list of reservation ids, rejects if any line cannot be reserved
    async function reserveAll(items, warehouse) {
      const ids = await Promise.all(items.map((item) => warehouse.reserve(item.sku, item.qty)));
      return ids;
    }
''')

CART = Module(
    name="js-linden-cart", lang="javascript", path="src/cart.js", difficulty=3,
    title="Cart helpers: quantities, totals, coupons, merge, shipping, receipt",
    blurb="The `linden-row` shop back end runs on Node; `src/cart.js` is the cart logic behind the checkout page.",
    intro="Checkout currently does its sums in the browser. This PR moves the cart logic to the server so prices can be trusted:",
    outro="Customer names and product names are free text. Compared totals with the old browser code on 50 recorded carts.",
    new_file=True,
    template=CART_TEMPLATE,
    ctx={"package.json": PKG, "README.md": "# linden-row\n\nShop back end.\n"},
    slots=[
        Slot("qty", "parseQty", _C_QTY, [
            Bad(_C_QTY.replace("!Number.isInteger(n) || ", ""), "validation", "NaN is not rejected: both comparisons with NaN are false, so `parseQty('abc')` returns NaN", ("NaN", "isInteger", "validation")),
            Bad(_C_QTY.replace("n < 1 || n > 99", "n < 1 || n >= 99"), "off-by-one", "99 is rejected although the limit is 99", (">=", "99", "boundary")),
            Bad(_C_QTY.replace("Number.parseInt(String(input).trim(), 10)", "Number(input)"), "validation", "Number() accepts '', '0x10', '1e1' and booleans, so strings like `0x10` become quantities", ("Number(", "parseInt", "hex", "coercion")),
        ], note="adds `parseQty()` for the quantity box"),
        Slot("line", "lineTotal", _C_LINE, [
            Bad(_C_LINE.replace("Math.round((item.pence * item.qty * (100 - (item.discountPct || 0))) / 100)", "Math.floor((item.pence * item.qty * (100 - (item.discountPct || 0))) / 100)"), "logic", "Math.floor instead of Math.round: every discounted line is rounded down", ("floor", "round", "half")),
            Bad(_C_LINE.replace("Math.round((item.pence * item.qty * (100 - (item.discountPct || 0))) / 100)", "(item.pence * item.qty * (100 - (item.discountPct || 0))) / 100"), "api-misuse", "the result is a float with fractions of a penny: nothing rounds the discounted amount", ("round", "float", "fraction", "pence")),
        ], note="adds `lineTotal()`"),
        Slot("total", "cartTotal", _C_TOTAL, [
            Bad(_C_TOTAL.replace("couponCode && Object.hasOwn(COUPONS, couponCode)", "couponCode && COUPONS[couponCode]"), "security", "COUPONS is a plain object, so codes like `constructor` or `__proto__` find inherited properties instead of being ignored (unsafe lookup)", ("hasOwn", "prototype", "constructor", "__proto__")),
            Bad(_C_TOTAL.replace("  return Math.max(total, 0);", "  return total;"), "logic", "an `off` coupon larger than the cart makes the total negative", ("Math.max", "negative", "total")),
            Bad(_C_TOTAL.replace("if (c.type === 'pct') total -= Math.round((total * c.value) / 100);", "if (c.type === 'pct') total -= (total * c.value) / 100;"), "api-misuse", "the percentage coupon leaves fractions of a penny in the total", ("round", "fraction", "pence", "float")),
        ], note="adds `cartTotal()` with coupons"),
        Slot("merge", "mergeCarts", _C_MERGE, [
            Bad(dd('''
                // combine two carts by SKU, adding the quantities; neither input is modified
                function mergeCarts(a, b) {
                  const bySku = new Map();
                  for (const item of [...a, ...b]) {
                    const have = bySku.get(item.sku);
                    if (have) have.qty += item.qty;
                    else bySku.set(item.sku, item);
                  }
                  return [...bySku.values()];
                }
            '''), "logic", "quantities are added on the objects that belong to the input carts, so `a` and `b` are modified", ("mutat", "qty +=", "input", "copy")),
        ], note="adds `mergeCarts()`"),
        Slot("sort", "sortByPrice", _C_SORT, [
            Bad(_C_SORT.replace("[...items].sort(", "items.sort("), "logic", "sorts the caller's array in place although the comment says it must not", ("in place", "mutat", "copy", "sort")),
            Bad(_C_SORT.replace("(x, y) => x.pence - y.pence", "(x, y) => x.pence > y.pence"), "api-misuse", "the comparator returns a boolean instead of a number, so the sort order is unreliable", ("comparator", "boolean", "sort")),
        ], note="adds `sortByPrice()`"),
        Slot("shipping", "shippingFor", _C_SHIPPING, [
            Bad(_C_SHIPPING.replace("if (totalPence >= 5000) return 0;", "if (totalPence > 5000) return 0;"), "off-by-one", "an order of exactly 50.00 pays shipping although shipping is free from 50.00", (">", "5000", "boundary", "free")),
            Bad(dd('''
                // shipping in pence: free from 5000, otherwise by destination
                function shippingFor(totalPence, country) {
                  if (totalPence >= 5000) return 0;
                  let cost = 1295;
                  switch (country) {
                    case 'GB':
                      cost = 395;
                    case 'IE':
                    case 'FR':
                      cost = 795;
                      break;
                  }
                  return cost;
                }
            '''), "logic", "the GB case has no break, so it falls through and GB orders are charged the IE/FR price", ("fall", "break", "switch", "GB")),
        ], note="adds `shippingFor()`: free from 50.00"),
        Slot("escape", "escapeHtml", _C_ESCAPE, [
            Bad(_C_ESCAPE.replace("    .replace(/\"/g, '&quot;')\n    .replace(/'/g, '&#39;');", "    .replace(/\"/g, '&quot;');"), "security", "single quotes are not escaped, so text placed inside a single-quoted attribute can break out of it (XSS)", ("quote", "attribute", "xss", "escape")),
            Bad(dd('''
                function escapeHtml(s) {
                  return String(s)
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;')
                    .replace(/&/g, '&amp;');
                }
            '''), "security", "& is escaped last, so the `&` of the entities produced by the earlier replacements is escaped again: output like `&amp;lt;` is shown to users and the escaping is no longer trustworthy", ("&amp;", "order", "double", "escape")),
        ], note="adds `escapeHtml()`"),
        Slot("receipt", "renderReceipt", _C_RECEIPT, [
            Bad(_C_RECEIPT.replace("<h1>Thank you, ${escapeHtml(customerName)}</h1>", "<h1>Thank you, ${customerName}</h1>"), "security", "the customer's name goes into the HTML unescaped (stored XSS in the receipt page and e-mail)", ("xss", "escapeHtml", "customerName", "unescaped")),
            Bad(_C_RECEIPT.replace("<td>${escapeHtml(i.name)}</td>", "<td>${i.name}</td>"), "security", "product names are inserted without escaping", ("xss", "escapeHtml", "name", "unescaped")),
        ], note="adds `renderReceipt()`"),
        Slot("reserve", "reserveAll", _C_RESERVE, [
            Bad(dd('''
                // reserve every line in the warehouse; resolves to the list of reservation ids, rejects if any line cannot be reserved
                async function reserveAll(items, warehouse) {
                  const ids = [];
                  items.forEach(async (item) => {
                    ids.push(await warehouse.reserve(item.sku, item.qty));
                  });
                  return ids;
                }
            '''), "concurrency", "forEach does not await its async callback, so the function returns the (empty) array before any reservation finished and rejections are unhandled", ("forEach", "await", "async", "Promise.all")),
            Bad(dd('''
                // reserve every line in the warehouse; resolves to the list of reservation ids, rejects if any line cannot be reserved
                async function reserveAll(items, warehouse) {
                  const ids = [];
                  for (const item of items) {
                    try {
                      ids.push(await warehouse.reserve(item.sku, item.qty));
                    } catch (err) {
                      console.error('reserve failed', err);
                    }
                  }
                  return ids;
                }
            '''), "error-handling", "a failed reservation is only logged, so the function resolves with fewer ids instead of rejecting, and the order goes through with items that were never reserved", ("catch", "swallow", "reject", "console.error")),
        ], note="adds `reserveAll()`: reserve every line in the warehouse"),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# async job runner
# ---------------------------------------------------------------------------------------------------------------------

RUNNER_TEMPLATE = dd('''
    'use strict';
    // Small promise helpers used by the nightly exports: bounded concurrency, retries, timeouts, a throttled logger.

    @@pool@@

    @@retry@@

    @@timeout@@

    @@once@@

    @@debounce@@

    module.exports = { runPool, retry, withTimeout, once, debounce };
''')

_R_POOL = dd('''
    // run the task functions with at most `limit` in flight; resolves to the results in input order
    async function runPool(tasks, limit) {
      const results = new Array(tasks.length);
      let next = 0;
      async function worker() {
        while (next < tasks.length) {
          const i = next++;
          results[i] = await tasks[i]();
        }
      }
      const workers = [];
      for (let w = 0; w < Math.min(limit, tasks.length); w++) workers.push(worker());
      await Promise.all(workers);
      return results;
    }
''')
_R_RETRY = dd('''
    // call fn up to `attempts` times, waiting `delayMs` between tries; rejects with the last error
    async function retry(fn, attempts, delayMs) {
      let lastErr;
      for (let n = 1; n <= attempts; n++) {
        try {
          return await fn(n);
        } catch (err) {
          lastErr = err;
          if (n < attempts) await new Promise((resolve) => setTimeout(resolve, delayMs));
        }
      }
      throw lastErr;
    }
''')
_R_TIMEOUT = dd('''
    // reject if promise does not settle within ms; the timer is always cleared
    function withTimeout(promise, ms) {
      let timer;
      const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(`timed out after ${ms} ms`)), ms);
      });
      return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
    }
''')
_R_ONCE = dd('''
    // wrap an async function so that concurrent callers share one run; a failure is not cached
    function once(fn) {
      let inflight = null;
      return () => {
        if (!inflight) {
          inflight = fn().finally(() => {
            inflight = null;
          });
        }
        return inflight;
      };
    }
''')
_R_DEBOUNCE = dd('''
    // call fn once, `ms` after the last call; later calls reset the timer and the latest arguments win
    function debounce(fn, ms) {
      let timer = null;
      return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => {
          timer = null;
          fn(...args);
        }, ms);
      };
    }
''')

RUNNER = Module(
    name="js-asynckit", lang="javascript", path="src/asynckit.js", difficulty=3,
    title="asynckit: bounded pool, retry, timeout, once, debounce",
    blurb="The `exports` service builds the nightly CSV exports; `src/asynckit.js` holds its promise helpers.",
    intro="The exporter fires all requests at once and hammers the API. This PR adds small helpers to tame that:",
    outro="Each helper was tried against a fake API that fails randomly. No unit tests yet.",
    new_file=True,
    template=RUNNER_TEMPLATE,
    ctx={"package.json": PKG.replace("linden-row", "exports"), "README.md": "# exports\n\nNightly exports.\n"},
    slots=[
        Slot("pool", "runPool", _R_POOL, [
            Bad(sub(_R_POOL, "const i = next++;\nresults[i] = await tasks[i]();", "results[next] = await tasks[next]();\nnext++;"), "concurrency", "next is read before the await and incremented after it, so several workers take the same task index: some tasks run twice and others never run", ("next++", "race", "index", "await")),
            Bad(_R_POOL.replace("Math.min(limit, tasks.length)", "tasks.length"), "logic", "every task gets its own worker, so the `limit` is ignored and everything runs at once", ("limit", "Math.min", "workers")),
            Bad(sub(_R_POOL, "while (next < tasks.length) {\nconst i = next++;\nresults[i] = await tasks[i]();\n}", "for (let i = 0; i < tasks.length; i++) {\n  results[i] = await tasks[i]();\n}"), "concurrency", "each worker walks the whole task list instead of taking the next free index, so every task runs once per worker", ("worker", "loop", "duplicate", "limit")),
        ], note="adds `runPool()`: bounded concurrency, results in input order"),
        Slot("retry", "retry", _R_RETRY, [
            Bad(_R_RETRY.replace("for (let n = 1; n <= attempts; n++) {", "for (let n = 1; n < attempts; n++) {"), "off-by-one", "one attempt too few: with attempts = 1 the function never calls fn and throws undefined", ("<", "attempts", "off by one", "undefined")),
            Bad(sub(_R_RETRY, "if (n < attempts) await new Promise((resolve) => setTimeout(resolve, delayMs));", "if (n < attempts) setTimeout(() => {}, delayMs);"), "concurrency", "the delay is not awaited, so retries run back-to-back with no wait", ("await", "delay", "setTimeout", "wait")),
            Bad(sub(_R_RETRY, "throw lastErr;", "return undefined;"), "error-handling", "when every attempt fails the helper resolves with undefined instead of rejecting with the last error", ("throw", "undefined", "swallow", "reject")),
        ], note="adds `retry()`"),
        Slot("timeout", "withTimeout", _R_TIMEOUT, [
            Bad(_R_TIMEOUT.replace("Promise.race([promise, timeout]).finally(() => clearTimeout(timer))", "Promise.race([promise, timeout])"), "resource-leak", "the timer is never cleared, so every call keeps a pending timer (and the process alive) until the timeout elapses", ("clearTimeout", "timer", "leak", "finally")),
        ], note="adds `withTimeout()`"),
        Slot("once", "once", _R_ONCE, [
            Bad(sub(_R_ONCE, "inflight = fn().finally(() => {\ninflight = null;\n});", "inflight = fn();"), "logic", "inflight is never reset, so the first result (or failure) is cached forever although a failure must not be cached", ("inflight", "cache", "reset", "finally")),
        ], note="adds `once()`: share one in-flight run between concurrent callers"),
        Slot("debounce", "debounce", _R_DEBOUNCE, [
            Bad(sub(_R_DEBOUNCE, "clearTimeout(timer);", ""), "logic", "the previous timer is not cleared, so every call fires `fn` (this is a delay, not a debounce)", ("clearTimeout", "timer", "every call")),
            Bad(_R_DEBOUNCE.replace("fn(...args);", "fn(args);"), "logic", "the arguments are passed as one array instead of being spread", ("spread", "args", "...args")),
        ], note="adds `debounce()`"),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# timesheets
# ---------------------------------------------------------------------------------------------------------------------

TIME_TEMPLATE = dd('''
    'use strict';
    // Timesheet helpers for the Tarn & Co workshop: dates are plain calendar days ("2025-03-14"), hours are decimals.

    const DAY_MS = 24 * 60 * 60 * 1000;

    @@parse@@

    @@iso@@

    @@weekday@@

    @@between@@

    @@weekstart@@

    @@round@@

    @@summary@@

    module.exports = { parseDay, toIso, isWeekend, workingDays, weekStart, roundHours, summarise };
''')

_T_PARSE = dd('''
    // "YYYY-MM-DD" -> a Date at 12:00 UTC of that calendar day (noon avoids edge effects of time zones); throws on bad input
    function parseDay(text) {
      const m = /^(\\d{4})-(\\d{2})-(\\d{2})$/.exec(text);
      if (!m) throw new RangeError(`bad date: ${text}`);
      const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
      const date = new Date(Date.UTC(y, mo - 1, d, 12));
      if (date.getUTCMonth() !== mo - 1 || date.getUTCDate() !== d) throw new RangeError(`no such day: ${text}`);
      return date;
    }
''')
_T_ISO = dd('''
    function toIso(date) {
      return date.toISOString().slice(0, 10);
    }
''')
_T_WEEKDAY = dd('''
    function isWeekend(date) {
      const dow = date.getUTCDay();
      return dow === 0 || dow === 6;
    }
''')
_T_BETWEEN = dd('''
    // number of working days (Mon-Fri) in the inclusive range [from, to]; 0 if to is before from
    function workingDays(from, to) {
      let n = 0;
      for (let t = from.getTime(); t <= to.getTime(); t += DAY_MS) {
        if (!isWeekend(new Date(t))) n++;
      }
      return n;
    }
''')
_T_WEEKSTART = dd('''
    // the Monday of the week that contains `date`
    function weekStart(date) {
      const back = (date.getUTCDay() + 6) % 7;
      return new Date(date.getTime() - back * DAY_MS);
    }
''')
_T_ROUND = dd('''
    // hours rounded to the nearest quarter hour; halves round up
    function roundHours(hours) {
      return Math.round(hours * 4) / 4;
    }
''')
_T_SUMMARY = dd('''
    // total hours per ISO week start: entries are {day: "YYYY-MM-DD", hours}; result keys are sorted
    function summarise(entries) {
      const totals = new Map();
      for (const e of entries) {
        const key = toIso(weekStart(parseDay(e.day)));
        totals.set(key, (totals.get(key) || 0) + e.hours);
      }
      return [...totals.entries()].sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0)).map(([week, hours]) => ({ week, hours }));
    }
''')

TIMESHEET = Module(
    name="js-timesheet", lang="javascript", path="src/timesheet.js", difficulty=3,
    title="Timesheet helpers: working days, week starts, quarter-hour rounding, weekly totals",
    blurb="The workshop's `tarn` app collects staff hours; `src/timesheet.js` does the date maths for the weekly report.",
    intro="The weekly report is assembled in a spreadsheet macro. This PR adds the date and hour helpers the app needs:",
    outro="The server runs in Europe/London; some staff enter hours from phones in other zones. Checked against the March 2025 timesheets.",
    new_file=True,
    template=TIME_TEMPLATE,
    ctx={"package.json": PKG.replace("linden-row", "tarn"), "README.md": "# tarn\n\nWorkshop hours.\n"},
    slots=[
        Slot("parse", "parseDay", _T_PARSE, [
            Bad(sub(_T_PARSE, "const date = new Date(Date.UTC(y, mo - 1, d, 12));\nif (date.getUTCMonth() !== mo - 1 || date.getUTCDate() !== d) throw new RangeError(`no such day: ${text}`);\nreturn date;", "return new Date(Date.UTC(y, mo - 1, d, 12));"), "validation", "impossible days such as 2025-02-30 roll over into March instead of being rejected", ("rollover", "2025-02-30", "getUTCDate", "validate")),
            Bad(_T_PARSE.replace("new Date(Date.UTC(y, mo - 1, d, 12))", "new Date(Date.UTC(y, mo, d, 12))"), "off-by-one", "JavaScript months are 0-based: `mo` instead of `mo - 1` shifts every date one month ahead (and the validity check then rejects 31 January etc.)", ("month", "0-based", "mo - 1")),
            Bad(_T_PARSE.replace("new Date(Date.UTC(y, mo - 1, d, 12))", "new Date(y, mo - 1, d)"), "logic", "local-time construction at midnight: in a zone with DST the calendar day can shift when converted to UTC, and the UTC getters below read the wrong day", ("local", "UTC", "timezone", "midnight")),
        ], note="adds `parseDay()`"),
        Slot("iso", "toIso", _T_ISO, [
            Bad(_T_ISO.replace("date.toISOString().slice(0, 10)", "date.toLocaleDateString('en-CA')"), "logic", "toLocaleDateString formats in the server's local zone, while every other helper works in UTC, so the printed day can differ from the Date's UTC day", ("local", "UTC", "timezone", "toLocaleDateString")),
        ], note="adds `toIso()`"),
        Slot("weekday", "isWeekend", _T_WEEKDAY, [
            Bad(_T_WEEKDAY.replace("date.getUTCDay()", "date.getDay()"), "logic", "getDay() uses the server's local zone while the rest of the file uses UTC; around midnight the weekday is wrong", ("getDay", "UTC", "local", "timezone")),
            Bad(_T_WEEKDAY.replace("dow === 0 || dow === 6", "dow === 6 || dow === 7"), "off-by-one", "getUTCDay() returns 0 for Sunday (never 7), so Sundays count as working days", ("Sunday", "0", "7", "getUTCDay")),
        ], note="adds `isWeekend()`"),
        Slot("between", "workingDays", _T_BETWEEN, [
            Bad(_T_BETWEEN.replace("t <= to.getTime()", "t < to.getTime()"), "off-by-one", "the end day is excluded although the range is inclusive", ("<", "<=", "inclusive", "end")),
            Bad(_T_BETWEEN.replace("let n = 0;", "let n = 1;"), "off-by-one", "the counter starts at 1, so every range has one working day too many (and an empty range returns 1)", ("n = 1", "start", "empty", "count")),
        ], note="adds `workingDays()`"),
        Slot("weekstart", "weekStart", _T_WEEKSTART, [
            Bad(_T_WEEKSTART.replace("(date.getUTCDay() + 6) % 7", "date.getUTCDay()"), "logic", "weeks start on Sunday: for a Sunday the result is the same day and for other days it is the Sunday before, instead of the Monday", ("Monday", "Sunday", "+ 6", "% 7")),
        ], note="adds `weekStart()` (Monday)"),
        Slot("round", "roundHours", _T_ROUND, [
            Bad(_T_ROUND.replace("Math.round(hours * 4) / 4", "Math.floor(hours * 4) / 4"), "logic", "rounds down to the quarter hour instead of to the nearest", ("floor", "round", "nearest")),
            Bad(_T_ROUND.replace("Math.round(hours * 4) / 4", "Math.round(hours * 4 / 4)"), "logic", "the operator precedence cancels the quarter-hour scaling, so hours are rounded to whole hours", ("precedence", "quarter", "whole")),
        ], note="adds `roundHours()`"),
        Slot("summary", "summarise", _T_SUMMARY, [
            Bad(_T_SUMMARY.replace("(a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0)", "(a, b) => a[1] - b[1]"), "logic", "the weeks are sorted by their total hours instead of by week", ("sort", "week", "hours", "comparator")),
            Bad(_T_SUMMARY.replace("totals.set(key, (totals.get(key) || 0) + e.hours);", "totals.set(key, e.hours);"), "logic", "each entry overwrites the week's total instead of adding to it", ("overwrite", "set", "add", "total")),
        ], note="adds `summarise()`: hours per week"),
    ],
)

MODULES = [CART, RUNNER, TIMESHEET]

from ._traps import apply_traps  # noqa: E402

apply_traps(MODULES)

for _m in MODULES:
    validate_module(_m)
