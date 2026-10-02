"""JavaScript bank modules: tramfare, hivecal, dateline, couponstack, chunkplan."""
from fx import dd

from ._bank import Bug
from ._jsbank import JMod, add

# --------------------------------------------------------------------------------------------------------- tramfare
add(JMod(
    key="tramfare", title="tramfare: tram fares with transfers",
    blurb="The city tram operator prices a day of taps with the `tramfare` library.", names=["fareFor", "dayTotal"],
    spec=dd('''
        # tramfare: fares, transfers and the daily cap

        Zones are the integers 1 to 4; a single fare costs 250, 350, 450 and 550 cents for zone 1 to 4. Anything else is a `RangeError`.

        ## `fareFor(zone) -> number`
        The single fare in cents for the zone.

        ## `dayTotal(taps) -> number`
        `taps` is an array of `{minute, zone}` in time order (a tap earlier than the one before it is a `RangeError`). The total in cents for the day:

        * A tap that is **not** inside an open window pays the full fare of its zone and *opens a window* starting at its minute, whose highest zone so far is
          that tap's zone.
        * A tap is inside the open window when `minute - windowStart <= 90` (90 minutes, inclusive).
        * Inside the window, a tap in the same or a lower zone than the window's highest zone is free; a tap in a higher zone pays only the difference between
          its fare and the fare of the window's highest zone, and raises the window's highest zone. The window's start does **not** move.
        * The total for the day never exceeds 1000 cents. No taps cost 0.
    '''),
    core=dd('''
        "use strict";

        const BASE = [250, 350, 450, 550];
        const CAP = 1000;
        const WINDOW = 90;

        function fareFor(zone) {
          if (!Number.isInteger(zone) || zone < 1 || zone > 4) throw new RangeError("zone must be 1 to 4");
          return BASE[zone - 1];
        }

        function dayTotal(taps) {
          let total = 0;
          let start = null;
          let top = 0;
          taps.forEach((tap, i) => {
            if (i > 0 && tap.minute < taps[i - 1].minute) throw new RangeError("taps must be in time order");
            const price = fareFor(tap.zone);
            const open = start !== null && tap.minute - start <= WINDOW;
            if (open && tap.zone <= top) return;
            if (open) {
              total += price - fareFor(top);
              top = tap.zone;
            } else {
              total += price;
              start = tap.minute;
              top = tap.zone;
            }
          });
          return Math.min(total, CAP);
        }

        module.exports = { fareFor, dayTotal };
    '''),
    visible=dd('''
        test("single fares", () => {
          assert.deepEqual([1, 2, 3, 4].map(lib.fareFor), [250, 350, 450, 550]);
        });

        test("a lone tap pays its fare", () => {
          assert.equal(lib.dayTotal([{ minute: 480, zone: 2 }]), 350);
        });

        test("a quick return in the same zone is free", () => {
          assert.equal(lib.dayTotal([{ minute: 480, zone: 2 }, { minute: 520, zone: 2 }]), 350);
        });
    '''),
    hidden=dd('''
        function oracle(taps) {
          const fares = { 1: 250, 2: 350, 3: 450, 4: 550 };
          let journey = null;
          let sum = 0;
          for (const t of taps) {
            if (journey && t.minute - journey.start <= 90) {
              if (t.zone > journey.top) {
                sum += fares[t.zone] - fares[journey.top];
                journey.top = t.zone;
              }
            } else {
              sum += fares[t.zone];
              journey = { start: t.minute, top: t.zone };
            }
          }
          return sum > 1000 ? 1000 : sum;
        }

        test("fares and range errors", () => {
          assert.deepEqual([1, 2, 3, 4].map(lib.fareFor), [250, 350, 450, 550]);
          for (const z of [0, 5, -1, 2.5, "2", null]) assert.throws(() => lib.fareFor(z), RangeError);
        });

        test("the 90 minute window is inclusive", () => {
          assert.equal(lib.dayTotal([{ minute: 0, zone: 1 }, { minute: 90, zone: 1 }]), 250);
          assert.equal(lib.dayTotal([{ minute: 0, zone: 1 }, { minute: 91, zone: 1 }]), 500);
        });

        test("upgrades pay only the difference and do not move the window", () => {
          assert.equal(lib.dayTotal([{ minute: 0, zone: 1 }, { minute: 30, zone: 3 }]), 450);
          assert.equal(lib.dayTotal([{ minute: 0, zone: 1 }, { minute: 60, zone: 3 }, { minute: 91, zone: 3 }]), 450 + 450);
          assert.equal(lib.dayTotal([{ minute: 0, zone: 2 }, { minute: 50, zone: 4 }, { minute: 85, zone: 1 }]), 550);
          assert.equal(lib.dayTotal([{ minute: 0, zone: 1 }, { minute: 10, zone: 2 }, { minute: 20, zone: 4 }]), 550);
        });

        test("lower or equal zones inside the window are free", () => {
          assert.equal(lib.dayTotal([{ minute: 0, zone: 4 }, { minute: 10, zone: 1 }, { minute: 20, zone: 4 }, { minute: 90, zone: 2 }]), 550);
        });

        test("daily cap", () => {
          const taps = [];
          for (let i = 0; i < 6; i++) taps.push({ minute: i * 200, zone: 3 });
          assert.equal(lib.dayTotal(taps), 1000);
          assert.equal(lib.dayTotal(taps.slice(0, 2)), 900);
          assert.equal(lib.dayTotal(taps.slice(0, 3)), 1000);
          assert.equal(lib.dayTotal([]), 0);
        });

        test("order and zones are validated", () => {
          assert.throws(() => lib.dayTotal([{ minute: 50, zone: 1 }, { minute: 40, zone: 1 }]), RangeError);
          assert.throws(() => lib.dayTotal([{ minute: 0, zone: 5 }]), RangeError);
          assert.equal(lib.dayTotal([{ minute: 5, zone: 1 }, { minute: 5, zone: 1 }]), 250);
        });

        test("random days match the model", () => {
          let seed = 12345;
          const rnd = (n) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };
          for (let k = 0; k < 400; k++) {
            const taps = [];
            let minute = rnd(300);
            for (let i = 0, n = rnd(9); i < n; i++) {
              taps.push({ minute, zone: 1 + rnd(4) });
              minute += [0, 1, 30, 89, 90, 91, 120, 200][rnd(8)];
            }
            assert.equal(lib.dayTotal(taps), oracle(taps), JSON.stringify(taps));
          }
        });
    '''),
    bugs=[
        Bug("window-edge", "tap.minute - start <= WINDOW", "tap.minute - start < WINDOW", ['dayTotal([{ minute: 0, zone: 1 }, { minute: 90, zone: 1 }])'], "dayTotal", "a tap exactly 90 minutes later starts a new journey"),
        Bug("upgrade-full", "total += price - fareFor(top);", "total += price;", ['dayTotal([{ minute: 0, zone: 1 }, { minute: 30, zone: 3 }])'], "dayTotal", "an upgrade pays the full fare of the new zone"),
        Bug("window-slides", "total += price - fareFor(top);\n      top = tap.zone;", "total += price - fareFor(top);\n      top = tap.zone;\n      start = tap.minute;",
            ['dayTotal([{ minute: 0, zone: 1 }, { minute: 60, zone: 3 }, { minute: 120, zone: 3 }])'], "dayTotal", "an upgrade restarts the 90 minute window"),
        Bug("cap-missing", "return Math.min(total, CAP);", "return total;", ['dayTotal([{ minute: 0, zone: 4 }, { minute: 200, zone: 4 }, { minute: 400, zone: 4 }])'], "dayTotal", "no daily cap"),
        Bug("cap-value", "const CAP = 1000;", "const CAP = 1100;", ['dayTotal([{ minute: 0, zone: 4 }, { minute: 200, zone: 4 }, { minute: 400, zone: 4 }])'], "dayTotal", "the daily cap is 1100"),
        Bug("order-unchecked", '    if (i > 0 && tap.minute < taps[i - 1].minute) throw new RangeError("taps must be in time order");\n', "",
            ['dayTotal([{ minute: 50, zone: 1 }, { minute: 40, zone: 1 }])'], "dayTotal", "taps out of order are accepted"),
        Bug("zone-range", "zone > 4", "zone > 5", ['dayTotal([{ minute: 0, zone: 5 }])'], "fareFor", "zone 5 is accepted and gives NaN"),
    ],
))

