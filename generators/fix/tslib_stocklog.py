"""Inventory ledger with reservations and backorders (typescript): bugs injected into a stock-keeping library."""
from fx import Lib, dd
from generators.fix._lang2 import PACKAGE_JSON, TS_NODE_SHIM, TS_VERIFY, TSCONFIG, register_libs

README = dd(r'''
    # stocklog

    The stock ledger of a small web shop's warehouse: events go in, per-SKU counts and open backorders come out.
    TypeScript, no dependencies. `import { Ledger } from './src/ledger'`, `import { validate } from './src/events'`.

    ## Events (`src/events.ts`)

    ```ts
    type LedgerEvent =
      | { type: 'receive'; sku: string; qty: number; at: number }            // stock arrives
      | { type: 'reserve'; sku: string; qty: number; order: string; at: number }
      | { type: 'release'; order: string; at: number }                       // cancel an order's holds
      | { type: 'ship'; order: string; at: number }
      | { type: 'adjust'; sku: string; delta: number; at: number };          // stock count correction
    ```

    `validate(event)` throws a `RangeError` unless `at` is a finite number and: `qty` (receive, reserve) is a positive integer,
    `delta` (adjust) a non-zero integer. It returns the event.

    ## `new Ledger()`

    `apply(event)` validates the event, then requires `event.at >= ` the `at` of the previous event (`RangeError`, nothing changes;
    equal times are fine). It returns the shipments (`[]` except for `ship`). Per SKU the ledger tracks `onHand`, the
    *reservations* (stock held for an order) and the *backorders* (what an order is still waiting for). **Available** stock is
    `onHand` minus everything reserved. Invariant: a SKU has backorders only while nothing is available.

    * `receive`: `onHand += qty`, then backorders of that SKU are filled (below).
    * `reserve`: the order gets `min(qty, available)` as a reservation; the remainder `qty - taken`, if any, becomes backorder
      of that order. Reserving again for the same order and SKU adds to its existing reservation / backorder.
    * `release`: removes every reservation *and* backorder of that order, in all SKUs; then the freed stock fills backorders.
    * `ship`: for every SKU where the order has a reservation, that quantity leaves `onHand` and the reservation disappears; the
      order's backorders stay. Returns `[{ sku, qty }]` sorted by sku (plain `<` order). An order with nothing reserved ships `[]`.
    * `adjust`: `onHand += delta`. If that would make `onHand` negative it is a `RangeError` and nothing changes. If `onHand` is now
      below the reserved total, the shortfall is taken away from reservations, newest *place in line* first (highest `seq`, below);
      each cut quantity becomes backorder of that order (added to an existing one). Otherwise backorders are filled.
    * **Filling backorders** goes through them in line order and turns `min(available, backorder)` into reservation (added to the
      order's existing reservation), stopping when nothing is available. Fully filled backorders disappear.
    * **Place in line.** The first time an order reserves a SKU (when it has neither reservation nor backorder there) it gets the
      next number of a counter shared by the whole ledger, its `seq`; it keeps that number for as long as it has either entry.
      Lists are kept sorted by `seq`.

    `ledger.snapshot(sku)` returns `{ sku, onHand, reserved, available, backordered, reservations, backorders }` where the last two
    are `[{ order, qty }]` in `seq` order (copies). An unknown SKU is all zeros and empty lists.

    `ledger.orderStatus(order)` returns `[{ sku, reserved, backordered }]` sorted by sku, for every SKU where the order has a
    reservation or backorder.
''')

EVENTS = dd(r'''
    export type LedgerEvent =
      | { type: "receive"; sku: string; qty: number; at: number }
      | { type: "reserve"; sku: string; qty: number; order: string; at: number }
      | { type: "release"; order: string; at: number }
      | { type: "ship"; order: string; at: number }
      | { type: "adjust"; sku: string; delta: number; at: number };

    export function validate(event: LedgerEvent): LedgerEvent {
      if (typeof event.at !== "number" || !Number.isFinite(event.at)) throw new RangeError("at must be a finite number");
      if (event.type === "receive" || event.type === "reserve") {
        if (!Number.isInteger(event.qty) || event.qty < 1) throw new RangeError("qty must be a positive integer");
      }
      if (event.type === "adjust") {
        if (!Number.isInteger(event.delta) || event.delta === 0) throw new RangeError("delta must be a non-zero integer");
      }
      return event;
    }
''')

