"""Checkout wizard flow with guards, skipped steps and history (typescript): bugs injected into a small state machine."""
from fx import Lib, dd
from generators.fix._lang2 import PACKAGE_JSON, TS_NODE_SHIM, TS_VERIFY, TSCONFIG, register_libs

README = dd(r'''
    # stepper

    The multi-step flow of a checkout page. TypeScript, no dependencies. `import { Wizard } from './src/wizard'`,
    `import { progress } from './src/progress'`.

    ## Steps

    A step is `{ id, guard?, skipIf? }`: `guard(data)` returns `true` to let the user leave the step, or a string with the error
    message; `skipIf(data)` returns `true` when the step does not apply for the current data.

    ## `new Wizard(steps, data)`

    `steps` must contain at least one step and every `id` must be a non-empty string and unique (`Error`). `data` is copied.
    The wizard starts on the first step that is not skipped for `data`; if every step is skipped it is an `Error`.

    * `current` is the id of the current step, `null` when the wizard is done. `done` is `true` after the last step was passed.
    * `values` returns a copy of the data; `set(patch)` merges `patch` into it (skip conditions and guards see the new data from
      then on).
    * `canNext()` is `true` when the wizard is not done and the current step's guard (if any) returns `true`.
    * `next()` on a wizard that is done is an `Error`. Otherwise it runs the current step's guard: a message `m` gives
      `{ ok: false, error: m }` and nothing changes. On success the current step is remembered in the *trail* and the wizard moves
      to the next step after it that is not skipped by the data **now**: `{ ok: true, done: false, step: id }`. If there is none the
      wizard is done: `{ ok: true, done: true, step: null }`.
    * `back()` returns to the step most recently left (the end of the trail, which skips steps that were never visited) and
      returns `true`; with an empty trail (and not done) it returns `false`. On a finished wizard it reopens the last step. It does
      not run guards, and the left step is removed from the trail.
    * `jump(id)` goes back to a step that is in the trail (`id` of the current step does nothing): that step becomes current and
      it and everything after it leaves the trail; a done wizard becomes active again. Any other id (unvisited, unknown, or later) is
      an `Error`.
    * `trail` is the ids of the steps left so far, oldest first.

    ## `progress(wizard)` (`src/progress.ts`)

    `{ index, total }` for a progress bar. `total` is the number of steps that are not skipped for the current data. `index` is the
    1-based position of the current step among them: the number of those non-skipped steps that come at or before the current one;
    when the wizard is done `index === total`. (`progress` needs the wizard's step list: use `wizard.steps`, a read-only copy of
    the steps, and `wizard.position`, the index of the current step in it, `-1` when done.)
''')

