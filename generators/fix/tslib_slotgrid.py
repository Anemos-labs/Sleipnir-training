"""Calendar day-view layout and free-slot search (typescript): bugs injected into a scheduling UI library."""
from fx import Lib, dd
from generators.fix._lang2 import PACKAGE_JSON, TS_NODE_SHIM, TS_VERIFY, TSCONFIG, register_libs

README = dd(r'''
    # slotgrid

    Layout maths for a calendar day view, and a free-slot finder. TypeScript, no dependencies.
    Times are whole minutes since midnight (`0` to `1440`). An event occupies `[start, end)`: two events that only
    touch (`a.end === b.start`) do not overlap.

    ## `src/time.ts`

    * `parseTime(text)`: 12-hour clock text such as `'9:05 AM'`, `'12:00 pm'`, `'11:59PM'` (one or two hour digits, two
      minute digits, an optional single space before `AM`/`PM`, any letter case, surrounding spaces ignored) to minutes
      since midnight. `'12:xx AM'` is just after midnight and `'12:xx PM'` just after noon. Text that does not have this
      shape is a `TypeError`; an hour outside `1..12` or minutes above `59` is a `RangeError`.
    * `formatTime(minutes)`: the inverse, as `'9:05 AM'` (no leading zero on the hour, minutes always two digits,
      upper-case suffix). `0` is `'12:00 AM'`, `720` is `'12:00 PM'`, `1440` is `'12:00 AM'` again. An argument that is not
      an integer in `0..1440` is a `RangeError`.

    ## `src/layout.ts`: `layoutDay(events, opts?)`

    `events` are `{ id, start, end }`. The result lists one placement per event:
    `{ id, column, columns, span, leftPct, widthPct }`.

    1. *Validation.* `end < start`, or a start or end outside `0..1440`, is a `RangeError`; two events with the same id
       are an `Error`.
    2. *Effective length.* An event shorter than `opts.minLength` minutes (default `15`, so zero-length events work) is
       treated as ending at `start + minLength` when deciding overlaps.
    3. *Order.* Events are processed, and returned, by `start` ascending, then longer effective end first, then `id`
       (plain `<` string comparison).
    4. *Clusters.* A cluster is a maximal run of events in that order in which each event starts before the latest end
       seen so far in the cluster. Different clusters are laid out independently.
    5. *Columns.* Inside a cluster, each event takes the lowest-numbered column whose previous event ended at or before
       its start (a new column when there is none). `columns` is the number of columns the whole cluster uses.
    6. *Span.* An event then widens to the right over the following columns as long as no event of the cluster in that
       column overlaps it (using effective ends); `span >= 1` counts its own column.
    7. *Percentages.* `leftPct = floor(column * 100 / columns)` and
       `widthPct = floor((column + span) * 100 / columns) - leftPct`.

    ## `src/free.ts`

    * `busyBlocks(events, minLength = 15)`: the events (effective lengths as above) merged into disjoint blocks
      `{ start, end }` in time order; events that overlap *or touch* are merged into one block.
    * `freeSlots(events, from, to, minGap = 30)`: the gaps of `[from, to)` not covered by any busy block, as
      `{ start, end }` in time order, keeping only gaps of at least `minGap` minutes. `from >= to` gives `[]`. Events
      outside the window are ignored; the ones crossing its edges only count inside it.
''')

TIME = dd(r'''
    export function parseTime(text: string): number {
      const m = /^(\d{1,2}):(\d{2}) ?(AM|PM)$/i.exec(text.trim());
      if (m === null) throw new TypeError(`bad time: ${text}`);
      const hour = Number(m[1]);
      const minute = Number(m[2]);
      if (hour < 1 || hour > 12 || minute > 59) throw new RangeError(`time out of range: ${text}`);
      const pm = m[3].toUpperCase() === "PM";
      return ((hour % 12) + (pm ? 12 : 0)) * 60 + minute;
    }

    export function formatTime(minutes: number): string {
      if (!Number.isInteger(minutes) || minutes < 0 || minutes > 1440) {
        throw new RangeError(`minutes out of range: ${minutes}`);
      }
      const h24 = Math.floor(minutes / 60) % 24;
      const minute = minutes % 60;
      const hour = h24 % 12 === 0 ? 12 : h24 % 12;
      return `${hour}:${minute < 10 ? "0" : ""}${minute} ${h24 < 12 ? "AM" : "PM"}`;
    }
''')

