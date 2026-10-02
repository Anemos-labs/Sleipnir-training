"""Mail routing rules with globs, headers and actions (typescript): bugs injected into a small rule engine."""
from fx import Lib, dd
from generators.fix._lang2 import PACKAGE_JSON, TS_NODE_SHIM, TS_VERIFY, TSCONFIG, register_libs

README = dd(r'''
    # mailrules

    The server-side filters of a small mail service. TypeScript, no dependencies.
    `import { globToRegExp, globMatch } from './src/glob'`, `import { matchCond } from './src/match'`,
    `import { route } from './src/engine'`.

    ## `src/glob.ts`

    `globToRegExp(glob, caseSensitive = false)` builds an anchored regular expression (it must match the whole text, and `.`
    also matches a newline): `*` matches any run of characters (also none), `?` exactly one character, every other character
    stands for itself (regular expression characters are escaped). Matching ignores letter case unless `caseSensitive`.
    `globMatch(glob, text, caseSensitive = false)` tests a text.

    ## `src/match.ts`: `matchCond(cond, msg)`

    A message is `{ from, to, subject, size, headers }` (`to` is an array, `headers` maps header names to values). A condition is
    `{ field, op, value, caseSensitive?, negate? }`.

    * Candidate texts by field: `from` gives `[msg.from]`; `to` gives all recipients; `subject` gives `[msg.subject]`; `size`
      gives `[String(msg.size)]`; `header:Name` gives the value of that header, looked up with the name compared ignoring
      case, as a one-element array, or `[]` when the message has no such header.
    * Text operators `contains`, `equals`, `glob` and `regex` hold when **some** candidate satisfies them (so a condition on
      `to` is true if any recipient matches; with no candidates it is false). `contains` is substring search, `equals`
      compares the whole text, `glob` uses `globMatch` and `regex` tests `new RegExp(value)` (flag `i` unless `caseSensitive`);
      `contains` and `equals` also ignore letter case unless `caseSensitive`. `value` is converted with `String()`.
    * `gt` and `lt` are numeric and use the number in `value`: for the field `size` the size of the message, for a header the
      header's text converted with `Number`; a missing header or one that is not a finite number is false. `gt` and `lt` are
      strict.
    * `negate` inverts the final outcome (so `negate` on a condition about a missing header is true).

    ## `src/engine.ts`: `route(rules, msg)`

    A rule is `{ name, when, any?, actions, stop? }`. It matches when **all** conditions of `when` match, or, with `any: true`,
    when at least one does; a rule with an empty `when` matches always (`any` or not). Rules are tried in order. For every matching
    rule its name is appended to `applied` and its actions are executed in order:

    | action | effect |
    |---|---|
    | `{ type: 'folder', name }` | sets the folder, but only if no earlier rule or action already did; the default folder is `'inbox'` |
    | `{ type: 'label', name }` | adds the label unless the message already has it (labels keep their order) |
    | `{ type: 'forward', to }` | adds the address unless already listed |
    | `{ type: 'flag' }` | `flagged` becomes `true` |
    | `{ type: 'priority', level }` | `priority` becomes the larger of the old value and `level` (starts at `0`) |
    | `{ type: 'drop' }` | `dropped` becomes `true` and no further actions or rules run (the rule's name is still in `applied`) |

    After the actions of a rule with `stop: true`, no further rules run. **Loop guard:** if the message has a header `X-Hops` (name
    compared ignoring case) whose value as a number is `>= 5`, `forward` actions are not executed; instead the label `'loop'` is
    added (once).

    The result is `{ folder, labels, forwards, flagged, priority, dropped, applied }`.
''')

GLOB = dd(r'''
    export function globToRegExp(glob: string, caseSensitive = false): RegExp {
      let source = "";
      for (const ch of glob) {
        if (ch === "*") source += ".*";
        else if (ch === "?") source += ".";
        else source += ch.replace(/[.+^${}()|[\]\\]/g, "\\$&");
      }
      return new RegExp(`^${source}$`, caseSensitive ? "s" : "is");
    }

    export function globMatch(glob: string, text: string, caseSensitive = false): boolean {
      return globToRegExp(glob, caseSensitive).test(text);
    }
''')