WIZARD = dd(r'''
    export interface Step<D> {
      id: string;
      guard?: (data: D) => true | string;
      skipIf?: (data: D) => boolean;
    }

    export type Outcome = { ok: true; done: boolean; step: string | null } | { ok: false; error: string };

    export class Wizard<D extends object> {
      private data: D;
      private at: number;
      private finished = false;
      private readonly path: number[] = [];
      private readonly list: Step<D>[];

      constructor(steps: Step<D>[], data: D) {
        if (steps.length === 0) throw new Error("a wizard needs at least one step");
        const seen = new Set<string>();
        for (const s of steps) {
          if (typeof s.id !== "string" || s.id === "") throw new Error("step ids must be non-empty strings");
          if (seen.has(s.id)) throw new Error(`duplicate step id ${s.id}`);
          seen.add(s.id);
        }
        this.list = steps.slice();
        this.data = { ...data };
        const first = this.firstFrom(0);
        if (first < 0) throw new Error("every step is skipped");
        this.at = first;
      }

      private skipped(i: number): boolean {
        const skip = this.list[i].skipIf;
        return skip !== undefined && skip(this.data);
      }

      private firstFrom(i: number): number {
        for (let k = i; k < this.list.length; k++) {
          if (!this.skipped(k)) return k;
        }
        return -1;
      }

      get steps(): Step<D>[] {
        return this.list.slice();
      }

      get position(): number {
        return this.finished ? -1 : this.at;
      }

      get current(): string | null {
        return this.finished ? null : this.list[this.at].id;
      }

      get done(): boolean {
        return this.finished;
      }

      get values(): D {
        return { ...this.data };
      }

      get trail(): string[] {
        return this.path.map((i) => this.list[i].id);
      }

      set(patch: Partial<D>): void {
        this.data = { ...this.data, ...patch };
      }

      private verdict(): true | string {
        const guard = this.list[this.at].guard;
        return guard === undefined ? true : guard(this.data);
      }

      canNext(): boolean {
        return !this.finished && this.verdict() === true;
      }

      next(): Outcome {
        if (this.finished) throw new Error("the wizard is done");
        const v = this.verdict();
        if (v !== true) return { ok: false, error: v };
        this.path.push(this.at);
        const following = this.firstFrom(this.at + 1);
        if (following < 0) {
          this.finished = true;
          return { ok: true, done: true, step: null };
        }
        this.at = following;
        return { ok: true, done: false, step: this.list[following].id };
      }

      back(): boolean {
        if (this.path.length === 0) return false;
        this.at = this.path.pop() as number;
        this.finished = false;
        return true;
      }

      jump(id: string): void {
        const target = this.list.findIndex((s) => s.id === id);
        if (!this.finished && target === this.at) return;
        const where = this.path.indexOf(target);
        if (target < 0 || where < 0) throw new Error(`cannot jump to ${id}`);
        this.path.length = where;
        this.at = target;
        this.finished = false;
      }
    }
''')

PROGRESS = dd(r'''
    import { Wizard } from "./wizard";

    export function progress<D extends object>(wizard: Wizard<D>): { index: number; total: number } {
      const values = wizard.values;
      const live: number[] = [];
      wizard.steps.forEach((step, i) => {
        if (step.skipIf === undefined || !step.skipIf(values)) live.push(i);
      });
      if (wizard.done) return { index: live.length, total: live.length };
      const here = wizard.position;
      return { index: live.filter((i) => i <= here).length, total: live.length };
    }
''')

VISIBLE = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { Wizard, Step } from "../src/wizard";

    interface Order { email?: string }
    const steps: Step<Order>[] = [{ id: "account" }, { id: "review" }];

    test("walks through the steps", () => {
      const w = new Wizard<Order>(steps, {});
      assert.equal(w.current, "account");
      assert.deepEqual(w.next(), { ok: true, done: false, step: "review" });
      assert.deepEqual(w.next(), { ok: true, done: true, step: null });
      assert.equal(w.done, true);
    });