LEDGER = dd(r'''
    import { LedgerEvent, validate } from "./events";

    interface Entry {
      order: string;
      qty: number;
      seq: number;
    }

    interface Stock {
      onHand: number;
      reservations: Entry[];
      backorders: Entry[];
    }

    export interface Shipment {
      sku: string;
      qty: number;
    }

    export interface Snapshot {
      sku: string;
      onHand: number;
      reserved: number;
      available: number;
      backordered: number;
      reservations: { order: string; qty: number }[];
      backorders: { order: string; qty: number }[];
    }

    function total(list: Entry[]): number {
      return list.reduce((sum, e) => sum + e.qty, 0);
    }

    export class Ledger {
      private readonly stock = new Map<string, Stock>();
      private counter = 0;
      private clock = -Infinity;

      private get(sku: string): Stock {
        let s = this.stock.get(sku);
        if (s === undefined) {
          s = { onHand: 0, reservations: [], backorders: [] };
          this.stock.set(sku, s);
        }
        return s;
      }

      private add(list: Entry[], order: string, qty: number, seq: number): void {
        const hit = list.find((e) => e.order === order);
        if (hit !== undefined) {
          hit.qty += qty;
          return;
        }
        list.push({ order, qty, seq });
        list.sort((a, b) => a.seq - b.seq);
      }

      private seqFor(s: Stock, order: string): number {
        const hit = s.reservations.find((e) => e.order === order) ?? s.backorders.find((e) => e.order === order);
        if (hit !== undefined) return hit.seq;
        this.counter += 1;
        return this.counter;
      }

      private fill(s: Stock): void {
        for (const b of s.backorders) {
          const free = s.onHand - total(s.reservations);
          if (free <= 0) break;
          const take = Math.min(free, b.qty);
          this.add(s.reservations, b.order, take, b.seq);
          b.qty -= take;
        }
        s.backorders = s.backorders.filter((b) => b.qty > 0);
      }

      apply(event: LedgerEvent): Shipment[] {
        validate(event);
        if (event.at < this.clock) throw new RangeError("events must arrive in time order");
        if (event.type === "adjust" && this.get(event.sku).onHand + event.delta < 0) throw new RangeError("stock cannot go below zero");
        this.clock = event.at;
        switch (event.type) {
          case "receive": {
            const s = this.get(event.sku);
            s.onHand += event.qty;
            this.fill(s);
            return [];
          }
          case "reserve": {
            const s = this.get(event.sku);
            const seq = this.seqFor(s, event.order);
            const free = Math.max(0, s.onHand - total(s.reservations));
            const taken = Math.min(event.qty, free);
            if (taken > 0) this.add(s.reservations, event.order, taken, seq);
            if (event.qty > taken) this.add(s.backorders, event.order, event.qty - taken, seq);
            return [];
          }
          case "release": {
            for (const s of this.stock.values()) {
              s.reservations = s.reservations.filter((e) => e.order !== event.order);
              s.backorders = s.backorders.filter((e) => e.order !== event.order);
              this.fill(s);
            }
            return [];
          }
          case "ship": {
            const out: Shipment[] = [];
            for (const [sku, s] of this.stock) {
              const r = s.reservations.find((e) => e.order === event.order);
              if (r === undefined) continue;
              s.onHand -= r.qty;
              s.reservations = s.reservations.filter((e) => e !== r);
              out.push({ sku, qty: r.qty });
            }
            return out.sort((a, b) => (a.sku < b.sku ? -1 : a.sku > b.sku ? 1 : 0));
          }
          case "adjust": {
            const s = this.get(event.sku);
            s.onHand += event.delta;
            let deficit = total(s.reservations) - s.onHand;
            if (deficit > 0) {
              for (const r of [...s.reservations].sort((a, b) => b.seq - a.seq)) {
                if (deficit === 0) break;
                const cut = Math.min(deficit, r.qty);
                r.qty -= cut;
                deficit -= cut;
                this.add(s.backorders, r.order, cut, r.seq);
              }
              s.reservations = s.reservations.filter((e) => e.qty > 0);
            } else {
              this.fill(s);
            }
            return [];
          }
        }
      }

      snapshot(sku: string): Snapshot {
        const s = this.stock.get(sku) ?? { onHand: 0, reservations: [], backorders: [] };
        const reserved = total(s.reservations);
        return {
          sku,
          onHand: s.onHand,
          reserved,
          available: s.onHand - reserved,
          backordered: total(s.backorders),
          reservations: s.reservations.map((e) => ({ order: e.order, qty: e.qty })),
          backorders: s.backorders.map((e) => ({ order: e.order, qty: e.qty })),
        };
      }

      orderStatus(order: string): { sku: string; reserved: number; backordered: number }[] {
        const out: { sku: string; reserved: number; backordered: number }[] = [];
        for (const [sku, s] of this.stock) {
          const reserved = s.reservations.find((e) => e.order === order)?.qty ?? 0;
          const backordered = s.backorders.find((e) => e.order === order)?.qty ?? 0;
          if (reserved > 0 || backordered > 0) out.push({ sku, reserved, backordered });
        }
        return out.sort((a, b) => (a.sku < b.sku ? -1 : a.sku > b.sku ? 1 : 0));
      }
    }
''')