MATCH = dd(r'''
    import { globMatch } from "./glob";

    export interface Message {
      from: string;
      to: string[];
      subject: string;
      size: number;
      headers: Record<string, string>;
    }

    export interface Cond {
      field: string;
      op: "contains" | "equals" | "glob" | "regex" | "gt" | "lt";
      value: string | number;
      caseSensitive?: boolean;
      negate?: boolean;
    }

    export function header(msg: Message, name: string): string | undefined {
      const key = Object.keys(msg.headers).find((k) => k.toLowerCase() === name.toLowerCase());
      return key === undefined ? undefined : msg.headers[key];
    }

    function candidates(msg: Message, field: string): string[] {
      if (field === "from") return [msg.from];
      if (field === "to") return msg.to;
      if (field === "subject") return [msg.subject];
      if (field === "size") return [String(msg.size)];
      if (field.startsWith("header:")) {
        const v = header(msg, field.slice(7));
        return v === undefined ? [] : [v];
      }
      throw new RangeError(`unknown field ${field}`);
    }

    function textTest(cond: Cond, candidate: string): boolean {
      const exact = cond.caseSensitive === true;
      const want = String(cond.value);
      switch (cond.op) {
        case "contains":
          return exact ? candidate.includes(want) : candidate.toLowerCase().includes(want.toLowerCase());
        case "equals":
          return exact ? candidate === want : candidate.toLowerCase() === want.toLowerCase();
        case "glob":
          return globMatch(want, candidate, exact);
        case "regex":
          return new RegExp(want, exact ? "" : "i").test(candidate);
        default:
          return false;
      }
    }

    export function matchCond(cond: Cond, msg: Message): boolean {
      let hit: boolean;
      if (cond.op === "gt" || cond.op === "lt") {
        let n: number;
        if (cond.field === "size") n = msg.size;
        else if (cond.field.startsWith("header:")) n = Number(header(msg, cond.field.slice(7)) ?? NaN);
        else n = NaN;
        const limit = Number(cond.value);
        hit = Number.isFinite(n) && (cond.op === "gt" ? n > limit : n < limit);
      } else {
        hit = candidates(msg, cond.field).some((c) => textTest(cond, c));
      }
      return cond.negate === true ? !hit : hit;
    }
''')

ENGINE = dd(r'''
    import { Cond, Message, header, matchCond } from "./match";

    export type Action =
      | { type: "folder"; name: string }
      | { type: "label"; name: string }
      | { type: "forward"; to: string }
      | { type: "flag" }
      | { type: "priority"; level: number }
      | { type: "drop" };

    export interface Rule {
      name: string;
      when: Cond[];
      any?: boolean;
      actions: Action[];
      stop?: boolean;
    }

    export interface Result {
      folder: string;
      labels: string[];
      forwards: string[];
      flagged: boolean;
      priority: number;
      dropped: boolean;
      applied: string[];
    }

    export function route(rules: Rule[], msg: Message): Result {
      const result: Result = { folder: "inbox", labels: [], forwards: [], flagged: false, priority: 0, dropped: false, applied: [] };
      let folderSet = false;
      const hops = Number(header(msg, "X-Hops") ?? 0);
      const looping = Number.isFinite(hops) && hops >= 5;
      for (const rule of rules) {
        const tests = rule.when.map((c) => matchCond(c, msg));
        const matched = rule.when.length === 0 || (rule.any === true ? tests.some(Boolean) : tests.every(Boolean));
        if (!matched) continue;
        result.applied.push(rule.name);
        for (const action of rule.actions) {
          if (action.type === "folder") {
            if (!folderSet) {
              result.folder = action.name;
              folderSet = true;
            }
          } else if (action.type === "label") {
            if (!result.labels.includes(action.name)) result.labels.push(action.name);
          } else if (action.type === "forward") {
            if (looping) {
              if (!result.labels.includes("loop")) result.labels.push("loop");
            } else if (!result.forwards.includes(action.to)) {
              result.forwards.push(action.to);
            }
          } else if (action.type === "flag") {
            result.flagged = true;
          } else if (action.type === "priority") {
            result.priority = Math.max(result.priority, action.level);
          } else {
            result.dropped = true;
            return result;
          }
        }
        if (rule.stop === true) break;
      }
      return result;
    }
''')