# ---------------------------------------------------------------------------------------------------------- hivecal
add(JMod(
    key="hivecal", title="hivecal: hive inspection calendar",
    blurb="The beekeeping club plans hive inspections with the `hivecal` library.", names=["monthOf", "season", "intervalDays", "schedule"],
    spec=dd('''
        # hivecal: when to inspect

        Days are numbered from 1 (1 January) in a calendar of **365 days** that repeats: day 366 is 1 January again. Month lengths are 31, 28, 31, 30, 31, 30,
        31, 31, 30, 31, 30, 31. A day that is not a positive integer is a `RangeError`.

        ## `monthOf(day) -> number`
        The month 1-12 of a day number.

        ## `season(month) -> string`
        `"spring"` for March and April, `"summer"` for May to July, `"autumn"` for August and September, `"winter"` otherwise.

        ## `intervalDays(month, colonies) -> number`
        Days between inspections for an apiary in that month: spring 14, summer 7, autumn 10, winter 30. Apiaries with **more than 20** colonies are inspected twice
        as often: half the interval, rounded **up**.

        ## `schedule(firstDay, lastDay, colonies) -> number[]`
        Inspection days from `firstDay` on: the first inspection is `firstDay`; after an inspection on day `d` the next one is `intervalDays(monthOf(d), colonies)`
        days later. Every day up to and including `lastDay` is listed. `firstDay > lastDay` gives an empty list.
    '''),
    core=dd('''
        "use strict";

        const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
        const BASE = { spring: 14, summer: 7, autumn: 10, winter: 30 };

        function monthOf(day) {
          if (!Number.isInteger(day) || day < 1) throw new RangeError("day must be a positive integer");
          let d = (day - 1) % 365;
          for (let m = 0; m < 12; m++) {
            if (d < MONTH_DAYS[m]) return m + 1;
            d -= MONTH_DAYS[m];
          }
          return 12;
        }

        function season(month) {
          if (month === 3 || month === 4) return "spring";
          if (month >= 5 && month <= 7) return "summer";
          if (month === 8 || month === 9) return "autumn";
          return "winter";
        }

        function intervalDays(month, colonies) {
          const base = BASE[season(month)];
          return colonies > 20 ? Math.ceil(base / 2) : base;
        }

        function schedule(firstDay, lastDay, colonies) {
          const out = [];
          let day = firstDay;
          while (day <= lastDay) {
            out.push(day);
            day += intervalDays(monthOf(day), colonies);
          }
          return out;
        }

        module.exports = { monthOf, season, intervalDays, schedule };
    '''),
    visible=dd('''
        test("month of a day", () => {
          assert.equal(lib.monthOf(1), 1);
          assert.equal(lib.monthOf(60), 3);
        });

        test("seasons", () => {
          assert.deepEqual([3, 6, 8, 12].map(lib.season), ["spring", "summer", "autumn", "winter"]);
        });

        test("a small apiary in spring", () => {
          assert.equal(lib.intervalDays(4, 5), 14);
        });
    '''),
    hidden=dd('''
        const LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

        function monthModel(day) {
          let d = day;
          while (d > 365) d -= 365;
          let m = 1;
          while (d > LENGTHS[m - 1]) { d -= LENGTHS[m - 1]; m++; }
          return m;
        }

        test("month boundaries", () => {
          const firsts = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
          firsts.forEach((d, i) => {
            assert.equal(lib.monthOf(d), i + 1, "first day of month " + (i + 1));
            assert.equal(lib.monthOf(d + (LENGTHS[i] - 1)), i + 1, "last day of month " + (i + 1));
          });
          assert.equal(lib.monthOf(365), 12);
          assert.equal(lib.monthOf(366), 1);
          assert.equal(lib.monthOf(730), 12);
          assert.equal(lib.monthOf(731), 1);
          for (const bad of [0, -3, 1.5, "7", NaN]) assert.throws(() => lib.monthOf(bad), RangeError);
        });

        test("seasons", () => {
          const want = ["winter", "winter", "spring", "spring", "summer", "summer", "summer", "autumn", "autumn", "winter", "winter", "winter"];
          want.forEach((s, i) => assert.equal(lib.season(i + 1), s));
        });

        test("intervals", () => {
          assert.equal(lib.intervalDays(3, 10), 14);
          assert.equal(lib.intervalDays(5, 10), 7);
          assert.equal(lib.intervalDays(9, 10), 10);
          assert.equal(lib.intervalDays(12, 10), 30);
          assert.equal(lib.intervalDays(3, 20), 14);
          assert.equal(lib.intervalDays(3, 21), 7);
          assert.equal(lib.intervalDays(5, 21), 4);
          assert.equal(lib.intervalDays(9, 21), 5);
          assert.equal(lib.intervalDays(1, 50), 15);
        });

        test("schedule, inclusive of the last day and across the year end", () => {
          assert.deepEqual(lib.schedule(10, 9, 5), []);
          assert.deepEqual(lib.schedule(10, 10, 5), [10]);
          assert.deepEqual(lib.schedule(1, 100, 5), [1, 31, 61, 75, 89]);
          assert.deepEqual(lib.schedule(150, 175, 5), [150, 157, 164, 171]);
          assert.deepEqual(lib.schedule(361, 400, 5), [361, 391]);
        });

        test("random schedules match the model", () => {
          let seed = 99;
          const rnd = (n) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };
          const base = { spring: 14, summer: 7, autumn: 10, winter: 30 };
          const seasonOf = (m) => (m === 3 || m === 4 ? "spring" : m >= 5 && m <= 7 ? "summer" : m === 8 || m === 9 ? "autumn" : "winter");
          for (let k = 0; k < 120; k++) {
            const first = 1 + rnd(700), last = first + rnd(300), colonies = rnd(40);
            const want = [];
            for (let d = first; d <= last; ) {
              want.push(d);
              const b = base[seasonOf(monthModel(d))];
              d += colonies > 20 ? Math.ceil(b / 2) : b;
            }
            assert.deepEqual(lib.schedule(first, last, colonies), want, [first, last, colonies].join(","));
          }
        });
    '''),
    bugs=[
        Bug("big-apiary-edge", "colonies > 20 ?", "colonies >= 20 ?", ["intervalDays(3, 20)"], "intervalDays", "twenty colonies already count as a big apiary"),
        Bug("half-floor", "Math.ceil(base / 2)", "Math.floor(base / 2)", ["intervalDays(6, 30)"], "intervalDays", "the halved interval is rounded down"),
        Bug("spring-short", 'if (month === 3 || month === 4) return "spring";', 'if (month === 3) return "spring";', ["season(4)"], "season", "April is not spring"),
        Bug("month-edge", "if (d < MONTH_DAYS[m]) return m + 1;", "if (d <= MONTH_DAYS[m]) return m + 1;", ["monthOf(32)"], "monthOf", "the first day of a month belongs to the previous month"),
        Bug("year-length", "(day - 1) % 365", "(day - 1) % 366", ["monthOf(366)"], "monthOf", "years are 366 days long"),
        Bug("last-day-excluded", "while (day <= lastDay) {", "while (day < lastDay) {", ["schedule(10, 10, 5)"], "schedule", "an inspection on the last day is dropped"),
    ],
))