LAYOUT = dd(r'''
    export interface CalEvent {
      id: string;
      start: number;
      end: number;
    }

    export interface Placement {
      id: string;
      column: number;
      columns: number;
      span: number;
      leftPct: number;
      widthPct: number;
    }

    export interface LayoutOptions {
      minLength?: number;
    }

    interface Item {
      id: string;
      start: number;
      end: number;
      column: number;
    }

    function validate(events: CalEvent[]): void {
      const seen = new Set<string>();
      for (const e of events) {
        if (e.end < e.start || e.start < 0 || e.start > 1440 || e.end > 1440) {
          throw new RangeError(`bad event times for ${e.id}`);
        }
        if (seen.has(e.id)) throw new Error(`duplicate event id ${e.id}`);
        seen.add(e.id);
      }
    }

    function overlap(a: Item, b: Item): boolean {
      return a.start < b.end && b.start < a.end;
    }

    function place(cluster: Item[], out: Placement[]): void {
      const columnEnds: number[] = [];
      for (const it of cluster) {
        let col = columnEnds.findIndex((end) => end <= it.start);
        if (col < 0) {
          col = columnEnds.length;
          columnEnds.push(it.end);
        } else {
          columnEnds[col] = it.end;
        }
        it.column = col;
      }
      const columns = columnEnds.length;
      for (const it of cluster) {
        let span = 1;
        while (it.column + span < columns && !cluster.some((o) => o.column === it.column + span && overlap(o, it))) {
          span++;
        }
        const leftPct = Math.floor((it.column * 100) / columns);
        const widthPct = Math.floor(((it.column + span) * 100) / columns) - leftPct;
        out.push({ id: it.id, column: it.column, columns, span, leftPct, widthPct });
      }
    }

    export function layoutDay(events: CalEvent[], opts: LayoutOptions = {}): Placement[] {
      const minLength = opts.minLength ?? 15;
      validate(events);
      const items: Item[] = events
        .map((e) => ({ id: e.id, start: e.start, end: Math.max(e.end, e.start + minLength), column: 0 }))
        .sort((a, b) => a.start - b.start || b.end - a.end || (a.id < b.id ? -1 : 1));
      const out: Placement[] = [];
      let cluster: Item[] = [];
      let latest = 0;
      for (const it of items) {
        if (cluster.length > 0 && it.start >= latest) {
          place(cluster, out);
          cluster = [];
          latest = 0;
        }
        cluster.push(it);
        latest = Math.max(latest, it.end);
      }
      if (cluster.length > 0) place(cluster, out);
      return out;
    }
''')

FREE = dd(r'''
    import { CalEvent } from "./layout";

    export interface Block {
      start: number;
      end: number;
    }

    export function busyBlocks(events: CalEvent[], minLength = 15): Block[] {
      const spans: Block[] = events
        .map((e) => ({ start: e.start, end: Math.max(e.end, e.start + minLength) }))
        .sort((a, b) => a.start - b.start || a.end - b.end);
      const blocks: Block[] = [];
      for (const s of spans) {
        const last = blocks[blocks.length - 1];
        if (last !== undefined && s.start <= last.end) {
          last.end = Math.max(last.end, s.end);
        } else {
          blocks.push({ start: s.start, end: s.end });
        }
      }
      return blocks;
    }

    export function freeSlots(events: CalEvent[], from: number, to: number, minGap = 30): Block[] {
      if (from >= to) return [];
      const slots: Block[] = [];
      let cursor = from;
      for (const b of busyBlocks(events)) {
        if (b.end <= from || b.start >= to) continue;
        if (b.start - cursor >= minGap) slots.push({ start: cursor, end: b.start });
        cursor = Math.max(cursor, b.end);
      }
      if (to - cursor >= minGap) slots.push({ start: cursor, end: to });
      return slots;
    }
''')