VISIBLE = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { globMatch } from "../src/glob";
    import { route } from "../src/engine";

    const msg = { from: "ann@corp.example", to: ["me@corp.example"], subject: "Weekly report", size: 1200, headers: {} };

    test("glob", () => {
      assert.equal(globMatch("*@corp.example", "ann@corp.example"), true);
      assert.equal(globMatch("a?c", "abc"), true);
    });

    test("default folder is the inbox", () => {
      assert.equal(route([], msg).folder, "inbox");
    });
''')

HIDDEN = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { globToRegExp, globMatch } from "../src/glob";
    import { matchCond, header, Cond, Message } from "../src/match";
    import { route, Rule } from "../src/engine";

    const msg = (over: Partial<Message> = {}): Message => ({
      from: "Ann <ann@corp.example>",
      to: ["me@corp.example", "team@lists.example"],
      subject: "Weekly report: Q3",
      size: 1200,
      headers: { "List-Id": "team.lists.example", "X-Priority": "2", Precedence: "bulk" },
      ...over,
    });
    const c = (field: string, op: Cond["op"], value: string | number, more: Partial<Cond> = {}): Cond => ({ field, op, value, ...more });

    test("globToRegExp builds anchored patterns", () => {
      assert.equal(globToRegExp("a*b").source, "^a.*b$");
      assert.equal(globToRegExp("a?b").source, "^a.b$");
      assert.equal(globToRegExp("a.b+c").source, "^a\\.b\\+c$");
      assert.equal(globToRegExp("x").flags, "is");
      assert.equal(globToRegExp("x", true).flags, "s");
    });

    test("globMatch", () => {
      assert.equal(globMatch("*", ""), true);
      assert.equal(globMatch("*", "anything at all"), true);
      assert.equal(globMatch("a*b", "ab"), true);
      assert.equal(globMatch("a*b", "axxxb"), true);
      assert.equal(globMatch("a*b", "axxxbc"), false);
      assert.equal(globMatch("a*b", "xab"), false);
      assert.equal(globMatch("a?c", "abc"), true);
      assert.equal(globMatch("a?c", "ac"), false);
      assert.equal(globMatch("a?c", "abbc"), false);
      assert.equal(globMatch("?", ""), false);
      assert.equal(globMatch("a.c", "a.c"), true);
      assert.equal(globMatch("a.c", "abc"), false);
      assert.equal(globMatch("(x)", "(x)"), true);
      assert.equal(globMatch("[ab]", "[ab]"), true);
      assert.equal(globMatch("[ab]", "a"), false);
      assert.equal(globMatch("1+1", "1+1"), true);
      assert.equal(globMatch("1+1", "111"), false);
      assert.equal(globMatch("^$", "^$"), true);
      assert.equal(globMatch("a|b", "a"), false);
      assert.equal(globMatch("a|b", "a|b"), true);
      assert.equal(globMatch("{1}", "{1}"), true);
      assert.equal(globMatch("back\\slash", "back\\slash"), true);
      assert.equal(globMatch("l*", "line1\nline2"), true);
      assert.equal(globMatch("a?b", "a\nb"), true);
      assert.equal(globMatch("*@corp.example", "ann@corp.example"), true);
    });

    test("globMatch case handling", () => {
      assert.equal(globMatch("ABC", "abc"), true);
      assert.equal(globMatch("ABC", "abc", true), false);
      assert.equal(globMatch("a*Z", "aXz", false), true);
      assert.equal(globMatch("a*Z", "aXz", true), false);
      assert.equal(globMatch("a*Z", "aXZ", true), true);
    });

    test("header lookup ignores the case of the name", () => {
      const m = msg();
      assert.equal(header(m, "list-id"), "team.lists.example");
      assert.equal(header(m, "LIST-ID"), "team.lists.example");
      assert.equal(header(m, "precedence"), "bulk");
      assert.equal(header(m, "x-nothing"), undefined);
    });

    test("contains and equals", () => {
      const m = msg();
      assert.equal(matchCond(c("subject", "contains", "report"), m), true);
      assert.equal(matchCond(c("subject", "contains", "REPORT"), m), true);
      assert.equal(matchCond(c("subject", "contains", "REPORT", { caseSensitive: true }), m), false);
      assert.equal(matchCond(c("subject", "contains", "Report: Q3", { caseSensitive: true }), m), false);
      assert.equal(matchCond(c("subject", "contains", "report: q3"), m), true);
      assert.equal(matchCond(c("subject", "contains", "nothing"), m), false);
      assert.equal(matchCond(c("subject", "equals", "weekly report: q3"), m), true);
      assert.equal(matchCond(c("subject", "equals", "weekly report"), m), false);
      assert.equal(matchCond(c("subject", "equals", "weekly report: q3", { caseSensitive: true }), m), false);
      assert.equal(matchCond(c("subject", "equals", "Weekly report: Q3", { caseSensitive: true }), m), true);
      assert.equal(matchCond(c("from", "contains", "ann@"), m), true);
    });

    test("glob and regex conditions", () => {
      const m = msg();
      assert.equal(matchCond(c("from", "glob", "*<ann@corp.example>"), m), true);
      assert.equal(matchCond(c("from", "glob", "ann@corp.example"), m), false);
      assert.equal(matchCond(c("from", "glob", "ANN <*"), m), true);
      assert.equal(matchCond(c("from", "glob", "ANN <*", { caseSensitive: true }), m), false);
      assert.equal(matchCond(c("subject", "regex", "^weekly"), m), true);
      assert.equal(matchCond(c("subject", "regex", "^weekly", { caseSensitive: true }), m), false);
      assert.equal(matchCond(c("subject", "regex", "Q[0-9]$", { caseSensitive: true }), m), true);
      assert.equal(matchCond(c("subject", "regex", "report"), m), true);
      assert.equal(matchCond(c("subject", "regex", "^report"), m), false);
    });

    test("to matches when any recipient matches", () => {
      const m = msg();
      assert.equal(matchCond(c("to", "equals", "team@lists.example"), m), true);
      assert.equal(matchCond(c("to", "equals", "me@corp.example"), m), true);
      assert.equal(matchCond(c("to", "glob", "*@lists.example"), m), true);
      assert.equal(matchCond(c("to", "contains", "nobody"), m), false);
      assert.equal(matchCond(c("to", "contains", "x"), msg({ to: [] })), false);
      assert.equal(matchCond(c("to", "contains", "x", { negate: true }), msg({ to: [] })), true);
    });

    test("header conditions", () => {
      const m = msg();
      assert.equal(matchCond(c("header:List-Id", "contains", "lists"), m), true);
      assert.equal(matchCond(c("header:list-id", "equals", "TEAM.LISTS.EXAMPLE"), m), true);
      assert.equal(matchCond(c("header:X-Nothing", "contains", ""), m), false);
      assert.equal(matchCond(c("header:X-Nothing", "contains", "", { negate: true }), m), true);
      assert.equal(matchCond(c("header:Precedence", "glob", "bu*"), m), true);
    });

    test("numeric conditions", () => {
      const m = msg();
      assert.equal(matchCond(c("size", "gt", 1199), m), true);
      assert.equal(matchCond(c("size", "gt", 1200), m), false);
      assert.equal(matchCond(c("size", "lt", 1201), m), true);
      assert.equal(matchCond(c("size", "lt", 1200), m), false);
      assert.equal(matchCond(c("size", "gt", "1000"), m), true);
      assert.equal(matchCond(c("header:X-Priority", "lt", 3), m), true);
      assert.equal(matchCond(c("header:X-Priority", "gt", 2), m), false);
      assert.equal(matchCond(c("header:X-Priority", "gt", 1), m), true);
      assert.equal(matchCond(c("header:Precedence", "gt", 0), m), false);
      assert.equal(matchCond(c("header:Precedence", "lt", 100), m), false);
      assert.equal(matchCond(c("header:X-Nothing", "lt", 100), m), false);
      assert.equal(matchCond(c("subject", "gt", 0), m), false);
      assert.equal(matchCond(c("size", "gt", 5, { negate: true }), m), false);
      assert.equal(matchCond(c("header:X-Nothing", "gt", 5, { negate: true }), m), true);
      assert.equal(matchCond(c("size", "equals", "1200"), m), true);
      assert.equal(matchCond(c("size", "lt", 5), msg({ size: 0 })), true);
    });

    test("negate and unknown fields", () => {
      const m = msg();
      assert.equal(matchCond(c("subject", "contains", "report", { negate: true }), m), false);
      assert.equal(matchCond(c("subject", "contains", "zzz", { negate: true }), m), true);
      assert.throws(() => matchCond(c("cc", "contains", "x"), m), RangeError);
    });

    const rules: Rule[] = [
      { name: "lists", when: [c("header:List-Id", "contains", "lists.example")], actions: [{ type: "label", name: "list" }, { type: "folder", name: "Lists" }] },
      { name: "boss", when: [c("from", "contains", "boss@")], actions: [{ type: "priority", level: 2 }, { type: "flag" }, { type: "folder", name: "VIP" }] },
      { name: "reports", when: [c("subject", "glob", "*report*"), c("size", "lt", 5000)], actions: [{ type: "label", name: "reports" }, { type: "priority", level: 1 }] },
      { name: "big", when: [c("size", "gt", 5000)], actions: [{ type: "label", name: "big" }, { type: "folder", name: "Big" }], stop: true },
      { name: "audit", when: [], actions: [{ type: "forward", to: "audit@corp.example" }, { type: "label", name: "list" }] },
    ];

    test("route: defaults", () => {
      assert.deepEqual(route([], msg()), { folder: "inbox", labels: [], forwards: [], flagged: false, priority: 0, dropped: false, applied: [] });
      assert.deepEqual(route([{ name: "never", when: [c("subject", "equals", "zzz")], actions: [{ type: "flag" }] }], msg()).applied, []);
    });

    test("route: several rules, first folder wins, labels and priority accumulate", () => {
      const r = route(rules, msg({ from: "boss@corp.example" }));
      assert.deepEqual(r, {
        folder: "Lists", labels: ["list", "reports"], forwards: ["audit@corp.example"], flagged: true, priority: 2, dropped: false,
        applied: ["lists", "boss", "reports", "audit"],
      });
    });

    test("route: priority is the maximum, not the last", () => {
      const rs: Rule[] = [
        { name: "a", when: [], actions: [{ type: "priority", level: 5 }] },
        { name: "b", when: [], actions: [{ type: "priority", level: 3 }] },
      ];
      assert.equal(route(rs, msg()).priority, 5);
      assert.equal(route([{ name: "neg", when: [], actions: [{ type: "priority", level: -4 }] }], msg()).priority, 0);
    });

    test("route: stop ends the rule list after the rule's actions", () => {
      const r = route(rules, msg({ size: 9000 }));
      assert.deepEqual(r.applied, ["lists", "big"]);
      assert.equal(r.folder, "Lists");
      assert.deepEqual(r.labels, ["list", "big"]);
      assert.deepEqual(r.forwards, []);
      const only = route(rules, msg({ size: 9000, headers: {} }));
      assert.equal(only.folder, "Big");
      assert.deepEqual(only.applied, ["big"]);
    });

    test("route: all conditions must match, or any with any:true", () => {
      const all: Rule = { name: "all", when: [c("subject", "contains", "report"), c("size", "gt", 5000)], actions: [{ type: "flag" }] };
      const any: Rule = { name: "any", any: true, when: [c("subject", "contains", "report"), c("size", "gt", 5000)], actions: [{ type: "flag" }] };
      assert.deepEqual(route([all], msg()).applied, []);
      assert.deepEqual(route([any], msg()).applied, ["any"]);
      assert.deepEqual(route([any], msg({ subject: "hello", size: 9000 })).applied, ["any"]);
      assert.deepEqual(route([any], msg({ subject: "hello" })).applied, []);
      assert.deepEqual(route([all], msg({ size: 9000 })).applied, ["all"]);
      assert.deepEqual(route([{ ...any, when: [] }], msg()).applied, ["any"]);
    });

    test("route: labels and forwards are not repeated", () => {
      const rs: Rule[] = [
        { name: "one", when: [], actions: [{ type: "label", name: "x" }, { type: "label", name: "x" }, { type: "forward", to: "a@x" }, { type: "forward", to: "a@x" }, { type: "forward", to: "b@x" }] },
        { name: "two", when: [], actions: [{ type: "label", name: "y" }, { type: "label", name: "x" }, { type: "forward", to: "a@x" }] },
      ];
      const r = route(rs, msg());
      assert.deepEqual(r.labels, ["x", "y"]);
      assert.deepEqual(r.forwards, ["a@x", "b@x"]);
    });

    test("route: the first folder action wins even within one rule", () => {
      const rs: Rule[] = [{ name: "f", when: [], actions: [{ type: "folder", name: "A" }, { type: "folder", name: "B" }] }, { name: "g", when: [], actions: [{ type: "folder", name: "C" }] }];
      assert.equal(route(rs, msg()).folder, "A");
      const inbox: Rule[] = [{ name: "f", when: [], actions: [{ type: "folder", name: "inbox" }] }, { name: "g", when: [], actions: [{ type: "folder", name: "Late" }] }];
      assert.equal(route(inbox, msg()).folder, "inbox");
    });

    test("route: drop stops everything", () => {
      const rs: Rule[] = [
        { name: "spam", when: [c("subject", "contains", "report")], actions: [{ type: "label", name: "spam" }, { type: "drop" }, { type: "label", name: "after" }, { type: "flag" }] },
        { name: "later", when: [], actions: [{ type: "label", name: "never" }] },
      ];
      const r = route(rs, msg());
      assert.deepEqual(r, { folder: "inbox", labels: ["spam"], forwards: [], flagged: false, priority: 0, dropped: true, applied: ["spam"] });
    });

    test("route: the loop guard turns forwards into a label", () => {
      const fwd: Rule = { name: "fwd", when: [], actions: [{ type: "forward", to: "x@y" }, { type: "forward", to: "z@y" }, { type: "label", name: "seen" }] };
      const four = route([fwd], msg({ headers: { "X-Hops": "4" } }));
      assert.deepEqual(four.forwards, ["x@y", "z@y"]);
      assert.deepEqual(four.labels, ["seen"]);
      const five = route([fwd], msg({ headers: { "x-hops": "5" } }));
      assert.deepEqual(five.forwards, []);
      assert.deepEqual(five.labels, ["loop", "seen"]);
      const nine = route([fwd, fwd], msg({ headers: { "X-HOPS": "9" } }));
      assert.deepEqual(nine.labels, ["loop", "seen"]);
      const junk = route([fwd], msg({ headers: { "X-Hops": "many" } }));
      assert.deepEqual(junk.forwards, ["x@y", "z@y"]);
      const none = route([fwd], msg({ headers: {} }));
      assert.deepEqual(none.forwards, ["x@y", "z@y"]);
      const zero = route([fwd], msg({ headers: { "X-Hops": "0" } }));
      assert.deepEqual(zero.forwards, ["x@y", "z@y"]);
    });

    test("route: flagged and stop with no actions", () => {
      const rs: Rule[] = [{ name: "halt", when: [c("size", "gt", 0)], actions: [], stop: true }, { name: "never", when: [], actions: [{ type: "flag" }] }];
      const r = route(rs, msg());
      assert.equal(r.flagged, false);
      assert.deepEqual(r.applied, ["halt"]);
      const flagged = route([{ name: "f", when: [], actions: [{ type: "flag" }] }], msg());
      assert.equal(flagged.flagged, true);
    });
''')