VISIBLE = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { Ledger } from "../src/ledger";

    test("receive and reserve", () => {
      const l = new Ledger();
      l.apply({ type: "receive", sku: "A", qty: 10, at: 1 });
      l.apply({ type: "reserve", sku: "A", qty: 4, order: "o1", at: 2 });
      const s = l.snapshot("A");
      assert.equal(s.onHand, 10);
      assert.equal(s.available, 6);
    });
''')

HIDDEN = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { Ledger } from "../src/ledger";
    import { validate, LedgerEvent } from "../src/events";

    let clock = 0;
    const tick = () => ++clock;
    const receive = (l: Ledger, sku: string, qty: number) => l.apply({ type: "receive", sku, qty, at: tick() });
    const reserve = (l: Ledger, sku: string, qty: number, order: string) => l.apply({ type: "reserve", sku, qty, order, at: tick() });
    const release = (l: Ledger, order: string) => l.apply({ type: "release", order, at: tick() });
    const ship = (l: Ledger, order: string) => l.apply({ type: "ship", order, at: tick() });
    const adjust = (l: Ledger, sku: string, delta: number) => l.apply({ type: "adjust", sku, delta, at: tick() });

    test("validate accepts good events and returns them", () => {
      const e: LedgerEvent = { type: "receive", sku: "A", qty: 1, at: 0 };
      assert.strictEqual(validate(e), e);
      assert.doesNotThrow(() => validate({ type: "release", order: "o", at: -5 }));
      assert.doesNotThrow(() => validate({ type: "adjust", sku: "A", delta: -3, at: 1 }));
      assert.doesNotThrow(() => validate({ type: "reserve", sku: "A", qty: 2, order: "o", at: 1.5 }));
    });

    test("validate rejects bad events", () => {
      assert.throws(() => validate({ type: "receive", sku: "A", qty: 0, at: 1 }), RangeError);
      assert.throws(() => validate({ type: "receive", sku: "A", qty: -1, at: 1 }), RangeError);
      assert.throws(() => validate({ type: "receive", sku: "A", qty: 1.5, at: 1 }), RangeError);
      assert.throws(() => validate({ type: "reserve", sku: "A", qty: 0, order: "o", at: 1 }), RangeError);
      assert.throws(() => validate({ type: "reserve", sku: "A", qty: 2.5, order: "o", at: 1 }), RangeError);
      assert.throws(() => validate({ type: "adjust", sku: "A", delta: 0, at: 1 }), RangeError);
      assert.throws(() => validate({ type: "adjust", sku: "A", delta: 0.5, at: 1 }), RangeError);
      assert.throws(() => validate({ type: "release", order: "o", at: NaN }), RangeError);
      assert.throws(() => validate({ type: "ship", order: "o", at: Infinity }), RangeError);
    });

    test("a full scenario: reserve, backorder, receive, ship, release, adjust", () => {
      const l = new Ledger();
      receive(l, "A", 10);
      reserve(l, "A", 4, "o1");
      assert.deepEqual(l.snapshot("A"), { sku: "A", onHand: 10, reserved: 4, available: 6, backordered: 0, reservations: [{ order: "o1", qty: 4 }], backorders: [] });
      reserve(l, "A", 8, "o2");
      reserve(l, "A", 3, "o3");
      assert.deepEqual(l.snapshot("A"), {
        sku: "A", onHand: 10, reserved: 10, available: 0, backordered: 5,
        reservations: [{ order: "o1", qty: 4 }, { order: "o2", qty: 6 }],
        backorders: [{ order: "o2", qty: 2 }, { order: "o3", qty: 3 }],
      });
      receive(l, "A", 4);
      assert.deepEqual(l.snapshot("A"), {
        sku: "A", onHand: 14, reserved: 14, available: 0, backordered: 1,
        reservations: [{ order: "o1", qty: 4 }, { order: "o2", qty: 8 }, { order: "o3", qty: 2 }],
        backorders: [{ order: "o3", qty: 1 }],
      });
      assert.deepEqual(ship(l, "o1"), [{ sku: "A", qty: 4 }]);
      assert.deepEqual(l.snapshot("A").reservations, [{ order: "o2", qty: 8 }, { order: "o3", qty: 2 }]);
      assert.equal(l.snapshot("A").onHand, 10);
      release(l, "o2");
      assert.deepEqual(l.snapshot("A"), {
        sku: "A", onHand: 10, reserved: 3, available: 7, backordered: 0,
        reservations: [{ order: "o3", qty: 3 }],
        backorders: [],
      });
      adjust(l, "A", -9);
      assert.deepEqual(l.snapshot("A"), {
        sku: "A", onHand: 1, reserved: 1, available: 0, backordered: 2,
        reservations: [{ order: "o3", qty: 1 }],
        backorders: [{ order: "o3", qty: 2 }],
      });
      adjust(l, "A", 5);
      assert.deepEqual(l.snapshot("A").reservations, [{ order: "o3", qty: 3 }]);
      assert.equal(l.snapshot("A").available, 3);
      assert.deepEqual(l.snapshot("A").backorders, []);
    });

    test("unknown skus are empty", () => {
      assert.deepEqual(new Ledger().snapshot("nope"), { sku: "nope", onHand: 0, reserved: 0, available: 0, backordered: 0, reservations: [], backorders: [] });
    });

    test("reserve with exactly the available stock", () => {
      const l = new Ledger();
      receive(l, "A", 5);
      reserve(l, "A", 5, "o1");
      const s = l.snapshot("A");
      assert.equal(s.available, 0);
      assert.equal(s.backordered, 0);
      reserve(l, "A", 1, "o2");
      assert.deepEqual(l.snapshot("A").backorders, [{ order: "o2", qty: 1 }]);
    });

    test("reserving without any stock is a pure backorder", () => {
      const l = new Ledger();
      reserve(l, "A", 3, "o1");
      assert.deepEqual(l.snapshot("A"), { sku: "A", onHand: 0, reserved: 0, available: 0, backordered: 3, reservations: [], backorders: [{ order: "o1", qty: 3 }] });
      receive(l, "A", 2);
      assert.deepEqual(l.snapshot("A").reservations, [{ order: "o1", qty: 2 }]);
      assert.deepEqual(l.snapshot("A").backorders, [{ order: "o1", qty: 1 }]);
    });

    test("reserving again for the same order adds up and keeps the place in line", () => {
      const l = new Ledger();
      receive(l, "A", 10);
      reserve(l, "A", 2, "o1");
      reserve(l, "A", 3, "o2");
      reserve(l, "A", 2, "o1");
      assert.deepEqual(l.snapshot("A").reservations, [{ order: "o1", qty: 4 }, { order: "o2", qty: 3 }]);
      reserve(l, "A", 20, "o3");
      reserve(l, "A", 1, "o2");
      reserve(l, "A", 1, "o3");
      const s = l.snapshot("A");
      assert.deepEqual(s.reservations, [{ order: "o1", qty: 4 }, { order: "o2", qty: 3 }, { order: "o3", qty: 3 }]);
      assert.deepEqual(s.backorders, [{ order: "o2", qty: 1 }, { order: "o3", qty: 18 }]);
    });

    test("backorders are filled in line order, partly if needed", () => {
      const l = new Ledger();
      reserve(l, "A", 5, "o1");
      reserve(l, "A", 5, "o2");
      reserve(l, "A", 5, "o3");
      receive(l, "A", 7);
      let s = l.snapshot("A");
      assert.deepEqual(s.reservations, [{ order: "o1", qty: 5 }, { order: "o2", qty: 2 }]);
      assert.deepEqual(s.backorders, [{ order: "o2", qty: 3 }, { order: "o3", qty: 5 }]);
      receive(l, "A", 4);
      s = l.snapshot("A");
      assert.deepEqual(s.reservations, [{ order: "o1", qty: 5 }, { order: "o2", qty: 5 }, { order: "o3", qty: 1 }]);
      assert.deepEqual(s.backorders, [{ order: "o3", qty: 4 }]);
      receive(l, "A", 10);
      s = l.snapshot("A");
      assert.equal(s.backordered, 0);
      assert.equal(s.available, 6);
    });

    test("place in line is shared across skus and decided by the first reservation", () => {
      const l = new Ledger();
      reserve(l, "A", 1, "o1");
      reserve(l, "B", 1, "o2");
      reserve(l, "B", 1, "o1");
      reserve(l, "A", 1, "o2");
      receive(l, "B", 1);
      // in B, o2 reserved first (seq 2) and o1 second (seq 3)
      assert.deepEqual(l.snapshot("B").reservations, [{ order: "o2", qty: 1 }]);
      assert.deepEqual(l.snapshot("B").backorders, [{ order: "o1", qty: 1 }]);
      receive(l, "A", 1);
      assert.deepEqual(l.snapshot("A").reservations, [{ order: "o1", qty: 1 }]);
      assert.deepEqual(l.snapshot("A").backorders, [{ order: "o2", qty: 1 }]);
    });

    test("an order that shipped can reserve again at the back of the line", () => {
      const l = new Ledger();
      receive(l, "A", 2);
      reserve(l, "A", 2, "o1");
      reserve(l, "A", 1, "o2");
      ship(l, "o1");
      reserve(l, "A", 1, "o1");
      assert.deepEqual(l.snapshot("A").backorders, [{ order: "o2", qty: 1 }, { order: "o1", qty: 1 }]);
      receive(l, "A", 1);
      assert.deepEqual(l.snapshot("A").reservations, [{ order: "o2", qty: 1 }]);
    });

    test("ship moves reserved stock out and leaves backorders", () => {
      const l = new Ledger();
      receive(l, "A", 3);
      receive(l, "B", 5);
      reserve(l, "A", 5, "o1");
      reserve(l, "B", 2, "o1");
      assert.deepEqual(ship(l, "o1"), [{ sku: "A", qty: 3 }, { sku: "B", qty: 2 }]);
      assert.deepEqual(l.snapshot("A"), { sku: "A", onHand: 0, reserved: 0, available: 0, backordered: 2, reservations: [], backorders: [{ order: "o1", qty: 2 }] });
      assert.deepEqual(l.snapshot("B"), { sku: "B", onHand: 3, reserved: 0, available: 3, backordered: 0, reservations: [], backorders: [] });
    });

    test("ship results are sorted by sku and skip untouched skus", () => {
      const l = new Ledger();
      receive(l, "zeta", 5);
      receive(l, "alpha", 5);
      receive(l, "Mid", 5);
      receive(l, "other", 5);
      reserve(l, "zeta", 1, "o1");
      reserve(l, "alpha", 2, "o1");
      reserve(l, "Mid", 3, "o1");
      assert.deepEqual(ship(l, "o1"), [{ sku: "Mid", qty: 3 }, { sku: "alpha", qty: 2 }, { sku: "zeta", qty: 1 }]);
      assert.deepEqual(ship(l, "o1"), []);
      assert.deepEqual(ship(l, "nobody"), []);
    });

    test("release frees reservations and cancels backorders, then refills the line", () => {
      const l = new Ledger();
      receive(l, "A", 4);
      receive(l, "B", 1);
      reserve(l, "A", 3, "o1");
      reserve(l, "A", 3, "o2");
      reserve(l, "B", 2, "o1");
      reserve(l, "B", 1, "o3");
      assert.deepEqual(l.orderStatus("o1"), [{ sku: "A", reserved: 3, backordered: 0 }, { sku: "B", reserved: 1, backordered: 1 }]);
      release(l, "o1");
      assert.deepEqual(l.orderStatus("o1"), []);
      assert.deepEqual(l.snapshot("A").reservations, [{ order: "o2", qty: 3 }]);
      assert.deepEqual(l.snapshot("A").backorders, []);
      assert.equal(l.snapshot("A").available, 1);
      assert.deepEqual(l.snapshot("B").reservations, [{ order: "o3", qty: 1 }]);
      assert.deepEqual(l.snapshot("B").backorders, []);
    });

    test("release of an unknown order changes nothing", () => {
      const l = new Ledger();
      receive(l, "A", 2);
      reserve(l, "A", 1, "o1");
      release(l, "ghost");
      assert.deepEqual(l.snapshot("A").reservations, [{ order: "o1", qty: 1 }]);
    });

    test("adjust upwards fills backorders, downwards cuts the newest place in line first", () => {
      const l = new Ledger();
      receive(l, "A", 10);
      reserve(l, "A", 4, "o1");
      reserve(l, "A", 4, "o2");
      reserve(l, "A", 2, "o3");
      adjust(l, "A", -5);
      let s = l.snapshot("A");
      assert.equal(s.onHand, 5);
      assert.deepEqual(s.reservations, [{ order: "o1", qty: 4 }, { order: "o2", qty: 1 }]);
      assert.deepEqual(s.backorders, [{ order: "o2", qty: 3 }, { order: "o3", qty: 2 }]);
      receive(l, "A", 4);
      s = l.snapshot("A");
      assert.deepEqual(s.reservations, [{ order: "o1", qty: 4 }, { order: "o2", qty: 4 }, { order: "o3", qty: 1 }]);
      assert.deepEqual(s.backorders, [{ order: "o3", qty: 1 }]);
      adjust(l, "A", 1);
      assert.deepEqual(l.snapshot("A").backorders, []);
      assert.equal(l.snapshot("A").available, 0);
    });

    test("adjust that does not cut reservations leaves them alone", () => {
      const l = new Ledger();
      receive(l, "A", 10);
      reserve(l, "A", 4, "o1");
      adjust(l, "A", -6);
      assert.deepEqual(l.snapshot("A"), { sku: "A", onHand: 4, reserved: 4, available: 0, backordered: 0, reservations: [{ order: "o1", qty: 4 }], backorders: [] });
      adjust(l, "A", -1);
      assert.deepEqual(l.snapshot("A"), { sku: "A", onHand: 3, reserved: 3, available: 0, backordered: 1, reservations: [{ order: "o1", qty: 3 }], backorders: [{ order: "o1", qty: 1 }] });
    });

    test("adjust cuts into an order's existing backorder", () => {
      const l = new Ledger();
      receive(l, "A", 3);
      reserve(l, "A", 5, "o1");
      assert.deepEqual(l.snapshot("A").backorders, [{ order: "o1", qty: 2 }]);
      adjust(l, "A", -2);
      assert.deepEqual(l.snapshot("A").reservations, [{ order: "o1", qty: 1 }]);
      assert.deepEqual(l.snapshot("A").backorders, [{ order: "o1", qty: 4 }]);
    });

    test("adjust below zero is rejected and leaves the ledger untouched", () => {
      const l = new Ledger();
      receive(l, "A", 3);
      reserve(l, "A", 2, "o1");
      assert.throws(() => adjust(l, "A", -4), RangeError);
      assert.equal(l.snapshot("A").onHand, 3);
      assert.deepEqual(l.snapshot("A").reservations, [{ order: "o1", qty: 2 }]);
      assert.throws(() => adjust(l, "unknown", -1), RangeError);
      assert.doesNotThrow(() => adjust(l, "A", -3));
      assert.equal(l.snapshot("A").onHand, 0);
    });

    test("events must come in time order, equal times are fine", () => {
      const l = new Ledger();
      l.apply({ type: "receive", sku: "A", qty: 1, at: 10 });
      l.apply({ type: "receive", sku: "A", qty: 1, at: 10 });
      assert.throws(() => l.apply({ type: "receive", sku: "A", qty: 1, at: 9 }), RangeError);
      assert.equal(l.snapshot("A").onHand, 2);
      l.apply({ type: "receive", sku: "A", qty: 1, at: 11 });
      assert.equal(l.snapshot("A").onHand, 3);
    });

    test("a rejected event does not move the clock", () => {
      const l = new Ledger();
      l.apply({ type: "receive", sku: "A", qty: 1, at: 5 });
      assert.throws(() => l.apply({ type: "receive", sku: "A", qty: 0, at: 100 }), RangeError);
      assert.throws(() => l.apply({ type: "adjust", sku: "A", delta: -9, at: 100 }), RangeError);
      assert.doesNotThrow(() => l.apply({ type: "receive", sku: "A", qty: 1, at: 6 }));
    });

    test("snapshots are copies", () => {
      const l = new Ledger();
      receive(l, "A", 2);
      reserve(l, "A", 1, "o1");
      const s = l.snapshot("A");
      s.reservations[0].qty = 99;
      s.reservations.push({ order: "x", qty: 1 });
      assert.deepEqual(l.snapshot("A").reservations, [{ order: "o1", qty: 1 }]);
    });

    test("orderStatus lists skus alphabetically", () => {
      const l = new Ledger();
      receive(l, "b", 5);
      receive(l, "a", 1);
      reserve(l, "b", 2, "o1");
      reserve(l, "a", 3, "o1");
      reserve(l, "c", 4, "o1");
      assert.deepEqual(l.orderStatus("o1"), [
        { sku: "a", reserved: 1, backordered: 2 },
        { sku: "b", reserved: 2, backordered: 0 },
        { sku: "c", reserved: 0, backordered: 4 },
      ]);
      assert.deepEqual(l.orderStatus("nobody"), []);
    });
''')

LIB = Lib(
    name="stocklog", lang="typescript", title="the stocklog ledger",
    blurb="The warehouse system of a small web shop keeps its per-SKU counts, reservations and backorders in stocklog.",
    files={"package.json": PACKAGE_JSON % "stocklog", "tsconfig.json": TSCONFIG, "types/node-shim.d.ts": TS_NODE_SHIM,
           "src/events.ts": EVENTS, "src/ledger.ts": LEDGER, "README.md": README, ".gitignore": "node_modules/\nbuild/\n"},
    visible_tests={"test/basic.test.ts": VISIBLE},
    hidden_tests={"test/full.test.ts": HIDDEN},
    mutate=["src/ledger.ts", "src/events.ts"], difficulty=4, tags=["inventory", "ledger", "state"],
    verify=TS_VERIFY,
)

register_libs([LIB], n=8)
