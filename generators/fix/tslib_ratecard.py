"""Tiered usage pricing for invoices (typescript): bugs injected into a rate-card library."""
from fx import Lib, dd
from generators.fix._lang2 import PACKAGE_JSON, TS_NODE_SHIM, TS_VERIFY, TSCONFIG, register_libs

README = dd(r'''
    # ratecard

    Prices metered usage for the invoices of a hosting platform. TypeScript, no dependencies:
    `import { price } from './src/plan'`, `import { graduated, volume, packages, validateTiers } from './src/tiers'`,
    `import { roundHalfUp, checkUnits } from './src/money'`.

    Money is integer cents. Unit prices of metered items are integers in **milli-cents** (thousandths of a cent): `500`
    milli-cents is half a cent. A line's amount is computed in milli-cents and rounded once, at the end of the line.

    ## `src/money.ts`

    * `roundHalfUp(n, d)`: `n / d` rounded half up, for `n >= 0` and `d > 0` (`roundHalfUp(5, 2)` is `3`).
    * `checkUnits(units)`: returns `units` when it is a non-negative integer, otherwise throws a `RangeError`.

    ## `src/tiers.ts`

    A tier is `{ upTo, unitMilli }`: the tier covers units up to and including `upTo` (`null` for no limit). `validateTiers(tiers)`
    throws a `RangeError` unless there is at least one tier, `upTo` values are positive integers that strictly increase, the last
    tier (and only the last) has `upTo: null`, and every `unitMilli` is a non-negative integer.

    * `graduated(tiers, units)`: milli-cents where each unit is charged at the rate of the tier it falls into. With tiers
      `{1000: 500}, {10000: 300}, {null: 100}` the 2,500 units cost `1000 * 500 + 1500 * 300 = 950000`.
    * `volume(tiers, units)`: milli-cents where *all* units are charged at the rate of the first tier whose `upTo` is at least
      `units` (the unlimited tier if none). 1,000 units cost `1000 * 500`; 1,001 units cost `1001 * 300`.
    * `packages(units, blockSize, blockCents)`: whole **cents** (not milli-cents): units are sold in blocks of `blockSize`; the
      number of blocks is `units / blockSize` rounded up. Zero units cost nothing. `blockSize` must be a positive integer
      (`RangeError`).

    Both `graduated` and `volume` validate their tiers and units first.

    ## `src/plan.ts`: `price(plan, usage)`

    A plan has `baseCents` (default 0), `items`, `discountPct` (default 0), `creditCents` (default 0) and `minimumCents`
    (default 0). An item has a `key`, a `label`, a `model` (`'graduated'`, `'volume'`, `'package'` or `'flat'`) and:

    * `graduated` / `volume`: `tiers`;
    * `package`: `blockSize` and `blockCents`;
    * `flat`: `flatCents`, charged once whatever the usage;
    * all except `flat` may have `freeUnits` (default 0): that many units are not charged (usage is reduced, not below 0).

    `usage` maps item keys to unit counts (missing means 0; each count is validated with `checkUnits`, even for flat items and
    items that end up free).

    The result is `{ lines, subtotalCents, discountCents, creditAppliedCents, trueUpCents, totalCents }`:

    1. `lines`: one `{ key, label, qty, cents }` for every item in plan order, except metered items (all models but `flat`) whose
       usage after free units is `0` *and* that cost nothing, which are left out. `qty` is the usage after free units (for
       `flat` items it is `1`). For metered items `cents` is `roundHalfUp(milli, 1000)`; package items already give cents.
    2. `subtotalCents = baseCents + sum of line cents`.
    3. `discountCents = roundHalfUp(subtotalCents * discountPct, 100)`.
    4. `creditAppliedCents = min(creditCents, subtotalCents - discountCents)`.
    5. `trueUpCents`: if `subtotalCents - discountCents - creditAppliedCents` is below `minimumCents`, the difference, else `0`.
    6. `totalCents = subtotalCents - discountCents - creditAppliedCents + trueUpCents`.
''')