LIB = Lib(
    name="mailrules", lang="typescript", title="the mailrules filter engine",
    blurb="The mail service sorts incoming messages into folders, labels and forwards with mailrules.",
    files={"package.json": PACKAGE_JSON % "mailrules", "tsconfig.json": TSCONFIG, "types/node-shim.d.ts": TS_NODE_SHIM,
           "src/glob.ts": GLOB, "src/match.ts": MATCH, "src/engine.ts": ENGINE, "README.md": README, ".gitignore": "node_modules/\nbuild/\n"},
    visible_tests={"test/basic.test.ts": VISIBLE},
    hidden_tests={"test/full.test.ts": HIDDEN},
    mutate=["src/engine.ts", "src/match.ts", "src/glob.ts"], difficulty=2, tags=["email", "rules", "glob"],
    verify=TS_VERIFY,
    probe_import=("const { globToRegExp, globMatch } = require('./build/src/glob');\nconst { matchCond, header } = require('./build/src/match');\nconst { route } = require('./build/src/engine');"),
    probes=[
        "globMatch('a*b', 'axxxbc')", "globMatch('a?c', 'ac')", "globMatch('a.c', 'abc')", "globMatch('1+1', '111')", "globMatch('ABC', 'abc', true)", "globMatch('l*', 'line1\\nline2')", "globMatch('[ab]', 'a')",
        "header({ headers: { 'List-Id': 'x' } }, 'list-id')",
        "matchCond({ field: 'subject', op: 'contains', value: 'REPORT', caseSensitive: true }, { from: 'a', to: [], subject: 'weekly report', size: 1, headers: {} })",
        "matchCond({ field: 'size', op: 'gt', value: 1200 }, { from: 'a', to: [], subject: '', size: 1200, headers: {} })",
        "matchCond({ field: 'header:X-Nothing', op: 'contains', value: '', negate: true }, { from: 'a', to: [], subject: '', size: 1, headers: {} })",
        "matchCond({ field: 'header:X-Priority', op: 'gt', value: 1 }, { from: 'a', to: [], subject: '', size: 1, headers: { 'x-priority': '2' } })",
        "matchCond({ field: 'to', op: 'glob', value: '*@lists.example' }, { from: 'a', to: ['me@corp.example', 'team@lists.example'], subject: '', size: 1, headers: {} })",
        "route([{ name: 'a', when: [], actions: [{ type: 'priority', level: 5 }] }, { name: 'b', when: [], actions: [{ type: 'priority', level: 3 }] }], { from: 'a', to: [], subject: '', size: 1, headers: {} }).priority",
        "route([{ name: 'f', when: [], actions: [{ type: 'folder', name: 'A' }, { type: 'folder', name: 'B' }] }], { from: 'a', to: [], subject: '', size: 1, headers: {} }).folder",
        "route([{ name: 'x', when: [], actions: [{ type: 'label', name: 'k' }, { type: 'label', name: 'k' }, { type: 'forward', to: 'a@x' }, { type: 'forward', to: 'a@x' }] }], { from: 'a', to: [], subject: '', size: 1, headers: {} })",
        "route([{ name: 'fwd', when: [], actions: [{ type: 'forward', to: 'x@y' }] }], { from: 'a', to: [], subject: '', size: 1, headers: { 'x-hops': '5' } })",
        "route([{ name: 'fwd', when: [], actions: [{ type: 'forward', to: 'x@y' }] }], { from: 'a', to: [], subject: '', size: 1, headers: { 'X-Hops': '4' } }).forwards",
        "route([{ name: 'any', any: true, when: [{ field: 'subject', op: 'contains', value: 'zzz' }, { field: 'size', op: 'gt', value: 0 }], actions: [{ type: 'flag' }] }], { from: 'a', to: [], subject: 'hi', size: 1, headers: {} }).applied",
        "route([{ name: 'halt', when: [], actions: [], stop: true }, { name: 'never', when: [], actions: [{ type: 'flag' }] }], { from: 'a', to: [], subject: '', size: 1, headers: {} })",
        "route([{ name: 'spam', when: [], actions: [{ type: 'drop' }, { type: 'flag' }] }, { name: 'later', when: [], actions: [] }], { from: 'a', to: [], subject: '', size: 1, headers: {} })",
    ],
)

register_libs([LIB], n=8)
