"""Refuse-collection calendar with holiday shifts (typescript): bugs injected into recurrence rules and week-shifting."""
from fx import Lib, dd
from generators.fix._lang2 import PACKAGE_JSON, TS_NODE_SHIM, TS_VERIFY, TSCONFIG, register_libs

README = dd(r'''
    # haulcal

    The pick-up calendar of a town's refuse service: recurrence rules, public holidays that push the week's collections back, and
    cancelled rounds. TypeScript, no dependencies. `import { Calendar } from './src/calendar'`, `import { parseRule, occurrences }
    from './src/rule'`, `import { ... } from './src/date'`.

    All dates are plain `YYYY-MM-DD` strings (calendar days, no time zones). Weekdays are ISO numbers: 1 is Monday, 7 is Sunday.
    Weeks run Monday to Sunday.

    ## `src/date.ts`

    * `parseDate(text)`: `{ y, m, d }`. The text must be exactly four digits, `-`, two digits, `-`, two digits, a real calendar date
      with a year from 1900 to 2200, otherwise `Error`.
    * `formatDate({ y, m, d })`: the zero padded text.
    * `isLeap(y)`, `daysInMonth(y, m)`.
    * `toDays(text)` and `fromDays(n)`: the day number (0 is `1970-01-01`) and back.
    * `weekday(text)`: 1 to 7. `dayName(text)`: `Mon`, `Tue`, `Wed`, `Thu`, `Fri`, `Sat` or `Sun`.
    * `addDays(text, n)` (n may be negative) and `mondayOf(text)`, the Monday of the date's week.

    ## `src/rule.ts`

    `parseRule(text)` reads a rule (upper or lower case, any amount of white space between the words, `Error` for anything else):

    * `weekly tue`: every Tuesday. Days are `mon tue wed thu fri sat sun`.
    * `biweekly tue from 2024-01-02`: every second week on that weekday. Week 0 is the week that contains the anchor date; the rule
      fires in weeks 0, 2, 4 and so on, and never before the anchor date itself (if the weekday of the anchor week lies before the
      anchor, that day is skipped). The anchor must be a valid date.
    * `monthly 2nd tue`: the n-th weekday of the month; the counts are `1st`, `2nd`, `3rd`, `4th` and `last` (the last such weekday,
      which may be the fourth or the fifth).
    * `monthday 15`: the given day of the month, 1 to 31; in a shorter month it falls on the last day of that month.

    `occurrences(rule, from, to)` lists the dates of a parsed rule from `from` to `to`, both included, oldest first (empty when
    `from` is after `to`).

    ## `src/calendar.ts`

    `new Calendar(rules, holidays = [], cancelled = [])`: `rules` are rule texts (`Error` for a bad one, or when there are none),
    `holidays` and `cancelled` are dates (`Error` if invalid).

    A collection that the rules put on the date `c` (its *original* date) is handled in this order:

    1. **Cancelled**: if `c` is in `cancelled`, the collection does not happen at all.
    2. **Holiday shift**: only holidays from Monday to Friday count, and each date once. Let `k` be the number of holidays in the
       same week as `c` that fall on a weekday up to and including the weekday of `c` (a holiday on the same day as `c` counts).
       When `k > 0` the collection moves `k` days later; if that lands on a Sunday it moves one more day, to Monday. With `k = 0`
       nothing moves. Only the week of the original date is looked at, whatever the new date is.

    A `Pickup` is `{ date, original, rule }`: the final date, the original date and the rule text exactly as it was given.

    * `pickups(from, to)`: the pickups whose final `date` lies from `from` to `to` (both included), sorted by date and, for the same
      date, by the position of the rule in `rules`. A collection whose original date is outside the range still counts when it moved
      into the range.
    * `next(after)`: the first pickup with a date after `after` (not on it), or `null` if there is none in the next 400 days.
    * `isPickupDay(date)`: `true` when some pickup has that final date.
    * `describe(pickup)`: `Tue 2024-03-05 [weekly mon] (was Mon 2024-03-04)`: the day name and final date, the rule in brackets, and,
      only when the collection moved, ` (was ` followed by the original day name and date and `)`.
''')

DATE = dd(r'''
    export interface Ymd {
      y: number;
      m: number;
      d: number;
    }

    const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    const NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const DAY_MS = 86400000;

    export function isLeap(y: number): boolean {
      return (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
    }

    export function daysInMonth(y: number, m: number): number {
      return m === 2 && isLeap(y) ? 29 : MONTH_DAYS[m - 1];
    }

    function pad(n: number, width: number): string {
      return String(n).padStart(width, "0");
    }

    export function parseDate(text: string): Ymd {
      const found = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
      if (found === null) throw new Error(`bad date: ${text}`);
      const y = Number(found[1]);
      const m = Number(found[2]);
      const d = Number(found[3]);
      if (y < 1900 || y > 2200 || m < 1 || m > 12 || d < 1 || d > daysInMonth(y, m)) {
        throw new Error(`bad date: ${text}`);
      }
      return { y, m, d };
    }

    export function formatDate(v: Ymd): string {
      return `${pad(v.y, 4)}-${pad(v.m, 2)}-${pad(v.d, 2)}`;
    }

    export function toDays(text: string): number {
      const { y, m, d } = parseDate(text);
      return Math.round(Date.UTC(y, m - 1, d) / DAY_MS);
    }

    export function fromDays(n: number): string {
      const t = new Date(n * DAY_MS);
      return formatDate({ y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: t.getUTCDate() });
    }

    export function weekday(text: string): number {
      const w = new Date(toDays(text) * DAY_MS).getUTCDay();
      return w === 0 ? 7 : w;
    }

    export function dayName(text: string): string {
      return NAMES[weekday(text) - 1];
    }

    export function addDays(text: string, n: number): string {
      return fromDays(toDays(text) + n);
    }

    export function mondayOf(text: string): string {
      return addDays(text, 1 - weekday(text));
    }
''')