VISIBLE = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { parseTime, formatTime } from "../src/time";
    import { layoutDay } from "../src/layout";

    test("time round trip", () => {
      assert.equal(parseTime("9:05 AM"), 545);
      assert.equal(formatTime(545), "9:05 AM");
    });

    test("one event fills the width", () => {
      const [p] = layoutDay([{ id: "a", start: 540, end: 600 }]);
      assert.deepEqual(p, { id: "a", column: 0, columns: 1, span: 1, leftPct: 0, widthPct: 100 });
    });
''')

HIDDEN = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { parseTime, formatTime } from "../src/time";
    import { layoutDay, CalEvent } from "../src/layout";
    import { busyBlocks, freeSlots } from "../src/free";

    const ev = (id: string, start: number, end: number): CalEvent => ({ id, start, end });
    const h = (hour: number, minute = 0): number => hour * 60 + minute;

    test("parseTime accepts the documented forms", () => {
      assert.equal(parseTime("12:00 AM"), 0);
      assert.equal(parseTime("12:30 AM"), 30);
      assert.equal(parseTime("1:00 AM"), 60);
      assert.equal(parseTime("9:05 AM"), 545);
      assert.equal(parseTime("11:59 AM"), 719);
      assert.equal(parseTime("12:00 PM"), 720);
      assert.equal(parseTime("12:15 pm"), 735);
      assert.equal(parseTime("1:00 PM"), 780);
      assert.equal(parseTime("11:59PM"), 1439);
      assert.equal(parseTime("  7:30 pm  "), 1170);
      assert.equal(parseTime("07:30 Am"), 450);
    });

    test("parseTime rejects bad text", () => {
      for (const bad of ["", "9:05", "9 AM", "9:5 AM", "9:05  AM", "900 AM", "9:05 XM", "13:00", "9:05 A.M.", "-1:00 AM", "9:05 AMM"]) {
        assert.throws(() => parseTime(bad), TypeError, bad);
      }
    });

    test("parseTime range errors", () => {
      assert.throws(() => parseTime("0:30 AM"), RangeError);
      assert.throws(() => parseTime("13:00 PM"), RangeError);
      assert.throws(() => parseTime("12:60 PM"), RangeError);
      assert.throws(() => parseTime("5:75 AM"), RangeError);
      assert.equal(parseTime("5:59 AM"), 359);
    });

    test("formatTime", () => {
      assert.equal(formatTime(0), "12:00 AM");
      assert.equal(formatTime(5), "12:05 AM");
      assert.equal(formatTime(60), "1:00 AM");
      assert.equal(formatTime(545), "9:05 AM");
      assert.equal(formatTime(719), "11:59 AM");
      assert.equal(formatTime(720), "12:00 PM");
      assert.equal(formatTime(779), "12:59 PM");
      assert.equal(formatTime(780), "1:00 PM");
      assert.equal(formatTime(1439), "11:59 PM");
      assert.equal(formatTime(1440), "12:00 AM");
    });

    test("formatTime rejects bad input", () => {
      assert.throws(() => formatTime(-1), RangeError);
      assert.throws(() => formatTime(1441), RangeError);
      assert.throws(() => formatTime(10.5), RangeError);
      assert.throws(() => formatTime(NaN), RangeError);
    });

    test("format and parse are inverse for every minute", () => {
      for (let m = 0; m < 1440; m++) assert.equal(parseTime(formatTime(m)), m);
    });

    test("layout: one event", () => {
      assert.deepEqual(layoutDay([ev("a", h(9), h(10))]), [{ id: "a", column: 0, columns: 1, span: 1, leftPct: 0, widthPct: 100 }]);
      assert.deepEqual(layoutDay([]), []);
    });

    test("layout: touching events are separate clusters", () => {
      const got = layoutDay([ev("a", h(9), h(10)), ev("b", h(10), h(11))]);
      assert.deepEqual(got.map((p) => [p.id, p.column, p.columns, p.widthPct]), [["a", 0, 1, 100], ["b", 0, 1, 100]]);
    });

    test("layout: two overlapping events share the width", () => {
      const got = layoutDay([ev("a", h(9), h(10)), ev("b", h(9, 30), h(10, 30))]);
      assert.deepEqual(got, [
        { id: "a", column: 0, columns: 2, span: 1, leftPct: 0, widthPct: 50 },
        { id: "b", column: 1, columns: 2, span: 1, leftPct: 50, widthPct: 50 },
      ]);
    });

    test("layout: a column is reused once its event has ended", () => {
      const got = layoutDay([ev("a", h(9), h(12)), ev("b", h(9), h(10)), ev("c", h(10), h(11))]);
      assert.deepEqual(got.map((p) => [p.id, p.column, p.columns, p.leftPct, p.widthPct]), [
        ["a", 0, 2, 0, 50],
        ["b", 1, 2, 50, 50],
        ["c", 1, 2, 50, 50],
      ]);
    });

    test("layout: three columns, thirds add up to 100", () => {
      const got = layoutDay([ev("a", h(9), h(10)), ev("b", h(9), h(10)), ev("c", h(9), h(10))]);
      assert.deepEqual(got.map((p) => [p.column, p.leftPct, p.widthPct]), [[0, 0, 33], [1, 33, 33], [2, 66, 34]]);
    });

    test("layout: seven columns round down per edge", () => {
      const evs = "abcdefg".split("").map((id) => ev(id, h(9), h(10)));
      const got = layoutDay(evs);
      assert.deepEqual(got.map((p) => p.leftPct), [0, 14, 28, 42, 57, 71, 85]);
      assert.deepEqual(got.map((p) => p.widthPct), [14, 14, 14, 15, 14, 14, 15]);
      assert.equal(got.reduce((a, p) => a + p.widthPct, 0), 100);
    });

    test("layout: events widen into free columns", () => {
      const got = layoutDay([
        ev("f", h(11), h(12)),
        ev("d", h(10), h(11)),
        ev("b", h(9, 30), h(10, 30)),
        ev("a", h(9), h(10)),
        ev("c", h(9), h(12)),
      ]);
      assert.deepEqual(got.map((p) => [p.id, p.column, p.columns, p.span, p.leftPct, p.widthPct]), [
        ["c", 0, 3, 1, 0, 33],
        ["a", 1, 3, 1, 33, 33],
        ["b", 2, 3, 1, 66, 34],
        ["d", 1, 3, 1, 33, 33],
        ["f", 1, 3, 2, 33, 67],
      ]);
    });

    test("layout: the widest event expands over every free column", () => {
      const got = layoutDay([ev("a", h(9), h(11)), ev("b", h(9), h(10)), ev("c", h(9), h(10)), ev("d", h(10), h(11))]);
      // a: col 0; b: col 1; c: col 2; d starts at 10 -> col 1 again, spans over col 2 (c is gone)
      assert.deepEqual(got.map((p) => [p.id, p.column, p.span]), [["a", 0, 1], ["b", 1, 1], ["c", 2, 1], ["d", 1, 2]]);
      const d = got.find((p) => p.id === "d")!;
      assert.equal(d.leftPct, 33);
      assert.equal(d.widthPct, 67);
    });

    test("layout: an event that starts when the cluster ends begins a new cluster", () => {
      const got = layoutDay([ev("a", h(9), h(10)), ev("b", h(9, 30), h(10)), ev("c", h(10), h(11))]);
      assert.deepEqual(got.map((p) => [p.id, p.column, p.columns, p.widthPct]), [["a", 0, 2, 50], ["b", 1, 2, 50], ["c", 0, 1, 100]]);
    });

    test("layout: the first column is reused too", () => {
      const got = layoutDay([ev("a", h(9), h(10)), ev("b", h(9, 30), h(11)), ev("c", h(10), h(11, 30))]);
      assert.deepEqual(got.map((p) => [p.id, p.column, p.columns, p.span, p.leftPct, p.widthPct]), [
        ["a", 0, 2, 1, 0, 50],
        ["b", 1, 2, 1, 50, 50],
        ["c", 0, 2, 1, 0, 50],
      ]);
    });

    test("layout: an event that only touches a neighbour still widens past it", () => {
      const got = layoutDay([ev("s", h(10, 30), h(11, 30)), ev("r", h(9, 30), h(10, 30)), ev("q", h(9), h(10)), ev("p", h(9), h(12))]);
      assert.deepEqual(got.map((p) => [p.id, p.column, p.columns, p.span, p.leftPct, p.widthPct]), [
        ["p", 0, 3, 1, 0, 33],
        ["q", 1, 3, 1, 33, 33],
        ["r", 2, 3, 1, 66, 34],
        ["s", 1, 3, 2, 33, 67],
      ]);
    });

    test("layout: separate clusters are independent", () => {
      const got = layoutDay([
        ev("a", h(8), h(9)),
        ev("b", h(8, 30), h(9, 30)),
        ev("c", h(13), h(14)),
        ev("d", h(13), h(15)),
        ev("e", h(13, 30), h(14)),
      ]);
      assert.deepEqual(got.map((p) => [p.id, p.column, p.columns]), [
        ["a", 0, 2],
        ["b", 1, 2],
        ["d", 0, 3],
        ["c", 1, 3],
        ["e", 2, 3],
      ]);
    });

    test("layout: ties are ordered longer first, then by id", () => {
      const got = layoutDay([ev("z", h(9), h(10)), ev("m", h(9), h(11)), ev("b", h(9), h(10))]);
      assert.deepEqual(got.map((p) => p.id), ["m", "b", "z"]);
      assert.deepEqual(got.map((p) => p.column), [0, 1, 2]);
    });

    test("layout: ids compare as plain strings", () => {
      const got = layoutDay([ev("B", h(9), h(10)), ev("a", h(9), h(10)), ev("10", h(9), h(10)), ev("9", h(9), h(10))]);
      assert.deepEqual(got.map((p) => p.id), ["10", "9", "B", "a"]);
    });

    test("layout: zero-length events get the minimum length", () => {
      const got = layoutDay([ev("a", h(10), h(10)), ev("b", h(10), h(10, 10))]);
      assert.deepEqual(got.map((p) => [p.id, p.column, p.columns]), [["a", 0, 2], ["b", 1, 2]]);
      const later = layoutDay([ev("a", h(10), h(10)), ev("b", h(10, 15), h(10, 20))]);
      assert.deepEqual(later.map((p) => [p.id, p.columns]), [["a", 1], ["b", 1]]);
      const near = layoutDay([ev("a", h(10), h(10)), ev("b", h(10, 14), h(10, 20))]);
      assert.deepEqual(near.map((p) => [p.id, p.columns]), [["a", 2], ["b", 2]]);
    });

    test("layout: minLength option", () => {
      const evs = [ev("a", h(10), h(10)), ev("b", h(10, 20), h(10, 40))];
      assert.deepEqual(layoutDay(evs).map((p) => p.columns), [1, 1]);
      assert.deepEqual(layoutDay(evs, { minLength: 30 }).map((p) => p.columns), [2, 2]);
      assert.deepEqual(layoutDay(evs, { minLength: 0 }).map((p) => p.columns), [1, 1]);
      assert.deepEqual(layoutDay([ev("a", 100, 100), ev("b", 100, 100)], { minLength: 0 }).map((p) => p.columns), [1, 1]);
    });

    test("layout: events longer than minLength keep their own end", () => {
      const got = layoutDay([ev("a", h(9), h(11)), ev("b", h(10, 59), h(12))], { minLength: 60 });
      assert.deepEqual(got.map((p) => p.columns), [2, 2]);
      const apart = layoutDay([ev("a", h(9), h(11)), ev("b", h(11), h(12))], { minLength: 60 });
      assert.deepEqual(apart.map((p) => p.columns), [1, 1]);
    });

    test("layout: validation", () => {
      assert.throws(() => layoutDay([ev("a", h(10), h(9))]), RangeError);
      assert.throws(() => layoutDay([ev("a", -1, 10)]), RangeError);
      assert.throws(() => layoutDay([ev("a", 10, 1441)]), RangeError);
      assert.throws(() => layoutDay([ev("a", 1441, 1441)]), RangeError);
      assert.throws(() => layoutDay([ev("a", 10, 20), ev("a", 30, 40)]), Error);
      assert.doesNotThrow(() => layoutDay([ev("a", 0, 1440)]));
      assert.doesNotThrow(() => layoutDay([ev("a", 1440, 1440)]));
    });

    test("layout does not modify its input", () => {
      const input = [ev("b", h(9), h(10)), ev("a", h(8), h(9))];
      layoutDay(input);
      assert.deepEqual(input, [ev("b", h(9), h(10)), ev("a", h(8), h(9))]);
    });

    test("busyBlocks merges overlapping and touching events", () => {
      const got = busyBlocks([ev("c", h(11), h(12)), ev("a", h(9), h(10)), ev("b", h(10), h(10, 30)), ev("d", h(11, 30), h(13))]);
      assert.deepEqual(got, [{ start: h(9), end: h(10, 30) }, { start: h(11), end: h(13) }]);
    });

    test("busyBlocks keeps the longest end", () => {
      const got = busyBlocks([ev("a", h(9), h(15)), ev("b", h(10), h(11)), ev("c", h(12), h(13))]);
      assert.deepEqual(got, [{ start: h(9), end: h(15) }]);
    });

    test("busyBlocks: gaps stay separate, minimum length applies", () => {
      assert.deepEqual(busyBlocks([ev("a", 600, 600)]), [{ start: 600, end: 615 }]);
      assert.deepEqual(busyBlocks([ev("a", 600, 600), ev("b", 616, 640)]), [{ start: 600, end: 615 }, { start: 616, end: 640 }]);
      assert.deepEqual(busyBlocks([ev("a", 600, 600), ev("b", 615, 640)]), [{ start: 600, end: 640 }]);
      assert.deepEqual(busyBlocks([ev("a", 600, 600), ev("b", 700, 703)]), [{ start: 600, end: 615 }, { start: 700, end: 715 }]);
      assert.deepEqual(busyBlocks([ev("a", 600, 600)], 5), [{ start: 600, end: 605 }]);
      assert.deepEqual(busyBlocks([]), []);
    });

    test("freeSlots: a plain working day", () => {
      const got = freeSlots([ev("a", h(9), h(10)), ev("b", h(12), h(13)), ev("c", h(15), h(16))], h(8), h(17));
      assert.deepEqual(got, [
        { start: h(8), end: h(9) },
        { start: h(10), end: h(12) },
        { start: h(13), end: h(15) },
        { start: h(16), end: h(17) },
      ]);
    });

    test("freeSlots: gaps shorter than minGap are dropped, equal ones kept", () => {
      const evs = [ev("a", h(9), h(10)), ev("b", h(10, 29), h(11)), ev("c", h(11, 30), h(12))];
      assert.deepEqual(freeSlots(evs, h(9), h(12)), [{ start: h(11), end: h(11, 30) }]);
      assert.deepEqual(freeSlots(evs, h(9), h(12), 29), [{ start: h(10), end: h(10, 29) }, { start: h(11), end: h(11, 30) }]);
      assert.deepEqual(freeSlots(evs, h(9), h(12), 31), []);
    });

    test("freeSlots: window edges", () => {
      const evs = [ev("a", h(7), h(9)), ev("b", h(16), h(18))];
      assert.deepEqual(freeSlots(evs, h(8), h(17)), [{ start: h(9), end: h(16) }]);
      assert.deepEqual(freeSlots([], h(8), h(8, 29)), []);
      assert.deepEqual(freeSlots([], h(8), h(8, 30)), [{ start: h(8), end: h(8, 30) }]);
      assert.deepEqual(freeSlots([ev("a", h(6), h(7))], h(8), h(9)), [{ start: h(8), end: h(9) }]);
      assert.deepEqual(freeSlots([ev("a", h(9), h(10))], h(8), h(9)), [{ start: h(8), end: h(9) }]);
      assert.deepEqual(freeSlots([ev("a", h(8), h(9))], h(8), h(9)), []);
    });

    test("freeSlots: overlapping events and empty windows", () => {
      const evs = [ev("a", h(9), h(12)), ev("b", h(10), h(11)), ev("c", h(11, 30), h(14))];
      assert.deepEqual(freeSlots(evs, h(8), h(16)), [{ start: h(8), end: h(9) }, { start: h(14), end: h(16) }]);
      assert.deepEqual(freeSlots(evs, h(10), h(10)), []);
      assert.deepEqual(freeSlots(evs, h(12), h(10)), []);
    });

    test("freeSlots: zero-length events block fifteen minutes", () => {
      const got = freeSlots([ev("a", h(9), h(9))], h(9), h(10), 15);
      assert.deepEqual(got, [{ start: h(9, 15), end: h(10) }]);
    });
''')

