"""Feature-flag evaluation with rollouts, rules and prerequisites (typescript): bugs injected into a flag library."""
from fx import Lib, dd
from generators.fix._lang2 import PACKAGE_JSON, TS_NODE_SHIM, TS_VERIFY, TSCONFIG, register_libs

README = dd(r'''
    # flagrules

    A small feature-flag evaluator for the web app's experiments. TypeScript, no dependencies.
    `import { evaluate } from './src/evaluate'`, `import { bucket, fnv1a } from './src/hash'`,
    `import { matchCond, compareVersions } from './src/cond'`.

    ## `src/hash.ts`

    * `fnv1a(text)`: the 32-bit FNV-1a hash of the UTF-16 code units of `text`, as an unsigned number. Start with
      `2166136261`; for every code unit XOR it into the hash, then multiply by `16777619` modulo 2^32.
      (`fnv1a('') === 2166136261`, `fnv1a('a') === 3826002220`.)
    * `bucket(key, userId, salt = '')`: a stable number in `0..9999`: `fnv1a(text) % 10000`, where `text` is `key:userId`, or
      `salt:key:userId` when `salt` is not empty.

    ## `src/cond.ts`

    * `compareVersions(a, b)`: compares dotted numeric versions (`'1.10.2'`). Each part must be digits only, otherwise the
      result is `null`. Parts are compared as numbers from the left, a missing part counts as `0` (`'1.2'` equals `'1.2.0'`).
      Returns `-1`, `0` or `1`.
    * `matchCond(cond, attrs)`: a condition is `{ attr, op, value }`. A user attribute that is missing (`undefined`) makes
      the condition false, except for `ne` and `nin`, which are then true. Otherwise, with `actual = attrs[attr]`:
      `eq` and `ne` compare with `===` / `!==`; `in` / `nin` need `value` to be an array and test membership (`nin`
      is false when `value` is not an array); `gt`, `gte`, `lt`, `lte` need both sides to be numbers; `startsWith` and
      `contains` need both to be strings (`contains` is substring search); `semverGte` needs both to be strings and
      `compareVersions(actual, value)` to be `0` or `1` (a `null` comparison is false).

    ## `src/evaluate.ts`

    `evaluate(flag, ctx, flags = {}, trail = [])` returns `{ on, reason }`. A flag is
    `{ key, enabled, requires?, allow?, deny?, rules?, rollout?, salt? }`; `ctx` is `{ userId, attrs? }`; `flags` maps keys to
    flags (for prerequisites). The first step that applies decides:

    1. `enabled` is false: off, reason `'disabled'`.
    2. If `flag.key` is already in `trail`, an `Error` is thrown (a prerequisite cycle). Then each key of `requires`, in order:
       a key missing from `flags` gives off with reason `'prerequisite-missing:<key>'`; a prerequisite that evaluates to off
       (with `trail` extended by this flag's key) gives off with reason `'prerequisite:<key>'`.
    3. `userId` in `deny`: off, `'denied'`. Then `userId` in `allow`: on, `'allowed'` (deny wins over allow).
    4. `rules`, in order: the first rule whose conditions (`when`, all must match) match decides, with reason `'rule:<index>'`.
       Its `serve` is `'on'`, `'off'`, or `{ rollout: pct }`, which is on when the user is inside that percentage.
    5. A `rollout` percentage on the flag: on when the user is inside it, reason `'rollout'`.
    6. Otherwise on, reason `'default'`.

    A user is *inside* a rollout of `pct` percent when `bucket(flag.key, userId, flag.salt) < Math.round(pct * 100)`. So `0`
    admits nobody and `100` everybody.
''')

HASH = dd(r'''
    export function fnv1a(text: string): number {
      let hash = 2166136261;
      for (let i = 0; i < text.length; i++) {
        hash = (hash ^ text.charCodeAt(i)) >>> 0;
        hash = Math.imul(hash, 16777619) >>> 0;
      }
      return hash;
    }

    export function bucket(key: string, userId: string, salt = ""): number {
      const text = salt === "" ? `${key}:${userId}` : `${salt}:${key}:${userId}`;
      return fnv1a(text) % 10000;
    }
''')