# --------------------------------------------------------------------------------------------------------- dateline
add(JMod(
    key="dateline", title="dateline: business-day arithmetic",
    blurb="The shipping office computes delivery dates with the `dateline` library.", names=["isBusinessDay", "addBusinessDays", "businessDaysBetween"],
    spec=dd('''
        # dateline: business days

        Dates are ISO strings `YYYY-MM-DD` (a malformed or impossible date is a `RangeError`). Saturdays and Sundays are never business days; neither is any date in the
        `holidays` array (an array of ISO strings, default empty; a holiday that falls on a weekend changes nothing).

        ## `isBusinessDay(date, holidays = []) -> boolean`

        ## `addBusinessDays(date, n, holidays = []) -> string`
        The date `n` business days after `date` (before it for negative `n`). The start date itself is not counted and may be any day; `n = 0` returns `date` unchanged
        even if it is not a business day. Example: one business day after a Friday is the following Monday.

        ## `businessDaysBetween(from, to, holidays = []) -> number`
        The number of business days in the half-open range after `from` up to and including `to`. Equal dates give 0. If `to` is earlier than `from` the result is the
        negative of `businessDaysBetween(to, from, holidays)`.
    '''),
    core=dd('''
        "use strict";

        const DAY = 86400000;

        function parse(iso) {
          const m = /^(\\d{4})-(\\d{2})-(\\d{2})$/.exec(iso);
          if (!m) throw new RangeError("bad date " + iso);
          const t = Date.UTC(+m[1], +m[2] - 1, +m[3]);
          const d = new Date(t);
          if (d.getUTCMonth() !== +m[2] - 1 || d.getUTCDate() !== +m[3]) throw new RangeError("impossible date " + iso);
          return t;
        }

        function format(t) {
          return new Date(t).toISOString().slice(0, 10);
        }

        function isBusinessDay(iso, holidays = []) {
          const dow = new Date(parse(iso)).getUTCDay();
          return dow !== 0 && dow !== 6 && !holidays.includes(iso);
        }

        function addBusinessDays(iso, n, holidays = []) {
          let t = parse(iso);
          const step = n < 0 ? -1 : 1;
          let left = Math.abs(n);
          while (left > 0) {
            t += step * DAY;
            if (isBusinessDay(format(t), holidays)) left--;
          }
          return format(t);
        }

        function businessDaysBetween(a, b, holidays = []) {
          const ta = parse(a);
          const tb = parse(b);
          if (ta === tb) return 0;
          if (tb < ta) return -businessDaysBetween(b, a, holidays);
          let n = 0;
          for (let t = ta + DAY; t <= tb; t += DAY) if (isBusinessDay(format(t), holidays)) n++;
          return n;
        }

        module.exports = { isBusinessDay, addBusinessDays, businessDaysBetween };
    '''),
    visible=dd('''
        test("weekends are not business days", () => {
          assert.equal(lib.isBusinessDay("2024-03-02"), false);
          assert.equal(lib.isBusinessDay("2024-03-04"), true);
        });

        test("one business day after a friday", () => {
          assert.equal(lib.addBusinessDays("2024-03-01", 1), "2024-03-04");
        });

        test("days between", () => {
          assert.equal(lib.businessDaysBetween("2024-03-01", "2024-03-08"), 5);
        });
    '''),
    hidden=dd('''
        const DAY = 86400000;
        const iso = (t) => new Date(t).toISOString().slice(0, 10);
        const biz = (t, hol) => { const d = new Date(t).getUTCDay(); return d !== 0 && d !== 6 && !hol.includes(iso(t)); };

        test("business day predicate", () => {
          const hol = ["2024-03-05", "2024-03-09"];
          assert.equal(lib.isBusinessDay("2024-03-05", hol), false);
          assert.equal(lib.isBusinessDay("2024-03-05"), true);
          assert.equal(lib.isBusinessDay("2024-03-09", hol), false);
          assert.equal(lib.isBusinessDay("2024-03-10"), false);
          assert.equal(lib.isBusinessDay("2024-03-11", hol), true);
          for (const bad of ["2024-3-1", "2024-02-30", "20240301", "", "2023-02-29"]) assert.throws(() => lib.isBusinessDay(bad), RangeError);
          assert.equal(lib.isBusinessDay("2024-02-29"), true);
        });

        test("adding business days", () => {
          assert.equal(lib.addBusinessDays("2024-03-01", 1), "2024-03-04");
          assert.equal(lib.addBusinessDays("2024-03-01", 5), "2024-03-08");
          assert.equal(lib.addBusinessDays("2024-03-02", 1), "2024-03-04");
          assert.equal(lib.addBusinessDays("2024-03-02", 0), "2024-03-02");
          assert.equal(lib.addBusinessDays("2024-03-04", -1), "2024-03-01");
          assert.equal(lib.addBusinessDays("2024-03-03", -1), "2024-03-01");
          assert.equal(lib.addBusinessDays("2024-03-04", -6), "2024-02-23");
          assert.equal(lib.addBusinessDays("2024-02-28", 2), "2024-03-01");
        });

        test("holidays are skipped", () => {
          const hol = ["2024-03-04", "2024-03-05", "2024-03-09"];
          assert.equal(lib.addBusinessDays("2024-03-01", 1, hol), "2024-03-06");
          assert.equal(lib.addBusinessDays("2024-03-06", -1, hol), "2024-03-01");
          assert.equal(lib.addBusinessDays("2024-03-08", 1, ["2024-03-09"]), "2024-03-11");
        });

        test("days between", () => {
          assert.equal(lib.businessDaysBetween("2024-03-01", "2024-03-01"), 0);
          assert.equal(lib.businessDaysBetween("2024-03-01", "2024-03-04"), 1);
          assert.equal(lib.businessDaysBetween("2024-03-02", "2024-03-03"), 0);
          assert.equal(lib.businessDaysBetween("2024-03-04", "2024-03-01"), -1);
          assert.equal(lib.businessDaysBetween("2024-03-01", "2024-03-15", ["2024-03-06"]), 9);
          assert.equal(lib.businessDaysBetween("2024-03-15", "2024-03-01", ["2024-03-06"]), -9);
        });

        test("random dates match brute force", () => {
          let seed = 7;
          const rnd = (n) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };
          const t0 = Date.UTC(2024, 0, 1);
          for (let k = 0; k < 250; k++) {
            const hol = [];
            for (let h = 0, n = rnd(6); h < n; h++) hol.push(iso(t0 + rnd(120) * DAY));
            const a = t0 + rnd(100) * DAY, b = t0 + rnd(100) * DAY;
            let count = 0;
            const lo = Math.min(a, b), hi = Math.max(a, b);
            for (let t = lo + DAY; t <= hi; t += DAY) if (biz(t, hol)) count++;
            assert.equal(lib.businessDaysBetween(iso(a), iso(b), hol), b >= a ? count : -count);
            const n = rnd(21) - 10;
            let t = a, left = Math.abs(n);
            while (left > 0) { t += (n < 0 ? -1 : 1) * DAY; if (biz(t, hol)) left--; }
            assert.equal(lib.addBusinessDays(iso(a), n, hol), iso(t));
          }
        });
    '''),
    bugs=[
        Bug("weekend-saturday", "return dow !== 0 && dow !== 6 && !holidays.includes(iso);", "return dow !== 0 && !holidays.includes(iso);", ['isBusinessDay("2024-03-02")'], "isBusinessDay", "Saturday is a business day"),
        Bug("holidays-ignored", "return dow !== 0 && dow !== 6 && !holidays.includes(iso);", "return dow !== 0 && dow !== 6;", ['isBusinessDay("2024-03-05", ["2024-03-05"])'], "isBusinessDay", "holidays are not skipped"),
        Bug("negative-ignored", "const step = n < 0 ? -1 : 1;", "const step = 1;", ['addBusinessDays("2024-03-04", -1)'], "addBusinessDays", "negative n moves forward"),
        Bug("start-counted", "while (left > 0) {\n    t += step * DAY;\n    if (isBusinessDay(format(t), holidays)) left--;\n  }",
            "while (left > 0) {\n    if (isBusinessDay(format(t), holidays)) left--;\n    t += step * DAY;\n  }", ['addBusinessDays("2024-03-01", 1)'], "addBusinessDays", "the start date counts as the first day"),
        Bug("between-open-end", "for (let t = ta + DAY; t <= tb; t += DAY)", "for (let t = ta + DAY; t < tb; t += DAY)", ['businessDaysBetween("2024-03-01", "2024-03-04")'], "businessDaysBetween", "the end date is not counted"),
        Bug("between-sign", "return -businessDaysBetween(b, a, holidays);", "return businessDaysBetween(b, a, holidays);", ['businessDaysBetween("2024-03-04", "2024-03-01")'], "businessDaysBetween", "a reversed range is positive"),
        Bug("zero-moves", "let left = Math.abs(n);", "let left = Math.max(1, Math.abs(n));", ['addBusinessDays("2024-03-02", 0)'], "addBusinessDays", "n = 0 still moves to a business day"),
    ],
))