''')

HIDDEN = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { Wizard, Step } from "../src/wizard";
    import { progress } from "../src/progress";

    interface Order {
      email?: string;
      digital?: boolean;
      card?: string;
      gift?: boolean;
    }

    const steps: Step<Order>[] = [
      { id: "account", guard: (d) => (d.email !== undefined && d.email.includes("@") ? true : "email") },
      { id: "shipping", skipIf: (d) => d.digital === true },
      { id: "gift", skipIf: (d) => d.gift !== true },
      { id: "payment", guard: (d) => (d.card !== undefined && d.card.length === 4 ? true : "card") },
      { id: "review" },
    ];
    const make = (data: Order = {}) => new Wizard<Order>(steps, data);

    test("construction rules", () => {
      assert.throws(() => new Wizard<Order>([], {}), Error);
      assert.throws(() => new Wizard<Order>([{ id: "a" }, { id: "a" }], {}), Error);
      assert.throws(() => new Wizard<Order>([{ id: "" }], {}), Error);
      assert.throws(() => new Wizard<Order>([{ id: "a", skipIf: () => true }, { id: "b", skipIf: () => true }], {}), Error);
      assert.doesNotThrow(() => new Wizard<Order>([{ id: "a" }], {}));
    });

    test("starts on the first step that is not skipped", () => {
      assert.equal(make().current, "account");
      const w = new Wizard<Order>([{ id: "a", skipIf: () => true }, { id: "b", skipIf: () => true }, { id: "c" }], {});
      assert.equal(w.current, "c");
      assert.deepEqual(w.trail, []);
      assert.equal(w.back(), false);
    });

    test("a failing guard keeps the wizard where it is", () => {
      const w = make();
      assert.equal(w.canNext(), false);
      assert.deepEqual(w.next(), { ok: false, error: "email" });
      assert.equal(w.current, "account");
      assert.deepEqual(w.trail, []);
      w.set({ email: "nobody" });
      assert.deepEqual(w.next(), { ok: false, error: "email" });
      w.set({ email: "me@example.org" });
      assert.equal(w.canNext(), true);
      assert.deepEqual(w.next(), { ok: true, done: false, step: "shipping" });
      assert.deepEqual(w.trail, ["account"]);
    });

    test("skipped steps are passed over", () => {
      const w = make({ email: "a@b", gift: false });
      assert.deepEqual(w.next(), { ok: true, done: false, step: "shipping" });
      assert.deepEqual(w.next(), { ok: true, done: false, step: "payment" });
      assert.deepEqual(w.trail, ["account", "shipping"]);
    });

    test("several steps can be skipped in a row", () => {
      const w = make({ email: "a@b", digital: true, gift: false });
      assert.deepEqual(w.next(), { ok: true, done: false, step: "payment" });
      const g = make({ email: "a@b", digital: true, gift: true });
      assert.deepEqual(g.next(), { ok: true, done: false, step: "gift" });
    });

    test("skip conditions are checked at the moment of moving", () => {
      const w = make({ email: "a@b" });
      w.set({ digital: true });
      assert.deepEqual(w.next(), { ok: true, done: false, step: "payment" });
      const v = make({ email: "a@b" });
      v.set({ gift: true });
      v.next();
      assert.deepEqual(v.next(), { ok: true, done: false, step: "gift" });
    });

    test("finishing", () => {
      const w = make({ email: "a@b", digital: true, card: "1234" });
      assert.deepEqual(w.next(), { ok: true, done: false, step: "payment" });
      assert.deepEqual(w.next(), { ok: true, done: false, step: "review" });
      assert.equal(w.done, false);
      assert.deepEqual(w.next(), { ok: true, done: true, step: null });
      assert.equal(w.done, true);
      assert.equal(w.current, null);
      assert.equal(w.canNext(), false);
      assert.throws(() => w.next(), Error);
      assert.deepEqual(w.trail, ["account", "payment", "review"]);
    });

    test("trailing skipped steps end the wizard early", () => {
      const w = new Wizard<Order>([{ id: "a" }, { id: "b", skipIf: () => true }], {});
      assert.deepEqual(w.next(), { ok: true, done: true, step: null });
    });

    test("back follows the trail, not the step order", () => {
      const w = make({ email: "a@b", digital: true });
      w.next();
      assert.equal(w.current, "payment");
      assert.equal(w.back(), true);
      assert.equal(w.current, "account");
      assert.deepEqual(w.trail, []);
      assert.equal(w.back(), false);
      assert.equal(w.current, "account");
    });

    test("back after a few steps and forward again", () => {
      const w = make({ email: "a@b", card: "9999" });
      w.next();
      w.next();
      assert.equal(w.current, "payment");
      assert.deepEqual(w.trail, ["account", "shipping"]);
      w.back();
      assert.equal(w.current, "shipping");
      assert.deepEqual(w.trail, ["account"]);
      w.set({ digital: true });
      assert.deepEqual(w.next(), { ok: true, done: false, step: "payment" });
      assert.deepEqual(w.trail, ["account", "shipping"]);
    });

    test("back from a finished wizard reopens the last step", () => {
      const w = make({ email: "a@b", digital: true, card: "1234" });
      w.next();
      w.next();
      w.next();
      assert.equal(w.done, true);
      assert.equal(w.back(), true);
      assert.equal(w.done, false);
      assert.equal(w.current, "review");
      assert.deepEqual(w.trail, ["account", "payment"]);
      assert.deepEqual(w.next(), { ok: true, done: true, step: null });
    });

    test("back does not run guards", () => {
      const w = make({ email: "a@b", digital: true });
      w.next();
      w.set({ email: "broken" });
      assert.equal(w.back(), true);
      assert.equal(w.current, "account");
    });

    test("jump goes back to visited steps only", () => {
      const w = make({ email: "a@b", card: "1234" });
      w.next();
      w.next();
      w.next();
      assert.equal(w.current, "review");
      assert.deepEqual(w.trail, ["account", "shipping", "payment"]);
      w.jump("shipping");
      assert.equal(w.current, "shipping");
      assert.deepEqual(w.trail, ["account"]);
      assert.throws(() => w.jump("payment"), Error);
      assert.throws(() => w.jump("review"), Error);
      assert.throws(() => w.jump("nowhere"), Error);
      w.jump("shipping");
      assert.equal(w.current, "shipping");
      assert.deepEqual(w.trail, ["account"]);
      w.jump("account");
      assert.equal(w.current, "account");
      assert.deepEqual(w.trail, []);
    });

    test("jump from a finished wizard", () => {
      const w = make({ email: "a@b", digital: true, card: "1234" });
      w.next();
      w.next();
      w.next();
      assert.equal(w.done, true);
      w.jump("account");
      assert.equal(w.done, false);
      assert.equal(w.current, "account");
      assert.deepEqual(w.trail, []);
      const v = make({ email: "a@b", digital: true, card: "1234" });
      v.next();
      v.next();
      v.next();
      v.jump("review");
      assert.equal(v.current, "review");
      assert.deepEqual(v.trail, ["account", "payment"]);
    });

    test("values are copies and set merges", () => {
      const start: Order = { email: "a@b" };
      const w = make(start);
      start.email = "changed";
      assert.equal(w.values.email, "a@b");
      w.set({ card: "1234" });
      w.set({ gift: true });
      assert.deepEqual(w.values, { email: "a@b", card: "1234", gift: true });
      const copy = w.values;
      copy.email = "x";
      assert.equal(w.values.email, "a@b");
    });

    test("progress counts the steps that apply", () => {
      const w = make({ email: "a@b" });
      assert.deepEqual(progress(w), { index: 1, total: 4 });
      w.next();
      assert.deepEqual(progress(w), { index: 2, total: 4 });
      w.set({ gift: true });
      assert.deepEqual(progress(w), { index: 2, total: 5 });
      w.next();
      assert.deepEqual(progress(w), { index: 3, total: 5 });
      w.set({ digital: true });
      assert.deepEqual(progress(w), { index: 2, total: 4 });
    });

    test("progress at the end and with skipped starts", () => {
      const w = make({ email: "a@b", digital: true, card: "1234" });
      assert.deepEqual(progress(w), { index: 1, total: 3 });
      w.next();
      w.next();
      assert.deepEqual(progress(w), { index: 3, total: 3 });
      w.next();
      assert.deepEqual(progress(w), { index: 3, total: 3 });
      const s = new Wizard<Order>([{ id: "a", skipIf: () => true }, { id: "b" }, { id: "c" }], {});
      assert.deepEqual(progress(s), { index: 1, total: 2 });
    });
''')

LIB = Lib(
    name="stepper", lang="typescript", title="the stepper flow library",
    blurb="The checkout page drives its multi-step form with stepper: guards, steps that can be skipped, and a trail to go back along.",
    files={"package.json": PACKAGE_JSON % "stepper", "tsconfig.json": TSCONFIG, "types/node-shim.d.ts": TS_NODE_SHIM,
           "src/wizard.ts": WIZARD, "src/progress.ts": PROGRESS, "README.md": README, ".gitignore": "node_modules/\nbuild/\n"},
    visible_tests={"test/basic.test.ts": VISIBLE},
    hidden_tests={"test/full.test.ts": HIDDEN},
    mutate=["src/wizard.ts", "src/progress.ts"], difficulty=2, tags=["state-machine", "wizard", "forms"],
    verify=TS_VERIFY,
)

register_libs([LIB], n=8)