COND = dd(r'''
    export type Value = string | number | boolean;
    export type Op = "eq" | "ne" | "in" | "nin" | "gt" | "gte" | "lt" | "lte" | "startsWith" | "contains" | "semverGte";

    export interface Cond {
      attr: string;
      op: Op;
      value: Value | Value[];
    }

    export function compareVersions(a: string, b: string): number | null {
      const left = a.split(".");
      const right = b.split(".");
      if (![...left, ...right].every((part) => /^\d+$/.test(part))) return null;
      const n = Math.max(left.length, right.length);
      for (let i = 0; i < n; i++) {
        const x = Number(left[i] ?? "0");
        const y = Number(right[i] ?? "0");
        if (x !== y) return x < y ? -1 : 1;
      }
      return 0;
    }

    export function matchCond(cond: Cond, attrs: Record<string, Value>): boolean {
      const actual = attrs[cond.attr];
      const want = cond.value;
      if (actual === undefined) return cond.op === "ne" || cond.op === "nin";
      switch (cond.op) {
        case "eq":
          return actual === want;
        case "ne":
          return actual !== want;
        case "in":
          return Array.isArray(want) && want.includes(actual);
        case "nin":
          return Array.isArray(want) && !want.includes(actual);
        case "gt":
          return typeof actual === "number" && typeof want === "number" && actual > want;
        case "gte":
          return typeof actual === "number" && typeof want === "number" && actual >= want;
        case "lt":
          return typeof actual === "number" && typeof want === "number" && actual < want;
        case "lte":
          return typeof actual === "number" && typeof want === "number" && actual <= want;
        case "startsWith":
          return typeof actual === "string" && typeof want === "string" && actual.startsWith(want);
        case "contains":
          return typeof actual === "string" && typeof want === "string" && actual.includes(want);
        case "semverGte": {
          if (typeof actual !== "string" || typeof want !== "string") return false;
          const c = compareVersions(actual, want);
          return c !== null && c >= 0;
        }
      }
    }
''')

EVALUATE = dd(r'''
    import { Cond, Value, matchCond } from "./cond";
    import { bucket } from "./hash";

    export type Serve = "on" | "off" | { rollout: number };

    export interface Rule {
      when: Cond[];
      serve: Serve;
    }

    export interface Flag {
      key: string;
      enabled: boolean;
      requires?: string[];
      allow?: string[];
      deny?: string[];
      rules?: Rule[];
      rollout?: number;
      salt?: string;
    }

    export interface Context {
      userId: string;
      attrs?: Record<string, Value>;
    }

    export interface Decision {
      on: boolean;
      reason: string;
    }

    function inside(flag: Flag, userId: string, pct: number): boolean {
      return bucket(flag.key, userId, flag.salt) < Math.round(pct * 100);
    }

    export function evaluate(flag: Flag, ctx: Context, flags: Record<string, Flag> = {}, trail: string[] = []): Decision {
      if (!flag.enabled) return { on: false, reason: "disabled" };
      if (trail.includes(flag.key)) throw new Error(`prerequisite cycle at ${flag.key}`);
      for (const req of flag.requires ?? []) {
        const dep = flags[req];
        if (dep === undefined) return { on: false, reason: `prerequisite-missing:${req}` };
        if (!evaluate(dep, ctx, flags, [...trail, flag.key]).on) return { on: false, reason: `prerequisite:${req}` };
      }
      if ((flag.deny ?? []).includes(ctx.userId)) return { on: false, reason: "denied" };
      if ((flag.allow ?? []).includes(ctx.userId)) return { on: true, reason: "allowed" };
      const rules = flag.rules ?? [];
      for (let i = 0; i < rules.length; i++) {
        const rule = rules[i];
        if (!rule.when.every((c) => matchCond(c, ctx.attrs ?? {}))) continue;
        const on = rule.serve === "on" ? true : rule.serve === "off" ? false : inside(flag, ctx.userId, rule.serve.rollout);
        return { on, reason: `rule:${i}` };
      }
      if (flag.rollout !== undefined) return { on: inside(flag, ctx.userId, flag.rollout), reason: "rollout" };
      return { on: true, reason: "default" };
    }
''')