LIB = Lib(
    name="slotgrid", lang="typescript", title="the slotgrid calendar library",
    blurb="The scheduling UI uses slotgrid to lay out overlapping events in a day view and to suggest free slots.",
    files={"package.json": PACKAGE_JSON % "slotgrid", "tsconfig.json": TSCONFIG, "types/node-shim.d.ts": TS_NODE_SHIM,
           "src/time.ts": TIME, "src/layout.ts": LAYOUT, "src/free.ts": FREE, "README.md": README, ".gitignore": "node_modules/\nbuild/\n"},
    visible_tests={"test/basic.test.ts": VISIBLE},
    hidden_tests={"test/full.test.ts": HIDDEN},
    mutate=["src/layout.ts", "src/free.ts", "src/time.ts"], difficulty=3, tags=["calendar", "layout", "scheduling"],
    verify=TS_VERIFY,
    probe_import="const { parseTime, formatTime } = require('./build/src/time');\nconst { layoutDay } = require('./build/src/layout');\nconst { busyBlocks, freeSlots } = require('./build/src/free');\nconst ev = (id, start, end) => ({ id, start, end });",
    probes=[
        "parseTime('12:15 pm')", "parseTime('12:00 AM')", "parseTime('11:59PM')", "parseTime('0:30 AM')", "formatTime(0)", "formatTime(720)", "formatTime(779)", "formatTime(1440)",
        "layoutDay([ev('a', 540, 600), ev('b', 570, 630)])",
        "layoutDay([ev('a', 540, 600), ev('b', 540, 600), ev('c', 540, 600)]).map((p) => [p.leftPct, p.widthPct])",
        "layoutDay([ev('a', 540, 600), ev('b', 600, 660)]).map((p) => p.columns)",
        "layoutDay([ev('f', 660, 720), ev('d', 600, 660), ev('b', 570, 630), ev('a', 540, 600), ev('c', 540, 720)]).map((p) => [p.id, p.column, p.span, p.widthPct])",
        "layoutDay([ev('a', 600, 600), ev('b', 614, 620)]).map((p) => p.columns)",
        "layoutDay([ev('z', 540, 600), ev('m', 540, 660), ev('b', 540, 600)]).map((p) => p.id)",
        "busyBlocks([ev('a', 540, 600), ev('b', 600, 630), ev('c', 660, 720)])",
        "busyBlocks([ev('a', 540, 900), ev('b', 600, 660)])",
        "freeSlots([ev('a', 540, 600), ev('b', 720, 780)], 480, 1020)",
        "freeSlots([ev('a', 540, 600), ev('b', 629, 660)], 540, 720)",
        "freeSlots([ev('a', 420, 540), ev('b', 960, 1080)], 480, 1020)",
    ],
)

register_libs([LIB], n=8)