RULE = dd(r'''
    import { daysInMonth, fromDays, mondayOf, parseDate, toDays, weekday } from "./date";

    export type Rule =
      | { kind: "weekly"; day: number }
      | { kind: "biweekly"; day: number; anchor: string }
      | { kind: "monthly"; nth: number; day: number }
      | { kind: "monthday"; dom: number };

    const DAYS = new Map<string, number>([
      ["mon", 1],
      ["tue", 2],
      ["wed", 3],
      ["thu", 4],
      ["fri", 5],
      ["sat", 6],
      ["sun", 7],
    ]);

    const COUNTS = new Map<string, number>([
      ["1st", 1],
      ["2nd", 2],
      ["3rd", 3],
      ["4th", 4],
      ["last", -1],
    ]);

    export function parseRule(text: string): Rule {
      const words = text.trim().toLowerCase().split(/\s+/);
      const bad = (): Error => new Error(`bad rule: ${text}`);
      const dayOf = (w: string): number => {
        const v = DAYS.get(w);
        if (v === undefined) throw bad();
        return v;
      };
      switch (words[0]) {
        case "weekly":
          if (words.length !== 2) throw bad();
          return { kind: "weekly", day: dayOf(words[1]) };
        case "biweekly": {
          if (words.length !== 4 || words[2] !== "from") throw bad();
          parseDate(words[3]);
          return { kind: "biweekly", day: dayOf(words[1]), anchor: words[3] };
        }
        case "monthly": {
          if (words.length !== 3) throw bad();
          const nth = COUNTS.get(words[1]);
          if (nth === undefined) throw bad();
          return { kind: "monthly", nth, day: dayOf(words[2]) };
        }
        case "monthday": {
          if (words.length !== 2 || !/^\d{1,2}$/.test(words[1])) throw bad();
          const dom = Number(words[1]);
          if (dom < 1 || dom > 31) throw bad();
          return { kind: "monthday", dom };
        }
        default:
          throw bad();
      }
    }

    function fires(rule: Rule, date: string): boolean {
      const w = weekday(date);
      const { y, m, d } = parseDate(date);
      switch (rule.kind) {
        case "weekly":
          return w === rule.day;
        case "biweekly": {
          if (w !== rule.day || date < rule.anchor) return false;
          const weeks = (toDays(mondayOf(date)) - toDays(mondayOf(rule.anchor))) / 7;
          return weeks % 2 === 0;
        }
        case "monthly": {
          if (w !== rule.day) return false;
          if (rule.nth === -1) return d + 7 > daysInMonth(y, m);
          return Math.ceil(d / 7) === rule.nth;
        }
        case "monthday":
          return d === Math.min(rule.dom, daysInMonth(y, m));
      }
    }

    export function occurrences(rule: Rule, from: string, to: string): string[] {
      const out: string[] = [];
      const last = toDays(to);
      for (let n = toDays(from); n <= last; n++) {
        const date = fromDays(n);
        if (fires(rule, date)) out.push(date);
      }
      return out;
    }
''')

CALENDAR = dd(r'''
    import { addDays, dayName, mondayOf, parseDate, weekday } from "./date";
    import { Rule, occurrences, parseRule } from "./rule";

    export interface Pickup {
      date: string;
      original: string;
      rule: string;
    }

    export class Calendar {
      private readonly rules: { text: string; rule: Rule }[];
      private readonly holidays = new Set<string>();
      private readonly cancelled = new Set<string>();

      constructor(rules: string[], holidays: string[] = [], cancelled: string[] = []) {
        if (rules.length === 0) throw new Error("no rules");
        this.rules = rules.map((text) => ({ text, rule: parseRule(text) }));
        for (const h of holidays) {
          parseDate(h);
          if (weekday(h) <= 5) this.holidays.add(h);
        }
        for (const c of cancelled) {
          parseDate(c);
          this.cancelled.add(c);
        }
      }

      private moved(original: string): string {
        const monday = mondayOf(original);
        const w = weekday(original);
        let k = 0;
        for (let i = 0; i < w && i < 5; i++) {
          if (this.holidays.has(addDays(monday, i))) k++;
        }
        if (k === 0) return original;
        const date = addDays(original, k);
        return weekday(date) === 7 ? addDays(date, 1) : date;
      }

      pickups(from: string, to: string): Pickup[] {
        const found: { pickup: Pickup; index: number }[] = [];
        this.rules.forEach((entry, index) => {
          for (const original of occurrences(entry.rule, addDays(from, -7), to)) {
            if (this.cancelled.has(original)) continue;
            const date = this.moved(original);
            if (date >= from && date <= to) found.push({ pickup: { date, original, rule: entry.text }, index });
          }
        });
        found.sort((a, b) => (a.pickup.date < b.pickup.date ? -1 : a.pickup.date > b.pickup.date ? 1 : a.index - b.index));
        return found.map((f) => f.pickup);
      }

      next(after: string): Pickup | null {
        const list = this.pickups(addDays(after, 1), addDays(after, 400));
        return list.length > 0 ? list[0] : null;
      }

      isPickupDay(date: string): boolean {
        return this.pickups(date, date).length > 0;
      }

      describe(p: Pickup): string {
        const base = `${dayName(p.date)} ${p.date} [${p.rule}]`;
        return p.original === p.date ? base : `${base} (was ${dayName(p.original)} ${p.original})`;
      }
    }
''')

VISIBLE = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { Calendar } from "../src/calendar";

    test("weekly pickups", () => {
      const cal = new Calendar(["weekly mon"]);
      assert.deepEqual(cal.pickups("2024-03-01", "2024-03-12").map((p) => p.date), ["2024-03-04", "2024-03-11"]);
    });

    test("a holiday moves the collection one day", () => {
      const cal = new Calendar(["weekly mon"], ["2024-03-04"]);
      const list = cal.pickups("2024-03-01", "2024-03-12");
      assert.equal(list[0].date, "2024-03-05");
      assert.equal(list[0].original, "2024-03-04");
    });