MONEY = dd(r'''
    export function roundHalfUp(n: number, d: number): number {
      return Math.floor((2 * n + d) / (2 * d));
    }

    export function checkUnits(units: number): number {
      if (!Number.isInteger(units) || units < 0) throw new RangeError(`bad unit count: ${units}`);
      return units;
    }
''')

TIERS = dd(r'''
    import { checkUnits } from "./money";

    export interface Tier {
      upTo: number | null;
      unitMilli: number;
    }

    export function validateTiers(tiers: Tier[]): void {
      if (tiers.length === 0) throw new RangeError("a rate card needs at least one tier");
      let prev = 0;
      tiers.forEach((tier, i) => {
        const last = i === tiers.length - 1;
        if (!Number.isInteger(tier.unitMilli) || tier.unitMilli < 0) throw new RangeError("unitMilli must be a non-negative integer");
        if (tier.upTo === null) {
          if (!last) throw new RangeError("only the last tier may be unlimited");
          return;
        }
        if (last) throw new RangeError("the last tier must be unlimited");
        if (!Number.isInteger(tier.upTo) || tier.upTo <= prev) throw new RangeError("tier limits must be increasing positive integers");
        prev = tier.upTo;
      });
    }

    export function graduated(tiers: Tier[], units: number): number {
      validateTiers(tiers);
      let remaining = checkUnits(units);
      let from = 0;
      let milli = 0;
      for (const tier of tiers) {
        if (remaining === 0) break;
        const size = tier.upTo === null ? remaining : tier.upTo - from;
        const take = Math.min(remaining, size);
        milli += take * tier.unitMilli;
        remaining -= take;
        from = tier.upTo === null ? from : tier.upTo;
      }
      return milli;
    }

    export function volume(tiers: Tier[], units: number): number {
      validateTiers(tiers);
      checkUnits(units);
      const tier = tiers.find((t) => t.upTo === null || units <= t.upTo) as Tier;
      return units * tier.unitMilli;
    }

    export function packages(units: number, blockSize: number, blockCents: number): number {
      if (!Number.isInteger(blockSize) || blockSize < 1) throw new RangeError("blockSize must be a positive integer");
      return Math.ceil(checkUnits(units) / blockSize) * blockCents;
    }
''')

PLAN = dd(r'''
    import { checkUnits, roundHalfUp } from "./money";
    import { Tier, graduated, packages, volume } from "./tiers";

    export interface Item {
      key: string;
      label: string;
      model: "graduated" | "volume" | "package" | "flat";
      tiers?: Tier[];
      blockSize?: number;
      blockCents?: number;
      flatCents?: number;
      freeUnits?: number;
    }

    export interface Plan {
      baseCents?: number;
      items: Item[];
      discountPct?: number;
      creditCents?: number;
      minimumCents?: number;
    }

    export interface Line {
      key: string;
      label: string;
      qty: number;
      cents: number;
    }

    export interface Invoice {
      lines: Line[];
      subtotalCents: number;
      discountCents: number;
      creditAppliedCents: number;
      trueUpCents: number;
      totalCents: number;
    }

    function priceItem(item: Item, usage: number): Line | null {
      if (item.model === "flat") return { key: item.key, label: item.label, qty: 1, cents: item.flatCents ?? 0 };
      const qty = Math.max(0, usage - (item.freeUnits ?? 0));
      let cents: number;
      if (item.model === "graduated") cents = roundHalfUp(graduated(item.tiers ?? [], qty), 1000);
      else if (item.model === "volume") cents = roundHalfUp(volume(item.tiers ?? [], qty), 1000);
      else cents = packages(qty, item.blockSize ?? 1, item.blockCents ?? 0);
      if (qty === 0 && cents === 0) return null;
      return { key: item.key, label: item.label, qty, cents };
    }

    export function price(plan: Plan, usage: Record<string, number>): Invoice {
      const lines: Line[] = [];
      let subtotal = plan.baseCents ?? 0;
      for (const item of plan.items) {
        const line = priceItem(item, checkUnits(usage[item.key] ?? 0));
        if (line !== null) {
          lines.push(line);
          subtotal += line.cents;
        }
      }
      const discount = roundHalfUp(subtotal * (plan.discountPct ?? 0), 100);
      const credit = Math.min(plan.creditCents ?? 0, subtotal - discount);
      const net = subtotal - discount - credit;
      const trueUp = Math.max(0, (plan.minimumCents ?? 0) - net);
      return { lines, subtotalCents: subtotal, discountCents: discount, creditAppliedCents: credit, trueUpCents: trueUp, totalCents: net + trueUp };
    }
''')