# ------------------------------------------------------------------------------------------------------ couponstack
add(JMod(
    key="couponstack", title="couponstack: stacking discount coupons",
    blurb="The web shop's checkout combines discount coupons with the `couponstack` library.", names=["applyCoupons"],
    spec=dd('''
        # couponstack: applying coupons to a cart

        ## `applyCoupons(cents, coupons) -> { total, applied }`
        `cents` is the cart value, a non-negative integer. A coupon is `{ code, kind, value, stackable }`: `kind` is `"percent"` (`value` an integer 0 to 100) or
        `"fixed"` (`value` a non-negative integer number of cents); `stackable` is true unless it is exactly `false`. Any other `kind` or a bad `value` in **any**
        coupon of the input is a `RangeError`, as is a bad `cents`.

        1. If at least one coupon is not stackable, it cannot be combined with anything: only the **first** non-stackable coupon of the list is used and every other
           coupon is ignored.
        2. Otherwise, or after that selection, the chosen coupons are applied in two passes: first all percent coupons in list order, each taking `round(total * value / 100)`
           off the running total (rounded half up to a whole cent), then all fixed coupons in list order, each taking `value` off (the total never goes below 0).
        3. `applied` lists the codes of the coupons that were used, percent coupons first, then fixed ones, each group in list order.

        Returns `{ total, applied }`.
    '''),
    core=dd('''
        "use strict";

        function roundHalfUp(n, d) {
          return Math.floor((2 * n + d) / (2 * d));
        }

        function applyCoupons(cents, coupons) {
          if (!Number.isInteger(cents) || cents < 0) throw new RangeError("cents must be a non-negative integer");
          for (const c of coupons) {
            const ok = Number.isInteger(c.value) && c.value >= 0 && (c.kind === "fixed" || (c.kind === "percent" && c.value <= 100));
            if (!ok) throw new RangeError("bad coupon " + c.code);
          }
          const solo = coupons.find((c) => c.stackable === false);
          const list = solo ? [solo] : coupons;
          let total = cents;
          const applied = [];
          for (const c of list.filter((x) => x.kind === "percent")) {
            total -= roundHalfUp(total * c.value, 100);
            applied.push(c.code);
          }
          for (const c of list.filter((x) => x.kind === "fixed")) {
            total = Math.max(0, total - c.value);
            applied.push(c.code);
          }
          return { total, applied };
        }

        module.exports = { applyCoupons };
    '''),
    visible=dd('''
        test("one percent coupon", () => {
          assert.deepEqual(lib.applyCoupons(2000, [{ code: "TEN", kind: "percent", value: 10 }]), { total: 1800, applied: ["TEN"] });
        });

        test("fixed coupon", () => {
          assert.deepEqual(lib.applyCoupons(500, [{ code: "FIVE", kind: "fixed", value: 500 }]), { total: 0, applied: ["FIVE"] });
        });

        test("bad cart value", () => {
          assert.throws(() => lib.applyCoupons(-1, []), RangeError);
        });
    '''),
    hidden=dd('''
        const P = (code, value, extra = {}) => ({ code, kind: "percent", value, ...extra });
        const F = (code, value, extra = {}) => ({ code, kind: "fixed", value, ...extra });

        function model(cents, coupons) {
          let chosen = coupons;
          for (const c of coupons) if (c.stackable === false) { chosen = [c]; break; }
          let total = cents;
          const applied = [];
          for (const c of chosen) if (c.kind === "percent") {
            const exact = total * c.value / 100;
            total -= Math.floor(exact + 0.5);
            applied.push(c.code);
          }
          for (const c of chosen) if (c.kind === "fixed") { total = Math.max(0, total - c.value); applied.push(c.code); }
          return { total, applied };
        }

        test("percent coupons compound in list order", () => {
          assert.deepEqual(lib.applyCoupons(10000, [P("A", 10), P("B", 20)]), { total: 7200, applied: ["A", "B"] });
          assert.deepEqual(lib.applyCoupons(999, [P("A", 50)]), { total: 499, applied: ["A"] });
          assert.deepEqual(lib.applyCoupons(1001, [P("A", 50)]), { total: 500, applied: ["A"] });
          assert.deepEqual(lib.applyCoupons(5, [P("A", 10)]), { total: 4, applied: ["A"] });  // 0.5 rounds up to 1
          assert.deepEqual(lib.applyCoupons(5, [P("A", 10), P("B", 10)]), { total: 4, applied: ["A", "B"] });  // then 0.4 rounds to 0
          assert.deepEqual(lib.applyCoupons(4, [P("A", 10)]), { total: 4, applied: ["A"] });
        });

        test("fixed coupons come after percent coupons whatever the list order", () => {
          assert.deepEqual(lib.applyCoupons(10000, [F("F", 1000), P("A", 10)]), { total: 8000, applied: ["A", "F"] });
          assert.deepEqual(lib.applyCoupons(1000, [F("F1", 700), F("F2", 700), P("A", 10)]), { total: 0, applied: ["A", "F1", "F2"] });
        });

        test("only the first non-stackable coupon is used", () => {
          const list = [P("A", 10), F("S1", 300, { stackable: false }), P("B", 50), F("S2", 900, { stackable: false })];
          assert.deepEqual(lib.applyCoupons(2000, list), { total: 1700, applied: ["S1"] });
          assert.deepEqual(lib.applyCoupons(2000, [P("A", 10, { stackable: true }), P("B", 10, { stackable: undefined })]), { total: 1620, applied: ["A", "B"] });
        });

        test("validation covers every coupon", () => {
          for (const bad of [{ code: "X", kind: "bogus", value: 1 }, P("X", 101), P("X", -1), F("X", 1.5), F("X", -5), P("X", "10")]) {
            assert.throws(() => lib.applyCoupons(100, [P("OK", 5), bad]), RangeError);
            assert.throws(() => lib.applyCoupons(100, [bad, F("S", 5, { stackable: false })]), RangeError);
          }
          for (const bad of [-1, 1.5, "100", null]) assert.throws(() => lib.applyCoupons(bad, []), RangeError);
          assert.deepEqual(lib.applyCoupons(0, []), { total: 0, applied: [] });
        });

        test("random carts match the model", () => {
          let seed = 31;
          const rnd = (n) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };
          for (let k = 0; k < 400; k++) {
            const list = [];
            for (let i = 0, n = rnd(6); i < n; i++) {
              const extra = rnd(5) === 0 ? { stackable: false } : {};
              list.push(rnd(2) ? P("p" + i, rnd(101), extra) : F("f" + i, rnd(900), extra));
            }
            const cents = rnd(30000);
            assert.deepEqual(lib.applyCoupons(cents, list), model(cents, list), JSON.stringify([cents, list]));
          }
        });
    '''),
    bugs=[
        Bug("solo-last", "const solo = coupons.find((c) => c.stackable === false);", "const solo = coupons.slice().reverse().find((c) => c.stackable === false);",
            ['applyCoupons(2000, [{ code: "S1", kind: "fixed", value: 300, stackable: false }, { code: "S2", kind: "fixed", value: 900, stackable: false }])'], "applyCoupons", "the last non-stackable coupon wins"),
        Bug("round-floor", "return Math.floor((2 * n + d) / (2 * d));", "return Math.floor(n / d);", ['applyCoupons(999, [{ code: "A", kind: "percent", value: 50 }])'], "roundHalfUp", "percentages round down"),
        Bug("negative-total", "total = Math.max(0, total - c.value);", "total -= c.value;", ['applyCoupons(100, [{ code: "F", kind: "fixed", value: 500 }])'], "applyCoupons", "the total can go negative"),
        Bug("stackable-default", 'c.stackable === false', 'c.stackable !== true', ['applyCoupons(2000, [{ code: "A", kind: "percent", value: 10 }, { code: "B", kind: "percent", value: 10 }])'], "applyCoupons", "coupons without the flag are not stackable"),
        Bug("percent-on-original", "total -= roundHalfUp(total * c.value, 100);", "total -= roundHalfUp(cents * c.value, 100);", ['applyCoupons(10000, [{ code: "A", kind: "percent", value: 10 }, { code: "B", kind: "percent", value: 20 }])'], "applyCoupons", "every percent coupon is taken from the original cart value"),
        Bug("percent-limit", "c.value <= 100", "c.value <= 1000", ['applyCoupons(100, [{ code: "X", kind: "percent", value: 150 }])'], "applyCoupons", "percentages above 100 are accepted"),
    ],
))