VISIBLE = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { fnv1a } from "../src/hash";
    import { evaluate } from "../src/evaluate";

    test("fnv1a", () => {
      assert.equal(fnv1a(""), 2166136261);
      assert.equal(fnv1a("a"), 3826002220);
    });

    test("a disabled flag is off", () => {
      assert.deepEqual(evaluate({ key: "x", enabled: false }, { userId: "u1" }), { on: false, reason: "disabled" });
      assert.deepEqual(evaluate({ key: "x", enabled: true }, { userId: "u1" }), { on: true, reason: "default" });
    });
''')

HIDDEN = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { fnv1a, bucket } from "../src/hash";
    import { compareVersions, matchCond, Cond, Value } from "../src/cond";
    import { evaluate, Flag } from "../src/evaluate";

    const ctx = (userId: string, attrs: Record<string, Value> = {}) => ({ userId, attrs });
    const cond = (attr: string, op: Cond["op"], value: Cond["value"]): Cond => ({ attr, op, value });

    test("fnv1a reference values", () => {
      assert.equal(fnv1a(""), 2166136261);
      assert.equal(fnv1a("a"), 3826002220);
      assert.equal(fnv1a("foobar"), 3214735720);
      assert.equal(fnv1a("checkout:u1"), 117740815);
      assert.equal(fnv1a("é"), fnv1a("é"));
      assert.notEqual(fnv1a("ab"), fnv1a("ba"));
    });

    test("bucket", () => {
      assert.equal(bucket("new-checkout", "u1"), 6576);
      assert.equal(bucket("new-checkout", "u3"), 1814);
      assert.equal(bucket("new-checkout", "bob"), 9993);
      assert.equal(bucket("new-checkout", "u4", "s2"), 82);
      assert.equal(bucket("new-checkout", "u1", "s2"), 7225);
      assert.equal(bucket("beta-ui", "u1"), 4952);
      assert.equal(bucket("beta-ui", "u3"), 190);
      assert.equal(bucket("new-checkout", "u1", ""), bucket("new-checkout", "u1"));
      for (let i = 0; i < 200; i++) {
        const b = bucket("k", `user-${i}`);
        assert.ok(b >= 0 && b < 10000);
      }
    });

    test("compareVersions", () => {
      assert.equal(compareVersions("1.2.3", "1.2.3"), 0);
      assert.equal(compareVersions("1.2", "1.2.0"), 0);
      assert.equal(compareVersions("1.2.0.0", "1.2"), 0);
      assert.equal(compareVersions("1.10", "1.9"), 1);
      assert.equal(compareVersions("1.9", "1.10"), -1);
      assert.equal(compareVersions("2", "1.99.99"), 1);
      assert.equal(compareVersions("1.2.1", "1.2"), 1);
      assert.equal(compareVersions("1.2", "1.2.1"), -1);
      assert.equal(compareVersions("0.9", "1"), -1);
      assert.equal(compareVersions("10.0.0", "9.9.9"), 1);
      assert.equal(compareVersions("007", "7"), 0);
    });

    test("compareVersions rejects non numeric parts", () => {
      assert.equal(compareVersions("1.x", "1.2"), null);
      assert.equal(compareVersions("1.2", "1.2-beta"), null);
      assert.equal(compareVersions("", "1"), null);
      assert.equal(compareVersions("1", ""), null);
      assert.equal(compareVersions("1..2", "1.2"), null);
      assert.equal(compareVersions("v1", "1"), null);
      assert.equal(compareVersions("-1", "1"), null);
      assert.equal(compareVersions("1.5", "1.5."), null);
    });

    test("matchCond: equality and membership", () => {
      const attrs = { plan: "pro", seats: 5, beta: true };
      assert.equal(matchCond(cond("plan", "eq", "pro"), attrs), true);
      assert.equal(matchCond(cond("plan", "eq", "free"), attrs), false);
      assert.equal(matchCond(cond("seats", "eq", 5), attrs), true);
      assert.equal(matchCond(cond("seats", "eq", "5"), attrs), false);
      assert.equal(matchCond(cond("beta", "eq", true), attrs), true);
      assert.equal(matchCond(cond("plan", "ne", "free"), attrs), true);
      assert.equal(matchCond(cond("plan", "ne", "pro"), attrs), false);
      assert.equal(matchCond(cond("plan", "in", ["free", "pro"]), attrs), true);
      assert.equal(matchCond(cond("plan", "in", ["free", "team"]), attrs), false);
      assert.equal(matchCond(cond("plan", "in", "pro"), attrs), false);
      assert.equal(matchCond(cond("plan", "nin", ["free", "team"]), attrs), true);
      assert.equal(matchCond(cond("plan", "nin", ["pro"]), attrs), false);
      assert.equal(matchCond(cond("plan", "nin", "free"), attrs), false);
      assert.equal(matchCond(cond("seats", "in", [5, 6]), attrs), true);
    });

    test("matchCond: missing attributes", () => {
      for (const op of ["eq", "in", "gt", "gte", "lt", "lte", "startsWith", "contains", "semverGte"] as const) {
        assert.equal(matchCond(cond("nope", op, op === "in" ? ["x"] : "x"), {}), false, op);
      }
      assert.equal(matchCond(cond("nope", "ne", "x"), {}), true);
      assert.equal(matchCond(cond("nope", "nin", ["x"]), {}), true);
    });

    test("matchCond: numbers", () => {
      const attrs = { age: 30, name: "bob" };
      assert.equal(matchCond(cond("age", "gt", 29), attrs), true);
      assert.equal(matchCond(cond("age", "gt", 30), attrs), false);
      assert.equal(matchCond(cond("age", "gte", 30), attrs), true);
      assert.equal(matchCond(cond("age", "gte", 31), attrs), false);
      assert.equal(matchCond(cond("age", "lt", 31), attrs), true);
      assert.equal(matchCond(cond("age", "lt", 30), attrs), false);
      assert.equal(matchCond(cond("age", "lte", 30), attrs), true);
      assert.equal(matchCond(cond("age", "lte", 29), attrs), false);
      assert.equal(matchCond(cond("name", "gt", 1), attrs), false);
      assert.equal(matchCond(cond("age", "gt", "1"), attrs), false);
      assert.equal(matchCond(cond("age", "lt", "99"), attrs), false);
      assert.equal(matchCond(cond("name", "lt", "zed"), attrs), false);
    });

    test("matchCond: strings and versions", () => {
      const attrs = { email: "ann@corp.example", app: "2.10.1", n: 3 };
      assert.equal(matchCond(cond("email", "startsWith", "ann@"), attrs), true);
      assert.equal(matchCond(cond("email", "startsWith", "corp"), attrs), false);
      assert.equal(matchCond(cond("email", "contains", "corp"), attrs), true);
      assert.equal(matchCond(cond("email", "contains", "other"), attrs), false);
      assert.equal(matchCond(cond("n", "startsWith", "3"), attrs), false);
      assert.equal(matchCond(cond("email", "contains", 1), attrs), false);
      assert.equal(matchCond(cond("app", "semverGte", "2.9"), attrs), true);
      assert.equal(matchCond(cond("app", "semverGte", "2.10.1"), attrs), true);
      assert.equal(matchCond(cond("app", "semverGte", "2.10.2"), attrs), false);
      assert.equal(matchCond(cond("app", "semverGte", "3"), attrs), false);
      assert.equal(matchCond(cond("app", "semverGte", "beta"), attrs), false);
      assert.equal(matchCond(cond("n", "semverGte", "1"), attrs), false);
    });

    test("evaluate: disabled and default", () => {
      assert.deepEqual(evaluate({ key: "f", enabled: false, rollout: 100 }, ctx("u1")), { on: false, reason: "disabled" });
      assert.deepEqual(evaluate({ key: "f", enabled: true }, ctx("u1")), { on: true, reason: "default" });
    });

    test("evaluate: allow and deny lists", () => {
      const flag: Flag = { key: "f", enabled: true, allow: ["vip", "both"], deny: ["banned", "both"], rollout: 0 };
      assert.deepEqual(evaluate(flag, ctx("vip")), { on: true, reason: "allowed" });
      assert.deepEqual(evaluate(flag, ctx("banned")), { on: false, reason: "denied" });
      assert.deepEqual(evaluate(flag, ctx("both")), { on: false, reason: "denied" });
      assert.deepEqual(evaluate(flag, ctx("other")), { on: false, reason: "rollout" });
      const open: Flag = { key: "f", enabled: true, deny: ["banned"] };
      assert.deepEqual(evaluate(open, ctx("banned")), { on: false, reason: "denied" });
      assert.deepEqual(evaluate(open, ctx("ok")), { on: true, reason: "default" });
    });

    test("evaluate: rollout percentages", () => {
      const users = ["u3", "u7", "u12", "alice", "u4", "u11", "u8", "u1", "u5", "u10", "u9", "erin", "dave", "u2", "carol", "u6", "bob"];
      const at = (pct: number) => users.filter((u) => evaluate({ key: "new-checkout", enabled: true, rollout: pct }, ctx(u)).on);
      assert.deepEqual(at(0), []);
      assert.deepEqual(at(100), users);
      assert.deepEqual(at(30), ["u3", "u7", "u12"]);
      assert.deepEqual(at(50), ["u3", "u7", "u12", "alice", "u4", "u11"]);
      assert.deepEqual(at(51.5), ["u3", "u7", "u12", "alice", "u4", "u11", "u8"]);
      assert.deepEqual(at(99.93), users.slice(0, 16));
      assert.deepEqual(at(99.94), users);
    });

    test("evaluate: the rollout threshold is exclusive and rounds to 0.01 percent", () => {
      const on = (pct: number) => evaluate({ key: "new-checkout", enabled: true, rollout: pct }, ctx("u12")).on;
      assert.equal(on(23.73), false);
      assert.equal(on(23.74), false);
      assert.equal(on(23.75), true);
      assert.equal(on(23.7449), false);
      assert.equal(on(23.7451), true);
    });

    test("evaluate: salt changes the buckets", () => {
      const flag: Flag = { key: "new-checkout", enabled: true, rollout: 10, salt: "s2" };
      assert.equal(evaluate(flag, ctx("u4")).on, true);
      assert.equal(evaluate(flag, ctx("u8")).on, true);
      assert.equal(evaluate(flag, ctx("u1")).on, false);
      assert.equal(evaluate({ ...flag, salt: undefined }, ctx("u4")).on, false);
      assert.equal(evaluate({ ...flag, salt: "" }, ctx("u4")).on, false);
      assert.equal(evaluate({ ...flag, rollout: 5 }, ctx("u4")).on, true);
      assert.equal(evaluate({ ...flag, rollout: 0.8 }, ctx("u4")).on, false);
      assert.equal(evaluate({ ...flag, rollout: 0.83 }, ctx("u4")).on, true);
    });

    test("evaluate: the first matching rule decides", () => {
      const flag: Flag = {
        key: "f",
        enabled: true,
        rollout: 0,
        rules: [
          { when: [cond("plan", "eq", "free")], serve: "off" },
          { when: [cond("country", "in", ["NO", "SE"]), cond("age", "gte", 18)], serve: "on" },
          { when: [], serve: { rollout: 100 } },
        ],
      };
      assert.deepEqual(evaluate(flag, ctx("u1", { plan: "free", country: "NO", age: 40 })), { on: false, reason: "rule:0" });
      assert.deepEqual(evaluate(flag, ctx("u1", { plan: "pro", country: "NO", age: 40 })), { on: true, reason: "rule:1" });
      assert.deepEqual(evaluate(flag, ctx("u1", { plan: "pro", country: "NO", age: 17 })), { on: true, reason: "rule:2" });
      assert.deepEqual(evaluate(flag, ctx("u1", { plan: "pro", country: "DE", age: 40 })), { on: true, reason: "rule:2" });
      assert.deepEqual(evaluate(flag, ctx("u1")), { on: true, reason: "rule:2" });
    });

    test("evaluate: all conditions of a rule must match, and no match falls through", () => {
      const flag: Flag = { key: "f", enabled: true, rollout: 0, rules: [{ when: [cond("a", "eq", 1), cond("b", "eq", 2)], serve: "on" }] };
      assert.deepEqual(evaluate(flag, ctx("u", { a: 1, b: 2 })), { on: true, reason: "rule:0" });
      assert.deepEqual(evaluate(flag, ctx("u", { a: 1, b: 3 })), { on: false, reason: "rollout" });
      assert.deepEqual(evaluate(flag, ctx("u", { a: 0, b: 2 })), { on: false, reason: "rollout" });
      assert.deepEqual(evaluate(flag, { userId: "u" }), { on: false, reason: "rollout" });
    });

    test("evaluate: rule rollouts use the flag key and salt", () => {
      const flag: Flag = { key: "new-checkout", enabled: true, rules: [{ when: [cond("x", "eq", 1)], serve: { rollout: 30 } }], salt: "" };
      const run = (u: string) => evaluate(flag, ctx(u, { x: 1 }));
      assert.deepEqual(run("u3"), { on: true, reason: "rule:0" });
      assert.deepEqual(run("u1"), { on: false, reason: "rule:0" });
      assert.deepEqual(evaluate({ ...flag, rules: [{ when: [], serve: { rollout: 0 } }] }, ctx("u3")), { on: false, reason: "rule:0" });
    });

    test("evaluate: allow and deny come before the rules", () => {
      const flag: Flag = { key: "f", enabled: true, allow: ["a"], deny: ["d"], rules: [{ when: [], serve: "off" }] };
      assert.deepEqual(evaluate(flag, ctx("a")), { on: true, reason: "allowed" });
      assert.deepEqual(evaluate(flag, ctx("d")), { on: false, reason: "denied" });
      assert.deepEqual(evaluate(flag, ctx("z")), { on: false, reason: "rule:0" });
    });

    test("evaluate: prerequisites", () => {
      const flags: Record<string, Flag> = {
        base: { key: "base", enabled: true, rollout: 50 },
        off: { key: "off", enabled: false },
        child: { key: "child", enabled: true, requires: ["base"] },
        multi: { key: "multi", enabled: true, requires: ["base", "off"] },
        missing: { key: "missing", enabled: true, requires: ["nope"] },
        deep: { key: "deep", enabled: true, requires: ["child"] },
      };
      // buckets of "base": u1 2680 (inside 50%), u3 7918 (outside)
      assert.deepEqual(evaluate(flags.child, ctx("u1"), flags), { on: true, reason: "default" });
      assert.deepEqual(evaluate(flags.child, ctx("u3"), flags), { on: false, reason: "prerequisite:base" });
      assert.deepEqual(evaluate(flags.multi, ctx("u1"), flags), { on: false, reason: "prerequisite:off" });
      assert.deepEqual(evaluate(flags.multi, ctx("u3"), flags), { on: false, reason: "prerequisite:base" });
      assert.deepEqual(evaluate(flags.missing, ctx("u1"), flags), { on: false, reason: "prerequisite-missing:nope" });
      assert.deepEqual(evaluate(flags.deep, ctx("u1"), flags), { on: true, reason: "default" });
      assert.deepEqual(evaluate(flags.deep, ctx("u3"), flags), { on: false, reason: "prerequisite:child" });
      assert.deepEqual(evaluate(flags.child, ctx("u1")), { on: false, reason: "prerequisite-missing:base" });
    });

    test("evaluate: prerequisites use their own rollout key, and the disabled check comes first", () => {
      const flags: Record<string, Flag> = {
        a: { key: "a", enabled: true, rollout: 30 },
        b: { key: "b", enabled: false, requires: ["zzz"] },
      };
      const p: Flag = { key: "p", enabled: true, requires: ["a"] };
      // buckets of "a": u6 1065 (inside 30%), u3 3922 (outside), u12 1370 (inside)
      assert.deepEqual(evaluate(p, ctx("u6"), flags), { on: true, reason: "default" });
      assert.deepEqual(evaluate(p, ctx("u12"), flags), { on: true, reason: "default" });
      assert.deepEqual(evaluate(p, ctx("u3"), flags), { on: false, reason: "prerequisite:a" });
      assert.deepEqual(evaluate(flags.b, ctx("u"), flags), { on: false, reason: "disabled" });
    });

    test("evaluate: prerequisite cycles are errors", () => {
      const flags: Record<string, Flag> = {
        a: { key: "a", enabled: true, requires: ["b"] },
        b: { key: "b", enabled: true, requires: ["a"] },
        self: { key: "self", enabled: true, requires: ["self"] },
      };
      assert.throws(() => evaluate(flags.a, ctx("u"), flags), Error);
      assert.throws(() => evaluate(flags.self, ctx("u"), flags), Error);
    });

    test("evaluate: a shared prerequisite is not a cycle", () => {
      const flags: Record<string, Flag> = {
        base: { key: "base", enabled: true },
        l: { key: "l", enabled: true, requires: ["base"] },
        r: { key: "r", enabled: true, requires: ["base"] },
        top: { key: "top", enabled: true, requires: ["l", "r", "base"] },
      };
      assert.deepEqual(evaluate(flags.top, ctx("u"), flags), { on: true, reason: "default" });
    });
''')