VISIBLE = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { roundHalfUp } from "../src/money";
    import { graduated } from "../src/tiers";

    const TIERS = [{ upTo: 1000, unitMilli: 500 }, { upTo: 10000, unitMilli: 300 }, { upTo: null, unitMilli: 100 }];

    test("round half up", () => {
      assert.equal(roundHalfUp(5, 2), 3);
      assert.equal(roundHalfUp(1499, 1000), 1);
    });

    test("graduated pricing", () => {
      assert.equal(graduated(TIERS, 2500), 950000);
    });
''')

HIDDEN = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { roundHalfUp, checkUnits } from "../src/money";
    import { graduated, volume, packages, validateTiers, Tier } from "../src/tiers";
    import { price, Plan } from "../src/plan";

    const TIERS: Tier[] = [{ upTo: 1000, unitMilli: 500 }, { upTo: 10000, unitMilli: 300 }, { upTo: null, unitMilli: 100 }];

    test("roundHalfUp", () => {
      assert.equal(roundHalfUp(0, 1000), 0);
      assert.equal(roundHalfUp(499, 1000), 0);
      assert.equal(roundHalfUp(500, 1000), 1);
      assert.equal(roundHalfUp(1499, 1000), 1);
      assert.equal(roundHalfUp(1500, 1000), 2);
      assert.equal(roundHalfUp(5, 2), 3);
      assert.equal(roundHalfUp(7, 3), 2);
      assert.equal(roundHalfUp(8, 3), 3);
      assert.equal(roundHalfUp(10, 5), 2);
      assert.equal(roundHalfUp(1234567, 100), 12346);
    });

    test("checkUnits", () => {
      assert.equal(checkUnits(0), 0);
      assert.equal(checkUnits(12), 12);
      for (const bad of [-1, 1.5, NaN, Infinity]) assert.throws(() => checkUnits(bad), RangeError);
    });

    test("validateTiers accepts good cards", () => {
      assert.doesNotThrow(() => validateTiers(TIERS));
      assert.doesNotThrow(() => validateTiers([{ upTo: null, unitMilli: 0 }]));
      assert.doesNotThrow(() => validateTiers([{ upTo: 1, unitMilli: 5 }, { upTo: 2, unitMilli: 0 }, { upTo: null, unitMilli: 1 }]));
    });

    test("validateTiers rejects bad cards", () => {
      assert.throws(() => validateTiers([]), RangeError);
      assert.throws(() => validateTiers([{ upTo: 10, unitMilli: 1 }]), RangeError);
      assert.throws(() => validateTiers([{ upTo: null, unitMilli: 1 }, { upTo: null, unitMilli: 1 }]), RangeError);
      assert.throws(() => validateTiers([{ upTo: null, unitMilli: 1 }, { upTo: 10, unitMilli: 1 }]), RangeError);
      assert.throws(() => validateTiers([{ upTo: 10, unitMilli: 1 }, { upTo: 10, unitMilli: 1 }, { upTo: null, unitMilli: 1 }]), RangeError);
      assert.throws(() => validateTiers([{ upTo: 10, unitMilli: 1 }, { upTo: 5, unitMilli: 1 }, { upTo: null, unitMilli: 1 }]), RangeError);
      assert.throws(() => validateTiers([{ upTo: 0, unitMilli: 1 }, { upTo: null, unitMilli: 1 }]), RangeError);
      assert.throws(() => validateTiers([{ upTo: -5, unitMilli: 1 }, { upTo: null, unitMilli: 1 }]), RangeError);
      assert.throws(() => validateTiers([{ upTo: 2.5, unitMilli: 1 }, { upTo: null, unitMilli: 1 }]), RangeError);
      assert.throws(() => validateTiers([{ upTo: null, unitMilli: -1 }]), RangeError);
      assert.throws(() => validateTiers([{ upTo: null, unitMilli: 0.5 }]), RangeError);
      assert.throws(() => validateTiers([{ upTo: 3, unitMilli: 1.5 }, { upTo: null, unitMilli: 1 }]), RangeError);
    });

    test("graduated", () => {
      assert.equal(graduated(TIERS, 0), 0);
      assert.equal(graduated(TIERS, 1), 500);
      assert.equal(graduated(TIERS, 1000), 500000);
      assert.equal(graduated(TIERS, 1001), 500300);
      assert.equal(graduated(TIERS, 2500), 950000);
      assert.equal(graduated(TIERS, 10000), 500000 + 9000 * 300);
      assert.equal(graduated(TIERS, 10001), 500000 + 2700000 + 100);
      assert.equal(graduated(TIERS, 25000), 500000 + 2700000 + 15000 * 100);
    });

    test("graduated with a free tier and a single tier", () => {
      const free: Tier[] = [{ upTo: 100, unitMilli: 0 }, { upTo: null, unitMilli: 250 }];
      assert.equal(graduated(free, 100), 0);
      assert.equal(graduated(free, 101), 250);
      assert.equal(graduated(free, 140), 10000);
      assert.equal(graduated([{ upTo: null, unitMilli: 7 }], 3), 21);
      assert.equal(graduated([{ upTo: 5, unitMilli: 1 }, { upTo: 6, unitMilli: 100 }, { upTo: null, unitMilli: 1000 }], 7), 5 + 100 + 1000);
    });

    test("graduated validates", () => {
      assert.throws(() => graduated(TIERS, -1), RangeError);
      assert.throws(() => graduated(TIERS, 2.5), RangeError);
      assert.throws(() => graduated([], 5), RangeError);
      assert.throws(() => graduated([{ upTo: 10, unitMilli: 1 }], 5), RangeError);
    });

    test("volume", () => {
      assert.equal(volume(TIERS, 0), 0);
      assert.equal(volume(TIERS, 1), 500);
      assert.equal(volume(TIERS, 1000), 500000);
      assert.equal(volume(TIERS, 1001), 300300);
      assert.equal(volume(TIERS, 2500), 750000);
      assert.equal(volume(TIERS, 10000), 3000000);
      assert.equal(volume(TIERS, 10001), 1000100);
      assert.equal(volume([{ upTo: null, unitMilli: 9 }], 10), 90);
    });

    test("volume validates", () => {
      assert.throws(() => volume(TIERS, -3), RangeError);
      assert.throws(() => volume(TIERS, 0.5), RangeError);
      assert.throws(() => volume([], 5), RangeError);
      assert.throws(() => volume([{ upTo: 5, unitMilli: 1 }], 5), RangeError);
    });

    test("packages", () => {
      assert.equal(packages(0, 1000, 250), 0);
      assert.equal(packages(1, 1000, 250), 250);
      assert.equal(packages(1000, 1000, 250), 250);
      assert.equal(packages(1001, 1000, 250), 500);
      assert.equal(packages(2500, 1000, 250), 750);
      assert.equal(packages(7, 1, 3), 21);
      assert.throws(() => packages(5, 0, 250), RangeError);
      assert.throws(() => packages(5, -2, 250), RangeError);
      assert.throws(() => packages(5, 1.5, 250), RangeError);
      assert.throws(() => packages(-5, 10, 250), RangeError);
      assert.throws(() => packages(5.5, 10, 250), RangeError);
    });

    const PLAN: Plan = {
      baseCents: 500,
      items: [
        { key: "requests", label: "API requests", model: "graduated", tiers: TIERS, freeUnits: 500 },
        { key: "bandwidth", label: "Bandwidth", model: "volume", tiers: TIERS },
        { key: "storage", label: "Storage blocks", model: "package", blockSize: 1000, blockCents: 250 },
        { key: "support", label: "Support", model: "flat", flatCents: 1999 },
      ],
    };

    test("price: lines in plan order, flat always present", () => {
      const inv = price(PLAN, { requests: 2500, bandwidth: 2500, storage: 1001 });
      assert.deepEqual(inv.lines, [
        { key: "requests", label: "API requests", qty: 2000, cents: 800 },
        { key: "bandwidth", label: "Bandwidth", qty: 2500, cents: 750 },
        { key: "storage", label: "Storage blocks", qty: 1001, cents: 500 },
        { key: "support", label: "Support", qty: 1, cents: 1999 },
      ]);
      assert.equal(inv.subtotalCents, 500 + 800 + 750 + 500 + 1999);
      assert.equal(inv.discountCents, 0);
      assert.equal(inv.creditAppliedCents, 0);
      assert.equal(inv.trueUpCents, 0);
      assert.equal(inv.totalCents, 4549);
    });

    test("price: unused metered items are left out, flat items stay", () => {
      const inv = price(PLAN, {});
      assert.deepEqual(inv.lines, [{ key: "support", label: "Support", qty: 1, cents: 1999 }]);
      assert.equal(inv.subtotalCents, 2499);
      assert.equal(inv.totalCents, 2499);
    });

    test("price: free units absorb small usage", () => {
      const inv = price(PLAN, { requests: 500 });
      assert.deepEqual(inv.lines.map((l) => l.key), ["support"]);
      const over = price(PLAN, { requests: 501 });
      assert.deepEqual(over.lines[0], { key: "requests", label: "API requests", qty: 1, cents: 1 });
      const under = price(PLAN, { requests: 200 });
      assert.deepEqual(under.lines.map((l) => l.key), ["support"]);
    });

    test("price: an item with usage but a zero amount stays, with a zero price it can vanish", () => {
      const cheap: Plan = { items: [{ key: "k", label: "Tiny", model: "graduated", tiers: [{ upTo: null, unitMilli: 1 }] }] };
      assert.deepEqual(price(cheap, { k: 3 }).lines, [{ key: "k", label: "Tiny", qty: 3, cents: 0 }]);
      assert.deepEqual(price(cheap, { k: 0 }).lines, []);
      const rounds: Plan = { items: [{ key: "k", label: "Half", model: "volume", tiers: [{ upTo: null, unitMilli: 500 }] }] };
      assert.equal(price(rounds, { k: 1 }).lines[0].cents, 1);
      assert.equal(price(rounds, { k: 3 }).lines[0].cents, 2);
      assert.equal(price(rounds, { k: 2 }).lines[0].cents, 1);
    });

    test("price: a line is rounded once, not per tier", () => {
      const plan: Plan = { items: [{ key: "k", label: "L", model: "graduated", tiers: [{ upTo: 1, unitMilli: 400 }, { upTo: null, unitMilli: 400 }] }] };
      // 3 * 400 = 1200 milli-cents = 1.2 cents -> 1; per-tier rounding would give 0 + 1
      assert.equal(price(plan, { k: 3 }).lines[0].cents, 1);
      const half: Plan = { items: [{ key: "k", label: "L", model: "graduated", tiers: [{ upTo: 1, unitMilli: 500 }, { upTo: null, unitMilli: 500 }] }] };
      assert.equal(price(half, { k: 3 }).lines[0].cents, 2);
    });

    test("price: discount rounds half up on the subtotal", () => {
      const plan: Plan = { baseCents: 1005, items: [], discountPct: 10 };
      const inv = price(plan, {});
      assert.equal(inv.discountCents, 101);
      assert.equal(inv.totalCents, 904);
      assert.equal(price({ baseCents: 1004, items: [], discountPct: 10 }, {}).discountCents, 100);
      assert.equal(price({ baseCents: 1000, items: [], discountPct: 12.5 }, {}).discountCents, 125);
      assert.equal(price({ baseCents: 999, items: [], discountPct: 100 }, {}).totalCents, 0);
    });

    test("price: credit is capped by what is left to pay", () => {
      const plan: Plan = { baseCents: 1000, items: [], discountPct: 10, creditCents: 5000 };
      const inv = price(plan, {});
      assert.equal(inv.discountCents, 100);
      assert.equal(inv.creditAppliedCents, 900);
      assert.equal(inv.totalCents, 0);
      const part = price({ baseCents: 1000, items: [], creditCents: 300 }, {});
      assert.equal(part.creditAppliedCents, 300);
      assert.equal(part.totalCents, 700);
      const exact = price({ baseCents: 1000, items: [], creditCents: 1000 }, {});
      assert.equal(exact.creditAppliedCents, 1000);
      assert.equal(exact.totalCents, 0);
    });

    test("price: minimum commitment trues up the total", () => {
      const below = price({ baseCents: 1000, items: [], minimumCents: 2500 }, {});
      assert.equal(below.trueUpCents, 1500);
      assert.equal(below.totalCents, 2500);
      const equal = price({ baseCents: 2500, items: [], minimumCents: 2500 }, {});
      assert.equal(equal.trueUpCents, 0);
      assert.equal(equal.totalCents, 2500);
      const above = price({ baseCents: 3000, items: [], minimumCents: 2500 }, {});
      assert.equal(above.trueUpCents, 0);
      assert.equal(above.totalCents, 3000);
    });

    test("price: the minimum is checked after discount and credit", () => {
      const inv = price({ baseCents: 4000, items: [], discountPct: 25, creditCents: 500, minimumCents: 3000 }, {});
      // subtotal 4000, discount 1000, credit 500 -> 2500 owed, below the 3000 minimum
      assert.equal(inv.discountCents, 1000);
      assert.equal(inv.creditAppliedCents, 500);
      assert.equal(inv.trueUpCents, 500);
      assert.equal(inv.totalCents, 3000);
      const zero = price({ baseCents: 100, items: [], creditCents: 100, minimumCents: 50 }, {});
      assert.equal(zero.creditAppliedCents, 100);
      assert.equal(zero.trueUpCents, 50);
      assert.equal(zero.totalCents, 50);
    });

    test("price: validation of usage", () => {
      assert.throws(() => price(PLAN, { requests: -1 }), RangeError);
      assert.throws(() => price(PLAN, { bandwidth: 1.5 }), RangeError);
      assert.throws(() => price(PLAN, { support: -4 }), RangeError);
      assert.throws(() => price(PLAN, { storage: NaN }), RangeError);
      assert.doesNotThrow(() => price(PLAN, { unknownKey: 12 }));
    });

    test("price: package items use their own free units and block rules", () => {
      const plan: Plan = { items: [{ key: "s", label: "S", model: "package", blockSize: 100, blockCents: 40, freeUnits: 250 }] };
      assert.deepEqual(price(plan, { s: 250 }).lines, []);
      assert.deepEqual(price(plan, { s: 251 }).lines, [{ key: "s", label: "S", qty: 1, cents: 40 }]);
      assert.deepEqual(price(plan, { s: 450 }).lines, [{ key: "s", label: "S", qty: 200, cents: 80 }]);
      assert.deepEqual(price(plan, { s: 451 }).lines, [{ key: "s", label: "S", qty: 201, cents: 120 }]);
    });

    test("price: volume items with free units move to a cheaper tier", () => {
      const plan: Plan = { items: [{ key: "v", label: "V", model: "volume", tiers: TIERS, freeUnits: 1500 }] };
      // 2500 usage - 1500 free = 1000 units, the first tier
      assert.equal(price(plan, { v: 2500 }).lines[0].cents, 500);
      assert.equal(price(plan, { v: 2501 }).lines[0].cents, 300);
    });
''')