# ------------------------------------------------------------------------------------------------------- chunkplan
add(JMod(
    key="chunkplan", title="chunkplan: upload chunk planning",
    blurb="The file uploader splits big uploads into parts with the `chunkplan` library.", names=["plan"],
    spec=dd('''
        # chunkplan: how to cut an upload into parts

        ## `plan(size, opts = {}) -> Array<{ index, start, end }>`
        `size` is the file size in bytes (a non-negative integer, otherwise `RangeError`). Options (defaults in brackets): `min` (5 MiB), `maxChunks` (10000), `align` (1 MiB).

        1. A size of 0 gives `[]`.
        2. The chunk size is `max(min, ceil(size / maxChunks))`, then rounded **up** to a multiple of `align`.
        3. Chunks are consecutive, numbered from 0, covering `[start, end)` with `end` capped at `size`; every chunk but the last has exactly the chunk size.
        4. If there is more than one chunk and the last one is **smaller than `min`**, it is merged into the one before it (which then ends at `size`).
    '''),
    core=dd('''
        "use strict";

        const MiB = 1024 * 1024;

        function plan(size, opts = {}) {
          const min = opts.min ?? 5 * MiB;
          const maxChunks = opts.maxChunks ?? 10000;
          const align = opts.align ?? MiB;
          if (!Number.isInteger(size) || size < 0) throw new RangeError("size must be a non-negative integer");
          if (size === 0) return [];
          let chunk = Math.max(min, Math.ceil(size / maxChunks));
          chunk = Math.ceil(chunk / align) * align;
          const out = [];
          for (let start = 0, i = 0; start < size; start += chunk, i++) {
            out.push({ index: i, start, end: Math.min(size, start + chunk) });
          }
          if (out.length > 1 && out[out.length - 1].end - out[out.length - 1].start < min) {
            const last = out.pop();
            out[out.length - 1].end = last.end;
          }
          return out;
        }

        module.exports = { plan };
    '''),
    visible=dd('''
        const MiB = 1024 * 1024;

        test("a small file is one chunk", () => {
          assert.deepEqual(lib.plan(3 * MiB), [{ index: 0, start: 0, end: 3 * MiB }]);
        });

        test("two even chunks", () => {
          assert.equal(lib.plan(10 * MiB).length, 2);
        });

        test("empty", () => {
          assert.deepEqual(lib.plan(0), []);
        });
    '''),
    hidden=dd('''
        const MiB = 1024 * 1024;

        function model(size, o = {}) {
          const min = o.min ?? 5 * MiB, maxChunks = o.maxChunks ?? 10000, align = o.align ?? MiB;
          if (size === 0) return [];
          let c = Math.max(min, Math.ceil(size / maxChunks));
          while (c % align !== 0) c++;
          const cuts = [];
          for (let s = 0; s < size; s += c) cuts.push([s, Math.min(size, s + c)]);
          if (cuts.length > 1 && cuts[cuts.length - 1][1] - cuts[cuts.length - 1][0] < min) {
            const l = cuts.pop();
            cuts[cuts.length - 1][1] = l[1];
          }
          return cuts.map(([start, end], index) => ({ index, start, end }));
        }

        test("defaults", () => {
          assert.deepEqual(lib.plan(1), [{ index: 0, start: 0, end: 1 }]);
          assert.deepEqual(lib.plan(5 * MiB), [{ index: 0, start: 0, end: 5 * MiB }]);
          assert.deepEqual(lib.plan(12 * MiB), [{ index: 0, start: 0, end: 5 * MiB }, { index: 1, start: 5 * MiB, end: 10 * MiB }, { index: 2, start: 10 * MiB, end: 12 * MiB }].slice(0, 2).map((c, i) => (i === 1 ? { ...c, end: 12 * MiB } : c)));
          assert.deepEqual(lib.plan(15 * MiB).map((c) => c.end - c.start), [5 * MiB, 5 * MiB, 5 * MiB]);
          assert.deepEqual(lib.plan(10 * MiB + 1).map((c) => c.end - c.start), [5 * MiB, 5 * MiB + 1]);
        });

        test("a short last chunk is merged only when smaller than min", () => {
          assert.deepEqual(lib.plan(100, { min: 40, maxChunks: 10, align: 1 }).map((c) => [c.start, c.end]), [[0, 40], [40, 100]]);
          assert.deepEqual(lib.plan(120, { min: 40, maxChunks: 10, align: 1 }).map((c) => [c.start, c.end]), [[0, 40], [40, 80], [80, 120]]);
          assert.deepEqual(lib.plan(119, { min: 40, maxChunks: 10, align: 1 }).map((c) => [c.start, c.end]), [[0, 40], [40, 119]]);
          assert.deepEqual(lib.plan(41, { min: 40, maxChunks: 10, align: 1 }).map((c) => [c.start, c.end]), [[0, 41]]);
        });

        test("chunk size grows with the chunk limit and is aligned upwards", () => {
          assert.deepEqual(lib.plan(1000, { min: 10, maxChunks: 4, align: 1 }).map((c) => c.end - c.start), [250, 250, 250, 250]);
          assert.deepEqual(lib.plan(1000, { min: 10, maxChunks: 3, align: 1 }).map((c) => c.end - c.start), [334, 334, 332]);
          assert.deepEqual(lib.plan(1000, { min: 10, maxChunks: 4, align: 64 }).map((c) => c.end - c.start), [256, 256, 256, 232]);
          assert.deepEqual(lib.plan(1000, { min: 100, maxChunks: 100, align: 64 }).map((c) => c.end - c.start), [128, 128, 128, 128, 128, 128, 128, 104]);
        });

        test("errors and the empty file", () => {
          for (const bad of [-1, 1.5, "10", null, NaN]) assert.throws(() => lib.plan(bad), RangeError);
          assert.deepEqual(lib.plan(0), []);
          assert.deepEqual(lib.plan(0, { min: 1, maxChunks: 1, align: 1 }), []);
        });

        test("random plans match the model", () => {
          let seed = 5;
          const rnd = (n) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };
          for (let k = 0; k < 400; k++) {
            const opts = { min: 1 + rnd(60), maxChunks: 1 + rnd(30), align: [1, 8, 16, 100][rnd(4)] };
            const size = rnd(3000);
            assert.deepEqual(lib.plan(size, opts), model(size, opts), JSON.stringify([size, opts]));
          }
        });
    '''),
    bugs=[
        Bug("merge-edge", "end - out[out.length - 1].start < min", "end - out[out.length - 1].start <= min", ['plan(120, { min: 40, maxChunks: 10, align: 1 })'], "plan", "a last chunk exactly as big as min is merged"),
        Bug("align-down", "chunk = Math.ceil(chunk / align) * align;", "chunk = Math.floor(chunk / align) * align;", ['plan(1000, { min: 10, maxChunks: 4, align: 64 })'], "plan", "the chunk size is aligned downwards"),
        Bug("limit-floor", "Math.ceil(size / maxChunks)", "Math.floor(size / maxChunks)", ['plan(1000, { min: 10, maxChunks: 3, align: 1 })'], "plan", "more chunks than allowed"),
        Bug("end-uncapped", "end: Math.min(size, start + chunk)", "end: start + chunk", ['plan(25, { min: 5, maxChunks: 4, align: 1 })'], "plan", "the last chunk ends past the end of the file"),
        Bug("merge-missing", "if (out.length > 1 && out[out.length - 1].end - out[out.length - 1].start < min) {", "if (false) {", ['plan(100, { min: 40, maxChunks: 10, align: 1 })'], "plan", "short last chunks are never merged"),
        Bug("zero-size", "if (size === 0) return [];", "if (size === 0) return [{ index: 0, start: 0, end: 0 }];", ["plan(0)"], "plan", "an empty file gets an empty chunk"),
    ],
))