LIB = Lib(
    name="flagrules", lang="typescript", title="the flagrules evaluator",
    blurb="The web app's experiment framework asks flagrules whether a feature is on for a given user.",
    files={"package.json": PACKAGE_JSON % "flagrules", "tsconfig.json": TSCONFIG, "types/node-shim.d.ts": TS_NODE_SHIM,
           "src/hash.ts": HASH, "src/cond.ts": COND, "src/evaluate.ts": EVALUATE, "README.md": README, ".gitignore": "node_modules/\nbuild/\n"},
    visible_tests={"test/basic.test.ts": VISIBLE},
    hidden_tests={"test/full.test.ts": HIDDEN},
    mutate=["src/evaluate.ts", "src/cond.ts", "src/hash.ts"], difficulty=4, tags=["feature-flags", "rollout", "hashing"],
    verify=TS_VERIFY,
    probe_import="const { fnv1a, bucket } = require('./build/src/hash');\nconst { compareVersions, matchCond } = require('./build/src/cond');\nconst { evaluate } = require('./build/src/evaluate');",
    probes=[
        "fnv1a('foobar')",
        "fnv1a('a')",
        "bucket('new-checkout', 'u1')",
        "bucket('new-checkout', 'u4', 's2')",
        "compareVersions('1.10', '1.9')",
        "compareVersions('1.2', '1.2.0')",
        "compareVersions('1.2.1', '1.2')",
        "compareVersions('1.x', '1.2')",
        "matchCond({ attr: 'age', op: 'gt', value: 30 }, { age: 30 })",
        "matchCond({ attr: 'age', op: 'gte', value: 30 }, { age: 30 })",
        "matchCond({ attr: 'nope', op: 'ne', value: 'x' }, {})",
        "matchCond({ attr: 'nope', op: 'in', value: ['x'] }, {})",
        "matchCond({ attr: 'plan', op: 'nin', value: 'free' }, { plan: 'pro' })",
        "matchCond({ attr: 'app', op: 'semverGte', value: '2.10.2' }, { app: '2.10.1' })",
        "matchCond({ attr: 'app', op: 'semverGte', value: '2.9' }, { app: '2.10.1' })",
        "evaluate({ key: 'new-checkout', enabled: true, rollout: 23.74 }, { userId: 'u12' })",
        "evaluate({ key: 'new-checkout', enabled: true, rollout: 23.75 }, { userId: 'u12' })",
        "evaluate({ key: 'new-checkout', enabled: true, rollout: 50 }, { userId: 'u8' })",
        "evaluate({ key: 'f', enabled: true, allow: ['both'], deny: ['both'] }, { userId: 'both' })",
        "evaluate({ key: 'f', enabled: true, rollout: 0, rules: [{ when: [{ attr: 'a', op: 'eq', value: 1 }, { attr: 'b', op: 'eq', value: 2 }], serve: 'on' }] }, { userId: 'u', attrs: { a: 1, b: 3 } })",
        "evaluate({ key: 'f', enabled: true, requires: ['nope'] }, { userId: 'u' }, {})",
        "evaluate({ key: 'c', enabled: true, requires: ['base'] }, { userId: 'u3' }, { base: { key: 'base', enabled: true, rollout: 50 } })",
        "evaluate({ key: 's', enabled: true, requires: ['s'] }, { userId: 'u' }, { s: { key: 's', enabled: true, requires: ['s'] } })",
    ],
)

register_libs([LIB], n=8)