LIB = Lib(
    name="ratecard", lang="typescript", title="the ratecard pricing library",
    blurb="The hosting platform's invoicing job turns metered usage into invoice lines with ratecard.",
    files={"package.json": PACKAGE_JSON % "ratecard", "tsconfig.json": TSCONFIG, "types/node-shim.d.ts": TS_NODE_SHIM,
           "src/money.ts": MONEY, "src/tiers.ts": TIERS, "src/plan.ts": PLAN, "README.md": README, ".gitignore": "node_modules/\nbuild/\n"},
    visible_tests={"test/basic.test.ts": VISIBLE},
    hidden_tests={"test/full.test.ts": HIDDEN},
    mutate=["src/tiers.ts", "src/plan.ts", "src/money.ts"], difficulty=3, tags=["billing", "tiers", "invoicing"],
    verify=TS_VERIFY,
    probe_import="const { roundHalfUp, checkUnits } = require('./build/src/money');\nconst { graduated, volume, packages, validateTiers } = require('./build/src/tiers');\nconst { price } = require('./build/src/plan');",
    probes=[
        'roundHalfUp(1500, 1000)',
        'roundHalfUp(5, 2)',
        'graduated([{ upTo: 1000, unitMilli: 500 }, { upTo: 10000, unitMilli: 300 }, { upTo: null, unitMilli: 100 }], 1001)',
        'graduated([{ upTo: 1000, unitMilli: 500 }, { upTo: 10000, unitMilli: 300 }, { upTo: null, unitMilli: 100 }], 2500)',
        'graduated([{ upTo: 1000, unitMilli: 500 }, { upTo: 10000, unitMilli: 300 }, { upTo: null, unitMilli: 100 }], 10001)',
        'volume([{ upTo: 1000, unitMilli: 500 }, { upTo: 10000, unitMilli: 300 }, { upTo: null, unitMilli: 100 }], 1000)',
        'volume([{ upTo: 1000, unitMilli: 500 }, { upTo: 10000, unitMilli: 300 }, { upTo: null, unitMilli: 100 }], 1001)',
        'volume([{ upTo: 1000, unitMilli: 500 }, { upTo: 10000, unitMilli: 300 }, { upTo: null, unitMilli: 100 }], 10001)',
        'packages(1000, 1000, 250)',
        'packages(1001, 1000, 250)',
        'packages(0, 1000, 250)',
        'validateTiers([{ upTo: 10, unitMilli: 1 }, { upTo: 10, unitMilli: 1 }, { upTo: null, unitMilli: 1 }])',
        'validateTiers([{ upTo: 10, unitMilli: 1 }])',
        "price({ baseCents: 500, items: [{ key: 'requests', label: 'API requests', model: 'graduated', tiers: [{ upTo: 1000, unitMilli: 500 }, { upTo: 10000, unitMilli: 300 }, { upTo: null, unitMilli: 100 }], freeUnits: 500 }, { key: 'support', label: 'Support', model: 'flat', flatCents: 1999 }] }, { requests: 2500 }).totalCents",
        "price({ baseCents: 500, items: [{ key: 'requests', label: 'API requests', model: 'graduated', tiers: [{ upTo: 1000, unitMilli: 500 }, { upTo: 10000, unitMilli: 300 }, { upTo: null, unitMilli: 100 }], freeUnits: 500 }, { key: 'support', label: 'Support', model: 'flat', flatCents: 1999 }] }, {}).lines",
        "price({ baseCents: 500, items: [{ key: 'requests', label: 'API requests', model: 'graduated', tiers: [{ upTo: 1000, unitMilli: 500 }, { upTo: 10000, unitMilli: 300 }, { upTo: null, unitMilli: 100 }], freeUnits: 500 }, { key: 'support', label: 'Support', model: 'flat', flatCents: 1999 }] }, { requests: 501 }).lines[0]",
        'price({ baseCents: 1005, items: [], discountPct: 10 }, {}).discountCents',
        'price({ baseCents: 1000, items: [], discountPct: 10, creditCents: 5000 }, {})',
        'price({ baseCents: 4000, items: [], discountPct: 25, creditCents: 500, minimumCents: 3000 }, {})',
        'price({ baseCents: 2500, items: [], minimumCents: 2500 }, {}).trueUpCents',
        "price({ items: [{ key: 'k', label: 'L', model: 'graduated', tiers: [{ upTo: 1, unitMilli: 400 }, { upTo: null, unitMilli: 400 }] }] }, { k: 3 }).lines[0].cents",
        "price({ baseCents: 500, items: [{ key: 'requests', label: 'API requests', model: 'graduated', tiers: [{ upTo: 1000, unitMilli: 500 }, { upTo: 10000, unitMilli: 300 }, { upTo: null, unitMilli: 100 }], freeUnits: 500 }, { key: 'support', label: 'Support', model: 'flat', flatCents: 1999 }] }, { requests: -1 })",
    ],
)

register_libs([LIB], n=8)