''')

HIDDEN = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { Calendar, Pickup } from "../src/calendar";
    import { addDays, dayName, daysInMonth, formatDate, fromDays, isLeap, mondayOf, parseDate, toDays, weekday } from "../src/date";
    import { occurrences, parseRule } from "../src/rule";

    function show(list: Pickup[]): string {
      return list.map((p) => (p.date === p.original ? `${p.date}:${p.rule}` : `${p.date}<${p.original}:${p.rule}`)).join(" | ");
    }

    function check(rules: string[], holidays: string[], cancelled: string[], from: string, to: string, expected: string): void {
      const cal = new Calendar(rules, holidays, cancelled);
      assert.equal(show(cal.pickups(from, to)), expected);
    }

    function nextOf(rules: string[], holidays: string[], cancelled: string[], after: string, expected: string): void {
      const cal = new Calendar(rules, holidays, cancelled);
      const p = cal.next(after);
      assert.equal(p === null ? "null" : cal.describe(p), expected);
    }

    function pick(date: string): Pickup {
      return { date, original: date, rule: "x" };
    }

        test("parseDate", () => {
          assert.deepEqual(parseDate("2024-02-29"), { y: 2024, m: 2, d: 29 });
          assert.deepEqual(parseDate("1900-01-01"), { y: 1900, m: 1, d: 1 });
          assert.deepEqual(parseDate("2200-12-31"), { y: 2200, m: 12, d: 31 });
          assert.deepEqual(parseDate("2024-03-04"), { y: 2024, m: 3, d: 4 });
          assert.deepEqual(parseDate("2000-02-29"), { y: 2000, m: 2, d: 29 });
          assert.deepEqual(parseDate("1999-12-31"), { y: 1999, m: 12, d: 31 });
          assert.throws(() => parseDate(""), Error);
          assert.throws(() => parseDate("2024-3-04"), Error);
          assert.throws(() => parseDate("2024-03-4"), Error);
          assert.throws(() => parseDate("24-03-04"), Error);
          assert.throws(() => parseDate("2024/03/04"), Error);
          assert.throws(() => parseDate("2024-13-01"), Error);
          assert.throws(() => parseDate("2024-00-10"), Error);
          assert.throws(() => parseDate("2024-02-30"), Error);
          assert.throws(() => parseDate("2023-02-29"), Error);
          assert.throws(() => parseDate("2024-04-31"), Error);
          assert.throws(() => parseDate("2024-03-00"), Error);
          assert.throws(() => parseDate("2024-03-32"), Error);
          assert.throws(() => parseDate(" 2024-03-04"), Error);
          assert.throws(() => parseDate("2024-03-04 "), Error);
          assert.throws(() => parseDate("2024-03-04T00:00"), Error);
          assert.throws(() => parseDate("1899-12-31"), Error);
          assert.throws(() => parseDate("2201-01-01"), Error);
          assert.throws(() => parseDate("20240304"), Error);
          assert.throws(() => parseDate("2024-03-04x"), Error);
          assert.throws(() => parseDate("x2024-03-04"), Error);
          assert.throws(() => parseDate("2100-02-29"), Error);
        });

        test("formatDate pads", () => {
          assert.equal(formatDate({ y: 2024, m: 3, d: 4 }), "2024-03-04");
          assert.equal(formatDate({ y: 1900, m: 12, d: 31 }), "1900-12-31");
          assert.equal(formatDate({ y: 2200, m: 1, d: 10 }), "2200-01-10");
          assert.equal(formatDate({ y: 2024, m: 11, d: 5 }), "2024-11-05");
        });

        test("leap years and month lengths", () => {
          assert.equal(isLeap(2024), true);
          assert.equal(isLeap(2023), false);
          assert.equal(isLeap(1900), false);
          assert.equal(isLeap(2000), true);
          assert.equal(isLeap(2100), false);
          assert.equal(isLeap(2200), false);
          assert.equal(daysInMonth(2024, 2), 29);
          assert.equal(daysInMonth(2023, 2), 28);
          assert.equal(daysInMonth(1900, 2), 28);
          assert.equal(daysInMonth(2000, 2), 29);
          assert.equal(daysInMonth(2100, 2), 28);
          assert.equal(daysInMonth(2024, 1), 31);
          assert.equal(daysInMonth(2024, 4), 30);
          assert.equal(daysInMonth(2024, 6), 30);
          assert.equal(daysInMonth(2024, 9), 30);
          assert.equal(daysInMonth(2024, 11), 30);
          assert.equal(daysInMonth(2024, 12), 31);
          assert.equal(daysInMonth(2024, 7), 31);
          assert.equal(daysInMonth(2024, 8), 31);
          assert.equal(daysInMonth(2024, 3), 31);
          assert.equal(daysInMonth(2024, 5), 31);
          assert.equal(daysInMonth(2024, 10), 31);
        });

        test("day numbers", () => {
          assert.equal(toDays("1970-01-01"), 0);
          assert.equal(toDays("1970-01-02"), 1);
          assert.equal(toDays("1969-12-31"), -1);
          assert.equal(toDays("2000-02-29"), 11016);
          assert.equal(toDays("2024-03-04"), 19786);
          assert.equal(toDays("2024-01-01"), 19723);
          assert.equal(toDays("1900-01-01"), -25567);
          assert.equal(toDays("2200-12-31"), 84370);
          assert.equal(fromDays(0), "1970-01-01");
          assert.equal(fromDays(1), "1970-01-02");
          assert.equal(fromDays(-1), "1969-12-31");
          assert.equal(fromDays(11016), "2000-02-29");
          assert.equal(fromDays(19786), "2024-03-04");
          assert.equal(fromDays(19723), "2024-01-01");
          assert.equal(fromDays(-25567), "1900-01-01");
          assert.equal(fromDays(84370), "2200-12-31");
          assert.throws(() => toDays("2024-02-30"), Error);
        });

        test("weekday and day names", () => {
          assert.equal(weekday("2024-03-04"), 1);
          assert.equal(weekday("2024-03-05"), 2);
          assert.equal(weekday("2024-03-06"), 3);
          assert.equal(weekday("2024-03-07"), 4);
          assert.equal(weekday("2024-03-08"), 5);
          assert.equal(weekday("2024-03-09"), 6);
          assert.equal(weekday("2024-03-10"), 7);
          assert.equal(weekday("1970-01-01"), 4);
          assert.equal(weekday("2000-01-01"), 6);
          assert.equal(weekday("1900-01-01"), 1);
          assert.equal(weekday("2200-12-31"), 3);
          assert.equal(weekday("2024-02-29"), 4);
          assert.equal(dayName("2024-03-04"), "Mon");
          assert.equal(dayName("2024-03-05"), "Tue");
          assert.equal(dayName("2024-03-06"), "Wed");
          assert.equal(dayName("2024-03-07"), "Thu");
          assert.equal(dayName("2024-03-08"), "Fri");
          assert.equal(dayName("2024-03-09"), "Sat");
          assert.equal(dayName("2024-03-10"), "Sun");
          assert.equal(dayName("1970-01-01"), "Thu");
          assert.equal(dayName("2000-01-01"), "Sat");
          assert.equal(dayName("1900-01-01"), "Mon");
          assert.equal(dayName("2200-12-31"), "Wed");
          assert.equal(dayName("2024-02-29"), "Thu");
        });

        test("addDays and mondayOf", () => {
          assert.equal(addDays("2024-02-28", 1), "2024-02-29");
          assert.equal(addDays("2024-02-28", 2), "2024-03-01");
          assert.equal(addDays("2023-02-28", 1), "2023-03-01");
          assert.equal(addDays("2024-12-31", 1), "2025-01-01");
          assert.equal(addDays("2024-01-01", -1), "2023-12-31");
          assert.equal(addDays("2024-03-01", -1), "2024-02-29");
          assert.equal(addDays("2024-03-10", 0), "2024-03-10");
          assert.equal(addDays("2024-01-31", 30), "2024-03-01");
          assert.equal(addDays("2023-12-31", 366), "2024-12-31");
          assert.equal(addDays("2024-03-04", -400), "2023-01-29");
          assert.equal(addDays("2000-03-01", -1), "2000-02-29");
          assert.equal(addDays("1900-03-01", -1), "1900-02-28");
          assert.equal(mondayOf("2024-03-04"), "2024-03-04");
          assert.equal(mondayOf("2024-03-05"), "2024-03-04");
          assert.equal(mondayOf("2024-03-10"), "2024-03-04");
          assert.equal(mondayOf("2024-03-11"), "2024-03-11");
          assert.equal(mondayOf("2024-01-01"), "2024-01-01");
          assert.equal(mondayOf("2024-01-07"), "2024-01-01");
          assert.equal(mondayOf("2023-01-01"), "2022-12-26");
          assert.equal(mondayOf("2024-03-01"), "2024-02-26");
          assert.equal(mondayOf("2000-01-02"), "1999-12-27");
        });

        test("parseRule reads the four kinds", () => {
          assert.deepEqual(parseRule("weekly tue"), { kind: "weekly", day: 2 });
          assert.deepEqual(parseRule("  WEEKLY   Sun "), { kind: "weekly", day: 7 });
          assert.deepEqual(parseRule("weekly mon"), { kind: "weekly", day: 1 });
          assert.deepEqual(parseRule("weekly sat"), { kind: "weekly", day: 6 });
          assert.deepEqual(parseRule("biweekly Thu from 2024-01-04"), { kind: "biweekly", day: 4, anchor: "2024-01-04" });
          assert.deepEqual(parseRule("biweekly fri   FROM  2024-02-29"), { kind: "biweekly", day: 5, anchor: "2024-02-29" });
          assert.deepEqual(parseRule("monthly 1st mon"), { kind: "monthly", nth: 1, day: 1 });
          assert.deepEqual(parseRule("monthly 2nd wed"), { kind: "monthly", nth: 2, day: 3 });
          assert.deepEqual(parseRule("monthly 3rd fri"), { kind: "monthly", nth: 3, day: 5 });
          assert.deepEqual(parseRule("monthly 4th sun"), { kind: "monthly", nth: 4, day: 7 });
          assert.deepEqual(parseRule("Monthly LAST thu"), { kind: "monthly", nth: -1, day: 4 });
          assert.deepEqual(parseRule("monthday 15"), { kind: "monthday", dom: 15 });
          assert.deepEqual(parseRule("monthday 31"), { kind: "monthday", dom: 31 });
          assert.deepEqual(parseRule("monthday 1"), { kind: "monthday", dom: 1 });
        });

        test("parseRule rejects other text", () => {
          assert.throws(() => parseRule(""), Error);
          assert.throws(() => parseRule("weekly"), Error);
          assert.throws(() => parseRule("weekly tue wed"), Error);
          assert.throws(() => parseRule("weekly tuesday"), Error);
          assert.throws(() => parseRule("weekly 2"), Error);
          assert.throws(() => parseRule("every tue"), Error);
          assert.throws(() => parseRule("biweekly tue"), Error);
          assert.throws(() => parseRule("biweekly tue from"), Error);
          assert.throws(() => parseRule("biweekly tue since 2024-01-02"), Error);
          assert.throws(() => parseRule("biweekly tue from 2024-02-30"), Error);
          assert.throws(() => parseRule("biweekly xyz from 2024-01-02"), Error);
          assert.throws(() => parseRule("biweekly tue from 2024-01-02 now"), Error);
          assert.throws(() => parseRule("monthly 5th mon"), Error);
          assert.throws(() => parseRule("monthly 0th mon"), Error);
          assert.throws(() => parseRule("monthly mon"), Error);
          assert.throws(() => parseRule("monthly first mon"), Error);
          assert.throws(() => parseRule("monthly 2nd"), Error);
          assert.throws(() => parseRule("monthly 2nd mon tue"), Error);
          assert.throws(() => parseRule("monthday"), Error);
          assert.throws(() => parseRule("monthday 0"), Error);
          assert.throws(() => parseRule("monthday 32"), Error);
          assert.throws(() => parseRule("monthday 100"), Error);
          assert.throws(() => parseRule("monthday 1x"), Error);
          assert.throws(() => parseRule("monthday -1"), Error);
          assert.throws(() => parseRule("monthday 3 4"), Error);
          assert.throws(() => parseRule("monthday last"), Error);
          assert.throws(() => parseRule("constructor"), Error);
          assert.throws(() => parseRule("weekly constructor"), Error);
          assert.throws(() => parseRule("monthly constructor mon"), Error);
        });

        test("occurrences", () => {
          assert.deepEqual(occurrences(parseRule("weekly tue"), "2024-03-01", "2024-03-31"), ["2024-03-05", "2024-03-12", "2024-03-19", "2024-03-26"]);
          assert.deepEqual(occurrences(parseRule("weekly sun"), "2024-02-26", "2024-03-10"), ["2024-03-03", "2024-03-10"]);
          assert.deepEqual(occurrences(parseRule("weekly mon"), "2024-03-04", "2024-03-04"), ["2024-03-04"]);
          assert.deepEqual(occurrences(parseRule("weekly mon"), "2024-03-05", "2024-03-10"), []);
          assert.deepEqual(occurrences(parseRule("weekly wed"), "2024-03-10", "2024-03-01"), []);
          assert.deepEqual(occurrences(parseRule("weekly fri"), "2023-12-25", "2024-01-08"), ["2023-12-29", "2024-01-05"]);
          assert.deepEqual(occurrences(parseRule("biweekly tue from 2024-01-02"), "2024-01-01", "2024-03-15"), ["2024-01-02", "2024-01-16", "2024-01-30", "2024-02-13", "2024-02-27", "2024-03-12"]);
          assert.deepEqual(occurrences(parseRule("biweekly mon from 2024-01-03"), "2024-01-01", "2024-03-15"), ["2024-01-15", "2024-01-29", "2024-02-12", "2024-02-26", "2024-03-11"]);
          assert.deepEqual(occurrences(parseRule("biweekly thu from 2024-01-03"), "2024-01-01", "2024-02-29"), ["2024-01-04", "2024-01-18", "2024-02-01", "2024-02-15", "2024-02-29"]);
          assert.deepEqual(occurrences(parseRule("biweekly sun from 2024-02-25"), "2024-02-20", "2024-04-01"), ["2024-02-25", "2024-03-10", "2024-03-24"]);
          assert.deepEqual(occurrences(parseRule("biweekly fri from 2023-12-29"), "2023-12-20", "2024-02-02"), ["2023-12-29", "2024-01-12", "2024-01-26"]);
          assert.deepEqual(occurrences(parseRule("monthly 1st mon"), "2024-01-01", "2024-06-30"), ["2024-01-01", "2024-02-05", "2024-03-04", "2024-04-01", "2024-05-06", "2024-06-03"]);
          assert.deepEqual(occurrences(parseRule("monthly 2nd tue"), "2024-01-01", "2024-06-30"), ["2024-01-09", "2024-02-13", "2024-03-12", "2024-04-09", "2024-05-14", "2024-06-11"]);
          assert.deepEqual(occurrences(parseRule("monthly 3rd wed"), "2024-02-01", "2024-04-30"), ["2024-02-21", "2024-03-20", "2024-04-17"]);
          assert.deepEqual(occurrences(parseRule("monthly 4th thu"), "2024-01-01", "2024-03-31"), ["2024-01-25", "2024-02-22", "2024-03-28"]);
          assert.deepEqual(occurrences(parseRule("monthly last fri"), "2024-01-01", "2024-06-30"), ["2024-01-26", "2024-02-23", "2024-03-29", "2024-04-26", "2024-05-31", "2024-06-28"]);
          assert.deepEqual(occurrences(parseRule("monthly last sat"), "2024-02-01", "2024-03-31"), ["2024-02-24", "2024-03-30"]);
          assert.deepEqual(occurrences(parseRule("monthly last thu"), "2023-11-01", "2024-02-29"), ["2023-11-30", "2023-12-28", "2024-01-25", "2024-02-29"]);
          assert.deepEqual(occurrences(parseRule("monthly 1st sun"), "2024-09-01", "2024-12-31"), ["2024-09-01", "2024-10-06", "2024-11-03", "2024-12-01"]);
          assert.deepEqual(occurrences(parseRule("monthday 15"), "2024-01-01", "2024-04-30"), ["2024-01-15", "2024-02-15", "2024-03-15", "2024-04-15"]);
          assert.deepEqual(occurrences(parseRule("monthday 31"), "2024-01-01", "2024-06-30"), ["2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30", "2024-05-31", "2024-06-30"]);
          assert.deepEqual(occurrences(parseRule("monthday 30"), "2024-01-01", "2024-03-31"), ["2024-01-30", "2024-02-29", "2024-03-30"]);
          assert.deepEqual(occurrences(parseRule("monthday 29"), "2023-02-01", "2024-03-31"), ["2023-02-28", "2023-03-29", "2023-04-29", "2023-05-29", "2023-06-29", "2023-07-29", "2023-08-29", "2023-09-29", "2023-10-29", "2023-11-29", "2023-12-29", "2024-01-29", "2024-02-29", "2024-03-29"]);
          assert.deepEqual(occurrences(parseRule("monthday 1"), "2023-12-31", "2024-01-02"), ["2024-01-01"]);
        });

        test("calendar construction", () => {
          assert.throws(() => new Calendar([]), Error);
          assert.throws(() => new Calendar(["weekly nope"]), Error);
          assert.throws(() => new Calendar(["weekly mon", "bad"]), Error);
          assert.throws(() => new Calendar(["weekly mon"], ["2024-02-30"]), Error);
          assert.throws(() => new Calendar(["weekly mon"], [], ["tomorrow"]), Error);
          assert.throws(() => new Calendar(["weekly mon"], [""]), Error);
          assert.doesNotThrow(() => new Calendar(["weekly mon"], ["2024-03-04"], ["2024-03-11"]));
          assert.doesNotThrow(() => new Calendar(["weekly mon"]));
        });

        test("rules without holidays", () => {
          check(["weekly mon"], [], [], "2024-03-01", "2024-03-31",
                "2024-03-04:weekly mon | 2024-03-11:weekly mon | 2024-03-18:weekly mon | 2024-03-25:weekly mon");
          check(["weekly mon", "weekly thu"], [], [], "2024-03-04", "2024-03-10",
                "2024-03-04:weekly mon | 2024-03-07:weekly thu");
          check(["weekly mon", "monthly 1st mon"], [], [], "2024-03-01", "2024-03-20",
                "2024-03-04:weekly mon | 2024-03-04:monthly 1st mon | 2024-03-11:weekly mon | 2024-03-18:weekly mon");
          check(["Weekly  TUE", " monthday   5 "], [], [], "2024-03-01", "2024-03-12",
                "2024-03-05:Weekly  TUE | 2024-03-05: monthday   5  | 2024-03-12:Weekly  TUE");
        });

        test("a holiday pushes the rest of its week back", () => {
          check(["weekly mon", "weekly tue", "weekly wed", "weekly thu", "weekly fri"], ["2024-03-06"], [], "2024-03-04", "2024-03-10",
                "2024-03-04:weekly mon | 2024-03-05:weekly tue | 2024-03-07<2024-03-06:weekly wed | 2024-03-08<2024-03-07:weekly thu | 2024-03-09<2024-03-08:weekly fri");
          check(["weekly mon", "weekly tue", "weekly wed", "weekly thu", "weekly fri"], ["2024-03-04"], [], "2024-03-04", "2024-03-10",
                "2024-03-05<2024-03-04:weekly mon | 2024-03-06<2024-03-05:weekly tue | 2024-03-07<2024-03-06:weekly wed | 2024-03-08<2024-03-07:weekly thu | 2024-03-09<2024-03-08:weekly fri");
          check(["weekly mon", "weekly tue", "weekly wed", "weekly thu", "weekly fri"], ["2024-03-08"], [], "2024-03-04", "2024-03-10",
                "2024-03-04:weekly mon | 2024-03-05:weekly tue | 2024-03-06:weekly wed | 2024-03-07:weekly thu | 2024-03-09<2024-03-08:weekly fri");
          check(["weekly wed"], ["2024-03-06"], [], "2024-03-01", "2024-03-31",
                "2024-03-07<2024-03-06:weekly wed | 2024-03-13:weekly wed | 2024-03-20:weekly wed | 2024-03-27:weekly wed");
          check(["weekly wed"], ["2024-03-07"], [], "2024-03-01", "2024-03-31",
                "2024-03-06:weekly wed | 2024-03-13:weekly wed | 2024-03-20:weekly wed | 2024-03-27:weekly wed");
          check(["weekly thu"], ["2024-03-05"], [], "2024-03-01", "2024-03-15",
                "2024-03-08<2024-03-07:weekly thu | 2024-03-14:weekly thu");
          check(["weekly fri"], ["2024-03-04"], [], "2024-03-01", "2024-03-15",
                "2024-03-01:weekly fri | 2024-03-09<2024-03-08:weekly fri | 2024-03-15:weekly fri");
          check(["weekly fri"], ["2024-03-04", "2024-03-05"], [], "2024-03-01", "2024-03-15",
                "2024-03-01:weekly fri | 2024-03-11<2024-03-08:weekly fri | 2024-03-15:weekly fri");
          check(["weekly fri"], ["2024-03-04", "2024-03-05", "2024-03-06"], [], "2024-03-01", "2024-03-15",
                "2024-03-01:weekly fri | 2024-03-11<2024-03-08:weekly fri | 2024-03-15:weekly fri");
          check(["weekly fri"], ["2024-03-08"], [], "2024-03-01", "2024-03-15",
                "2024-03-01:weekly fri | 2024-03-09<2024-03-08:weekly fri | 2024-03-15:weekly fri");
          check(["weekly thu"], ["2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07"], [], "2024-03-01", "2024-03-15",
                "2024-03-11<2024-03-07:weekly thu | 2024-03-14:weekly thu");
        });

        test("weekend collections and weekend holidays", () => {
          check(["weekly sat"], ["2024-03-04"], [], "2024-03-01", "2024-03-20",
                "2024-03-02:weekly sat | 2024-03-11<2024-03-09:weekly sat | 2024-03-16:weekly sat");
          check(["weekly sat"], ["2024-03-04", "2024-03-07"], [], "2024-03-01", "2024-03-20",
                "2024-03-02:weekly sat | 2024-03-11<2024-03-09:weekly sat | 2024-03-16:weekly sat");
          check(["weekly sun"], ["2024-03-04"], [], "2024-03-01", "2024-03-20",
                "2024-03-03:weekly sun | 2024-03-11<2024-03-10:weekly sun | 2024-03-17:weekly sun");
          check(["weekly sun"], ["2024-03-04", "2024-03-05"], [], "2024-03-01", "2024-03-20",
                "2024-03-03:weekly sun | 2024-03-12<2024-03-10:weekly sun | 2024-03-17:weekly sun");
          check(["weekly sun", "weekly mon"], ["2024-03-09", "2024-03-10"], [], "2024-03-01", "2024-03-20",
                "2024-03-03:weekly sun | 2024-03-04:weekly mon | 2024-03-10:weekly sun | 2024-03-11:weekly mon | 2024-03-17:weekly sun | 2024-03-18:weekly mon");
          check(["weekly fri"], ["2024-03-09", "2024-03-10", "2024-03-09"], [], "2024-03-01", "2024-03-20",
                "2024-03-01:weekly fri | 2024-03-08:weekly fri | 2024-03-15:weekly fri");
          check(["weekly fri"], ["2024-03-06", "2024-03-06"], [], "2024-03-01", "2024-03-20",
                "2024-03-01:weekly fri | 2024-03-09<2024-03-08:weekly fri | 2024-03-15:weekly fri");
        });

        test("the range applies to the final date", () => {
          check(["weekly fri"], ["2024-03-04"], [], "2024-03-09", "2024-03-12",
                "2024-03-09<2024-03-08:weekly fri");
          check(["weekly fri"], ["2024-03-04"], [], "2024-03-08", "2024-03-08",
                "");
          check(["weekly fri"], ["2024-03-04"], [], "2024-03-10", "2024-03-10",
                "");
          check(["weekly fri"], ["2024-03-04", "2024-03-05"], [], "2024-03-10", "2024-03-11",
                "2024-03-11<2024-03-08:weekly fri");
          check(["weekly fri"], ["2024-03-04", "2024-03-05"], [], "2024-03-11", "2024-03-11",
                "2024-03-11<2024-03-08:weekly fri");
          check(["weekly fri"], ["2024-03-04", "2024-03-05"], [], "2024-03-12", "2024-03-20",
                "2024-03-15:weekly fri");
          check(["weekly mon"], ["2024-03-04"], [], "2024-03-04", "2024-03-04",
                "");
          check(["weekly mon"], ["2024-03-04"], [], "2024-03-05", "2024-03-05",
                "2024-03-05<2024-03-04:weekly mon");
          check(["weekly tue"], ["2024-03-05"], [], "2024-03-05", "2024-03-05",
                "");
          check(["weekly tue"], ["2024-03-05"], [], "2024-03-06", "2024-03-06",
                "2024-03-06<2024-03-05:weekly tue");
          check(["weekly sat"], ["2024-03-04"], [], "2024-03-11", "2024-03-11",
                "2024-03-11<2024-03-09:weekly sat");
          check(["weekly fri"], ["2024-12-30", "2024-12-31", "2025-01-01"], [], "2024-12-27", "2025-01-15",
                "2024-12-27:weekly fri | 2025-01-06<2025-01-03:weekly fri | 2025-01-10:weekly fri");
          check(["weekly mon"], [], [], "2024-03-05", "2024-03-04",
                "");
        });

        test("cancelled collections", () => {
          check(["weekly mon"], [], ["2024-03-11"], "2024-03-01", "2024-03-31",
                "2024-03-04:weekly mon | 2024-03-18:weekly mon | 2024-03-25:weekly mon");
          check(["weekly mon"], ["2024-03-11"], ["2024-03-11"], "2024-03-01", "2024-03-31",
                "2024-03-04:weekly mon | 2024-03-18:weekly mon | 2024-03-25:weekly mon");
          check(["weekly tue"], ["2024-03-11"], ["2024-03-12"], "2024-03-01", "2024-03-31",
                "2024-03-05:weekly tue | 2024-03-19:weekly tue | 2024-03-26:weekly tue");
          check(["weekly fri"], ["2024-03-11"], ["2024-03-15"], "2024-03-08", "2024-03-20",
                "2024-03-08:weekly fri");
          check(["weekly fri"], ["2024-03-11"], ["2024-03-16"], "2024-03-08", "2024-03-20",
                "2024-03-08:weekly fri | 2024-03-16<2024-03-15:weekly fri");
          check(["weekly fri", "weekly sat"], [], ["2024-03-08", "2024-03-09"], "2024-03-01", "2024-03-20",
                "2024-03-01:weekly fri | 2024-03-02:weekly sat | 2024-03-15:weekly fri | 2024-03-16:weekly sat");
          check(["weekly mon", "weekly wed"], ["2024-03-05"], ["2024-03-06"], "2024-03-04", "2024-03-10",
                "2024-03-04:weekly mon");
          check(["weekly mon", "weekly wed"], ["2024-03-05"], ["2024-03-04"], "2024-03-04", "2024-03-10",
                "2024-03-07<2024-03-06:weekly wed");
        });

        test("ties between rules", () => {
          check(["weekly mon", "monthly 1st mon", "monthday 4"], [], [], "2024-03-01", "2024-03-10",
                "2024-03-04:weekly mon | 2024-03-04:monthly 1st mon | 2024-03-04:monthday 4");
          check(["monthday 4", "weekly mon"], [], [], "2024-03-01", "2024-03-10",
                "2024-03-04:monthday 4 | 2024-03-04:weekly mon");
          check(["weekly thu", "weekly wed"], ["2024-03-05"], [], "2024-03-04", "2024-03-10",
                "2024-03-07<2024-03-06:weekly wed | 2024-03-08<2024-03-07:weekly thu");
          check(["weekly tue", "weekly wed"], ["2024-03-04"], [], "2024-03-04", "2024-03-10",
                "2024-03-06<2024-03-05:weekly tue | 2024-03-07<2024-03-06:weekly wed");
          check(["weekly wed", "weekly tue"], ["2024-03-04"], [], "2024-03-04", "2024-03-10",
                "2024-03-06<2024-03-05:weekly tue | 2024-03-07<2024-03-06:weekly wed");
          check(["weekly mon", "weekly mon"], [], [], "2024-03-04", "2024-03-04",
                "2024-03-04:weekly mon | 2024-03-04:weekly mon");
        });

        test("next", () => {
          nextOf(["weekly mon"], [], [], "2024-03-04", "Mon 2024-03-11 [weekly mon]");
          nextOf(["weekly mon"], [], [], "2024-03-03", "Mon 2024-03-04 [weekly mon]");
          nextOf(["weekly mon"], [], [], "2024-03-05", "Mon 2024-03-11 [weekly mon]");
          nextOf(["weekly fri"], ["2024-03-04"], [], "2024-03-07", "Sat 2024-03-09 [weekly fri] (was Fri 2024-03-08)");
          nextOf(["weekly fri"], ["2024-03-04"], [], "2024-03-08", "Sat 2024-03-09 [weekly fri] (was Fri 2024-03-08)");
          nextOf(["weekly fri"], ["2024-03-04"], [], "2024-03-09", "Fri 2024-03-15 [weekly fri]");
          nextOf(["weekly fri"], ["2024-03-04"], [], "2024-03-10", "Fri 2024-03-15 [weekly fri]");
          nextOf(["monthday 31"], [], [], "2024-04-01", "Tue 2024-04-30 [monthday 31]");
          nextOf(["monthly last fri"], [], [], "2024-12-31", "Fri 2025-01-31 [monthly last fri]");
          nextOf(["biweekly tue from 2024-03-05"], [], [], "2024-03-05", "Tue 2024-03-19 [biweekly tue from 2024-03-05]");
          nextOf(["weekly wed"], ["2024-03-06"], ["2024-03-07"], "2024-03-05", "Thu 2024-03-07 [weekly wed] (was Wed 2024-03-06)");
          nextOf(["monthday 15"], [], ["2024-01-15", "2024-02-15", "2024-03-15", "2024-04-15", "2024-05-15", "2024-06-15", "2024-07-15", "2024-08-15", "2024-09-15", "2024-10-15", "2024-11-15", "2024-12-15", "2025-01-15", "2025-02-15"], "2024-01-01", "null");
          nextOf(["monthday 15"], [], ["2024-01-15", "2024-02-15", "2024-03-15", "2024-04-15", "2024-05-15", "2024-06-15", "2024-07-15", "2024-08-15", "2024-09-15", "2024-10-15", "2024-11-15", "2024-12-15", "2025-01-15"], "2024-01-01", "null");
          nextOf(["monthday 15"], [], ["2024-01-15"], "2024-01-14", "Thu 2024-02-15 [monthday 15]");
          nextOf(["monthday 4"], [], ["2024-01-04", "2024-02-04", "2024-03-04", "2024-04-04", "2024-05-04", "2024-06-04", "2024-07-04", "2024-08-04", "2024-09-04", "2024-10-04", "2024-11-04", "2024-12-04", "2025-01-04"], "2024-01-01", "Tue 2025-02-04 [monthday 4]");
          nextOf(["monthday 4"], [], ["2024-01-04", "2024-02-04", "2024-03-04", "2024-04-04", "2024-05-04", "2024-06-04", "2024-07-04", "2024-08-04", "2024-09-04", "2024-10-04", "2024-11-04", "2024-12-04", "2025-01-04"], "2023-12-31", "null");
        });

        test("isPickupDay", () => {
          const cal = new Calendar(["weekly wed"], ["2024-03-04"], ["2024-03-20"]);
          assert.equal(cal.isPickupDay("2024-03-05"), false);
          assert.equal(cal.isPickupDay("2024-03-06"), false);
          assert.equal(cal.isPickupDay("2024-03-07"), true);
          assert.equal(cal.isPickupDay("2024-03-13"), true);
          assert.equal(cal.isPickupDay("2024-03-14"), false);
          assert.equal(cal.isPickupDay("2024-03-20"), false);
          assert.equal(cal.isPickupDay("2024-03-21"), false);
          assert.equal(cal.isPickupDay("2024-03-10"), false);
        });

        test("describe", () => {
          const cal = new Calendar(["weekly mon", "Biweekly  fri from 2024-03-01"], ["2024-03-04"]);
          assert.equal(cal.describe({ date: "2024-03-05", original: "2024-03-04", rule: "weekly mon" }), "Tue 2024-03-05 [weekly mon] (was Mon 2024-03-04)");
          assert.equal(cal.describe({ date: "2024-03-11", original: "2024-03-11", rule: "weekly mon" }), "Mon 2024-03-11 [weekly mon]");
          assert.equal(cal.describe({ date: "2024-03-10", original: "2024-03-08", rule: "Biweekly  fri from 2024-03-01" }), "Sun 2024-03-10 [Biweekly  fri from 2024-03-01] (was Fri 2024-03-08)");
          assert.equal(cal.describe(cal.pickups("2024-03-01", "2024-03-01")[0]), "Fri 2024-03-01 [Biweekly  fri from 2024-03-01]");
          assert.equal(cal.describe(cal.pickups("2024-03-05", "2024-03-05")[0]), "Tue 2024-03-05 [weekly mon] (was Mon 2024-03-04)");
          assert.equal(cal.describe(cal.pickups("2024-03-11", "2024-03-11")[0]), "Mon 2024-03-11 [weekly mon]");
          assert.equal(cal.describe(cal.pickups("2024-03-15", "2024-03-15")[0]), "Fri 2024-03-15 [Biweekly  fri from 2024-03-01]");
        });

        test("mixed calendars 1", () => {
          check(["monthly last wed", "biweekly mon from 2023-11-03", "weekly wed"], ["2023-11-28", "2023-11-18", "2023-11-13", "2023-11-17"], ["2023-11-27"], "2023-11-19", "2023-12-02",
                "2023-11-22:weekly wed | 2023-11-30<2023-11-29:monthly last wed | 2023-11-30<2023-11-29:weekly wed");
          check(["weekly sun", "weekly sat"], ["2024-11-12"], ["2024-12-01"], "2024-11-17", "2024-12-04",
                "2024-11-18<2024-11-17:weekly sun | 2024-11-18<2024-11-16:weekly sat | 2024-11-23:weekly sat | 2024-11-24:weekly sun | 2024-11-30:weekly sat");
          check(["weekly thu", "monthday 15", "monthday 31"], ["2024-04-30", "2024-05-14", "2024-05-01"], ["2024-05-09"], "2024-05-02", "2024-05-30",
                "2024-05-04<2024-05-02:weekly thu | 2024-05-16<2024-05-15:monthday 15 | 2024-05-17<2024-05-16:weekly thu | 2024-05-23:weekly thu | 2024-05-30:weekly thu");
          check(["weekly wed", "monthday 31", "weekly fri"], ["2024-04-01", "2024-03-21", "2024-03-22"], [], "2024-03-20", "2024-04-18",
                "2024-03-20:weekly wed | 2024-03-25<2024-03-22:weekly fri | 2024-03-27:weekly wed | 2024-03-29:weekly fri | 2024-03-31:monthday 31 | 2024-04-04<2024-04-03:weekly wed | 2024-04-06<2024-04-05:weekly fri | 2024-04-10:weekly wed | 2024-04-12:weekly fri | 2024-04-17:weekly wed");
        });

        test("mixed calendars 2", () => {
          check(["weekly wed"], ["2023-02-07", "2023-02-03", "2023-02-19"], [], "2023-02-03", "2023-02-25",
                "2023-02-09<2023-02-08:weekly wed | 2023-02-15:weekly wed | 2023-02-22:weekly wed");
          check(["weekly sat", "biweekly sun from 2024-10-18"], ["2024-10-15", "2024-10-07", "2024-10-12"], [], "2024-10-11", "2024-10-26",
                "2024-10-14<2024-10-12:weekly sat | 2024-10-21<2024-10-19:weekly sat | 2024-10-21<2024-10-20:biweekly sun from 2024-10-18 | 2024-10-26:weekly sat");
          check(["weekly sun", "weekly sun", "monthly 2nd sat"], ["2023-04-26"], [], "2023-04-25", "2023-05-28",
                "2023-05-01<2023-04-30:weekly sun | 2023-05-01<2023-04-30:weekly sun | 2023-05-07:weekly sun | 2023-05-07:weekly sun | 2023-05-13:monthly 2nd sat | 2023-05-14:weekly sun | 2023-05-14:weekly sun | 2023-05-21:weekly sun | 2023-05-21:weekly sun | 2023-05-28:weekly sun | 2023-05-28:weekly sun");
          check(["biweekly thu from 2023-02-10", "monthday 5", "monthday 5"], ["2023-03-17", "2023-03-18", "2023-02-28"], [], "2023-02-26", "2023-03-25",
                "2023-03-06<2023-03-05:monthday 5 | 2023-03-06<2023-03-05:monthday 5 | 2023-03-09:biweekly thu from 2023-02-10 | 2023-03-23:biweekly thu from 2023-02-10");
        });

        test("mixed calendars 3", () => {
          check(["monthly 1st tue", "weekly sun", "biweekly fri from 2024-02-12"], ["2024-03-18", "2024-03-16", "2024-02-27", "2024-03-17"], ["2024-03-31"], "2024-02-28", "2024-04-01",
                "2024-03-02<2024-03-01:biweekly fri from 2024-02-12 | 2024-03-04<2024-03-03:weekly sun | 2024-03-05:monthly 1st tue | 2024-03-10:weekly sun | 2024-03-15:biweekly fri from 2024-02-12 | 2024-03-17:weekly sun | 2024-03-25<2024-03-24:weekly sun | 2024-03-29:biweekly fri from 2024-02-12");
          check(["weekly thu", "monthly 3rd wed"], ["2025-06-12"], [], "2025-06-03", "2025-06-21",
                "2025-06-05:weekly thu | 2025-06-13<2025-06-12:weekly thu | 2025-06-18:monthly 3rd wed | 2025-06-19:weekly thu");
        });
''')

LIB = Lib(
    name="haulcal", lang="typescript", title="the haulcal pick-up calendar library",
    blurb="The refuse service publishes its collection days from haulcal: recurrence rules, public holidays that push the week back, cancelled rounds.",
    files={"package.json": PACKAGE_JSON % "haulcal", "tsconfig.json": TSCONFIG, "types/node-shim.d.ts": TS_NODE_SHIM,
           "src/date.ts": DATE, "src/rule.ts": RULE, "src/calendar.ts": CALENDAR, "README.md": README, ".gitignore": "node_modules/\nbuild/\n"},
    visible_tests={"test/basic.test.ts": VISIBLE},
    hidden_tests={"test/full.test.ts": HIDDEN},
    mutate=["src/calendar.ts", "src/rule.ts", "src/date.ts"], difficulty=4, tags=["calendar", "recurrence", "dates"],
    verify=TS_VERIFY,
    probe_import="const { weekday, addDays, mondayOf, daysInMonth, parseDate } = require('./build/src/date');\nconst { parseRule, occurrences } = require('./build/src/rule');\nconst { Calendar } = require('./build/src/calendar');",
    probes=[
        "weekday('2024-03-04')",
        "addDays('2024-02-28', 2)",
        "mondayOf('2024-03-10')",
        "daysInMonth(1900, 2)",
        "parseDate('2024-02-30')",
        "occurrences(parseRule('monthly last fri'), '2024-01-01', '2024-03-31')",
        "occurrences(parseRule('monthday 31'), '2024-01-01', '2024-04-30')",
        "occurrences(parseRule('monthly 2nd tue'), '2024-01-01', '2024-03-31')",
        "occurrences(parseRule('biweekly tue from 2024-01-02'), '2024-01-01', '2024-02-15')",
        "parseRule('monthly 5th mon')",
        "parseRule('weekly   Sun')",
        "new Calendar(['weekly fri'], ['2024-03-04', '2024-03-05']).pickups('2024-03-01', '2024-03-15')",
        "new Calendar(['weekly fri'], ['2024-03-04']).pickups('2024-03-09', '2024-03-12')",
        "new Calendar(['weekly sat'], ['2024-03-04']).pickups('2024-03-01', '2024-03-20')",
        "new Calendar(['weekly wed'], ['2024-03-06']).pickups('2024-03-01', '2024-03-15')",
        "new Calendar(['weekly mon'], [], ['2024-03-11']).pickups('2024-03-01', '2024-03-20')",
        "new Calendar(['weekly fri'], ['2024-03-04']).next('2024-03-09')",
    ],
)

register_libs([LIB], n=8)
